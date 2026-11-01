import { Pause, Play, Send, SkipForward, Square } from "lucide";
import { ApiFailure, get, post, request } from "../api";
import { h, icon, replace } from "../dom";
import { t } from "../strings";
import { errorMessage, toast } from "../ui";
import type { Flight, FxShown, Look } from "./model";

const T = t.run;
const TICK_MS = 250;
const INT64_TEXT = /^-?\d{1,19}$/;
const TRACE_SHOWN = 300;

export interface RunState {
  now_ms: number;
  paused: boolean;
  seed: number;
  furni: { id: number; x: number; y: number; z: number; rot: number; state: number }[];
  users: { id: number; name: string; x: number; y: number; dir: number }[];
  variables: { variable: string; holder: string; value: string }[];
  defined_variables: { variable: string; scope: string }[];
  game: { running: boolean; scores: Record<string, number> };
  fx: FxShown[];
  flights: Flight[];
  looks: { furni: Record<number, Look>; users: Record<number, Look> };
  trace: { at_ms: number; kind: string; message: string }[];
  trace_next: number;
  limit_hits: number;
  answer?: string;
}

export interface BoxField {
  name: string;
  kind: "text" | "textarea" | "number" | "bool" | "select" | "furni";
  label: string;
  default: unknown;
  options?: string[];
  labels?: Record<string, string>;
  saved_only?: boolean;
  min?: number;
  step?: number;
  max?: number;
}

export interface BoxSpec {
  kind: string;
  fidelity: string;
  checked_on?: string | null;
  fields: BoxField[];
}

export type BoxCatalogue = Record<string, BoxSpec>;

/** Rooms can use keywords such as :time, so only the debug commands themselves are held back from chat. */
export function isDebugCommand(text: string): boolean {
  return /^:(vars|set|trace|pause|resume|step|as)(\s|$)/.test(text);
}

