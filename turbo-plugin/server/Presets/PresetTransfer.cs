using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Hotel;
using Turbo.Primitives.Messages.Outgoing.Room.Session;
using Turbo.Primitives.Players;
using Turbo.Primitives.Rooms;
using Turbo.Primitives.Rooms.Enums.Wired;
using Turbo.Primitives.Rooms.Snapshots.Furniture;
using Turbo.Primitives.Rooms.Snapshots.Wired;
using Turbo.Primitives.Rooms.Wired.Variable;

namespace Wiredbench.Presets;

/// <summary>What an import did: the room it went into (null when it did not start) and a report for the player.</summary>
public sealed record PresetImportResult(int? RoomId, string Message);

/// <summary>
/// G-Presets files into rooms and rooms into files, through the hotel's own paths only: furni are
/// taken from the player's inventory (or made, for players who may give furni) and placed as the
/// player would place them, and each box is saved as the player saving it in its editor, so the
/// room's rights, limits, placement policies and every box's checks decide what goes in.
/// </summary>
public sealed class PresetTransfer(IHotel hotel, PresetLibrary library)
{
    /// <summary>Who may have furni made for an import: whoever may give furni with the hotel's own command.</summary>
    private const string MAKE_PERMISSION = "command.giveitem";

    private const string MAKE_CAUSE = "wiredbench.preset";

    /// <summary>A new room starts from this model; the file's floor plan is then saved over it.</summary>
    private const string BASE_MODEL = "model_a";

    private const int NEW_ROOM_PLAYERS_MAX = 25;

    // How long an import into a new room waits for the player to arrive in it.
    private static readonly TimeSpan ARRIVAL_WAIT = TimeSpan.FromSeconds(20);
    private static readonly TimeSpan ARRIVAL_POLL = TimeSpan.FromMilliseconds(250);

    // The longest a whole import into a new room may take, the wait for arrival included.
    private static readonly TimeSpan NEW_ROOM_LIMIT = TimeSpan.FromMinutes(2);

    private readonly ConcurrentDictionary<PlayerId, byte> _newRoomRunning = new();

    /// <summary>
    /// An import into a new room, started and left running: this returns at once, with the task
    /// that finishes it. It must not be waited for in a message handler. The import waits for the
    /// player to arrive in the room, and the client only enters the room after the server has
    /// answered its "open this room" packet, which waits behind the handler of the message that
    /// asked for the import: waited for there, the player never arrives and the import gave up
    /// after the full wait with an empty room. <paramref name="report"/> gets the message for the
    /// player when it is over, however it ended.
    /// </summary>
    public Task StartNewRoomImport(
        PlayerId player,
        string json,
        string roomName,
        Func<string, CancellationToken, Task> report
    )
    {
        if (!_newRoomRunning.TryAdd(player, 0))
            return report("An import into a new room is already running.", CancellationToken.None);

        return Task.Run(async () =>
        {
            string message;

            try
            {
                using var limit = new CancellationTokenSource(NEW_ROOM_LIMIT);

                message = (await ImportAsync(player, json, true, roomName, limit.Token).ConfigureAwait(false)).Message;
            }
            catch (OperationCanceledException)
            {
                message = "The import took too long and was stopped; check the new room in your navigator.";
            }
            catch (Exception)
            {
                message = "The import failed; check the new room in your navigator.";
            }
            finally
            {
                _newRoomRunning.TryRemove(player, out _);
            }

            try
            {
                await report(message, CancellationToken.None).ConfigureAwait(false);
            }
            catch (Exception)
            {
                // The player left: nobody to tell.
            }
        });
    }

