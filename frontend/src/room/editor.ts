import {
  ArrowDownLeft,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpLeft,
  ArrowUpRight,
  Box,
  ClipboardCheck,
  Eraser,
  Footprints,
  Grid2x2,
  Hammer,
  Move,
  PackageOpen,
  Play,
  Power,
  Redo2,
  RotateCw,
  Save,
  Search,
  Square,
  Trash2,
  Undo2,
  UserPlus,
  X,
} from "lucide";
import { ApiFailure, type CatalogItem, get, type ItemPage, request } from "../api";
import { debounce, h, icon, replace } from "../dom";
import { furniSize, hotelLabel, iconUrl, TYPE_ORDER, timeAgo } from "../format";
import { state } from "../state";
import { t } from "../strings";
import { act, confirmDialog, errorMessage, formDialog, toast } from "../ui";
import {
  directionBetween,
  drawTile,
  emptyRoom,
  type FurniInfo,
  findPath,
  fitsInRoom,
  footprint,
  History,
  nextDirection,
  nextId,
  normaliseRoom,
  type PlacedAvatar,
  type PlacedFurni,
  type RoomDocument,
  stackHeight,
  standAt,
  UNKNOWN_FURNI,
} from "./model";
import { type AvatarPose, avatarUrl, type Hit, RoomRenderer, type Scene } from "./renderer";
import {
  type BoxCatalogue,
  type BoxField,
  loadBoxCatalogue,
  RunPanel,
  type RunState,
} from "./run-panel";

const T = t.editor;
const DEMO_FIGURE = "hd-180-1.ch-210-66.lg-270-82.sh-290-91.hr-100-61";
const SECONDS_PER_STEP = 0.5;
const WALK_FRAMES_PER_SECOND = 8;
const AUTOSAVE_MS = 1500;
const PALETTE_SIZE = 60;
const MAX_PICKS = 20;
const ARROW_STEPS: Record<string, [number, number]> = {
  arrowup: [0, -1],
  arrowdown: [0, 1],
  arrowleft: [-1, 0],
  arrowright: [1, 0],
};

interface SandboxData {
  id: number;
  name: string;
  hotel: string;
  kind: string;
  revision: number;
  updated_at: string;
  document: Record<string, unknown>;
}

interface CheckIssue {
  severity: string;
  code: string;
  box: number;
  classname: string;
  x: number;
  y: number;
  message: string;
}

interface Walker {
  avatarId: number;
  path: [number, number][];
  from: [number, number, number];
  elapsed: number;
}

class WbEditor extends HTMLElement {
  private sandbox: SandboxData | null = null;
  private room: RoomDocument = emptyRoom();
  private renderer: RoomRenderer | null = null;
  private items = new Map<string, CatalogItem | null>();
  private history = new History();
  private mode: "build" | "play" = "build";
  private boxes: BoxCatalogue = {};
  private run: RunPanel | null = null;
  private savedRoom: RoomDocument | null = null;
  private picking: { field: BoxField; item: PlacedFurni; chosen: number[] } | null = null;
  private selected: Hit | null = null;
  private placing: { classname: string; rot: number } | null = null;
  private moving: number | null = null;
  private checked: CheckIssue[] | null = null;
  private hover: [number, number] | null = null;
  private walkers = new Map<number, Walker>();
  private clock = 0;
  private dirty = false;
  private savedAt: string | null = null;
  private saveError = "";
  private saving: Promise<void> | null = null;
  private needsDraw = true;
  private query = "";
  private paletteType = "";
  private toolbar = h("div", { class: "toolbar editor-toolbar" });
  private palette = h("aside", { class: "editor-palette" });
  private paletteList = h("div", { class: "palette-list", "data-testid": "palette-list" });
  private canvasHost = h("div", { class: "editor-canvas" });
  private selectionBar = h("div", { class: "selection-bar" });
  private avatarList = h("ul", { class: "avatar-list", "data-testid": "avatar-list" });
  private furniCard = h("div", { class: "furni-card", "data-testid": "furni-card", hidden: true });
  private stage = h("div", { class: "editor-stage" });
  private inspector = h("aside", { class: "editor-inspector", "data-testid": "inspector" });
  private statusLine = h("span", { class: "muted status-line", "data-testid": "save-status" });
  private walkStatus = h("p", { class: "muted", role: "status", "data-testid": "walk-status" });
  private queueSave = debounce(() => void this.save(), AUTOSAVE_MS);
  private onKey = (event: KeyboardEvent) => this.handleKey(event);
  private onLeave = (event: BeforeUnloadEvent) => {
    if (this.dirty) event.preventDefault();
  };

  async connectedCallback(): Promise<void> {
    const id = Number(location.pathname.split("/").at(-1));
    replace(this, h("p", { class: "muted editor-loading" }, t.common.loading));
    try {
      this.sandbox = await get<SandboxData>(`/api/sandboxes/${id}`);
      this.room = normaliseRoom(this.sandbox.document);
      this.savedAt = this.sandbox.updated_at;
      await this.loadItems(this.room.furni.map((f) => f.classname));
    } catch (error) {
      replace(
        this,
        h(
          "div",
          { class: "empty" },
          h("h2", {}, T.cannotOpen),
          h("p", {}, errorMessage(error)),
          h("a", { class: "btn", href: "/workspace" }, t.nav.workspace),
        ),
      );
      return;
    }
    this.stage.append(this.canvasHost, this.selectionBar, this.furniCard);
    replace(
      this,
      this.toolbar,
      h("div", { class: "editor-body" }, this.palette, this.stage, this.inspector),
    );
    this.boxes = await loadBoxCatalogue().catch(() => ({}));
    this.buildPalette();
    this.renderPanels();
    window.addEventListener("keydown", this.onKey);
    window.addEventListener("beforeunload", this.onLeave);
    await this.startRenderer();
  }

  disconnectedCallback(): void {
    window.removeEventListener("keydown", this.onKey);
    window.removeEventListener("beforeunload", this.onLeave);
    this.endRun();
    if (this.dirty) void this.save();
    this.renderer?.destroy();
    this.renderer = null;
  }

  // --- Test and tool access ---

  /** Where a tile appears on the page. */
  tileOnPage(x: number, y: number, z = 0): { x: number; y: number } | null {
    return this.renderer?.tileOnPage(x, y, z) ?? null;
  }

  get roomDocument(): RoomDocument {
    return this.room;
  }

  // --- Rendering ---

  private async startRenderer(): Promise<void> {
    const renderer = new RoomRenderer();
    try {
      await renderer.init(this.canvasHost);
    } catch {
      replace(this.canvasHost, h("p", { class: "note editor-loading" }, T.noWebgl));
      return;
    }
    this.renderer = renderer;
    renderer.onChange = () => {
      this.needsDraw = true;
    };
    renderer.app.ticker.add((ticker) => this.tick(ticker.deltaMS / 1000));
    this.bindPointer(renderer.app.canvas);
    for (const avatar of this.room.avatars) renderer.preloadWalk(avatar, avatar.dir);
  }

  private scene(): Scene {
    return {
      room: this.room,
      lookup: this.lookup,
      revisionOf: (classname) => this.items.get(classname)?.revision ?? null,
      selected: this.selected,
      picked: this.pickedFurni(),
      ghost: this.ghost(),
      hover: this.mode === "play" ? this.hover : null,
      avatarPose: (avatar) => this.avatarPose(avatar),
    };
  }

