using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Wiredbench.Presets;

/// <summary>One furni of a G-Presets file: its id in the file, its class name, tile, height, rotation and state.</summary>
public sealed record GPresetFurni(
    int Id,
    string ClassName,
    int X,
    int Y,
    double Z,
    int Rotation,
    string State
);

/// <summary>
/// One wired box of a G-Presets file, in the file's own terms: <see cref="WiredId"/> is the furni
/// it is, <see cref="Items"/> and <see cref="SecondItems"/> the furni it picked (file ids), each
/// source list one code per slot, and <see cref="VariableIds"/> the variables it names by the
/// file's ids. A variable box's <see cref="VariableId"/> is the id of the variable it makes, which
/// other boxes of the file name it by.
/// </summary>
public sealed record GPresetBox(
    string Section,
    int WiredId,
    ImmutableArray<int> Options,
    string Config,
    ImmutableArray<int> Items,
    ImmutableArray<int> SecondItems,
    ImmutableArray<int> FurniSources,
    ImmutableArray<int> UserSources,
    ImmutableArray<string> VariableIds,
    int Delay,
    int Quantifier,
    bool Filter,
    bool Inverse,
    string VariableId = ""
);

/// <summary>
/// A furni a snapshot box (Match Snapshot, its conditions) is bound to in a G-Presets file: how the
/// furni stood when the box was saved, each part null when the box leaves it out. Its tile is
/// relative to the preset, as the furni's are, and its altitude in hundredths of a tile.
/// </summary>
public sealed record GPresetBinding(
    int FurniId,
    int WiredId,
    int? X,
    int? Y,
    int? Rotation,
    string? State,
    int? Altitude
);

/// <summary>
/// A G-Presets file (the G-Earth extension's room preset JSON). Most of its fields are not
/// documented, so the file is kept as the JSON it was: reading takes out what Wiredbench knows,
/// and writing starts from the original and changes only that, so a field this code cannot read
/// comes back as it was (as WiredBench's Python exchange did).
/// </summary>
public sealed class GPresetFile
{
    /// <summary>The wired sections, in the order the file lists them; G-Presets needs the first three.</summary>
    public static readonly ImmutableArray<string> SECTIONS =
    [
        "triggers",
        "conditions",
        "effects",
        "selectors",
        "addons",
        "variables",
    ];

    /// <summary>The sections G-Presets will not load a file without, even empty.</summary>
    public static readonly ImmutableArray<string> REQUIRED_SECTIONS = ["triggers", "conditions", "effects"];

    private static readonly JsonSerializerOptions WRITE = new() { WriteIndented = true };

    private readonly JsonObject _root;

    // A file Wiredbench made, rather than read: it gets every section G-Presets needs.
    private readonly bool _created;

    private GPresetFile(JsonObject root, bool created = false)
    {
        _root = root;
        _created = created;
    }

    /// <summary>The room's heightmap, rows split by <c>\r</c>; empty when the file has none.</summary>
    public string FloorPlan => _root["floorplan"]?.GetValueKind() == JsonValueKind.String
        ? _root["floorplan"]!.GetValue<string>()
        : string.Empty;

    public ImmutableArray<GPresetFurni> Furni { get; set; } = [];

    public ImmutableArray<GPresetBox> Boxes { get; set; } = [];

    private ImmutableArray<GPresetBinding> _bindings = [];
    private bool _bindingsChanged;

    /// <summary>The snapshot boxes' bindings (<c>bindings</c>); written back only when set.</summary>
    public ImmutableArray<GPresetBinding> Bindings
    {
        get => _bindings;
        set
        {
            _bindings = value;
            _bindingsChanged = true;
        }
    }

    private ImmutableDictionary<string, string> _variablesMap = ImmutableDictionary<string, string>.Empty;
    private bool _variablesMapChanged;

    /// <summary>
    /// The room's own variables by name (<c>wired.variables_map</c>): the id each had in the room
    /// the file was made in, which the file's boxes name it by. Written back only when set.
    /// </summary>
    public ImmutableDictionary<string, string> VariablesMap
    {
        get => _variablesMap;
        set
        {
            _variablesMap = value;
            _variablesMapChanged = true;
        }
    }

