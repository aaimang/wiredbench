/** Wiredbench's own drawing of Variable FX displays. It shows the same elements as a real room, not its art. */
import { Container, Graphics, Text } from "pixi.js";
import { type FxShown, fxFill } from "./model";

const FRAME = 0x2a2a2a;
const EDGE = 0x8a8f86;
const EMPTY = 0x3a3d3a;
const GREEN = 0x4fc24f;
const RED = 0xd4342c;
const YELLOW = 0xf0c419;
const DIGIT = 0x7fe08a;
const BADGE_SIZE = 14;
/** Every row but the boss bar shares this width and these edges, so the stack reads as one column. */
const COLUMN = 60;
const LEFT = -COLUMN / 2;
/** Where bars start when an icon or badge sits to their left. */
const BESIDE_ICON = LEFT + 16;
const BESIDE_WIDTH = COLUMN - 16;
const ROW_GAP = 4;
const ROW_HEIGHTS: Record<string, number> = {
  number: 14,
  levelling: 14,
  boss: 16,
  hp: 12,
  status: 12,
};
const DEFAULT_ROW_HEIGHT = 10;
const INK = 0x111111;

/** Small pictures as rows of pixels: # is the colour and + is the shading beside it. */
const HEART = [" ## ## ", "#++#++#", "#+++++#", " #+++# ", "  #+#  ", "   #   "];
const BOLT = ["   ## ", "  ##  ", " #### ", "   ## ", "  ##  ", " ##   "];
const SKULL = [" ##### ", "#######", "#+ # +#", "#######", " ## ## ", " # # # "];

function picture(rows: string[], color: number, shade: number, scale: number): Graphics {
  const art = new Graphics();
  // A dark edge first, so a pale icon still shows on a pale floor.
  rows.forEach((row, y) => {
    [...row].forEach((pixel, x) => {
      if (pixel !== " ") art.rect(x * scale - 1, y * scale - 1, scale + 2, scale + 2).fill(INK);
    });
  });
  rows.forEach((row, y) => {
    [...row].forEach((pixel, x) => {
      if (pixel === " ") return;
      art.rect(x * scale, y * scale, scale, scale).fill(pixel === "#" ? color : shade);
    });
  });
  return art;
}

function bar(width: number, height: number, fill: number, color: number, segments = 0): Graphics {
  const art = new Graphics()
    .rect(-1, -1, width + 2, height + 2)
    .fill(FRAME)
    .rect(0, 0, width, height)
    .fill(EMPTY)
    .rect(0, 0, Math.round(width * fill), height)
    .fill(color)
    .rect(0, 0, Math.round(width * fill), 1)
    .fill({ color: 0xffffff, alpha: 0.35 });
  for (let i = 1; i < segments; i++) {
    art.rect(Math.round((width * i) / segments), 0, 1, height).fill(FRAME);
  }
  return art;
}

function label(text: string, size: number, fill: number): Text {
  const shown = new Text({
    text,
    style: {
      fontFamily: "monospace",
      fontSize: size,
      fontWeight: "bold",
      fill,
      stroke: { color: 0x000000, width: 3 },
    },
  });
  shown.anchor.set(0.5);
  return shown;
}

/** How much height a display takes in the stack over its holder, with the gap below it. */
export function fxHeight(kind: string): number {
  return (ROW_HEIGHTS[kind] ?? DEFAULT_ROW_HEIGHT) + ROW_GAP;
}

function iconRow(icon: Graphics, iconWidth: number, shown: Graphics, barHeight: number): Container {
  const row = new Container();
  icon.position.set(BESIDE_ICON - 3 - iconWidth, -6);
  shown.position.set(BESIDE_ICON, -barHeight / 2);
  row.addChild(shown, icon);
  return row;
}

/** One display, centred on its origin. */
export function fxArt(fx: FxShown): Container {
  const fill = fxFill(fx);
  const art = new Container();
  switch (fx.kind) {
    case "number":
      art.addChild(label(fx.value, 14, DIGIT));
      break;
    case "levelling": {
      // Without a level-up add-on, a real room showed level 0 and an almost empty bar.
      const badge = new Container();
      badge.position.set(LEFT + BADGE_SIZE / 2, 0);
      badge.addChild(
        new Graphics()
          .roundRect(-BADGE_SIZE / 2, -BADGE_SIZE / 2, BADGE_SIZE, BADGE_SIZE, 3)
          .fill(FRAME)
          .stroke({ width: 2, color: GREEN }),
        label("0", 10, 0xffffff),
      );
      const progress = bar(
        BESIDE_WIDTH,
        6,
        Math.max(0, Math.min(Number(fx.value) / 100, 1)),
        GREEN,
        5,
      );
      progress.position.set(BESIDE_ICON, -3);
      art.addChild(progress, badge);
      break;
    }
    case "boss": {
      const width = 120;
      const main = bar(width, 12, fill, RED);
      main.position.set(-width / 2, -6);
      const left = picture(SKULL, 0xf2f2ee, 0x222222, 2);
      left.position.set(-width / 2 - 16, -6);
      const right = picture(SKULL, 0xf2f2ee, 0x222222, 2);
      right.position.set(width / 2 + 2, -6);
      art.addChild(main, left, right);
      break;
    }
    case "hp":
      art.addChild(
        iconRow(picture(HEART, RED, 0xf25a50, 2), 14, bar(BESIDE_WIDTH, 6, fill, GREEN), 6),
      );
      break;
    case "status":
      art.addChild(
        iconRow(picture(BOLT, YELLOW, YELLOW, 2), 12, bar(BESIDE_WIDTH, 6, fill, YELLOW, 5), 6),
      );
      break;
    default: {
      const frame = new Graphics().rect(LEFT, -5, COLUMN, 10).fill(EDGE);
      const main = bar(COLUMN - 4, 6, fill, GREEN);
      main.position.set(LEFT + 2, -3);
      art.addChild(frame, main);
    }
  }
  return art;
}