    /// <summary>
    /// Imports a file into the room the player is in, or a new room (<paramref name="newRoom"/>).
    /// With an <paramref name="anchor"/> tile (the root G-Presets asks its user to click), each
    /// furni goes on its tile in the file plus the root, keeping its height, so the file's (0, 0)
    /// lands there; without one they go on the file's own tiles.
    /// </summary>
    public async Task<PresetImportResult> ImportAsync(
        PlayerId player,
        string json,
        bool newRoom,
        string roomName,
        CancellationToken ct,
        (int X, int Y)? anchor = null
    )
    {
        GPresetFile file;

        try
        {
            file = GPresetFile.Parse(json);
        }
        catch (GPresetException ex)
        {
            return new(null, ex.Message);
        }

        if (file.Furni.IsEmpty)
            return new(null, "This preset holds wired settings only, with no furni to place.");

        // G-Presets' root: each furni (and each binding) at its tile in the file plus the root,
        // so the file's (0, 0) lands on the picked tile; a file it exported starts at (0, 0).
        if (anchor is { } at)
        {
            file.Furni = [.. file.Furni.Select(x => x with { X = x.X + at.X, Y = x.Y + at.Y })];
            file.Bindings =
            [
                .. file.Bindings.Select(x =>
                    x with { X = x.X + at.X, Y = x.Y + at.Y }
                ),
            ];
        }

        RoomId room;

        if (newRoom)
        {
            var created = await hotel
                .Rooms.CreateAsync(
                    player,
                    roomName,
                    BASE_MODEL,
                    NEW_ROOM_PLAYERS_MAX,
                    file.FloorPlan.Length > 0 ? file.FloorPlan : null,
                    ct
                )
                .ConfigureAwait(false);

            if (created is null)
                return new(null, "The hotel would not make a room: you may be at your room limit, or the name was refused.");

            room = created.Room;

            await hotel
                .Players.SendAsync(player, new RoomForwardMessageComposer { RoomId = room }, ct)
                .ConfigureAwait(false);

            if (!await ArriveAsync(player, room, ct).ConfigureAwait(false))
                return new(room.Value, $"Room {room.Value} was made; enter it and import the preset again, into this room.");
        }
        else if (await hotel.Players.CurrentRoomAsync(player, ct).ConfigureAwait(false) is { } current)
            room = current;
        else
            return new(null, "Enter a room first.");

        if (await hotel.Rooms.CaptureLayoutAsync(room, player, ct).ConfigureAwait(false) is not { } target)
            return new(room.Value, "You may not change the wired of this room.");

        // G-Presets' heights: a file's are above the lowest floor of what was copied, so they go
        // above the lowest floor of the tiles they land on.
        var floor = FloorUnder(target, file.Furni);

        var report = new List<string>();
        var ids = await ChooseItemsAsync(player, file, report, ct).ConfigureAwait(false);
        var layout = new RoomLayoutSnapshot
        {
            Items =
            [
                .. file
                    .Furni.Where(x => ids.ContainsKey(x.Id))
                    .Select(x => new RoomLayoutItemSnapshot
                    {
                        ItemId = ids[x.Id],
                        X = x.X,
                        Y = x.Y,
                        Z = (int)Math.Round(x.Z * 100) + floor,
                        Rotation = x.Rotation,
                        State = int.TryParse(x.State, NumberStyles.Integer, CultureInfo.InvariantCulture, out var state) ? state : 0,
                    }),
            ],
        };

        await hotel.Rooms.RestoreLayoutAsync(room, player, layout, true, ct).ConfigureAwait(false);

        var inRoom = (await hotel.Rooms.CaptureLayoutAsync(room, player, ct).ConfigureAwait(false))
            ?.Items.Select(x => x.ItemId)
            .ToHashSet() ?? [];
        var placed = ids.Where(x => inRoom.Contains(x.Value)).ToDictionary(x => x.Key, x => x.Value);

        report.Insert(0, $"Placed {placed.Count} of {file.Furni.Length} furni.");

        if (placed.Count < ids.Count)
            report.Add($"{ids.Count - placed.Count} could not be placed (a blocked or missing tile, or the room's limits) and stay in your inventory.");

        await SaveBoxesAsync(room, player, file, placed, report, ct).ConfigureAwait(false);

        return new(room.Value, string.Join(" ", report));
    }

