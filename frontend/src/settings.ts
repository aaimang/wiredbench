import { type AuditRow, type CacheInfo, get, patch, post, type Settings } from "./api";
import { h, replace } from "./dom";
import { formatBytes, hotelLabel, timeAgo } from "./format";
import { applyTheme, state } from "./state";
import { t } from "./strings";
import { act, errorMessage, toast } from "./ui";

const T = t.settings;

function select(name: string, value: string, options: [string, string][]): HTMLSelectElement {
  return h(
    "select",
    { id: name, name },
    ...options.map(([option, label]) =>
      h("option", { value: option, selected: option === value }, label),
    ),
  );
}

function field(id: string, label: string, control: HTMLElement, help?: string): HTMLElement {
  return h(
    "div",
    { class: "field" },
    h("label", { for: id }, label),
    control,
    help && h("p", { class: "muted" }, help),
  );
}

class WbSettings extends HTMLElement {
  connectedCallback(): void {
    void this.render();
  }

  private async render(): Promise<void> {
    try {
      const [settings, cache, audit] = await Promise.all([
        get<Settings>("/api/settings"),
        get<CacheInfo>("/api/cache"),
        get<AuditRow[]>("/api/audit"),
      ]);
      replace(
        this,
        h(
          "div",
          { class: "settings-page" },
          h("h1", {}, T.title),
          this.preferences(settings),
          this.cacheSection(cache),
          this.passwordSection(),
          this.activity(audit),
          h("p", { class: "muted" }, T.version(settings.version)),
        ),
      );
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  private preferences(settings: Settings): HTMLElement {
    const form = h(
      "form",
      { class: "settings-section", "aria-labelledby": "general-title" },
      h("h2", { id: "general-title" }, T.general),
      field(
        "default_hotel",
        T.defaultHotel,
        select(
          "default_hotel",
          settings.default_hotel,
          settings.hotels.map((hotel) => [hotel, hotelLabel(hotel)]),
        ),
      ),
      field("theme", T.theme, select("theme", settings.theme, Object.entries(T.themes))),
      field(
        "session_hours",
        T.sessionHours,
        h("input", {
          id: "session_hours",
          name: "session_hours",
          type: "number",
          min: 1,
          max: 720,
          value: settings.session_hours,
        }),
      ),
      h("h2", {}, T.gamedata),
      field(
        "gamedata_check",
        T.gamedataCheck,
        select("gamedata_check", settings.gamedata_check, Object.entries(T.checks)),
        T.gamedataHelp,
      ),
      h("h2", {}, T.cache),
      field(
        "cache_max_mb",
        T.cacheLimit,
        h("input", {
          id: "cache_max_mb",
          name: "cache_max_mb",
          type: "number",
          min: 16,
          max: 102400,
          value: settings.cache_max_mb,
        }),
      ),
      h(
        "label",
        { class: "setting-toggle" },
        h("input", {
          name: "click_outside_cancels",
          type: "checkbox",
          checked: settings.click_outside_cancels,
        }),
        T.clickOutside,
      ),
      h(
        "label",
        { class: "setting-toggle" },
        h("input", {
          name: "pickup_shortcut",
          type: "checkbox",
          checked: settings.pickup_shortcut,
        }),
        T.pickupShortcut,
      ),
      field(
        "tick_ms",
        T.tickMs,
        h("input", {
          id: "tick_ms",
          name: "tick_ms",
          type: "number",
          min: 50,
          max: 5000,
          value: settings.tick_ms,
        }),
        T.tickHelp,
      ),
      field(
        "rate_limit_mock",
        T.mockRate,
        h("input", {
          id: "rate_limit_mock",
          name: "rate_limit_mock",
          type: "number",
          min: 1,
          max: 1000000,
          value: settings.rate_limit_mock,
        }),
      ),
      field(
        "audit_days",
        T.auditDays,
        h("input", {
          id: "audit_days",
          name: "audit_days",
          type: "number",
          min: 1,
          max: 3650,
          value: settings.audit_days,
        }),
      ),
      h("button", { class: "btn btn-primary", type: "submit" }, T.save),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(form).entries());
      const button = form.querySelector<HTMLButtonElement>("button[type=submit]");
      void act(button, async () => {
        const saved = await patch<Settings>("/api/settings", {
          ...values,
          session_hours: Number(values.session_hours),
          cache_max_mb: Number(values.cache_max_mb),
          tick_ms: Number(values.tick_ms),
          rate_limit_mock: Number(values.rate_limit_mock),
          audit_days: Number(values.audit_days),
          click_outside_cancels: "click_outside_cancels" in values,
          pickup_shortcut: "pickup_shortcut" in values,
        });
        state.settings = saved;
        applyTheme(saved.theme);
        toast(T.saved);
        await this.render();
      });
    });
    return form;
  }

  private cacheSection(cache: CacheInfo): HTMLElement {
    const clear = h("button", { class: "btn" }, T.clearCache);
    clear.addEventListener("click", () => {
      void act(clear, async () => {
        const { removed } = await post<{ removed: number }>("/api/cache/clear");
        toast(T.cleared(removed));
        await this.render();
      });
    });
    return h(
      "section",
      { class: "settings-section" },
      h(
        "p",
        { "data-testid": "cache-use" },
        T.cacheUse(formatBytes(cache.assets_bytes), formatBytes(cache.limit_bytes)),
      ),
      h("p", {}, T.cacheGamedata(formatBytes(cache.gamedata_bytes))),
      clear,
      h("p", { class: "muted" }, T.clearHelp),
    );
  }

  private passwordSection(): HTMLElement {
    const current = h("input", {
      id: "current_password",
      name: "current_password",
      type: "password",
      required: true,
      autocomplete: "current-password",
    });
    const next = h("input", {
      id: "new_password",
      name: "new_password",
      type: "password",
      required: true,
      minlength: 12,
      autocomplete: "new-password",
    });
    const form = h(
      "form",
      { class: "settings-section" },
      h("h2", {}, T.password),
      field("current_password", T.currentPassword, current),
      field("new_password", T.newPassword, next),
      h("p", { class: "muted" }, T.passwordSafety),
      h("button", { class: "btn", type: "submit" }, T.changePassword),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void act(form.querySelector("button"), async () => {
        await post("/api/auth/password", {
          current_password: current.value,
          new_password: next.value,
        });
        form.reset();
        toast(T.passwordChanged);
      });
    });
    return form;
  }

  private activity(rows: AuditRow[]): HTMLElement {
    return h(
      "section",
      { class: "settings-section" },
      h("h2", {}, T.activity),
      h(
        "ul",
        { class: "history" },
        ...rows
          .slice(0, 15)
          .map((row) =>
            h(
              "li",
              {},
              h("span", {}, row.action.replaceAll("_", " ")),
              h("span", { class: "muted activity-target" }, row.target),
              h("span", { class: "muted" }, timeAgo(row.at)),
            ),
          ),
      ),
    );
  }
}

customElements.define("wb-settings", WbSettings);
