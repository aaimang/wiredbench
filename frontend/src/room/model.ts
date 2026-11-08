/** The room as data, with no drawing or network code, so its rules can be tested directly. */

export const MAX_STEP_UP = 1.5;
const MAX_LAY_HEIGHT = 0.9;

export interface PlacedFurni {
  id: number;
  classname: string;
  x: number;
  y: number;
  z: number;
  rot: number;
  state: number;
  [key: string]: unknown;
}

export interface PlacedAvatar {
  id: number;
  name: string;
  hotel: string;
  figure: string;
  x: number;
  y: number;
  z: number;
  dir: number;
  pose: "std" | "sit" | "lay";
  face?: string | null;
  [key: string]: unknown;
}

export interface RoomDocument {
  schema: number;
  room: { width: number; height: number; timezone?: string };
  furni: PlacedFurni[];
  avatars: PlacedAvatar[];
  [key: string]: unknown;
}

/** What the room needs to know about a kind of furni, from furnidata. */
export interface FurniInfo {
  xdim: number;
  ydim: number;
  height: number;
  canStand: boolean;
  canSit: boolean;
  canLay: boolean;
  canStack: boolean;
  /** How it reacts when used, such as a dice or a gate. Plain furni when left out. */
  kind?: FurniKind;
}

export type InfoLookup = (classname: string) => FurniInfo;

/** Used for furni that is missing from the catalogue, so a saved room still opens. */
export const UNKNOWN_FURNI: FurniInfo = {
  xdim: 1,
  ydim: 1,
  height: 1,
  canStand: false,
  canSit: false,
  canLay: false,
  canStack: true,
};

export function emptyRoom(): RoomDocument {
  return { schema: 1, room: { width: 12, height: 12 }, furni: [], avatars: [] };
}

/** Fills in anything a saved document lacks. Unknown fields stay, so nothing is lost on saving. */
export function normaliseRoom(document: Record<string, unknown>): RoomDocument {
  const base = emptyRoom();
  return {
    ...document,
    schema: base.schema,
    room: (document.room as RoomDocument["room"] | undefined) ?? base.room,
    furni: (document.furni as PlacedFurni[] | undefined) ?? [],
    avatars: (document.avatars as PlacedAvatar[] | undefined) ?? [],
  };
}

export function nextId(room: RoomDocument): number {
  return Math.max(0, ...room.furni.map((f) => f.id), ...room.avatars.map((a) => a.id)) + 1;
}

/** Width along x and depth along y. Turning a quarter turn swaps them. */
export function footprintSize(info: FurniInfo, rot: number): [number, number] {
  return rot === 2 || rot === 6 ? [info.ydim, info.xdim] : [info.xdim, info.ydim];
}

export function footprint(
  item: { x: number; y: number },
  info: FurniInfo,
  rot: number,
): [number, number][] {
  const [width, depth] = footprintSize(info, rot);
  const tiles: [number, number][] = [];
  for (let dx = 0; dx < width; dx++) {
    for (let dy = 0; dy < depth; dy++) tiles.push([item.x + dx, item.y + dy]);
  }
  return tiles;
}

export function fitsInRoom(room: RoomDocument, tiles: [number, number][]): boolean {
  return tiles.every(([x, y]) => x >= 0 && y >= 0 && x < room.room.width && y < room.room.height);
}

export function furniAt(
  room: RoomDocument,
  lookup: InfoLookup,
  x: number,
  y: number,
  ignoreId?: number,
): PlacedFurni[] {
  return room.furni
    .filter(
      (item) =>
        item.id !== ignoreId &&
        footprint(item, lookup(item.classname), item.rot).some(([fx, fy]) => fx === x && fy === y),
    )
    .sort((a, b) => a.z - b.z);
}

/** The height something placed here would rest at: on top of the tallest thing on any of its tiles. */
export function stackHeight(
  room: RoomDocument,
  lookup: InfoLookup,
  tiles: [number, number][],
  ignoreId?: number,
): number {
  let top = 0;
  for (const [x, y] of tiles) {
    for (const item of furniAt(room, lookup, x, y, ignoreId)) {
      top = Math.max(top, item.z + lookup(item.classname).height);
    }
  }
  return Math.round(top * 100) / 100;
}