    /// <summary>
    /// Saves the room the player is in to the library as a G-Presets file under
    /// <paramref name="name"/>; the report for the player.
    /// </summary>
    public async Task<string> ExportAsync(PlayerId player, string name, CancellationToken ct)
    {
        if (await hotel.Players.CurrentRoomAsync(player, ct).ConfigureAwait(false) is not { } room)
            return "Enter a room first.";

        if (await hotel.Rooms.CaptureLayoutAsync(room, player, ct).ConfigureAwait(false) is not { } layout)
            return "You may not change the wired of this room.";

        var definitions = (await hotel.Rooms.FurniAsync(room, ct).ConfigureAwait(false)).ToDictionary(
            x => x.ItemId,
            x => x.DefinitionId
        );
        var boxes = await hotel.Wired.ReadBoxesAsync(room, player, ct).ConfigureAwait(false) ?? [];
        var listed = await hotel.Wired.ReadVariablesAsync(room, player, ct).ConfigureAwait(false) ?? [];
        var json = ToFile(layout, definitions, boxes, listed).ToJson();

        try
        {
            var saved = await library.AddAsync(name, json, player.Value, ct).ConfigureAwait(false);

            return $"Saved \"{saved.Name}\" to the library: {saved.FurniCount} furni, {saved.BoxCount} wired boxes.";
        }
        catch (GPresetException ex)
        {
            return ex.Message;
        }
    }

    /// <summary>
    /// An item for each furni of the file: one of the player's own of that furni, else a new one
    /// for a player who may have furni made. File id to item id; what was missing goes in the report.
    /// </summary>
    private async Task<Dictionary<int, int>> ChooseItemsAsync(
        PlayerId player,
        GPresetFile file,
        List<string> report,
        CancellationToken ct
    )
    {
        var owned = (await hotel.Inventory.FurnitureOfAsync(player, ct).ConfigureAwait(false))
            .GroupBy(x => x.DefinitionId)
            .ToDictionary(x => x.Key, x => new Queue<int>(x.Select(y => y.ItemId)));
        var canMake = await hotel.Players.HasPermissionAsync(player, MAKE_PERMISSION, ct).ConfigureAwait(false);
        var ids = new Dictionary<int, int>();
        var missing = new SortedDictionary<string, int>(StringComparer.Ordinal);
        var unknown = new SortedSet<string>(StringComparer.Ordinal);
        var walls = 0;
        var made = 0;

        foreach (var furni in file.Furni)
        {
            if (hotel.Inventory.FindFurniture(furni.ClassName) is not { } definition)
            {
                unknown.Add(furni.ClassName);

                continue;
            }

            if (definition.IsWallItem)
            {
                walls++;

                continue;
            }

            if (owned.TryGetValue(definition.DefinitionId, out var mine) && mine.TryDequeue(out var itemId))
            {
                ids[furni.Id] = itemId;

                continue;
            }

            if (canMake && await hotel.Inventory.GrantFurnitureItemAsync(player, definition.DefinitionId, MAKE_CAUSE, ct).ConfigureAwait(false) is { } newId)
            {
                ids[furni.Id] = newId;
                made++;

                continue;
            }

            missing[furni.ClassName] = missing.GetValueOrDefault(furni.ClassName) + 1;
        }

        if (made > 0)
            report.Add($"Made {made} furni you did not have.");

        if (missing.Count > 0)
            report.Add("Missing from your inventory: " + string.Join(", ", missing.Select(x => $"{x.Value} x {x.Key}")) + ".");

        if (unknown.Count > 0)
            report.Add("This hotel has no furni called: " + string.Join(", ", unknown.Take(10)) + (unknown.Count > 10 ? ", ..." : "") + ".");

        if (walls > 0)
            report.Add($"{walls} wall furni were left out: imports place floor furni only.");

        return ids;
    }

