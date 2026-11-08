import { describe, expect, it } from "vitest";
import { state } from "../state";
import { depth, screenToTile, tileCentre } from "./iso";
import {
  actionBlocked,
  actionMs,
  avatarExtras,
  besideTiles,
  canStackOn,
  directionBetween,
  drawTile,
  EFFECT_FRAME_MS,
  type EffectManifest,
  effectLayers,
  emptyRoom,
  enteredFromFront,
  type FurniArtData,
  type FurniInfo,
  type FurniPart,
  faceGestures,
  faceIsAnimated,
  figureAction,
  findPath,
  fitsInRoom,
  flightAt,
  footprint,
  frontTile,
  furniAt,
  furniKind,
  furniParts,
  fxFill,
  glideSteps,
  History,
  highlightTint,
  type InfoLookup,
  isNextTo,
  isWiredBox,
  nextDirection,
  nextId,
  normaliseRoom,
  type PlacedFurni,
  pickWalkLook,
  type RoomDocument,
  restingDir,
  restTile,
  seatedFacing,
  settleOnBeds,
  showsTime,
  stackHeight,
  standAt,
  standUpOffSeats,
  timeDigits,
  UNKNOWN_FURNI,
  usedFromFront,
  usedFromNextTo,
  withFace,
} from "./model";
import { avatarImageAt, avatarUrl, bodyEffectUrl, shadowUrl } from "./renderer";
import { isDebugCommand, runClock } from "./run-panel";

const INFO: Record<string, FurniInfo> = {
  wall: {
    xdim: 1,
    ydim: 1,
    height: 1,
    canStand: false,
    canSit: false,
    canLay: false,
    canStack: true,
  },
  mat: {
    xdim: 1,
    ydim: 1,
    height: 0.1,
    canStand: true,
    canSit: false,
    canLay: false,
    canStack: true,
  },
  chair: {
    xdim: 1,
    ydim: 1,
    height: 1,
    canStand: false,
    canSit: true,
    canLay: false,
    canStack: false,
  },
  bed: {
    xdim: 2,
    ydim: 3,
    height: 1,
    canStand: false,
    canSit: false,
    canLay: true,
    canStack: false,
  },
  tower: {
    xdim: 1,
    ydim: 1,
    height: 3,
    canStand: true,
    canSit: false,
    canLay: false,
    canStack: true,
  },
};
const lookup = (name: string) => INFO[name] as FurniInfo;

function room(...furni: [string, number, number, number?, number?][]): RoomDocument {
  const base = emptyRoom();
  base.room = { width: 6, height: 6 };
  base.furni = furni.map(
    ([classname, x, y, z = 0, rot = 0], index): PlacedFurni => ({
      id: index + 1,
      classname,
      x,
      y,
      z,
      rot,
      state: 0,
    }),
  );
  return base;
}

describe("geometry", () => {
  it("finds the tile under any point of it", () => {
    for (const [x, y] of [
      [0, 0],
      [3, 1],
      [1, 5],
      [7, 7],
    ] as const) {
      const centre = tileCentre(x, y);
      expect(screenToTile(centre.x, centre.y)).toEqual([x, y]);
      expect(screenToTile(centre.x + 20, centre.y + 4)).toEqual([x, y]);
      expect(screenToTile(centre.x - 20, centre.y - 4)).toEqual([x, y]);
    }
  });

  it("moves up the screen with height", () => {
    expect(tileCentre(2, 2, 1).y).toBe(tileCentre(2, 2).y - 32);
  });

  it("draws nearer tiles later, then higher, then by layer", () => {
    expect(depth(1, 1, 0)).toBeLessThan(depth(2, 1, 0));
    expect(depth(1, 1, 0)).toBeLessThan(depth(1, 1, 1));
    expect(depth(1, 1, 0, 1)).toBeLessThan(depth(1, 1, 0, 800));
    expect(depth(1, 1, 5, 800)).toBeLessThan(depth(2, 1, 0));
  });
});