/** As in a real room, nothing can be put on furni whose top cannot hold things, such as a chair. */
export function canStackOn(
  room: RoomDocument,
  lookup: InfoLookup,
  tiles: [number, number][],
  ignoreId?: number,
): boolean {
  return tiles.every(([x, y]) => {
    const top = furniAt(room, lookup, x, y, ignoreId).at(-1);
    return !top || lookup(top.classname).canStack;
  });
}

export interface Stand {
  walkable: boolean;
  z: number;
  pose: "std" | "sit" | "lay";
  dir?: number;
}

/** What standing on a tile means, decided by the top furni there. */
export function standAt(room: RoomDocument, lookup: InfoLookup, x: number, y: number): Stand {
  const top = furniAt(room, lookup, x, y).at(-1);
  if (!top) return { walkable: true, z: 0, pose: "std" };
  const info = lookup(top.classname);
  // A gate is walked through only while it is open, as in a real room.
  if (info.kind === "gate") return { walkable: top.state !== 0, z: top.z, pose: "std" };
  // Sit and lay heights are the furni's own height, like a stand. A real seat's sit height may differ.
  const z = top.z + info.height;
  if (info.canSit) return { walkable: true, z, pose: "sit", dir: top.rot };
  // Bed heights in furnidata are for stacking and sit well above the mattress.
  if (info.canLay) {
    // A bed is lain along its length, head on the pillow at its first row: facing 2 along x, 4 along y.
    const [width, length] = footprintSize(info, top.rot);
    return {
      walkable: true,
      z: top.z + Math.min(info.height, MAX_LAY_HEIGHT),
      pose: "lay",
      dir: width >= length ? 2 : 4,
    };
  }
  if (info.canStand) return { walkable: true, z, pose: "std" };
  return { walkable: false, z, pose: "std" };
}

/**
 * The tile an avatar rests on after walking to a tile. On a bed that is the head row, in the lane of
 * the tile chosen, so a one-tile-wide bed is lain in the middle and a double bed on one side.
 */
export function restTile(
  room: RoomDocument,
  lookup: InfoLookup,
  x: number,
  y: number,
): [number, number] {
  const top = furniAt(room, lookup, x, y).at(-1);
  if (!top || !lookup(top.classname).canLay) return [x, y];
  const [width, length] = footprintSize(lookup(top.classname), top.rot);
  return width >= length ? [top.x, y] : [x, top.y];
}

/** Where an avatar at rest faces: the way its seat or bed is turned, or its own direction. */
/** Which way each seated or lying avatar faces now, so standing them up later keeps it. */
export function seatedFacing(room: RoomDocument, lookup: InfoLookup): Map<number, number> {
  return new Map(
    room.avatars
      .filter((avatar) => avatar.pose === "sit" || avatar.pose === "lay")
      .map((avatar) => [avatar.id, restingDir(room, lookup, avatar)]),
  );
}

/**
 * Stands up anyone left sitting or lying where their seat or bed is no longer, such as after the chair is
 * moved or picked up in Build mode. A real room stands them up too. They keep facing the way they faced
 * on the seat, from `facing` taken before the change. Says whether anyone moved.
 */
export function standUpOffSeats(
  room: RoomDocument,
  lookup: InfoLookup,
  facing: Map<number, number> = new Map(),
): boolean {
  let moved = false;
  for (const avatar of room.avatars) {
    if (avatar.pose !== "sit" && avatar.pose !== "lay") continue;
    const stand = standAt(room, lookup, avatar.x, avatar.y);
    if (stand.pose === avatar.pose) continue;
    avatar.pose = "std";
    avatar.z = stand.pose === "std" ? stand.z : 0;
    avatar.dir = facing.get(avatar.id) ?? avatar.dir;
    moved = true;
  }
  return moved;
}

