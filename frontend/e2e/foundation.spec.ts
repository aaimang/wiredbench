import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";

const FURNIDATA = join(process.env.WB_E2E_DIR as string, "furnidata.json");
const PASSWORD = "e2e test password";

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
  ...extra,
});

function publish(...floor: object[]): void {
  writeFileSync(
    FURNIDATA,
    JSON.stringify({ roomitemtypes: { furnitype: floor }, wallitemtypes: { furnitype: [] } }),
  );
}

async function login(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("link", { name: "Catalogue" })).toBeVisible();
}

test("nothing is reachable before login, and bad passwords show an error", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Log in to Wiredbench" })).toBeVisible();
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("wrong password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("alert")).toHaveText("That username or password is wrong.");
  expect(errors).toEqual([]);
});

test("first download, browse WIRED, then an update with a correct diff", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (message) => {
    // A refused resource would mean the Content-Security-Policy broke the app.
    if (message.text().includes("Content Security Policy")) problems.push(message.text());
  });

  publish(
    furni("wf_trg_says_something", "User Says Keyword"),
    furni("wf_act_show_message", "Show Message"),
    furni("wf_test_act", "Test Effect", { offerid: -1, bc: false }),
    furni("chair", "Plain Chair"),
  );
  await login(page);

  await expect(page.getByRole("heading", { name: "No catalogue for Sandbox yet" })).toBeVisible();
  await page.getByTestId("download-button").click();
  const dialog = page.getByTestId("update-dialog");
  await expect(dialog.getByRole("heading", { name: "First download for Sandbox" })).toBeVisible();
  await expect(dialog).toContainText("4 furni, including 3 WIRED");
  await dialog.getByRole("button", { name: "Use this catalogue" }).click();

  const list = page.getByTestId("furni-list");
  await expect(list.getByText("User Says Keyword")).toBeVisible();
  await expect(list.getByRole("heading", { name: "Triggers" })).toBeVisible();
  await expect(list.getByText("Plain Chair")).toHaveCount(0);
  await expect(list.locator('[data-classname="wf_test_act"]')).toContainText("Not in catalogue");

  await page.getByRole("button", { name: "All furni" }).click();
  await expect(list.getByText("Plain Chair")).toBeVisible();
  await page.getByRole("button", { name: "WIRED", exact: true }).click();

  await page.getByLabel("Search name, classname or description").fill("wf_act");
  await expect(page.getByTestId("list-count")).toHaveText("1 of 1");
  await list.getByText("Show Message").click();
  await expect(page.locator(".detail-panel")).toContainText("wf_act_show_message");
  await page.getByLabel("Search name, classname or description").fill("");
  await expect(page.getByTestId("list-count")).toHaveText("3 of 3");

  // Nothing has changed upstream.
  await page.getByTestId("update-button").click();
  await expect(page.getByTestId("status-line")).toContainText("Up to date");

  // Habbo publishes one new WIRED, one renamed, one removed.
  publish(
    furni("wf_trg_says_something", "User Says Keyword"),
    furni("wf_act_show_message", "Show Message v2"),
    furni("wf_xtra_random", "Random Pick"),
    furni("chair", "Plain Chair"),
  );
  await page.getByTestId("update-button").click();
  await expect(dialog.getByRole("heading", { name: "Update for Sandbox" })).toBeVisible();
  const wiredRow = dialog.locator(".diff-summary-row").first();
  await expect(wiredRow).toContainText("1 new");
  await expect(wiredRow).toContainText("1 changed");
  await expect(wiredRow).toContainText("1 removed");
  await expect(dialog.locator(".diff-summary-row").nth(1)).toContainText("0 new");
  await expect(dialog.locator(".diff-entry").first()).toContainText("wf_xtra_random");
  await dialog.locator("summary", { hasText: "wf_act_show_message" }).click();
  await expect(dialog.locator("ins", { hasText: "Show Message v2" }).first()).toBeVisible();

  // Reviewing does not apply anything.
  await expect(list.getByText("Test Effect")).toHaveCount(1);
  await dialog.getByRole("button", { name: "Apply update" }).click();
  await expect(list.getByText("Random Pick")).toBeVisible();
  await expect(list.getByText("Test Effect")).toHaveCount(0);
  await expect(list.locator('[data-classname="wf_xtra_random"]')).toContainText("New");

  // Everything is still there after a reload, including the filter column.
  await page.reload();
  await expect(page.getByRole("button", { name: /^Triggers/ })).toBeVisible();
  await expect(page.getByText("Select a box to see its details.")).toBeVisible();
  await page.getByRole("button", { name: /^Add-ons/ }).click();
  await expect(page.getByTestId("list-count")).toHaveText("1 of 1");
  await page.getByRole("button", { name: /^All types/ }).click();

  // Earlier versions can be restored.
  await page.getByRole("button", { name: "Versions" }).click();
  await page.getByRole("button", { name: "Roll back" }).click();
  await expect(list.getByText("Test Effect")).toBeVisible();

  expect(problems).toEqual([]);
});

