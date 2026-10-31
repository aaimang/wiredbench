import {
  Copy,
  Download,
  FileOutput,
  Folder as FolderIcon,
  FolderInput,
  FolderPlus,
  Layers,
  Pencil,
  Plus,
  Trash2,
  Upload,
} from "lucide";
import {
  del,
  type Folder,
  get,
  patch,
  post,
  type Sandbox,
  type TrashEntry,
  type Tree,
} from "./api";
import { h, icon, replace } from "./dom";
import {
  descendantIds,
  flattenFolders,
  folderPath,
  formatDate,
  hotelLabel,
  timeAgo,
} from "./format";
import { state } from "./state";
import { t } from "./strings";
import { act, confirmDialog, errorMessage, formDialog, openDialog, toast } from "./ui";

const T = t.workspace;

interface ImportReport {
  furni?: number;
  boxes?: number;
  not_placed?: number;
  not_simulated?: Record<string, number>;
  warnings: string[];
}

interface ExportResult {
  filename: string;
  file: unknown;
  report: {
    shopping_list: { classname: string; name: string; count: number }[];
    warnings: string[];
  };
}

class WbWorkspace extends HTMLElement {
  private tree: Tree = { folders: [], sandboxes: [] };
  private currentFolder: number | null = null;
  private showTrash = false;
  private trash: TrashEntry[] = [];
  private openSandbox: Sandbox | null = null;
  private sidebar = h("nav", { class: "folder-tree", "aria-label": T.title });
  private main = h("div", { class: "workspace-main" });

  connectedCallback(): void {
    replace(this, h("div", { class: "workspace-body" }, this.sidebar, this.main));
    void this.reload();
  }

  private async reload(): Promise<void> {
    try {
      this.tree = await get<Tree>("/api/workspace/tree");
      if (this.showTrash) this.trash = await get<TrashEntry[]>("/api/trash");
      if (!this.tree.folders.some((folder) => folder.id === this.currentFolder)) {
        this.currentFolder = null;
      }
      if (this.openSandbox) {
        const id = this.openSandbox.id;
        this.openSandbox = this.tree.sandboxes.find((sandbox) => sandbox.id === id) ?? null;
      }
    } catch (error) {
      toast(errorMessage(error), "error");
    }
    this.render();
  }

  private render(): void {
    this.renderSidebar();
    if (this.showTrash) this.renderTrash();
    else if (this.openSandbox) void this.renderSandbox(this.openSandbox);
    else this.renderFolder();
  }

  private renderSidebar(): void {
    const entry = (label: string, node: Node, active: boolean, depth: number, go: () => void) =>
      h(
        "button",
        {
          class: `tree-item tree-depth-${Math.min(depth, 6)}`,
          "aria-current": active ? "true" : null,
          onclick: go,
        },
        node,
        h("span", { class: "tree-label" }, label),
      );
    const go = (folder: number | null) => () => {
      this.currentFolder = folder;
      this.showTrash = false;
      this.openSandbox = null;
      this.render();
    };
    const inFolder = !this.showTrash && !this.openSandbox;
    replace(
      this.sidebar,
      entry(T.root, icon(Layers), inFolder && this.currentFolder === null, 0, go(null)),
      ...flattenFolders(this.tree.folders).map((folder) =>
        entry(
          folder.name,
          icon(FolderIcon),
          inFolder && this.currentFolder === folder.id,
          folder.depth + 1,
          go(folder.id),
        ),
      ),
      h("div", { class: "toolbar-spacer" }),
      entry(T.trash, icon(Trash2), this.showTrash, 0, () => {
        this.showTrash = true;
        this.openSandbox = null;
        void this.reload();
      }),
    );
  }

  private renderFolder(): void {
    const folders = this.tree.folders.filter((f) => f.parent_id === this.currentFolder);
    const sandboxes = this.tree.sandboxes.filter((s) => s.folder_id === this.currentFolder);
    const crumbs = folderPath(this.tree.folders, this.currentFolder);
    const empty = !folders.length && !sandboxes.length;
    replace(
      this.main,
      h(
        "div",
        { class: "toolbar" },
        h("h1", { class: "crumbs" }, [T.root, ...crumbs.map((c) => c.name)].join(" / ")),
        h("div", { class: "toolbar-spacer" }),
        h(
          "button",
          {
            class: "btn btn-quiet",
            onclick: () =>
              void act(null, async () => {
                const added = await post<Sandbox>("/api/tutorials/time-tracking", {});
                toast(T.created(added.name));
                await this.reload();
              }),
          },
          T.addExample,
        ),
        h(
          "button",
          { class: "btn", onclick: () => this.createFolder() },
          icon(FolderPlus),
          T.newFolder,
        ),
        this.importButton(),
        h(
          "button",
          { class: "btn btn-primary", onclick: () => this.createSandbox() },
          icon(Plus),
          T.newSandbox,
        ),
      ),
      empty
        ? h("div", { class: "empty" }, h("h2", {}, T.empty), h("p", {}, T.emptyHint))
        : h(
            "ul",
            { class: "item-list", "data-testid": "workspace-items" },
            ...folders.map((folder) => this.folderRow(folder)),
            ...sandboxes.map((sandbox) => this.sandboxRow(sandbox)),
          ),
    );
  }