export function restingDir(
  room: RoomDocument,
  lookup: InfoLookup,
  avatar: { x: number; y: number; dir: number },
): number {
  return standAt(room, lookup, avatar.x, avatar.y).dir ?? avatar.dir;
}

/**
 * The tile that decides an avatar's draw order. On large furni it is that furni's front tile, or the
 * furni, which draws from its own front tile, would cover an avatar sitting or standing on it.
 */
export function drawTile(
  room: RoomDocument,
  lookup: InfoLookup,
  x: number,
  y: number,
): [number, number] {
  const top = furniAt(room, lookup, x, y).at(-1);
  if (!top) return [x, y];
  const [width, depth] = footprintSize(lookup(top.classname), top.rot);
  return [Math.max(x, top.x + width - 1), Math.max(y, top.y + depth - 1)];
}

/** Direction numbers: 0 is -y, then clockwise on screen, so 2 is +x and 4 is +y. */
const MAX_GLIDE_STEPS = 2;

/** How many tiles an avatar walks to get there, or null when it is too far and simply appears. */
export function glideSteps(from: [number, number], to: [number, number]): number | null {
  const steps = Math.max(Math.abs(to[0] - from[0]), Math.abs(to[1] - from[1]));
  return steps > MAX_GLIDE_STEPS ? null : steps;
}

export function directionBetween(from: [number, number], to: [number, number]): number {
  const dx = Math.sign(to[0] - from[0]);
  const dy = Math.sign(to[1] - from[1]);
  const table: Record<string, number> = {
    "0,-1": 0,
    "1,-1": 1,
    "1,0": 2,
    "1,1": 3,
    "0,1": 4,
    "-1,1": 5,
    "-1,0": 6,
    "-1,-1": 7,
  };
  return table[`${dx},${dy}`] ?? 2;
}

export function nextDirection(directions: number[], current: number): number {
  if (directions.length === 0) return current;
  const index = directions.indexOf(current);
  return directions[(index + 1) % directions.length] ?? current;
}

/** Tiles in the Habbo walking style: eight directions, without cutting across blocked corners. */
export function findPath(
  room: RoomDocument,
  lookup: InfoLookup,
  start: [number, number],
  goal: [number, number],
  occupied: Set<string> = new Set(),
): [number, number][] | null {
  const key = (x: number, y: number) => `${x},${y}`;
  const { width, height } = room.room;
  const inRoom = (x: number, y: number) => x >= 0 && y >= 0 && x < width && y < height;
  if (!inRoom(...goal) || !standAt(room, lookup, ...goal).walkable) return null;
  if (occupied.has(key(...goal))) return null;

  const stands = new Map<string, Stand>();
  const stand = (x: number, y: number) => {
    const k = key(x, y);
    let value = stands.get(k);
    if (!value) {
      value = standAt(room, lookup, x, y);
      stands.set(k, value);
    }
    return value;
  };
  const isGoal = (x: number, y: number) => x === goal[0] && y === goal[1];
  const passable = (x: number, y: number, fromZ: number) => {
    if (!inRoom(x, y) || occupied.has(key(x, y))) return false;
    const here = stand(x, y);
    if (!here.walkable || here.z - fromZ > MAX_STEP_UP) return false;
    // Seats and beds can be sat on but not walked across.
    return here.pose === "std" || isGoal(x, y);
  };

  const heuristic = (x: number, y: number) =>
    Math.max(Math.abs(x - goal[0]), Math.abs(y - goal[1]));
  const costs = new Map([[key(...start), 0]]);
  const cameFrom = new Map<string, [number, number]>();
  const open: { x: number; y: number; score: number }[] = [
    { x: start[0], y: start[1], score: heuristic(...start) },
  ];

  while (open.length > 0) {
    let best = 0;
    for (let i = 1; i < open.length; i++) {
      if ((open[i]?.score ?? 0) < (open[best]?.score ?? 0)) best = i;
    }
    const current = open.splice(best, 1)[0] as { x: number; y: number };
    if (isGoal(current.x, current.y)) {
      const path: [number, number][] = [];
      let step: [number, number] | undefined = [current.x, current.y];
      while (step && !(step[0] === start[0] && step[1] === start[1])) {
        path.unshift(step);
        step = cameFrom.get(key(...step));
      }
      return path;
    }
    const fromZ = stand(current.x, current.y).z;
    const cost = costs.get(key(current.x, current.y)) ?? 0;
    for (const dx of [-1, 0, 1]) {
      for (const dy of [-1, 0, 1]) {
        if (dx === 0 && dy === 0) continue;
        const x = current.x + dx;
        const y = current.y + dy;
        if (!passable(x, y, fromZ)) continue;
        if (dx !== 0 && dy !== 0) {
          // A diagonal step needs both tiles beside it clear.
          if (!passable(current.x + dx, current.y, fromZ)) continue;
          if (!passable(current.x, current.y + dy, fromZ)) continue;
        }
        // Slightly above 1 so straight lines win over zigzags of the same length.
        const next = cost + (dx !== 0 && dy !== 0 ? 1.001 : 1);
        if (next < (costs.get(key(x, y)) ?? Number.POSITIVE_INFINITY)) {
          costs.set(key(x, y), next);
          cameFrom.set(key(x, y), [current.x, current.y]);
          open.push({ x, y, score: next + heuristic(x, y) });
        }
      }
    }
  }
  return null;
}