describe("placement", () => {
  it("swaps width and depth on a quarter turn", () => {
    expect(footprint({ x: 1, y: 1 }, INFO.bed as FurniInfo, 0)).toHaveLength(6);
    expect(footprint({ x: 0, y: 0 }, INFO.bed as FurniInfo, 0)).toContainEqual([1, 2]);
    expect(footprint({ x: 0, y: 0 }, INFO.bed as FurniInfo, 2)).toContainEqual([2, 1]);
    expect(footprint({ x: 0, y: 0 }, INFO.bed as FurniInfo, 2)).not.toContainEqual([1, 2]);
  });

  it("checks room edges", () => {
    const r = room();
    expect(fitsInRoom(r, [[5, 5]])).toBe(true);
    expect(fitsInRoom(r, [[6, 0]])).toBe(false);
    expect(fitsInRoom(r, [[0, -1]])).toBe(false);
  });

  it("stacks on the tallest thing under any tile", () => {
    const r = room(["mat", 1, 1], ["tower", 2, 1]);
    expect(stackHeight(r, lookup, [[0, 0]])).toBe(0);
    expect(stackHeight(r, lookup, [[1, 1]])).toBe(0.1);
    expect(
      stackHeight(r, lookup, [
        [1, 1],
        [2, 1],
      ]),
    ).toBe(3);
    expect(stackHeight(r, lookup, [[2, 1]], 2)).toBe(0);
  });

  it("puts nothing on a chair, but on a mat, the floor or the chair's own tile when moving it", () => {
    const r = room(["mat", 1, 1], ["chair", 2, 1]);
    expect(canStackOn(r, lookup, [[0, 0]])).toBe(true);
    expect(canStackOn(r, lookup, [[1, 1]])).toBe(true);
    expect(
      canStackOn(r, lookup, [
        [1, 1],
        [2, 1],
      ]),
    ).toBe(false);
    expect(canStackOn(r, lookup, [[2, 1]], 2)).toBe(true);
  });

  it("lists furni on a tile from the bottom up, including large furni", () => {
    const r = room(["mat", 1, 1, 1], ["bed", 0, 0]);
    expect(furniAt(r, lookup, 1, 1).map((f) => f.classname)).toEqual(["bed", "mat"]);
  });

  it("gives new things an unused ID", () => {
    const r = room(["mat", 0, 0], ["mat", 1, 0]);
    expect(nextId(r)).toBe(3);
    expect(nextId(emptyRoom())).toBe(1);
  });

  it("cycles through the directions a furni has", () => {
    expect(nextDirection([2, 4], 2)).toBe(4);
    expect(nextDirection([2, 4], 4)).toBe(2);
    expect(nextDirection([0, 2, 4, 6], 7)).toBe(0);
    expect(nextDirection([], 3)).toBe(3);
  });

  it("opens older documents and keeps unknown fields", () => {
    const opened = normaliseRoom({ later: { wired: true } });
    expect(opened.room).toEqual({ width: 12, height: 12 });
    expect(opened.furni).toEqual([]);
    expect(opened.later).toEqual({ wired: true });
  });
});

describe("standing", () => {
  it("stands someone up when their chair or bed is moved away", () => {
    const r = room(["chair", 2, 0, 0, 4], ["bed", 0, 3]);
    const seated = { id: 1, name: "A", hotel: "com", figure: "hd-180-1", dir: 4 };
    r.avatars = [
      { ...seated, x: 2, y: 0, z: 1, pose: "sit" },
      { ...seated, id: 2, x: 1, y: 4, z: 0.9, pose: "lay" },
    ];
    expect(standUpOffSeats(r, lookup)).toBe(false);
    // Saved facing 4 from an earlier walk, but the chair turns them to face 2.
    r.furni = r.furni.map((item) => (item.classname === "chair" ? { ...item, rot: 2 } : item));
    const facing = seatedFacing(r, lookup);
    r.furni = r.furni.map((item) => (item.classname === "chair" ? { ...item, x: 4 } : item));
    expect(standUpOffSeats(r, lookup, facing)).toBe(true);
    expect(r.avatars[0]).toMatchObject({ pose: "std", z: 0, dir: 2 });
    expect(r.avatars[1]).toMatchObject({ pose: "lay" });
    r.furni = [];
    standUpOffSeats(r, lookup);
    expect(r.avatars[1]).toMatchObject({ pose: "std", z: 0 });
  });

  it("keeps people on the mattress of a bed taller than it looks", () => {
    const tall: InfoLookup = (name) => ({ ...lookup(name), height: 1.73 });
    expect(standAt(room(["bed", 0, 0]), tall, 0, 0).z).toBe(0.9);
  });

  it("depends on the top furni", () => {
    const r = room(["wall", 0, 0], ["mat", 1, 0], ["chair", 2, 0, 0, 4], ["bed", 0, 3]);
    expect(standAt(r, lookup, 3, 3)).toMatchObject({ walkable: true, z: 0, pose: "std" });
    expect(standAt(r, lookup, 0, 0).walkable).toBe(false);
    expect(standAt(r, lookup, 1, 0)).toMatchObject({ walkable: true, z: 0.1, pose: "std" });
    expect(standAt(r, lookup, 2, 0)).toMatchObject({ pose: "sit", dir: 4, z: 1 });
    expect(standAt(r, lookup, 1, 4)).toMatchObject({ pose: "lay" });
  });

  it("faces the way a seat is turned, wherever the avatar was saved facing", () => {
    const r = room(["chair", 2, 0, 0, 4], ["mat", 1, 0]);
    expect(restingDir(r, lookup, { x: 2, y: 0, dir: 2 })).toBe(4);
    expect(restingDir(r, lookup, { x: 1, y: 0, dir: 2 })).toBe(2);
  });
});

