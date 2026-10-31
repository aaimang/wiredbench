import type { Settings } from "./api";

export const state: { settings: Settings | null; username: string } = {
  settings: null,
  username: "",
};

const THEME_KEY = "wb-theme";

export function applyTheme(theme: string): void {
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage can be blocked. The theme still applies for this page.
  }
}

/** Applies the last theme straight away, so a dark-mode user does not see a light flash. */
export function restoreTheme(): void {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) applyTheme(saved);
  } catch {
    // Storage can be blocked. The server's value is applied after login.
  }
}