  private actions(...buttons: [string, Parameters<typeof icon>[0], () => void][]): HTMLElement {
    return h(
      "div",
      { class: "row-actions" },
      ...buttons.map(([label, node, run]) =>
        h(
          "button",
          { class: "btn btn-quiet btn-icon", "aria-label": label, title: label, onclick: run },
          icon(node),
        ),
      ),
    );
  }

  private folderRow(folder: Folder): HTMLElement {
    return h(
      "li",
      { class: "item-row" },
      h(
        "button",
        {
          class: "item-open",
          onclick: () => {
            this.currentFolder = folder.id;
            this.render();
          },
        },
        icon(FolderIcon),
        h("span", { class: "item-name" }, folder.name),
      ),
      this.actions(
        [
          T.rename,
          Pencil,
          () => this.rename(folder.name, (name) => patch(`/api/folders/${folder.id}`, { name })),
        ],
        [T.move, FolderInput, () => this.moveFolder(folder)],
        [
          T.delete,
          Trash2,
          () =>
            void act(null, async () => {
              await del(`/api/folders/${folder.id}`);
              toast(T.deleted(folder.name));
              await this.reload();
            }),
        ],
      ),
    );
  }

  private sandboxRow(sandbox: Sandbox): HTMLElement {
    const readOnly = sandbox.kind === "tutorial";
    return h(
      "li",
      { class: "item-row" },
      h(
        "button",
        {
          class: "item-open",
          onclick: () => {
            this.openSandbox = sandbox;
            this.render();
          },
        },
        icon(Layers),
        h("span", { class: "item-name" }, sandbox.name),
        readOnly && h("span", { class: "badge" }, T.tutorial),
        h(
          "span",
          { class: "muted item-meta" },
          `${hotelLabel(sandbox.hotel)}, ${T.updated(timeAgo(sandbox.updated_at))}`,
        ),
      ),
      this.actions(
        ...(readOnly
          ? []
          : ([
              [
                T.rename,
                Pencil,
                () =>
                  this.rename(sandbox.name, (name) =>
                    patch(`/api/sandboxes/${sandbox.id}`, { name }),
                  ),
              ],
              [T.move, FolderInput, () => this.moveSandbox(sandbox)],
            ] as [string, Parameters<typeof icon>[0], () => void][])),
        [
          T.duplicate,
          Copy,
          () =>
            void act(null, async () => {
              const copy = await post<Sandbox>(`/api/sandboxes/${sandbox.id}/duplicate`);
              toast(T.created(copy.name));
              await this.reload();
            }),
        ],
        [T.exportBackup, Download, () => this.exportRoom(sandbox, "native")],
        [T.exportPreset, FileOutput, () => this.exportRoom(sandbox, "gpresets")],
        ...(readOnly
          ? []
          : ([
              [
                T.delete,
                Trash2,
                () =>
                  void act(null, async () => {
                    await del(`/api/sandboxes/${sandbox.id}`);
                    toast(T.deleted(sandbox.name));
                    await this.reload();
                  }),
              ],
            ] as [string, Parameters<typeof icon>[0], () => void][])),
      ),
    );
  }

  private createFolder(): void {
    formDialog(
      T.newFolder,
      [{ name: "name", label: T.name, required: true, maxlength: 120 }],
      T.create,
      async ({ name }) => {
        await post("/api/folders", { name, parent_id: this.currentFolder });
        toast(T.created(name ?? ""));
        await this.reload();
      },
    );
  }

