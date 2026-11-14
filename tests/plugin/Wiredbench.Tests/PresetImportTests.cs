using Turbo.Primitives.Rooms.Snapshots.Furniture;
using Turbo.Primitives.Players;
using Turbo.Primitives.Rooms;
using Turbo.Primitives.Rooms.Wired.Variable;
using Turbo.Testing;
using Wiredbench.Presets;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// A G-Presets import into the room the player is in, against the test kit's hotel: the player's
/// own furni first, new furni only for players who may give furni, every furni placed on its own
/// tile, and each box saved onto its furni with its picks pointed at the placed items.
/// </summary>
public sealed class PresetImportTests
{
    // A fridge, a "furni state changed" trigger that picks it, a "toggle state" effect with a delay.
    private const string PRESET = """
        {
          "furni": [
            { "id": 1, "className": "ktchn_fridge", "rotation": 4, "state": "0", "location": { "x": 1, "y": 2, "z": 0 } },
            { "id": 2, "className": "wf_trg_state_changed", "location": { "x": 3, "y": 3, "z": 0 } },
            { "id": 3, "className": "wf_act_toggle_state", "location": { "x": 3, "y": 3, "z": 0.5 } }
          ],
          "wired": {
            "triggers": [ { "wiredId": 2, "items": [1], "furniSources": [100] } ],
            "conditions": [],
            "effects": [ { "wiredId": 3, "options": [0], "furniSources": [0], "delay": 5 } ]
          }
        }
        """;

    private readonly FakeHotel _hotel = new();
    private readonly FakePlayer _alice;
    private readonly FakeRoom _room;
    private readonly int _fridge;
    private readonly int _trigger;
    private readonly int _effect;

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    public PresetImportTests()
    {
        _alice = _hotel.Players.Add("alice", online: true);
        _room = _hotel.Rooms.Add("Lab", _alice);
        _hotel.Rooms.Enter(_room, _alice);
        _fridge = _hotel.Inventory.AddFurniture("ktchn_fridge").DefinitionId;
        _trigger = _hotel.Inventory.AddFurniture("wf_trg_state_changed").DefinitionId;
        _effect = _hotel.Inventory.AddFurniture("wf_act_toggle_state").DefinitionId;
    }

    [Fact]
    public async Task The_player_s_own_furni_are_placed_and_the_rest_reported_missing()
    {
        _hotel.Inventory.Hold(_alice, _fridge);

        var result = await Import();

        Assert.Equal(_room.Id.Value, result.RoomId);
        Assert.Contains("Placed 1 of 3 furni.", result.Message);
        Assert.Contains("Missing from your inventory: 1 x wf_act_toggle_state, 1 x wf_trg_state_changed.", result.Message);
        Assert.Contains("Set up 0 of 2 wired boxes.", result.Message);
        Assert.Empty(_hotel.Inventory.Grants);
        Assert.Equal(0, _hotel.Inventory.Held(_alice, _fridge));

        var fridge = Assert.Single(await _hotel.Rooms.FurniAsync(_room, Ct));
        Assert.Equal((_fridge, 1, 2), (fridge.DefinitionId, fridge.X, fridge.Y));
    }

    // The room an import running in the background has made.
    private async Task<FakeRoom> NewRoomAsync(string name)
    {
        for (var i = 0; i < 100; i++)
        {
            if (_hotel.Rooms.All.FirstOrDefault(x => x.Name == name) is { } room)
                return room;

            await Task.Delay(50, Ct);
        }

        throw new InvalidOperationException($"No room called {name} was made");
    }

    [Fact]
    public async Task An_import_into_a_new_room_leaves_the_caller_free_so_the_player_can_arrive()
    {
        _alice.Permissions.Add("command.giveitem");
        _hotel.Inventory.Hold(_alice, _fridge);
        _hotel.Rooms.Leave(_alice);

        var reported = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);

        // What the message handler does: start it and return. It must come back at once, with the
        // player still outside the new room: the client enters only after the handler is done.
        var job = new PresetTransfer(_hotel, null!).StartNewRoomImport(
            _alice.Id,
            PRESET,
            "Lab 2",
            (text, _) =>
            {
                reported.TrySetResult(text);

                return Task.CompletedTask;
            }
        );

        Assert.False(job.IsCompleted);

        await Task.Delay(700, Ct);

        Assert.False(reported.Task.IsCompleted, "the import should be waiting for the player to arrive");

        var created = await NewRoomAsync("Lab 2");

        _hotel.Rooms.Enter(created, _alice);

        var message = await reported.Task.WaitAsync(TimeSpan.FromSeconds(10), Ct);