    /// <summary>
    /// Reads a file; the problems that stop it being imported are thrown as a
    /// <see cref="GPresetException"/> with a sentence for the player.
    /// </summary>
    public static GPresetFile Parse(string json)
    {
        JsonNode? node;

        try
        {
            node = JsonNode.Parse(json);
        }
        catch (JsonException ex)
        {
            throw new GPresetException($"The file is not JSON: {ex.Message}");
        }

        if (node is not JsonObject root)
            throw new GPresetException("The file is not a G-Presets file: it is not a JSON object.");

        // A wired-only preset (box settings, no furni) has no furni list at all.
        var furni = root["furni"] switch
        {
            JsonArray list => list,
            null when root["wired"] is JsonObject => [],
            _ => throw new GPresetException("The file is not a G-Presets file: it has no furni list."),
        };

        var file = new GPresetFile(root);
        var read = new List<GPresetFurni>();

        foreach (var item in furni)
        {
            if (item is not JsonObject x)
                throw new GPresetException("A furni of the file is not an object.");

            var id = Int(x["id"]) ?? throw new GPresetException("A furni of the file has no id.");
            var className = Text(x["className"]);

            if (className.Length == 0)
                throw new GPresetException($"Furni {id} has no class name.");

            if (x["location"] is not JsonObject at || Int(at["x"]) is not { } fx || Int(at["y"]) is not { } fy)
                throw new GPresetException($"Furni {id} ({className}) has no tile.");

            read.Add(
                new GPresetFurni(
                    id,
                    className,
                    fx,
                    fy,
                    Double(at["z"]) ?? 0,
                    Int(x["rotation"]) ?? 0,
                    Text(x["state"])
                )
            );
        }

        var duplicate = read.GroupBy(x => x.Id).FirstOrDefault(x => x.Count() > 1);

        if (duplicate is not null)
            throw new GPresetException($"Two furni of the file have the id {duplicate.Key}.");

        file.Furni = [.. read];
        file.Boxes = [.. ReadBoxes(root)];
        file._bindings = [.. ReadBindings(root)];
        file._variablesMap = ReadVariablesMap(root);

        return file;
    }

    /// <summary>A new file of these furni and boxes, with every section G-Presets looks for.</summary>
    public static GPresetFile Create(
        string floorPlan,
        IEnumerable<GPresetFurni> furni,
        IEnumerable<GPresetBox> boxes
    )
    {
        var file = new GPresetFile(
            new JsonObject
            {
                ["bindings"] = new JsonArray(),
                ["furni"] = new JsonArray(),
                ["wired"] = new JsonObject(),
            },
            created: true
        );

        // G-Presets writes no floor plan; one is kept only when there is one.
        if (floorPlan.Length > 0)
            file._root["floorplan"] = floorPlan;

        file.Furni = [.. furni];
        file.Boxes = [.. boxes];

        return file;
    }