  private lookup = (classname: string): FurniInfo => {
    const item = this.items.get(classname);
    if (!item) return UNKNOWN_FURNI;
    const data = item.data ?? {};
    return {
      xdim: item.xdim,
      ydim: item.ydim,
      height: item.height ?? 1,
      canStand: data.canstandon === true,
      canSit: data.cansiton === true,
      canLay: data.canlayon === true,
    };
  };

  private ghost(): Scene["ghost"] {
    const moved = this.movingFurni();
    const source = moved ?? this.placing;
    if (!source || !this.hover) return null;
    const [x, y] = this.hover;
    const { classname, rot } = source;
    const tiles = footprint({ x, y }, this.lookup(classname), rot);
    return {
      classname,
      x,
      y,
      rot,
      z: stackHeight(this.room, this.lookup, tiles, moved?.id),
      valid: fitsInRoom(this.room, tiles),
    };
  }

  private avatarPose(avatar: PlacedAvatar): AvatarPose {
    const walker = this.walkers.get(avatar.id);
    const [next] = walker?.path ?? [];
    if (!walker || !next) {
      const [frontX, frontY] = drawTile(this.room, this.lookup, avatar.x, avatar.y);
      return {
        x: avatar.x,
        y: avatar.y,
        z: avatar.z,
        dir: avatar.dir,
        action: avatar.pose,
        frame: 0,
        frontX,
        frontY,
      };
    }
    const progress = Math.min(1, walker.elapsed / SECONDS_PER_STEP);
    const [fromX, fromY, fromZ] = walker.from;
    const target = standAt(this.room, this.lookup, next[0], next[1]);
    const front = drawTile(this.room, this.lookup, next[0], next[1]);
    return {
      x: fromX + (next[0] - fromX) * progress,
      y: fromY + (next[1] - fromY) * progress,
      z: fromZ + (target.z - fromZ) * progress,
      dir: directionBetween([fromX, fromY], next),
      action: "wlk",
      frame: Math.floor(this.clock * WALK_FRAMES_PER_SECOND) % 4,
      frontX: Math.max(fromX, front[0]),
      frontY: Math.max(fromY, front[1]),
    };
  }

  private tick(seconds: number): void {
    if (this.walkers.size > 0) {
      this.clock += seconds;
      this.advanceWalkers(seconds);
      this.needsDraw = true;
    }
    if (this.renderer?.motionDue() || this.needsDraw) {
      this.needsDraw = false;
      this.renderer?.draw(this.scene());
    }
  }

  private advanceWalkers(seconds: number): void {
    for (const walker of [...this.walkers.values()]) {
      const avatar = this.room.avatars.find((a) => a.id === walker.avatarId);
      if (!avatar) {
        this.walkers.delete(walker.avatarId);
        continue;
      }
      walker.elapsed += seconds;
      while (walker.elapsed >= SECONDS_PER_STEP) {
        const next = walker.path.shift();
        if (!next) break;
        walker.elapsed -= SECONDS_PER_STEP;
        const stand = standAt(this.room, this.lookup, next[0], next[1]);
        avatar.dir = directionBetween([walker.from[0], walker.from[1]], next);
        avatar.x = next[0];
        avatar.y = next[1];
        avatar.z = stand.z;
        void this.run?.input({ type: "move", user: avatar.id, x: next[0], y: next[1] });
        walker.from = [next[0], next[1], stand.z];
        const [after] = walker.path;
        if (after) {
          this.renderer?.preloadWalk(avatar, directionBetween(next, after));
        } else {
          this.finishWalk(walker, avatar, stand);
          break;
        }
      }
    }
  }

  private finishWalk(
    walker: Walker,
    avatar: PlacedAvatar,
    stand: ReturnType<typeof standAt>,
  ): void {
    this.walkers.delete(walker.avatarId);
    avatar.pose = stand.pose;
    if (stand.dir !== undefined) avatar.dir = stand.dir;
    this.walkStatus.textContent = T.arrived(avatar.name, stand.pose, avatar.x, avatar.y);
    this.renderInspector();
    this.markDirty();
  }

  // --- Pointer ---