/** Undo and redo over whole-room snapshots. */
export class History {
  private past: string[] = [];
  private future: string[] = [];
  private static readonly LIMIT = 200;

  record(room: RoomDocument): void {
    this.past.push(JSON.stringify(room));
    if (this.past.length > History.LIMIT) this.past.shift();
    this.future = [];
  }

  get canUndo(): boolean {
    return this.past.length > 0;
  }

  get canRedo(): boolean {
    return this.future.length > 0;
  }

  undo(current: RoomDocument): RoomDocument | null {
    const previous = this.past.pop();
    if (previous === undefined) return null;
    this.future.push(JSON.stringify(current));
    return JSON.parse(previous);
  }

  redo(current: RoomDocument): RoomDocument | null {
    const next = this.future.pop();
    if (next === undefined) return null;
    this.past.push(JSON.stringify(current));
    return JSON.parse(next);
  }
}

const FURNI_FPS = 24;
const GAME_TIMERS = new Set(["bb_counter", "fball_counter", "es_counter"]);

export interface FurniPart {
  x: number;
  y: number;
  w: number;
  h: number;
  dx: number;
  dy: number;
  flip: boolean;
  layer: number;
  z: number;
  alpha: number;
  ink: string;
}

export interface FurniTrack {
  layer: number;
  repeat: number;
  loop: boolean;
  frames: (FurniPart | null)[];
}

export interface FurniArtData {
  directions: number[];
  poses: Record<string, FurniPart[]>;
  tracks?: Record<string, FurniTrack[]>;
  transitions?: Record<string, FurniTrack[]>;
  digits?: Record<string, Record<string, FurniPart>[]>;
}

/** Whether this furni shows a time rather than a picture for each state. */
export function showsTime(classname: string): boolean {
  const base = classname.split("*")[0] ?? "";
  return (
    base.startsWith("wf_upcounter") || base.startsWith("wf_game_upcounter") || GAME_TIMERS.has(base)
  );
}

/** The digits a time takes up, most significant first: minutes and seconds on four digit displays. */
export function timeDigits(seconds: number, count: number): number[] {
  const whole = Math.max(0, Math.floor(seconds));
  const shown =
    count === 4
      ? `${Math.min(Math.floor(whole / 60), 99)}`.padStart(2, "0") +
        `${whole % 60}`.padStart(2, "0")
      : `${whole}`.padStart(count, "0").slice(-count);
  return [...shown].map(Number);
}