  private importButton(): HTMLElement {
    const input = h("input", {
      type: "file",
      accept: ".json,application/json",
      hidden: true,
      "aria-label": T.importFile,
      "data-testid": "import-file",
    });
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      input.value = "";
      if (file) void act(null, () => this.importRoom(file));
    });
    const button = h(
      "button",
      { class: "btn", onclick: () => input.click() },
      icon(Upload),
      T.importRoom,
    );
    return h("span", {}, input, button);
  }

  private async importRoom(file: File): Promise<void> {
    let parsed: unknown;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      toast(T.notJson, "error");
      return;
    }
    const created = await post<Sandbox & { report: ImportReport }>("/api/import", {
      file: parsed,
      name:
        file.name
          .replace(/\.json$/i, "")
          .replace(/\.wiredbench$/i, "")
          .slice(0, 100) || undefined,
      folder_id: this.currentFolder ?? undefined,
    });
    toast(T.imported(created.name));
    await this.reload();
    const report = created.report;
    const lines = [
      ...(report.furni === undefined ? [] : [T.importSummary(report.furni, report.boxes ?? 0)]),
      ...(Object.keys(report.not_simulated ?? {}).length
        ? [T.importNotSimulated(Object.keys(report.not_simulated ?? {}).length)]
        : []),
      ...(report.not_placed ? [T.importNotPlaced(report.not_placed)] : []),
      ...report.warnings,
    ];
    if (lines.length)
      this.showReport(
        T.importTitle,
        lines.map((line) => h("p", {}, line)),
      );
  }

  private exportRoom(sandbox: Sandbox, format: "native" | "gpresets"): void {
    void act(null, async () => {
      const out = await get<ExportResult>(`/api/sandboxes/${sandbox.id}/export`, { format });
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(out.file, null, 2)], { type: "application/json" }),
      );
      const link = h("a", { href: url, download: out.filename });
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      if (format === "native") {
        toast(T.exportTitle(out.filename));
        return;
      }
      const rows = out.report.shopping_list;
      this.showReport(T.exportTitle(out.filename), [
        h("p", { class: "muted" }, T.exportUntested),
        ...(out.report.warnings.length
          ? [
              h("h3", {}, T.warnings),
              h("ul", {}, ...out.report.warnings.map((w) => h("li", {}, w))),
            ]
          : []),
        ...(rows.length
          ? [
              h("h3", {}, T.shoppingList),
              h(
                "table",
                { class: "table" },
                h("thead", {}, h("tr", {}, h("th", {}, T.furniName), h("th", {}, T.amount))),
                h(
                  "tbody",
                  {},
                  ...rows.map((row) =>
                    h(
                      "tr",
                      {},
                      h("td", {}, row.name || row.classname),
                      h("td", {}, String(row.count)),
                    ),
                  ),
                ),
              ),
            ]
          : []),
      ]);
    });
  }

  private showReport(title: string, body: HTMLElement[]): void {
    const close = h("button", { class: "btn btn-primary", type: "button" }, T.close);
    const dialog = h(
      "dialog",
      { class: "dialog", "data-testid": "exchange-report" },
      h("h2", {}, title),
      ...body,
      close,
    );
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => dialog.remove());
    this.append(dialog);
    openDialog(dialog);
  }

  private createSandbox(): void {
    const hotels = state.settings?.hotels ?? [];
    formDialog(
      T.newSandbox,
      [
        { name: "name", label: T.name, required: true, maxlength: 120 },
        { name: "description", label: T.description, type: "textarea", maxlength: 2000 },
        {
          name: "hotel",
          label: T.hotel,
          type: "select",
          value: state.settings?.default_hotel,
          options: hotels.map((hotel) => ({ value: hotel, label: hotelLabel(hotel) })),
        },
      ],
      T.create,
      async ({ name, description, hotel }) => {
        await post("/api/sandboxes", { name, description, hotel, folder_id: this.currentFolder });
        toast(T.created(name ?? ""));
        await this.reload();
      },
    );
  }

  private rename(current: string, send: (name: string) => Promise<unknown>): void {
    formDialog(
      T.rename,
      [{ name: "name", label: T.name, value: current, required: true, maxlength: 120 }],
      T.save,
      async ({ name }) => {
        await send(name ?? "");
        await this.reload();
      },
    );
  }

  private folderOptions(blocked: Set<number>): { value: string; label: string }[] {
    return [
      { value: "", label: T.root },
      ...flattenFolders(this.tree.folders)
        .filter((folder) => !blocked.has(folder.id))
        .map((folder) => ({
          value: String(folder.id),
          label: `${"  ".repeat(folder.depth + 1)}${folder.name}`,
        })),
    ];
  }

  private moveFolder(folder: Folder): void {
    const options = this.folderOptions(descendantIds(this.tree.folders, folder.id));
    formDialog(
      `${T.move}: ${folder.name}`,
      [
        {
          name: "target",
          label: T.moveTo,
          type: "select",
          value: String(folder.parent_id ?? ""),
          options,
        },
      ],
      T.move,
      async ({ target }) => {
        await patch(`/api/folders/${folder.id}`, { parent_id: target ? Number(target) : null });
        toast(T.moved);
        await this.reload();
      },
    );
  }

  private moveSandbox(sandbox: Sandbox): void {
    formDialog(
      `${T.move}: ${sandbox.name}`,
      [
        {
          name: "target",
          label: T.moveTo,
          type: "select",
          value: String(sandbox.folder_id ?? ""),
          options: this.folderOptions(new Set()),
        },
      ],
      T.move,
      async ({ target }) => {
        await patch(`/api/sandboxes/${sandbox.id}`, { folder_id: target ? Number(target) : null });
        toast(T.moved);
        await this.reload();
      },
    );
  }

  private async renderSandbox(sandbox: Sandbox): Promise<void> {
    const back = h(
      "button",
      {
        class: "btn btn-quiet",
        onclick: () => {
          this.openSandbox = null;
          this.render();
        },
      },
      [T.root, ...folderPath(this.tree.folders, sandbox.folder_id).map((c) => c.name)].join(" / "),
    );
    const history = h("ul", { class: "history" });
    const readOnly = sandbox.kind === "tutorial";
    const edit = h(
      "button",
      {
        class: "btn",
        onclick: () =>
          formDialog(
            T.description,
            [
              {
                name: "description",
                label: T.description,
                type: "textarea",
                value: sandbox.description,
                maxlength: 2000,
              },
            ],
            T.save,
            async ({ description }) => {
              await patch(`/api/sandboxes/${sandbox.id}`, { description });
              toast(T.saved);
              await this.reload();
            },
          ),
      },
      icon(Pencil),
      T.description,
    );
    replace(
      this.main,
      h(
        "div",
        { class: "toolbar" },
        back,
        h("div", { class: "toolbar-spacer" }),
        !readOnly && edit,
      ),
      h(
        "div",
        { class: "sandbox-page" },
        h("h1", {}, sandbox.name),
        sandbox.description && h("p", { class: "prose" }, sandbox.description),
        h(
          "p",
          { class: "muted" },
          `${hotelLabel(sandbox.hotel)}, ${T.revision(sandbox.revision)}, ${T.updated(timeAgo(sandbox.updated_at))}`,
        ),
        h(
          "a",
          { class: "btn btn-primary sandbox-open", href: `/sandbox/${sandbox.id}` },
          T.openRoom,
        ),
        h("h2", {}, T.history),
        history,
      ),
    );
    try {
      const versions = await get<{ revision: number; created_at: string }[]>(
        `/api/sandboxes/${sandbox.id}/versions`,
      );
      replace(
        history,
        ...versions.map((version) => {
          const restore = h("button", { class: "btn btn-small" }, T.restoreVersion);
          restore.addEventListener("click", () => {
            void act(restore, async () => {
              await post(`/api/sandboxes/${sandbox.id}/versions/${version.revision}/restore`);
              toast(T.restored(T.revision(version.revision)));
              await this.reload();
            });
          });
          return h(
            "li",
            {},
            h("span", {}, T.revision(version.revision)),
            h("span", { class: "muted" }, timeAgo(version.created_at)),
            version.revision !== sandbox.revision && !readOnly && restore,
          );
        }),
      );
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  private renderTrash(): void {
    replace(
      this.main,
      h("div", { class: "toolbar" }, h("h1", { class: "crumbs" }, T.trash)),
      this.trash.length === 0
        ? h("div", { class: "empty" }, h("h2", {}, T.trashEmpty), h("p", {}, T.trashNote))
        : h(
            "ul",
            { class: "item-list", "data-testid": "trash-items" },
            ...this.trash.map((entry) => this.trashRow(entry)),
          ),
    );
  }

  private trashRow(entry: TrashEntry): HTMLElement {
    const restore = h("button", { class: "btn btn-small" }, T.restore);
    restore.addEventListener("click", () => {
      void act(restore, async () => {
        await post(`/api/trash/${entry.kind}/${entry.id}/restore`);
        toast(T.restored(entry.name));
        await this.reload();
      });
    });
    const purge = h(
      "button",
      {
        class: "btn btn-small btn-quiet-danger",
        onclick: () =>
          confirmDialog(T.confirmPurge(entry.name), T.purge, async () => {
            await del(`/api/trash/${entry.kind}/${entry.id}`);
            toast(T.purged(entry.name));
            await this.reload();
          }),
      },
      T.purge,
    );
    return h(
      "li",
      { class: "item-row" },
      h(
        "div",
        { class: "item-open item-static" },
        icon(entry.kind === "folder" ? FolderIcon : Layers),
        h("span", { class: "item-name" }, entry.name),
        h("span", { class: "muted item-meta" }, T.purgeAt(formatDate(entry.purge_at))),
      ),
      h("div", { class: "row-actions row-actions-visible" }, restore, purge),
    );
  }
}

customElements.define("wb-workspace", WbWorkspace);
