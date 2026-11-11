using Turbo.Contracts.Hotel;
using Turbo.Primitives.Rooms.Enums.Wired;
using Turbo.Primitives.Rooms.Snapshots.Furniture;
using Turbo.Primitives.Rooms.Snapshots.Wired;
using Turbo.Testing;
using Wiredbench.Presets;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// A room written as G-Presets' exporter writes one (sirjonasxx/G-Presets GPresetExporter):
/// furni numbered from 1, tiles relative to the corner, the room's user-made variables in
/// <c>variables_map</c>, a variable box's own id by its name, a snapshot box's snapshot as
/// bindings with its text left empty, and a sub-variable's furni renumbered.
/// </summary>
public sealed class PresetExportTests
{
    private readonly FakeHotel _hotel = new();

    [Fact]
    public void A_room_is_written_as_g_presets_writes_it()
    {
        var fridge = _hotel.Inventory.AddFurniture("ktchn_fridge").DefinitionId;
        var match = _hotel.Inventory.AddFurniture("wf_act_match_to_sshot").DefinitionId;
        var context = _hotel.Inventory.AddFurniture("wf_var_context").DefinitionId;
        var give = _hotel.Inventory.AddFurniture("wf_act_give_var").DefinitionId;

        var layout = new RoomLayoutSnapshot
        {
            Items =
            [
                Item(500, 10, 7, 0, state: 1),
                Item(501, 12, 8, 50),
                Item(502, 11, 9, 0),
                Item(503, 12, 8, 115),
            ],
        };
        var definitions = new Dictionary<int, int> { [500] = fridge, [501] = match, [502] = context, [503] = give };
        var boxes = new[]
        {
            Box(501, WiredType.Action, "wf_act_match_to_sshot") with
            {
                StuffIds = [500],
                StringParam = "",
                SnapshotText = "500,1,N,10,7,N",
                Delay = 2,
            },
            Box(502, WiredType.Variable, "wf_var_context") with { StringParam = "picked_item" },
            Box(503, WiredType.Action, "wf_act_give_var") with { VariableIds = ["9001", "s9001-500"] },
        };
        var variables = new[]
        {
            new HotelWiredVariable("9001", "picked_item", WiredVariableType.Created),
            new HotelWiredVariable("-240", "@position.x", WiredVariableType.Internal),
        };

        var file = new PresetTransfer(_hotel, null!).ToFile(layout, definitions, boxes, variables);
        var read = GPresetFile.Parse(file.ToJson());

        Assert.Equal(
            [
                new GPresetFurni(1, "ktchn_fridge", 0, 0, 0, 0, "1"),
                new GPresetFurni(2, "wf_act_match_to_sshot", 2, 1, 0.5, 0, "0"),
                new GPresetFurni(3, "wf_var_context", 1, 2, 0, 0, "0"),
                new GPresetFurni(4, "wf_act_give_var", 2, 1, 1.15, 0, "0"),
            ],
            read.Furni
        );

        var sshot = read.Boxes.Single(x => x.WiredId == 2);
        Assert.Equal("effects", sshot.Section);
        Assert.Equal([1], sshot.Items);
        Assert.Equal("", sshot.Config);
        Assert.Equal(new GPresetBinding(1, 2, 0, 0, null, "1", null), Assert.Single(read.Bindings));

        Assert.Equal("9001", read.Boxes.Single(x => x.WiredId == 3).VariableId);
        Assert.Equal(["9001", "s9001-1"], read.Boxes.Single(x => x.WiredId == 4).VariableIds);
        Assert.Equal(new Dictionary<string, string> { ["picked_item"] = "9001" }, read.VariablesMap);
    }

    // G-Presets' reader requires a furni's name, rotation and z, a box's options, config and
    // items, and the bindings list, so a file Wiredbench writes has them all, defaults included.
    [Fact]
    public void A_written_file_has_every_field_g_presets_requires()
    {
        var fridge = _hotel.Inventory.AddFurniture("ktchn_fridge").DefinitionId;
        var trigger = _hotel.Inventory.AddFurniture("wf_trg_state_changed").DefinitionId;
        var layout = new RoomLayoutSnapshot { Items = [Item(500, 3, 3, 0), Item(501, 4, 3, 0)] };
        var definitions = new Dictionary<int, int> { [500] = fridge, [501] = trigger };

        var json = System.Text.Json.Nodes.JsonNode.Parse(
            new PresetTransfer(_hotel, null!)
                .ToFile(layout, definitions, [Box(501, WiredType.Trigger, "wf_trg_state_changed")], [])
                .ToJson()
        )!;

        foreach (var furni in json["furni"]!.AsArray())
        {
            Assert.NotNull(furni!["name"]);
            Assert.NotNull(furni["rotation"]);
            Assert.NotNull(furni["location"]!["z"]);
        }

        var box = json["wired"]!["triggers"]![0]!;
        Assert.Equal("[]", box["options"]!.ToJsonString());
        Assert.Equal("", (string)box["config"]!);
        Assert.Equal("[]", box["items"]!.ToJsonString());
        Assert.NotNull(json["bindings"]);
        Assert.NotNull(json["wired"]!["effects"]);
        Assert.Null(json["floorplan"]);
    }

    private static RoomLayoutItemSnapshot Item(int id, int x, int y, int z, int state = 0) =>
        new()
        {
            ItemId = id,
            X = x,
            Y = y,
            Z = z,
            Rotation = 0,
            State = state,
        };

    private static WiredBoxSettingsSnapshot Box(int id, WiredType type, string logic) =>
        new()
        {
            ItemId = id,
            WiredType = type,
            WiredCode = 0,
            LogicName = logic,
            IntParams = [],
            StringParam = "",
            StuffIds = [],
            StuffIds2 = [],
            VariableIds = [],
            FurniSources = [],
            UserSources = [],
        };
}
