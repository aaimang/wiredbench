import "pixi.js/unsafe-eval"; // Pixi's default shader setup needs eval, which the Content-Security-Policy refuses.
import {
  Application,
  Container,
  Graphics,
  Rectangle,
  Sprite,
  Texture,
  TextureStyle,
} from "pixi.js";
import { get, withQuery } from "../api";
import { depth, screenToTile, TILE_HEIGHT, TILE_WIDTH, tileCentre, Z_UNIT } from "./iso";
import {
  type FurniArtData,
  footprint,
  footprintSize,
  furniParts,
  type InfoLookup,
  type PlacedAvatar,
  type PlacedFurni,
  type RoomDocument,
} from "./model";

export interface FurniManifest extends FurniArtData {
  states: number[];
  colors: Record<string, Record<string, string>>;
}

export interface FurniArt {
  manifest: FurniManifest;
  atlas: Texture;
}

export interface Hit {
  kind: "furni" | "avatar";
  id: number;
}

/** A moving avatar's drawn position and look, which differ from the saved one while it walks. */
export interface AvatarPose {
  x: number;
  y: number;
  z: number;
  dir: number;
  action: string;
  frame: number;
  /** Tile used for draw order, because a walking avatar is between tiles. */
  frontX: number;
  frontY: number;
}

export interface Scene {
  room: RoomDocument;
  lookup: InfoLookup;
  revisionOf: (classname: string) => number | null;
  selected: Hit | null;
  /** Furni a WIRED box has picked, shown while that box is open. */
  picked: Set<number>;
  ghost: { classname: string; x: number; y: number; z: number; rot: number; valid: boolean } | null;
  hover: [number, number] | null;
  avatarPose: (avatar: PlacedAvatar) => AvatarPose;
}

/** Matches ART_VERSION on the server. Furni art is cached for good, so a new shape needs a new address. */
const ART_VERSION = 2;
const AVATAR_ANCHOR = { x: 32, y: 96 };
const AVATAR_SIZE = { w: 64, h: 110 };
const SELECTED_TINT = 0xfff0a0;
const PICKED_TINT = 0xb28ad8;
/** How far a pose sits below the top of its furni, in height units. Matched by eye to real furni. */
const POSE_DROP: Record<string, number> = { sit: 0.5, lay: 0.5 };

function cssColor(name: string, fallback: number): number {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return /^#[0-9a-f]{6}$/i.test(value) ? Number.parseInt(value.slice(1), 16) : fallback;
}

async function loadTexture(url: string): Promise<Texture> {
  const image = new Image();
  image.src = url;
  await image.decode();
  const texture = Texture.from(image);
  texture.source.scaleMode = "nearest";
  return texture;
}

export function avatarUrl(
  avatar: Pick<PlacedAvatar, "hotel" | "figure">,
  action: string,
  dir: number,
  frame: number,
): string {
  return withQuery(`/api/avatars/${avatar.hotel}/image`, {
    figure: avatar.figure,
    action,
    direction: dir,
    frame,
  });
}

/** Draws the room. It holds no room state of its own: each draw takes a complete Scene. */
export class RoomRenderer {
  readonly app = new Application();
  private world = new Container({ sortableChildren: true });
  private floor = new Graphics();
  private marks = new Graphics();
  private layer = new Container({ sortableChildren: true });
  private furni = new Map<string, Promise<FurniArt | null>>();
  private furniLoaded = new Map<string, FurniArt | null>();
  private avatars = new Map<string, Texture | null>();
  private avatarLoading = new Set<string>();
  private parts = new Map<string, Texture>();
  private hits: { hit: Hit; bounds: Rectangle; order: number }[] = [];
  private scene: Scene | null = null;
  private drawnRoomSize = "";
  private panX = 0;
  private panY = 0;

  onChange: () => void = () => {};

  async init(host: HTMLElement): Promise<void> {
    TextureStyle.defaultOptions.scaleMode = "nearest";
    await this.app.init({
      resizeTo: host,
      background: cssColor("--bg", 0xe4e5dc),
      antialias: false,
      preference: "webgl",
      autoStart: true,
    });
    this.app.canvas.setAttribute("data-testid", "room-canvas");
    host.append(this.app.canvas);
    this.floor.zIndex = -2;
    this.marks.zIndex = -1;
    this.world.addChild(this.floor, this.marks, this.layer);
    this.app.stage.addChild(this.world);
  }

  destroy(): void {
    this.app.destroy({ removeView: true }, { children: true });
  }

