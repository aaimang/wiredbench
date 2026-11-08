import { writeFileSync } from "node:fs";
import { join } from "node:path";
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
  const entered = page.waitForResponse((res) => res.url().includes("/run"));
  await page.locator(`a[href="/view/${room}"]`).click();
  await entered;
  await expect(page.getByTestId("view-say")).toBeVisible();
  const walked = page.waitForResponse((res) => res.url().endsWith("/run/input"));
  const canvas = page.getByTestId("room-canvas");
  const box = await canvas.boundingBox();
  await canvas.click({ position: { x: (box?.width ?? 400) / 2, y: (box?.height ?? 300) / 2 } });
  const step = await walked;
  expect(step.status()).toBe(200);
  // Without the way it walked, the server would turn the avatar back to where it first faced.
  expect(step.request().postDataJSON()).toMatchObject({ type: "move", dir: expect.any(Number) });
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

test(":wired opens an inspection window with live values and is never said aloud", async ({
  page,
}) => {
  await login(page);
  const room = await page.evaluate(async () => {
    const me = await (await fetch("/api/auth/me")).json();
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token };
    const res = await fetch("/api/tutorials/time-tracking", {
      method: "POST",
      headers,
      body: "{}",
    });
    const id = (await res.json()).id as number;
    const saved = await (await fetch(`/api/sandboxes/${id}`)).json();
    const { width, height } = saved.document.room;
    saved.document.furni.push({
      id: 700,
      classname: "plain_chair",
      x: Math.floor(width / 2),
      y: Math.floor(height / 2),
      z: 0,
      rot: 0,
      state: 0,
    });
    await fetch(`/api/sandboxes/${id}/document`, {
      method: "PUT",
      headers,
      body: JSON.stringify({ document: saved.document, base_revision: saved.revision }),
    });
    return id;
  });
  await page.getByTestId("view-as").click();
  await expect(page.getByTestId("view-banner")).toBeVisible();
  await page.locator(`a[href="/view/${room}"]`).click();
  const say = page.getByTestId("view-say");
  await expect(say).toBeVisible();
  await expect(page.getByTestId("inspect")).toHaveCount(0);

  const said: string[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/run/input")) said.push(r.postData() ?? "");
  });
  await say.fill(":wired");
  await say.press("Enter");
  const rows = page.getByTestId("inspect-rows");
  await expect(rows).toContainText("@furni_count");
  expect(said.join()).not.toContain(":wired");
  await expect(page.getByTestId("view-messages")).not.toContainText(":wired");

  await page.getByTestId("inspect-context").click();
  await expect(rows).toContainText("@selector_furni_count");
  await expect(rows).not.toContainText("@furni_count");
  await page.getByTestId("inspect-furni").click();
  await expect(page.getByTestId("inspect")).toContainText("Click a furni");
  const canvas = page.getByTestId("room-canvas");
  const box = await canvas.boundingBox();
  const [middleX, middleY] = [(box?.width ?? 400) / 2, (box?.height ?? 300) / 2];
  await canvas.click({ position: { x: middleX, y: middleY - 10 } });
  await expect(page.getByTestId("inspect")).toContainText("Values for plain_chair");
  await expect(rows).toContainText("@id");
  expect(said.join(), "picking a furni does not use it").not.toContain('"click"');

  // A walk is sent one tile at a time, as a client does.
  await canvas.click({ position: { x: middleX, y: middleY + 90 } });
  await expect.poll(() => said.filter((body) => body.includes('"move"')).length).toBeGreaterThan(1);

  await say.fill("hello");
  await say.press("Enter");
  await expect(page.getByTestId("view-messages")).toContainText("hello");
  await say.fill(":WIRED");
  await say.press("Enter");
  await expect(page.getByTestId("inspect")).toHaveCount(0);
});

