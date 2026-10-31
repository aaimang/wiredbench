import { t } from "./strings";

export class ApiFailure extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

let csrfToken = "";
let onSignedOut: () => void = () => {};

export function setCsrfToken(token: string): void {
  csrfToken = token;
}

export function setSignedOutHandler(handler: () => void): void {
  onSignedOut = handler;
}

type Query = Record<string, string | number | undefined | null>;

export function withQuery(path: string, query: Query = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiFailure(0, "offline", t.common.offline);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && data?.error === "not_logged_in") onSignedOut();
    throw new ApiFailure(
      response.status,
      data?.error ?? "unknown",
      data?.message ?? t.common.unknownError,
    );
  }
  return data as T;
}

export const get = <T>(path: string, query?: Query) => request<T>("GET", withQuery(path, query));
export const post = <T>(path: string, body?: unknown) => request<T>("POST", path, body);
export const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
export const del = (path: string) => request<void>("DELETE", path);

export interface Me {
  username: string;
  csrf_token: string;
  view_as: boolean;
}

export interface CatalogVersion {
  id: number;
  hotel: string;
  status: "pending" | "dismissed" | "current" | "archived";
  base_version_id: number | null;
  fetched_at: string;
  applied_at: string | null;
  item_count: number;
  wired_count: number;
  skipped_count: number;
}

export interface CatalogStatus {
  hotel: string;
  current: CatalogVersion | null;
  pending: CatalogVersion | null;
  versions: CatalogVersion[];
  last_checked_at: string | null;
  last_result: string | null;
  last_error: string | null;
  updates_waiting: string[];
  cooldown_seconds: number;
}

export interface SyncResult {
  result: "up_to_date" | "first_import" | "update_available";
  version_id: number | null;
  status: CatalogStatus;
}

export interface CatalogItem {
  classname: string;
  kind: "floor" | "wall";
  furni_id: number;
  revision: number;
  name: string;
  description: string;
  category: string;
  furniline: string;
  xdim: number;
  ydim: number;
  height: number | null;
  is_wired: boolean;
  wired_type: string | null;
  release_stage: string;
  is_new: boolean;
  data?: Record<string, unknown>;
}

export interface ItemPage {
  version: CatalogVersion | null;
  items: CatalogItem[];
  total: number;
  facets: Record<string, number>;
}

export interface DiffEntry {
  classname: string;
  change: "new" | "changed" | "removed";
  is_wired: boolean;
  wired_type: string | null;
  name: string;
  fields: { field: string; old: unknown; new: unknown }[];
}

export interface DiffPage {
  summary: Record<string, number>;
  total: number;
  entries: DiffEntry[];
}

export interface Folder {
  id: number;
  parent_id: number | null;
  name: string;
}

export interface Sandbox {
  id: number;
  folder_id: number | null;
  name: string;
  description: string;
  kind: string;
  hotel: string;
  revision: number;
  updated_at: string;
}

export interface Tree {
  folders: Folder[];
  sandboxes: Sandbox[];
}

export interface TrashEntry {
  kind: "folder" | "sandbox";
  id: number;
  name: string;
  deleted_at: string;
  purge_at: string;
}

export interface Settings {
  default_hotel: string;
  gamedata_check: string;
  cache_max_mb: number;
  session_hours: number;
  theme: string;
  tick_ms: number;
  rate_limit_mock: number;
  audit_days: number;
  click_outside_cancels: boolean;
  pickup_shortcut: boolean;
  hotels: string[];
  version: string;
}

export interface CacheInfo {
  assets_bytes: number;
  gamedata_bytes: number;
  limit_bytes: number;
}

export interface AuditRow {
  at: string;
  actor: string;
  action: string;
  target: string;
}
