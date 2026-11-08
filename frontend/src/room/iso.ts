/** Isometric geometry for 64 pixel Habbo tiles. */

export const TILE_WIDTH = 64;
export const TILE_HEIGHT = 32;
export const Z_UNIT = 32;

/** Screen position of a tile's centre at a height. */
export function tileCentre(x: number, y: number, z = 0): { x: number; y: number } {
  return {
    x: (x - y) * (TILE_WIDTH / 2),
    y: (x + y + 1) * (TILE_HEIGHT / 2) - z * Z_UNIT,
  };
}

/** The floor tile under a screen position. */
export function screenToTile(screenX: number, screenY: number): [number, number] {
  const a = screenX / (TILE_WIDTH / 2);
  const b = screenY / (TILE_HEIGHT / 2);
  return [Math.floor((a + b) / 2), Math.floor((b - a) / 2)];
}

/** How far one tile along x or y, and one tile of height, bring a thing towards Habbo's room camera. */
const DEPTH_PER_TILE = Math.sqrt(3 / 8);
const DEPTH_PER_HEIGHT = Math.sqrt(1 / 6);

/**
 * Habbo's draw order: higher draws in front. A thing sorts by the tile it stands on and its height, as
 * Habbo's room camera (turned -135 and 30 degrees) measures how near it is, and `relative` moves it
 * back: a furni's layer, or an avatar's small step forward. A furni counts from its own tile, the
 * corner it was placed on, whatever its size, as Habbo's client does.
 */
export function depth(x: number, y: number, z: number, relative = 0): number {
  return DEPTH_PER_TILE * (x + y) + DEPTH_PER_HEIGHT * z - relative;
}

/**
 * How far back a furni layer sits, from the z in its file: a thousandth of it, turned round, so a
 * negative z is further back, and each later layer a thousandth nearer, all times the square root of a
 * half. The shadow (layer -1) sits one step back.
 */
export function layerDepth(layerZ: number, layer: number): number {
  return (layer < 0 ? 1 : layerZ / -1000 - layer * 0.001) * Math.SQRT1_2;
}

/** An avatar sorts a hundredth nearer than its tile, or 0.409 further back while lying. */
export const AVATAR_DEPTH = -0.01;
export const LYING_DEPTH = -0.409;
