import { get, post, request } from "./api";
import { h, replace } from "./dom";
import { runClock } from "./room/run-panel";
import { t } from "./strings";
import { act, errorMessage, openDialog, toast } from "./ui";

const T = t.dashboard;
const REFRESH_MS = 2000;

interface DashboardRoom {
  id: number;
  name: string;
  paused: boolean;
  now_ms: number;
  boxes: { id: number; classname: string; x: number; y: number; runs: number }[];
  stacks: { stack: string; runs: number; work: number }[];
  signals: number;
  errors: number;
  stubs: number;
  limit_hits: number;
  problems: { at_ms: number; kind: string; message: string }[];
}

interface KeyStatus {
  configured: boolean;
  allow_mass_deletion: boolean;
  read_key?: string;
  write_key?: string;
}

function table(headings: string[], rows: (string | number)[][]): HTMLElement {
  return h(
    "table",
    { class: "table" },
    h("thead", {}, h("tr", {}, ...headings.map((heading) => h("th", {}, heading)))),
    h(
      "tbody",
      {},
      ...rows.map((row) => h("tr", {}, ...row.map((cell) => h("td", {}, String(cell))))),
    ),
  );
}

class WbDashboard extends HTMLElement {
  private timer: ReturnType<typeof setInterval> | null = null;
  private rooms = h("div", { class: "dashboard-page" });
  /** Key panels are kept between refreshes, so a tick cannot wipe a tick box or a dialog. */
  private keyPanels = new Map<number, HTMLElement>();

  connectedCallback(): void {
    replace(this, this.rooms);
    void this.refresh();
    this.timer = setInterval(() => void this.refresh(), REFRESH_MS);
  }

  disconnectedCallback(): void {
    if (this.timer !== null) clearInterval(this.timer);
  }

  private async refresh(): Promise<void> {
    try {
      const { rooms } = await get<{ rooms: DashboardRoom[] }>("/api/dashboard");
      replace(
        this.rooms,
        h("h1", {}, T.title),
        h("p", { class: "muted" }, T.note),
        ...(rooms.length
          ? rooms.map((room) => this.room(room))
          : [h("p", { "data-testid": "dashboard-empty" }, T.empty)]),
      );
    } catch (error) {
      if (this.timer !== null) clearInterval(this.timer);
      replace(this.rooms, h("p", { class: "form-error", role: "alert" }, errorMessage(error)));
    }
  }

  private room(room: DashboardRoom): HTMLElement {
    const counts: [string, number][] = [
      [T.signals, room.signals],
      [T.errors, room.errors],
      [T.stubs, room.stubs],
      [T.limitHits, room.limit_hits],
    ];
    return h(
      "section",
      { class: "dashboard-room", "data-testid": "dashboard-room" },
      h("h2", {}, room.name),
      h("p", { class: "muted" }, room.paused ? T.paused : T.time(runClock(room.now_ms))),
      h(
        "dl",
        { class: "dashboard-counts" },
        ...counts.map(([label, value]) =>
          h("div", {}, h("dt", {}, label), h("dd", {}, String(value))),
        ),
      ),
      h(
        "div",
        { class: "dashboard-columns" },
        h(
          "div",
          {},
          h("h3", {}, T.stacks),
          room.stacks.length
            ? table(
                [T.stack, T.runs, T.work],
                room.stacks.map((row) => [row.stack, row.runs, row.work]),
              )
            : h("p", { class: "muted" }, T.noRows),
        ),
        h(
          "div",
          {},
          h("h3", {}, T.boxes),
          room.boxes.length
            ? table(
                [T.box, T.tile, T.runs],
                room.boxes.map((row) => [row.classname, `${row.x}, ${row.y}`, row.runs]),
              )
            : h("p", { class: "muted" }, T.noRows),
        ),
        h(
          "div",
          {},
          h("h3", {}, T.problems),
          room.problems.length
            ? h(
                "ul",
                { class: "dashboard-problems" },
                ...room.problems.map((line) =>
                  h("li", {}, `${runClock(line.at_ms)} ${line.message}`),
                ),
              )
            : h("p", { class: "muted" }, T.noProblems),
        ),
      ),
      this.keyPanel(room.id),
    );
  }

  private keyPanel(id: number): HTMLElement {
    const existing = this.keyPanels.get(id);
    if (existing) return existing;
    const panel = h("div", { class: "dashboard-keys", "data-testid": `api-keys-${id}` });
    this.keyPanels.set(id, panel);
    void this.renderKeys(id, panel);
    return panel;
  }

  private async renderKeys(id: number, panel: HTMLElement): Promise<void> {
    const url = `/api/sandboxes/${id}/api-keys`;
    const status = await get<KeyStatus>(url);
    const mass = h("input", {
      id: `mass-${id}`,
      type: "checkbox",
      checked: status.allow_mass_deletion,
    });
    const generate = h(
      "button",
      { class: "btn", type: "button" },
      status.configured ? T.regenerate : T.generate,
    );
    generate.addEventListener("click", () => {
      void act(generate, async () => {
        const keys = await post<KeyStatus>(url, { allow_mass_deletion: mass.checked });
        this.showKeys(keys);
        await this.renderKeys(id, panel);
      });
    });
    const clear = h("button", { class: "btn", type: "button" }, T.clear);
    clear.addEventListener("click", () => {
      void act(clear, async () => {
        await request("DELETE", url);
        toast(T.cleared);
        await this.renderKeys(id, panel);
      });
    });
    replace(
      panel,
      h("h3", {}, T.api),
      h("p", {}, T.apiHelp(`${location.origin}/api/public/rooms/${id}`)),
      h("p", { class: "muted" }, status.configured ? T.apiHasKeys : T.apiNoKeys),
      h(
        "div",
        { class: "dashboard-actions" },
        generate,
        status.configured && clear,
        h("label", { for: `mass-${id}` }, mass, ` ${T.massDelete}`),
      ),
    );
  }

  private showKeys(keys: KeyStatus): void {
    const close = h("button", { class: "btn btn-primary", type: "button" }, T.close);
    const dialog = h(
      "dialog",
      { class: "dialog", "data-testid": "keys-dialog" },
      h("h2", {}, T.keysTitle),
      h("p", { class: "muted" }, T.keysHelp),
      h("p", {}, T.readKey, h("code", { class: "key-value" }, keys.read_key ?? "")),
      h("p", {}, T.writeKey, h("code", { class: "key-value" }, keys.write_key ?? "")),
      close,
    );
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => dialog.remove());
    this.append(dialog);
    openDialog(dialog);
  }
}

customElements.define("wb-dashboard", WbDashboard);
