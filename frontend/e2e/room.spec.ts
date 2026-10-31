import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";

const FURNIDATA = join(process.env.WB_E2E_DIR as string, "furnidata.json");

const furni = (classname: string, name: string, extra: object = {}) => ({
  id: classname.length,
  classname,
  revision: 100,
  name,
  description: `About ${name}`,
  offerid: 5,
  bc: true,
  xdim: 1,
  ydim: 1,
  height: 1,
  ...extra,
});

async function login(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("e2e test password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("link", { name: "Catalogue" })).toBeVisible();
}

type EditorElement = HTMLElement & {
  tileOnPage(x: number, y: number): { x: number; y: number } | null;
  roomDocument: {
    furni: { classname: string; x: number; y: number; rot: number; z: number; state: number }[];
    avatars: { x: number; y: number; pose: string; dir: number; z: number }[];
  };
};

async function clickTile(page: Page, x: number, y: number): Promise<void> {
  const point = await page.evaluate(
    ([tx, ty]) =>
      (document.querySelector("wb-editor") as EditorElement).tileOnPage(tx as number, ty as number),
    [x, y],
  );
  if (!point) throw new Error("The room is not drawn yet.");
  await page.mouse.move(point.x, point.y);
  await page.mouse.down();
  await page.mouse.up();
}

const room = (page: Page) =>
  page.evaluate(() => (document.querySelector("wb-editor") as EditorElement).roomDocument);

test("build a room, walk to a chair, sit, and find it all there after a reload", async ({
  page,
}) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(error.message));
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) problems.push(message.text());
  });

  writeFileSync(
    FURNIDATA,
    JSON.stringify({
      roomitemtypes: {
        furnitype: [
          furni("wf_act_show_message", "Show Message", { height: 0.65, canstandon: true }),
          furni("test_chair", "Test Chair", { cansiton: true }),
          furni("test_wall", "Test Block"),
        ],
      },
      wallitemtypes: { furnitype: [] },
    }),
  );
  await login(page);
  await page.getByTestId("download-button").or(page.getByTestId("update-button")).first().click();
  const dialog = page.getByTestId("update-dialog");
  await dialog.getByRole("button", { name: /Use this catalogue|Apply update/ }).click();
  await expect(page.getByTestId("furni-list")).toContainText("Show Message");

  await page.getByRole("link", { name: "Workspace" }).click();
  await page.getByRole("button", { name: "New sandbox" }).click();
  await page.getByRole("textbox", { name: "Name" }).fill("Walking room");
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByRole("button", { name: /^Walking room/ }).click();
  await page.getByRole("link", { name: "Open room" }).click();

  const canvas = page.getByTestId("room-canvas");
  await expect(canvas).toBeVisible();

  // Place a chair and a WIRED box, and a block in the way.
  await page.getByLabel("Search all furni").fill("test_chair");
  await page.locator('.palette-row[data-classname="test_chair"]').click();
  await expect(page.locator(".selection-bar")).toHaveAttribute("data-placing", "test_chair");
  await clickTile(page, 5, 2);
  await page.getByLabel("Search all furni").fill("test_wall");
  await page.locator('.palette-row[data-classname="test_wall"]').click();
  await expect(page.locator(".selection-bar")).toHaveAttribute("data-placing", "test_wall");
  await clickTile(page, 3, 2);
  await page.getByLabel("Search all furni").fill("");
  await page.locator('.palette-row[data-classname="wf_act_show_message"]').click();
  await expect(page.locator(".selection-bar")).toHaveAttribute(
    "data-placing",
    "wf_act_show_message",
  );
  await clickTile(page, 1, 1);
  await clickTile(page, 1, 1);
  await page.keyboard.press("Escape");
  let saved = await room(page);
  expect(saved.furni.map((f) => f.classname)).toEqual([
    "test_chair",
    "test_wall",
    "wf_act_show_message",
    "wf_act_show_message",
  ]);
  expect(saved.furni[3]?.z, "the second box stacks on the first").toBe(0.65);

  // Select, move with the arrows, turn, change state.
  await clickTile(page, 1, 1);
  await expect(page.getByTestId("inspector")).toContainText("wf_act_show_message");
  await page.getByRole("button", { name: "Move down right" }).click();
  await page.locator(".selection-bar").getByRole("button", { name: "Rotate" }).click();
  await page.getByTestId("inspector").getByRole("button", { name: "1", exact: true }).click();
  saved = await room(page);
  // The click lands on the lower box, because the upper one is drawn higher up the screen.
  const moved = saved.furni.find((f) => f.x === 2);
  expect([moved?.x, moved?.y, moved?.state]).toEqual([2, 1, 1]);
  expect(moved?.rot).toBe(4);
  expect(moved?.z, "nothing under it at its new spot").toBe(0);

  // Undo and redo.
  await page.getByRole("button", { name: "Undo" }).click();
  expect((await room(page)).furni.find((f) => f.x === 2)?.state).toBe(0);
  await page.getByRole("button", { name: "Redo" }).click();
  expect((await room(page)).furni.find((f) => f.x === 2)?.state).toBe(1);

  // Add an avatar and walk it, then sit.
  await page.getByRole("button", { name: "Add avatar" }).click();
  await page.getByRole("button", { name: "Play" }).click();
  await clickTile(page, 0, 2);
  await expect(page.getByTestId("walk-status")).toContainText("stopped at 0, 2", {
    timeout: 15000,
  });
  await clickTile(page, 5, 2);
  await expect(page.getByTestId("walk-status")).toContainText("walking to 5, 2");
  await expect(page.getByTestId("walk-status")).toContainText("sat down at 5, 2", {
    timeout: 15000,
  });
  const sitting = (await room(page)).avatars[0];
  expect(sitting).toMatchObject({ x: 5, y: 2, pose: "sit", z: 1 });

  // A blocked tile cannot be walked to.
  await clickTile(page, 3, 2);
  await expect(page.getByTestId("walk-status")).toContainText("cannot get there");

  // It saves by itself, and everything comes back after a reload.
  await expect(page.getByTestId("save-status")).toContainText("Saved", { timeout: 10000 });
  await page.reload();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  const reloaded = await room(page);
  expect(reloaded.avatars[0]).toMatchObject({ x: 5, y: 2, pose: "sit" });
  expect(reloaded.furni).toHaveLength(4);
  expect(reloaded.furni.find((f) => f.x === 2)).toMatchObject({ y: 1, state: 1 });

  // The room draws without errors under the real Content-Security-Policy.
  expect(problems).toEqual([]);
});