  /** Fetches a furni's art once. Null means Habbo has none, and a placeholder is drawn. */
  loadFurni(classname: string, revision: number): Promise<FurniArt | null> {
    const key = `${revision}/${classname}`;
    let pending = this.furni.get(key);
    if (!pending) {
      const name = encodeURIComponent(classname);
      pending = (async () => {
        try {
          const manifest = await get<FurniManifest>(
            `/api/furni/${revision}/${name}/manifest?v=${ART_VERSION}`,
          );
          const atlas = await loadTexture(`/api/furni/${revision}/${name}/atlas?v=${ART_VERSION}`);
          return { manifest, atlas };
        } catch {
          return null;
        }
      })().then((art) => {
        this.furniLoaded.set(key, art);
        this.onChange();
        return art;
      });
      this.furni.set(key, pending);
    }
    return pending;
  }

  private avatarTexture(avatar: PlacedAvatar, action: string, dir: number, frame: number) {
    const url = avatarUrl(avatar, action, dir, frame);
    const known = this.avatars.get(url);
    if (known !== undefined) return known;
    if (!this.avatarLoading.has(url)) {
      this.avatarLoading.add(url);
      loadTexture(url)
        .then((texture) => this.avatars.set(url, texture))
        .catch(() => this.avatars.set(url, null))
        .finally(() => {
          this.avatarLoading.delete(url);
          this.onChange();
        });
    }
    return null;
  }

  /** Loads walking frames ahead of time, so the first steps do not flicker. */
  preloadWalk(avatar: PlacedAvatar, dir: number): void {
    for (let frame = 0; frame < 4; frame++) this.avatarTexture(avatar, "wlk", dir, frame);
  }

  private centre(): { x: number; y: number } {
    const { width, height } = this.scene?.room.room ?? { width: 12, height: 12 };
    const mid = tileCentre(width / 2, height / 2);
    return {
      x: this.app.screen.width / 2 - mid.x + this.panX,
      y: this.app.screen.height / 2 - mid.y + this.panY,
    };
  }

  pan(dx: number, dy: number): void {
    this.panX += dx;
    this.panY += dy;
    this.applyPan();
  }

  private applyPan(): void {
    const origin = this.centre();
    this.world.position.set(origin.x, origin.y);
  }

  /** Where a tile appears on the page. Used for tests and for placing the selection bar. */
  tileOnPage(x: number, y: number, z = 0): { x: number; y: number } {
    const point = tileCentre(x, y, z);
    const rect = this.app.canvas.getBoundingClientRect();
    return { x: rect.left + this.world.x + point.x, y: rect.top + this.world.y + point.y };
  }

  tileAt(canvasX: number, canvasY: number): [number, number] {
    return screenToTile(canvasX - this.world.x, canvasY - this.world.y);
  }

  /** The nearest furni or avatar drawn under a canvas position. */
  hitAt(canvasX: number, canvasY: number): Hit | null {
    const x = canvasX - this.world.x;
    const y = canvasY - this.world.y;
    let best: { hit: Hit; order: number } | null = null;
    for (const entry of this.hits) {
      if (entry.bounds.contains(x, y) && (!best || entry.order > best.order)) best = entry;
    }
    return best?.hit ?? null;
  }

  /** Set by a draw that showed something still moving, so the next frame must be drawn too. */
  animating = false;
  private lastMotion = 0;

  /** Furni move at 24 frames a second at most, so a room is not rebuilt on every screen refresh. */
  motionDue(): boolean {
    const now = performance.now();
    if (!this.animating || now - this.lastMotion < 1000 / 24) return false;
    this.lastMotion = now;
    return true;
  }

  private stateSince = new Map<string, { state: number; since: number }>();

  private elapsedInState(item: { x: number; y: number; state: number; id?: number }): number {
    const key = item.id === undefined ? "ghost" : String(item.id);
    const now = performance.now();
    const known = this.stateSince.get(key);
    if (known?.state === item.state) return now - known.since;
    this.stateSince.set(key, { state: item.state, since: now });
    return 0;
  }

  draw(scene: Scene): void {
    this.scene = scene;
    this.animating = false;
    this.applyPan();
    const sizeKey = `${scene.room.room.width}x${scene.room.room.height}`;
    if (sizeKey !== this.drawnRoomSize) {
      this.drawFloor(scene);
      this.drawnRoomSize = sizeKey;
    }
    this.drawMarks(scene);
    for (const child of this.layer.removeChildren()) child.destroy({ children: true });
    this.hits = [];
    for (const item of scene.room.furni) this.drawFurni(scene, item);
    for (const avatar of scene.room.avatars) this.drawAvatar(scene, avatar);
    if (scene.ghost) this.drawGhost(scene);
  }