function trackFrame(track: FurniTrack, elapsedMs: number): FurniPart | null {
  // Infinity would make a looping layer's frame not a number, and the layer would vanish.
  const time = Number.isFinite(elapsedMs) ? elapsedMs : 0;
  const step = Math.floor(((time / 1000) * FURNI_FPS) / track.repeat);
  const index = track.loop ? step % track.frames.length : Math.min(step, track.frames.length - 1);
  return track.frames[index] ?? null;
}

/** What to draw for a furni at a moment. `elapsedMs` counts from when it entered this state, and a furni that was already in it has been there forever. */
export function furniParts(
  art: FurniArtData,
  classname: string,
  direction: number,
  state: number,
  elapsedMs: number,
): { parts: FurniPart[]; moving: boolean } {
  const pose = art.poses[`${direction}:${state}`] ?? art.poses[`${direction}:0`] ?? [];
  const digits = showsTime(classname) ? art.digits?.[String(direction)] : undefined;
  if (digits?.length) {
    const layers = new Set(digits.map((slot) => slot["0"]?.layer));
    const values = timeDigits(state, digits.length);
    const shown = digits.flatMap((slot, index) => slot[String(values[index])] ?? []);
    const parts = [...pose.filter((part) => !layers.has(part.layer)), ...shown];
    return { parts: parts.sort((a, b) => a.z - b.z), moving: false };
  }
  const entering = art.transitions?.[`${direction}:${state}`] ?? [];
  const playing = entering.some((track) => elapsedMs < endOf(track));
  const tracks = playing ? entering : art.tracks?.[`${direction}:${state}`];
  if (!tracks?.length) return { parts: pose, moving: false };
  const replaced = new Set(tracks.map((track) => track.layer));
  const current = tracks.flatMap((track) => trackFrame(track, elapsedMs) ?? []);
  const parts = [...pose.filter((part) => !replaced.has(part.layer)), ...current];
  const moving = tracks.some((track) => track.loop || elapsedMs < endOf(track));
  return { parts: parts.sort((a, b) => a.z - b.z), moving };
}

function endOf(track: FurniTrack): number {
  return ((track.frames.length * track.repeat) / FURNI_FPS) * 1000;
}

export interface Highlight {
  type: string;
  strength: number;
  color: number;
  pulse: boolean;
}

export interface Look {
  highlight?: Highlight;
  invisible?: boolean;
  click_through?: boolean;
}

function mixWithWhite(color: number, amount: number): number {
  const part = (shift: number) => {
    const value = (color >> shift) & 255;
    return Math.round(255 + (value - 255) * amount) << shift;
  };
  return part(16) | part(8) | part(0);
}

/** How strongly a look shows at a moment, from 0 to 1. A pulse rises and falls. */
export function lookAmount(look: Highlight, nowMs: number): number {
  const pulse = look.pulse ? 0.5 + 0.5 * Math.sin(nowMs / 200) : 1;
  return (look.strength / 100) * pulse;
}

/** The tint for the looks a tint can draw. Outline, glow and brighten are drawn as extra sprites. */
export function highlightTint(look: Highlight | undefined, nowMs: number): number | null {
  if (!look || look.strength <= 0) return null;
  if (look.type === "darken") return mixWithWhite(0x000000, lookAmount(look, nowMs));
  return look.type === "tint" ? mixWithWhite(look.color, lookAmount(look, nowMs)) : null;
}

export interface FxShown {
  kind: string;
  target: "user" | "furni";
  id: number;
  value: string;
  min: number;
  max: number;
  order: number;
}

/** How full a bar is, from 0 to 1. A range with no width reads as empty, not as an error. */
export function fxFill(fx: Pick<FxShown, "value" | "min" | "max">): number {
  const span = fx.max - fx.min;
  if (span <= 0) return 0;
  return Math.max(0, Math.min((Number(fx.value) - fx.min) / span, 1));
}

/** Whether a wf_ name is a WIRED box. Tiles, tokens and wires share the prefix but hold no WIRED logic. */
export function isWiredBox(classname: string): boolean {
  return /(?:^|_)(trg|act|cnd|slc|xtra|var)(?:_|$)/.test(classname.slice(3));
}