    /// <summary>
    /// Saves the file's boxes onto the placed furni the way G-Presets' importer does: in its
    /// order (variable boxes, then add-ons, those naming no variables first, then conditions,
    /// effects, triggers and selectors), each variable id mapped to this room's by the variable's
    /// name, and a snapshot box saved with its bound furni set as the file binds them.
    /// </summary>
    private async Task SaveBoxesAsync(
        RoomId room,
        PlayerId player,
        GPresetFile file,
        Dictionary<int, int> placed,
        List<string> report,
        CancellationToken ct
    )
    {
        var refusals = new List<string>();
        var lostPicks = 0;
        var saved = 0;
        var unmapped = new SortedSet<string>(StringComparer.Ordinal);
        var variables = new VariableMap(file);
        var references = file
            .Furni.Where(x => x.ClassName == "wf_var_reference")
            .Select(x => x.Id)
            .ToHashSet();
        var bindings = file.Bindings.ToLookup(x => x.WiredId);

        foreach (var box in InSaveOrder(file.Boxes.Where(x => placed.ContainsKey(x.WiredId))))
        {
            // A box naming a variable of the file waits for the room to list it (a variable box
            // is listed from the room's next wired tick), as G-Presets waits for the room's diff.
            var needed = box.VariableIds.Select(VariableMap.Root).Where(variables.IsFileVariable).ToHashSet();

            if (needed.Count > 0 && !variables.Has(needed))
                await WaitForVariablesAsync(room, player, variables, needed, ct).ConfigureAwait(false);

            // A reference variable names a variable of another room: its own id stays.
            if (references.Contains(box.WiredId) && !box.VariableIds.IsEmpty)
                variables.Keep(box.VariableIds[0]);

            var picks = Map(box.Items, placed);
            var picks2 = Map(box.SecondItems, placed);

            lostPicks += (box.Items.Length - picks.Length) + (box.SecondItems.Length - picks2.Length);

            var settings = new WiredBoxSettingsSnapshot
            {
                ItemId = placed[box.WiredId],
                WiredType = WiredType.None,
                WiredCode = 0,
                LogicName = string.Empty,
                IntParams = box.Options,
                StringParam = box.Config,
                StuffIds = picks,
                StuffIds2 = picks2,
                VariableIds = [.. box.VariableIds.Select(id => variables.Correct(id, placed, unmapped))],
                FurniSources = [.. box.FurniSources.Select(x => ImmutableArray.Create(x))],
                UserSources = [.. box.UserSources.Select(x => ImmutableArray.Create(x))],
                Delay = box.Delay,
                Quantifier = box.Quantifier,
                Filter = box.Filter,
                Invert = box.Inverse,
            };

            var result = await SaveWithBindingsAsync(room, player, settings, bindings[box.WiredId], placed, ct)
                .ConfigureAwait(false);

            if (result is { IsSaved: true })
                saved++;
            else
                refusals.Add(file.Furni.FirstOrDefault(x => x.Id == box.WiredId)?.ClassName ?? box.WiredId.ToString(CultureInfo.InvariantCulture));

            // What this box makes may be what the next one names.
            if (box.VariableId.Length > 0)
                await RefreshVariablesAsync(room, player, variables, ct).ConfigureAwait(false);
        }

        report.Add($"Set up {saved} of {file.Boxes.Length} wired boxes.");

        if (refusals.Count > 0)
            report.Add("The hotel refused the settings of: " + string.Join(", ", refusals.Take(10)) + (refusals.Count > 10 ? ", ..." : "") + ".");

        if (lostPicks > 0)
            report.Add($"{lostPicks} picks pointed at furni that were not placed and were left out.");

        if (unmapped.Count > 0)
            report.Add(
                $"{unmapped.Count} variables the file names were not found in this room ("
                    + string.Join(", ", unmapped.Take(5))
                    + "); those slots were left empty."
            );
    }

    /// <summary>G-Presets' save order: what the others name goes first.</summary>
    private static IEnumerable<GPresetBox> InSaveOrder(IEnumerable<GPresetBox> boxes)
    {
        var all = boxes.ToList();

        static bool Names(GPresetBox x) => !x.VariableIds.IsEmpty;

        return all.Where(x => x.Section == "variables" && !Names(x))
            .Concat(all.Where(x => x.Section == "addons" && !Names(x)))
            .Concat(all.Where(x => x.Section == "variables" && Names(x)))
            .Concat(all.Where(x => x.Section == "addons" && Names(x)))
            .Concat(all.Where(x => x.Section == "conditions"))
            .Concat(all.Where(x => x.Section == "effects"))
            .Concat(all.Where(x => x.Section == "triggers"))
            .Concat(all.Where(x => x.Section == "selectors"));
    }