  private drawFloor(scene: Scene): void {
    const fill = cssColor("--panel", 0xf2f2eb);
    const line = cssColor("--line", 0xc3c5b8);
    const { width, height } = scene.room.room;
    this.floor.clear();
    for (let x = 0; x < width; x++) {
      for (let y = 0; y < height; y++) this.tilePath(this.floor, x, y, 0);
    }
    this.floor.fill(fill).stroke({ width: 1, color: line, pixelLine: true });
  }

  private tilePath(target: Graphics, x: number, y: number, z: number): void {
    const c = tileCentre(x, y, z);
    target.poly([
      c.x,
      c.y - TILE_HEIGHT / 2,
      c.x + TILE_WIDTH / 2,
      c.y,
      c.x,
      c.y + TILE_HEIGHT / 2,
      c.x - TILE_WIDTH / 2,
      c.y,
    ]);
  }

  private drawMarks(scene: Scene): void {
    this.marks.clear();
    if (scene.hover) {
      this.tilePath(this.marks, scene.hover[0], scene.hover[1], 0);
      this.marks.stroke({ width: 2, color: cssColor("--line-strong", 0x8f9386) });
    }
    if (scene.selected?.kind === "furni") {
      const item = scene.room.furni.find((f) => f.id === scene.selected?.id);
      if (item) {
        for (const [x, y] of footprint(item, scene.lookup(item.classname), item.rot)) {
          this.tilePath(this.marks, x, y, 0);
        }
        this.marks.stroke({ width: 2, color: cssColor("--wire-effect", 0xc96f00) });
      }
    }
    if (scene.ghost) {
      const { ghost } = scene;
      const color = ghost.valid
        ? cssColor("--wire-condition", 0x2b7a3d)
        : cssColor("--wire-trigger", 0xc8321e);
      for (const [x, y] of footprint(ghost, scene.lookup(ghost.classname), ghost.rot)) {
        this.tilePath(this.marks, x, y, 0);
      }
      this.marks.stroke({ width: 2, color });
    }
  }

  private artFor(scene: Scene, classname: string): FurniArt | null | undefined {
    const revision = scene.revisionOf(classname);
    if (revision === null) return null;
    const key = `${revision}/${classname}`;
    if (!this.furniLoaded.has(key)) {
      void this.loadFurni(classname, revision);
      return undefined;
    }
    return this.furniLoaded.get(key);
  }

  private front(scene: Scene, item: { x: number; y: number; rot: number; classname: string }) {
    const [width, height] = footprintSize(scene.lookup(item.classname), item.rot);
    return [item.x + width - 1, item.y + height - 1] as const;
  }

  private drawFurni(scene: Scene, item: PlacedFurni): void {
    const selected = scene.selected?.kind === "furni" && scene.selected.id === item.id;
    const tint = selected ? SELECTED_TINT : scene.picked.has(item.id) ? PICKED_TINT : null;
    const bounds = this.addFurniSprites(scene, item, tint, 1, depth);
    if (bounds) {
      const [fx, fy] = this.front(scene, item);
      this.hits.push({
        hit: { kind: "furni", id: item.id },
        bounds,
        order: depth(fx, fy, item.z),
      });
    }
  }

  private drawGhost(scene: Scene): void {
    const ghost = scene.ghost;
    if (!ghost) return;
    const tint = ghost.valid ? null : cssColor("--wire-trigger", 0xc8321e);
    this.addFurniSprites(scene, { ...ghost, state: 0 }, tint, 0.6, (fx, fy, z, layer = 0) =>
      depth(fx, fy, z, layer),
    );
  }

  private addFurniSprites(
    scene: Scene,
    item: {
      id?: number;
      classname: string;
      x: number;
      y: number;
      z: number;
      rot: number;
      state: number;
    },
    tint: number | null,
    opacity: number,
    order: typeof depth,
  ): Rectangle | null {
    const art = this.artFor(scene, item.classname);
    const centre = tileCentre(item.x, item.y, item.z);
    const [fx, fy] = this.front(scene, item);
    if (art === undefined) return null; // Still downloading.
    if (art === null) return this.addPlaceholder(scene, item, tint, opacity);
    const { manifest, atlas } = art;
    const direction = manifest.directions.includes(item.rot)
      ? item.rot
      : (manifest.directions[0] ?? 0);
    const { parts: pose, moving } = furniParts(
      manifest,
      item.classname,
      direction,
      item.state,
      this.elapsedInState(item),
    );
    if (moving) this.animating = true;
    const color = manifest.colors[item.classname.split("*")[1] ?? ""];
    let left = Number.POSITIVE_INFINITY;
    let top = Number.POSITIVE_INFINITY;
    let right = Number.NEGATIVE_INFINITY;
    let bottom = Number.NEGATIVE_INFINITY;
    for (const part of pose) {
      const sprite = new Sprite(this.partTexture(atlas, part));
      const x = centre.x + part.dx;
      const y = centre.y + part.dy;
      if (part.flip) {
        sprite.scale.x = -1;
        sprite.position.set(x + part.w, y);
      } else {
        sprite.position.set(x, y);
      }
      sprite.alpha = (part.alpha / 255) * opacity;
      if (part.ink === "add") sprite.blendMode = "add";
      const layerColor = color?.[String(part.layer)];
      if (tint !== null && part.layer >= 0) sprite.tint = tint;
      else if (layerColor) sprite.tint = Number.parseInt(layerColor, 16);
      sprite.zIndex = order(fx, fy, item.z, part.z);
      this.layer.addChild(sprite);
      if (part.layer >= 0) {
        left = Math.min(left, x);
        top = Math.min(top, y);
        right = Math.max(right, x + part.w);
        bottom = Math.max(bottom, y + part.h);
      }
    }
    return right > left ? new Rectangle(left, top, right - left, bottom - top) : null;
  }

