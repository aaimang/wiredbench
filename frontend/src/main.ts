import "@fontsource-variable/hanken-grotesk/index.css";
import "@fontsource/spline-sans-mono/400.css";
import "./styles.css";
import "./catalogue";
import "./workspace";
import "./settings";
import { Boxes, FolderTree, LogOut, Settings as SettingsIcon } from "lucide";
import {
  ApiFailure,
  get,
  type Me,
  post,
  type Settings,
  setCsrfToken,
  setSignedOutHandler,
} from "./api";
import { h, icon, replace } from "./dom";
import { applyTheme, restoreTheme, state } from "./state";
import { t } from "./strings";
import { act, errorMessage } from "./ui";

const root = document.getElementById("app") as HTMLElement;
const PAGES: Record<string, { tag: string; label: string; node: Parameters<typeof icon>[0] }> = {
  "/catalogue": { tag: "wb-catalogue", label: t.nav.catalogue, node: Boxes },
  "/workspace": { tag: "wb-workspace", label: t.nav.workspace, node: FolderTree },
  "/settings": { tag: "wb-settings", label: t.nav.settings, node: SettingsIcon },
};

function logo(): SVGSVGElement {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 32 32");
  svg.setAttribute("class", "logo");
  svg.setAttribute("aria-hidden", "true");
  const paths: [string, string][] = [
    ["logo-base", "M16 5 30 12.5v7L16 27 2 19.5v-7z"],
    ["logo-top", "M16 7.800 25.800 13 16 18.200 6.200 13z"],
    ["logo-spark", "M10.500 13h5l1.500-2.500 1.500 5 1.300-2.500h2.200"],
  ];
  for (const [name, d] of paths) {
    const path = document.createElementNS(ns, "path");
    path.setAttribute("class", name);
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function navigate(path: string, push = true): void {
  if (push) history.pushState(null, "", path);
  void route();
}

async function route(): Promise<void> {
  if (!state.username) {
    showLogin();
    return;
  }
  const path = location.pathname;
  if (/^\/sandbox\/\d+$/.test(path)) {
    await import("./room/editor"); // Separate chunk, so other pages do not load the renderer.
    showShell("/workspace", "wb-editor");
    return;
  }
  const page = PAGES[path];
  if (!page) {
    navigate("/catalogue");
    return;
  }
  showShell(path, page.tag);
}

function showLogin(): void {
  const username = h("input", {
    id: "username",
    name: "username",
    autocomplete: "username",
    required: true,
    maxlength: 64,
  });
  const password = h("input", {
    id: "password",
    name: "password",
    type: "password",
    autocomplete: "current-password",
    required: true,
  });
  const error = h("p", { class: "form-error", role: "alert", hidden: true });
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, t.login.submit);
  const form = h(
    "form",
    { class: "login-form" },
    h("div", { class: "login-brand" }, logo(), h("span", {}, t.appName)),
    h("h1", {}, t.login.title),
    h("div", { class: "field" }, h("label", { for: "username" }, t.login.username), username),
    h("div", { class: "field" }, h("label", { for: "password" }, t.login.password), password),
    error,
    submit,
    h("p", { class: "muted" }, t.login.firstRun),
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    error.hidden = true;
    submit.disabled = true;
    post<Me>("/api/auth/login", { username: username.value, password: password.value })
      .then(async (me) => {
        await enter(me);
        navigate(location.pathname === "/login" ? "/catalogue" : location.pathname, false);
      })
      .catch((failure: unknown) => {
        error.textContent = errorMessage(failure);
        error.hidden = false;
        password.select();
      })
      .finally(() => {
        submit.disabled = false;
      });
  });
  replace(
    root,
    h(
      "main",
      { class: "login-page" },
      form,
      h("p", { class: "muted login-note" }, t.notAffiliated),
    ),
  );
  username.focus();
}

async function enter(me: Me): Promise<void> {
  setCsrfToken(me.csrf_token);
  state.username = me.username;
  state.settings = await get<Settings>("/api/settings");
  applyTheme(state.settings.theme);
}

function showShell(path: string, tag: string): void {
  const links = Object.entries(PAGES).map(([href, page]) =>
    h(
      "a",
      {
        href,
        class: "nav-link",
        "aria-label": page.label,
        "aria-current": href === path ? "page" : null,
        onclick: ((event: MouseEvent) => {
          if (event.metaKey || event.ctrlKey) return;
          event.preventDefault();
          navigate(href);
        }) as EventListener,
      },
      icon(page.node, 18),
      h("span", {}, page.label),
    ),
  );
  const logout = h(
    "button",
    { class: "nav-link nav-logout", "aria-label": t.nav.logout },
    icon(LogOut, 18),
    h("span", {}, t.nav.logout),
  );
  logout.addEventListener("click", () => {
    void act(logout, async () => {
      await post("/api/auth/logout");
      signedOut();
    });
  });
  replace(
    root,
    h(
      "div",
      { class: "shell" },
      h(
        "header",
        { class: "rail" },
        h("div", { class: "rail-brand" }, logo(), h("span", {}, t.appName)),
        h("nav", { class: "rail-nav", "aria-label": "Main" }, ...links),
        h(
          "div",
          { class: "rail-foot" },
          h("span", { class: "muted rail-user" }, state.username),
          logout,
        ),
      ),
      h("main", { class: "page" }, document.createElement(tag)),
    ),
  );
}

function signedOut(): void {
  state.username = "";
  state.settings = null;
  setCsrfToken("");
  showLogin();
}

async function start(): Promise<void> {
  restoreTheme();
  setSignedOutHandler(signedOut);
  window.addEventListener("popstate", () => void route());
  try {
    await enter(await get<Me>("/api/auth/me"));
  } catch (error) {
    if (!(error instanceof ApiFailure && error.status === 401)) throw error;
  }
  await route();
}

void start();
