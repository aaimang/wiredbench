import { Box, X } from "lucide";
import { ApiFailure, get, post } from "../api";
import { h, icon, replace } from "../dom";
import { t } from "../strings";
import { errorMessage, toast } from "../ui";
import { InspectWindow } from "./inspect";
import {
  avatarExtras,
  besideTiles,
  clickTileAt,
  directionBetween,
  drawTile,
  type Flight,
  type FurniInfo,
  type FxShown,
  findPath,
  fitsInRoom,
  frontTile,
  furniKind,
  furniWalkTarget,
  glideSteps,
  isFrozen,
  isNextTo,
  type Look,
  normaliseRoom,
  type PlacedAvatar,
  type RoomDocument,
  restingHeight,
  restTile,
  standAt,
  stateHeights,
  syncTemporary,
  UNKNOWN_FURNI,
  usedFromFront,
  usedFromNextTo,
  WALK_FRAMES_PER_SECOND,
  withFace,
} from "./model";
import { type AvatarPose, type Hit, RoomRenderer } from "./renderer";

const T = t.viewAs;
const TICK_MS = 250;
/** Time a tab lost while hidden is caught up, but a long sleep must not fast-forward the room. */
const MAX_TICK_MS = 5000;
const INSPECT_MS = 1000;
const SECONDS_PER_STEP = 0.5;
const CHAT_LINES = 6;
const BUBBLE_MS = 12_000;
const BUBBLE_FADE_MS = 400;
const BUBBLE_GAP = 4;
/** How far above an avatar's feet its bubbles start, which is about its head. */
const BUBBLE_RISE = 110;
const WIRED_COMMAND = ":wired";

interface ViewItem {
  revision?: number;
  category?: string;
  hand_items?: number[];
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
    bot?: boolean;
    figure?: string;
  }[];
  /** Chat the room hears has no user. A bot's or a user's line says who spoke. */
  messages: { at_ms: number; user: number | null; speaker?: number; text: string }[];
  /** False while a Click User box keeps the avatar menu shut. */
  user_menu?: boolean;
  flights: Flight[];
  fx: FxShown[];
  looks: { furni: Record<number, Look>; users: Record<number, Look> };
}

interface Tile {
  x: number;
  y: number;
}

/** A room as a visitor sees it. Everything here comes from /api/view, which has no WIRED config. */
class WbRoomView extends HTMLElement {
  private renderer: RoomRenderer | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private room: RoomDocument | null = null;
  private items: Record<string, ViewItem> = {};
  private user: number | null = null;
  private url = "";
  private roomId = 0;
  private bubbles = h("div", {
    class: "view-bubbles",
    "data-testid": "view-messages",
    "aria-live": "polite",
  });
  private card = h("div", {
    class: "furni-card view-card",
    "data-testid": "view-card",
    hidden: true,
  });
  private selected: Hit | null = null;
  private say: HTMLInputElement | null = null;
  private seen = new Set<string>();
  /** Messages already there on entering were sent before this visit, so they are not shown. */
  private entering = true;
  private stage = h("div", { class: "view-stage" });
  private inspect: InspectWindow | null = null;
  private walker: {
    path: [number, number][];
    from: [number, number, number];
    elapsed: number;
    onArrive?: () => void;
  } | null = null;
  private walkClock = 0;
  private effects: Pick<ViewState, "flights" | "fx" | "looks" | "user_menu"> | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  private waiting = 0;
  private lastTick = 0;
  private lastInspect = 0;
  private avatarGlides = new Map<
    number,
    { from: [number, number, number]; began: number; ms: number }
  >();

  connectedCallback(): void {
    document.addEventListener("keydown", this.onKey);
    const match = /^\/view\/(\d+)$/.exec(location.pathname);
    void (match ? this.showRoom(Number(match[1])) : this.showList());
  }