describe("draw order", () => {
  it("puts an avatar in front of the large furni it is on", () => {
    const r = room(["bed", 1, 1]);
    expect(drawTile(r, lookup, 1, 1)).toEqual([2, 3]);
    expect(drawTile(r, lookup, 2, 3)).toEqual([2, 3]);
    expect(drawTile(r, lookup, 5, 5)).toEqual([5, 5]);
  });

  it("follows the furni's rotation", () => {
    const r = room(["bed", 1, 1, 0, 2]);
    expect(drawTile(r, lookup, 1, 1)).toEqual([3, 2]);
  });
});

describe("walking", () => {
  it("names all eight directions", () => {
    const steps: [number, number][] = [
      [0, -1],
      [1, -1],
      [1, 0],
      [1, 1],
      [0, 1],
      [-1, 1],
      [-1, 0],
      [-1, -1],
    ];
    expect(steps.map((s) => directionBetween([0, 0], s))).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
  });

  it("goes diagonally when the way is clear", () => {
    expect(findPath(room(), lookup, [0, 0], [3, 3])).toEqual([
      [1, 1],
      [2, 2],
      [3, 3],
    ]);
  });

  it("goes around blocks without cutting corners", () => {
    const r = room(["wall", 1, 0], ["wall", 1, 1]);
    const path = findPath(r, lookup, [0, 0], [2, 0]) ?? [];
    expect(path.at(-1)).toEqual([2, 0]);
    expect(path).not.toContainEqual([1, 1]);
    expect(path).toEqual([
      [0, 1],
      [0, 2],
      [1, 2],
      [2, 2],
      [2, 1],
      [2, 0],
    ]);
  });

  it("refuses diagonal steps past a single blocked tile", () => {
    const r = room(["wall", 1, 0]);
    const path = findPath(r, lookup, [0, 0], [1, 1]) ?? [];
    expect(path).toEqual([
      [0, 1],
      [1, 1],
    ]);
  });

  it("returns null when there is no way", () => {
    const r = room(["wall", 1, 0], ["wall", 1, 1], ["wall", 0, 1]);
    expect(findPath(r, lookup, [0, 0], [3, 3])).toBeNull();
    expect(findPath(r, lookup, [3, 3], [1, 1])).toBeNull();
    expect(findPath(room(), lookup, [0, 0], [9, 9])).toBeNull();
  });

  it("sits on a chair at the end but never walks across one", () => {
    const row = (y: number) => ["chair", 2, y] as [string, number, number];
    const r = room(row(0), row(1), row(2), row(3), row(4));
    const path = findPath(r, lookup, [0, 0], [4, 0]) ?? [];
    expect(path.some(([x, y]) => x === 2 && y < 5)).toBe(false);
    expect(findPath(room(["chair", 2, 0]), lookup, [0, 0], [2, 0])?.at(-1)).toEqual([2, 0]);
  });

  it("will not step up something too tall", () => {
    const r = room(["tower", 1, 0]);
    expect(findPath(r, lookup, [0, 0], [1, 0])).toBeNull();
  });

  it("avoids other avatars and cannot end on one", () => {
    const occupied = new Set(["1,0"]);
    const path = findPath(room(), lookup, [0, 0], [2, 0], occupied) ?? [];
    expect(path).not.toContainEqual([1, 0]);
    expect(findPath(room(), lookup, [0, 0], [1, 0], occupied)).toBeNull();
  });

  it("gives an empty path when already there", () => {
    expect(findPath(room(), lookup, [1, 1], [1, 1])).toEqual([]);
  });
});

