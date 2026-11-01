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

async function clickTile(page: Page, x: number, y: number): Promise<void> {
  const point = await page.evaluate(
    ([tx, ty]) =>
      (
        document.querySelector("wb-editor") as unknown as {
          tileOnPage(x: number, y: number): { x: number; y: number } | null;
        }
      ).tileOnPage(tx as number, ty as number),
    [x, y],
  );
  if (!point) throw new Error("The room is not drawn yet.");
  await page.mouse.move(point.x, point.y);
  await page.mouse.down();
  await page.mouse.up();
}

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
  await expect(list.getByRole("listitem")).toHaveCount(87);
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

test("the stack checker lists problems and leads to the box", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-switch-flip")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  const check = page.getByRole("button", { name: "Check stacks" });
  await check.click();
  await expect(page.getByTestId("check-summary")).toContainText("No problems found");

  // Removing the trigger's picks breaks the stack.
  const point = await page.evaluate(() =>
    (
      document.querySelector("wb-editor") as unknown as {
        tileOnPage(a: number, b: number): { x: number; y: number };
      }
    ).tileOnPage(4, 2),
  );
  await page.mouse.click(point.x, point.y);
  await page
    .getByTestId("picked-furni")
    .getByRole("button", { name: /Remove/ })
    .click();
  await page.getByRole("button", { name: "Close" }).click();
  await check.click();
  await expect(page.getByTestId("check-summary")).toContainText("1 errors");
  const list = page.getByTestId("check-list");
  await expect(list).toContainText("It has no furni picked.");
  await list.getByRole("button").first().click();
  await expect(page.getByTestId("box-problems")).toContainText("It has no furni picked.");
});

test("the run panel lists a variable before anything holds it", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const row = page.locator(".run-vars tr", { hasText: "score" });
  await expect(row).toContainText("Nobody yet");
  await page.screenshot({ path: process.env.WB_SHOT ?? "test-results/defined-variable.png" });
});

test("a running user can be moved and turned from the inspector", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.locator(".avatar-row-pick").first().click();
  const panel = page.getByTestId("avatar-place");
  await panel.getByLabel("Column").fill("3");
  await panel.getByLabel("Row").fill("4");
  await panel.getByLabel("Direction").selectOption("5");
  await expect(page.getByTestId("avatar-position")).toContainText("3");
  await expect(page.getByTestId("avatar-position")).toContainText("4");
  await expect(panel.getByLabel("Direction")).toHaveValue("5");
});

test("walking loads every direction ahead for what the avatar holds and does", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.locator(".avatar-row-pick").first().click();
  const panel = page.getByTestId("avatar-place");
  await panel.getByLabel("Column").fill("3");
  await panel.getByLabel("Row").fill("1");
  await expect(panel.getByLabel("Column")).toHaveValue("3");
  await page.getByTestId("avatar-actions").getByLabel("Sign").selectOption({ label: "6" });
  const asked = new Map<string, Set<string>>();
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!url.pathname.endsWith("/image")) return;
    if (!(url.searchParams.get("action") ?? "").startsWith("wlk,sig=6")) return;
    const dir = url.searchParams.get("direction") ?? "";
    asked.set(dir, (asked.get(dir) ?? new Set()).add(url.searchParams.get("frame") ?? ""));
  });
  // Diagonal and straight, so that the avatar must turn on the way.
  await clickTile(page, 1, 2);
  await expect(page.getByTestId("walk-status")).toContainText("walking to");
  // Well inside the first step, every direction it will use has its four frames on the way.
  await expect
    .poll(() => [...asked.values()].filter((frames) => frames.size === 4).length, { timeout: 450 })
    .toBeGreaterThanOrEqual(2);
});

test("walking in a run keeps the new facing and the panel follows it", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.locator(".avatar-row-pick").first().click();
  const panel = page.getByTestId("avatar-place");
  await panel.getByLabel("Column").fill("3");
  await panel.getByLabel("Row").fill("1");
  await panel.getByLabel("Direction").selectOption("2");
  await expect(panel.getByLabel("Column")).toHaveValue("3");
  await clickTile(page, 1, 1);
  await expect(page.getByTestId("walk-status")).toContainText("stopped at 1, 1", {
    timeout: 15000,
  });
  await expect(panel.getByLabel("Column")).toHaveValue("1");
  await expect(panel.getByLabel("Direction")).toHaveValue("6");
  await page.waitForTimeout(800);
  await expect(panel.getByLabel("Direction")).toHaveValue("6");
});

