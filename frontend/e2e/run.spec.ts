import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";

const FURNIDATA = join(process.env.WB_E2E_DIR as string, "furnidata.json");
const furni = (classname: string, extra: object = {}) => ({
  id: classname.length,
  classname,
  revision: 100,
  name: classname,
  description: "",
  offerid: 5,
  bc: true,
  xdim: 1,
  ydim: 1,
  height: 0.65,
  canstandon: true,
  ...extra,
});

async function login(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("e2e test password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("link", { name: "Catalogue" })).toBeVisible();
}

test("the time tracking example runs in the browser and leaves the saved room alone", async ({
  page,
}) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(error.message));

  writeFileSync(
    FURNIDATA,
    JSON.stringify({
      roomitemtypes: {
        furnitype: [
          furni("chair_norja", { cansiton: true, canstandon: false, height: 1 }),
          furni("wf_antenna1"),
          furni("wf_antenna2"),
          furni("wf_var_user"),
          furni("wf_xtra_var_time_util"),
          furni("wf_trg_walks_on_furni"),
          furni("wf_act_give_var"),
          furni("wf_act_give_reward"),
        ],
      },
      wallitemtypes: { furnitype: [] },
    }),
  );
  await login(page);
  await page.getByTestId("download-button").or(page.getByTestId("update-button")).first().click();
  const update = page.getByTestId("update-dialog");
  await update.getByRole("button", { name: /Use this catalogue|Apply update/ }).click();
  await expect(page.getByTestId("furni-list")).toBeVisible();

  await page.getByRole("link", { name: "Workspace" }).click();
  await page.getByRole("button", { name: "Add time tracking example" }).click();
  await page
    .getByRole("button", { name: /^Time tracking example/ })
    .first()
    .click();
  await page.getByRole("link", { name: "Open room" }).click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();

  type Editor = HTMLElement & {
    tileOnPage(x: number, y: number): { x: number; y: number } | null;
    roomDocument: { avatars: { x: number; y: number }[] };
  };
  const click = async (x: number, y: number) => {
    const point = await page.evaluate(
      ([a, b]) =>
        (document.querySelector("wb-editor") as Editor).tileOnPage(a as number, b as number),
      [x, y],
    );
    if (!point) throw new Error("No room yet.");
    await page.mouse.move(point.x, point.y);
    await page.mouse.down();
    await page.mouse.up();
  };

  // A box shows its settings and how far to trust it.
  const inspector = page.getByTestId("inspector");
  await expect(async () => {
    await click(0, 2); // Art downloads first, and only drawn furni can be clicked.
    await expect(page.getByTestId("fidelity")).toBeVisible({ timeout: 500 });
  }).toPass({ timeout: 15000 });
  await expect(inspector).toContainText("Furni ID");
  await page.keyboard.press("Escape");

  // Run: sit, and time is banked by the keyword.
  await page.getByTestId("run-button").click();
  await expect(page.getByTestId("run-panel")).toBeVisible();
  await expect(page.getByTestId("run-trace")).toContainText("Room started");
  await click(4, 4);
  await expect(page.getByTestId("run-trace")).toContainText("Stack 0,2 runs", { timeout: 15000 });
  await expect(page.getByTestId("run-variables")).toContainText("on_duty");

  const command = page.getByTestId("run-command");
  await command.fill(":pause");
  await command.press("Enter");
  await expect(page.getByTestId("run-trace")).toContainText("Paused.");
  await command.fill(":step");
  await command.press("Enter");
  await expect(page.getByTestId("run-trace")).toContainText("Stepped to");
  await command.fill(":resume");
  await command.press("Enter");
  await command.fill("__import__('os')");
  await command.press("Enter");
  await expect(page.getByTestId("run-trace")).toContainText("says: __import__");

  await page.waitForTimeout(1500);
  await command.fill(":time");
  await command.press("Enter");
  await expect(page.getByTestId("run-trace")).toContainText("says: :time");
  await expect(page.getByTestId("run-variables")).toContainText("seconds", { timeout: 5000 });

  // Stopping restores the room as saved.
  await page.getByRole("button", { name: "Stop" }).first().click();
  await expect(page.getByTestId("run-panel")).toHaveCount(0);
  const avatar = await page.evaluate(
    () => (document.querySelector("wb-editor") as Editor).roomDocument.avatars[0],
  );
  expect(avatar).toMatchObject({ x: 4, y: 6 });
  await expect(page.getByTestId("save-status")).toContainText("Saved");
  expect(problems).toEqual([]);
});

test("the guide lists boxes, filters them and adds an example room", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  const list = page.getByTestId("guide-list");
  await expect(list).toContainText("wf_act_toggle_state");
  await expect(list).toContainText("Tried in a real room");
  await expect(page.getByTestId("guide-coverage")).toContainText("Checked in a real room");
  await page.getByLabel("All evidence").selectOption("real_room");
  await expect(list).toContainText("Checked in a real room on 2026-10-31");
  await page.getByLabel("All evidence").selectOption("");
  await page.getByLabel("Search boxes").fill("toggle_state");
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await page.getByLabel("Search boxes").fill("no such box");
  await expect(list).toContainText("No boxes match");
  await page.getByLabel("Search boxes").fill("");
  await page.getByLabel("All statuses").selectOption("real_room");
  await expect(list.getByRole("listitem")).toHaveCount(2);
  await page
    .getByTestId("tutorial-switch-flip")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await expect(page).toHaveURL(/\/sandbox\/\d+$/);
});

test("a box lists and highlights its picks", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-switch-flip")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeEnabled();
  const click = async (x: number, y: number) => {
    const point = await page.evaluate(
      ([tx, ty]) =>
        (
          document.querySelector("wb-editor") as unknown as {
            tileOnPage(a: number, b: number): { x: number; y: number };
          }
        ).tileOnPage(tx as number, ty as number),
      [x, y],
    );
    await page.mouse.click(point.x, point.y);
  };
  await click(4, 2);
  const inspector = page.getByTestId("inspector");
  const picks = inspector.getByTestId("picked-furni");
  await expect(picks.getByRole("listitem")).toHaveCount(1);
  await expect(picks).toContainText("at ");

  await inspector.getByRole("button", { name: /Pick in room/ }).click();
  await click(6, 4);
  await expect(picks.getByRole("listitem")).toHaveCount(2);
  await expect(picks).toContainText("at 6, 4");
  await picks
    .getByRole("button", { name: /Remove .* from the picks/ })
    .first()
    .click();
  await expect(picks.getByRole("listitem")).toHaveCount(1);
  await inspector.getByRole("button", { name: /Done picking/ }).click();
  await expect(picks).toContainText("at 6, 4");
  await picks.getByRole("button", { name: /Remove .* from the picks/ }).click();
  await expect(inspector).toContainText("Nothing picked yet.");
});
