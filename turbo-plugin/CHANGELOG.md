# Wiredbench plugin changelog

Every change to `turbo-plugin/` raises `manifest.json`'s `Version` and adds its heading here
(`python scripts/plugin_version.py --bump patch`; CI runs `--check`). The client module shows the
version the server sends, so a player sees the plugin they are talking to.

Releases continue the numbering of Wiredbench's old web app, whose last was v0.11.0: the plugin's
first release is 0.12.0. The 0.2.0 to 0.3.0 headings below were never released on their own.

## 0.13.0 (2026-11-13)

- The Wired trace window can pause the room's wired and step through it. Paused, triggers fire and
  conditions are asked, but each stack's effects are held; Step runs the next one, and Resume runs
  what is held. Needs the `wiredbench-seams` change that adds `IHotelWired.SetPausedAsync`,
  `StepAsync` and `GetPauseAsync`.
- The tutorial rooms' variables now hold a value. They were made without one, so a score or a
  counter had nothing to give or change. A library copy that is still exactly the old file is
  replaced at the next plugin load; one you edited is left as it is.

## 0.12.0 (2026-11-13)

Wiredbench's first release as a Turbo plugin. The web app of v0.11.0 (room editor, Python engine,
WIRED Web API mock) is gone; its parts now live in the plugin, Turbo and its Nitro client.

- Windows in the hotel's own client: Wired trace, Sandbox (save, reset, wired kits), Presets
  (G-Presets import, export and a library with five tutorial rooms) and Check room.
- `:copy <name> <hotel>` wears a Habbo user's look and keeps it in the wardrobe.
- Admin panel pages: WIRED use across loaded rooms, the preset library, and box parity with the
  Habbo client.
- New icons, pixel art in the look of Habbo's WIRED banners: the mark is a cyan W standing on a
  dark WIRED box rimmed in white (`toolbar.png` fills the toolbar's icon slot, `wiredbench.png`
  the windows and the panel), and each tool shows its sign in front of its WIRED box. The tool
  tiles draw them at their full 32 pixels.

## 0.3.0 (2026-11-13)

- Check room: a new window (and Wiredbench tool) finds wired that cannot work as built, without
  running it: picks of furni no longer in the room, a slot or antenna with nothing picked, a
  keyword trigger with no keyword, a stack nothing starts or that does nothing, a selector's or
  signal's targets read without one, a signal no one sends or receives, and a variable no box
  makes. Ported from WiredBench's Python app.
- Tutorials: the old app's five example rooms (switch, signal relay, score counter, visitor view,
  time tracking) are G-Presets files in `data/presets`, added to the library as the plugin loads.

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
