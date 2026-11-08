import "pixi.js/unsafe-eval"; // Pixi's default shader setup needs eval, which the Content-Security-Policy refuses.
import {
  Application,
  BlurFilter,
  ColorMatrixFilter,
  Container,
  Graphics,
  Rectangle,
  Sprite,
  Texture,
  TextureStyle,
} from "pixi.js";
import { get, withQuery } from "../api";
import { state } from "../state";
import { fxArt, fxHeight } from "./fx-art";
import { depth, screenToTile, TILE_HEIGHT, TILE_WIDTH, tileCentre, Z_UNIT } from "./iso";
import {
  type AvatarAction,
  avatarExtras,
  EFFECT_FRAME_MS,
  type EffectManifest,
  effectLayers,
  FACE_NAMES,
  type Flight,
  type FurniArtData,
  type FxShown,
  faceGestures,
  faceIsAnimated,
  figureAction,
  flightAt,
  footprint,
  footprintSize,
  furniAt,
  furniParts,
  type Highlight,
  highlightTint,
  type InfoLookup,
  type Look,
  lookAmount,
  type PlacedAvatar,
  type PlacedFurni,
  pickWalkLook,
  type RoomDocument,
  SIXTY_SEVEN_MS,
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
  /** Added to the pose in the avatar's image, such as a sign. */
  extra?: string[];
  gesture?: string;
  frame: number;
  /** An action's own frame while walking, such as a kiss, so it does not step with the legs. */
  actionFrame?: number;
  /** Tile used for draw order, because a walking avatar is between tiles. */
  frontX: number;
  frontY: number;
}

export interface Scene {
  flights?: Flight[] | null;
  /** A furni moved by WIRED slides to its new tile. Off while building, where a move is instant. */
  slides?: boolean;
  fx?: FxShown[] | null;
  looks?: { furni: Record<number, Look>; users: Record<number, Look> } | null;
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
// Invisible is fully hidden, as in a real room. Only what the builder has selected stays findable.
const SELECTED_INVISIBLE_OPACITY = 0.35;
const SETTLED_MS = 3_600_000;
/** Assumed from the engine's half-second tick. Not measured in a real room. */
const SLIDE_MS = 500;
const OUTLINE_OFFSETS = [
  [-1, -1],
  [0, -1],
  [1, -1],
  [-1, 0],
  [1, 0],
  [-1, 1],
  [0, 1],
  [1, 1],
];
const GLOW_OFFSETS = [...OUTLINE_OFFSETS, [-2, 0], [2, 0], [0, -2], [0, 2]];
const GLOW_OPACITY = 0.8;
/** Space between the head and the first variable shown over it. */
const FX_GAP_USER = 8;
const FX_RISE_FURNI = 40;
const ART_VERSION = 3;
const AVATAR_ANCHOR = { x: 32, y: 96 };
/** Room the server leaves around an avatar drawn with an effect, matching EFFECT_MARGIN there. */
const EFFECT_MARGIN = { x: 52, top: 90 };
const SELECTED_TINT = 0xfff0a0;
const PICKED_TINT = 0xb28ad8;
/** How far a pose sits below the top of its furni, in height units. Matched by eye to real furni. */
/** Habbo's client draws a sitting or lying avatar half its 64 pixel scale lower than a standing one. */
const POSTURE_DROP = 32;
/**
 * The lying image is 110 by 64. Habbo's client puts its art origin 30 pixels along from the standing
 * one (the horizontal canvas's own offset), so facing 2 its top left is 47 left of the tile centre, and
 * facing 4, which is mirrored, 63.
 */
const LAY_IMAGE = { w: 110, h: 64, left2: 47, left4: 63, top: 16 };
/** How far below the image's top the head starts, measured on Habbo's images: standing and sitting, lying. */
const HEAD_IN_IMAGE = { upright: 23, lay: 13 };
/** Habbo gets four downloads at a time, and this leaves two for images already on screen. */
const WARM_DOWNLOADS = 2;
const MAX_WARM_QUEUE = 512;
const WALK_FRAMES = [0, 1, 2, 3];
const ALL_DIRECTIONS = [0, 1, 2, 3, 4, 5, 6, 7];

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
  gesture = "std",
  effect?: number,
  effectFrame = 0,
  actionFrame?: number,
): string {
  // The choice is part of the address, so switching it never shows an image cached the other way.
  const ours = state.settings?.avatar_drawing === "wiredbench";
  return withQuery(`/api/avatars/${avatar.hotel}/image`, {
    figure: avatar.figure,
    action,
    gesture,
    direction: dir,
    frame,
    ...(ours ? { drawn_by: "wiredbench" } : {}),
    ...(effect ? { effect, effect_frame: effectFrame } : {}),
    // Only drawn here: Habbo's image service has one frame for the walk and the action together.
    ...(ours && actionFrame !== undefined ? { action_frame: actionFrame } : {}),
  });
}