    /// <summary>
    /// The file as JSON: the original's fields, with the furni and boxes written over the entries
    /// they came from (matched by id) and new ones added.
    /// </summary>
    public string ToJson()
    {
        var root = _root.DeepClone().AsObject();
        var oldFurni = (root["furni"] as JsonArray ?? [])
            .OfType<JsonObject>()
            .Where(x => Int(x["id"]) is not null)
            .GroupBy(x => Int(x["id"])!.Value)
            .ToDictionary(x => x.Key, x => x.First());
        var furni = new JsonArray();

        foreach (var item in Furni)
        {
            var x = oldFurni.TryGetValue(item.Id, out var old)
                ? old.DeepClone().AsObject()
                : new JsonObject { ["name"] = $"{item.ClassName}[{item.Id}]" };

            x["id"] = item.Id;
            x["className"] = item.ClassName;
            // A furni the file did not have gets every field G-Presets reads (rotation and z
            // are required there); one it had keeps the fields it had.
            var isNewFurni = old is null;

            Set(x, "rotation", item.Rotation, item.Rotation == 0 && !isNewFurni);
            Set(x, "state", item.State, item.State.Length == 0);

            var location = x["location"] as JsonObject ?? new JsonObject();

            location["x"] = item.X;
            location["y"] = item.Y;
            Set(location, "z", Number(item.Z), item.Z == 0 && !isNewFurni);
            x["location"] = location;
            furni.Add(x);
        }

        if (root.ContainsKey("furni") || furni.Count > 0)
            root["furni"] = furni;

        var wired = root["wired"] as JsonObject ?? new JsonObject();
        var oldBoxes = SECTIONS.ToDictionary(
            section => section,
            section =>
                (wired[section] as JsonArray ?? [])
                    .OfType<JsonObject>()
                    .Where(x => Int(x["wiredId"]) is not null)
                    .GroupBy(x => Int(x["wiredId"])!.Value)
                    .ToDictionary(x => x.Key, x => x.First())
        );

        foreach (var section in SECTIONS)
        {
            var list = new JsonArray();

            foreach (var box in Boxes.Where(x => x.Section == section))
            {
                var x = oldBoxes[section].TryGetValue(box.WiredId, out var old)
                    ? old.DeepClone().AsObject()
                    : new JsonObject();

                x["wiredId"] = box.WiredId;
                // A box the file did not have gets every field G-Presets writes (options, config
                // and items are required there); one it had keeps the fields it had.
                var isNew = !oldBoxes[section].ContainsKey(box.WiredId);

                Set(x, "options", Array(box.Options), box.Options.IsEmpty && !isNew);
                Set(x, "config", box.Config, box.Config.Length == 0 && !isNew);
                Set(x, "items", Array(box.Items), box.Items.IsEmpty && !isNew);
                Set(x, "secondItems", Array(box.SecondItems), box.SecondItems.IsEmpty && !isNew);
                Set(x, "furniSources", Array(box.FurniSources), box.FurniSources.IsEmpty && !isNew);
                Set(x, "userSources", Array(box.UserSources), box.UserSources.IsEmpty && !isNew);
                Set(
                    x,
                    "variableIds",
                    new JsonArray([.. box.VariableIds.Select(v => (JsonNode)v)]),
                    box.VariableIds.IsEmpty && !isNew
                );

                Set(x, "variableId", box.VariableId, box.VariableId.Length == 0 && !(isNew && section == "variables"));

                // A new box carries the switches of its section, as G-Presets writes them.

                if (section == "effects")
                    Set(x, "delay", box.Delay, box.Delay == 0 && !isNew);

                if (section == "conditions")
                    Set(x, "quantifier", box.Quantifier, box.Quantifier == 0 && !isNew);

                if (section == "selectors")
                {
                    Set(x, "filter", box.Filter, !box.Filter && !isNew);
                    Set(x, "inverse", box.Inverse, !box.Inverse && !isNew);
                }

                list.Add(x);
            }

            // A section the file did not have stays out unless it has boxes; G-Presets needs
            // the first three whatever they hold.
            if (
                list.Count > 0
                || wired.ContainsKey(section)
                || (_created && REQUIRED_SECTIONS.Contains(section))
            )
                wired[section] = list;
        }

        if (_variablesMapChanged)
        {
            var map = new JsonObject();

            foreach (var (name, id) in _variablesMap.OrderBy(x => x.Key, StringComparer.Ordinal))
                map[name] = id;

            wired["variables_map"] = map;
        }

        root["wired"] = wired;

        if (_bindingsChanged)
            root["bindings"] = new JsonArray([.. _bindings.Select(WriteBinding)]);

        return root.ToJsonString(WRITE);
    }

    private static IEnumerable<GPresetBinding> ReadBindings(JsonObject root)
    {
        foreach (var item in root["bindings"] as JsonArray ?? [])
        {
            if (item is not JsonObject x || Int(x["furniId"]) is not { } furniId || Int(x["wiredId"]) is not { } wiredId)
                continue;

            var at = x["location"] as JsonObject;

            yield return new GPresetBinding(
                furniId,
                wiredId,
                at is null ? null : Int(at["x"]),
                at is null ? null : Int(at["y"]),
                Int(x["rotation"]),
                x["state"] is null ? null : Text(x["state"]),
                Int(x["altitude"])
            );
        }
    }