test("folders and sandboxes: create, move, trash, restore", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Workspace" }).click();
  await page.getByRole("button", { name: "New folder" }).click();
  await page.getByRole("textbox", { name: "Name" }).fill("Games");
  await page.getByRole("button", { name: "Create" }).click();

  await page.getByRole("button", { name: "New sandbox" }).click();
  await page.getByRole("textbox", { name: "Name" }).fill("Time tracking");
  await page.getByRole("button", { name: "Create" }).click();
  const items = page.getByTestId("workspace-items");
  await expect(items.getByText("Time tracking")).toBeVisible();

  await page.getByRole("button", { name: "New folder" }).click();
  await page.getByRole("textbox", { name: "Name" }).fill("games");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("alert")).toContainText("already called");
  await page.getByRole("button", { name: "Cancel" }).click();

  const row = items.getByRole("listitem").filter({ hasText: "Time tracking" });
  await row.getByRole("button", { name: "Move", exact: true }).click();
  await page.getByLabel("Move to", { exact: true }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "Move", exact: true }).last().click();
  await expect(items.getByText("Time tracking")).toHaveCount(0);

  await items.getByText("Games").click();
  await expect(items.getByText("Time tracking")).toBeVisible();
  await items.getByRole("button", { name: "Duplicate" }).click();
  await expect(items.getByText("Time tracking (copy)")).toBeVisible();

  await page.getByRole("button", { name: "All sandboxes" }).click();
  await items
    .getByRole("listitem")
    .filter({ hasText: "Games" })
    .getByRole("button", { name: "Move to trash" })
    .click();
  await expect(page.getByText("This folder is empty.")).toBeVisible();

  await page.getByRole("button", { name: "Trash" }).click();
  const trash = page.getByTestId("trash-items");
  await trash.getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText("The trash is empty.")).toBeVisible();
  await page.getByRole("button", { name: "All sandboxes" }).click();
  await items.getByText("Games").click();
  await expect(items.getByText("Time tracking", { exact: true })).toBeVisible();
});

test("every page shows the fan site disclaimer", async ({ page }) => {
  const notice = page.getByTestId("site-notice");
  await page.goto("/");
  await expect(notice).toContainText("not affiliated with, endorsed, sponsored");
  await login(page);
  for (const name of ["Catalogue", "Workspace", "Settings"]) {
    await page.getByRole("link", { name }).click();
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("Habbo Fan Site Policy");
  }
  await expect(page.getByText("Do not use the same password as your Habbo account.")).toBeVisible();
});

test("settings save, the session survives reload, and logout ends it", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByLabel("Theme").selectOption("dark");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.getByLabel("Theme")).toHaveValue("dark");
  await page.getByLabel("Theme").selectOption("system");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", "dark");

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("heading", { name: "Log in to Wiredbench" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Log in to Wiredbench" })).toBeVisible();
});

test("the phone layout has no sideways page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await login(page);
  for (const link of ["Catalogue", "Workspace", "Settings"]) {
    await page.getByRole("link", { name: link }).click();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, link).toBeLessThanOrEqual(0);
  }
});

test("import a G-Presets file, then export it again", async ({ page }) => {
  const preset = {
    bindings: [],
    furni: [
      {
        id: 1,
        className: "wf_floor_switch1",
        name: "a",
        rotation: 0,
        location: { x: 1, y: 1, z: 0 },
      },
      {
        id: 2,
        className: "wf_trg_state_changed",
        name: "b",
        rotation: 0,
        location: { x: 2, y: 2, z: 0 },
      },
    ],
    wired: {
      triggers: [
        { wiredId: 2, options: [], config: "", items: [1], furniSources: [100], unknownField: 7 },
      ],
    },
  };
  await login(page);
  await page.getByRole("link", { name: "Workspace" }).click();
  await page.getByTestId("import-file").setInputFiles({
    name: "Imported switch.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(preset)),
  });
  const report = page.getByTestId("exchange-report");
  await expect(report).toContainText("Furni: 2. WIRED boxes: 1.");
  await report.getByRole("button", { name: "Close" }).click();

  const row = page
    .getByTestId("workspace-items")
    .getByRole("listitem")
    .filter({ hasText: "Imported switch" });
  const download = page.waitForEvent("download");
  await row.getByRole("button", { name: "Export G-Presets file" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("Imported-switch.json");
  const stream = await file.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  expect(JSON.parse(Buffer.concat(chunks).toString())).toEqual(preset);
  await expect(report).toContainText("has not yet been proven in a real room");
  await report.getByRole("button", { name: "Close" }).click();

  await page.getByTestId("import-file").setInputFiles({
    name: "broken.json",
    mimeType: "application/json",
    buffer: Buffer.from("{not json"),
  });
  await expect(page.getByText("This file is not valid JSON.")).toBeVisible();
});
