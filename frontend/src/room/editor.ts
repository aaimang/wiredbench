import {
  ArrowDownLeft,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpLeft,
  ArrowUpRight,
  Box,
  Eraser,
  Footprints,
  Grid2x2,
  Hammer,
  Redo2,
  RotateCw,
  Save,
  Search,
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

const T = t.editor;
const DEMO_FIGURE = "hd-180-1.ch-210-66.lg-270-82.sh-290-91.hr-100-61";
const SECONDS_PER_STEP = 0.5;
const WALK_FRAMES_PER_SECOND = 8;
const AUTOSAVE_MS = 1500;
const PALETTE_SIZE = 60;

interface SandboxData {
  id: number;
  name: string;
  hotel: string;
  kind: string;
  revision: number;
  updated_at: string;
  document: Record<string, unknown>;
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
  private selected: Hit | null = null;
  private placing: { classname: string; rot: number } | null = null;
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
    replace(
      this,
      this.toolbar,
      h(
        "div",
        { class: "editor-body" },
        this.palette,
        h("div", { class: "editor-stage" }, this.canvasHost, this.selectionBar),
        this.inspector,
      ),
    );
    this.buildPalette();
    this.renderPanels();
    window.addEventListener("keydown", this.onKey);
    window.addEventListener("beforeunload", this.onLeave);
    await this.startRenderer();
  }

  disconnectedCallback(): void {
    window.removeEventListener("keydown", this.onKey);
    window.removeEventListener("beforeunload", this.onLeave);
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
    if (!this.placing || !this.hover) return null;
    const [x, y] = this.hover;
    const { classname, rot } = this.placing;
    const tiles = footprint({ x, y }, this.lookup(classname), rot);
    return {
      classname,
      x,
      y,
      rot,
      z: stackHeight(this.room, this.lookup, tiles),
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
    if (this.needsDraw) {
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
    canvas.addEventListener("pointerleave", () => {
      down = null;
      this.hover = null;
      this.needsDraw = true;
    });
    canvas.addEventListener("pointerup", (event) => {
      const wasDrag = down?.moved;
      down = null;
      if (!wasDrag) this.handleClick(position(event));
    });
  }

  private handleClick(at: { x: number; y: number }): void {
    const renderer = this.renderer;
    if (!renderer) return;
    const tile = renderer.tileAt(at.x, at.y);
    const inside = fitsInRoom(this.room, [tile]);
    if (this.placing) {
      if (inside) this.placeAt(tile);
      return;
    }
    const hit = renderer.hitAt(at.x, at.y);
    if (this.mode === "build") {
      this.select(hit);
      return;
    }
    if (hit?.kind === "avatar") {
      this.select(hit);
      return;
    }
    const clicked = hit ? this.room.furni.find((f) => f.id === hit.id) : null;
    const goal: [number, number] | null = clicked ? [clicked.x, clicked.y] : inside ? tile : null;
    if (goal) this.walkTo(goal);
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

  private markDirty(): void {
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
    if (!sandbox || !this.dirty) return Promise.resolve();
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
      this.select(null);
    } else if (key === "delete" || key === "backspace") {
      this.removeSelected();
    } else if (key === "r") {
      const furni = this.selectedFurni();
      if (furni) void this.rotateFurni(furni);
      else if (this.placing) void this.rotatePlacing();
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
      this.toolButton(T.undo, Undo2, () => this.undoRedo(false), !this.history.canUndo),
      this.toolButton(T.redo, Redo2, () => this.undoRedo(true), !this.history.canRedo),
      this.toolButton(T.roomSize, Grid2x2, () => this.editRoomSize()),
      this.toolButton(T.clearRoom, Eraser, () => this.clearRoom(), this.isEmpty()),
      h("div", { class: "toolbar-spacer" }),
      this.statusLine,
      saveButton,
    );
    this.renderSaveStatus();
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
        this.toolButton(T.cancelPlacing, X, () => {
          this.placing = null;
          this.needsDraw = true;
          this.renderPanels();
        }),
      );
      this.selectionBar.dataset.placing = this.placing.classname;
      this.selectionBar.hidden = false;
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

  private renderInspector(): void {
    const furni = this.selectedFurni();
    const avatar = this.selectedAvatar();
    if (furni) replace(this.inspector, ...this.furniInspector(furni));
    else if (avatar) replace(this.inspector, ...this.avatarInspector(avatar));
    else {
      replace(
        this.inspector,
        h("p", { class: "muted" }, this.mode === "play" ? T.playHint : T.buildHint),
        this.walkStatus,
      );
    }
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
      this.walkStatus,
    ];
  }
}

customElements.define("wb-editor", WbEditor);
