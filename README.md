# Wiredbench

Build, run and debug Habbo WIRED stacks in a local sandbox, then export them to a real room through G-Presets.

Wiredbench runs on your own computer with one admin login. It downloads Habbo's public furni list
to your machine and never redistributes Habbo's assets.

> **Status: early development.** You can build a room, configure WIRED, run it and reach it through a
> local copy of Habbo's Web API. Neither the engine nor the mock has been fully compared with a real
> room, so behaviour may differ from the game, and import and export are not built. See [PLAN.md](PLAN.md).

Wiredbench is not affiliated with, endorsed, sponsored, or specifically approved by Sulake Oy or its Affiliates. Wiredbench may use the trademarks and other intellectual property of Habbo, which is permitted under Habbo Fan Site Policy.

## What works today

- **Catalogue:** every WIRED box and furni from a hotel's furnidata, searchable and grouped by type,
  with icons. Boxes with no catalogue offer, such as test and prototype boxes, are labelled.
- **Update furnidata:** check Habbo for a new version, review exactly what is new, changed or
  removed, then apply it or keep what you have. Earlier versions can be restored.
- **Room editor:** place, stack, move and rotate floor furni using real Habbo art, with colour
  variants, furni states, undo and redo, and saving by itself.
- **Avatars:** add any Habbo by name and hotel, then click to walk, sit and lie down in Play mode.
- **WIRED engine:** run a room with core triggers, conditions, selectors, effects, add-ons, variables and
  signals. Each box says whether its behaviour is documented or assumed, and others are logged as not
  simulated yet.
- **Debugger:** live trace and variables, pause and step, debug commands, and a time tracking example room.
- **Mock Web API:** a running room answers Habbo's WIRED Web API at `/api/public/rooms/<sandbox ID>`, using
  its own read and write keys, which you generate on the dashboard and which are stored hashed.
- **Dashboard:** runs per box, busiest stacks, signals, errors and limit hits for running rooms. These are
  simulated counts, not hotel performance.
- **View as user:** walk and chat in a room as a visitor. WIRED settings, the trace and variables never
  leave the server, boxes with no catalogue offer are hidden, and every other route is refused.
- **Import and export:** bring in a G-Presets JSON file, and export it again with unknown fields untouched.
  Export also makes a furni list and warns about boxes that may be hard to get. A small exported file has
  worked in a real room, and larger setups are still unproven. A Wiredbench file backs up a room exactly.
- **Guide:** every WIRED box with its official name, purpose, an example and how far its simulation can be
  trusted, plus example rooms you can add to your workspace.
- **Coverage:** [docs/box-coverage.md](docs/box-coverage.md) shows how far each box's options have been checked.
  [docs/box-fields.md](docs/box-fields.md) lists each box's real default options and which are still unnamed.
- **Stack check:** finds stacks that cannot work as built, such as no trigger, missing picks or an undefined
  variable, and leads you to the box.
- **Workspace:** nested folders of sandboxes, with rename, move, duplicate, version history and a
  30-day trash.
- **Settings:** default hotel, theme, automatic update checks, cache limit, engine tick, mock API rate
  limit, log retention, password change and an activity log.

## Start with Docker

```bash
docker compose up --build --detach
```

```bash
docker compose exec wiredbench cat /data/initial-admin-password
```

Open <http://127.0.0.1:8000> and log in as `admin` with that password. Changing your password in
Settings deletes the file.

To use your own initial password, mount a file and set `WB_ADMIN_PASSWORD_FILE` to its path. It only
applies when the admin is first created.

### Lost password

```bash
docker compose exec -it wiredbench /app/.venv/bin/wiredbench reset-password
```

### Other computers

By default only this computer can connect, and that is the safe way to run it. To open it to others,
put it behind an HTTPS reverse proxy, change the `ports` entry in `compose.yaml`, and set
`WB_PUBLIC_URL` to the public address. Requests from a different address are refused, and login
cookies become HTTPS-only. Behind a proxy every visitor shares one rate-limit address, because
forwarded addresses are not trusted.

## Develop