describe("undo", () => {
  it("steps back and forward, and new changes clear redo", () => {
    const history = new History();
    const a = room();
    const b = room(["mat", 0, 0]);
    expect(history.canUndo).toBe(false);
    history.record(a);
    const undone = history.undo(b);
    expect(undone).toEqual(a);
    expect(history.canRedo).toBe(true);
    expect(history.redo(a)).toEqual(b);
    history.undo(b);
    history.record(a);
    expect(history.canRedo).toBe(false);
  });
});

describe("run console", () => {
  it("keeps room keywords as chat", () => {
    expect(isDebugCommand(":time")).toBe(false);
    expect(isDebugCommand(":varsity")).toBe(false);
    expect(isDebugCommand("hello")).toBe(false);
    expect(isDebugCommand(":vars global")).toBe(true);
    expect(isDebugCommand(":pause")).toBe(true);
  });

  it("formats the clock", () => {
    expect(runClock(65500)).toBe("1:05.5");
    expect(runClock(0)).toBe("0:00.0");
  });
});

describe("furni animation", () => {
  const part = (layer: number, dx = 0): FurniPart => ({
    x: dx,
    y: 0,
    w: 1,
    h: 1,
    dx,
    dy: 0,
    flip: false,
    layer,
    z: layer,
    alpha: 255,
    ink: "",
  });
  const art: FurniArtData = {
    directions: [2],
    poses: { "2:0": [part(0)], "2:1": [part(0), part(1, 1)] },
    tracks: { "2:1": [{ layer: 1, repeat: 24, loop: true, frames: [part(1, 1), part(1, 2)] }] },
  };

  it("plays a state's frames and loops them", () => {
    const at = (ms: number) =>
      furniParts(art, "lamp", 2, 1, ms).parts.find((p) => p.layer === 1)?.dx;
    expect(at(0)).toBe(1);
    expect(at(1000)).toBe(2);
    expect(at(2000)).toBe(1);
    expect(furniParts(art, "lamp", 2, 1, 0).moving).toBe(true);
    expect(furniParts(art, "lamp", 2, 0, 0).moving).toBe(false);
  });

  it("never loses a looping layer, however long the furni has been there", () => {
    for (const elapsed of [3_600_000, Number.POSITIVE_INFINITY]) {
      const layer = furniParts(art, "lamp", 2, 1, elapsed).parts.find((p) => p.layer === 1);
      expect(layer).toBeDefined();
    }
  });

  it("holds the last frame of an animation that does not loop", () => {
    const once = {
      ...art,
      tracks: { "2:1": [{ layer: 1, repeat: 24, loop: false, frames: [part(1, 1), part(1, 2)] }] },
    };
    const result = furniParts(once, "lamp", 2, 1, 9000);
    expect(result.parts.find((p) => p.layer === 1)?.dx).toBe(2);
    expect(result.moving).toBe(false);
  });

  it("plays a transition on the way into a state, then shows the state", () => {
    const bomb: FurniArtData = {
      directions: [2],
      poses: { "2:1": [part(0)] },
      transitions: {
        "2:1": [{ layer: 0, repeat: 24, loop: false, frames: [part(0, 5), part(0, 6)] }],
      },
    };
    expect(furniParts(bomb, "bomb", 2, 1, 0).parts[0]?.dx).toBe(5);
    expect(furniParts(bomb, "bomb", 2, 1, 0).moving).toBe(true);
    expect(furniParts(bomb, "bomb", 2, 1, 1000).parts[0]?.dx).toBe(6);
    const done = furniParts(bomb, "bomb", 2, 1, Number.POSITIVE_INFINITY);
    expect(done.parts[0]?.dx).toBe(0);
    expect(done.moving).toBe(false);
  });

  it("shows a counter's time from its digit layers", () => {
    expect(timeDigits(90, 4)).toEqual([0, 1, 3, 0]);
    expect(timeDigits(6005, 4)).toEqual([9, 9, 0, 5]);
    expect(timeDigits(7, 2)).toEqual([0, 7]);
    const slot = (layer: number) =>
      Object.fromEntries([...Array(10).keys()].map((d) => [String(d), { ...part(layer), x: d }]));
    const clock: FurniArtData = {
      directions: [2],
      poses: { "2:0": [part(0), part(1)] },
      digits: { "2": [slot(1), slot(2)] },
    };
    const { parts } = furniParts(clock, "wf_upcounter1", 2, 37, 0);
    expect(parts.filter((p) => p.layer > 0).map((p) => p.x)).toEqual([3, 7]);
    expect(furniParts(clock, "lamp", 2, 37, 0).parts.map((p) => p.layer)).toEqual([0, 1]);
  });

  it("does not treat a state that has no picture as anything but its first", () => {
    expect(showsTime("wf_game_upcounter2")).toBe(true);
    expect(showsTime("bb_counter")).toBe(true);
    expect(showsTime("rela_candle1")).toBe(false);
  });
});

