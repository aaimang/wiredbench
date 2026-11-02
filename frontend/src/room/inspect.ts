import { X } from "lucide";
import { get } from "../api";
import { h, icon, replace } from "../dom";
import { t } from "../strings";

const T = t.viewAs.inspect;
const TABS = ["global", "context", "furni"] as const;
export type InspectTab = (typeof TABS)[number];

interface InspectRow {
  name: string;
  value: string | null;
}

/** The window opened by :wired. It floats over the room, which stays usable behind it. */
export class InspectWindow {
  readonly element: HTMLElement;
  tab: InspectTab = "global";
  private furni: { id: number; name: string } | null = null;
  private rows = h("tbody");
  private note = h("p", { class: "muted inspect-note" });
  private tabs = new Map<InspectTab, HTMLElement>();

  constructor(
    private url: string,
    onClose: () => void,
  ) {
    const close = h(
      "button",
      { class: "btn btn-small btn-icon", type: "button", "aria-label": T.close },
      icon(X, 14),
    );
    close.addEventListener("click", onClose);
    const title = h("div", { class: "inspect-title" }, h("h2", {}, T.title), close);
    this.element = h(
      "section",
      { class: "inspect", "aria-label": T.title, "data-testid": "inspect" },
      title,
      h(
        "div",
        { class: "inspect-tabs", role: "tablist" },
        ...TABS.map((tab) => {
          const button = h(
            "button",
            { type: "button", role: "tab", "data-testid": `inspect-${tab}` },
            T.tabs[tab],
          );
          button.addEventListener("click", () => this.show(tab));
          this.tabs.set(tab, button);
          return button;
        }),
      ),
      this.note,
      h(
        "div",
        { class: "inspect-rows" },
        h("table", { class: "table", "data-testid": "inspect-rows" }, this.rows),
      ),
    );
    this.element.addEventListener("keydown", (event) => {
      if (event.key === "Escape") onClose();
    });
    this.bindDrag(title);
    this.show("global");
  }

  private show(tab: InspectTab): void {
    this.tab = tab;
    for (const [name, button] of this.tabs) {
      button.setAttribute("aria-selected", String(name === tab));
    }
    void this.refresh();
  }

  pickFurni(id: number, name: string): void {
    this.furni = { id, name };
    void this.refresh();
  }

  /** Called on every room tick, so that the values stay live. */
  async refresh(): Promise<void> {
    const tab = this.tab;
    this.note.textContent =
      tab === "furni"
        ? this.furni
          ? T.furniPicked(this.furni.name)
          : T.furniHelp
        : (T.notes[tab] ?? "");
    if (tab === "furni" && !this.furni) {
      replace(this.rows);
      return;
    }
    const holder = tab === "furni" ? `&furni=${this.furni?.id}` : "";
    try {
      const rows = await get<InspectRow[]>(`${this.url}?target=${tab}${holder}`);
      if (this.tab !== tab) return;
      replace(
        this.rows,
        ...rows.map((row) =>
          h("tr", {}, h("td", {}, row.name), h("td", {}, row.value ?? T.noValue)),
        ),
      );
    } catch {
      // A missed refresh is put right by the next tick.
    }
  }

  private bindDrag(handle: HTMLElement): void {
    handle.addEventListener("pointerdown", (event) => {
      if ((event.target as HTMLElement).closest("button")) return;
      const box = this.element.getBoundingClientRect();
      const parent = this.element.parentElement?.getBoundingClientRect();
      if (!parent) return;
      const [offsetX, offsetY] = [event.clientX - box.left, event.clientY - box.top];
      handle.setPointerCapture(event.pointerId);
      const move = (next: PointerEvent) => {
        const left = Math.max(
          0,
          Math.min(next.clientX - offsetX - parent.left, parent.width - box.width),
        );
        const top = Math.max(
          0,
          Math.min(next.clientY - offsetY - parent.top, parent.height - box.height),
        );
        Object.assign(this.element.style, { left: `${left}px`, top: `${top}px`, right: "auto" });
      };
      const stop = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", stop);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", stop);
    });
  }
}