test("a visitor sees a WIRED effect drawn in the room", async ({ page }) => {
  await login(page);
  const room = await page.evaluate(async () => {
    const me = await (await fetch("/api/auth/me")).json();
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token };
    const res = await fetch("/api/tutorials/time-tracking", {
      method: "POST",
      headers,
      body: "{}",
    });
    const id = (await res.json()).id as number;
    const saved = await (await fetch(`/api/sandboxes/${id}`)).json();
    const box = (id: number, classname: string, x: number, z: number, wired: object) => ({
      id,
      classname,
      x,
      y: 1,
      z,
      rot: 0,
      state: 0,
      wired,
    });
    saved.document.avatars = [
      { id: 1, name: "A", hotel: "com", figure: "hd-180-1", x: 3, y: 3, z: 0, dir: 2 },
    ];
    saved.document.furni = [
      box(10, "wf_trg_says_something", 1, 0, { text: "go" }),
      box(11, "wf_act_give_var", 1, 1, { variable: "hp", value: 40 }),
      box(20, "wf_var_user", 2, 0, { variable: "hp" }),
      box(21, "wf_xtra_varfx_number", 2, 1, {}),
    ];
    await fetch(`/api/sandboxes/${id}/document`, {
      method: "PUT",
      headers,
      body: JSON.stringify({ document: saved.document, base_revision: saved.revision }),
    });
    return id;
  });
  await page.getByTestId("view-as").click();
  await expect(page.getByTestId("view-banner")).toBeVisible();
  await page.locator(`a[href="/view/${room}"]`).click();
  const say = page.getByTestId("view-say");
  await expect(say).toBeVisible();
  const canvas = page.getByTestId("view-canvas");
  const answer = page.waitForResponse((r) => r.url().endsWith("/run/input"));
  await page.waitForTimeout(500);
  // Only the room's middle, because chat and the focused input also change the page.
  const area = (await canvas.boundingBox()) ?? { x: 0, y: 0, width: 1280, height: 720 };
  const clip = {
    x: area.x + area.width * 0.4,
    y: area.y + 80,
    width: area.width * 0.2,
    height: area.height * 0.6,
  };
  const before = await page.screenshot({ clip });

  await say.fill("go");
  await say.press("Enter");
  const state = await (await answer).json();
  expect(state.fx[0]).toMatchObject({ id: 1, value: "40" });
  await expect.poll(async () => (await page.screenshot({ clip })).equals(before)).toBe(false);
});

test("a visitor's room updates several times a second and furni slides", async ({ page }) => {
  await login(page);
  const room = await page.evaluate(async () => {
    const me = await (await fetch("/api/auth/me")).json();
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token };
    const res = await fetch("/api/tutorials/time-tracking", {
      method: "POST",
      headers,
      body: "{}",
    });
    const id = (await res.json()).id as number;
    const saved = await (await fetch(`/api/sandboxes/${id}`)).json();
    const box = (id: number, classname: string, z: number, wired: object) => ({
      id,
      classname,
      x: 1,
      y: 1,
      z,
      rot: 0,
      state: 0,
      wired,
    });
    saved.document.avatars = [
      { id: 1, name: "A", hotel: "com", figure: "hd-180-1", x: 8, y: 8, z: 0, dir: 2 },
    ];
    saved.document.furni = [
      box(10, "wf_trg_says_something", 0, { text: "go" }),
      box(11, "wf_act_rel_mov", 1, { furni: [50], move_x: 5 }),
      { ...box(12, "wf_trg_says_something", 0, { text: "back" }), x: 2 },
      { ...box(13, "wf_act_rel_mov", 1, { furni: [50], move_x: -5 }), x: 2 },
      { id: 50, classname: "plain_chair", x: 1, y: 5, z: 0, rot: 0, state: 0 },
    ];
    await fetch(`/api/sandboxes/${id}/document`, {
      method: "PUT",
      headers,
      body: JSON.stringify({ document: saved.document, base_revision: saved.revision }),
    });
    return id;
  });
  await page.getByTestId("view-as").click();
  await expect(page.getByTestId("view-banner")).toBeVisible();
  await page.locator(`a[href="/view/${room}"]`).click();
  const say = page.getByTestId("view-say");
  await expect(say).toBeVisible();

  const ticks: number[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/run/advance")) ticks.push(r.postDataJSON().ms);
  });
  // The first room load can be slow, so the three updates get a few seconds to arrive.
  await expect.poll(() => ticks.length, { timeout: 5000 }).toBeGreaterThanOrEqual(3);
  expect(Math.max(...ticks)).toBeLessThan(1000);

  const area = (await page.getByTestId("view-canvas").boundingBox()) ?? {
    x: 0,
    y: 0,
    width: 1280,
    height: 720,
  };
  const clip = { x: area.x, y: area.y + 80, width: area.width, height: area.height * 0.6 };
  await say.fill("go");
  await say.press("Enter");
  const frames = new Set<string>();
  const end = Date.now() + 1500;
  while (Date.now() < end) {
    frames.add((await page.screenshot({ clip })).toString("base64"));
  }
  expect(frames.size, "the furni is seen between its two tiles").toBeGreaterThan(2);

  // A slide is drawn on every screen frame, as a walk is, not at the 24 a second of furni art.
  const drawn = await page.evaluate(async () => {
    const view = document.querySelector("wb-room-view") as unknown as {
      renderer: { draw: (...args: unknown[]) => void };
    };
    const draw = view.renderer.draw.bind(view.renderer);
    let count = 0;
    view.renderer.draw = (...args) => {
      count += 1;
      draw(...args);
    };
    const input = document.querySelector("[data-testid=view-say]") as HTMLInputElement;
    input.value = "back";
    input.form?.requestSubmit();
    await new Promise((done) => setTimeout(done, 1000));
    return count;
  });
  // A half-second slide is about 12 draws at the 24 a second of furni art, and 30 on every frame.
  expect(drawn, "draws in the second after asking for a slide").toBeGreaterThan(20);

  // The workspace Run view slides a moved furni the same way.
  await page.getByRole("button", { name: "Back to admin" }).click();
  await page.goto(`/sandbox/${room}`);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const runSay = page.getByPlaceholder(/command such as/);
  await expect(runSay).toBeVisible();
  const runDrawn = await page.evaluate(async () => {
    const editor = document.querySelector("wb-editor") as unknown as {
      renderer: { draw: (...args: unknown[]) => void };
    };
    const draw = editor.renderer.draw.bind(editor.renderer);
    let count = 0;
    editor.renderer.draw = (...args) => {
      count += 1;
      draw(...args);
    };
    const input = [...document.querySelectorAll("input")].find((i) =>
      /command such as/.test(i.placeholder),
    ) as HTMLInputElement;
    input.value = "go";
    input.form?.requestSubmit();
    await new Promise((done) => setTimeout(done, 1000));
    return count;
  });
  expect(runDrawn, "draws in the second after asking for a Run slide").toBeGreaterThan(20);
});

