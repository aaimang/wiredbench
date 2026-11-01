import { ApiFailure, get, post } from "../api";
import { h, replace } from "../dom";
import { t } from "../strings";
import { errorMessage, toast } from "../ui";
import { InspectWindow } from "./inspect";
import {
  avatarExtras,
  directionBetween,
  drawTile,
  type FurniInfo,
  findPath,
  fitsInRoom,
  normaliseRoom,
  type RoomDocument,
  standAt,
  UNKNOWN_FURNI,
  withFace,
} from "./model";
import { RoomRenderer } from "./renderer";

const T = t.viewAs;
const TICK_MS = 1000;
const SECONDS_PER_STEP = 0.5;
const WALK_FRAMES_PER_SECOND = 8;
const CHAT_LINES = 6;
const WIRED_COMMAND = ":wired";

interface ViewItem {
  revision?: number;
  xdim?: number;
  ydim?: number;
  height?: number;
  data?: Record<string, unknown>;
}

interface ViewRoom {
  id: number;
  name: string;
  document: Record<string, unknown>;
  items: Record<string, ViewItem>;
}

interface ViewState {
  furni: { id: number; x: number; y: number; z: number; rot: number; state: number }[];
  users: {
    id: number;
    name: string;
    x: number;
    y: number;
    dir: number;
    details?: Record<string, number>;
  }[];
  messages: { at_ms: number; user: number; text: string }[];
}

/** A room as a visitor sees it. Everything here comes from /api/view, which has no WIRED config. */
class WbRoomView extends HTMLElement {
  private renderer: RoomRenderer | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private room: RoomDocument | null = null;
  private items: Record<string, ViewItem> = {};
  private user: number | null = null;
  private url = "";
  private log = h("ul", { class: "dashboard-problems", "data-testid": "view-messages" });
  private seen = new Set<string>();
  private stage = h("div", { class: "view-stage" });
  private inspect: InspectWindow | null = null;
  private walker: {
    path: [number, number][];
    from: [number, number, number];
    elapsed: number;
  } | null = null;
  private walkClock = 0;

  connectedCallback(): void {
    const match = /^\/view\/(\d+)$/.exec(location.pathname);
    void (match ? this.showRoom(Number(match[1])) : this.showList());
  }

  disconnectedCallback(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.renderer?.destroy();
  }

  private async showList(): Promise<void> {
    try {
      const { rooms } = await get<{ rooms: { id: number; name: string }[] }>("/api/view/sandboxes");
      replace(
        this,
        h(
          "div",
          { class: "view-list" },
          h("h1", {}, T.title),
          ...(rooms.length
            ? rooms.map((room) => {
                const link = h("a", { href: `/view/${room.id}` }, room.name);
                return link;
              })
            : [h("p", {}, T.noRooms)]),
        ),
      );
    } catch (error) {
      replace(this, h("p", { class: "form-error", role: "alert" }, errorMessage(error)));
    }
  }

  private lookup = (classname: string): FurniInfo => {
    const item = this.items[classname];
    if (!item) return UNKNOWN_FURNI;
    return {
      xdim: item.xdim ?? 1,
      ydim: item.ydim ?? 1,
      height: item.height ?? 1,
      canStand: item.data?.canstandon === true,
      canSit: item.data?.cansiton === true,
      canLay: item.data?.canlayon === true,
    };
  };

  private async showRoom(id: number): Promise<void> {
    try {
      const data = await get<ViewRoom>(`/api/view/sandboxes/${id}`);
      this.url = `/api/view/sandboxes/${id}/run`;
      this.room = normaliseRoom(data.document);
      this.items = data.items;
      this.user = this.room.avatars[0]?.id ?? null;
      const canvas = h("div", { class: "view-canvas", "data-testid": "view-canvas" });
      replace(
        this.stage,
        canvas,
        h(
          "div",
          { class: "view-head" },
          h("a", { href: "/view" }, T.back),
          h("h1", {}, data.name),
          this.avatarPicker(),
        ),
        h("div", { class: "view-foot" }, this.log, this.sayForm()),
      );
      replace(this, this.stage);
      const renderer = new RoomRenderer();
      try {
        await renderer.init(canvas);
      } catch {
        replace(canvas, h("p", { class: "note" }, T.noWebgl));
      }
      if (renderer.app?.canvas) {
        this.renderer = renderer;
        renderer.onChange = () => this.draw();
        for (const name of new Set(this.room.furni.map((item) => item.classname))) {
          const revision = this.items[name]?.revision;
          if (revision !== undefined) void renderer.loadFurni(name, revision);
        }
        this.bindPointer(renderer.app.canvas);
        renderer.app.ticker.add((ticker) => {
          if (this.walker) this.advanceWalk(ticker.deltaMS / 1000);
          if (this.walker || renderer.motionDue()) this.draw();
        });
        this.draw(); // Clicks need tile positions, which exist once the room has been drawn.
      }
      this.apply(await post<ViewState>(this.query(this.url)));
      this.timer = setInterval(() => void this.tick(), TICK_MS);
    } catch (error) {
      replace(this, h("p", { class: "form-error", role: "alert" }, errorMessage(error)));
    }
  }