export interface Flight {
  id: number;
  start_ms: number;
  ms: number;
  from: [number, number];
  to: [number, number];
  height: number;
  past: number;
}

/** A height of 100 rose about 19 pixels in a real room, and a height of 50 about half of that. */
const CURVE_PIXELS_PER_HEIGHT = 0.19;

/** Where a flying furni is drawn, `progress` from 0 to 1. Past the target is only animation. */
export function flightAt(
  flight: Pick<Flight, "from" | "to" | "height" | "past">,
  progress: number,
): { x: number; y: number; lift: number } {
  const [fromX, fromY] = flight.from;
  const [dx, dy] = [flight.to[0] - fromX, flight.to[1] - fromY];
  const tiles = Math.max(Math.abs(dx), Math.abs(dy), 1);
  const reach = 1 + flight.past / tiles;
  const t = Math.max(0, Math.min(progress, 1));
  return {
    x: fromX + dx * reach * t,
    y: fromY + dy * reach * t,
    lift: Math.sin(Math.PI * t) * flight.height * CURVE_PIXELS_PER_HEIGHT,
  };
}

/** A real room showed this before anyone set a time zone. */
export const DEFAULT_TIMEZONE = "Europe/London";
export const MAX_ROOM_SIZE = 64;

export type AvatarAction = "wave" | "blow" | "respect" | "sixty_seven";

export const ACTION_MS = 2500;
const ACTION_FRAME_MS = 250;
/** Habbo's avatar animation ticks, at the walk's 8 a second. Its file lists how many ticks each frame holds. */
const TICK_MS = 125;
/**
 * Actions Habbo plays once, frame by frame, rather than in a loop. Blow kiss holds each frame for 10
 * ticks: the hand at the mouth, then out with the eyes shut and the lips pursed. Respect holds each
 * thumbs-up frame for 15 ticks, so it lasts longer than the other actions.
 */
const PLAYED_ONCE: Partial<Record<AvatarAction, number>> = {
  blow: 10 * TICK_MS,
  respect: 15 * TICK_MS,
};

/** How long an action lasts before the avatar goes back to what it was doing. */
export function actionMs(action: AvatarAction): number {
  const frameMs = PLAYED_ONCE[action];
  return frameMs ? Math.max(ACTION_MS, 2 * frameMs) : ACTION_MS;
}
export const SIXTY_SEVEN_MS = 400;
export const SIGN_MAX = 17;
/** A real room holds a sign for a few seconds. The exact length is assumed, and matches the engine. */
export const SIGN_MS = 5000;

/** Habbo's avatar effect action prevents blowing a kiss, so the client greys the option out. */
export function actionBlocked(saved: unknown, action: AvatarAction): boolean {
  return action === "blow" && (((saved ?? {}) as Record<string, number>)["@effect"] ?? 0) > 0;
}

/** What Habbo's avatar image is asked to add to a pose. Effect and dance have no art there. */
export function avatarExtras(
  saved: unknown,
  action?: AvatarAction,
  elapsedMs = 0,
): { extra: string[]; gesture: string; frame: number } {
  const details = (saved ?? {}) as Record<string, number>;
  const step = Math.floor(elapsedMs / ACTION_FRAME_MS);
  const extra: string[] = [];
  let frame = 0;
  const sign = details["@sign"];
  const blocked = action !== undefined && actionBlocked(details, action);
  if (action === "sixty_seven") {
    extra.push(`sig=${Math.floor(elapsedMs / SIXTY_SEVEN_MS) % 2 ? 7 : 6}`);
  } else if (action && !blocked) {
    extra.push({ wave: "wav", blow: "blw", respect: "respect" }[action]);
    const frameMs = PLAYED_ONCE[action];
    frame = frameMs ? Math.min(1, Math.floor(elapsedMs / frameMs)) : step % 2;
  } else if (sign !== undefined && sign >= 0 && sign <= SIGN_MAX) {
    extra.push(`sig=${sign}`);
  }
  const hand = details["@handitem"] ?? 0;
  if (hand > 0 && hand < 10000) extra.push(`crr=${hand}`);
  return { extra, gesture: details["@is_idle"] ? "eyb" : "std", frame };
}