  disconnectedCallback(): void {
    document.removeEventListener("keydown", this.onKey);
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
      canStack: item.data?.canputstuffon !== false,
      kind: furniKind(classname, item.category ?? null, item.hand_items),
      stateHeights: stateHeights.get(classname),
    };
  };

  private async showRoom(id: number): Promise<void> {
    try {
      const data = await get<ViewRoom>(`/api/view/sandboxes/${id}`);
      this.roomId = id;
      this.url = `/api/view/sandboxes/${id}/run`;
      this.room = normaliseRoom(data.document);
      this.items = data.items;
      this.user = this.room.avatars.find((a) => !a.bot)?.id ?? null;
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
        this.bubbles,
        this.card,
        h("div", { class: "view-foot" }, this.sayForm()),
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
          else if (this.avatarGlides.size > 0) this.walkClock += ticker.deltaMS / 1000;
          if (this.walker || this.avatarGlides.size > 0 || renderer.motionDue()) this.draw();
        });
        this.draw(); // Clicks need tile positions, which exist once the room has been drawn.
      }
      this.apply(await post<ViewState>(this.query(this.url)));
      this.lastTick = performance.now();
      this.timer = setInterval(() => void this.tick(), TICK_MS);
    } catch (error) {
      replace(this, h("p", { class: "form-error", role: "alert" }, errorMessage(error)));
    }
  }

  private query(path: string): string {
    return this.user === null ? path : `${path}?user=${this.user}`;
  }

  private avatarPicker(): HTMLElement {
    // Nobody plays as a bot: WIRED moves it.
    const avatars = (this.room?.avatars ?? []).filter((a) => !a.bot);
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
      this.entering = true;
      replace(this.bubbles);
      this.renderCard();
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
    this.say = input;
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
      // The room sends the line back, unless a WIRED box hides it.
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

  /** Typing anywhere in the room goes to the chat box, as in a client. */
  private onKey = (event: KeyboardEvent): void => {
    const target = event.target as HTMLElement | null;
    if (target?.closest("input, textarea, select, [contenteditable]")) return;
    if (event.ctrlKey || event.metaKey || event.altKey || !this.say) return;
    if (event.key === "Escape") {
      this.choose(null);
      return;
    }
    if (event.key === "Enter") event.preventDefault();
    else if (event.key.length !== 1) return;
    this.say.focus(); // Focused before the key lands, so the typed letter goes into the box.
  };

  /** A bubble starts over its speaker, and pushes the older ones up. */
  private addChat(text: string, speaker: number | null): void {
    const bubble = h("p", { class: "view-bubble" }, text);
    this.bubbles.append(bubble);
    const area = this.stage.getBoundingClientRect();
    const avatar = this.room?.avatars.find((a) => a.id === speaker);
    const at =
      avatar && this.renderer ? this.renderer.tileOnPage(avatar.x, avatar.y, avatar.z) : null;
    const width = bubble.offsetWidth;
    const height = bubble.offsetHeight;
    const centre = at ? at.x - area.left : area.width / 2;
    const left = Math.max(8, Math.min(centre - width / 2, area.width - width - 8));
    const top = at ? at.y - area.top - BUBBLE_RISE - height : area.height / 2;
    for (const older of this.bubbles.children) {
      if (older === bubble || !(older instanceof HTMLElement)) continue;
      older.style.top = `${Number.parseFloat(older.style.top) - height - BUBBLE_GAP}px`;
    }
    Object.assign(bubble.style, { left: `${left}px`, top: `${Math.max(0, top)}px` });
    while (this.bubbles.children.length > CHAT_LINES) this.bubbles.firstElementChild?.remove();
    setTimeout(() => {
      bubble.classList.add("view-bubble-gone");
      setTimeout(() => bubble.remove(), BUBBLE_FADE_MS);
    }, BUBBLE_MS);
  }

  private choose(hit: Hit | null): void {
    this.selected = hit;
    this.renderCard();
    this.draw();
  }

  private furniIcon(classname: string): HTMLElement {
    const picture = h("span", { class: "furni-icon" });
    const image = h("img", {
      src: `/api/view/sandboxes/${this.roomId}/icons/${encodeURIComponent(classname)}`,
      alt: "",
      "data-testid": "view-card-icon",
    });
    image.addEventListener("error", () => replace(picture, icon(Box, 16)));
    picture.append(image);
    return picture;
  }

  /** What a click on a furni or avatar shows. Only what the room itself would tell a visitor. */
  private renderCard(): void {
    const hit = this.selected;
    const furni = hit?.kind === "furni" ? this.room?.furni.find((f) => f.id === hit.id) : null;
    const avatar = hit?.kind === "avatar" ? this.room?.avatars.find((a) => a.id === hit.id) : null;
    if (!furni && !avatar) {
      this.selected = null;
      this.card.hidden = true;
      return;
    }
    const data = furni ? (this.items[furni.classname]?.data ?? {}) : {};
    const name = avatar?.name ?? (typeof data.name === "string" ? data.name : "");
    const about = avatar
      ? avatar.id === this.user
        ? T.card.you
        : ""
      : typeof data.description === "string"
        ? data.description
        : "";
    replace(
      this.card,
      h(
        "div",
        { class: "furni-card-head view-card-head" },
        ...(furni ? [this.furniIcon(furni.classname)] : []),
        h("h2", {}, name || furni?.classname || ""),
        h(
          "button",
          {
            class: "btn btn-quiet btn-icon",
            "aria-label": T.card.close,
            title: T.card.close,
            onclick: () => this.choose(null),
          },
          icon(X),
        ),
      ),
      ...(about ? [h("p", {}, about)] : []),
      ...(furni
        ? [
            h(
              "div",
              { class: "furni-card-actions" },
              h(
                "button",
                {
                  class: "btn btn-small",
                  "data-testid": "view-use",
                  onclick: () => this.useFurni(furni.id),
                },
                T.card.use,
              ),
            ),
          ]
        : []),
    );
    this.card.hidden = false;
  }

  /** Like the client, the avatar first walks to where the furni is used from. */
  private useFurni(id: number): void {
    const room = this.room;
    const item = room?.furni.find((f) => f.id === id);
    const avatar = room?.avatars.find((a) => a.id === this.user);
    const send = () => void this.send({ type: "use", furni: id });
    if (!room || !item || !avatar) {
      send();
      return;
    }
    const kind = this.lookup(item.classname).kind ?? furniKind(item.classname, null);
    if (usedFromFront(kind)) {
      const front = frontTile(item);
      if (avatar.x === front[0] && avatar.y === front[1]) send();
      else this.walkTo(front, send);
      return;
    }
    if (!usedFromNextTo(kind) || isNextTo([avatar.x, avatar.y], [item.x, item.y])) {
      send();
      return;
    }
    const occupied = new Set(
      room.avatars.filter((a) => a.id !== avatar.id).map((a) => `${a.x},${a.y}`),
    );
    const [spot] = besideTiles(item, room)
      .filter(([x, y]) => standAt(room, this.lookup, x, y).walkable && !occupied.has(`${x},${y}`))
      .sort(
        (a, b) =>
          Math.hypot(a[0] - avatar.x, a[1] - avatar.y) -
          Math.hypot(b[0] - avatar.x, b[1] - avatar.y),
      );
    if (spot) this.walkTo(spot, send);
    else send();
  }

  private walkTo(goal: [number, number], onArrive?: () => void): void {
    const room = this.room;
    const avatar = room?.avatars.find((a) => a.id === this.user);
    if (!room || !avatar || isFrozen(avatar)) return;
    const [next] = this.walker?.path ?? [];
    const start: [number, number] = next ?? [avatar.x, avatar.y];
    const occupied = new Set(
      room.avatars.filter((a) => a.id !== avatar.id).map((a) => `${a.x},${a.y}`),
    );
    const path = findPath(room, this.lookup, start, goal, occupied);
    if (path === null) return;
    if (!next && path.length === 0) {
      if (onArrive) onArrive();
      else void this.send({ type: "move", x: goal[0], y: goal[1] });
      return;
    }
    if (this.walker && next) Object.assign(this.walker, { path: [next, ...path], onArrive });
    else this.walker = { path, from: [avatar.x, avatar.y, avatar.z], elapsed: 0, onArrive };
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
      const [after] = walker.path;
      // Only the last step sits, so passing over a chair keeps the way the avatar walks.
      const seated = after ? undefined : stand.dir;
      avatar.dir = seated ?? directionBetween([walker.from[0], walker.from[1]], next);
      // Arriving on a bed, the avatar lies down on its head row, in the lane it walked to.
      const [x, y] = after ? next : restTile(this.room, this.lookup, next[0], next[1]);
      Object.assign(avatar, { x, y, z: stand.z, pose: stand.pose });
      walker.from = [x, y, stand.z];
      if (!after) this.walker = null;
      void this.send({ type: "move", x, y, dir: avatar.dir });
      if (!this.walker) {
        walker.onArrive?.();
        return;
      }
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
        this.choose(hit);
        void this.send({ type: "click", furni: hit.id });
        // As in the hotel, clicking a furni you can stand, sit or lie on walks to the tile clicked on it.
        const clicked = this.room?.furni.find((f) => f.id === hit.id);
        const renderer = this.renderer;
        const goal =
          clicked && renderer
            ? furniWalkTarget(clicked, this.lookup, (height) => renderer.tileAtHeight(x, y, height))
            : null;
        if (goal) this.walkTo(goal);
        return;
      }
      if (hit?.kind === "avatar") {
        // A Click User box can keep the menu shut, as in a real room. Your own still opens.
        this.choose(hit.id === this.user || this.effects?.user_menu !== false ? hit : null);
        // Clicking someone else runs Click User, as it does in a real room.
        if (hit.id !== this.user) void this.send({ type: "click_user", target: hit.id });
        return;
      }
      this.choose(null);
      const tile = this.renderer?.tileAt(x, y);
      if (tile && this.room && fitsInRoom(this.room, [tile])) {
        const clickTile = clickTileAt(this.room, tile[0], tile[1]);
        if (clickTile) void this.send({ type: "click", furni: clickTile.id });
        this.walkTo([tile[0], tile[1]]);
      }
    });
    // A double-click is two clicks first, and each one is a click in the room too.
    canvas.addEventListener("dblclick", (event) => {
      const rect = canvas.getBoundingClientRect();
      const hit = this.renderer?.hitAt(event.clientX - rect.left, event.clientY - rect.top);
      if (hit?.kind === "furni" && this.inspect?.tab !== "furni") this.useFurni(hit.id);
    });
  }

  private async send(entry: Record<string, unknown>): Promise<void> {
    if (this.user === null) return;
    try {
      await this.call(() => post<ViewState>(`${this.url}/input`, { ...entry, user: this.user }));
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  /** One request at a time, in order, so an older answer cannot overwrite a newer one. */
  private call(run: () => Promise<ViewState>): Promise<void> {
    this.waiting += 1;
    const answer = this.queue
      .then(async () => this.apply(await run()))
      .finally(() => {
        this.waiting -= 1;
      });
    this.queue = answer.catch(() => {});
    return answer;
  }

  private async tick(): Promise<void> {
    if (this.waiting > 0) return;
    const now = performance.now();
    const ms = Math.min(Math.round(now - this.lastTick), MAX_TICK_MS);
    try {
      await this.call(() => post<ViewState>(this.query(`${this.url}/advance`), { ms }));
      this.lastTick = now;
    } catch (error) {
      if (error instanceof ApiFailure && error.status === 429) return; // The next tick tries again.
      if (this.timer !== null) clearInterval(this.timer);
      toast(errorMessage(error), "error");
    }
  }

  private apply(state: ViewState): void {
    const room = this.room;
    if (!room) return;
    this.effects = state;
    room.furni = syncTemporary(room.furni, state.furni);
    for (const item of state.furni) {
      const placed = room.furni.find((f) => f.id === item.id);
      if (placed) Object.assign(placed, item);
    }
    room.avatars = room.avatars.filter((a) => state.users.some((u) => u.id === a.id));
    for (const user of state.users) {
      const avatar = room.avatars.find((a) => a.id === user.id);
      // A later request has this avatar's newer step, so this answer would pull it back.
      if (avatar && !((this.walker || this.waiting > 1) && avatar.id === this.user)) {
        this.glideAvatar(avatar, user);
        const stand = standAt(room, this.lookup, user.x, user.y);
        Object.assign(avatar, {
          x: user.x,
          y: user.y,
          dir: user.dir,
          z: stand.z,
          pose: stand.pose,
          details: user.details,
          // Bot Clothes changes what a bot wears.
          ...(user.bot && user.figure ? { figure: user.figure } : {}),
        });
      }
    }
    // Only the latest messages are sent, so a count would stop finding new ones.
    for (const message of state.messages) {
      const key = `${message.at_ms}:${message.text}`;
      if (!this.seen.has(key) && !this.entering) {
        this.addChat(message.text, message.speaker ?? message.user);
      }
      this.seen.add(key);
    }
    this.entering = false;
    const now = performance.now();
    if (now - this.lastInspect >= INSPECT_MS) {
      this.lastInspect = now;
      void this.inspect?.refresh();
    }
    this.draw();
  }

  private glideAvatar(avatar: PlacedAvatar, to: Tile): void {
    if (avatar.x === to.x && avatar.y === to.y) return;
    const steps = glideSteps([avatar.x, avatar.y], [to.x, to.y]);
    if (steps === null) {
      this.avatarGlides.delete(avatar.id);
      return;
    }
    this.avatarGlides.set(avatar.id, {
      from: [avatar.x, avatar.y, avatar.z],
      began: performance.now(),
      ms: steps * SECONDS_PER_STEP * 1000,
    });
    this.renderer?.preloadWalk(avatar, directionBetween([avatar.x, avatar.y], [to.x, to.y]));
  }

  private walkingPose(
    room: RoomDocument,
    avatar: PlacedAvatar,
    from: [number, number, number],
    next: [number, number],
    progress: number,
  ): AvatarPose {
    const [fromX, fromY, fromZ] = from;
    const target = standAt(room, this.lookup, next[0], next[1]);
    const front = drawTile(room, this.lookup, next[0], next[1]);
    const look = withFace(avatarExtras(avatar.details), avatar, performance.now());
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

  private draw(): void {
    const room = this.room;
    if (!room || !this.renderer) return;
    this.renderer.draw({
      flights: this.effects?.flights,
      slides: true,
      fx: this.effects?.fx,
      looks: this.effects?.looks,
      room,
      lookup: this.lookup,
      revisionOf: (classname) => this.items[classname]?.revision ?? null,
      selected: this.selected,
      picked: new Set(),
      ghost: null,
      hover: null,
      avatarPose: (avatar) => {
        const walker = avatar.id === this.user ? this.walker : null;
        const [next] = walker?.path ?? [];
        if (walker && next) {
          const progress = Math.min(1, walker.elapsed / SECONDS_PER_STEP);
          return this.walkingPose(room, avatar, walker.from, next, progress);
        }
        const glide = this.avatarGlides.get(avatar.id);
        if (glide) {
          const progress = (performance.now() - glide.began) / glide.ms;
          if (progress < 1) {
            return this.walkingPose(room, avatar, glide.from, [avatar.x, avatar.y], progress);
          }
          this.avatarGlides.delete(avatar.id);
        }
        const [frontX, frontY] = drawTile(room, this.lookup, avatar.x, avatar.y);
        return {
          x: avatar.x,
          y: avatar.y,
          z: restingHeight(room, this.lookup, avatar),
          // The server turns a seated visitor back to the seat after a moment, as a real room does.
          dir: avatar.dir,
          action: avatar.pose,
          ...withFace(avatarExtras(avatar.details), avatar, performance.now()),
          frontX,
          frontY,
        };
      },
    });
  }
}

customElements.define("wb-room-view", WbRoomView);