    /// <summary>
    /// Saves a box; a snapshot box with bindings is saved with its bound furni set as bound (a
    /// save takes the box's snapshot from its picked furni as they stand), and they are put back
    /// after, as G-Presets does.
    /// </summary>
    private async Task<Turbo.Primitives.Rooms.Wired.WiredSaveResult?> SaveWithBindingsAsync(
        RoomId room,
        PlayerId player,
        WiredBoxSettingsSnapshot settings,
        IEnumerable<GPresetBinding> bindings,
        Dictionary<int, int> placed,
        CancellationToken ct
    )
    {
        var bound = bindings.Where(x => placed.ContainsKey(x.FurniId)).ToList();

        if (bound.Count == 0)
            return await hotel.Wired.SaveBoxAsync(room, player, settings, ct).ConfigureAwait(false);

        var before = await hotel.Rooms.CaptureLayoutAsync(room, player, ct).ConfigureAwait(false);
        var now = before?.Items.ToDictionary(x => x.ItemId) ?? [];
        var bindLayout = new RoomLayoutSnapshot
        {
            Items =
            [
                .. bound
                    .Where(x => now.ContainsKey(placed[x.FurniId]))
                    .Select(x =>
                    {
                        var at = now[placed[x.FurniId]];

                        return at with
                        {
                            X = x.X ?? at.X,
                            Y = x.Y ?? at.Y,
                            Rotation = x.Rotation ?? at.Rotation,
                            Z = x.Altitude ?? at.Z,
                            State = x.State is { } state && int.TryParse(state, NumberStyles.Integer, CultureInfo.InvariantCulture, out var s) ? s : at.State,
                        };
                    }),
            ],
        };

        await hotel.Rooms.RestoreLayoutAsync(room, player, bindLayout, false, ct).ConfigureAwait(false);

        var result = await hotel.Wired.SaveBoxAsync(room, player, settings, ct).ConfigureAwait(false);

        if (before is not null)
            await hotel
                .Rooms.RestoreLayoutAsync(
                    room,
                    player,
                    new RoomLayoutSnapshot { Items = [.. bindLayout.Items.Select(x => now[x.ItemId])] },
                    false,
                    ct
                )
                .ConfigureAwait(false);

        return result;
    }

    private async Task RefreshVariablesAsync(RoomId room, PlayerId player, VariableMap variables, CancellationToken ct)
    {
        if (await hotel.Wired.ReadVariablesAsync(room, player, ct).ConfigureAwait(false) is { } listed)
            variables.Learn(listed);
    }

    private async Task WaitForVariablesAsync(
        RoomId room,
        PlayerId player,
        VariableMap variables,
        HashSet<string> needed,
        CancellationToken ct
    )
    {
        for (var attempt = 0; attempt < VARIABLE_TRIES; attempt++)
        {
            await RefreshVariablesAsync(room, player, variables, ct).ConfigureAwait(false);

            if (variables.Has(needed))
                return;

            await Task.Delay(VARIABLE_WAIT, hotel.Clock, ct).ConfigureAwait(false);
        }
    }

    // How long a box naming a variable of the file waits for the room to list it (about 5 s, as
    // G-Presets waits for the room's variable diff).
    private const int VARIABLE_TRIES = 20;
    private static readonly TimeSpan VARIABLE_WAIT = TimeSpan.FromMilliseconds(250);

    /// <summary>
    /// The file's variable ids mapped to this room's by name, as G-Presets maps them: a variable of
    /// <c>variables_map</c> and each variable box's own (its text is its name) is found in the
    /// room's list by that name.
    /// </summary>
    private sealed class VariableMap(GPresetFile file)
    {
        private readonly Dictionary<string, string> _real = [];

