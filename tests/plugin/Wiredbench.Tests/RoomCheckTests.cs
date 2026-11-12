using System.Collections.Immutable;
using Turbo.Contracts.Hotel;
using Turbo.Primitives.Rooms.Enums.Wired;
using Turbo.Primitives.Rooms.Snapshots.Wired;
using Turbo.Testing;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// The room check finds stacks that cannot work as built, without running them: the rules of
/// WiredBench's Python checker, read against the boxes Turbo stores. Each test builds a room with
/// one mistake and expects exactly that issue; a room built right has none.
/// </summary>
public sealed class RoomCheckTests
{
    private const int PICKED = 100;
    private const int SECOND_PICKED = 101;
    private const int SELECTOR = 200;
    private const int SIGNAL = 201;

    private readonly List<HotelRoomFurni> _furni = [];
    private readonly List<WiredBoxSettingsSnapshot> _boxes = [];
    private readonly List<HotelWiredVariable> _variables = [];

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    private int Furni(int x = 0, int y = 0)
    {
        var id = 1000 + _furni.Count;
        _furni.Add(new HotelRoomFurni(id, 1, x, y));

        return id;
    }

    private WiredBoxSettingsSnapshot Add(int x, int y, WiredType type, string logic, Func<WiredBoxSettingsSnapshot, WiredBoxSettingsSnapshot>? with = null)
    {
        var id = Furni(x, y);
        var box = new WiredBoxSettingsSnapshot
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
        box = with?.Invoke(box) ?? box;
        _boxes.Add(box);

        return box;
    }

    /// <summary>A stack that works: a trigger and an effect on one tile.</summary>
    private void Stack(int x, int y)
    {
        Add(x, y, WiredType.Trigger, "wf_trg_enter_room");
        Add(x, y, WiredType.Action, "wf_act_show_message", b => b with { StringParam = "hi" });
    }

    private ImmutableArray<RoomIssue> Check() => RoomChecker.Check(_furni, _boxes, _variables);

    private static ImmutableArray<ImmutableArray<int>> Slots(params int[] sources) => [.. sources.Select(x => ImmutableArray.Create(x))];

    [Fact]
    public void A_room_built_right_has_no_issues()
    {
        var lamp = Furni(5, 5);
        Add(1, 1, WiredType.Trigger, "wf_trg_state_changed", b => b with { StuffIds = [lamp], FurniSources = Slots(PICKED) });
        Add(1, 1, WiredType.Action, "wf_act_toggle_state", b => b with { StuffIds = [lamp], FurniSources = Slots(PICKED) });

        Assert.Empty(Check());
    }

    [Fact]
    public void A_pick_of_furni_no_longer_in_the_room_is_an_error()
    {
        Add(1, 1, WiredType.Trigger, "wf_trg_state_changed", b => b with { StuffIds = [4242], FurniSources = Slots(PICKED) });
        Add(1, 1, WiredType.Action, "wf_act_show_message");

        var issue = Assert.Single(Check());
        Assert.Equal(("error", "missing_furni"), (issue.Severity, issue.Code));
        Assert.Equal("It picks furni 4242, which is not in the room.", issue.Message);
        Assert.Equal((1, 1), (issue.X, issue.Y));
    }

    [Fact]
    public void A_slot_that_reads_picks_with_none_picked_is_an_error()
    {
        Add(1, 1, WiredType.Trigger, "wf_trg_enter_room");
        Add(1, 1, WiredType.Action, "wf_act_toggle_state", b => b with { FurniSources = Slots(PICKED) });
        Add(2, 2, WiredType.Trigger, "wf_trg_enter_room");
        Add(2, 2, WiredType.Action, "wf_act_move_to_furni", b => b with { StuffIds = [Furni()], FurniSources = Slots(PICKED, SECOND_PICKED) });

        Assert.Equal(["no_picks", "no_picks"], Check().Select(x => x.Code));
    }

    [Fact]
    public void A_slot_that_reads_a_selector_needs_no_picks()
    {
        Add(1, 1, WiredType.Trigger, "wf_trg_enter_room");
        Add(1, 1, WiredType.Selector, "wf_slc_furni_area");
        Add(1, 1, WiredType.Action, "wf_act_toggle_state", b => b with { FurniSources = Slots(SELECTOR) });

        Assert.Empty(Check());
    }

    [Fact]
    public void A_keyword_trigger_without_a_keyword_is_an_error_unless_it_matches_all_text()
    {
        Add(1, 1, WiredType.Trigger, "wf_trg_says_something", b => b with { IntParams = [0, 0, 1], StringParam = " " });
        Add(1, 1, WiredType.Action, "wf_act_show_message");
        Add(2, 2, WiredType.Trigger, "wf_trg_says_something", b => b with { IntParams = [0, 2, 1] });
        Add(2, 2, WiredType.Action, "wf_act_show_message");

        var issue = Assert.Single(Check());
        Assert.Equal(("no_keyword", 1), (issue.Code, issue.X));
    }

    [Fact]
    public void A_stack_with_no_trigger_or_no_effect_is_a_warning()
    {
        Add(1, 1, WiredType.Action, "wf_act_show_message");
        Add(2, 2, WiredType.Trigger, "wf_trg_enter_room");

        Assert.Equal(
            [("warning", "no_trigger", 1), ("warning", "no_effect", 2)],
            Check().Select(x => (x.Severity, x.Code, x.X))
        );
    }

    [Fact]
    public void A_stack_another_one_calls_needs_no_trigger()
    {
        var called = Add(4, 4, WiredType.Action, "wf_act_show_message");
        Add(1, 1, WiredType.Trigger, "wf_trg_enter_room");
        Add(1, 1, WiredType.Action, "wf_act_call_stacks", b => b with { StuffIds = [called.ItemId], FurniSources = Slots(PICKED) });

        Assert.Empty(Check());
    }

