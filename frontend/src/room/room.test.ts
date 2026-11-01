import { describe, expect, it } from "vitest";
import { depth, screenToTile, tileCentre } from "./iso";
import {
  avatarExtras,
  directionBetween,
  drawTile,
  emptyRoom,
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
  furniAt,
  furniParts,
  fxFill,
  History,
  highlightTint,
  type InfoLookup,
  isWiredBox,
  nextDirection,
  nextId,
  normaliseRoom,
  type PlacedFurni,
  pickWalkLook,
  type RoomDocument,
  showsTime,
  stackHeight,
  standAt,
  timeDigits,
  withFace,
} from "./model";
import { isDebugCommand, runClock } from "./run-panel";

const INFO: Record<string, FurniInfo> = {
  wall: { xdim: 1, ydim: 1, height: 1, canStand: false, canSit: false, canLay: false },
  mat: { xdim: 1, ydim: 1, height: 0.1, canStand: true, canSit: false, canLay: false },
  chair: { xdim: 1, ydim: 1, height: 1, canStand: false, canSit: true, canLay: false },
  bed: { xdim: 2, ydim: 3, height: 1, canStand: false, canSit: false, canLay: true },
  tower: { xdim: 1, ydim: 1, height: 3, canStand: true, canSit: false, canLay: false },
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
    expect(avatarExtras({}, "blow", 250).frame).toBe(1);
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
    expect(withFace(look, { face: null, pose: "std" }, false, 0)).toEqual(look);
    expect(withFace(look, { face: "nope", pose: "std" }, false, 0)).toEqual(look);
  });

  it("keeps a still face at any time and while walking", () => {
    expect(withFace(look, standing, false, 99999).gesture).toBe("sml");
    expect(withFace(look, standing, true, 99999).gesture).toBe("sml");
  });

  it("moves a speaking face between its frames", () => {
    const speaking = { face: "speaking", pose: "std" as const };
    expect(withFace(look, speaking, false, 0).gesture).toBe("spk");
    expect(withFace(look, speaking, false, 200).gesture).toBe("std");
    expect(faceIsAnimated("speaking")).toBe(true);
    expect(faceIsAnimated("happy")).toBe(false);
  });

  it("only uses the laugh image when it would not stop a walk or a seat", () => {
    const laughing = { face: "laughing", pose: "std" as const };
    expect(withFace(look, laughing, false, 0).extra).toEqual(["lgh"]);
    expect(withFace(look, laughing, true, 0)).toMatchObject({ extra: [], gesture: "spk" });
    expect(withFace(look, { ...laughing, pose: "sit" }, false, 0).extra).toEqual([]);
    expect(withFace({ ...look, extra: ["sig=6"] }, laughing, false, 0).extra).toEqual(["sig=6"]);
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