describe("wired looks", () => {
  const look = { type: "tint", strength: 100, color: 0x123456, pulse: false };

  it("tints with the chosen colour and strength", () => {
    expect(highlightTint(look, 0)).toBe(0x123456);
    expect(highlightTint({ ...look, strength: 0 }, 0)).toBeNull();
    expect(highlightTint(undefined, 0)).toBeNull();
    expect(highlightTint({ ...look, type: "outline" }, 0)).toBeNull();
    expect(highlightTint({ ...look, type: "brighten" }, 0)).toBeNull();
    expect(highlightTint({ ...look, type: "darken", strength: 50 }, 0)).toBe(0x808080);
  });

  it("pulses over time", () => {
    const pulsing = { ...look, pulse: true };
    expect(highlightTint(pulsing, 0)).not.toBe(highlightTint(pulsing, 300));
  });
});

describe("variable displays", () => {
  it("fills a bar within its range and never past it", () => {
    expect(fxFill({ value: "50", min: 0, max: 100 })).toBe(0.5);
    expect(fxFill({ value: "150", min: 0, max: 100 })).toBe(1);
    expect(fxFill({ value: "-5", min: 0, max: 100 })).toBe(0);
    expect(fxFill({ value: "5", min: 10, max: 10 })).toBe(0);
  });
});

describe("box names", () => {
  it("tells WIRED boxes from furni that share the prefix", () => {
    expect(isWiredBox("wf_act_give_var")).toBe(true);
    expect(isWiredBox("wf_xtra_varfx_hp")).toBe(true);
    expect(isWiredBox("wf_tile1")).toBe(false);
    expect(isWiredBox("wf_upcounter1")).toBe(false);
  });
});

describe("projectile flights", () => {
  const flight = {
    from: [5, 2] as [number, number],
    to: [8, 2] as [number, number],
    height: 100,
    past: 0,
  };

  it("flies from start to target and curves highest in the middle", () => {
    expect(flightAt(flight, 0)).toEqual({ x: 5, y: 2, lift: 0 });
    expect(flightAt(flight, 0.5).x).toBe(6.5);
    expect(flightAt(flight, 0.5).lift).toBeCloseTo(19);
    expect(flightAt(flight, 1).x).toBe(8);
    expect(flightAt(flight, 1).lift).toBeCloseTo(0);
  });

  it("is a straight line at height 0, and animates past its target when asked", () => {
    expect(flightAt({ ...flight, height: 0 }, 0.5).lift).toBe(0);
    expect(flightAt({ ...flight, past: 3 }, 1).x).toBe(11);
  });
});

describe("avatar actions", () => {
  it("adds what the panel holds to the pose", () => {
    expect(avatarExtras({ "@sign": 0 }).extra).toEqual(["sig=0"]);
    expect(avatarExtras({ "@sign": 18 }).extra).toEqual([]);
    expect(avatarExtras({ "@handitem": 12 }).extra).toEqual(["crr=12"]);
    expect(avatarExtras({ "@is_idle": 1 }).gesture).toBe("eyb");
    expect(avatarExtras({ "@effect": 4, "@dance": 1 }).extra).toEqual([]);
  });

  it("swaps frames while an action plays, and an action covers a held sign", () => {
    expect(avatarExtras({ "@sign": 6 }, "wave", 0)).toMatchObject({ extra: ["wav"], frame: 0 });
    // One kiss over the whole action, as Habbo holds each blow kiss frame for 10 ticks.
    expect(avatarExtras({}, "blow", 250).frame).toBe(0);
    expect(avatarExtras({}, "blow", 1249).frame).toBe(0);
    expect(avatarExtras({}, "blow", 1250).frame).toBe(1);
    expect(avatarExtras({}, "blow", 2499).frame).toBe(1);
    expect(avatarExtras({}, "wave", 250).frame).toBe(1);
    expect(avatarExtras({}, "sixty_seven", 0).extra).toEqual(["sig=6"]);
    expect(avatarExtras({}, "sixty_seven", 400).extra).toEqual(["sig=7"]);
  });

  it("builds the image action with the pose first", () => {
    expect(figureAction("std", [])).toBe("std");
    expect(figureAction("std", ["sig=6"])).toBe("sig=6");
    expect(figureAction("sit", ["sig=6", "crr=1"])).toBe("sit,sig=6,crr=1");
  });
});