        // The file's own variables: name to the id the file names it by.
        private readonly Dictionary<string, string> _byName = file
            .VariablesMap.Concat(
                file.Boxes.Where(x => x.VariableId.Length > 0 && x.Config.Length > 0)
                    .Select(x => KeyValuePair.Create(x.Config, x.VariableId))
            )
            .GroupBy(x => x.Key, StringComparer.Ordinal)
            .ToDictionary(x => x.Key, x => x.Last().Value, StringComparer.Ordinal);

        private readonly HashSet<string> _fileIds = [
            .. file.VariablesMap.Values,
            .. file.Boxes.Where(x => x.VariableId.Length > 0).Select(x => x.VariableId),
        ];

        public bool IsFileVariable(string id) => _fileIds.Contains(id);

        public bool Has(IEnumerable<string> ids) => ids.All(_real.ContainsKey);

        public void Keep(string id) => _real[id] = id;

        public void Learn(IEnumerable<HotelWiredVariable> listed)
        {
            foreach (var variable in listed)
            {
                if (_byName.TryGetValue(variable.Name, out var fileId))
                    _real[fileId] = variable.Id;
            }
        }

        /// <summary>The variable a sub-variable id <c>sX-Y[-I]</c> is of (<c>X</c>); any other id itself.</summary>
        public static string Root(string id) =>
            WiredVariableId.TryParseSub(id, out var parent, out _, out _) ? parent : id;

        /// <summary>
        /// G-Presets' rule: <c>0</c>, a built-in <c>-N</c> and a smart <c>~N</c> stay; a
        /// sub-variable <c>sX-Y[-I]</c> takes this room's variable and furni; any other is this room's
        /// variable of that name, or the empty <c>0</c> (<c>n</c>, the client's empty slot, too).
        /// </summary>
        public string Correct(string id, Dictionary<int, int> placed, SortedSet<string> unmapped)
        {
            if (id is "0" || id.StartsWith('-') || id.StartsWith('~'))
                return id;

            if (id.StartsWith('s'))
            {
                if (!WiredVariableId.TryParseSub(id, out var parent, out var addon, out var index))
                {
                    unmapped.Add(id);

                    return "0";
                }

                // The parent as this room names it (a built-in or smart one is the same everywhere),
                // and the add-on as it was placed; the index stays.
                var variable = parent.StartsWith('-') || parent.StartsWith('~') ? parent : _real.GetValueOrDefault(parent, "0");
                var furni = placed.GetValueOrDefault(addon);

                return variable == "0" || furni == 0 ? "0" : WiredVariableId.SubText(variable, furni, index);
            }

            if (_real.TryGetValue(id, out var real))
                return real;

            if (id is not ("n" or ""))
                unmapped.Add(id);

            return "0";
        }
    }

    private static ImmutableArray<int> Map(ImmutableArray<int> fileIds, Dictionary<int, int> placed) =>
        [.. fileIds.Where(placed.ContainsKey).Select(x => placed[x])];