test("a visitor clicks to select, double-clicks to use and chats in bubbles", async ({ page }) => {
  writeFileSync(
    join(process.env.WB_E2E_DIR as string, "furnidata.json"),
    JSON.stringify({
      roomitemtypes: {
        furnitype: [
          {
            id: 11,
            classname: "chair_norja",
            revision: 100,
            name: "Norja chair",
            description: "A chair to test the card.",
            offerid: 5,
            bc: true,
            xdim: 1,
            ydim: 1,
            height: 1,
            cansiton: true,
          },
        ],
      },
      wallitemtypes: { furnitype: [] },
    }),
  );
  await login(page);
  await page.getByTestId("download-button").or(page.getByTestId("update-button")).first().click();
  await page
    .getByTestId("update-dialog")
    .getByRole("button", { name: /Use this catalogue|Apply update/ })
    .click();
  await expect(page.getByTestId("furni-list")).toBeVisible();
  const {
    id: room,
    width,
    height,
  } = await page.evaluate(async () => {
    const me = await (await fetch("/api/auth/me")).json();
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token };
    const res = await fetch("/api/tutorials/time-tracking", {
      method: "POST",
      headers,
      body: "{}",
    });
    const id = (await res.json()).id as number;
    const saved = await (await fetch(`/api/sandboxes/${id}`)).json();
    const { width, height } = saved.document.room;
    const [x, y] = [Math.floor(width / 2), Math.floor(height / 2)];
    saved.document.avatars = [
      { id: 1, name: "Ann", hotel: "com", figure: "hd-180-1", x: x - 3, y: y + 3, z: 0, dir: 2 },
    ];
    saved.document.furni = [
      { id: 700, classname: "chair_norja", x: x + 3, y: y - 3, z: 0, rot: 4, state: 0 },
    ];
    await fetch(`/api/sandboxes/${id}/document`, {
      method: "PUT",
      headers,
      body: JSON.stringify({ document: saved.document, base_revision: saved.revision }),
    });
    return { id, width: width as number, height: height as number };
  });
  await page.getByTestId("view-as").click();
  await expect(page.getByTestId("view-banner")).toBeVisible();
  await page.locator(`a[href="/view/${room}"]`).click();
  const say = page.getByTestId("view-say");
  await expect(say).toBeVisible();
  await page.waitForTimeout(500);

  const sent: string[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/run/input")) sent.push(r.postData() ?? "");
  });
  const canvas = page.getByTestId("room-canvas");
  const box = (await canvas.boundingBox()) ?? { x: 0, y: 0, width: 800, height: 600 };
  // Where a tile's centre is drawn, measured from the canvas.
  const tile = (dx: number, dy: number) => ({
    x: box.width / 2 + (dx - dy) * 32 - ((width % 2) - (height % 2)) * 16,
    y: box.height / 2 + (dx + dy) * 16 + 16 - ((width % 2) + (height % 2)) * 8,
  });
  const chair = tile(3, -3);
  const card = page.getByTestId("view-card");

  await canvas.click({ position: { x: chair.x, y: chair.y - 10 } });
  await expect(card).toContainText("Norja chair");
  await expect(card).toContainText("A chair to test the card.");
  const picture = page.getByTestId("view-card-icon");
  await expect(picture).toHaveAttribute("src", `/api/view/sandboxes/${room}/icons/chair_norja`);
  await expect
    .poll(() => picture.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);
  await expect.poll(() => sent.filter((body) => body.includes('"click"')).length).toBe(1);
  expect(sent.join(), "one click does not use it").not.toContain('"use"');

  await canvas.dblclick({ position: { x: chair.x, y: chair.y - 10 } });
  await expect.poll(() => sent.filter((body) => body.includes('"use"')).length).toBe(1);
  await page.getByTestId("view-use").click();
  await expect.poll(() => sent.filter((body) => body.includes('"use"')).length).toBe(2);

  // Clicking the chair also walked Ann to it, and she sits, as in the hotel.
  const seated = () =>
    page.evaluate(() => {
      const view = document.querySelector("wb-room-view") as unknown as {
        room: { avatars: { x: number; y: number; pose: string; dir: number }[] };
      };
      const [only] = view.room.avatars;
      return `${only?.x},${only?.y},${only?.pose},${only?.dir}`;
    });
  // She faces the way the chair is turned, not the way she walked to it.
  await expect
    .poll(seated, { timeout: 10_000 })
    .toBe(`${Math.floor(width / 2) + 3},${Math.floor(height / 2) - 3},sit,4`);

  const ann = chair;
  await canvas.click({ position: { x: ann.x, y: ann.y - 45 } });
  await expect(card).toContainText("Ann");
  await expect(card).toContainText("You are walking as this avatar.");
  await page.keyboard.press("Escape");
  await expect(card).toBeHidden();

  // Typing anywhere goes to the chat box, as in a client.
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.type("hi");
  await expect(say).toBeFocused();
  await expect(say).toHaveValue("hi");
  await page.keyboard.press("Enter");
  const bubbles = page.locator(".view-bubble");
  await expect(bubbles).toHaveCount(1);
  const first = await bubbles.first().boundingBox();
  expect(first?.y ?? 0, "the bubble is over the speaker").toBeLessThan(box.y + ann.y - 45);
  expect(Math.abs((first?.x ?? 0) + (first?.width ?? 0) / 2 - (box.x + ann.x))).toBeLessThan(8);

  await say.fill("again");
  await say.press("Enter");
  await expect(bubbles).toHaveCount(2);
  await expect
    .poll(async () => (await bubbles.first().boundingBox())?.y ?? 0, { message: "pushed up" })
    .toBeLessThan((first?.y ?? 0) - 10);
});