    [Fact]
    public void Reading_a_selection_or_a_signal_the_stack_has_not_is_a_warning()
    {
        Add(1, 1, WiredType.Trigger, "wf_trg_enter_room");
        Add(1, 1, WiredType.Action, "wf_act_toggle_state", b => b with { FurniSources = Slots(SELECTOR) });
        Add(2, 2, WiredType.Trigger, "wf_trg_enter_room");
        Add(2, 2, WiredType.Action, "wf_act_teleport_to", b => b with { UserSources = Slots(SIGNAL) });

        Assert.Equal(["no_selector", "no_signal"], Check().Select(x => x.Code));
    }

    [Fact]
    public void A_signal_must_be_both_sent_and_received_on_the_same_antenna()
    {
        var antenna = Furni(9, 9);
        var other = Furni(9, 8);
        Add(1, 1, WiredType.Trigger, "wf_trg_enter_room");
        Add(1, 1, WiredType.Action, "wf_act_send_signal", b => b with { StuffIds = [antenna], FurniSources = Slots(PICKED, SELECTOR), UserSources = Slots(SELECTOR) });
        Add(2, 2, WiredType.Trigger, "wf_trg_recv_signal", b => b with { StuffIds = [other], FurniSources = Slots(PICKED) });
        Add(2, 2, WiredType.Action, "wf_act_show_message");

        Assert.Equal(
            [("no_receiver", 1), ("no_sender", 2)],
            Check().Select(x => (x.Code, x.X))
        );
    }

    [Fact]
    public void A_signal_on_a_shared_antenna_is_fine_and_a_missing_antenna_is_an_error()
    {
        var antenna = Furni(9, 9);
        Add(1, 1, WiredType.Trigger, "wf_trg_enter_room");
        Add(1, 1, WiredType.Action, "wf_act_send_signal", b => b with { StuffIds = [antenna], FurniSources = Slots(PICKED, SELECTOR) });
        Add(2, 2, WiredType.Trigger, "wf_trg_recv_signal", b => b with { StuffIds = [antenna], FurniSources = Slots(PICKED) });
        Add(2, 2, WiredType.Action, "wf_act_show_message");
        Add(3, 3, WiredType.Trigger, "wf_trg_recv_signal", b => b with { FurniSources = Slots(PICKED) });
        Add(3, 3, WiredType.Action, "wf_act_show_message");

        var issue = Assert.Single(Check());
        Assert.Equal(("no_antenna", 3), (issue.Code, issue.X));
    }

    [Fact]
    public void A_variable_no_box_makes_is_an_error_but_built_in_ones_are_not()
    {
        _variables.Add(new HotelWiredVariable("9001", "score", WiredVariableType.Created));
        Add(1, 1, WiredType.Trigger, "wf_trg_enter_room");
        Add(1, 1, WiredType.Action, "wf_act_give_var", b => b with { VariableIds = ["9001", "9002", "-240", "~3", "s9001-5", "0", ""] });

        var issue = Assert.Single(Check());
        Assert.Equal(("error", "undefined_variable"), (issue.Severity, issue.Code));
        Assert.Contains("9002", issue.Message);
    }

    [Fact]
    public void A_box_that_names_a_variable_has_its_slots_left_alone()
    {
        // Give Variable's second user slot reads a selector only when the value comes from another
        // variable; Has Variable's furni slot only when the variable is a furni's.
        _variables.Add(new HotelWiredVariable("9001", "score", WiredVariableType.Created));
        Add(1, 1, WiredType.Trigger, "wf_trg_enter_room");
        Add(1, 1, WiredType.Condition, "wf_cnd_has_var", b => b with { VariableIds = ["9001"], FurniSources = Slots(PICKED) });
        Add(1, 1, WiredType.Action, "wf_act_give_var", b => b with { VariableIds = ["9001", "0"], UserSources = Slots(0, SELECTOR) });

        Assert.Empty(Check());
    }

    [Fact]
    public void Errors_come_before_warnings()
    {
        Add(5, 5, WiredType.Action, "wf_act_show_message");
        Add(9, 9, WiredType.Trigger, "wf_trg_says_something");
        Add(9, 9, WiredType.Action, "wf_act_show_message");

        Assert.Equal(["no_keyword", "no_trigger"], Check().Select(x => x.Code));
    }

    [Fact]
    public async Task The_window_gets_the_room_it_checked_and_a_summary()
    {
        var hotel = new FakeHotel();
        var alice = hotel.Players.Add("Alice");
        var room = hotel.Rooms.Add("Lab", alice);
        var handler = new CheckRunHandler(hotel);

        Assert.Equal("Enter a room first.", (await handler.RunAsync(alice.Id, Ct)).Message);

        hotel.Rooms.Enter(room, alice);
        var box = room.AddFurni(1, 3, 4);
        hotel.Wired.AddBox(room, new WiredBoxSettingsSnapshot
        {
            ItemId = box.ItemId,
            WiredType = WiredType.Action,
            WiredCode = 0,
            LogicName = "wf_act_show_message",
            IntParams = [],
            StringParam = "hi",
            StuffIds = [],
            StuffIds2 = [],
            VariableIds = [],
            FurniSources = [],
            UserSources = [],
        });

        var state = await handler.RunAsync(alice.Id, Ct);

        Assert.Equal((room.Id.Value, 1), (state.RoomId, state.Boxes));
        Assert.Equal("0 errors and 1 warning in 1 wired box.", state.Message);
        Assert.Equal(("no_trigger", 3, 4), (state.Issues[0].Code, state.Issues[0].X, state.Issues[0].Y));
    }
}
