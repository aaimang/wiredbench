using System;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Turbo.Contracts.Plugins;
using Turbo.Contracts.Plugins.Admin;
using Wiredbench.Presets;

namespace Wiredbench;

/// <summary>
/// Wiredbench's pages in the Turbo admin panel. The panel draws them from this schema; no
/// Wiredbench code runs in the panel. Staff need <c>plugin.wiredbench.view</c> to see them, and
/// <c>plugin.wiredbench.presets</c> to add or delete presets.
/// </summary>
public sealed class WiredbenchAdmin(
    PluginManifest manifest,
    PresetLibrary library,
    ParityReport parity,
    WiredUsage usage,
    IPluginFiles files
) : IPluginAdmin
{
    private const int PAGE_SIZE = 50;

    /// <summary>The accept list of the panel's file pickers for a G-Presets file.</summary>
    private static readonly string[] JSON_FILES = [".json", "application/json"];

    public void Configure(IPluginAdminBuilder admin)
    {
        var view = admin.Node("view", "See the Wiredbench pages");
        var presets = admin.Node("presets", "Add and delete G-Presets files in the preset library");

        admin.Map(
            "GET",
            "status",
            view,
            (_, _) =>
                Task.FromResult(
                    PluginAdminResult.Ok(
                        new[]
                        {
                            new { label = "Plugin version", value = manifest.Version },
                            new { label = "Client module", value = "On" },
                        }
                    )
                )
        );

        admin.Map(
            "GET",
            "presets",
            view,
            async (request, ct) =>
            {
                var all = await library.ListAsync(ct);
                var page = request.Query.TryGetValue("page", out var p) && int.TryParse(p, out var n) ? Math.Max(n, 1) : 1;

                return PluginAdminResult.Ok(
                    new
                    {
                        items = all.Skip((page - 1) * PAGE_SIZE)
                            .Take(PAGE_SIZE)
                            .Select(x => new
                            {
                                id = x.Id,
                                name = x.Name,
                                furni = x.FurniCount,
                                boxes = x.BoxCount,
                                savedBy = x.SavedBy,
                                savedAt = x.SavedAt,
                            }),
                        total = all.Count,
                        pageSize = PAGE_SIZE,
                    }
                );
            }
        );

        admin.Map(
            "GET",
            "presets/{id}",
            view,
            async (request, ct) =>
                await FindAsync(request, ct) is { } row
                    ? PluginAdminResult.Ok(
                        new
                        {
                            id = row.Id,
                            name = row.Name,
                            furni = row.FurniCount,
                            boxes = row.BoxCount,
                            savedBy = row.SavedBy,
                            savedAt = row.SavedAt,
                            size = row.Json.Length,
                        }
                    )
                    : PluginAdminResult.NotFound("There is no such preset.")
        );

        admin.Map(
            "GET",
            "presets/{id}/file",
            view,
            async (request, ct) =>
                await FindAsync(request, ct) is { } row
                    ? PluginAdminResult.FileOf(Encoding.UTF8.GetBytes(row.Json), "application/json", FileName(row.Name))
                    : PluginAdminResult.NotFound("There is no such preset.")
        );

        admin.Map(
            "POST",
            "presets",
            presets,
            async (request, ct) =>
            {
                var name = Text(request.Body, "name");
                var json = FirstText(Text(request.Body, "file"), Text(request.Body, "json"));

                try
                {
                    var saved = await library.AddAsync(name, json, request.PlayerId, ct);

                    return PluginAdminResult.Ok(new { id = saved.Id });
                }
                catch (GPresetException ex)
                {
                    return PluginAdminResult.BadRequest(ex.Message);
                }
            }
        );

        admin.Map(
            "PUT",
            "presets/{id}",
            presets,
            async (request, ct) =>
            {
                if (!int.TryParse(request.Route.TryGetValue("id", out var raw) ? raw : null, out var id))
                    return PluginAdminResult.NotFound("There is no such preset.");

                try
                {
                    var saved = await library.UpdateAsync(
                        id,
                        Text(request.Body, "name"),
                        FirstText(Text(request.Body, "file"), Text(request.Body, "json")),
                        ct
                    );

                    return saved is null
                        ? PluginAdminResult.NotFound("There is no such preset.")
                        : PluginAdminResult.Ok(new { id = saved.Id });
                }
                catch (GPresetException ex)
                {
                    return PluginAdminResult.BadRequest(ex.Message);
                }
            }
        );

        admin.Map(
            "DELETE",
            "presets/{id}",
            presets,
            async (request, ct) =>
                int.TryParse((request.Route.TryGetValue("id", out var raw) ? raw : null), out var id) && await library.DeleteAsync(id, ct)
                    ? PluginAdminResult.NoContent()
                    : PluginAdminResult.NotFound("There is no such preset.")
        );

        admin.Map(
            "GET",
            "wired/summary",
            view,
            async (request, ct) =>
                PluginAdminResult.Ok(WiredUsage.Summary(await usage.RoomsAsync(RoomFilter(request), ct)))
        );

        admin.Map(
            "GET",
            "wired/rooms",
            view,
            async (request, ct) =>
            {
                var rows = await usage.RoomsAsync(RoomFilter(request), ct);
                var page = request.Query.TryGetValue("page", out var p) && int.TryParse(p, out var n) ? Math.Max(n, 1) : 1;

                return PluginAdminResult.Ok(
                    new
                    {
                        items = rows.Skip((page - 1) * PAGE_SIZE)
                            .Take(PAGE_SIZE)
                            .Select(x => new
                            {
                                id = x.RoomId,
                                room = x.RoomId,
                                name = x.Name,
                                boxes = x.Boxes,
                                stacks = x.Stacks,
                                usage = $"{x.UsagePercent:0.#}%",
                                heavy = x.Heavy,
                                executions = x.Executions,
                                runTime = WiredUsage.Duration(x.RunMs),
                                average = $"{x.AverageMs:0.##} ms",
                                longest = $"{x.LongestMs} ms",
                                errors = x.Errors,
                                trace = x.TraceOn,
                            }),
                        total = rows.Count,
                        pageSize = PAGE_SIZE,
                    }
                );
            }
        );

        admin.Map("GET", "parity/summary", view, (_, _) => Task.FromResult(PluginAdminResult.Ok(parity.Summary())));

        admin.Map(
            "GET",
            "parity/codes",
            view,
            (request, _) =>
            {
                var kind = request.Query.TryGetValue("kind", out var k) && k != "all" ? k : null;
                var gapsOnly = request.Query.TryGetValue("gaps", out var g) && g is "true" or "1";
                var rows = parity.Rows(kind, gapsOnly);
                var page = request.Query.TryGetValue("page", out var p) && int.TryParse(p, out var n) ? Math.Max(n, 1) : 1;

                return Task.FromResult(
                    PluginAdminResult.Ok(
                        new
                        {
                            items = rows.Skip((page - 1) * PAGE_SIZE)
                                .Take(PAGE_SIZE)
                                .Select(x => new
                                {
                                    id = $"{x.Kind}-{x.Code}",
                                    kind = x.Kind,
                                    code = x.Code,
                                    name = x.Name,
                                    client = x.Client,
                                    editors = x.Editors,
                                    boxes = x.Boxes,
                                    furni = x.Furni,
                                    gaps = x.Gaps,
                                }),
                            total = rows.Count,
                            pageSize = PAGE_SIZE,
                        }
                    )
                );
            }
        );

        var roomFilter = new PluginAdminField("room", "Room id or name", Hint: "Empty for every loaded room");

        admin.Page(
            new PluginAdminPage(
                "overview",
                "Wiredbench",
                view,
                [
                    new PluginAdminBlock(
                        "text",
                        Text: "**Wiredbench** builds and debugs WIRED in this hotel's own client: the "
                            + "Wired trace, sandbox rooms that save and reset, wired kits, and G-Presets "
                            + "files imported into a room or a new one. Its windows are on the client's toolbar."
                    ),
                    new PluginAdminBlock("stats", Title: "Status", Endpoint: "status"),
                    new PluginAdminBlock(
                        "text",
                        Text: "**WIRED across the hotel**: every loaded room with wired, counted from when it "
                            + "loaded. *Usage* is the wired monitor's figure against the room's cap; *running "
                            + "time* is the server time its executions took. Filter by a room id or part of its name."
                    ),
                    new PluginAdminBlock("stats", Title: "WIRED usage, every loaded room", Endpoint: "wired/summary"),
                    new PluginAdminBlock(
                        "table",
                        Title: "Rooms",
                        Endpoint: "wired/rooms",
                        Columns:
                        [
                            new PluginAdminColumn("room", "Room", "number"),
                            new PluginAdminColumn("name", "Name"),
                            new PluginAdminColumn("boxes", "Boxes", "number"),
                            new PluginAdminColumn("stacks", "Stacks", "number"),
                            new PluginAdminColumn("usage", "Usage"),
                            new PluginAdminColumn("heavy", "Heavy", "bool"),
                            new PluginAdminColumn("executions", "Executions", "number"),
                            new PluginAdminColumn("runTime", "Running time"),
                            new PluginAdminColumn("average", "Average"),
                            new PluginAdminColumn("longest", "Longest"),
                            new PluginAdminColumn("errors", "Errors", "number"),
                            new PluginAdminColumn("trace", "Trace on", "bool"),
                        ],
                        Filters: [roomFilter]
                    ),
                ],
                Description: "WIRED sandbox tools and WIRED use across the hotel",
                Icon: IconOf("wiredbench.png")
            )
        );

        admin.Page(
            new PluginAdminPage(
                "presets",
                "G-Presets",
                view,
                [
                    new PluginAdminBlock(
                        "text",
                        Text: "G-Presets files players can import from the **Sandbox** window, into the room "
                            + "they are in or a new one. Upload or paste a file below, or export a room from the "
                            + "Presets window. A file is read as an import reads it before it is kept. An import "
                            + "uses the player's own furni first, and makes the rest only for players who may "
                            + "use **:giveitem**. Open a preset to rename it, replace its file or delete it."
                    ),
                    new PluginAdminBlock(
                        "table",
                        Title: "Library",
                        Endpoint: "presets",
                        Columns:
                        [
                            new PluginAdminColumn("name", "Name"),
                            new PluginAdminColumn("furni", "Furni", "number"),
                            new PluginAdminColumn("boxes", "Wired boxes", "number"),
                            new PluginAdminColumn("savedBy", "Saved by player", "number"),
                            new PluginAdminColumn("savedAt", "Saved", "time"),
                        ],
                        ItemPage: "preset"
                    ),
                    new PluginAdminBlock(
                        "form",
                        Title: "Add a preset",
                        Fields:
                        [
                            new PluginAdminField("name", "Name", Required: true, Max: PresetLibrary.MAX_NAME_LENGTH),
                            new PluginAdminField(
                                "file",
                                "G-Presets file",
                                "file",
                                Options: JSON_FILES,
                                Hint: "A .json file saved by G-Presets or exported from a room."
                            ),
                            new PluginAdminField(
                                "json",
                                "Or paste the file (JSON)",
                                "textarea",
                                Hint: "Used when no file is chosen. Checked before it is kept."
                            ),
                        ],
                        Submit: new PluginAdminAction("Add to library", "POST", "presets", Node: presets)
                    ),
                ],
                Description: "G-Presets files for the Presets window",
                Icon: IconOf("presets.png")
            )
        );

        var kindFilter = new PluginAdminField(
            "kind",
            "Kind",
            "select",
            Options: ["all", "trigger", "action", "condition", "selector", "addon", "variable"]
        );

        admin.Page(
            new PluginAdminPage(
                "parity",
                "Parity",
                view,
                [
                    new PluginAdminBlock(
                        "text",
                        Text: "Every wired code the Habbo client has an editor for, against this hotel's Turbo "
                            + "boxes, the client's nitro-next editors and the hotel's furni. The report is written "
                            + "by **python scripts/parity.py** (with **--swf** for a new client build and "
                            + "**--hotel-db** for the furni) and shows here when the plugin reloads."
                    ),
                    new PluginAdminBlock("stats", Title: "Summary", Endpoint: "parity/summary"),
                    new PluginAdminBlock(
                        "table",
                        Title: "Codes",
                        Endpoint: "parity/codes",
                        Columns:
                        [
                            new PluginAdminColumn("kind", "Kind"),
                            new PluginAdminColumn("code", "Code", "number"),
                            new PluginAdminColumn("name", "Name"),
                            new PluginAdminColumn("client", "In the client", "bool"),
                            new PluginAdminColumn("editors", "Nitro editors", "number"),
                            new PluginAdminColumn("boxes", "Turbo box"),
                            new PluginAdminColumn("furni", "Furni"),
                            new PluginAdminColumn("gaps", "Gaps", "badge"),
                        ],
                        Filters: [kindFilter, new PluginAdminField("gaps", "Only codes with a gap", "bool")]
                    ),
                ],
                Description: "WIRED boxes: client, Turbo, Nitro and furni",
                Icon: IconOf("parity.png")
            )
        );

        admin.Page(
            new PluginAdminPage(
                "preset",
                "G-Preset",
                view,
                [
                    new PluginAdminBlock(
                        "detail",
                        Endpoint: "presets/{id}",
                        Fields:
                        [
                            new PluginAdminField("name", "Name"),
                            new PluginAdminField("furni", "Furni"),
                            new PluginAdminField("boxes", "Wired boxes"),
                            new PluginAdminField("savedBy", "Saved by player"),
                            new PluginAdminField("savedAt", "Saved"),
                            new PluginAdminField("size", "Size (characters)"),
                        ],
                        Downloads: [new PluginAdminAction("Download G-Presets file", "GET", "presets/{id}/file")]
                    ),
                    new PluginAdminBlock(
                        "form",
                        Title: "Change this preset",
                        Fields:
                        [
                            new PluginAdminField("name", "Name", Max: PresetLibrary.MAX_NAME_LENGTH),
                            new PluginAdminField(
                                "file",
                                "Replace the file",
                                "file",
                                Options: JSON_FILES,
                                Hint: "Optional. The new file is checked before it replaces this one."
                            ),
                        ],
                        Submit: new PluginAdminAction("Save changes", "PUT", "presets/{id}", Node: presets)
                    ),
                    new PluginAdminBlock(
                        "actions",
                        Actions:
                        [
                            new PluginAdminAction(
                                "Delete",
                                "DELETE",
                                "presets/{id}",
                                Confirm: "Delete this preset from the library?",
                                Danger: true,
                                Node: presets,
                                Then: "back"
                            ),
                        ]
                    ),
                ],
                Nav: false,
                Icon: IconOf("presets.png")
            )
        );
    }

    private async Task<PresetRow?> FindAsync(PluginAdminRequest request, System.Threading.CancellationToken ct) =>
        int.TryParse((request.Route.TryGetValue("id", out var raw) ? raw : null), out var id) ? await library.GetAsync(id, ct) : null;

    private static string? RoomFilter(PluginAdminRequest request) =>
        request.Query.TryGetValue("room", out var room) ? room : null;

    private static string FirstText(string a, string b) => string.IsNullOrWhiteSpace(a) ? b : a;

    /// <summary>
    /// One of the plugin's pictures (wwwroot) as a data URI, the panel's icon for a page; null,
    /// the panel's plug, when the file is missing.
    /// </summary>
    private string? IconOf(string file)
    {
        using var stream = files.OpenRead($"wwwroot/{file}");

        if (stream is null)
            return null;

        using var bytes = new System.IO.MemoryStream();

        stream.CopyTo(bytes);

        return "data:image/png;base64," + Convert.ToBase64String(bytes.ToArray());
    }

    private static string Text(JsonElement? body, string key) =>
        body is { ValueKind: JsonValueKind.Object } x && x.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;

    /// <summary>The preset's name as a file name: letters, digits, dashes and underscores.</summary>
    private static string FileName(string name)
    {
        var safe = new string([.. name.Select(c => char.IsLetterOrDigit(c) || c is '-' or '_' ? c : '-')]).Trim('-');

        return (safe.Length > 0 ? safe : "preset") + ".json";
    }
}