test("a room's earlier WIRED messages are not shown again on coming back", async ({ page }) => {
  await login(page);
  const room = await page.evaluate(async () => {
    const me = await (await fetch("/api/auth/me")).json();
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token };
    const res = await fetch("/api/tutorials/time-tracking", {
      method: "POST",
      headers,
      body: "{}",
    });
    const id = (await res.json()).id as number;
    const saved = await (await fetch(`/api/sandboxes/${id}`)).json();
    const box = (id: number, classname: string, z: number, wired: object) => ({
      id,
      classname,
      x: 1,
      y: 1,
      z,
      rot: 0,
      state: 0,
      wired,
    });
    saved.document.avatars = [
      { id: 1, name: "A", hotel: "com", figure: "hd-180-1", x: 4, y: 4, z: 0, dir: 2 },
    ];
    saved.document.furni = [
      box(10, "wf_trg_says_something", 0, { text: "ping" }),
      box(11, "wf_act_show_message", 1, { text: "pong" }),
    ];
    await fetch(`/api/sandboxes/${id}/document`, {
      method: "PUT",
      headers,
      body: JSON.stringify({ document: saved.document, base_revision: saved.revision }),
    });
    return id;
  });
  await page.getByTestId("view-as").click();
  await expect(page.getByTestId("view-banner")).toBeVisible();
  await page.locator(`a[href="/view/${room}"]`).click();
  const say = page.getByTestId("view-say");
  const bubbles = page.locator(".view-bubble");
  await expect(say).toBeVisible();
  await say.fill("ping");
  await say.press("Enter");
  await expect(bubbles.filter({ hasText: "pong" })).toHaveCount(1);

  await page.reload();
  await expect(say).toBeVisible();
  await page.waitForTimeout(1500);
  await expect(bubbles).toHaveCount(0);
  await say.fill("ping");
  await say.press("Enter");
  await expect(bubbles.filter({ hasText: "pong" })).toHaveCount(1);
});

