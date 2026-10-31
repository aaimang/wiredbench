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

/**
 * Draw order for things in the room. Nearer tiles draw later, higher things draw over lower ones on the
 * same tile, and the layer value orders the parts of one furni.
 */
export function depth(frontX: number, frontY: number, z: number, layer = 0): number {
  return (frontX + frontY) * 10000 + z * 100 + layer * 0.01;
}