    /// <summary>
    /// A room as G-Presets' exporter writes one: furni numbered from 1 in the order they stand,
    /// tiles relative to the corner of what was taken, the room's user-made variables in
    /// <c>variables_map</c> and each variable box's id by its name, a snapshot box's snapshot as
    /// <c>bindings</c> (its text left empty), and a sub-variable's furni renumbered.
    /// </summary>
    public GPresetFile ToFile(
        RoomLayoutSnapshot layout,
        IReadOnlyDictionary<int, int> definitions,
        IEnumerable<WiredBoxSettingsSnapshot> boxes,
        IEnumerable<HotelWiredVariable> variables
    )
    {
        var furni = layout
            .Items.Where(x => definitions.ContainsKey(x.ItemId))
            .Select(x => (Item: x, Furniture: hotel.Inventory.Furniture(definitions[x.ItemId])))
            .Where(x => x.Furniture is not null)
            .OrderBy(x => x.Item.ItemId)
            .ToList();

        if (furni.Count == 0)
            return GPresetFile.Create(string.Empty, [], []);

        var ids = furni.Select((x, i) => (x.Item.ItemId, Id: i + 1)).ToDictionary(x => x.ItemId, x => x.Id);
        var minX = furni.Min(x => x.Item.X);
        var minY = furni.Min(x => x.Item.Y);
        // G-Presets' heights: above the lowest floor of the area taken.
        var floor = layout.LowestFloorLevel(minX, minY, furni.Max(x => x.Item.X), furni.Max(x => x.Item.Y));
        var created = variables
            .Where(x => x.Type == WiredVariableType.Created)
            .GroupBy(x => x.Name, StringComparer.Ordinal)
            .ToImmutableDictionary(x => x.Key, x => x.First().Id, StringComparer.Ordinal);
        var bindings = new List<GPresetBinding>();
        var fileBoxes = new List<GPresetBox>();
        var boxList = boxes.ToList();
        var subs = SubVariables(layout, boxList, created);

        foreach (var box in boxList.Where(x => ids.ContainsKey(x.ItemId)))
        {
            var wiredId = ids[box.ItemId];
            var config = box.StringParam;

            if (box.SnapshotText.Length > 0)
            {
                bindings.AddRange(ToBindings(box.SnapshotText, wiredId, ids, minX, minY));
                config = string.Empty;
            }

            var fileBox = new GPresetBox(
                box.WiredType switch
                {
                    WiredType.Trigger => "triggers",
                    WiredType.Condition => "conditions",
                    WiredType.Action => "effects",
                    WiredType.Selector => "selectors",
                    WiredType.Addon => "addons",
                    _ => "variables",
                },
                wiredId,
                box.IntParams,
                config,
                [.. box.StuffIds.Where(ids.ContainsKey).Select(x => ids[x])],
                [.. box.StuffIds2.Where(ids.ContainsKey).Select(x => ids[x])],
                [.. box.FurniSources.Select(x => x.IsEmpty ? 0 : x[0])],
                [.. box.UserSources.Select(x => x.IsEmpty ? 0 : x[0])],
                [.. box.VariableIds.Select(id => ToFileVariableId(id, ids, subs))],
                box.Delay,
                box.Quantifier,
                box.Filter,
                box.Invert,
                box.WiredType == WiredType.Variable
                    ? created.GetValueOrDefault(box.StringParam, WiredVariableId.OfBox(box.ItemId).ToString())
                    : string.Empty
            );

            fileBoxes.Add(fileBox);
        }

        var file = GPresetFile.Create(
            string.Empty,
            furni.Select(x => new GPresetFurni(
                ids[x.Item.ItemId],
                x.Furniture!.Name,
                x.Item.X - minX,
                x.Item.Y - minY,
                Math.Max(0, x.Item.Z - floor) / 100.0,
                x.Item.Rotation,
                x.Item.State.ToString(CultureInfo.InvariantCulture)
            )),
            fileBoxes
        );

        file.Bindings = [.. bindings];
        file.VariablesMap = created;

        return file;
    }

    /// <summary>
    /// A snapshot box's text ("id,state,rotation,x,y,altitude" per furni, "N" for a part it
    /// leaves out) as G-Presets' bindings, for the furni that are in the file.
    /// </summary>
    private static IEnumerable<GPresetBinding> ToBindings(
        string snapshot,
        int wiredId,
        Dictionary<int, int> ids,
        int minX,
        int minY
    )
    {
        static int? Part(string[] fields, int index) =>
            index < fields.Length && int.TryParse(fields[index], NumberStyles.Integer, CultureInfo.InvariantCulture, out var n) ? n : null;

        foreach (var entry in snapshot.Split(';', StringSplitOptions.RemoveEmptyEntries))
        {
            var fields = entry.Split(',');

            if (Part(fields, 0) is not { } itemId || !ids.TryGetValue(itemId, out var furniId))
                continue;

            var x = Part(fields, 3);
            var y = Part(fields, 4);

            yield return new GPresetBinding(
                furniId,
                wiredId,
                x is null || y is null ? null : x - minX,
                x is null || y is null ? null : y - minY,
                Part(fields, 2),
                fields.Length > 1 && fields[1] != "N" ? fields[1] : null,
                Part(fields, 5)
            );
        }
    }

