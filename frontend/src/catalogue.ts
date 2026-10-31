import { Box, History, RefreshCw, Search, X } from "lucide";
import {
  ApiFailure,
  type CatalogItem,
  type CatalogStatus,
  get,
  type ItemPage,
  post,
  type SyncResult,
} from "./api";
import { debounce, h, icon, replace } from "./dom";
import { furniSize, groupByType, hotelLabel, iconUrl, TYPE_ORDER, timeAgo } from "./format";
import { type BoxCatalogue, loadBoxCatalogue } from "./room/run-panel";
import { state } from "./state";
import { t } from "./strings";
import { act, errorMessage, toast } from "./ui";
import { reviewUpdate, versionsDialog } from "./update-dialog";

const PAGE = 500; // More than the WIRED total, so that list is never cut short.

function furniIcon(item: CatalogItem): HTMLElement {
  const holder = h("span", { class: "furni-icon" });
  const image = h("img", { src: iconUrl(item), alt: "", loading: "lazy" });
  image.addEventListener("error", () => replace(holder, icon(Box, 16)));
  holder.append(image);
  return holder;
}

export function stageBadge(
  item: Pick<CatalogItem, "release_stage" | "is_new">,
): HTMLElement | null {
  if (item.is_new) return h("span", { class: "badge badge-new" }, t.stages.new);
  if (item.release_stage === "not_in_catalogue") {
    return h("span", { class: "badge badge-hidden" }, t.stages.not_in_catalogue);
  }
  return null;
}

class WbCatalogue extends HTMLElement {
  private hotel = state.settings?.default_hotel ?? "sandbox";
  private q = "";
  private scope: "wired" | "all" = "wired";
  private wiredType = "";
  private stage = "";
  private items: CatalogItem[] = [];
  private total = 0;
  private facets: Record<string, number> = {};
  private status: CatalogStatus | null = null;
  private selected: CatalogItem | null = null;
  private notice = "";
  private searchInput = h("input", {
    type: "search",
    placeholder: t.catalogue.search,
    "aria-label": t.catalogue.search,
    class: "search-input",
  });
  private toolbar = h("div", { class: "toolbar" });
  private filters = h("nav", { class: "type-filters", "aria-label": t.detail.type });
  private list = h("div", { class: "furni-list", "data-testid": "furni-list" });
  private detail = h("aside", { class: "detail-panel" });
  private request = 0;
  private boxes: BoxCatalogue = {};

  connectedCallback(): void {
    this.searchInput.addEventListener(
      "input",
      debounce(() => {
        this.q = this.searchInput.value;
        void this.load();
      }, 200),
    );
    replace(
      this,
      this.toolbar,
      h("div", { class: "catalogue-body" }, this.filters, this.list, this.detail),
    );
    this.renderDetail();
    void this.refresh();
    void loadBoxCatalogue()
      .then((boxes) => {
        this.boxes = boxes;
      })
      .catch(() => {});
  }

  private async refresh(): Promise<void> {
    await Promise.all([this.loadStatus(), this.load()]);
  }

  private async loadStatus(): Promise<void> {
    try {
      this.status = await get<CatalogStatus>("/api/catalog/status", { hotel: this.hotel });
    } catch (error) {
      toast(errorMessage(error), "error");
    }
    this.renderToolbar();
  }