describe("avatar faces", () => {
  const look = { extra: [] as string[], gesture: "std", frame: 0 };
  const standing = { face: "happy", pose: "std" as const };

  it("keeps the default look with no face or an unknown one", () => {
    expect(withFace(look, { face: null, pose: "std" }, 0)).toEqual(look);
    expect(withFace(look, { face: "nope", pose: "std" }, 0)).toEqual(look);
  });

  it("keeps a still face at any time", () => {
    expect(withFace(look, standing, 0).gesture).toBe("sml");
    expect(withFace(look, standing, 99999).gesture).toBe("sml");
  });

  it("moves a speaking face between its frames", () => {
    const speaking = { face: "speaking", pose: "std" as const };
    expect(withFace(look, speaking, 0).gesture).toBe("spk");
    expect(withFace(look, speaking, 200).gesture).toBe("std");
    expect(faceIsAnimated("speaking")).toBe(true);
    expect(faceIsAnimated("happy")).toBe(false);
  });

  it("laughs with an open mouth and a smile, never Habbo's broken laugh image", () => {
    const laughing = { face: "laughing", pose: "std" as const };
    expect(withFace(look, laughing, 0)).toMatchObject({ extra: [], gesture: "spk" });
    expect(withFace(look, laughing, 350)).toMatchObject({ extra: [], gesture: "sml" });
    expect(withFace({ ...look, extra: ["sig=6"] }, laughing, 0).extra).toEqual(["sig=6"]);
    expect(faceGestures("laughing")).toEqual(["spk", "sml"]);
  });
});

describe("walking looks", () => {
  it("shows the first look with every step loaded, and nothing if none has", () => {
    const ready = new Set(["old", "plain"]);
    expect(pickWalkLook(["new", "old", "plain"], (look) => ready.has(look))).toBe("old");
    expect(pickWalkLook(["new"], (look) => ready.has(look))).toBeNull();
  });
});

describe("glideSteps", () => {
  it("walks a short move and lets a long one appear", () => {
    expect(glideSteps([1, 1], [2, 2])).toBe(1);
    expect(glideSteps([1, 1], [3, 1])).toBe(2);
    expect(glideSteps([1, 1], [4, 1])).toBeNull();
  });
});

describe("avatar effects", () => {
  const manifest: EffectManifest = {
    drawable: true,
    sprites: [
      {
        id: "a",
        member: "std_fx_a",
        add: true,
        turns: true,
        dirs: { "2": { dx: 3, dy: 0, dz: -1 } },
      },
      { id: "b", member: "std_fx_b", add: false, turns: false, dirs: {} },
    ],
    frames: [
      [
        { s: "a", f: 0 },
        { s: "b", f: 0 },
      ],
      [{ s: "a", f: 1, dy: -4 }],
    ],
    images: {
      std_fx_a_2_0: { x: 0, y: 0, w: 4, h: 4, ox: -10, oy: 80 },
      std_fx_a_2_1: { x: 5, y: 0, w: 4, h: 4, ox: -10, oy: 80 },
      std_fx_b_0_0: { x: 0, y: 5, w: 4, h: 4, ox: 2, oy: 50 },
    },
  };

  it("places layers from Habbo's offsets and steps through frames", () => {
    const [glow, plain] = effectLayers(manifest, 2, 0);
    expect(glow).toMatchObject({ x: 13, y: 20, front: false, add: true });
    expect(plain).toMatchObject({ x: -2, y: 50, front: true, add: false });
    expect(effectLayers(manifest, 2, EFFECT_FRAME_MS)).toMatchObject([{ y: 16 }]);
  });

  it("skips a direction the effect has no art for", () => {
    expect(effectLayers(manifest, 4, 0)).toHaveLength(1);
  });
});