test("a visitor walks to a teleport, goes in and comes out of its partner", async ({ page }) => {
  const teleport = (id: number) => ({
    id,
    classname: id === 21 ? "teleport_door" : "teleport_door*2",
    revision: 100,
    name: "Teleport",
    description: "",
    offerid: 5,
    bc: true,
    xdim: 1,
    ydim: 1,
    height: 0.1,
    category: "teleport",
  });
  writeFileSync(
    join(process.env.WB_E2E_DIR as string, "furnidata.json"),
    JSON.stringify({
      roomitemtypes: { furnitype: [teleport(21), teleport(22)] },
      wallitemtypes: { furnitype: [] },
    }),
  );
  await login(page);
  await page.getByTestId("download-button").or(page.getByTestId("update-button")).first().click();
  await page
    .getByTestId("update-dialog")
    .getByRole("button", { name: /Use this catalogue|Apply update/ })
    .click();
  await expect(page.getByTestId("furni-list")).toBeVisible();
  const {
    id: room,
    width,
    height,
  } = await page.evaluate(async () => {
    const me = await (await fetch("/api/auth/me")).json();
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token };
    const res = await fetch("/api/tutorials/time-tracking", {
      method: "POST",
      headers,
      body: "{}",
    });
    const id = (await res.json()).id as number;
    const saved = await (await fetch(`/api/sandboxes/${id}`)).json();
    const { width, height } = saved.document.room;
    const [x, y] = [Math.floor(width / 2), Math.floor(height / 2)];
    saved.document.avatars = [
      { id: 1, name: "Ann", hotel: "com", figure: "hd-180-1", x: x - 3, y: y + 3, z: 0, dir: 2 },
    ];
    // Turned 4, a teleport is entered from the tile below it on the map.
    saved.document.furni = [
      { id: 701, classname: "teleport_door", x, y, z: 0, rot: 4, state: 0, link: 702 },
      {
        id: 702,
        classname: "teleport_door*2",
        x: x + 3,
        y: y - 3,
        z: 0,
        rot: 4,
        state: 0,
        link: 701,
      },
    ];
    await fetch(`/api/sandboxes/${id}/document`, {
      method: "PUT",
      headers,
      body: JSON.stringify({ document: saved.document, base_revision: saved.revision }),
    });
    return { id, width: width as number, height: height as number };
  });
  await page.getByTestId("view-as").click();
  await expect(page.getByTestId("view-banner")).toBeVisible();
  await page.locator(`a[href="/view/${room}"]`).click();
  await expect(page.getByTestId("view-say")).toBeVisible();
  await page.waitForTimeout(500);

  const canvas = page.getByTestId("room-canvas");
  const box = (await canvas.boundingBox()) ?? { x: 0, y: 0, width: 800, height: 600 };
  const tile = (dx: number, dy: number) => ({
    x: box.width / 2 + (dx - dy) * 32 - ((width % 2) - (height % 2)) * 16,
    y: box.height / 2 + (dx + dy) * 16 + 16 - ((width % 2) + (height % 2)) * 8,
  });
  const door = tile(0, 0);
  await canvas.dblclick({ position: { x: door.x, y: door.y - 10 } });

  const ann = () =>
    page.evaluate(() => {
      const view = document.querySelector("wb-room-view") as unknown as {
        room: { avatars: { x: number; y: number }[] };
      };
      const [only] = view.room.avatars;
      return `${only?.x},${only?.y}`;
    });
  const [x, y] = [Math.floor(width / 2), Math.floor(height / 2)];
  // She walks to the front, steps in, and steps out in front of the partner.
  await expect.poll(ann, { timeout: 15_000 }).toBe(`${x + 3},${y - 2}`);
});