    /// <summary>
    /// The lowest floor level, in hundredths, under the area <paramref name="furni"/> cover in
    /// <paramref name="layout"/>'s room: what G-Presets measures a copy's heights from.
    /// </summary>
    public static int FloorUnder(RoomLayoutSnapshot layout, IEnumerable<GPresetFurni> furni)
    {
        var list = furni.ToList();

        return list.Count == 0
            ? 0
            : layout.LowestFloorLevel(list.Min(x => x.X), list.Min(x => x.Y), list.Max(x => x.X), list.Max(x => x.Y));
    }

    /// <summary>
    /// A variable id as the file writes it: this room's sub-variable (an add-on's
    /// <c>OfBox(addon, index)</c>) as G-Presets' <c>s&lt;parent&gt;-&lt;add-on&gt;[-&lt;index&gt;]</c>
    /// with the add-on numbered as the file numbers it; any other id as it is.
    /// </summary>
    private static string ToFileVariableId(string id, Dictionary<int, int> ids, IReadOnlyDictionary<string, (string Parent, int Addon, int Index)> subs)
    {
        if (subs.TryGetValue(id, out var sub))
            return ids.TryGetValue(sub.Addon, out var addon) ? WiredVariableId.SubText(sub.Parent, addon, sub.Index) : "0";

        return WiredVariableId.TryParseSub(id, out var parent, out var furni, out var index) && ids.TryGetValue(furni, out var renumbered)
            ? WiredVariableId.SubText(parent, renumbered, index)
            : id;
    }

    // An add-on derives at most this many sub-variables (the level-up add-on's mask is a byte's worth or so).
    private const int MAX_SUB_VARIABLES = 16;

    /// <summary>
    /// This room's sub-variables, by the id boxes name them with: each add-on's
    /// <c>OfBox(addon, index)</c>, with the file id of the variable box on the add-on's tile.
    /// </summary>
    private static Dictionary<string, (string Parent, int Addon, int Index)> SubVariables(
        RoomLayoutSnapshot layout,
        IReadOnlyList<WiredBoxSettingsSnapshot> boxes,
        IReadOnlyDictionary<string, string> created
    )
    {
        var at = layout.Items.ToDictionary(x => x.ItemId, x => (x.X, x.Y));
        var variableBoxes = boxes.Where(x => x.WiredType == WiredType.Variable && at.ContainsKey(x.ItemId)).ToList();
        var subs = new Dictionary<string, (string, int, int)>(StringComparer.Ordinal);

        foreach (var addon in boxes.Where(x => x.WiredType == WiredType.Addon && at.ContainsKey(x.ItemId)))
        {
            var parent = variableBoxes.FirstOrDefault(x => at[x.ItemId] == at[addon.ItemId]);

            if (parent is null)
                continue;

            var parentId = created.GetValueOrDefault(parent.StringParam, WiredVariableId.OfBox(parent.ItemId).ToString());

            for (var index = 0; index < MAX_SUB_VARIABLES; index++)
                subs[WiredVariableId.OfBox(addon.ItemId, index).ToString()] = (parentId, addon.ItemId, index);
        }

        return subs;
    }

    private async Task<bool> ArriveAsync(PlayerId player, RoomId room, CancellationToken ct)
    {
        var until = hotel.Clock.GetUtcNow() + ARRIVAL_WAIT;

        while (hotel.Clock.GetUtcNow() < until)
        {
            // In the room for the room's own sake, not just recorded as heading there: the
            // layout calls answer nothing for a room no one is in yet, which an import into a
            // new room read as a refusal and left the room empty.
            if (
                await hotel.Players.CurrentRoomAsync(player, ct).ConfigureAwait(false) == room
                && (await hotel.Rooms.PlayersAsync(room, ct).ConfigureAwait(false)).Contains(player)
            )
                return true;

            await Task.Delay(ARRIVAL_POLL, hotel.Clock, ct).ConfigureAwait(false);
        }

        return false;
    }
}