  /** One texture per atlas region, kept for reuse: each one holds a listener on the shared source. */
  private partTexture(
    atlas: Texture,
    part: { x: number; y: number; w: number; h: number },
  ): Texture {
    const key = `${atlas.source.uid}:${part.x},${part.y},${part.w},${part.h}`;
    let texture = this.parts.get(key);
    if (!texture) {
      texture = new Texture({
        source: atlas.source,
        frame: new Rectangle(part.x, part.y, part.w, part.h),
      });
      this.parts.set(key, texture);
    }
    return texture;
  }

  /** A plain block, used when a furni has no art, so that it can still be seen and selected. */
  private addPlaceholder(
    scene: Scene,
    item: { classname: string; x: number; y: number; z: number; rot: number },
    tint: number | null,
    opacity: number,
  ): Rectangle {
    const info = scene.lookup(item.classname);
    const lift = Math.max(info.height, 0.2) * Z_UNIT;
    const c = tileCentre(item.x, item.y, item.z);
    const [fx, fy] = this.front(scene, item);
    const halfW = TILE_WIDTH / 2 - 8;
    const halfH = TILE_HEIGHT / 2 - 4;
    const color = tint ?? cssColor("--wire-utility", 0x6b6f66);
    const block = new Graphics()
      .poly([
        c.x - halfW,
        c.y,
        c.x,
        c.y + halfH,
        c.x + halfW,
        c.y,
        c.x + halfW,
        c.y - lift,
        c.x,
        c.y - lift - halfH,
        c.x - halfW,
        c.y - lift,
      ])
      .fill({ color, alpha: 0.75 * opacity })
      .stroke({ width: 1, color: cssColor("--ink", 0x1c211c), alpha: opacity });
    block.zIndex = depth(fx, fy, item.z);
    this.layer.addChild(block);
    return new Rectangle(c.x - halfW, c.y - lift - halfH, halfW * 2, lift + halfH * 2);
  }

  private drawAvatar(scene: Scene, avatar: PlacedAvatar): void {
    const pose = scene.avatarPose(avatar);
    const centre = tileCentre(pose.x, pose.y, pose.z - (POSE_DROP[pose.action] ?? 0));
    const left = centre.x - AVATAR_ANCHOR.x;
    const top = centre.y - AVATAR_ANCHOR.y;
    const selected = scene.selected?.kind === "avatar" && scene.selected.id === avatar.id;
    const order = depth(pose.frontX, pose.frontY, pose.z, 900);
    const texture = this.avatarTexture(avatar, pose.action, pose.dir, pose.frame);
    if (selected) {
      const ring = new Graphics();
      this.tilePath(ring, pose.x, pose.y, pose.z);
      ring.stroke({ width: 2, color: cssColor("--wire-effect", 0xc96f00) });
      ring.zIndex = order - 1;
      this.layer.addChild(ring);
    }
    if (texture) {
      const sprite = new Sprite(texture);
      sprite.position.set(left, top);
      sprite.zIndex = order;
      this.layer.addChild(sprite);
    } else {
      const stand = new Graphics()
        .ellipse(centre.x, centre.y - 30, 12, 30)
        .fill({ color: cssColor("--wire-utility", 0x6b6f66), alpha: 0.5 });
      stand.zIndex = order;
      this.layer.addChild(stand);
    }
    this.hits.push({
      hit: { kind: "avatar", id: avatar.id },
      bounds: new Rectangle(left + 12, top + 10, AVATAR_SIZE.w - 24, AVATAR_SIZE.h - 14),
      order: order,
    });
  }
}
