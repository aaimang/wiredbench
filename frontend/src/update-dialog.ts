import { ChevronRight } from "lucide";
import {
  type CatalogStatus,
  type CatalogVersion,
  type DiffEntry,
  type DiffPage,
  get,
  post,
} from "./api";
import { h, icon, replace } from "./dom";
import { displayValue, formatDate, hotelLabel, timeAgo } from "./format";
import { t } from "./strings";
import { act, openDialog, toast } from "./ui";

const PAGE = 200;

function summaryRow(label: string, summary: Record<string, number>, scope: string): HTMLElement {
  const count = (change: string) => summary[`${scope}_${change}`] ?? 0;
  return h(
    "div",
    { class: "diff-summary-row" },
    h("span", { class: "diff-summary-label" }, label),
    h("span", { class: "chg chg-new" }, `${count("new")} ${t.update.added}`),
    h("span", { class: "chg chg-changed" }, `${count("changed")} ${t.update.changed}`),
    h("span", { class: "chg chg-removed" }, `${count("removed")} ${t.update.removed}`),
  );
}

export function diffEntry(entry: DiffEntry): HTMLElement {
  const head = [
    h(
      "span",
      { class: `chg chg-${entry.change}` },
      t.update[entry.change === "new" ? "added" : entry.change],
    ),
    h("span", { class: "diff-name" }, entry.name || entry.classname),
    h("code", {}, entry.classname),
  ];
  if (!entry.fields.length) return h("div", { class: "diff-entry" }, ...head);
  return h(
    "details",
    { class: "diff-entry" },
    h(
      "summary",
      {},
      icon(ChevronRight, 14),
      ...head,
      h("span", { class: "muted" }, t.update.fields(entry.fields.length)),
    ),
    h(
      "dl",
      { class: "diff-fields" },
      ...entry.fields.flatMap((field) => [
        h("dt", {}, field.field),
        h(
          "dd",
          {},
          h("del", {}, displayValue(field.old)),
          " ",
          h("ins", {}, displayValue(field.new)),
        ),
      ]),
    ),
  );
}

/** Shows what an update would change. Nothing is applied unless the admin chooses to. */
export async function reviewUpdate(version: CatalogVersion, onDone: () => void): Promise<void> {
  const base = version.base_version_id ?? 0;
  const first = await get<DiffPage>(`/api/catalog/diff/${base}/${version.id}`, { limit: PAGE });
  const isFirst = base === 0;
  const dialog = h("dialog", { class: "dialog dialog-wide", "data-testid": "update-dialog" });
  const list = h("div", { class: "diff-list" });
  let shown = 0;

  const addEntries = (entries: DiffEntry[]) => {
    list.append(...entries.map(diffEntry));
    shown += entries.length;
  };
  const more = h("button", { class: "btn" }, t.update.showMore);
  more.hidden = first.total <= PAGE;
  more.addEventListener("click", () => {
    void act(more, async () => {
      const page = await get<DiffPage>(`/api/catalog/diff/${base}/${version.id}`, {
        limit: PAGE,
        offset: shown,
      });
      addEntries(page.entries);
      more.hidden = shown >= page.total;
    });
  });
  addEntries(first.entries);

  const apply = h(
    "button",
    { class: "btn btn-primary" },
    isFirst ? t.update.applyFirst : t.update.apply,
  );
  apply.addEventListener("click", () => {
    void act(apply, async () => {
      await post("/api/catalog/apply", { version_id: version.id });
      toast(t.update.applied);
      dialog.close();
      onDone();
    });
  });
  const dismiss = h("button", { class: "btn" }, t.update.dismiss);
  dismiss.addEventListener("click", () => {
    void act(dismiss, async () => {
      await post("/api/catalog/dismiss", { version_id: version.id });
      toast(t.update.dismissed);
      dialog.close();
      onDone();
    });
  });

  const dismissLabel = isFirst ? t.update.notNow : t.update.dismiss;
  dismiss.textContent = dismissLabel;
  apply.autofocus = true; // The first control would otherwise be at the end of a long list.
  dialog.append(
    h("h2", {}, (isFirst ? t.update.titleFirst : t.update.title)(hotelLabel(version.hotel))),
    h("p", { class: "muted" }, t.update.counts(version.item_count, version.wired_count)),
    ...(version.skipped_count > 0
      ? [h("p", { class: "muted" }, t.update.skipped(version.skipped_count))]
      : []),
    h(
      "div",
      { class: "diff-summary" },
      summaryRow(t.update.wired, first.summary, "wired"),
      summaryRow(t.update.other, first.summary, "other"),
    ),
    first.total === 0
      ? h("p", {}, t.update.noChanges)
      : h("div", { class: "diff-scroll" }, list, more),
    h(
      "div",
      { class: "dialog-actions" },
      apply,
      version.status === "pending"
        ? dismiss
        : h("button", { class: "btn", onclick: () => dialog.close() }, t.update.close),
    ),
  );
  openDialog(dialog);
}

export function versionsDialog(
  status: CatalogStatus,
  onDone: () => void,
  forceRefresh: (button: HTMLButtonElement) => Promise<void>,
): void {
  const dialog = h("dialog", { class: "dialog" });
  const rows = status.versions.map((version) => {
    const action = versionAction(version, dialog, onDone);
    return h(
      "tr",
      { class: version.status === "current" ? "row-current" : null },
      h(
        "td",
        {},
        formatDate(version.fetched_at),
        h("div", { class: "muted" }, timeAgo(version.fetched_at)),
      ),
      h("td", {}, t.update.counts(version.item_count, version.wired_count)),
      h("td", {}, t.versions[version.status] as string),
      h("td", { class: "cell-action" }, action),
    );
  });
  const force = h("button", { class: "btn" }, t.catalogue.force);
  force.addEventListener("click", () => {
    dialog.close();
    void forceRefresh(force);
  });
  const body = h("tbody", {});
  replace(body, ...rows);
  dialog.append(
    h("h2", {}, (t.versions.title as (hotel: string) => string)(hotelLabel(status.hotel))),
    h("div", { class: "table-scroll" }, h("table", { class: "table" }, body)),
    h(
      "div",
      { class: "dialog-actions" },
      force,
      h("button", { class: "btn", onclick: () => dialog.close() }, t.update.close),
    ),
    h("p", { class: "muted" }, t.catalogue.forceHint),
  );
  openDialog(dialog);
}

function versionAction(
  version: CatalogVersion,
  dialog: HTMLDialogElement,
  onDone: () => void,
): HTMLElement | null {
  if (version.status === "archived") {
    const button = h("button", { class: "btn btn-small" }, t.versions.rollback as string);
    button.addEventListener("click", () => {
      void act(button, async () => {
        await post("/api/catalog/rollback", { version_id: version.id });
        toast(t.versions.rolledBack as string);
        dialog.close();
        onDone();
      });
    });
    return button;
  }
  if (version.status === "pending" || version.status === "dismissed") {
    const button = h("button", { class: "btn btn-small" }, t.versions.review as string);
    button.addEventListener("click", () => {
      void act(button, async () => {
        dialog.close();
        await reviewUpdate(version, onDone);
      });
    });
    return button;
  }
  return null;
}