Needs [uv](https://docs.astral.sh/uv/) and Node 24.

```bash
uv sync
```

```bash
npm --prefix frontend install
```

```bash
uv run pre-commit install
```

Run the backend, then the frontend with hot reload in a second terminal. Open
<http://localhost:5173>, and set `WB_PUBLIC_URL=http://localhost:5173` so its requests are accepted.

```bash
WB_PUBLIC_URL=http://localhost:5173 uv run wiredbench serve
```

```bash
npm --prefix frontend run dev
```

Run all the tests:

```bash
uv run pytest --cov
```

```bash
npm --prefix frontend test
```

```bash
npm --prefix frontend run build && npm --prefix frontend run e2e
```

The first browser test run needs `npx playwright install chromium` in `frontend/`.

### Checking the mock API

Run the official Python wrapper against the mock:

```bash
uv run --with wired-api-python==0.1.4 python scripts/wrapper_check.py
```

To record how a real room answers, put `WB_LIVE_CHECK_ROOM_ID`, `WB_LIVE_CHECK_READ_KEY` and
`WB_LIVE_CHECK_WRITE_KEY` in a gitignored `.env`, plus `WB_LIVE_CHECK_HOTEL` if the room is not on
`sandbox` (`com` is the other choice). The script only reads unless you add `--write`, which needs a room
variable named `wb_live_check`. It prints status codes and response shapes, never keys, names or values.

```bash
uv run python scripts/live_check.py --env-file .env
```

### How changes land

1. After the initial commit, each feature or fix gets its own worktree and branch.
2. Pre-commit hooks give fast feedback, including tests. They can be skipped, so CI is the real gate.
3. Pull requests run tests on macOS, Windows and Ubuntu, browser tests, security scans and a Docker
   smoke test.
4. Commits use [Conventional Commits](https://www.conventionalcommits.org). `release-please` proposes
   the next [SemVer](https://semver.org) version and notes. Merging its pull request creates the tag,
   a GitHub release titled with the bare tag, and a container image with an SBOM.

## Configuration

Set these as environment variables, or in a `.env` file during development. This table is generated
from the code, and CI fails if it is out of date.

<!-- generated:env -->
| Variable | Default | Purpose |
|---|---|---|
| `WB_DATA_DIR` | `data` | Folder for the database and caches. |
| `WB_HOST` | `127.0.0.1` | Address the server listens on. |
| `WB_PORT` | `8000` | Port the server listens on. |
| `WB_PUBLIC_URL` | `http://127.0.0.1:8000` | Address people open in the browser. Used for origin and host checks and secure cookies. |
| `WB_ADMIN_USERNAME` | `admin` | Admin login name, used when the admin is first created. |
| `WB_ADMIN_PASSWORD_FILE` |  | File holding the initial admin password. If unset, a password is generated and saved to `<data_dir>/initial-admin-password`. |
| `WB_DEFAULT_HOTEL` | `sandbox` | Hotel selected until changed in Settings. |
| `WB_CACHE_MAX_MB` | `512` | Initial furni asset cache limit, in MB. |
| `WB_SESSION_HOURS` | `168` | Initial login lifetime, in hours. |
| `WB_RATE_LIMIT_LOGIN` | `5` | Failed logins allowed per address per 15 minutes. |
| `WB_RATE_LIMIT_WRITES` | `240` | Write requests allowed per address per minute. |
| `WB_RATE_LIMIT_READS` | `3000` | Read requests allowed per address per minute. |
| `WB_RATE_LIMIT_MOCK` | `600` | Mock Web API requests allowed per address per minute. |
| `WB_TICK_MS` | `500` | Initial WIRED engine tick length, in milliseconds. |
| `WB_AUDIT_DAYS` | `90` | Initial number of days to keep the activity log. |
| `WB_SYNC_COOLDOWN_SECONDS` | `30` | Minimum wait between manual checks per hotel. |
| `WB_MAX_GAMEDATA_MB` | `64` | Largest gamedata download accepted, in MB. |
| `WB_STATIC_DIR` |  | Built frontend folder. Defaults to `frontend/dist`. |
<!-- /generated:env -->

## API

Every route needs an admin login unless listed as public. Writes also need a CSRF token. Tests walk
this list, so a new route is protected by default. There is no interactive API documentation on a
running server.

<!-- generated:api -->
| Method | Path | Access |
|---|---|---|
| GET | `/api/audit` | Admin |
| POST | `/api/auth/login` | Public |
| POST | `/api/auth/logout` | Admin |
| GET | `/api/auth/me` | Admin |
| POST | `/api/auth/password` | Admin |
| DELETE | `/api/auth/view-as` | Admin |
| POST | `/api/auth/view-as` | Admin |
| GET | `/api/avatars/{hotel}/image` | Admin |
| GET | `/api/avatars/{hotel}/lookup` | Admin |
| GET | `/api/cache` | Admin |
| POST | `/api/cache/clear` | Admin |
| POST | `/api/catalog/apply` | Admin |
| GET | `/api/catalog/diff/{from_id}/{to_id}` | Admin |
| POST | `/api/catalog/dismiss` | Admin |
| GET | `/api/catalog/icons/{revision}/{classname}` | Admin |
| GET | `/api/catalog/items` | Admin |
| GET | `/api/catalog/items/{classname}` | Admin |
| POST | `/api/catalog/rollback` | Admin |
| GET | `/api/catalog/status` | Admin |
| POST | `/api/catalog/sync` | Admin |
| GET | `/api/dashboard` | Admin |
| GET | `/api/engine/boxes` | Admin |
| POST | `/api/folders` | Admin |
| DELETE | `/api/folders/{folder_id}` | Admin |
| PATCH | `/api/folders/{folder_id}` | Admin |
| GET | `/api/furni/{revision}/{classname}/atlas` | Admin |
| GET | `/api/furni/{revision}/{classname}/manifest` | Admin |
| GET | `/api/guide` | Admin |
| POST | `/api/import` | Admin |
| GET | `/api/public/rooms/{room_id}/variables` | Public |
| POST | `/api/public/rooms/{room_id}/variables/bulk-delete` | Public |
| GET | `/api/public/rooms/{room_id}/variables/global/{name}` | Public |
| PATCH | `/api/public/rooms/{room_id}/variables/global/{name}` | Public |
| POST | `/api/public/rooms/{room_id}/variables/{scope}/{name}/batch` | Public |
| GET | `/api/public/rooms/{room_id}/variables/{scope}/{name}/{kind}` | Public |
| GET | `/api/public/rooms/{room_id}/variables/{scope}/{name}/{kind}/count` | Public |
| DELETE | `/api/public/rooms/{room_id}/variables/{scope}/{name}/{kind}/{entity}` | Public |
| GET | `/api/public/rooms/{room_id}/variables/{scope}/{name}/{kind}/{entity}` | Public |
| PATCH | `/api/public/rooms/{room_id}/variables/{scope}/{name}/{kind}/{entity}` | Public |
| PUT | `/api/public/rooms/{room_id}/variables/{scope}/{name}/{kind}/{entity}` | Public |
| GET | `/api/public/rooms/{room_id}/variables_profile/furni/{kind}/{entity}` | Public |
| PATCH | `/api/public/rooms/{room_id}/variables_profile/furni/{kind}/{entity}` | Public |
| GET | `/api/public/rooms/{room_id}/variables_profile/global` | Public |
| PATCH | `/api/public/rooms/{room_id}/variables_profile/global` | Public |
| GET | `/api/public/rooms/{room_id}/variables_profile/user/users` | Public |
| DELETE | `/api/public/rooms/{room_id}/variables_profile/user/{kind}/{entity}` | Public |
| GET | `/api/public/rooms/{room_id}/variables_profile/user/{kind}/{entity}` | Public |
| PATCH | `/api/public/rooms/{room_id}/variables_profile/user/{kind}/{entity}` | Public |
| POST | `/api/sandboxes` | Admin |
| DELETE | `/api/sandboxes/{sandbox_id}` | Admin |
| GET | `/api/sandboxes/{sandbox_id}` | Admin |
| PATCH | `/api/sandboxes/{sandbox_id}` | Admin |
| DELETE | `/api/sandboxes/{sandbox_id}/api-keys` | Admin |
| GET | `/api/sandboxes/{sandbox_id}/api-keys` | Admin |
| POST | `/api/sandboxes/{sandbox_id}/api-keys` | Admin |
| GET | `/api/sandboxes/{sandbox_id}/check` | Admin |
| PUT | `/api/sandboxes/{sandbox_id}/document` | Admin |
| POST | `/api/sandboxes/{sandbox_id}/duplicate` | Admin |
| GET | `/api/sandboxes/{sandbox_id}/export` | Admin |
| DELETE | `/api/sandboxes/{sandbox_id}/run` | Admin |
| GET | `/api/sandboxes/{sandbox_id}/run` | Admin |
| POST | `/api/sandboxes/{sandbox_id}/run` | Admin |
| POST | `/api/sandboxes/{sandbox_id}/run/advance` | Admin |
| POST | `/api/sandboxes/{sandbox_id}/run/command` | Admin |
| POST | `/api/sandboxes/{sandbox_id}/run/input` | Admin |
| GET | `/api/sandboxes/{sandbox_id}/versions` | Admin |
| POST | `/api/sandboxes/{sandbox_id}/versions/{revision}/restore` | Admin |
| GET | `/api/settings` | Admin |
| PATCH | `/api/settings` | Admin |
| GET | `/api/trash` | Admin |
| DELETE | `/api/trash/{kind}/{item_id}` | Admin |
| POST | `/api/trash/{kind}/{item_id}/restore` | Admin |
| GET | `/api/tutorials` | Admin |
| POST | `/api/tutorials/{slug}` | Admin |
| GET | `/api/view/sandboxes` | Admin |
| GET | `/api/view/sandboxes/{sandbox_id}` | Admin |
| POST | `/api/view/sandboxes/{sandbox_id}/run` | Admin |
| POST | `/api/view/sandboxes/{sandbox_id}/run/advance` | Admin |
| POST | `/api/view/sandboxes/{sandbox_id}/run/input` | Admin |
| GET | `/api/workspace/tree` | Admin |
| GET | `/healthz` | Public |
<!-- /generated:api -->

## Security

- Passwords use Argon2id. Sessions are random tokens stored hashed, in `HttpOnly`, `SameSite=Strict`
  cookies.
- Every route is denied by default. Writes need a CSRF token and a matching origin, and unknown `Host`
  headers are refused, which blocks DNS rebinding.
- Login, reads and writes are rate limited, and login failures are throttled per address and per
  username.
- Database queries are parameterised. Search wildcards are treated as plain text.
- Outbound requests can only reach a fixed list of Habbo hosts, including after redirects. Downloads
  have size limits and are validated before anything is stored.
- Text from Habbo is always rendered as text, under a strict Content-Security-Policy.

Report a security problem through a private GitHub security advisory on this repository.

## Licence

[MIT](LICENSE). This covers Wiredbench's own code only, not Habbo's data or assets.