        Assert.Contains("Placed 3 of 3 furni.", message);
        Assert.Equal(3, (await _hotel.Rooms.FurniAsync(created, Ct)).Count);
    }

    [Fact]
    public async Task A_new_room_without_a_floor_plan_in_the_file_gets_the_largest_flat_floor()
    {
        _hotel.Rooms.Leave(_alice);

        var job = new PresetTransfer(_hotel, null!).StartNewRoomImport(_alice.Id, PRESET, "Big", (_, _) => Task.CompletedTask);

        _hotel.Rooms.Enter(await NewRoomAsync("Big"), _alice);
        await job.WaitAsync(TimeSpan.FromSeconds(10), Ct);

        var rows = (await NewRoomAsync("Big")).FloorPlan!.Split('\r');

        Assert.Equal(64, rows.Length);
        Assert.All(rows, row => Assert.Equal(new string('0', 64), row));
    }

    [Fact]
    public async Task A_new_room_keeps_the_floor_plan_the_file_brings()
    {
        _hotel.Rooms.Leave(_alice);

        var withPlan = PRESET.Replace("\"furni\":", "\"floorplan\": \"000\\r000\", \"furni\":");

        var job = new PresetTransfer(_hotel, null!).StartNewRoomImport(_alice.Id, withPlan, "Small", (_, _) => Task.CompletedTask);

        _hotel.Rooms.Enter(await NewRoomAsync("Small"), _alice);
        await job.WaitAsync(TimeSpan.FromSeconds(10), Ct);

        Assert.Equal("000\r000", (await NewRoomAsync("Small")).FloorPlan);
    }

    [Fact]
    public async Task A_second_new_room_import_while_one_runs_is_refused()
    {
        _hotel.Rooms.Leave(_alice);

        var transfer = new PresetTransfer(_hotel, null!);
        var first = transfer.StartNewRoomImport(_alice.Id, PRESET, "Lab 2", (_, _) => Task.CompletedTask);
        string? second = null;

        await transfer.StartNewRoomImport(_alice.Id, PRESET, "Lab 3", (text, _) => Task.FromResult(second = text));

        Assert.Equal("An import into a new room is already running.", second);
        Assert.False(first.IsCompleted);

        _hotel.Rooms.Enter(await NewRoomAsync("Lab 2"), _alice);
        await first.WaitAsync(TimeSpan.FromSeconds(10), Ct);
    }

    [Fact]
    public async Task A_player_who_may_give_furni_has_the_rest_made_and_the_wired_set_up()
    {
        _alice.Permissions.Add("command.giveitem");
        _hotel.Inventory.Hold(_alice, _fridge);

        var result = await Import();

        Assert.Contains("Placed 3 of 3 furni.", result.Message);
        Assert.Contains("Made 2 furni you did not have.", result.Message);
        Assert.Contains("Set up 2 of 2 wired boxes.", result.Message);

        var furni = (await _hotel.Rooms.FurniAsync(_room, Ct)).ToDictionary(x => x.DefinitionId, x => x.ItemId);
        var boxes = _hotel.Wired.BoxesOf(_room);
        var trigger = boxes[furni[_trigger]];
        var effect = boxes[furni[_effect]];

        Assert.Equal([furni[_fridge]], trigger.StuffIds);
        Assert.Equal([100], Assert.Single(trigger.FurniSources));
        Assert.Equal(5, effect.Delay);
        Assert.Equal("wf_act_toggle_state", effect.LogicName);
    }

    [Fact]
    public async Task At_a_picked_tile_the_file_s_corner_lands_on_it_and_the_rest_keeps_its_place()
    {
        _alice.Permissions.Add("command.giveitem");

        // G-Presets' root: the file's (0, 0) lands on the picked tile (5, 5), so the fridge at
        // (1, 2) goes to (6, 7) and the stack at (3, 3) to (8, 8).
        var result = await new PresetTransfer(_hotel, null!).ImportAsync(
            _alice,
            PRESET,
            newRoom: false,
            "Lab",
            Ct,
            anchor: (5, 5)
        );

        Assert.Contains("Placed 3 of 3 furni.", result.Message);

        var tiles = (await _hotel.Rooms.FurniAsync(_room, Ct)).ToDictionary(x => x.DefinitionId, x => (x.X, x.Y));
        Assert.Equal((6, 7), tiles[_fridge]);
        Assert.Equal((8, 8), tiles[_trigger]);
        Assert.Equal((8, 8), tiles[_effect]);
    }

    // The file's context variable "500" is made by its variable box (id 4); an effect names it,
    // a built-in variable (-240) and G-Presets' empty slot (n).
    private const string VARIABLES = """
        {
          "furni": [
            { "id": 3, "className": "wf_act_toggle_state", "location": { "x": 1, "y": 1, "z": 0 } },
            { "id": 4, "className": "wf_var_context", "location": { "x": 2, "y": 1, "z": 0 } }
          ],
          "wired": {
            "triggers": [], "conditions": [],
            "effects": [ { "wiredId": 3, "variableIds": ["500", "-240", "n", "777", "s500-3", "~131", "s500-3-2", "s-240-3"] } ],
            "variables": [ { "wiredId": 4, "config": "picked_item", "options": [1], "variableId": "500" } ]
          }
        }
        """;

    [Fact]
    public async Task Variables_the_file_makes_are_renamed_to_the_boxes_placed_here()
    {
        _alice.Permissions.Add("command.giveitem");
        var context = _hotel.Inventory.AddFurniture("wf_var_context").DefinitionId;

        var result = await new PresetTransfer(_hotel, null!).ImportAsync(_alice, VARIABLES, newRoom: false, "Lab", Ct);

        var furni = (await _hotel.Rooms.FurniAsync(_room, Ct)).ToDictionary(x => x.DefinitionId, x => x.ItemId);
        var effect = _hotel.Wired.BoxesOf(_room)[furni[_effect]];

        // By name, as G-Presets maps them: the file's "500" is the room's "picked_item"; a built-in
        // and a smart id stay; the empty slot and an id nothing here has are 0; a sub-variable
        // takes the room's variable and the placed furni.
        var picked = WiredVariableId.OfBox(furni[context]).ToString();

        Assert.Equal(
            [picked, "-240", "0", "0", $"s{picked}-{furni[_effect]}", "~131", $"s{picked}-{furni[_effect]}-2", $"s-240-{furni[_effect]}"],
            effect.VariableIds
        );
        Assert.Contains("1 variables the file names were not found in this room (777)", result.Message);
    }

    // G-Presets' importer puts a file's heights above the lowest floor of the tiles it lands on.
    [Fact]
    public void Heights_go_above_the_lowest_floor_where_the_furni_land()
    {
        var target = new RoomLayoutSnapshot { Items = [], FloorWidth = 4, FloorLevels = [-1, 300, 200, 400] };
        GPresetFurni At(int x) => new(1, "x", x, 0, 0, 0, "0");

        Assert.Equal(200, PresetTransfer.FloorUnder(target, [At(1), At(3)]));
        Assert.Equal(300, PresetTransfer.FloorUnder(target, [At(0), At(1)]));
        Assert.Equal(0, PresetTransfer.FloorUnder(new RoomLayoutSnapshot { Items = [] }, [At(1)]));
    }

    // A Match Snapshot box bound to the fridge in state 1 at (4, 4): the fridge is moved and
    // switched there while the box is saved, and put back after, as G-Presets does.
    private const string BOUND = """
        {
          "furni": [
            { "id": 1, "className": "ktchn_fridge", "rotation": 0, "state": "0", "location": { "x": 1, "y": 1, "z": 0 } },
            { "id": 2, "className": "wf_act_match_to_sshot", "location": { "x": 2, "y": 2, "z": 0 } }
          ],
          "wired": { "triggers": [], "conditions": [], "effects": [ { "wiredId": 2, "items": [1], "options": [1, 0, 1, 0], "furniSources": [100] } ] },
          "bindings": [ { "furniId": 1, "wiredId": 2, "location": { "x": 4, "y": 4 }, "state": "1" } ]
        }
        """;

    [Fact]
    public async Task A_snapshot_box_is_saved_with_its_furni_as_bound_and_they_are_put_back()
    {
        _alice.Permissions.Add("command.giveitem");
        var match = _hotel.Inventory.AddFurniture("wf_act_match_to_sshot").DefinitionId;
        var result = await new PresetTransfer(_hotel, null!).ImportAsync(_alice, BOUND, newRoom: false, "Lab", Ct);

        Assert.Contains("Set up 1 of 1 wired boxes.", result.Message);

        var furni = (await _hotel.Rooms.FurniAsync(_room, Ct)).ToDictionary(x => x.DefinitionId, x => (x.ItemId, x.X, x.Y));
        Assert.Equal((1, 1), (furni[_fridge].X, furni[_fridge].Y));
        Assert.Equal([furni[_fridge].ItemId], _hotel.Wired.BoxesOf(_room)[furni[match].ItemId].StuffIds);
    }

    [Fact]
    public async Task Outside_a_room_nothing_is_imported()
    {
        _hotel.Rooms.Leave(_alice);

        var result = await Import();

        Assert.Null(result.RoomId);
        Assert.Equal("Enter a room first.", result.Message);
    }

    [Fact]
    public async Task A_wired_only_file_has_nothing_to_place()
    {
        var result = await new PresetTransfer(_hotel, null!).ImportAsync(
            _alice,
            """{ "wired": { "addons": [ { "wiredId": 22, "config": "0=150" } ] } }""",
            newRoom: false,
            "Lab",
            Ct
        );

        Assert.Null(result.RoomId);
        Assert.Contains("wired settings only", result.Message);
    }

    // The library is only used to export; an import reads the file it is given.
    private Task<PresetImportResult> Import() =>
        new PresetTransfer(_hotel, null!).ImportAsync(_alice, PRESET, newRoom: false, "Lab", Ct);
}