  private async load(append = false): Promise<void> {
    const ticket = ++this.request;
    try {
      const page = await get<ItemPage>("/api/catalog/items", {
        hotel: this.hotel,
        q: this.q,
        scope: this.scope,
        wired_type: this.wiredType,
        stage: this.stage,
        limit: PAGE,
        offset: append ? this.items.length : 0,
      });
      if (ticket !== this.request) return; // A newer search has replaced this one.
      this.items = append ? [...this.items, ...page.items] : page.items;
      this.total = page.total;
      this.facets = page.facets;
      this.filters.hidden = page.version === null;
      this.renderFilters();
      this.renderList();
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  private renderToolbar(): void {
    const hotels = state.settings?.hotels ?? [this.hotel];
    const select = h(
      "select",
      { "aria-label": t.catalogue.hotel, "data-testid": "hotel-select" },
      ...hotels.map((hotel) =>
        h("option", { value: hotel, selected: hotel === this.hotel }, hotelLabel(hotel)),
      ),
    );
    select.addEventListener("change", () => {
      this.hotel = select.value;
      this.selected = null;
      this.notice = "";
      this.renderDetail();
      void this.refresh();
    });
    const scopeButton = (value: "wired" | "all", label: string) =>
      h(
        "button",
        {
          class: "segment",
          "aria-pressed": String(this.scope === value),
          onclick: () => {
            this.scope = value;
            this.wiredType = "";
            this.renderToolbar();
            void this.load();
          },
        },
        label,
      );
    replace(
      this.toolbar,
      select,
      h("label", { class: "search" }, icon(Search), this.searchInput),
      h(
        "div",
        { class: "segments", role: "group" },
        scopeButton("wired", t.catalogue.wired),
        scopeButton("all", t.catalogue.all),
      ),
      h("div", { class: "toolbar-spacer" }),
      this.statusLine(),
      this.versionsButton(),
      this.status && !this.status.current && !this.status.pending ? null : this.updateButton(),
    );
  }

  private statusLine(): HTMLElement {
    const status = this.status;
    let text = this.notice;
    if (!text && status?.last_checked_at && status.current) {
      const prefix = status.last_result === "up_to_date" ? `${t.catalogue.upToDate}, ` : "";
      text = prefix + t.catalogue.checkedAgo(timeAgo(status.last_checked_at));
    }
    return h("span", { class: "status-line muted", "data-testid": "status-line" }, text);
  }

  private versionsButton(): HTMLElement | null {
    const status = this.status;
    if (!status?.current) return null;
    return h(
      "button",
      {
        class: "btn btn-quiet",
        onclick: () =>
          versionsDialog(
            status,
            () => void this.refresh(),
            (button) => this.sync(button, true),
          ),
      },
      icon(History),
      t.catalogue.versions,
    );
  }

  private updateButton(): HTMLElement {
    const pending = this.status?.pending;
    if (pending) {
      const review = h(
        "button",
        { class: "btn btn-attention", "data-testid": "update-button" },
        h("span", { class: "dot" }),
        t.catalogue.review,
      );
      review.addEventListener("click", () => {
        void act(review, () => reviewUpdate(pending, () => void this.refresh()));
      });
      return review;
    }
    const button = h(
      "button",
      { class: "btn btn-primary", "data-testid": "update-button" },
      icon(RefreshCw),
      t.catalogue.update,
    );
    button.addEventListener("click", () => void this.sync(button, false));
    return button;
  }

  private async sync(button: HTMLButtonElement, force: boolean): Promise<void> {
    button.disabled = true;
    const label = [...button.childNodes];
    replace(button, t.catalogue.checking);
    try {
      const result = await post<SyncResult>("/api/catalog/sync", { hotel: this.hotel, force });
      this.status = result.status;
      this.notice = "";
      this.renderToolbar();
      if (result.status.pending && result.result !== "up_to_date") {
        await reviewUpdate(result.status.pending, () => void this.refresh());
      } else {
        toast(t.catalogue.upToDate);
      }
    } catch (error) {
      button.replaceChildren(...label);
      button.disabled = false;
      const current = this.status?.current;
      if (error instanceof ApiFailure && error.status === 502 && current) {
        this.notice = t.catalogue.staleWarning(timeAgo(current.fetched_at));
      }
      toast(errorMessage(error), "error");
      await this.loadStatus();
    }
  }

  private renderFilters(): void {
    const typeButton = (value: string, label: string, count: number | null) =>
      h(
        "button",
        {
          class: `type-filter wire-${value || "all"}`,
          "aria-pressed": String(this.wiredType === value),
          onclick: () => {
            this.wiredType = value;
            void this.load();
          },
        },
        h("span", { class: "wire-tail" }),
        h("span", { class: "type-filter-label" }, label),
        count !== null && h("span", { class: "muted" }, count.toLocaleString("en")),
      );
    const sum = Object.values(this.facets).reduce((a, b) => a + b, 0);
    const stageSelect = h(
      "select",
      { "aria-label": t.catalogue.stage, "data-testid": "stage-select" },
      h("option", { value: "" }, t.catalogue.allStages),
      ...Object.entries(t.stages).map(([value, label]) =>
        h("option", { value, selected: value === this.stage }, label),
      ),
    );
    stageSelect.addEventListener("change", () => {
      this.stage = stageSelect.value;
      void this.load();
    });
    replace(
      this.filters,
      typeButton("", t.catalogue.allTypes, sum),
      ...TYPE_ORDER.filter(
        (type) => this.facets[type] !== undefined || this.wiredType === type,
      ).map((type) => typeButton(type, t.types[type] ?? type, this.facets[type] ?? 0)),
      h("div", { class: "stage-filter" }, stageSelect),
    );
  }

  private renderList(): void {
    if (!this.status?.current && this.items.length === 0) {
      void this.renderEmpty();
      return;
    }
    if (this.items.length === 0) {
      const clear = h(
        "button",
        {
          class: "btn",
          onclick: () => {
            this.q = "";
            this.searchInput.value = "";
            this.wiredType = "";
            this.stage = "";
            void this.load();
          },
        },
        t.catalogue.clearFilters,
      );
      replace(this.list, h("div", { class: "empty" }, h("p", {}, t.catalogue.noResults), clear));
      return;
    }
    const groups = groupByType(this.items).map(([type, items]) =>
      h(
        "section",
        { class: `furni-group wire-${type}` },
        h("h2", { class: "furni-group-title" }, t.types[type] ?? t.catalogue.all),
        ...items.map((item) => this.renderRow(item)),
      ),
    );
    const left = this.total - this.items.length;
    const more = h("button", { class: "btn load-more" }, t.catalogue.loadMore(left));
    more.addEventListener("click", () => void act(more, () => this.load(true)));
    replace(
      this.list,
      h(
        "p",
        { class: "muted list-count", "data-testid": "list-count" },
        t.catalogue.total(this.items.length, this.total),
      ),
      ...groups,
      left > 0 && more,
    );
  }

  private async renderEmpty(): Promise<void> {
    if (this.status === null) await this.loadStatus();
    if (this.status?.current) return;
    const button = h(
      "button",
      { class: "btn btn-primary", "data-testid": "download-button" },
      t.catalogue.download,
    );
    button.addEventListener("click", () => void this.sync(button, false));
    replace(
      this.list,
      h(
        "div",
        { class: "empty" },
        h("h2", {}, t.catalogue.emptyTitle(hotelLabel(this.hotel))),
        h("p", {}, t.catalogue.emptyBody),
        button,
      ),
    );
  }

  private renderRow(item: CatalogItem): HTMLElement {
    const selected = this.selected?.classname === item.classname;
    return h(
      "button",
      {
        class: "furni-row",
        "aria-pressed": String(selected),
        "data-classname": item.classname,
        onclick: () => void this.select(item),
      },
      h("span", { class: "wire-tick" }),
      furniIcon(item),
      h(
        "span",
        { class: "furni-names" },
        h("span", { class: "furni-name" }, item.name || item.classname),
        h("code", {}, item.classname),
      ),
      stageBadge(item),
    );
  }

  private async select(item: CatalogItem): Promise<void> {
    this.selected = item;
    for (const row of this.list.querySelectorAll<HTMLElement>(".furni-row")) {
      row.setAttribute("aria-pressed", String(row.dataset.classname === item.classname));
    }
    this.renderDetail();
    try {
      const full = await get<CatalogItem>(
        `/api/catalog/items/${encodeURIComponent(item.classname)}`,
        {
          hotel: this.hotel,
        },
      );
      if (this.selected?.classname === item.classname) {
        this.selected = full;
        this.renderDetail();
      }
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  private simulation(classname: string): string {
    const spec = this.boxes[classname];
    return spec ? (t.run.fidelity[spec.fidelity] ?? spec.fidelity) : t.detail.notSimulated;
  }

  private renderDetail(): void {
    const item = this.selected;
    this.detail.classList.toggle("is-open", item !== null);
    if (!item) {
      replace(this.detail, h("p", { class: "muted detail-prompt" }, t.catalogue.selectPrompt));
      return;
    }
    const row = (label: string, value: string | Node | null) =>
      value === "" || value === null ? [] : [h("dt", {}, label), h("dd", {}, value)];
    const close = h(
      "button",
      {
        class: "btn btn-quiet btn-icon detail-close",
        "aria-label": t.detail.close,
        onclick: () => {
          this.selected = null;
          this.renderDetail();
        },
      },
      icon(X),
    );
    replace(
      this.detail,
      close,
      h("div", { class: "detail-head" }, furniIcon(item), h("h2", {}, item.name || item.classname)),
      item.description && h("p", {}, item.description),
      item.release_stage === "not_in_catalogue" &&
        h("p", { class: "note" }, t.detail.candidateNote),
      h(
        "dl",
        { class: "facts" },
        ...row(t.detail.classname, h("code", {}, item.classname)),
        ...row(t.detail.type, item.wired_type ? (t.types[item.wired_type] ?? "") : t.catalogue.all),
        ...row(t.detail.status, t.stages[item.is_new ? "new" : item.release_stage] ?? ""),
        ...row(t.detail.size, furniSize(item)),
        ...row(t.detail.furniId, String(item.furni_id)),
        ...row(t.detail.revision, String(item.revision)),
        ...row(t.detail.category, item.category),
        ...row(t.detail.line, item.furniline),
        ...row(t.detail.simulation, item.is_wired ? this.simulation(item.classname) : ""),
      ),
      item.data &&
        h(
          "details",
          { class: "raw-data" },
          h("summary", {}, t.detail.raw),
          h("pre", {}, JSON.stringify(item.data, null, 2)),
        ),
    );
  }
}

customElements.define("wb-catalogue", WbCatalogue);