test("a slow click on Pause counts while the room is running", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const pause = page.getByRole("button", { name: "Pause", exact: true });
  await pause.waitFor();
  const box = await pause.boundingBox();
  if (!box) throw new Error("The Pause button has no position.");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  // Long enough for ticks to answer between press and release.
  await page.mouse.down();
  await page.waitForTimeout(600);
  await page.mouse.up();
  await expect(page.getByRole("button", { name: "Resume", exact: true })).toBeVisible();
  await expect(page.getByTestId("run-trace").getByText("Paused.")).toHaveCount(1);
});

test("the user panel draws signs, hand items and actions, and values stay current", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.locator(".avatar-row-pick").first().click();
  const asked = (part: string) =>
    page.waitForRequest(
      (r) => r.url().includes("/image") && decodeURIComponent(r.url()).includes(part),
    );
  const actions = page.getByTestId("avatar-actions");
  let shown = asked("action=sig=6");
  await actions.getByLabel("Sign").selectOption({ label: "6" });
  await shown;
  shown = asked("action=wav");
  await actions.getByRole("button", { name: "Wave" }).click();
  await shown;
  await actions.getByLabel("Sign").selectOption({ label: "None" });
  await page.getByTestId("avatar-details").locator("summary").click();
  shown = asked("crr=3");
  const hand = page.getByTestId("avatar-details").getByLabel("Hand item");
  await hand.selectOption("3");
  await shown;
  await expect(page.getByTestId("run-built-ins")).toContainText("3");
  await expect(hand).toHaveValue("3");
  await hand.selectOption({ label: "None" });
  await expect(page.getByTestId("run-built-ins")).not.toContainText("@handitem");
  // A sign goes down on its own, which the panel then shows.
  await actions.getByLabel("Sign").selectOption({ label: "Heart" });
  await expect(actions.getByLabel("Sign")).toHaveValue("-1", { timeout: 9000 });
});

test("a game can be started and ended from the run panel", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const scores = page.getByTestId("game-scores");
  await expect(scores).toContainText("No game running");
  await page.getByRole("button", { name: "Start game" }).click();
  await expect(scores).toContainText("Game running");
  await page.getByRole("button", { name: "End game" }).click();
  await expect(scores).toContainText("No game running");
});

test("a box saved during a run reaches the running room", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-switch-flip")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.getByRole("button", { name: "Build", exact: true }).click();
  const point = await page.evaluate(() =>
    (
      document.querySelector("wb-editor") as unknown as {
        tileOnPage(a: number, b: number): { x: number; y: number };
      }
    ).tileOnPage(4, 2),
  );
  await page.mouse.click(point.x, point.y);
  const save = page.getByRole("button", { name: "Save settings" });
  await expect(save).toBeVisible();
  await save.click();
  await expect(page.getByTestId("run-panel")).toContainText("was changed");
});

test("a value in the run panel can be changed by double-clicking it", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const say = page.getByPlaceholder(/Say something/);
  await say.fill("point");
  await say.press("Enter");
  const row = page.locator(".run-vars tr", { hasText: "score" });
  await expect(row.locator(".run-value")).toHaveText("1");
  await row.locator(".run-value").dblclick();
  const field = row.getByRole("textbox");
  await page.waitForTimeout(600); // The field must survive the ticks while it is open.
  await field.fill("42");
  await field.press("Enter");
  await expect(row.locator(".run-value")).toHaveText("42");
  await say.fill("point");
  await say.press("Enter");
  await expect(row.locator(".run-value")).toHaveText("43");
});

test("the run panel shows built-in values for the room and a selected user", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const table = page.getByTestId("run-built-ins");
  await expect(table).toContainText("@user_count");
  await page.locator(".avatar-row-pick").first().click();
  await expect(table).toContainText("@direction");
  await expect(table).not.toContainText("@user_count");
});

test("avatar details reach built-in values, and a change in a run takes effect", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Guide" }).click();
  await page
    .getByTestId("tutorial-score-counter")
    .getByRole("button", { name: "Add and open" })
    .click();
  await expect(page.getByTestId("room-canvas")).toBeVisible();
  await page.locator(".avatar-row-pick").first().click();
  const details = page.getByTestId("avatar-details");
  await details.locator("summary").click();
  await details.getByRole("spinbutton", { name: "Level" }).fill("7");
  await details.getByRole("spinbutton", { name: "Level" }).press("Tab");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.locator(".avatar-row-pick").first().click();
  const row = page.getByTestId("run-built-ins").locator("tr", { hasText: "@level" });
  await expect(row).toContainText("7");
  const live = page.getByTestId("avatar-details");
  await live.locator("summary").click();
  await live.getByRole("spinbutton", { name: "Level" }).fill("9");
  await live.getByRole("spinbutton", { name: "Level" }).press("Tab");
  await expect(row).toContainText("9");
});