    private static JsonObject WriteBinding(GPresetBinding binding)
    {
        var x = new JsonObject { ["furniId"] = binding.FurniId, ["wiredId"] = binding.WiredId };

        if (binding.X is { } bx && binding.Y is { } by)
            x["location"] = new JsonObject { ["x"] = bx, ["y"] = by };

        if (binding.Rotation is { } rotation)
            x["rotation"] = rotation;

        if (binding.State is { } state)
            x["state"] = state;

        if (binding.Altitude is { } altitude)
            x["altitude"] = altitude;

        return x;
    }

    private static ImmutableDictionary<string, string> ReadVariablesMap(JsonObject root) =>
        (root["wired"] as JsonObject)?["variables_map"] is JsonObject map
            ? map.Where(x => x.Value is not null).ToImmutableDictionary(x => x.Key, x => Text(x.Value))
            : ImmutableDictionary<string, string>.Empty;

    private static IEnumerable<GPresetBox> ReadBoxes(JsonObject root)
    {
        if (root["wired"] is not JsonObject wired)
            yield break;

        foreach (var section in SECTIONS)
        {
            if (wired[section] is not JsonArray boxes)
                continue;

            foreach (var item in boxes)
            {
                if (item is not JsonObject x || Int(x["wiredId"]) is not { } wiredId)
                    continue;

                yield return new GPresetBox(
                    section,
                    wiredId,
                    Ints(x["options"]),
                    Text(x["config"]),
                    Ints(x["items"]),
                    Ints(x["secondItems"]),
                    Ints(x["furniSources"]),
                    Ints(x["userSources"]),
                    [.. (x["variableIds"] as JsonArray ?? []).Select(v => v is null ? string.Empty : Text(v))],
                    Int(x["delay"]) ?? 0,
                    Int(x["quantifier"]) ?? 0,
                    Bool(x["filter"]),
                    Bool(x["inverse"]),
                    Text(x["variableId"])
                );
            }
        }
    }

    /// <summary>
    /// Writes a field, unless the entry did not have it and the value is its default: an
    /// untouched file comes back with no field it did not have.
    /// </summary>
    private static void Set(JsonObject x, string key, JsonNode? value, bool isDefault)
    {
        if (isDefault && !x.ContainsKey(key))
            return;

        x[key] = value;
    }

    /// <summary>A height as a whole number when it is one (<c>0</c>, not <c>0.0</c>), as the file writes it.</summary>
    private static JsonNode Number(double value) =>
        value == Math.Floor(value) && Math.Abs(value) < int.MaxValue ? (int)value : value;

    private static JsonArray Array(ImmutableArray<int> values) =>
        new([.. values.Select(v => (JsonNode)v)]);

    private static ImmutableArray<int> Ints(JsonNode? node) =>
        [.. (node as JsonArray ?? []).Select(Int).Where(x => x is not null).Select(x => x!.Value)];

    private static int? Int(JsonNode? node) =>
        node is JsonValue value
            ? value.GetValueKind() switch
            {
                JsonValueKind.Number when value.TryGetValue<int>(out var i) => i,
                JsonValueKind.Number when value.TryGetValue<double>(out var d) && d == Math.Floor(d) => (int)d,
                JsonValueKind.String when int.TryParse(value.GetValue<string>(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var s) => s,
                _ => null,
            }
            : null;

    private static double? Double(JsonNode? node) =>
        node is JsonValue value && value.GetValueKind() == JsonValueKind.Number
            ? value.GetValue<double>()
            : null;

    private static bool Bool(JsonNode? node) =>
        node is JsonValue value && value.GetValueKind() == JsonValueKind.True;

    private static string Text(JsonNode? node) =>
        node is JsonValue value
            ? value.GetValueKind() switch
            {
                JsonValueKind.String => value.GetValue<string>(),
                JsonValueKind.Number => value.ToJsonString(),
                _ => string.Empty,
            }
            : string.Empty;
}

/// <summary>A G-Presets file that cannot be read, with what is wrong in a sentence for the player.</summary>
public sealed class GPresetException(string message) : Exception(message);
