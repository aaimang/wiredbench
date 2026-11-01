import { ApiFailure, get, post } from "../api";
import { h, replace } from "../dom";
import { t } from "../strings";
import { errorMessage, toast } from "../ui";
import {
  avatarExtras,
  drawTile,
  type FurniInfo,
  fitsInRoom,
  normaliseRoom,
  type RoomDocument,
  standAt,
  UNKNOWN_FURNI,
} from "./model";
import { RoomRenderer } from "./renderer";

const T = t.viewAs;
const TICK_MS = 1000;

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
  private seen = 0;

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
        this,
        h(
          "div",
          { class: "view-room" },
          h(
            "div",
            { class: "view-head" },
            h("a", { href: "/view" }, T.back),
            h("h1", {}, data.name),
            this.avatarPicker(),
          ),
          canvas,
          h(
            "div",
            { class: "view-foot" },
            h("p", { class: "muted" }, T.help),
            this.log,
            this.sayForm(),
          ),
        ),
      );
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
        renderer.app.ticker.add(() => {
          if (renderer.motionDue()) this.draw();
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
      this.seen = 0;
      replace(this.log);
    });
    return h("label", { for: "view-user" }, `${T.actingAs} `, select);
  }

  private sayForm(): HTMLElement {
    const input = h("input", {
      placeholder: T.say,
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
      void this.send({ type: "say", text });
    });
    return form;
  }

  private bindPointer(canvas: HTMLCanvasElement): void {
    canvas.addEventListener("click", (event) => {
      const rect = canvas.getBoundingClientRect();
      const [x, y] = [event.clientX - rect.left, event.clientY - rect.top];
      const hit = this.renderer?.hitAt(x, y);
      if (hit?.kind === "furni") {
        void this.send({ type: "click", furni: hit.id });
        return;
      }
      const tile = this.renderer?.tileAt(x, y);
      if (tile && this.room && fitsInRoom(this.room, [tile])) {
        void this.send({ type: "move", x: tile[0], y: tile[1] });
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
      if (avatar) {
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
    for (const message of state.messages.slice(this.seen)) {
      this.log.append(h("li", {}, message.text));
    }
    this.seen = state.messages.length;
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
        const [frontX, frontY] = drawTile(room, this.lookup, avatar.x, avatar.y);
        return {
          x: avatar.x,
          y: avatar.y,
          z: avatar.z,
          dir: avatar.dir,
          action: avatar.pose,
          ...avatarExtras(avatar.details),
          frontX,
          frontY,
        };
      },
    });
  }
}

customElements.define("wb-room-view", WbRoomView);