/**
 * Where an avatar's image goes for its pose, from the tile point at its height: the top left, size and
 * where the head starts. Matches Habbo's client: sitting and lying drop 32 pixels, lying is wider.
 */
export function avatarImageAt(
  pose: Pick<AvatarPose, "action" | "dir">,
  centre: { x: number; y: number },
): { left: number; top: number; w: number; h: number; head: number } {
  if (pose.action === "lay") {
    const left = centre.x - (pose.dir === 2 ? LAY_IMAGE.left2 : LAY_IMAGE.left4);
    const top = centre.y - LAY_IMAGE.top;
    return { left, top, w: LAY_IMAGE.w, h: LAY_IMAGE.h, head: top + HEAD_IN_IMAGE.lay };
  }
  const top = centre.y - AVATAR_ANCHOR.y + (pose.action === "sit" ? POSTURE_DROP : 0);
  return {
    left: centre.x - AVATAR_ANCHOR.x,
    top,
    w: 64,
    h: 110,
    head: top + HEAD_IN_IMAGE.upright,
  };
}

/** Habbo's floor shadow for an avatar's pose: standing (and walking) or sitting. Lying has none. */
export function shadowUrl(
  avatar: Pick<PlacedAvatar, "hotel">,
  pose: Pick<AvatarPose, "action" | "dir">,
): string {
  const kind = pose.action === "sit" || pose.action === "lay" ? pose.action : "std";
  return withQuery(`/api/avatars/${avatar.hotel}/shadow`, { pose: kind, direction: pose.dir });
}

/**
 * The image of an avatar with a body-changing effect at a moment. The pose keeps its own frame, such
 * as a step of the walk, and the effect plays on its own clock, so walking still moves the legs.
 */
export function bodyEffectUrl(
  avatar: Pick<PlacedAvatar, "hotel" | "figure">,
  pose: Pick<AvatarPose, "action" | "extra" | "dir" | "frame" | "gesture">,
  effect: number,
  frameCount: number,
  nowMs: number,
): string {
  const step = Math.floor(nowMs / EFFECT_FRAME_MS);
  return avatarUrl(
    avatar,
    figureAction(pose.action, pose.extra ?? []),
    pose.dir,
    pose.frame,
    pose.gesture,
    effect,
    frameCount > 1 ? step % frameCount : 0,
  );
}

