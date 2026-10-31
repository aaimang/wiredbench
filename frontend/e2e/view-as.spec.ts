import { expect, type Page, test } from "@playwright/test";

async function login(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("e2e test password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("link", { name: "Catalogue" })).toBeVisible();
}

test("dashboard, mock API keys and view as user work from the browser", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);
  const token = await page.evaluate(async () => {
    const me = await (await fetch("/api/auth/me")).json();
    return me.csrf_token as string;
  });
  const room = await page.evaluate(async (csrf) => {
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": csrf };
    const res = await fetch("/api/tutorials/time-tracking", {
      method: "POST",
      headers,
      body: "{}",
    });
    const id = (await res.json()).id as number;
    await fetch(`/api/sandboxes/${id}/run`, { method: "POST", headers, body: '{"seed":1}' });
    return id;
  }, token);

  await page.getByRole("link", { name: "Dashboard" }).click();
  const panel = page
    .getByTestId("dashboard-room")
    .filter({ has: page.getByTestId(`api-keys-${room}`) });
  await expect(panel).toContainText("Time tracking example");
  await expect(panel).toContainText("Busiest stacks");

  await panel.getByRole("button", { name: "Generate keys" }).click();
  const dialog = page.getByTestId("keys-dialog");
  await expect(dialog).toContainText("Copy these keys now");
  const read = (await dialog.locator("code").first().textContent()) ?? "";
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(panel.getByRole("button", { name: "Replace keys" })).toBeVisible();
  const status = await page.evaluate(
    async ([id, key]) =>
      (
        await fetch(`/api/public/rooms/${id}/variables`, {
          headers: { "X-Wired-Read-Key": key as string },
        })
      ).status,
    [room, read],
  );
  expect(status).toBe(200);

  await page.getByTestId("view-as").click();
  await expect(page.getByTestId("view-banner")).toBeVisible();
  await expect(page.getByRole("link", { name: "Workspace" })).toHaveCount(0);
  await expect(page.getByTestId("site-notice")).toContainText("Habbo Fan Site Policy");
  await page.locator(`a[href="/view/${room}"]`).click();
  await expect(page.getByTestId("view-say")).toBeVisible();
  const walked = page.waitForResponse((res) => res.url().endsWith("/run/input"));
  const canvas = page.getByTestId("room-canvas");
  const box = await canvas.boundingBox();
  await canvas.click({ position: { x: (box?.width ?? 400) / 2, y: (box?.height ?? 300) / 2 } });
  expect((await walked).status()).toBe(200);
  await page.getByTestId("view-say").fill("hello");
  await page.getByRole("button", { name: "Send" }).click();

  const refused = await page.evaluate(
    async (id) => (await fetch(`/api/sandboxes/${id}`)).status,
    room,
  );
  expect(refused).toBe(403);
  await page.reload();
  await expect(page.getByTestId("view-banner")).toBeVisible();

  await page.getByRole("button", { name: "Back to admin" }).click();
  await expect(page.getByRole("link", { name: "Workspace" })).toBeVisible();
  expect(errors).toEqual([]);
});