/** Formats a run's virtual time, such as 1:05.5. */
export function runClock(ms: number): string {
  const seconds = ms / 1000;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds - minutes * 60).toFixed(1).padStart(4, "0")}`;
}

/** The console under a running room: trace, variables and controls. The engine runs on the server. */
export class RunPanel {
  readonly element = h("section", { class: "run-panel", "data-testid": "run-panel" });
  private traceList = h("ol", { class: "run-trace", "data-testid": "run-trace" });
  private variables = h("tbody", { "data-testid": "run-variables" });
  private clock = h("span", { class: "run-clock", "data-testid": "run-clock" });
  private controls = h("div", { class: "run-controls" });
  private cursor = 0;
  private paused = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  private busy = false;

  constructor(
    private url: string,
    private onState: (state: RunState) => void,
    private onStop: () => void,
    private currentUser: () => number | null,
  ) {
    const command = h("input", {
      class: "run-input",
      placeholder: T.commandPlaceholder,
      "aria-label": T.commandPlaceholder,
      maxlength: 200,
      "data-testid": "run-command",
    });
    const form = h(
      "form",
      { class: "run-form" },
      command,
      h(
        "button",
        { class: "btn btn-icon", "aria-label": T.send, title: T.send, type: "submit" },
        icon(Send),
      ),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const text = command.value.trim();
      if (!text) return;
      command.value = "";
      void this.submit(text);
    });
    replace(
      this.element,
      h("div", { class: "run-head" }, this.clock, this.controls),
      h(
        "div",
        { class: "run-columns" },
        this.traceList,
        h(
          "div",
          { class: "run-vars" },
          h(
            "table",
            { class: "table" },
            h(
              "thead",
              {},
              h("tr", {}, h("th", {}, T.variable), h("th", {}, T.holder), h("th", {}, T.value)),
            ),
            this.variables,
          ),
        ),
        h(
          "div",
          { class: "run-built-ins" },
          h("h4", {}, T.builtIns),
          h("table", { class: "table", "data-testid": "run-built-ins" }, this.builtIns),
        ),
      ),
      form,
    );
  }

  async start(): Promise<void> {
    this.apply(await post<RunState>(this.url, {}));
    this.timer = setInterval(() => void this.tick(), TICK_MS);
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    void request("DELETE", this.url).catch(() => {});
  }

  private async tick(): Promise<void> {
    if (this.busy || this.paused) return;
    await this.call(
      () => post<RunState>(`${this.url}/advance?since=${this.cursor}`, { ms: TICK_MS }),
      true,
    );
  }

  /** Sends something a user did, such as stepping onto a tile or saying something. */
  input(entry: Record<string, unknown>): Promise<void> {
    return this.call(() => post<RunState>(`${this.url}/input?since=${this.cursor}`, entry));
  }

  private async submit(text: string): Promise<void> {
    if (isDebugCommand(text)) {
      await this.command(text);
      return;
    }
    const user = this.currentUser();
    if (user === null) {
      toast(T.pickUserToSpeak, "error");
      return;
    }
    await this.input({ type: "say", user, text });
  }

  private async command(text: string): Promise<void> {
    await this.call(async () => {
      const state = await post<RunState>(`${this.url}/command?since=${this.cursor}`, { text });
      this.addLine(state.now_ms, "answer", state.answer ?? "");
      return state;
    });
  }

  private async call(run: () => Promise<RunState>, background = false): Promise<void> {
    this.busy = true;
    try {
      this.apply(await run());
    } catch (error) {
      // Being told to slow down is no reason to end the run. The next tick tries again.
      if (error instanceof ApiFailure && error.status === 429) {
        if (!background) toast(errorMessage(error), "error");
        return;
      }
      toast(errorMessage(error), "error");
      if (this.timer !== null) {
        clearInterval(this.timer);
        this.timer = null;
      }
    } finally {
      this.busy = false;
    }
  }

  private apply(state: RunState): void {
    if (this.stopped) return; // A late answer must not move things in the room Stop just put back.
    this.cursor = state.trace_next;
    this.paused = state.paused;
    this.clock.textContent = runClock(state.now_ms);
    for (const line of state.trace) this.addLine(line.at_ms, line.kind, line.message);
    void this.refreshBuiltIns();
    // The table is rebuilt on every tick, which would throw away a value being typed.
    if (!this.editingValue) this.renderVariables(state);
    this.game = state.game;
    this.renderControls();
    this.onState(state);
  }

  /** Which holder the built-in table shows. Null means the room itself. */
  inspect(target: "furni" | "user" | null, holder: number | null): void {
    this.inspected = target === null ? null : { target, holder };
  }

  private async refreshBuiltIns(): Promise<void> {
    const shown = this.inspected;
    const query = shown ? `target=${shown.target}&holder=${shown.holder}` : "target=global";
    const rows = await get<{ name: string; value: string }[]>(
      `${this.url}/built-ins?${query}`,
    ).catch(() => null);
    if (!rows || this.stopped) return;
    replace(
      this.builtIns,
      ...rows.map((row) =>
        h("tr", {}, h("td", {}, h("code", {}, row.name)), h("td", {}, row.value)),
      ),
    );
  }

  private renderVariables(state: RunState): void {
    replace(
      this.variables,
      ...state.variables.map((row) =>
        h(
          "tr",
          {},
          h("td", {}, h("code", {}, row.variable)),
          h("td", {}, this.holderName(state, row.holder)),
          this.valueCell(row),
        ),
      ),
      ...state.defined_variables.map((row) =>
        h(
          "tr",
          {},
          h("td", {}, h("code", {}, row.variable)),
          h("td", {}, row.scope === "context" ? T.duringRun : T.nobodyYet),
          h("td", {}),
        ),
      ),
    );
  }

  private valueCell(row: RunState["variables"][number]): HTMLElement {
    const cell = h("td", { class: "run-value", title: T.editValueHint }, row.value);
    cell.addEventListener("dblclick", () => this.editValue(cell, row));
    return cell;
  }

  /** Enter or leaving the field saves the value, and Escape puts it back. */
  private editValue(cell: HTMLElement, row: RunState["variables"][number]): void {
    if (this.editingValue) return;
    this.editingValue = true;
    const field = h("input", {
      value: row.value,
      inputmode: "numeric",
      "aria-label": T.editValue(row.variable),
    }) as HTMLInputElement;
    let done = false;
    const finish = (save: boolean) => {
      if (done) return;
      done = true;
      this.editingValue = false;
      const value = field.value.trim();
      if (!save || value === row.value) {
        void this.tick();
        return;
      }
      if (!INT64_TEXT.test(value)) {
        toast(T.badValue, "error");
        void this.tick();
        return;
      }
      void this.input({ type: "set_value", variable: row.variable, key: row.holder, value });
    };
    field.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Enter") finish(true);
      if (event.key === "Escape") finish(false);
    });
    field.addEventListener("blur", () => finish(true));
    replace(cell, field);
    field.focus();
    field.select();
  }

  private holderName(state: RunState, holder: string): string {
    const [scope, id] = holder.split(":");
    if (scope === "user") return state.users.find((u) => String(u.id) === id)?.name ?? holder;
    return holder;
  }

  private addLine(at: number, kind: string, message: string): void {
    this.traceList.append(
      h(
        "li",
        { class: `trace-line trace-${kind}` },
        h("span", { class: "trace-time" }, runClock(at)),
        h("span", { class: "trace-text" }, message),
      ),
    );
    while (this.traceList.childElementCount > TRACE_SHOWN)
      this.traceList.firstElementChild?.remove();
    this.traceList.scrollTop = this.traceList.scrollHeight;
  }

  private game: RunState["game"] | null = null;
  private editingValue = false;
  private inspected: { target: "furni" | "user"; holder: number | null } | null = null;
  private builtIns = h("tbody");
  private stopped = false;

  private renderControls(): void {
    const button = (label: string, node: Parameters<typeof icon>[0], run: () => void) =>
      h("button", { class: "btn btn-small", onclick: run }, icon(node, 14), label);
    replace(
      this.controls,
      this.paused
        ? button(T.resume, Play, () => void this.command(":resume"))
        : button(T.pause, Pause, () => void this.command(":pause")),
      button(T.step, SkipForward, () => void this.command(":step")),
      button(T.stop, Square, () => this.onStop()),
      this.game?.running
        ? button(T.endGame, Square, () => void this.input({ type: "game_end" }))
        : button(T.startGame, Play, () => void this.input({ type: "game_start" })),
      h(
        "span",
        { class: "muted", "data-testid": "game-scores" },
        T.gameScores(this.game?.running ?? false, this.game?.scores ?? {}),
      ),
    );
  }
}

let boxCatalogue: Promise<BoxCatalogue> | null = null;

export function loadBoxCatalogue(): Promise<BoxCatalogue> {
  boxCatalogue ??= get<BoxCatalogue>("/api/engine/boxes");
  return boxCatalogue;
}
