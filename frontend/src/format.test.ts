import { describe, expect, it } from "vitest";
import type { CatalogItem, Folder } from "./api";
import {
  descendantIds,
  displayValue,
  flattenFolders,
  folderPath,
  formatBytes,
  furniSize,
  groupByType,
  iconUrl,
  timeAgo,
} from "./format";

const folder = (id: number, parent_id: number | null): Folder => ({
  id,
  parent_id,
  name: `f${id}`,
});

describe("format", () => {
  it("formats bytes", () => {
    expect(formatBytes(12)).toBe("12 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(5 * 1024 ** 2)).toBe("5.0 MB");
    expect(formatBytes(3 * 1024 ** 3)).toBe("3.0 GB");
  });

  it("formats ages", () => {
    const now = new Date("2026-10-31T12:00:00Z");
    expect(timeAgo("2026-10-31T11:59:40Z", now)).toBe("just now");
    expect(timeAgo("2026-10-31T11:59:00Z", now)).toBe("1 minute ago");
    expect(timeAgo("2026-10-31T09:00:00Z", now)).toBe("3 hours ago");
    expect(timeAgo("2026-10-29T12:00:00Z", now)).toBe("2 days ago");
  });

  it("escapes the classname in icon URLs", () => {
    expect(iconUrl({ revision: 5, classname: "chair*1" })).toBe("/api/catalog/icons/5/chair*1");
    expect(iconUrl({ revision: 5, classname: "a/../b" })).toBe("/api/catalog/icons/5/a%2F..%2Fb");
  });

  it("describes sizes", () => {
    expect(furniSize({ kind: "wall", xdim: 1, ydim: 1, height: null })).toBe("Wall");
    expect(furniSize({ kind: "floor", xdim: 2, ydim: 1, height: 0.65 })).toBe("2×1, height 0.65");
  });

  it("shows diff values", () => {
    expect(displayValue(null)).toBe("none");
    expect(displayValue("x")).toBe("x");
    expect(displayValue({ a: 1 })).toBe('{"a":1}');
  });

  it("groups furni by type in a fixed order", () => {
    const item = (wired_type: string | null) => ({ wired_type }) as CatalogItem;
    const groups = groupByType([item(null), item("utility"), item("effect"), item("trigger")]);
    expect(groups.map(([type]) => type)).toEqual(["trigger", "effect", "utility", "furni"]);
  });
});

describe("folders", () => {
  const folders = [folder(1, null), folder(2, 1), folder(3, 2), folder(4, null)];

  it("flattens children under their parents", () => {
    expect(flattenFolders(folders).map((f) => [f.id, f.depth])).toEqual([
      [1, 0],
      [2, 1],
      [3, 2],
      [4, 0],
    ]);
  });

  it("blocks moving a folder inside itself", () => {
    expect([...descendantIds(folders, 1)].sort()).toEqual([1, 2, 3]);
    expect([...descendantIds(folders, 4)]).toEqual([4]);
  });

  it("builds the breadcrumb path", () => {
    expect(folderPath(folders, 3).map((f) => f.id)).toEqual([1, 2, 3]);
    expect(folderPath(folders, null)).toEqual([]);
  });
});
