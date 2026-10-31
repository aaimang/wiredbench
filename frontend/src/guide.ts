import { Search } from "lucide";
import { get, post, type Sandbox } from "./api";
import { debounce, h, icon, replace } from "./dom";
import { TYPE_ORDER } from "./format";
import { t } from "./strings";
import { act, errorMessage } from "./ui";

const T = t.guide;

interface GuideRow {
  classname: string;
  name: string;
  type: string;
  purpose: string;
  example: string;
  status: string;
  release_stage: string;
}

interface Tutorial {
  slug: string;
  title: string;
  description: string;
  try: string;
}

class WbGuide extends HTMLElement {
  private rows: GuideRow[] = [];
  private query = "";
  private type = "";
  private status = "";
  private list = h("ul", { class: "guide-list", "data-testid": "guide-list" });
  private count = h("p", { class: "muted", role: "status", "data-testid": "guide-count" });

  connectedCallback(): void {
    void this.load();
  }

  private async load(): Promise<void> {
    try {
      const [tutorials, guide] = await Promise.all([
        get<Tutorial[]>("/api/tutorials"),
        get<{ rows: GuideRow[] }>("/api/guide"),
      ]);
      this.rows = guide.rows;
      replace(
        this,
        h(
          "div",
          { class: "guide-page" },
          h("h1", {}, T.title),
          h("h2", {}, T.tutorials),
          h("p", { class: "muted" }, T.tutorialsHelp),
          h("div", { class: "guide-tutorials" }, ...tutorials.map((item) => this.tutorial(item))),
          h("h2", {}, T.boxes),
          ...(this.rows.some((row) => row.release_stage !== "unknown")
            ? []
            : [h("p", { class: "note" }, T.noCatalogue)]),
          this.filters(),
          this.count,
          this.list,
        ),
      );
      this.render();
    } catch (error) {
      replace(this, h("p", { class: "form-error", role: "alert" }, errorMessage(error)));
    }
  }

  private tutorial(item: Tutorial): HTMLElement {
    const add = h("button", { class: "btn" }, T.add);
    add.addEventListener("click", () => {
      void act(add, async () => {
        const room = await post<Sandbox>(`/api/tutorials/${item.slug}`, {});
        location.assign(`/sandbox/${room.id}`);
      });
    });
    return h(
      "section",
      { class: "guide-tutorial", "data-testid": `tutorial-${item.slug}` },
      h("h3", {}, item.title),
      h("p", {}, item.description),
      h("p", { class: "muted" }, T.tryIt(item.try)),
      add,
    );
  }

  private filters(): HTMLElement {
    const search = h("input", {
      type: "search",
      class: "search-input",
      placeholder: T.search,
      "aria-label": T.search,
    });
    search.addEventListener(
      "input",
      debounce(() => {
        this.query = search.value.trim().toLowerCase();
        this.render();
      }, 150),
    );
    const type = h(
      "select",
      { "aria-label": T.allTypes },
      h("option", { value: "" }, T.allTypes),
      ...TYPE_ORDER.map((value) => h("option", { value }, t.types[value] ?? value)),
    );
    type.addEventListener("change", () => {
      this.type = type.value;
      this.render();
    });
    const status = h(
      "select",
      { "aria-label": T.allStatuses },
      h("option", { value: "" }, T.allStatuses),
      ...Object.entries(T.statuses).map(([value, label]) => h("option", { value }, label)),
    );
    status.addEventListener("change", () => {
      this.status = status.value;
      this.render();
    });
    return h(
      "div",
      { class: "guide-filters" },
      h("label", { class: "search" }, icon(Search), search),
      type,
      status,
    );
  }

  private render(): void {
    const shown = this.rows.filter(
      (row) =>
        (!this.type || row.type === this.type) &&
        (!this.status || row.status === this.status) &&
        (!this.query ||
          `${row.classname} ${row.name} ${row.purpose}`.toLowerCase().includes(this.query)),
    );
    this.count.textContent = T.count(shown.length, this.rows.length);
    if (!shown.length) {
      replace(this.list, h("li", {}, T.none));
      return;
    }
    replace(this.list, ...shown.map((row) => this.row(row)));
  }

  private row(row: GuideRow): HTMLElement {
    return h(
      "li",
      { class: `guide-row wire-${row.type}` },
      h("h3", {}, row.name),
      h("code", {}, row.classname),
      h("p", {}, row.purpose || T.noPurpose),
      row.example && h("p", { class: "muted" }, T.example(row.example)),
      h(
        "p",
        { class: "chips" },
        h(
          "span",
          { class: `badge guide-status-${row.status}` },
          T.statuses[row.status] ?? row.status,
        ),
        row.release_stage === "not_in_catalogue" && h("span", { class: "badge" }, T.noOffer),
      ),
    );
  }
}

customElements.define("wb-guide", WbGuide);
