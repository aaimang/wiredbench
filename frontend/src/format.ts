import type { CatalogItem, Folder } from "./api";

export const HOTEL_LABELS: Record<string, string> = {
  sandbox: "Sandbox",
  com: "Habbo.com",
  "com.br": "Habbo.com.br",
  de: "Habbo.de",
  es: "Habbo.es",
  fi: "Habbo.fi",
  fr: "Habbo.fr",
  it: "Habbo.it",
  nl: "Habbo.nl",
  "com.tr": "Habbo.com.tr",
};

export const TYPE_ORDER = [
  "trigger",
  "effect",
  "condition",
  "selector",
  "addon",
  "variable",
  "utility",
];

export function hotelLabel(hotel: string): string {
  return HOTEL_LABELS[hotel] ?? hotel;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const units: [number, string][] = [
    [86400, "day"],
    [3600, "hour"],
    [60, "minute"],
  ];
  for (const [size, name] of units) {
    if (seconds >= size) {
      const count = Math.floor(seconds / size);
      return `${count} ${name}${count === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function furniSize(item: Pick<CatalogItem, "kind" | "xdim" | "ydim" | "height">): string {
  if (item.kind === "wall") return "Wall";
  const height = item.height === null ? "" : `, height ${item.height}`;
  return `${item.xdim}×${item.ydim}${height}`;
}

export function iconUrl(item: Pick<CatalogItem, "revision" | "classname">): string {
  return `/api/catalog/icons/${item.revision}/${encodeURIComponent(item.classname)}`;
}

export function displayValue(value: unknown): string {
  if (value === undefined || value === null) return "none";
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function groupByType(items: CatalogItem[]): [string, CatalogItem[]][] {
  const groups = new Map<string, CatalogItem[]>();
  for (const item of items) {
    const key = item.wired_type ?? "furni";
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return [...groups.entries()].sort(([a], [b]) => rank(a) - rank(b));
}

function rank(type: string): number {
  const index = TYPE_ORDER.indexOf(type);
  return index === -1 ? TYPE_ORDER.length : index;
}

export interface FolderNode extends Folder {
  depth: number;
}

/** Folders in display order, each followed by its children. Orphans are not shown. */
export function flattenFolders(folders: Folder[]): FolderNode[] {
  const children = new Map<number | null, Folder[]>();
  for (const folder of folders) {
    children.set(folder.parent_id, [...(children.get(folder.parent_id) ?? []), folder]);
  }
  const result: FolderNode[] = [];
  const visit = (parent: number | null, depth: number) => {
    for (const folder of children.get(parent) ?? []) {
      result.push({ ...folder, depth });
      visit(folder.id, depth + 1);
    }
  };
  visit(null, 0);
  return result;
}

/** IDs a folder cannot move into: itself and everything inside it. */
export function descendantIds(folders: Folder[], id: number): Set<number> {
  const blocked = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const folder of folders) {
      if (folder.parent_id !== null && blocked.has(folder.parent_id) && !blocked.has(folder.id)) {
        blocked.add(folder.id);
        grew = true;
      }
    }
  }
  return blocked;
}

export function folderPath(folders: Folder[], id: number | null): Folder[] {
  const byId = new Map(folders.map((folder) => [folder.id, folder]));
  const path: Folder[] = [];
  let current = id === null ? undefined : byId.get(id);
  while (current) {
    path.unshift(current);
    current = current.parent_id === null ? undefined : byId.get(current.parent_id);
  }
  return path;
}