/**
 * Faces the avatar keeps until changed. Each frame is an avatar image gesture, and more than one
 * makes it move. Habbo's "lgh" laugh image is not used, because it draws the arms missing or loose.
 */
const FACES: Record<string, { frames: string[]; ms: number }> = {
  happy: { frames: ["sml"], ms: 0 },
  laughing: { frames: ["spk", "sml"], ms: 350 },
  excited: { frames: ["sml", "srp"], ms: 500 },
  sad: { frames: ["sad"], ms: 0 },
  upset: { frames: ["sad", "eyb"], ms: 700 },
  angry: { frames: ["agr"], ms: 0 },
  surprised: { frames: ["srp"], ms: 0 },
  speaking: { frames: ["spk", "std"], ms: 180 },
  sleepy: { frames: ["eyb", "std"], ms: 1200 },
  sleeping: { frames: ["eyb"], ms: 0 },
  dead: { frames: ["eyb"], ms: 0 }, // Habbo has no such face, so this is a stand-in.
};
export const FACE_NAMES = Object.keys(FACES);
export function faceIsAnimated(face: unknown): boolean {
  return (FACES[String(face)]?.frames.length ?? 0) > 1;
}

/** Every gesture a face uses, so that they can all be loaded before the first one is shown. */
export function faceGestures(face: unknown): string[] {
  return FACES[String(face)]?.frames ?? [];
}

/** Puts the chosen face on a look. With no face, the look keeps its default expression. */
export function withFace<T extends { extra: string[]; gesture: string }>(
  look: T,
  avatar: Pick<PlacedAvatar, "face" | "pose">,
  now: number,
): T {
  const face = FACES[String(avatar.face)];
  if (!face) return look;
  const frame = face.frames[face.ms ? Math.floor(now / face.ms) % face.frames.length : 0] ?? "std";
  return { ...look, gesture: frame };
}

/** The first look that can be shown in full. They come in order of preference. */
export function pickWalkLook<T>(looks: T[], complete: (look: T) => boolean): T | null {
  return looks.find(complete) ?? null;
}

/** The action value of an avatar image: the pose first, and plain standing left out when more is added. */
export function figureAction(pose: string, extra: string[]): string {
  return [...(pose === "std" && extra.length ? [] : [pose]), ...extra].join(",");
}

/** An effect's layers, from Habbo's own effect file. Effects that change the body are not drawn. */
export interface EffectManifest {
  drawable: boolean;
  /** Frames of an effect that changes the body, which only Wiredbench's own avatar drawing shows. */
  frame_count?: number;
  /** A body-changing effect's floor shadow: Habbo's plain one, its own drawn in its image, or none. */
  shadow?: "plain" | "own" | "none";
  /** How many pixels a body-changing effect lifts the avatar at most. */
  lift?: number;
  sprites?: {
    id: string;
    member: string;
    add: boolean;
    turns: boolean;
    dirs: Record<string, { dx: number; dy: number; dz: number }>;
  }[];
  frames?: { s: string; f: number; dx?: number; dy?: number; dd?: number }[][];
  images?: Record<string, { x: number; y: number; w: number; h: number; ox: number; oy: number }>;
}

/** Habbo plays effects at about 12 frames a second. */
export const EFFECT_FRAME_MS = 83;
/** Where an avatar image puts Habbo's offset origin, measured from its top. */
const EFFECT_ORIGIN_Y = 100;