test("the phone layout of the editor has no sideways page scroll", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Workspace" }).click();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("button", { name: /^Walking room/ }).click();
  await page.getByRole("link", { name: "Open room" }).click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test("the furni card, click outside, shortcuts and repeated use", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Workspace" }).click();
  await page.getByRole("button", { name: "New sandbox" }).click();
  await page.getByRole("textbox", { name: "Name" }).fill("Shortcut room");
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByRole("button", { name: /^Shortcut room/ }).click();
  await page.getByRole("link", { name: "Open room" }).click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();

  const outside = async () => {
    const box = await page.getByTestId("room-canvas").boundingBox();
    await page.mouse.click((box?.x ?? 0) + 4, (box?.y ?? 0) + 4);
  };
  const bar = page.locator(".selection-bar");
  const first = async () => (await room(page)).furni[0];

  // Placing keeps going until a click outside the room stops it.
  await page.getByLabel("Search all furni").fill("test_chair");
  await page.locator('.palette-row[data-classname="test_chair"]').click();
  await expect(bar).toHaveAttribute("data-placing", "test_chair");
  await clickTile(page, 5, 2);
  await expect(bar).toHaveAttribute("data-placing", "test_chair");
  await outside();
  await expect(bar).not.toHaveAttribute("data-placing", "test_chair");
  expect((await room(page)).furni).toHaveLength(1);

  // The card and its actions.
  await clickTile(page, 5, 2);
  const card = page.getByTestId("furni-card");
  await expect(card).toContainText("Test Chair");
  await card.getByRole("button", { name: "Use" }).click();
  await expect.poll(async () => (await first())?.state).toBe(1);
  await card.getByRole("button", { name: "Use" }).click();
  await expect.poll(async () => (await first())?.state).toBe(0);
  await card.getByRole("button", { name: "Move" }).click();
  await expect(card).toBeHidden();
  await clickTile(page, 7, 2);
  await expect.poll(async () => (await first())?.x).toBe(7);

  // Shift turns, Ctrl moves, arrows nudge, P and Ctrl+Shift pick up, and undo restores.
  const startRot = (await first())?.rot;
  await page.keyboard.down("Shift");
  await clickTile(page, 7, 2);
  await page.keyboard.up("Shift");
  await expect.poll(async () => (await first())?.rot).not.toBe(startRot);
  await page.keyboard.down("Control");
  await clickTile(page, 7, 2);
  await page.keyboard.up("Control");
  await expect(bar).toContainText("Click a tile to move it");
  await page.keyboard.press("Escape");
  await clickTile(page, 7, 2);
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await first())?.x).toBe(6);
  await page.keyboard.press("p");
  await expect.poll(async () => (await room(page)).furni.length).toBe(0);
  await page.keyboard.press("ControlOrMeta+z");
  await expect.poll(async () => (await room(page)).furni.length).toBe(1);
  await page.keyboard.down("Control");
  await page.keyboard.down("Shift");
  await clickTile(page, 6, 2);
  await page.keyboard.up("Shift");
  await page.keyboard.up("Control");
  await expect.poll(async () => (await room(page)).furni.length).toBe(0);
  await page.keyboard.press("ControlOrMeta+z");

  // Using furni while running keeps working, which is the bug this replaces.
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByTestId("run-panel")).toBeVisible();
  const point = await page.evaluate(() =>
    (document.querySelector("wb-editor") as EditorElement).tileOnPage(6, 2),
  );
  const seen: (number | undefined)[] = [];
  for (let use = 0; use < 4; use += 1) {
    const answered = page.waitForResponse(
      async (res) =>
        res.url().includes("/run/input") && res.request().postData()?.includes('"use"') === true,
    );
    await page.mouse.dblclick(point?.x ?? 0, point?.y ?? 0);
    await answered;
    await page.waitForTimeout(50);
    seen.push((await first())?.state);
  }
  expect(seen).toEqual([1, 0, 1, 0]);
  await page.getByRole("button", { name: "Stop" }).first().click();

  // Both options can be turned off.
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByLabel("Clicking outside the room stops placing or moving").uncheck();
  await page.getByLabel("Ctrl+Shift+click and the P key pick up furni").uncheck();
  await page.getByRole("button", { name: "Save settings" }).click();
  await page.getByRole("link", { name: "Workspace" }).click();
  await page.getByRole("button", { name: /^Shortcut room/ }).click();
  await page.getByRole("link", { name: "Open room" }).click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByLabel("Search all furni").fill("test_chair");
  await page.locator('.palette-row[data-classname="test_chair"]').click();
  await expect(bar).toHaveAttribute("data-placing", "test_chair");
  await outside();
  await expect(bar).toHaveAttribute("data-placing", "test_chair");
  await page.keyboard.press("Escape");
  await clickTile(page, 6, 2);
  await expect(page.getByTestId("furni-card")).toBeVisible();
  await page.keyboard.press("p");
  expect((await room(page)).furni.length).toBe(1);
  await expect(page.getByTestId("furni-card")).not.toContainText("Ctrl+Shift");

  // Later tests expect the defaults.
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByLabel("Clicking outside the room stops placing or moving").check();
  await page.getByLabel("Ctrl+Shift+click and the P key pick up furni").check();
  await page.getByRole("button", { name: "Save settings" }).click();
});