  private query(path: string): string {
    return this.user === null ? path : `${path}?user=${this.user}`;
  }

  private avatarPicker(): HTMLElement {
    const avatars = this.room?.avatars ?? [];
    if (!avatars.length) return h("p", { class: "muted" }, T.noAvatars);
    const select = h(
      "select",
      { id: "view-user", "aria-label": T.actingAs },
      ...avatars.map((avatar) => h("option", { value: String(avatar.id) }, avatar.name)),
    );
    select.addEventListener("change", () => {
      this.user = Number(select.value);
      this.walker = null;
      this.seen.clear();
      replace(this.log);
    });
    return h("label", { for: "view-user" }, `${T.actingAs} `, select);
  }

  private sayForm(): HTMLElement {
    const input = h("input", {
      placeholder: T.sayHint,
      "aria-label": T.say,
      maxlength: 500,
      "data-testid": "view-say",
    });
    const form = h(
      "form",
      { class: "run-form" },
      input,
      h("button", { class: "btn", type: "submit" }, T.send),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      if (text.toLowerCase() === WIRED_COMMAND) {
        this.toggleInspect();
        return;
      }
      const speaker = this.room?.avatars.find((a) => a.id === this.user);
      this.addChat(speaker ? `${speaker.name}: ${text}` : text);
      void this.send({ type: "say", text });
    });
    return form;
  }

  private toggleInspect(): void {
    if (this.inspect) {
      this.inspect.element.remove();
      this.inspect = null;
      return;
    }
    this.inspect = new InspectWindow(`${this.url}/inspect`, () => this.toggleInspect());
    this.stage.append(this.inspect.element);
  }

  private addChat(text: string): void {
    this.log.append(h("li", {}, text));
    while (this.log.children.length > CHAT_LINES) this.log.firstElementChild?.remove();
  }

  private walkTo(goal: [number, number]): void {
    const room = this.room;
    const avatar = room?.avatars.find((a) => a.id === this.user);
    if (!room || !avatar) return;
    const [next] = this.walker?.path ?? [];
    const start: [number, number] = next ?? [avatar.x, avatar.y];
    const occupied = new Set(
      room.avatars.filter((a) => a.id !== avatar.id).map((a) => `${a.x},${a.y}`),
    );
    const path = findPath(room, this.lookup, start, goal, occupied);
    if (path === null) return;
    if (!next && path.length === 0) {
      void this.send({ type: "move", x: goal[0], y: goal[1] });
      return;
    }
    if (this.walker && next) this.walker.path = [next, ...path];
    else this.walker = { path, from: [avatar.x, avatar.y, avatar.z], elapsed: 0 };
    let from = start;
    for (const step of path) {
      this.renderer?.preloadWalk(avatar, directionBetween(from, step));
      from = step;
    }
  }

  private advanceWalk(seconds: number): void {
    const walker = this.walker;
    const avatar = this.room?.avatars.find((a) => a.id === this.user);
    if (!walker || !avatar || !this.room) {
      this.walker = null;
      return;
    }
    this.walkClock += seconds;
    walker.elapsed += seconds;
    while (walker.elapsed >= SECONDS_PER_STEP) {
      const next = walker.path.shift();
      if (!next) break;
      walker.elapsed -= SECONDS_PER_STEP;
      const stand = standAt(this.room, this.lookup, next[0], next[1]);
      avatar.dir = directionBetween([walker.from[0], walker.from[1]], next);
      Object.assign(avatar, { x: next[0], y: next[1], z: stand.z, pose: stand.pose });
      walker.from = [next[0], next[1], stand.z];
      if (walker.path.length === 0) this.walker = null;
      void this.send({ type: "move", x: next[0], y: next[1] });
      if (!this.walker) return;
    }
  }

  private bindPointer(canvas: HTMLCanvasElement): void {
    canvas.addEventListener("click", (event) => {
      const rect = canvas.getBoundingClientRect();
      const [x, y] = [event.clientX - rect.left, event.clientY - rect.top];
      const hit = this.renderer?.hitAt(x, y);
      if (hit?.kind === "furni") {
        if (this.inspect?.tab === "furni") {
          const item = this.room?.furni.find((f) => f.id === hit.id);
          this.inspect.pickFurni(
            hit.id,
            (this.items[item?.classname ?? ""]?.data?.name as string) ??
              item?.classname ??
              String(hit.id),
          );
          return;
        }
        void this.send({ type: "click", furni: hit.id });
        return;
      }
      const tile = this.renderer?.tileAt(x, y);
      if (tile && this.room && fitsInRoom(this.room, [tile])) {
        this.walkTo([tile[0], tile[1]]);
      }
    });
  }

  private async send(entry: Record<string, unknown>): Promise<void> {
    if (this.user === null) return;
    try {
      this.apply(await post<ViewState>(`${this.url}/input`, { ...entry, user: this.user }));
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  private async tick(): Promise<void> {
    try {
      this.apply(await post<ViewState>(this.query(`${this.url}/advance`), { ms: TICK_MS }));
    } catch (error) {
      if (error instanceof ApiFailure && error.status === 429) return; // The next tick tries again.
      if (this.timer !== null) clearInterval(this.timer);
      toast(errorMessage(error), "error");
    }
  }

  private apply(state: ViewState): void {
    const room = this.room;
    if (!room) return;
    for (const item of state.furni) {
      const placed = room.furni.find((f) => f.id === item.id);
      if (placed) Object.assign(placed, item);
    }
    room.avatars = room.avatars.filter((a) => state.users.some((u) => u.id === a.id));
    for (const user of state.users) {
      const avatar = room.avatars.find((a) => a.id === user.id);
      if (avatar && !(this.walker && avatar.id === this.user)) {
        const stand = standAt(room, this.lookup, user.x, user.y);
        Object.assign(avatar, {
          x: user.x,
          y: user.y,
          dir: user.dir,
          z: stand.z,
          pose: stand.pose,
          details: user.details,
        });
      }
    }
    // Only the latest messages are sent, so a count would stop finding new ones.
    for (const message of state.messages) {
      const key = `${message.at_ms}:${message.text}`;
      if (!this.seen.has(key)) this.addChat(message.text);
      this.seen.add(key);
    }
    void this.inspect?.refresh();
    this.draw();
  }

  private draw(): void {
    const room = this.room;
    if (!room || !this.renderer) return;
    this.renderer.draw({
      room,
      lookup: this.lookup,
      revisionOf: (classname) => this.items[classname]?.revision ?? null,
      selected: null,
      picked: new Set(),
      ghost: null,
      hover: null,
      avatarPose: (avatar) => {
        const walker = avatar.id === this.user ? this.walker : null;
        const [next] = walker?.path ?? [];
        if (walker && next) {
          const progress = Math.min(1, walker.elapsed / SECONDS_PER_STEP);
          const [fromX, fromY, fromZ] = walker.from;
          const target = standAt(room, this.lookup, next[0], next[1]);
          const front = drawTile(room, this.lookup, next[0], next[1]);
          const look = withFace(avatarExtras(avatar.details), avatar, true, performance.now());
          return {
            x: fromX + (next[0] - fromX) * progress,
            y: fromY + (next[1] - fromY) * progress,
            z: fromZ + (target.z - fromZ) * progress,
            dir: directionBetween([fromX, fromY], next),
            action: "wlk",
            extra: look.extra,
            gesture: look.gesture,
            frame: Math.floor(this.walkClock * WALK_FRAMES_PER_SECOND) % 4,
            frontX: Math.max(fromX, front[0]),
            frontY: Math.max(fromY, front[1]),
          };
        }
        const [frontX, frontY] = drawTile(room, this.lookup, avatar.x, avatar.y);
        return {
          x: avatar.x,
          y: avatar.y,
          z: avatar.z,
          dir: avatar.dir,
          action: avatar.pose,
          ...withFace(avatarExtras(avatar.details), avatar, false, performance.now()),
          frontX,
          frontY,
        };
      },
    });
  }
}

customElements.define("wb-room-view", WbRoomView);
