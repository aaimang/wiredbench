# Wiredbench plugin changelog

Every change to `turbo-plugin/` raises `manifest.json`'s `Version` and adds its heading here
(`python scripts/plugin_version.py --bump patch`; CI runs `--check`). The client module shows the
version the server sends, so a player sees the plugin they are talking to.

## 0.2.0 (2026-11-12)

- Windows: icons and headers, tooltips on every button, red for delete or stop, green for run
  or place. Wiredbench shows "Version x, connected as name (id)".
- Wired trace: "Tracing room : id name", and each step's time in the room's time zone.
- Presets: delete (twice to confirm), refresh, and new presets appear on their own.
- Sandbox: sections for the room layout and wired kits, with what Save and Reset do.
- Panel: page icons; G-Presets upload a .json file, rename a preset or replace its file;
  Wiredbench shows WIRED use across loaded rooms (boxes, stacks, usage, executions, running
  time, errors) with a room filter.
- `:copy <name> <hotel>` wears a Habbo user's look from that hotel (COM when left out) and keeps it
  in the wardrobe, as worn: the outfit shows without logging in again.

## 0.1.0 (2026-11-11)

- Wired trace, sandbox rooms (save, reset, kits), G-Presets import and export, parity report.