/** The frames an action plays on its own clock while walking. Sixty-seven swaps signs instead. */
function walkActionFrames(action?: AvatarAction): (number | undefined)[] {
  return action && action !== "sixty_seven" ? [0, 1] : [undefined];
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
  private avatarLoading = new Map<string, Promise<void>>();
  private avatarShown = new Map<
    number,
    {
      texture: Texture;
      dir: number;
      extra: string[];
      gesture: string | undefined;
      actionFrame?: number;
    }
  >();
  private warmQueue: string[] = [];
  private warmLoading = 0;
  private parts = new Map<string, Texture>();
  /** Undefined while loading, null when the effect cannot be drawn. */
  /** Undefined while loading, null when unknown. A body-changing effect has no atlas. */
  private effects = new Map<
    string,
    { manifest: EffectManifest; atlas: Texture | null } | null | undefined
  >();
  /** Per avatar, the last effect image shown for each way of facing and step, and overall. */
  private effectShown = new Map<number, Map<string, Texture>>();
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
    this.app.renderer.on("resize", () => this.onChange()); // The room is centred when drawn.
    host.append(this.app.canvas);
    this.floor.zIndex = -2;
    this.marks.zIndex = -1;
    this.world.addChild(this.floor, this.marks, this.layer);
    this.app.stage.addChild(this.world);
  }

  destroy(): void {
    this.app.destroy({ removeView: true }, { children: true });
  }

  /** Fetches an effect's layers once. Null means it is unknown, so the avatar shows without it. */
  private loadEffect(hotel: string, effect: number): void {
    const key = `${hotel}/${effect}`;
    if (this.effects.has(key)) return;
    this.effects.set(key, undefined);
    void (async () => {
      try {
        const manifest = await get<EffectManifest>(`/api/effects/${hotel}/${effect}/manifest`);
        if (!manifest.drawable) return { manifest, atlas: null };
        const atlas = await loadTexture(`/api/effects/${hotel}/${effect}/atlas`);
        return { manifest, atlas };
      } catch {
        return null;
      }
    })().then((art) => {
      this.effects.set(key, art);
      this.onChange();
    });
  }

  /** Draws an avatar's effect around its image, in front of it or behind it. */
  private drawEffect(avatar: PlacedAvatar, dir: number, left: number, top: number, order: number) {
    const effect = (avatar.details as Record<string, number> | undefined)?.["@effect"] ?? 0;
    if (effect <= 0) return;
    const art = this.effects.get(`${avatar.hotel}/${effect}`);
    if (art === undefined) {
      this.loadEffect(avatar.hotel, effect);
      return;
    }
    if (!art?.atlas) return;
    if ((art.manifest.frames?.length ?? 0) > 1) this.animating = true;
    for (const layer of effectLayers(art.manifest, dir, performance.now())) {
      const sprite = new Sprite(this.partTexture(art.atlas, layer.image));
      sprite.position.set(left + layer.x, top + layer.y);
      // Layers keep their own order around the avatar without passing anything else in the room.
      sprite.zIndex = order + (layer.front ? 0.0001 : -0.0001) * (1 + Math.abs(layer.dz));
      if (layer.add) sprite.blendMode = "add";
      this.layer.addChild(sprite);
    }
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

  private avatarTexture(
    avatar: PlacedAvatar,
    action: string,
    dir: number,
    frame: number,
    gesture = "std",
  ) {
    const url = avatarUrl(avatar, action, dir, frame, gesture);
    const known = this.avatars.get(url);
    if (known !== undefined) return known;
    this.loadAvatar(url);
    return null;
  }

  private loadAvatar(url: string): Promise<void> {
    if (this.avatars.has(url)) return Promise.resolve();
    let loading = this.avatarLoading.get(url);
    if (!loading) {
      loading = loadTexture(url)
        .then((texture) => void this.avatars.set(url, texture))
        .catch(() => void this.avatars.set(url, null))
        .finally(() => {
          this.avatarLoading.delete(url);
          this.onChange();
        });
      this.avatarLoading.set(url, loading);
    }
    return loading;
  }

  private async loadAvatars(urls: string[]): Promise<void> {
    await Promise.all(urls.map((url) => this.loadAvatar(url)));
  }

  /** Loads images nobody is waiting for yet, leaving Habbo's other download slots for those in view. */
  private warm(urls: string[]): void {
    const wanted = urls.filter((url) => !this.avatars.has(url));
    // The latest request goes first, because it is what the avatar is doing now.
    // An effect asks for new frames all the time, so the oldest requests are let go.
    this.warmQueue = [...new Set([...wanted, ...this.warmQueue])].slice(0, MAX_WARM_QUEUE);
    while (this.warmLoading < WARM_DOWNLOADS) {
      const url = this.warmQueue.shift();
      if (!url) return;
      if (this.avatars.has(url) || this.avatarLoading.has(url)) continue;
      this.warmLoading++;
      void this.loadAvatar(url).finally(() => {
        this.warmLoading--;
        this.warm([]);
      });
    }
  }

  /**
   * Loads walking frames ahead of time, so a step or a turn never waits on a frame. They must match
   * what the avatar is holding or doing, because each combination is its own set of images.
   */
  preloadWalk(
    avatar: PlacedAvatar,
    dir: number,
    details: unknown = avatar.details,
    action?: AvatarAction,
  ): void {
    // Sixty-seven swaps between two signs, so both sets are needed.
    for (const elapsed of action === "sixty_seven" ? [0, SIXTY_SEVEN_MS] : [0]) {
      const { extra, gesture } = avatarExtras(details, action, elapsed);
      const gestures = faceGestures(avatar.face);
      for (const look of gestures.length ? gestures : [gesture]) {
        for (const actionFrame of walkActionFrames(action)) {
          this.loadWalkLook(avatar, extra, look, dir, actionFrame);
        }
      }
    }
  }

  private faceUrls(avatar: PlacedAvatar, pose: AvatarPose): string[] {
    const action = figureAction(pose.action, pose.extra ?? []);
    const frames = pose.action === "wlk" ? [0, 1, 2, 3] : [pose.frame];
    const gestures = faceGestures(avatar.face);
    return (gestures.length ? gestures : ["std"]).flatMap((gesture) =>
      frames.map((frame) => avatarUrl(avatar, action, pose.dir, frame, gesture)),
    );
  }

  /** Settles once all of this avatar's chosen face can be shown in this pose. */
  loadFace(avatar: PlacedAvatar, pose: AvatarPose): Promise<void> {
    return this.loadAvatars(this.faceUrls(avatar, pose));
  }

  private actionUrls(
    avatar: PlacedAvatar,
    pose: string,
    dir: number,
    action: AvatarAction,
  ): string[] {
    const { extra, gesture } = avatarExtras(avatar.details, action);
    const shown = figureAction(pose, extra);
    const faces = faceGestures(avatar.face);
    const gestures = faces.length ? faces : [gesture];
    const frames = pose === "wlk" ? [0, 1, 2, 3] : [0, 1];
    // Walking, each step comes with each of the action's own frames.
    const own = pose === "wlk" ? walkActionFrames(action) : [undefined];
    return gestures.flatMap((look) => [
      ...frames.flatMap((frame) =>
        own.map((actionFrame) =>
          avatarUrl(avatar, shown, dir, frame, look, undefined, 0, actionFrame),
        ),
      ),
      ...(action === "sixty_seven"
        ? frames.map((frame) =>
            avatarUrl(avatar, figureAction(pose, ["sig=7", ...extra.slice(1)]), dir, frame, look),
          )
        : []),
    ]);
  }

  /** Settles once every frame of an action can be shown, so it starts without a stutter. */
  preloadAction(
    avatar: PlacedAvatar,
    pose: string,
    dir: number,
    action: AvatarAction,
  ): Promise<void> {
    return this.loadAvatars(this.actionUrls(avatar, pose, dir, action));
  }

  /** Loads what the user panel can ask for next, so a choice is usually ready when it is made. */
  warmChoices(
    avatar: PlacedAvatar,
    details: unknown,
    actions: AvatarAction[],
    signs: number,
  ): void {
    const { pose, dir } = avatar;
    // First the plain walk, which any walk can fall back on, then how this avatar looks now.
    const look = avatarExtras(details);
    const lookGestures = faceGestures(avatar.face);
    const walking = [
      { extra: [] as string[], gesture: "std" },
      ...(lookGestures.length ? lookGestures : [look.gesture]).map((gesture) => ({
        extra: look.extra,
        gesture,
      })),
    ].flatMap(({ extra, gesture }) =>
      ALL_DIRECTIONS.flatMap((direction) =>
        WALK_FRAMES.map((frame) => this.walkUrl(avatar, extra, gesture, direction, frame)),
      ),
    );
    const faces = FACE_NAMES.flatMap((face) =>
      this.faceUrls({ ...avatar, face }, {
        ...avatarExtras(avatar.details),
        action: pose,
        dir,
      } as AvatarPose),
    );
    const moves = actions.flatMap((action) => this.actionUrls(avatar, pose, dir, action));
    const gestures = faceGestures(avatar.face);
    const held = Array.from({ length: signs }, (_, sign) => {
      const { extra, gesture } = avatarExtras({
        ...((avatar.details ?? {}) as object),
        "@sign": sign,
      });
      return avatarUrl(avatar, figureAction(pose, extra), dir, 0, gestures[0] ?? gesture);
    });
    this.warm([...walking, ...faces, ...moves, ...held]);
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
  /** Set by a draw that showed a furni sliding or flying, which moves on every frame like a walk. */
  private travelling = false;
  private lastMotion = 0;

  /**
   * Furni art animates at 24 frames a second at most, so a room is not rebuilt on every screen refresh.
   * A furni travelling across the room is drawn every frame, or it would move in visible jumps.
   */
  motionDue(): boolean {
    const now = performance.now();
    if (this.travelling) {
      this.lastMotion = now;
      return true;
    }
    if (!this.animating || now - this.lastMotion < 1000 / 24) return false;
    this.lastMotion = now;
    return true;
  }

  private flightStarts = new Map<string, number>();
  private slides = new Map<
    number,
    { from: [number, number]; to: [number, number]; began: number }
  >();
  private drawnAt = new Map<number, [number, number]>();
  private stateSince = new Map<string, { state: number; since: number }>();

  private elapsedInState(item: { x: number; y: number; state: number; id?: number }): number {
    const key = item.id === undefined ? "ghost" : String(item.id);
    const now = performance.now();
    const known = this.stateSince.get(key);
    if (known?.state === item.state) return now - known.since;
    // A furni seen for the first time did not just change, so it starts long past any transition.
    const elapsed = known ? 0 : SETTLED_MS;
    this.stateSince.set(key, { state: item.state, since: now - elapsed });
    return elapsed;
  }

  draw(scene: Scene): void {
    this.scene = scene;
    this.animating = false;
    this.travelling = false;
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
    this.drawFx(scene);
  }

  /** Wiredbench's own plain numbers and bars, stacked over each holder. Not Habbo's art. */
  private drawFx(scene: Scene): void {
    const used = new Map<string, number>();
    const ordered = [...(scene.fx ?? [])].sort((a, b) => a.order - b.order);
    for (const fx of ordered) {
      const holder =
        fx.target === "user"
          ? scene.room.avatars.find((a) => a.id === fx.id)
          : scene.room.furni.find((f) => f.id === fx.id);
      if (!holder) continue;
      const key = `${fx.target}:${fx.id}`;
      const below = used.get(key) ?? 0;
      const height = fxHeight(fx.kind);
      used.set(key, below + height);
      const { centre, rise } =
        fx.target === "user"
          ? this.overHead(scene, holder as PlacedAvatar)
          : { centre: tileCentre(holder.x, holder.y, holder.z), rise: FX_RISE_FURNI };
      const art = fxArt(fx);
      art.position.set(centre.x, centre.y - rise - below - height / 2);
      art.zIndex = Number.MAX_SAFE_INTEGER;
      this.layer.addChild(art);
    }
  }

  /**
   * Where a user's variables start: just over the head as drawn, so they follow a walk, drop with a
   * seat, and rise with an effect that lifts the avatar, such as a broom.
   */
  private overHead(
    scene: Scene,
    avatar: PlacedAvatar,
  ): { centre: { x: number; y: number }; rise: number } {
    const pose = scene.avatarPose(avatar);
    const centre = tileCentre(pose.x, pose.y, pose.z);
    const { head } = avatarImageAt(pose, centre);
    const effect = (avatar.details as Record<string, number> | undefined)?.["@effect"] ?? 0;
    const art = effect > 0 ? this.effects.get(`${avatar.hotel}/${effect}`) : undefined;
    const drawsBody =
      state.settings?.avatar_drawing === "wiredbench" && art?.manifest.drawable === false;
    const lift = drawsBody ? (art?.manifest.lift ?? 0) : 0;
    return { centre, rise: centre.y - head + FX_GAP_USER + lift };
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

  /** Where a furni is drawn while it flies or slides, and where it ended up once it has. */
  private flown(scene: Scene, item: PlacedFurni): PlacedFurni {
    const shown = this.travelled(scene, item);
    this.drawnAt.set(item.id, [shown.x, shown.y]);
    return shown;
  }

  /** Clocks start when the browser hears of a move, so it is never cut short. */
  private travelled(scene: Scene, item: PlacedFurni): PlacedFurni {
    const now = performance.now();
    // An older flight is kept for a while after landing, so only one that ends here is this move.
    const flight = scene.flights?.find(
      (f) => f.id === item.id && f.to[0] === item.x && f.to[1] === item.y,
    );
    if (flight) {
      this.slides.delete(item.id);
      const key = `${flight.id}:${flight.start_ms}`;
      const began = this.flightStarts.get(key) ?? now;
      this.flightStarts.set(key, began);
      const progress = (now - began) / flight.ms;
      if (progress >= 1) return item;
      this.animating = true;
      this.travelling = true;
      const at = flightAt(flight, progress);
      return { ...item, x: at.x, y: at.y, z: item.z + at.lift / Z_UNIT };
    }
    const last = this.drawnAt.get(item.id);
    let slide = this.slides.get(item.id);
    if (slide && (slide.to[0] !== item.x || slide.to[1] !== item.y)) slide = undefined;
    if (!slide && scene.slides && last && (last[0] !== item.x || last[1] !== item.y)) {
      slide = { from: last, to: [item.x, item.y], began: now };
      this.slides.set(item.id, slide);
    }
    const progress = slide ? (now - slide.began) / SLIDE_MS : 1;
    if (!slide || progress >= 1) {
      this.slides.delete(item.id);
      return item;
    }
    this.animating = true;
    this.travelling = true;
    const [fromX, fromY] = slide.from;
    return {
      ...item,
      x: fromX + (item.x - fromX) * progress,
      y: fromY + (item.y - fromY) * progress,
    };
  }

  private drawFurni(scene: Scene, placed: PlacedFurni): void {
    const item = this.flown(scene, placed);
    const selected = scene.selected?.kind === "furni" && scene.selected.id === item.id;
    const look = scene.looks?.furni[item.id];
    if (look?.highlight?.pulse) this.animating = true;
    const tint = selected
      ? SELECTED_TINT
      : scene.picked.has(item.id)
        ? PICKED_TINT
        : highlightTint(look?.highlight, performance.now());
    const opacity = look?.invisible ? (selected ? SELECTED_INVISIBLE_OPACITY : 0) : 1;
    const bounds = this.addFurniSprites(scene, item, tint, opacity, depth, look?.highlight);
    if (bounds && !look?.click_through) {
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
    highlight?: Highlight,
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
    const drawn: Sprite[] = [];
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
        drawn.push(sprite);
        left = Math.min(left, x);
        top = Math.min(top, y);
        right = Math.max(right, x + part.w);
        bottom = Math.max(bottom, y + part.h);
      }
    }
    if (highlight && opacity > 0) this.addLook(drawn, highlight);
    return right > left ? new Rectangle(left, top, right - left, bottom - top) : null;
  }

  /** Draws the looks a tint cannot: an edge around the shape, or light added on top of it. */
  private addLook(sprites: Sprite[], look: Highlight): void {
    const amount = lookAmount(look, performance.now());
    if (amount <= 0 || !sprites.length) return;
    const copy = (source: Sprite, dx = 0, dy = 0) => {
      const sprite = new Sprite(source.texture);
      sprite.position.set(source.x + dx, source.y + dy);
      sprite.scale.copyFrom(source.scale);
      return sprite;
    };
    if (look.type === "brighten") {
      for (const source of sprites) {
        const light = copy(source);
        light.blendMode = "add";
        light.alpha = amount;
        light.zIndex = source.zIndex + 0.001;
        this.layer.addChild(light);
      }
      return;
    }
    if (look.type !== "outline" && look.type !== "glow") return;
    const glow = look.type === "glow";
    const edge = new Container();
    for (const [dx = 0, dy = 0] of glow ? GLOW_OFFSETS : OUTLINE_OFFSETS) {
      for (const source of sprites) edge.addChild(copy(source, dx, dy));
    }
    // Every pixel becomes the chosen colour and only its transparency is kept, which makes a silhouette.
    const solid = new ColorMatrixFilter();
    const [r, g, b] = [(look.color >> 16) & 255, (look.color >> 8) & 255, look.color & 255];
    solid.matrix = [0, 0, 0, 0, r / 255, 0, 0, 0, 0, g / 255, 0, 0, 0, 0, b / 255, 0, 0, 0, 1, 0];
    edge.filters = glow ? [solid, new BlurFilter({ strength: 3 })] : [solid];
    edge.alpha = glow ? amount * GLOW_OPACITY : amount;
    edge.zIndex = Math.min(...sprites.map((sprite) => sprite.zIndex)) - 0.001;
    this.layer.addChild(edge);
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

  private standingTexture(avatar: PlacedAvatar, pose: AvatarPose): Texture | null {
    const action = figureAction(pose.action, pose.extra ?? []);
    const loaded = this.avatarTexture(avatar, action, pose.dir, pose.frame, pose.gesture);
    const last = this.avatarShown.get(avatar.id);
    if (loaded) {
      this.avatarShown.set(avatar.id, {
        texture: loaded,
        dir: pose.dir,
        extra: pose.extra ?? [],
        gesture: pose.gesture,
      });
      return loaded;
    }
    // Facing the same way, the last image beats a flash of the default face.
    if (last?.dir === pose.dir) return last.texture;
    return (
      this.avatars.get(avatarUrl(avatar, pose.action, pose.dir, pose.frame)) ??
      last?.texture ??
      null
    );
  }

  /**
   * A walk never waits on an image. It shows the closest look with all four steps loaded, so the
   * avatar keeps stepping, and looks are not mixed on the way, which would flicker.
   */
  private walkingTexture(avatar: PlacedAvatar, pose: AvatarPose): Texture | null {
    const extra = pose.extra ?? [];
    const last = this.avatarShown.get(avatar.id);
    this.loadWalkLook(avatar, extra, pose.gesture, pose.dir, pose.actionFrame);
    const look = pickWalkLook<{
      extra: string[];
      gesture: string | undefined;
      actionFrame?: number;
    }>(
      [
        { extra, gesture: pose.gesture, actionFrame: pose.actionFrame },
        ...(last
          ? [{ extra: last.extra, gesture: last.gesture, actionFrame: last.actionFrame }]
          : []),
        { extra: [], gesture: pose.gesture },
        { extra: [], gesture: "std" },
      ],
      (option) =>
        WALK_FRAMES.every((frame) =>
          this.avatars.get(
            this.walkUrl(avatar, option.extra, option.gesture, pose.dir, frame, option.actionFrame),
          ),
        ),
    );
    if (!look) return last?.texture ?? null;
    const texture = this.avatars.get(
      this.walkUrl(avatar, look.extra, look.gesture, pose.dir, pose.frame, look.actionFrame),
    );
    if (!texture) return last?.texture ?? null;
    this.avatarShown.set(avatar.id, { texture, dir: pose.dir, ...look });
    return texture;
  }

  private walkUrl(
    avatar: PlacedAvatar,
    extra: string[],
    gesture: string | undefined,
    dir: number,
    frame: number,
    actionFrame?: number,
  ): string {
    return avatarUrl(
      avatar,
      figureAction("wlk", extra),
      dir,
      frame,
      gesture,
      undefined,
      0,
      actionFrame,
    );
  }

  private loadWalkLook(
    avatar: PlacedAvatar,
    extra: string[],
    gesture: string | undefined,
    dir: number,
    actionFrame?: number,
  ): void {
    for (const frame of WALK_FRAMES)
      void this.loadAvatar(this.walkUrl(avatar, extra, gesture, dir, frame, actionFrame));
  }

  /**
   * An effect that changes the body, such as a hoverboard, drawn by the server one frame at a time. Only
   * with Wiredbench's own avatar drawing, because Habbo's image service draws no effects. Null otherwise.
   */
  private bodyEffectTexture(
    avatar: PlacedAvatar,
    pose: AvatarPose,
  ): { texture: Texture | null } | null {
    if (state.settings?.avatar_drawing !== "wiredbench") return null;
    const effect = (avatar.details as Record<string, number> | undefined)?.["@effect"] ?? 0;
    if (effect <= 0) return null;
    const art = this.effects.get(`${avatar.hotel}/${effect}`);
    if (art === undefined) this.loadEffect(avatar.hotel, effect);
    const count = art?.manifest.drawable === false ? (art.manifest.frame_count ?? 0) : 0;
    if (!count) return null;
    if (count > 1) this.animating = true;
    const now = performance.now();
    const at = (ms: number, step = pose.frame) =>
      bodyEffectUrl(avatar, { ...pose, frame: step }, effect, count, ms);
    const url = at(now);
    const loaded = this.avatars.get(url);
    if (loaded === undefined) void this.loadAvatar(url);
    // The server could not draw this one. The plain avatar keeps walking and turning, where holding the
    // last effect image would look frozen.
    if (loaded === null) return null;
    // The next effect frames, and every step of a walk, so a step never waits on an image.
    const steps = pose.action === "wlk" ? WALK_FRAMES : [pose.frame];
    this.warm(
      [1, 2].flatMap((ahead) => steps.map((step) => at(now + ahead * EFFECT_FRAME_MS, step))),
    );
    // While this one loads, the last image shown facing this way and at this step keeps the legs
    // moving and the turn shown. Only with nothing like it does the last image stay up.
    const shown = this.effectShown.get(avatar.id) ?? new Map<string, Texture>();
    const key = `${effect}/${pose.dir}/${pose.frame}/${pose.action}`;
    if (loaded) {
      shown.set(key, loaded);
      shown.set("last", loaded);
      this.effectShown.set(avatar.id, shown);
    }
    return { texture: loaded ?? shown.get(key) ?? shown.get("last") ?? null };
  }

  /**
   * The floor shadow Habbo's client draws under every avatar. It stays on the floor when an effect lifts
   * the avatar, and is left out when the effect removes it or draws its own.
   */
  private drawShadow(
    avatar: PlacedAvatar,
    pose: AvatarPose,
    left: number,
    top: number,
    order: number,
  ) {
    const effect = (avatar.details as Record<string, number> | undefined)?.["@effect"] ?? 0;
    const art = effect > 0 ? this.effects.get(`${avatar.hotel}/${effect}`) : undefined;
    const drawsBody =
      state.settings?.avatar_drawing === "wiredbench" && art?.manifest.drawable === false;
    if (drawsBody && art?.manifest.shadow !== undefined && art.manifest.shadow !== "plain") return;
    const url = shadowUrl(avatar, pose);
    const texture = this.avatars.get(url);
    if (texture === undefined) void this.loadAvatar(url);
    if (!texture) return;
    const sprite = new Sprite(texture);
    sprite.position.set(left, top);
    sprite.zIndex = order - 0.5;
    this.layer.addChild(sprite);
  }

  /**
   * Where an avatar sorts among furni. Someone sitting or lying sorts at the seat's own level, between
   * its layers: Habbo's furni art gives parts in front of a sitter, such as a chair back seen from
   * behind, a positive depth and parts behind a negative one.
   */
  private avatarOrder(scene: Scene, pose: AvatarPose): number {
    if (pose.action === "sit" || pose.action === "lay") {
      const seat = furniAt(scene.room, scene.lookup, Math.round(pose.x), Math.round(pose.y)).at(-1);
      if (seat) return depth(pose.frontX, pose.frontY, seat.z, 0);
    }
    return depth(pose.frontX, pose.frontY, pose.z, 900);
  }

  private drawAvatar(scene: Scene, avatar: PlacedAvatar): void {
    const pose = scene.avatarPose(avatar);
    const centre = tileCentre(pose.x, pose.y, pose.z);
    const { left, top, w, h } = avatarImageAt(pose, centre);
    const selected = scene.selected?.kind === "avatar" && scene.selected.id === avatar.id;
    const order = this.avatarOrder(scene, pose);
    const changed = this.bodyEffectTexture(avatar, pose);
    const texture =
      changed?.texture ??
      (changed
        ? null
        : pose.action === "wlk"
          ? this.walkingTexture(avatar, pose)
          : this.standingTexture(avatar, pose));
    if (faceIsAnimated(avatar.face)) this.animating = true;
    void this.loadFace(avatar, pose);
    if (selected) {
      const ring = new Graphics();
      this.tilePath(ring, pose.x, pose.y, pose.z);
      ring.stroke({ width: 2, color: cssColor("--wire-effect", 0xc96f00) });
      ring.zIndex = order - 1;
      this.layer.addChild(ring);
    }
    const look = scene.looks?.users[avatar.id];
    if (texture && !look?.invisible) this.drawShadow(avatar, pose, left, top, order);
    if (texture) {
      const sprite = new Sprite(texture);
      sprite.position.set(
        left - (changed ? EFFECT_MARGIN.x : 0),
        top - (changed ? EFFECT_MARGIN.top : 0),
      );
      sprite.zIndex = order;
      if (look?.highlight?.pulse) this.animating = true;
      const tinted = highlightTint(look?.highlight, performance.now());
      if (tinted !== null) sprite.tint = tinted;
      if (look?.invisible) sprite.alpha = selected ? SELECTED_INVISIBLE_OPACITY : 0;
      this.layer.addChild(sprite);
      if (look?.highlight && !look.invisible) this.addLook([sprite], look.highlight);
      if (!look?.invisible && !changed) this.drawEffect(avatar, pose.dir, left, top, order);
    } else {
      const stand = new Graphics()
        .ellipse(centre.x, centre.y - 30, 12, 30)
        .fill({ color: cssColor("--wire-utility", 0x6b6f66), alpha: 0.5 });
      stand.zIndex = order;
      this.layer.addChild(stand);
    }
    if (scene.looks?.users[avatar.id]?.click_through) return;
    this.hits.push({
      hit: { kind: "avatar", id: avatar.id },
      bounds: new Rectangle(left + 12, top + 10, w - 24, h - 14),
      // A click on a seated avatar picks the avatar, even where the seat is drawn over it.
      order: depth(pose.frontX, pose.frontY, pose.z, 900),
    });
  }
}