describe("body-changing effects", () => {
  const avatar = { hotel: "com", figure: "hd-180-1" };
  const query = (url: string) => new URL(url, "http://localhost").searchParams;

  it("keep the walk's step and direction apart from the effect's own frame", () => {
    const walking = { action: "wlk", extra: [], gesture: "std" };
    const steps = [0, 1, 2, 3].map((frame) =>
      query(bodyEffectUrl(avatar, { ...walking, dir: 2, frame }, 3, 1, 5000)),
    );
    // Before, the effect's frame took the walk's place, so a one-frame effect froze the legs.
    expect(steps.map((found) => found.get("frame"))).toEqual(["0", "1", "2", "3"]);
    expect(steps.every((found) => found.get("effect_frame") === "0")).toBe(true);
    const turned = query(bodyEffectUrl(avatar, { ...walking, dir: 6, frame: 1 }, 3, 1, 5000));
    expect(turned.get("direction")).toBe("6");
  });

  it("play the effect on its own clock", () => {
    const standing = { action: "std", extra: [], gesture: "std", dir: 2, frame: 0 };
    const later = query(bodyEffectUrl(avatar, standing, 27, 10, 83 * 13));
    expect(later.get("effect")).toBe("27");
    expect(later.get("effect_frame")).toBe("3");
    expect(later.get("frame")).toBe("0");
  });
});

describe("avatar actions follow Habbo's frame lengths", () => {
  it("plays respect once, each thumbs-up frame for 15 ticks", () => {
    expect(actionMs("respect")).toBe(3750);
    expect(actionMs("blow")).toBe(2500);
    expect(actionMs("wave")).toBe(2500);
    expect(avatarExtras({}, "respect", 1874).frame).toBe(0);
    expect(avatarExtras({}, "respect", 1875).frame).toBe(1);
    expect(avatarExtras({}, "respect", 3749).frame).toBe(1);
  });

  it("does not blow a kiss with an effect on, as Habbo's effect action prevents it", () => {
    expect(avatarExtras({ "@effect": 247 }, "blow", 0).extra).toEqual([]);
    expect(avatarExtras({ "@effect": 247 }, "wave", 0).extra).toEqual(["wav"]);
  });

  it("asks for an action's own frame only when Wiredbench draws the avatar", () => {
    const avatar = { hotel: "com", figure: "hd-180-1" };
    const asked = () =>
      new URL(avatarUrl(avatar, "wlk,blw", 2, 3, "std", undefined, 0, 1), "http://x");
    const saved = state.settings;
    try {
      state.settings = { avatar_drawing: "habbo" } as typeof state.settings;
      expect(asked().searchParams.has("action_frame")).toBe(false);
      state.settings = { avatar_drawing: "wiredbench" } as typeof state.settings;
      expect(asked().searchParams.get("action_frame")).toBe("1");
      expect(asked().searchParams.get("frame")).toBe("3");
    } finally {
      state.settings = saved;
    }
  });
});

describe("matching a real room", () => {
  it("greys out blow kiss while an effect is on, as Habbo does", () => {
    expect(actionBlocked({ "@effect": 38 }, "blow")).toBe(true);
    expect(actionBlocked({}, "blow")).toBe(false);
    expect(actionBlocked({ "@effect": 38 }, "wave")).toBe(false);
  });

  it("asks for the floor shadow of the pose, with walking using the standing one", () => {
    const query = (action: string) =>
      new URL(shadowUrl({ hotel: "com" }, { action, dir: 4 }), "http://x").searchParams;
    expect(query("wlk").get("pose")).toBe("std");
    expect(query("sit").get("pose")).toBe("sit");
    expect(query("lay").get("pose")).toBe("lay");
    expect(query("std").get("direction")).toBe("4");
  });
});

describe("avatar placement matches Habbo's client", () => {
  const centre = { x: 100, y: 200 };

  it("draws a sitting avatar 32 pixels lower than a standing one, in the same column", () => {
    const standing = avatarImageAt({ action: "std", dir: 2 }, centre);
    const sitting = avatarImageAt({ action: "sit", dir: 2 }, centre);
    expect(sitting.top - standing.top).toBe(32);
    expect(sitting.left).toBe(standing.left);
    expect(sitting.head - standing.head).toBe(32);
  });

  it("places the wide lying image on the bed, mirrored between its two directions", () => {
    const two = avatarImageAt({ action: "lay", dir: 2 }, centre);
    const four = avatarImageAt({ action: "lay", dir: 4 }, centre);
    expect([two.w, two.h]).toEqual([110, 64]);
    expect(two.top).toBe(four.top);
    // The image's centre sits as far right of the tile facing 2 as left of it facing 4.
    expect(two.left + two.w / 2 - centre.x).toBe(centre.x - (four.left + four.w / 2));
    expect(two.top).toBeGreaterThan(avatarImageAt({ action: "std", dir: 2 }, centre).top);
  });
});