  private bindPointer(canvas: HTMLCanvasElement): void {
    let down: { x: number; y: number; moved: boolean } | null = null;
    const position = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    };
    canvas.addEventListener("pointerdown", (event) => {
      down = { ...position(event), moved: false };
    });
    canvas.addEventListener("pointermove", (event) => {
      const at = position(event);
      if (down) {
        if (down.moved || Math.abs(at.x - down.x) + Math.abs(at.y - down.y) > 4) {
          this.renderer?.pan(at.x - down.x, at.y - down.y);
          down = { ...at, moved: true };
          this.needsDraw = true;
        }
        return;
      }
      const tile = this.renderer?.tileAt(at.x, at.y) ?? null;
      const inside = tile && fitsInRoom(this.room, [tile]);
      const next = inside ? tile : null;
      if (next?.[0] !== this.hover?.[0] || next?.[1] !== this.hover?.[1]) {
        this.hover = next;
        this.needsDraw = true;
      }
    });
    canvas.addEventListener("dblclick", (event) => {
      const at = position(event as unknown as PointerEvent);
      const hit = this.renderer?.hitAt(at.x, at.y);
      if (hit?.kind !== "furni") return;
      if (this.run) {
        void this.run.input({ type: "use", user: this.runUser(), furni: hit.id });
        return;
      }
      const item = this.room.furni.find((f) => f.id === hit.id);
      if (item) void this.useFurni(item);
    });
    canvas.addEventListener("pointerleave", () => {
      down = null;
      this.hover = null;
      this.needsDraw = true;
    });
    canvas.addEventListener("pointerup", (event) => {
      if (!down) return;
      const wasDrag = down.moved;
      down = null;
      if (!wasDrag) this.handleClick(position(event), event);
    });
    // On a Mac, Ctrl+click is a right-click and may never send pointerup.
    canvas.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      if (event.ctrlKey && down && !down.moved) {
        down = null;
        this.handleClick(position(event as unknown as PointerEvent), event);
      }
    });
  }

  private handleClick(at: { x: number; y: number }, keys: MouseEvent): void {
    const renderer = this.renderer;
    if (!renderer) return;
    const tile = renderer.tileAt(at.x, at.y);
    const inside = fitsInRoom(this.room, [tile]);
    if (this.picking) {
      const picked = renderer.hitAt(at.x, at.y);
      if (picked?.kind === "furni") this.togglePick(picked.id);
      return;
    }
    if (this.placing || this.moving !== null) {
      if (inside) {
        if (this.placing) this.placeAt(tile);
        else this.moveTo(tile);
      } else if (state.settings?.click_outside_cancels !== false) {
        this.stopPlacing();
      }
      return;
    }
    const hit = renderer.hitAt(at.x, at.y);
    if (this.mode === "build") {
      this.select(hit);
      if (hit?.kind === "furni") this.applyClickKeys(keys);
      return;
    }
    if (hit?.kind === "avatar") {
      this.select(hit);
      return;
    }
    const clicked = hit ? this.room.furni.find((f) => f.id === hit.id) : null;
    if (clicked && this.run) {
      void this.run.input({ type: "click", user: this.runUser(), furni: clicked.id });
    }
    const goal: [number, number] | null = clicked ? [clicked.x, clicked.y] : inside ? tile : null;
    if (goal) this.walkTo(goal);
  }

  /** Shift turns, Ctrl or Cmd moves, and both together pick up. */
  private applyClickKeys(keys: MouseEvent): void {
    const furni = this.selectedFurni();
    if (!furni) return;
    const command = keys.ctrlKey || keys.metaKey;
    if (command && keys.shiftKey) {
      if (state.settings?.pickup_shortcut !== false) this.removeSelected();
    } else if (command) {
      this.startMoving(furni);
    } else if (keys.shiftKey) {
      void this.rotateFurni(furni);
    }
  }

  private movingFurni(): PlacedFurni | null {
    return this.room.furni.find((f) => f.id === this.moving) ?? null;
  }

  private startMoving(item: PlacedFurni): void {
    this.moving = item.id;
    this.needsDraw = true;
    this.renderPanels();
  }

  private stopPlacing(): void {
    this.placing = null;
    this.moving = null;
    this.needsDraw = true;
    this.renderPanels();
  }

  private moveTo(tile: [number, number]): void {
    const item = this.movingFurni();
    if (!item) return;
    const [dx, dy] = [tile[0] - item.x, tile[1] - item.y];
    if (!this.canMove(item, dx, dy)) {
      toast(T.doesNotFit, "error");
      return;
    }
    this.moveFurni(item, dx, dy);
    this.stopPlacing();
  }

  private async useFurni(item: PlacedFurni): Promise<void> {
    const revision = this.items.get(item.classname)?.revision;
    const art =
      revision === undefined ? null : await this.renderer?.loadFurni(item.classname, revision);
    const states = art?.manifest.states ?? [0, 1];
    const next = states[(states.indexOf(item.state) + 1) % states.length] ?? 0;
    this.change(() => {
      item.state = next;
    });
  }

  private select(hit: Hit | null): void {
    this.selected = hit;
    this.needsDraw = true;
    this.renderPanels();
  }

  // --- Room changes ---

  private change(apply: () => void): void {
    this.history.record(this.room);
    apply();
    this.markDirty();
    this.renderPanels();
  }

  private async checkStacks(): Promise<void> {
    const sandbox = this.sandbox;
    if (!sandbox) return;
    await this.save();
    if (this.saveError) throw new Error(this.saveError);
    const result = await get<{ issues: CheckIssue[] }>(`/api/sandboxes/${sandbox.id}/check`);
    this.checked = result.issues;
    this.select(null);
    const problems = result.issues.filter((issue) => issue.severity !== "info");
    if (!problems.length) toast(T.checkClean);
  }

  private checkResults(): HTMLElement[] {
    const issues = this.checked;
    if (!issues) return [];
    const count = (severity: string) =>
      issues.filter((issue) => issue.severity === severity).length;
    return [
      h("h2", {}, T.checkTitle),
      h(
        "p",
        { "data-testid": "check-summary" },
        count("error") + count("warning")
          ? T.checkFound(count("error"), count("warning"))
          : T.checkClean,
      ),
      h(
        "ul",
        { class: "check-list", "data-testid": "check-list" },
        ...issues.map((issue) =>
          h(
            "li",
            {},
            h(
              "span",
              { class: `badge check-${issue.severity}` },
              T.severity[issue.severity] ?? issue.severity,
            ),
            h(
              "button",
              {
                class: "check-row",
                type: "button",
                onclick: () => this.select({ kind: "furni", id: issue.box }),
              },
              h("code", {}, issue.classname),
              h("span", {}, T.checkRow(issue.x, issue.y, issue.message)),
            ),
          ),
        ),
      ),
    ];
  }

  private markDirty(): void {
    this.checked = null;
    if (this.run) {
      this.needsDraw = true; // A run works on a copy, so nothing here is saved.
      return;
    }
    this.dirty = true;
    this.needsDraw = true;
    this.renderSaveStatus();
    this.queueSave();
  }

  private selectedFurni(): PlacedFurni | null {
    if (this.selected?.kind !== "furni") return null;
    return this.room.furni.find((f) => f.id === this.selected?.id) ?? null;
  }

  private selectedAvatar(): PlacedAvatar | null {
    if (this.selected?.kind !== "avatar") return null;
    return this.room.avatars.find((a) => a.id === this.selected?.id) ?? null;
  }

  private async loadItems(classnames: string[]): Promise<void> {
    const hotel = this.sandbox?.hotel;
    const missing = [...new Set(classnames)].filter((name) => !this.items.has(name));
    await Promise.all(
      missing.map(async (name) => {
        try {
          const item = await get<CatalogItem>(`/api/catalog/items/${encodeURIComponent(name)}`, {
            hotel,
          });
          this.items.set(name, item);
        } catch (error) {
          if (!(error instanceof ApiFailure && error.status === 404)) throw error;
          this.items.set(name, null); // Kept in the room and marked as missing.
        }
      }),
    );
    this.needsDraw = true;
  }

  private async startPlacing(item: CatalogItem): Promise<void> {
    if (item.kind === "wall") {
      toast(T.wallNotYet, "error");
      return;
    }
    this.mode = "build";
    this.moving = null;
    this.placing = null; // Art can be slow to download, and a click meanwhile must not place the old choice.
    this.renderPanels();
    await this.loadItems([item.classname]);
    const art = await this.renderer?.loadFurni(item.classname, item.revision);
    this.placing = { classname: item.classname, rot: art?.manifest.directions[0] ?? 0 };
    this.selected = null;
    this.needsDraw = true;
    this.renderPanels();
  }

  private placeAt(tile: [number, number]): void {
    const placing = this.placing;
    if (!placing) return;
    const { classname, rot } = placing;
    const tiles = footprint({ x: tile[0], y: tile[1] }, this.lookup(classname), rot);
    if (!fitsInRoom(this.room, tiles)) {
      toast(T.doesNotFit, "error");
      return;
    }
    const z = stackHeight(this.room, this.lookup, tiles);
    this.change(() => {
      this.room.furni.push({
        id: nextId(this.room),
        classname,
        x: tile[0],
        y: tile[1],
        z,
        rot,
        state: 0,
      });
    });
  }

  private canMove(item: PlacedFurni, dx: number, dy: number): boolean {
    const tiles = footprint(
      { x: item.x + dx, y: item.y + dy },
      this.lookup(item.classname),
      item.rot,
    );
    return fitsInRoom(this.room, tiles);
  }

  private moveFurni(item: PlacedFurni, dx: number, dy: number): void {
    if (!this.canMove(item, dx, dy)) return;
    this.change(() => {
      item.x += dx;
      item.y += dy;
      item.z = stackHeight(
        this.room,
        this.lookup,
        footprint(item, this.lookup(item.classname), item.rot),
        item.id,
      );
    });
  }

  private async rotateFurni(item: PlacedFurni): Promise<void> {
    const revision = this.items.get(item.classname)?.revision;
    const art =
      revision === undefined ? null : await this.renderer?.loadFurni(item.classname, revision);
    const directions = art?.manifest.directions ?? [0, 2, 4, 6];
    const rot = nextDirection(directions, item.rot);
    const tiles = footprint(item, this.lookup(item.classname), rot);
    if (!fitsInRoom(this.room, tiles)) {
      toast(T.doesNotFit, "error");
      return;
    }
    this.change(() => {
      item.rot = rot;
    });
  }

  private removeSelected(): void {
    const furni = this.selectedFurni();
    const avatar = this.selectedAvatar();
    if (!furni && !avatar) return;
    this.change(() => {
      if (furni) this.room.furni = this.room.furni.filter((f) => f.id !== furni.id);
      if (avatar) {
        this.room.avatars = this.room.avatars.filter((a) => a.id !== avatar.id);
        this.walkers.delete(avatar.id);
      }
      this.selected = null;
    });
  }

  private undoRedo(redo: boolean): void {
    const restored = redo ? this.history.redo(this.room) : this.history.undo(this.room);
    if (!restored) return;
    this.room = restored;
    this.walkers.clear();
    this.selected = null;
    this.markDirty();
    this.renderPanels();
  }

  private addAvatar(name: string, hotel: string, figure: string): void {
    const free = this.freeTile();
    if (!free) {
      toast(T.roomFull, "error");
      return;
    }
    const stand = standAt(this.room, this.lookup, free[0], free[1]);
    const id = nextId(this.room);
    this.change(() => {
      this.room.avatars.push({
        id,
        name,
        hotel,
        figure,
        x: free[0],
        y: free[1],
        z: stand.z,
        dir: 2,
        pose: "std",
      });
      this.selected = { kind: "avatar", id };
    });
    const avatar = this.room.avatars.at(-1);
    if (avatar) this.renderer?.preloadWalk(avatar, 2);
    this.renderPanels();
  }

  /** The free standing tile nearest the middle of the room. */
  private freeTile(): [number, number] | null {
    const { width, height } = this.room.room;
    const taken = new Set(this.room.avatars.map((a) => `${a.x},${a.y}`));
    let best: [number, number] | null = null;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let x = 0; x < width; x++) {
      for (let y = 0; y < height; y++) {
        const stand = standAt(this.room, this.lookup, x, y);
        if (!stand.walkable || stand.pose !== "std" || taken.has(`${x},${y}`)) continue;
        const distance = Math.abs(x - width / 2) + Math.abs(y - height / 2);
        if (distance < bestDistance) {
          best = [x, y];
          bestDistance = distance;
        }
      }
    }
    return best;
  }

  private walkTo(goal: [number, number]): void {
    const avatar = this.selectedAvatar() ?? this.room.avatars[0];
    if (!avatar) {
      toast(T.addAvatarFirst, "error");
      return;
    }
    if (this.selected?.id !== avatar.id) {
      this.selected = { kind: "avatar", id: avatar.id };
      this.renderPanels();
    }
    const walking = this.walkers.get(avatar.id);
    const [nextStep] = walking?.path ?? [];
    const start: [number, number] = nextStep ?? [avatar.x, avatar.y];
    const occupied = new Set(
      this.room.avatars.filter((a) => a.id !== avatar.id).map((a) => `${a.x},${a.y}`),
    );
    const path = findPath(this.room, this.lookup, start, goal, occupied);
    if (path === null) {
      this.walkStatus.textContent = T.noWay(avatar.name);
      return;
    }
    if (path.length === 0 && !walking) return;
    this.walkStatus.textContent = T.walking(avatar.name, goal[0], goal[1]);
    if (walking && nextStep) {
      walking.path = [nextStep, ...path];
      return;
    }
    avatar.pose = "std";
    const [first] = path;
    if (first) this.renderer?.preloadWalk(avatar, directionBetween([avatar.x, avatar.y], first));
    this.walkers.set(avatar.id, {
      avatarId: avatar.id,
      path,
      from: [avatar.x, avatar.y, avatar.z],
      elapsed: 0,
    });
    this.renderInspector();
  }

  // --- Saving ---

  private save(): Promise<void> {
    if (this.saving) {
      // A save is in flight. Once it ends, save anything that changed meanwhile.
      return this.saving.then(() => (this.dirty ? this.save() : undefined));
    }
    const sandbox = this.sandbox;
    if (!sandbox || !this.dirty || this.run) return Promise.resolve();
    const sent = JSON.stringify(this.room);
    this.saving = request<SandboxData>("PUT", `/api/sandboxes/${sandbox.id}/document`, {
      document: this.room,
      base_revision: sandbox.revision,
    })
      .then((saved) => {
        sandbox.revision = saved.revision;
        this.savedAt = saved.updated_at;
        this.saveError = "";
        this.dirty = JSON.stringify(this.room) !== sent;
      })
      .catch((error: unknown) => {
        this.saveError = errorMessage(error);
      })
      .finally(() => {
        this.saving = null;
        this.renderSaveStatus();
      });
    return this.saving;
  }

  // --- Keyboard ---

  private handleKey(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest("input, textarea, select, dialog")) return;
    const command = event.metaKey || event.ctrlKey;
    const key = event.key.toLowerCase();
    if (command && key === "z") {
      event.preventDefault();
      this.undoRedo(event.shiftKey);
    } else if (command && key === "y") {
      event.preventDefault();
      this.undoRedo(true);
    } else if (command && key === "s") {
      event.preventDefault();
      void this.save();
    } else if (key === "escape") {
      this.placing = null;
      this.moving = null;
      this.select(null);
    } else if (key === "delete" || key === "backspace") {
      this.removeSelected();
    } else if (key === "r") {
      const furni = this.selectedFurni();
      if (furni) void this.rotateFurni(furni);
      else if (this.placing) void this.rotatePlacing();
    } else if (this.mode === "build" && this.selectedFurni()) {
      this.handleFurniKey(event, key, this.selectedFurni() as PlacedFurni);
    }
  }

  private handleFurniKey(event: KeyboardEvent, key: string, furni: PlacedFurni): void {
    const step = ARROW_STEPS[key];
    if (step) {
      event.preventDefault();
      this.moveFurni(furni, step[0], step[1]);
    } else if (key === "m") {
      this.startMoving(furni);
    } else if (key === "u") {
      void this.useFurni(furni);
    } else if (key === "p" && state.settings?.pickup_shortcut !== false) {
      this.removeSelected();
    }
  }

  private async rotatePlacing(): Promise<void> {
    const placing = this.placing;
    const revision = placing ? this.items.get(placing.classname)?.revision : undefined;
    if (!placing || revision === undefined) return;
    const art = await this.renderer?.loadFurni(placing.classname, revision);
    placing.rot = nextDirection(art?.manifest.directions ?? [0, 2, 4, 6], placing.rot);
    this.needsDraw = true;
  }

  // --- Panels ---

  private renderPanels(): void {
    this.renderToolbar();
    this.renderSelectionBar();
    this.renderFurniCard();
    this.renderAvatarList();
    this.renderInspector();
  }

  private renderSaveStatus(): void {
    if (this.saveError) {
      this.statusLine.textContent = this.saveError;
      this.statusLine.classList.add("status-error");
      return;
    }
    this.statusLine.classList.remove("status-error");
    this.statusLine.textContent = this.dirty
      ? T.unsaved
      : this.savedAt
        ? T.saved(timeAgo(this.savedAt))
        : "";
  }

  private toolButton(
    label: string,
    node: Parameters<typeof icon>[0],
    run: () => void,
    disabled = false,
  ): HTMLElement {
    return h(
      "button",
      {
        class: "btn btn-quiet btn-icon",
        "aria-label": label,
        title: label,
        disabled,
        onclick: run,
      },
      icon(node),
    );
  }

  private renderToolbar(): void {
    const sandbox = this.sandbox;
    if (!sandbox) return;
    const modeButton = (value: "build" | "play", label: string, node: Parameters<typeof icon>[0]) =>
      h(
        "button",
        {
          class: "segment segment-icon",
          "aria-pressed": String(this.mode === value),
          onclick: () => {
            this.mode = value;
            this.placing = null;
            this.needsDraw = true;
            this.renderPanels();
          },
        },
        icon(node),
        label,
      );
    const saveButton = h("button", { class: "btn" }, icon(Save), T.save);
    saveButton.addEventListener("click", () => void act(saveButton, () => this.save()));
    replace(
      this.toolbar,
      h(
        "a",
        {
          class: "btn btn-quiet btn-icon",
          href: "/workspace",
          "aria-label": T.back,
          title: T.back,
        },
        icon(ArrowLeft),
      ),
      h("h1", { class: "crumbs" }, sandbox.name),
      h(
        "div",
        { class: "segments", role: "group", "aria-label": T.mode },
        modeButton("build", T.build, Hammer),
        modeButton("play", T.play, Footprints),
      ),
      this.runButton(),
      this.toolButton(T.undo, Undo2, () => this.undoRedo(false), !this.history.canUndo),
      this.toolButton(T.redo, Redo2, () => this.undoRedo(true), !this.history.canRedo),
      this.toolButton(T.roomSize, Grid2x2, () => this.editRoomSize()),
      this.toolButton(T.clearRoom, Eraser, () => this.clearRoom(), this.isEmpty()),
      this.toolButton(
        T.checkStacks,
        ClipboardCheck,
        () => void act(null, () => this.checkStacks()),
      ),
      h("div", { class: "toolbar-spacer" }),
      this.statusLine,
      saveButton,
    );
    this.renderSaveStatus();
  }

  private runButton(): HTMLElement {
    const button = h(
      "button",
      { class: "btn btn-primary", "data-testid": "run-button" },
      icon(this.run ? Square : Play),
      this.run ? t.run.stop : t.run.run,
    );
    button.addEventListener("click", () => {
      void act(button, () => (this.run ? Promise.resolve(this.endRun()) : this.startRun()));
    });
    return button;
  }

  private runUser(): number | null {
    return this.selectedAvatar()?.id ?? this.room.avatars[0]?.id ?? null;
  }

  private async startRun(): Promise<void> {
    const sandbox = this.sandbox;
    if (!sandbox) return;
    await this.save();
    if (this.saveError) throw new Error(this.saveError);
    this.savedRoom = JSON.parse(JSON.stringify(this.room));
    this.placing = null;
    this.mode = "play";
    this.selected = null;
    const panel = new RunPanel(
      `/api/sandboxes/${sandbox.id}/run`,
      (state) => this.applyRun(state),
      () => {
        this.endRun();
        this.renderPanels();
      },
      () => this.runUser(),
    );
    this.run = panel;
    this.stage.append(panel.element);
    try {
      await panel.start();
    } catch (error) {
      this.endRun();
      throw error;
    }
    this.renderPanels();
  }

  private endRun(): void {
    if (!this.run) return;
    this.run.stop();
    this.run.element.remove();
    this.run = null;
    this.walkers.clear();
    if (this.savedRoom) this.room = this.savedRoom;
    this.savedRoom = null;
    this.selected = null;
    this.mode = "build";
    this.needsDraw = true;
    this.renderPanels();
  }

  /** Shows what the engine did. Walking avatars are left alone, because the browser moves them. */
  private applyRun(state: RunState): void {
    for (const item of state.furni) {
      const placed = this.room.furni.find((f) => f.id === item.id);
      if (placed) Object.assign(placed, item);
    }
    this.room.avatars = this.room.avatars.filter((a) => state.users.some((u) => u.id === a.id));
    for (const user of state.users) {
      const avatar = this.room.avatars.find((a) => a.id === user.id);
      if (avatar && !this.walkers.has(user.id)) {
        if (avatar.x !== user.x || avatar.y !== user.y) {
          const stand = standAt(this.room, this.lookup, user.x, user.y);
          Object.assign(avatar, { x: user.x, y: user.y, z: stand.z, pose: stand.pose });
        }
        avatar.dir = user.dir;
      }
    }
    this.needsDraw = true;
  }

  private togglePick(id: number): void {
    const picking = this.picking;
    if (!picking) return;
    if (!picking.chosen.includes(id) && picking.chosen.length >= MAX_PICKS) {
      toast(t.run.pickLimit(MAX_PICKS), "error");
      return;
    }
    picking.chosen = picking.chosen.includes(id)
      ? picking.chosen.filter((value) => value !== id)
      : [...picking.chosen, id];
    this.needsDraw = true;
    this.renderInspector();
  }

  /** What the open box has picked: the picks being made, or else all it has saved. */
  private pickedFurni(): Set<number> {
    if (this.picking) return new Set(this.picking.chosen);
    const item = this.selectedFurni();
    const fields = item ? (this.boxes[item.classname]?.fields ?? []) : [];
    const saved = (item?.wired ?? {}) as Record<string, unknown>;
    const picks = fields
      .filter((field) => field.kind === "furni")
      .flatMap((field) => (saved[field.name] as number[] | undefined) ?? []);
    return new Set(picks);
  }

  private pickedList(
    field: BoxField,
    item: PlacedFurni,
    settings: Record<string, unknown>,
    chosen: number[],
  ): HTMLElement {
    if (!chosen.length) return h("p", { class: "muted" }, t.run.pickedEmpty);
    const remove = (id: number) => {
      if (this.picking?.field.name === field.name && this.picking.item.id === item.id) {
        this.togglePick(id);
        return;
      }
      this.change(() => {
        item.wired = { ...settings, [field.name]: chosen.filter((value) => value !== id) };
      });
      this.needsDraw = true;
    };
    return h(
      "ul",
      { class: "picked-list", "data-testid": `picked-${field.name}` },
      ...chosen.map((id) => {
        const furni = this.room.furni.find((f) => f.id === id);
        const name = furni ? this.items.get(furni.classname)?.name || furni.classname : "";
        const label = furni ? t.run.pickedRow(name, furni.x, furni.y) : t.run.pickedMissing(id);
        return h(
          "li",
          {},
          h("span", {}, label),
          h(
            "button",
            {
              class: "btn btn-quiet btn-icon",
              type: "button",
              "aria-label": t.run.removePick(name || String(id)),
              title: t.run.removePick(name || String(id)),
              onclick: () => remove(id),
            },
            icon(X, 14),
          ),
        );
      }),
    );
  }

  /** The settings form for a WIRED box, built from what the engine says the box takes. */
  private boxSettings(item: PlacedFurni): HTMLElement[] {
    if (!item.classname.startsWith("wf_")) return [];
    const spec = this.boxes[item.classname];
    if (!spec) {
      return [
        h("span", { class: "badge badge-hidden", "data-testid": "fidelity" }, t.run.stub),
        h("p", { class: "muted" }, t.run.stubHelp),
      ];
    }
    const settings = (item.wired ?? {}) as Record<string, unknown>;
    const form = h("form", { class: "box-settings", "data-testid": "box-settings" });
    const controls = spec.fields.map((field) => this.fieldControl(field, item, settings));
    form.append(
      h("h3", {}, t.run.settings),
      ...controls,
      h("button", { class: "btn", type: "submit" }, t.run.saveSettings),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      this.saveBoxSettings(form, spec.fields, item, settings);
    });
    const help = t.run.fidelityHelp[spec.fidelity] ?? "";
    return [
      h(
        "span",
        { class: `badge fidelity-${spec.fidelity}`, title: help, "data-testid": "fidelity" },
        t.run.fidelity[spec.fidelity] ?? spec.fidelity,
      ),
      h("p", { class: "muted" }, help),
      ...(spec.fields.length ? [form] : []),
    ];
  }

  private fieldControl(
    field: BoxField,
    item: PlacedFurni,
    settings: Record<string, unknown>,
  ): HTMLElement {
    const value = settings[field.name] ?? field.default;
    const id = `box-${field.name}`;
    let control: HTMLElement;
    if (field.kind === "furni") {
      const picking = this.picking;
      const active = picking?.field.name === field.name && picking.item.id === item.id;
      const chosen = active ? picking.chosen : ((value as number[]) ?? []);
      const button = h(
        "button",
        { class: "btn btn-small", type: "button", "data-field": field.name },
        active ? t.run.picking(chosen.length) : t.run.pick(chosen.length),
      );
      button.addEventListener("click", () => {
        if (active && picking) {
          item.wired = { ...settings, [field.name]: picking.chosen };
          this.picking = null;
          this.needsDraw = true;
          this.change(() => {});
        } else {
          this.picking = { field, item, chosen: [...chosen] };
          this.needsDraw = true;
          this.renderInspector();
        }
      });
      control = h("div", {}, button, this.pickedList(field, item, settings, chosen));
    } else if (field.kind === "bool") {
      control = h("input", { id, name: field.name, type: "checkbox", checked: value === true });
    } else if (field.kind === "select") {
      control = h(
        "select",
        { id, name: field.name },
        ...(field.options ?? []).map((option) =>
          h(
            "option",
            { value: option, selected: option === value },
            field.labels?.[option] ?? option,
          ),
        ),
      );
    } else if (field.kind === "textarea") {
      control = h("textarea", { id, name: field.name, rows: 3 }, String(value ?? ""));
    } else {
      control = h("input", {
        id,
        name: field.name,
        type: field.kind === "number" ? "number" : "text",
        value: String(value ?? ""),
        min: field.min,
        max: field.max,
        step: field.step,
      });
    }
    return h(
      "div",
      { class: "field" },
      h("label", { for: id }, field.label),
      control,
      field.saved_only && h("p", { class: "muted" }, t.run.savedOnly),
    );
  }

  private saveBoxSettings(
    form: HTMLFormElement,
    fields: BoxField[],
    item: PlacedFurni,
    settings: Record<string, unknown>,
  ): void {
    const values = new FormData(form);
    const next: Record<string, unknown> = { ...settings };
    for (const field of fields) {
      if (field.kind === "furni") continue;
      if (field.kind === "bool") next[field.name] = values.get(field.name) !== null;
      else if (field.kind === "number") next[field.name] = Number(values.get(field.name) ?? 0);
      else next[field.name] = String(values.get(field.name) ?? "");
    }
    this.change(() => {
      item.wired = next;
    });
  }

  private isEmpty(): boolean {
    return this.room.furni.length === 0 && this.room.avatars.length === 0;
  }

  private clearRoom(): void {
    confirmDialog(T.confirmClear, T.clearRoom, async () => {
      this.change(() => {
        this.room.furni = [];
        this.room.avatars = [];
        this.walkers.clear();
        this.selected = null;
      });
    });
  }

  private editRoomSize(): void {
    const { width, height } = this.room.room;
    formDialog(
      T.roomSize,
      [
        { name: "width", label: T.width, value: String(width), required: true },
        { name: "height", label: T.depth, value: String(height), required: true },
      ],
      T.apply,
      async (values) => {
        const w = Number(values.width);
        const d = Number(values.height);
        if (!Number.isInteger(w) || !Number.isInteger(d) || w < 1 || d < 1 || w > 64 || d > 64) {
          throw new Error(T.badSize);
        }
        const fits = (x: number, y: number) => x < w && y < d;
        const outside =
          this.room.avatars.some((a) => !fits(a.x, a.y)) ||
          this.room.furni.some((f) =>
            footprint(f, this.lookup(f.classname), f.rot).some(([x, y]) => !fits(x, y)),
          );
        if (outside) throw new Error(T.sizeWouldCut);
        this.change(() => {
          this.room.room = { width: w, height: d };
        });
      },
    );
  }

  private buildPalette(): void {
    const search = h("input", {
      type: "search",
      class: "search-input",
      placeholder: T.searchFurni,
      "aria-label": T.searchFurni,
    });
    search.addEventListener(
      "input",
      debounce(() => {
        this.query = search.value;
        void this.loadPalette();
      }, 200),
    );
    const type = h(
      "select",
      { "aria-label": T.boxType },
      h("option", { value: "" }, T.allWired),
      ...TYPE_ORDER.map((value) => h("option", { value }, t.types[value] ?? value)),
    );
    type.addEventListener("change", () => {
      this.paletteType = type.value;
      void this.loadPalette();
    });
    replace(
      this.palette,
      this.avatarForm(),
      this.avatarList,
      h("h2", {}, T.furni),
      h("label", { class: "search" }, icon(Search), search),
      type,
      this.paletteList,
    );
    void this.loadPalette();
  }

  private avatarForm(): HTMLElement {
    const hotels = state.settings?.hotels ?? [];
    const name = h("input", {
      placeholder: T.habboName,
      "aria-label": T.habboName,
      maxlength: 32,
    });
    const hotel = h(
      "select",
      { "aria-label": T.hotel },
      ...hotels.map((value) =>
        h("option", { value, selected: value === (this.sandbox?.hotel ?? "") }, hotelLabel(value)),
      ),
    );
    const submit = h("button", { class: "btn", type: "submit" }, icon(UserPlus), T.addAvatar);
    const form = h("form", { class: "avatar-form" }, h("h2", {}, T.avatars), name, hotel, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void act(submit, async () => {
        const wanted = name.value.trim();
        if (!wanted) {
          this.addAvatar(T.demoAvatar, hotel.value, DEMO_FIGURE);
          return;
        }
        const found = await get<{ name: string; figure: string }>(
          `/api/avatars/${hotel.value}/lookup`,
          { name: wanted },
        );
        this.addAvatar(found.name, hotel.value, found.figure);
        name.value = "";
      });
    });
    return form;
  }

  private async loadPalette(): Promise<void> {
    try {
      const searching = this.query.trim() !== "";
      const page = await get<ItemPage>("/api/catalog/items", {
        hotel: this.sandbox?.hotel,
        q: this.query,
        scope: searching ? "all" : "wired",
        wired_type: this.paletteType,
        limit: PALETTE_SIZE,
      });
      if (page.version === null) {
        replace(
          this.paletteList,
          h("p", { class: "muted" }, T.noCatalogue),
          h("a", { class: "btn", href: "/catalogue" }, t.nav.catalogue),
        );
        return;
      }
      replace(
        this.paletteList,
        ...(page.items.length === 0 ? [h("p", { class: "muted" }, t.catalogue.noResults)] : []),
        ...page.items.map((item) => this.paletteRow(item)),
        ...(page.total > page.items.length
          ? [h("p", { class: "muted" }, T.moreResults(page.total - page.items.length))]
          : []),
      );
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  private paletteRow(item: CatalogItem): HTMLElement {
    const holder = h("span", { class: "furni-icon" });
    const image = h("img", { src: iconUrl(item), alt: "", loading: "lazy" });
    image.addEventListener("error", () => replace(holder, icon(Box, 16)));
    holder.append(image);
    const row = h(
      "button",
      {
        class: `palette-row wire-${item.wired_type ?? "furni"}`,
        "data-classname": item.classname,
        title: item.description || item.name,
      },
      h("span", { class: "wire-tick" }),
      holder,
      h(
        "span",
        { class: "furni-names" },
        h("span", { class: "furni-name" }, item.name || item.classname),
        h("code", {}, item.classname),
      ),
    );
    row.addEventListener("click", () => {
      void act(row, () => this.startPlacing(item));
    });
    return row;
  }

  private renderSelectionBar(): void {
    const furni = this.selectedFurni();
    const avatar = this.selectedAvatar();
    if (this.placing) {
      replace(
        this.selectionBar,
        h("span", { class: "selection-hint" }, T.placingHint),
        this.toolButton(T.cancelPlacing, X, () => this.stopPlacing()),
      );
      this.selectionBar.dataset.placing = this.placing.classname;
      this.selectionBar.hidden = false;
      return;
    }
    if (this.moving !== null) {
      replace(
        this.selectionBar,
        h("span", { class: "selection-hint" }, T.movingHint),
        this.toolButton(T.cancelMoving, X, () => this.stopPlacing()),
      );
      this.selectionBar.hidden = false;
      delete this.selectionBar.dataset.placing;
      return;
    }
    delete this.selectionBar.dataset.placing;
    if (avatar && this.mode === "build") {
      replace(
        this.selectionBar,
        this.toolButton(T.remove, Trash2, () => this.removeSelected()),
      );
      this.selectionBar.hidden = false;
      return;
    }
    if (!furni || this.mode !== "build") {
      this.selectionBar.hidden = true;
      return;
    }
    const arrow = (label: string, node: Parameters<typeof icon>[0], dx: number, dy: number) =>
      this.toolButton(
        label,
        node,
        () => this.moveFurni(furni, dx, dy),
        !this.canMove(furni, dx, dy),
      );
    replace(
      this.selectionBar,
      arrow(T.moveUpLeft, ArrowUpLeft, -1, 0),
      arrow(T.moveUpRight, ArrowUpRight, 0, -1),
      arrow(T.moveDownLeft, ArrowDownLeft, 0, 1),
      arrow(T.moveDownRight, ArrowDownRight, 1, 0),
      this.toolButton(T.rotate, RotateCw, () => void this.rotateFurni(furni)),
      h(
        "button",
        {
          class: "btn btn-quiet-danger btn-icon",
          "aria-label": T.remove,
          title: T.remove,
          onclick: () => this.removeSelected(),
        },
        icon(Trash2),
      ),
    );
    this.selectionBar.hidden = false;
  }

  private renderFurniCard(): void {
    const furni = this.selectedFurni();
    if (!furni || this.mode !== "build" || this.placing || this.moving !== null) {
      this.furniCard.hidden = true;
      return;
    }
    const info = this.items.get(furni.classname);
    const picture = h("span", { class: "furni-icon" });
    if (info) {
      const image = h("img", { src: iconUrl(info), alt: "" });
      image.addEventListener("error", () => replace(picture, icon(Box, 16)));
      picture.append(image);
    } else {
      picture.append(icon(Box, 16));
    }
    const action = (label: string, node: Parameters<typeof icon>[0], run: () => void) =>
      h("button", { class: "btn btn-small", onclick: run }, icon(node, 14), label);
    const pickUp = state.settings?.pickup_shortcut !== false;
    replace(
      this.furniCard,
      h(
        "div",
        { class: "furni-card-head" },
        picture,
        h("h2", {}, info?.name || furni.classname),
        h(
          "button",
          {
            class: "btn btn-quiet btn-icon",
            "aria-label": T.closeCard,
            title: T.closeCard,
            onclick: () => this.select(null),
          },
          icon(X),
        ),
      ),
      ...(info?.description ? [h("p", {}, info.description)] : []),
      h(
        "div",
        { class: "furni-card-actions" },
        action(T.move, Move, () => this.startMoving(furni)),
        action(T.rotate, RotateCw, () => void this.rotateFurni(furni)),
        action(T.pickUp, PackageOpen, () => this.removeSelected()),
        action(T.use, Power, () => void this.useFurni(furni)),
        action(T.inspect, Search, () => this.inspector.querySelector("h2")?.scrollIntoView()),
      ),
      h("p", { class: "muted" }, pickUp ? T.shortcuts : T.shortcutsNoPickUp),
    );
    this.furniCard.hidden = false;
  }

  private renderInspector(): void {
    const furni = this.selectedFurni();
    const avatar = this.selectedAvatar();
    if (furni) replace(this.inspector, ...this.furniInspector(furni));
    else if (avatar) replace(this.inspector, ...this.avatarInspector(avatar));
    else {
      replace(
        this.inspector,
        ...this.checkResults(),
        h("p", { class: "muted" }, this.mode === "play" ? T.playHint : T.buildHint),
        this.walkStatus,
      );
    }
  }

  private boxProblems(item: PlacedFurni): HTMLElement[] {
    const mine = (this.checked ?? []).filter((issue) => issue.box === item.id);
    if (!mine.length) return [];
    return [
      h(
        "div",
        { class: "note", "data-testid": "box-problems" },
        h("strong", {}, T.boxProblems),
        h("ul", {}, ...mine.map((issue) => h("li", {}, issue.message))),
      ),
    ];
  }

  private furniInspector(item: PlacedFurni): HTMLElement[] {
    const info = this.items.get(item.classname);
    const data = this.lookup(item.classname);
    const position = (label: string, key: "x" | "y" | "z", step: string, readOnly: boolean) => {
      const input = h("input", {
        type: "number",
        step,
        min: 0,
        value: item[key],
        readonly: readOnly,
        "aria-label": label,
      });
      input.addEventListener("change", () => this.setPosition(item, key, Number(input.value)));
      return h("label", { class: "coordinate" }, h("span", {}, label), input);
    };
    const chips = [
      info ? furniSize(info) : null,
      info?.is_wired ? T.wiredChip : null,
      data.canStand ? T.walkChip : null,
      data.canSit ? T.sitChip : null,
      data.canLay ? T.layChip : null,
    ].filter((chip): chip is string => chip !== null);
    return [
      h("h2", {}, info?.name || item.classname),
      ...this.boxProblems(item),
      ...(info?.description ? [h("p", {}, info.description)] : []),
      ...(info === null ? [h("p", { class: "note" }, T.missingFromCatalogue)] : []),
      h("code", {}, item.classname),
      h("div", { class: "chips" }, ...chips.map((chip) => h("span", { class: "badge" }, chip))),
      h(
        "div",
        { class: "coordinates" },
        position("X", "x", "1", false),
        position("Y", "y", "1", false),
        position("Z", "z", "0.01", false),
      ),
      this.stateButtons(item),
      h("p", { class: "muted" }, t.run.idLabel(item.id)),
      ...this.boxSettings(item),
    ];
  }

  private stateButtons(item: PlacedFurni): HTMLElement {
    const holder = h("div", { class: "state-buttons" });
    const revision = this.items.get(item.classname)?.revision;
    if (revision === undefined) return holder;
    void this.renderer?.loadFurni(item.classname, revision).then((art) => {
      const states = art?.manifest.states ?? [];
      if (states.length < 2) return;
      replace(
        holder,
        h("span", { class: "muted" }, T.state),
        ...states.map((value) =>
          h(
            "button",
            {
              class: "btn btn-small",
              "aria-pressed": String(item.state === value),
              disabled: item.state === value,
              onclick: () => this.change(() => (item.state = value)),
            },
            value,
          ),
        ),
      );
    });
    return holder;
  }

  private setPosition(item: PlacedFurni, key: "x" | "y" | "z", value: number): void {
    if (!Number.isFinite(value) || value < 0) {
      this.renderInspector();
      return;
    }
    if (key !== "z") {
      const moved = { x: item.x, y: item.y, [key]: Math.floor(value) };
      const tiles = footprint(moved, this.lookup(item.classname), item.rot);
      if (!fitsInRoom(this.room, tiles)) {
        toast(T.doesNotFit, "error");
        this.renderInspector();
        return;
      }
    }
    this.change(() => {
      item[key] = key === "z" ? Math.min(40, value) : Math.floor(value);
    });
  }

  private renderAvatarList(): void {
    // Redrawing would lose what someone is typing.
    if (
      this.avatarList.contains(document.activeElement) &&
      document.activeElement?.tagName === "INPUT"
    ) {
      return;
    }
    if (!this.room.avatars.length) {
      replace(this.avatarList, h("li", { class: "muted" }, T.noAvatars));
      return;
    }
    replace(this.avatarList, ...this.room.avatars.map((avatar) => this.avatarRow(avatar)));
  }

  private avatarRow(avatar: PlacedAvatar): HTMLElement {
    const selected = this.selected?.kind === "avatar" && this.selected.id === avatar.id;
    const locked = this.run !== null; // A running room has already read its names.
    const name = h("input", {
      value: avatar.name,
      maxlength: 32,
      "aria-label": T.avatarName(avatar.name),
      disabled: locked,
    });
    name.addEventListener("keydown", (event) => {
      if (event.key === "Enter") name.blur();
      if (event.key === "Escape") {
        name.value = avatar.name;
        name.blur();
      }
    });
    name.addEventListener("change", () => this.renameAvatar(avatar, name));
    return h(
      "li",
      { class: "avatar-row", "aria-current": selected ? "true" : null },
      h(
        "button",
        {
          class: "btn avatar-row-pick",
          type: "button",
          "aria-label": T.selectAvatar(avatar.name),
          title: T.selectAvatar(avatar.name),
          onclick: () => this.select({ kind: "avatar", id: avatar.id }),
        },
        h("img", { src: avatarUrl(avatar, "std", 2, 0), alt: "" }),
      ),
      name,
      h(
        "button",
        {
          class: "btn btn-quiet-danger btn-icon",
          type: "button",
          "aria-label": T.removeAvatar(avatar.name),
          title: T.removeAvatar(avatar.name),
          disabled: locked,
          onclick: () => this.removeAvatar(avatar.id),
        },
        icon(Trash2),
      ),
    );
  }

  /** Changes the name shown here. The look stays, because it comes from the saved figure. */
  private renameAvatar(avatar: PlacedAvatar, input: HTMLInputElement): void {
    const wanted = input.value.trim();
    const problem = !/^[\p{L}\p{N}_.-]{1,32}$/u.test(wanted)
      ? T.nameInvalid
      : this.room.avatars.some(
            (other) => other.id !== avatar.id && other.name.toLowerCase() === wanted.toLowerCase(),
          )
        ? T.nameTaken
        : null;
    if (problem) {
      toast(problem, "error");
      input.value = avatar.name;
      return;
    }
    if (wanted === avatar.name) {
      input.value = wanted;
      return;
    }
    input.blur();
    this.change(() => {
      avatar.name = wanted;
    });
  }

  private removeAvatar(id: number): void {
    this.change(() => {
      this.room.avatars = this.room.avatars.filter((a) => a.id !== id);
      this.walkers.delete(id);
      if (this.selected?.kind === "avatar" && this.selected.id === id) this.selected = null;
    });
    this.needsDraw = true;
  }

  private avatarInspector(avatar: PlacedAvatar): HTMLElement[] {
    const preview = h("img", {
      src: avatarUrl(avatar, avatar.pose, avatar.dir, 0),
      alt: "",
      class: "avatar-preview",
    });
    return [
      preview,
      h("h2", {}, avatar.name),
      h("p", { class: "muted" }, hotelLabel(avatar.hotel)),
      h(
        "p",
        { "data-testid": "avatar-position" },
        T.avatarAt(avatar.x, avatar.y, T.poses[avatar.pose] ?? avatar.pose),
      ),
      h("p", { class: "muted" }, this.mode === "play" ? T.clickToWalk : T.switchToPlay),
      ...(this.run ? [this.avatarDebug(avatar)] : []),
      this.walkStatus,
    ];
  }

  /** Puts a user where a test needs them while the room runs. Height comes from what is on the tile. */
  private avatarDebug(avatar: PlacedAvatar): HTMLElement {
    const number = (label: string, value: number, max: number) =>
      h("input", { type: "number", min: 0, max, value, "aria-label": label });
    const x = number(T.debugX, avatar.x, this.room.room.width - 1);
    const y = number(T.debugY, avatar.y, this.room.room.height - 1);
    const dir = number(T.debugDir, avatar.dir, 7);
    const apply = async () => {
      const [toX, toY] = [Number(x.value), Number(y.value)];
      if (toX !== avatar.x || toY !== avatar.y) {
        await this.run?.input({ type: "move", user: avatar.id, x: toX, y: toY });
      }
      await this.run?.input({ type: "turn", user: avatar.id, dir: Number(dir.value) });
      this.renderInspector();
    };
    return h(
      "form",
      {
        class: "avatar-debug",
        "data-testid": "avatar-debug",
        onsubmit: (event: Event) => {
          event.preventDefault();
          void apply();
        },
      },
      h("label", {}, T.debugX, x),
      h("label", {}, T.debugY, y),
      h("label", {}, T.debugDir, dir),
      h("p", { class: "muted" }, T.debugHeight(avatar.z)),
      h("button", { class: "btn", type: "submit" }, T.debugApply),
    );
  }
}

customElements.define("wb-editor", WbEditor);