/** Each layer of an effect at a moment, placed from the top left of the avatar's image. */
export function effectLayers(manifest: EffectManifest, dir: number, nowMs: number) {
  const sprites = manifest.sprites ?? [];
  const frames = manifest.frames ?? [];
  const shown: { s: string; f: number; dx?: number; dy?: number; dd?: number }[] = frames.length
    ? (frames[Math.floor(nowMs / EFFECT_FRAME_MS) % frames.length] ?? [])
    : sprites.map((sprite) => ({ s: sprite.id, f: 0 }));
  const layers = [];
  for (const part of shown) {
    const sprite = sprites.find((candidate) => candidate.id === part.s);
    if (!sprite) continue;
    const facing = sprite.turns ? (((dir + (part.dd ?? 0)) % 8) + 8) % 8 : 0;
    const image = manifest.images?.[`${sprite.member}_${facing}_${part.f}`];
    if (!image) continue;
    const shift = sprite.dirs[String(facing)] ?? { dx: 0, dy: 0, dz: 0 };
    layers.push({
      image,
      x: -image.ox + shift.dx + (part.dx ?? 0),
      y: EFFECT_ORIGIN_Y - image.oy + shift.dy + (part.dy ?? 0),
      front: shift.dz >= 0,
      dz: shift.dz,
      add: sprite.add,
    });
  }
  return layers;
}

/** A furni's interaction kind, sorted as the room engine does from its name and catalogue category. */
export type FurniKind =
  | "dice"
  | "switch"
  | "teleport"
  | "gate"
  | "one_way_gate"
  | "vending"
  | "default";

export function furniKind(
  classname: string,
  category: string | null,
  handItems: readonly number[] = [],
): FurniKind {
  const name = classname.toLowerCase();
  if (name.includes("dice")) return "dice";
  if (name.startsWith("wf_floor_switch")) return "switch";
  if (name.startsWith("one_way_door")) return "one_way_gate";
  if (category === "teleport") return "teleport";
  if (category === "gate") return "gate";
  if (category === "vending_machine" || handItems.length > 0) return "vending";
  return "default";
}

/** Furni a user must stand next to to use, such as dice and floor switches. */
export function usedFromNextTo(kind: FurniKind): boolean {
  return kind === "dice" || kind === "switch";
}

/** On one of the eight tiles around a tile. */
export function isNextTo(user: [number, number], item: [number, number]): boolean {
  return Math.max(Math.abs(user[0] - item[0]), Math.abs(user[1] - item[1])) === 1;
}

/** The tiles around a 1 by 1 furni that are inside the room. */
export function besideTiles(
  item: Pick<PlacedFurni, "x" | "y">,
  room: Pick<RoomDocument, "room">,
): [number, number][] {
  const found: [number, number][] = [];
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      const [x, y] = [item.x + dx, item.y + dy];
      if ((dx || dy) && x >= 0 && y >= 0 && x < room.room.width && y < room.room.height)
        found.push([x, y]);
    }
  }
  return found;
}

/** Puts anyone lying on a bed onto its head row, as a room saved before this rule may hold them anywhere. */
export function settleOnBeds(room: RoomDocument, lookup: InfoLookup): void {
  for (const avatar of room.avatars) {
    if (avatar.pose !== "lay") continue;
    const [x, y] = restTile(room, lookup, avatar.x, avatar.y);
    if (room.avatars.some((other) => other !== avatar && other.x === x && other.y === y)) continue;
    avatar.x = x;
    avatar.y = y;
  }
}

/** The tile in front of a furni turned this way: where a teleport or one-way gate is entered from. */
export function frontTile(item: Pick<PlacedFurni, "x" | "y" | "rot">): [number, number] {
  const [dx, dy] = ({ 0: [0, -1], 2: [1, 0], 4: [0, 1], 6: [-1, 0] } as Record<number, number[]>)[
    item.rot % 8
  ] ?? [0, 1];
  return [item.x + (dx ?? 0), item.y + (dy ?? 1)];
}

/** Furni entered from the tile in front of them. */
/** Furni used from the tile in front of them: teleports, one-way gates and vending machines. */
export function usedFromFront(kind: FurniKind): boolean {
  return enteredFromFront(kind) || kind === "vending";
}

export function enteredFromFront(kind: FurniKind): boolean {
  return kind === "teleport" || kind === "one_way_gate";
}