describe("furni kinds match the room engine", () => {
  it("sorts furni by name and category", () => {
    expect(furniKind("edice", "fortuna")).toBe("dice");
    expect(furniKind("wf_floor_switch1", "wired_add_on")).toBe("switch");
    expect(furniKind("one_way_door*1", "gate")).toBe("one_way_gate");
    expect(furniKind("lamp_basic", "lighting")).toBe("default");
    // A furni that hands out items is a vending machine, whatever its category.
    expect(furniKind("giftflowers", "other", [1019])).toBe("vending");
    expect(usedFromFront("vending") && usedFromFront("teleport") && !usedFromFront("dice")).toBe(
      true,
    );
    expect(usedFromNextTo("dice") && usedFromNextTo("switch") && !usedFromNextTo("default")).toBe(
      true,
    );
  });

  it("enters teleports and one-way gates from the tile in front", () => {
    expect(enteredFromFront("teleport") && enteredFromFront("one_way_gate")).toBe(true);
    expect(enteredFromFront("dice")).toBe(false);
    expect(frontTile({ x: 3, y: 3, rot: 0 })).toEqual([3, 2]);
    expect(frontTile({ x: 3, y: 3, rot: 2 })).toEqual([4, 3]);
    expect(frontTile({ x: 3, y: 3, rot: 4 })).toEqual([3, 4]);
    expect(frontTile({ x: 3, y: 3, rot: 6 })).toEqual([2, 3]);
  });

  it("lets people walk through a gate only while it is open", () => {
    const gates: InfoLookup = (name) =>
      name === "gate" ? { ...UNKNOWN_FURNI, canStand: false, kind: "gate" } : lookup(name);
    const r = room(["gate", 2, 2]);
    expect(standAt(r, gates, 2, 2).walkable).toBe(false);
    r.furni = r.furni.map((item) => ({ ...item, state: 1 }));
    expect(standAt(r, gates, 2, 2).walkable).toBe(true);
  });

  it("finds the tiles next to a furni, inside the room", () => {
    expect(isNextTo([4, 4], [5, 5])).toBe(true);
    expect(isNextTo([5, 5], [5, 5])).toBe(false);
    expect(isNextTo([3, 5], [5, 5])).toBe(false);
    expect(besideTiles({ x: 0, y: 0 }, { room: { width: 4, height: 4 } })).toEqual([
      [0, 1],
      [1, 0],
      [1, 1],
    ]);
  });
});

describe("lying on a bed", () => {
  const bedInfo = (name: string) =>
    name.startsWith("bed")
      ? { ...lookup("bed"), xdim: name === "bed2" ? 2 : 1, ydim: 3 }
      : lookup(name);

  it("rests on the head row, in the middle of a one-wide bed and on either side of a double bed", () => {
    const r = room(["bed1", 1, 1, 0, 0], ["bed2", 4, 1, 0, 0], ["bed1", 1, 6, 0, 2]);
    // Turned 0, a bed runs along y and its first row is the head.
    expect(restTile(r, bedInfo, 1, 3)).toEqual([1, 1]);
    expect(restTile(r, bedInfo, 5, 3)).toEqual([5, 1]);
    expect(restTile(r, bedInfo, 4, 2)).toEqual([4, 1]);
    // Turned 2, it runs along x.
    expect(restTile(r, bedInfo, 3, 6)).toEqual([1, 6]);
    expect(standAt(r, bedInfo, 1, 3)).toMatchObject({ pose: "lay", dir: 4 });
    expect(standAt(r, bedInfo, 3, 6)).toMatchObject({ pose: "lay", dir: 2 });
    expect(restTile(r, bedInfo, 8, 8)).toEqual([8, 8]);
  });

  it("moves someone saved on a bed's foot to its head when the room opens", () => {
    const r = room(["bed1", 3, 3, 0, 0]);
    r.avatars = [
      { id: 1, name: "A", hotel: "com", figure: "hd-1", x: 3, y: 5, z: 0.9, dir: 4, pose: "lay" },
    ];
    settleOnBeds(r, bedInfo);
    expect([r.avatars[0]?.x, r.avatars[0]?.y]).toEqual([3, 3]);
  });
});

describe("sitting faces a straight direction", () => {
  it("turns a sitter on a diagonal seat to the direction before, as Habbo does", () => {
    expect(standAt(room(["chair", 1, 1, 0, 3]), lookup, 1, 1)).toMatchObject({
      pose: "sit",
      dir: 2,
    });
    expect(standAt(room(["chair", 1, 1, 0, 4]), lookup, 1, 1)).toMatchObject({
      pose: "sit",
      dir: 4,
    });
  });
});
