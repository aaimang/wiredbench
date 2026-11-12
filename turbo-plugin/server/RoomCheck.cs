using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Hotel;
using Turbo.Contracts.Plugins;
using Turbo.Primitives.Plugins.Messages;
using Turbo.Primitives.Rooms.Enums.Wired;
using Turbo.Primitives.Rooms.Snapshots.Wired;

namespace Wiredbench;

/// <summary>
/// One thing wrong with a room's wired: <see cref="Severity"/> is "error" when a box cannot work
/// as built, "warning" when it is usually a mistake but can be meant. <see cref="Code"/> names the
/// rule; <see cref="BoxId"/> is the box's item, standing on <see cref="X"/>, <see cref="Y"/>.
/// </summary>
public sealed record RoomIssue(string Severity, string Code, int BoxId, string Logic, int X, int Y, string Message);

/// <summary>
/// Finds stacks that cannot work as built, without running them (WiredBench's Python checker,
/// read against Turbo's boxes): picks of furni no longer in the room, a furni slot or an antenna
/// slot with nothing picked, a keyword trigger with no keyword, a stack nothing starts or that does
/// nothing, a box reading a selector's or a signal's targets with neither in its stack, a signal
/// no stack receives or no box sends, and a variable no box in the room makes. A box that names a
/// variable reads the slots its variable needs, which its settings do not say: its slots are not
/// checked.
/// </summary>
public static class RoomChecker
{
    public const string ERROR = "error";
    public const string WARNING = "warning";

    // The client's source codes (WiredSourceType), furni and users alike.
    private const int PICKED = 100;
    private const int SECOND_PICKED = 101;
    private const int SELECTOR = 200;
    private const int SIGNAL = 201;

    private const string RECEIVER = "wf_trg_recv_signal";
    private const string SAYS = "wf_trg_says_something";

    // wf_trg_says_something's second param: 2 is "Match all text", which takes no keyword.
    private const int SAYS_MATCH_PARAM = 1;
    private const int SAYS_MATCH_ANY_TEXT = 2;

    private static readonly ImmutableHashSet<string> CALLERS = ["wf_act_call_stacks", "wf_act_neg_call_stacks"];
    private static readonly ImmutableHashSet<string> SENDERS = ["wf_act_send_signal", "wf_act_neg_send_signal"];

    public static ImmutableArray<RoomIssue> Check(
        IReadOnlyCollection<HotelRoomFurni> furni,
        IReadOnlyCollection<WiredBoxSettingsSnapshot> boxes,
        IReadOnlyCollection<HotelWiredVariable> variables
    )
    {
        var tiles = furni.ToDictionary(x => x.ItemId, x => (x.X, x.Y));
        var placed = boxes.Where(x => tiles.ContainsKey(x.ItemId)).ToList();
        var issues = new List<RoomIssue>();

        void Add(string severity, string code, WiredBoxSettingsSnapshot box, string message)
        {
            var (x, y) = tiles[box.ItemId];
            issues.Add(new RoomIssue(severity, code, box.ItemId, box.LogicName, x, y, message));
        }

        var stacks = placed.GroupBy(x => tiles[x.ItemId]).ToDictionary(x => x.Key, x => x.ToList());

        CheckPicks(placed, tiles, Add);
        CheckStacks(stacks, tiles, Add);
        CheckSignals(placed, Add);
        CheckVariables(placed, variables, Add);

        return
        [
            .. issues
                .OrderBy(x => x.Severity == ERROR ? 0 : 1)
                .ThenBy(x => x.Y)
                .ThenBy(x => x.X)
                .ThenBy(x => x.BoxId)
                .ThenBy(x => x.Code, StringComparer.Ordinal),
        ];
    }

    private static void CheckPicks(
        List<WiredBoxSettingsSnapshot> boxes,
        Dictionary<int, (int X, int Y)> tiles,
        Action<string, string, WiredBoxSettingsSnapshot, string> add
    )
    {
        foreach (var box in boxes)
        {
            foreach (var id in box.StuffIds.Concat(box.StuffIds2).Distinct())
                if (!tiles.ContainsKey(id))
                    add(ERROR, "missing_furni", box, $"It picks furni {id}, which is not in the room.");

            var antennaBox = SENDERS.Contains(box.LogicName) || box.LogicName == RECEIVER;

            for (var slot = 0; slot < (NamesVariable(box) ? 0 : box.FurniSources.Length); slot++)
            {
                var sources = box.FurniSources[slot];
                var empty =
                    (sources.Contains(PICKED) && box.StuffIds.IsEmpty)
                    || (sources.Contains(SECOND_PICKED) && box.StuffIds2.IsEmpty);

                if (!empty)
                    continue;

                if (antennaBox && slot == 0)
                    add(ERROR, "no_antenna", box, "It has no antenna picked.");
                else
                    add(ERROR, "no_picks", box, "It has no furni picked.");
            }

            if (
                box.LogicName == SAYS
                && box.IntParams.ElementAtOrDefault(SAYS_MATCH_PARAM) != SAYS_MATCH_ANY_TEXT
                && string.IsNullOrWhiteSpace(box.StringParam)
            )
                add(ERROR, "no_keyword", box, "It has no keyword, so it never runs.");
        }
    }

    private static void CheckStacks(
        Dictionary<(int X, int Y), List<WiredBoxSettingsSnapshot>> stacks,
        Dictionary<int, (int X, int Y)> tiles,
        Action<string, string, WiredBoxSettingsSnapshot, string> add
    )
    {
        // A stack a Call Stacks box runs needs no trigger of its own.
        var called = stacks
            .Values.SelectMany(x => x)
            .Where(x => CALLERS.Contains(x.LogicName))
            .SelectMany(x => x.StuffIds)
            .Where(tiles.ContainsKey)
            .Select(x => tiles[x])
            .ToHashSet();

        foreach (var (tile, boxes) in stacks)
        {
            var trigger = boxes.FirstOrDefault(x => x.WiredType == WiredType.Trigger);
            var working = boxes.FirstOrDefault(x =>
                x.WiredType is WiredType.Action or WiredType.Condition or WiredType.Selector
            );

            if (trigger is null && working is not null && !called.Contains(tile))
                add(WARNING, "no_trigger", working, "Nothing starts this stack, because it has no trigger.");

            if (trigger is not null && boxes.All(x => x.WiredType != WiredType.Action))
                add(WARNING, "no_effect", trigger, "This stack does nothing, because it has no effect.");

            var hasSelector = boxes.Any(x => x.WiredType == WiredType.Selector);
            var hasReceiver = boxes.Any(x => x.LogicName == RECEIVER);

            foreach (var box in boxes.Where(x => !NamesVariable(x)))
            {
                var sources = box.FurniSources.Concat(box.UserSources).SelectMany(x => x).ToHashSet();

                // A sender or a caller hands on its stack's selection; reading none is no mistake.
                var forwards = SENDERS.Contains(box.LogicName) || CALLERS.Contains(box.LogicName);

                if (sources.Contains(SELECTOR) && !hasSelector && !forwards)
                    add(WARNING, "no_selector", box, "It uses selected targets, but its stack has no selector.");

                if (sources.Contains(SIGNAL) && !hasReceiver)
                    add(WARNING, "no_signal", box, "It uses a signal's targets, but its stack receives no signal.");
            }
        }
    }

    private static void CheckSignals(
        List<WiredBoxSettingsSnapshot> boxes,
        Action<string, string, WiredBoxSettingsSnapshot, string> add
    )
    {
        var senders = boxes.Where(x => SENDERS.Contains(x.LogicName)).ToList();
        var receivers = boxes.Where(x => x.LogicName == RECEIVER).ToList();
        var sent = senders.Select(Antennas).ToList();
        var received = receivers.Select(Antennas).ToList();

        // An antenna slot reading a selector's or a signal's furni is known only as it runs: a
        // sender like that may reach any receiver, and a receiver like that may hear any sender.
        var anySender = sent.Any(x => x is null);
        var anyReceiver = received.Any(x => x is null);
        var sentTo = sent.Where(x => x is not null).SelectMany(x => x!).ToHashSet();
        var heardOn = received.Where(x => x is not null).SelectMany(x => x!).ToHashSet();

        for (var i = 0; i < senders.Count; i++)
            if (sent[i] is { Count: > 0 } antennas && !anyReceiver && !antennas.Overlaps(heardOn))
                add(WARNING, "no_receiver", senders[i], "No stack receives this signal.");

        for (var i = 0; i < receivers.Count; i++)
            if (received[i] is { Count: > 0 } antennas && !anySender && !antennas.Overlaps(sentTo))
                add(WARNING, "no_sender", receivers[i], "No effect in this room sends this signal.");
    }

    /// <summary>
    /// Whether the box names a variable: which of its furni and user slots it reads then depends on
    /// the variable (a user's or a furni's, a value of its own or another's), which the settings do
    /// not say, so its slots are not checked.
    /// </summary>
    private static bool NamesVariable(WiredBoxSettingsSnapshot box) =>
        box.VariableIds.Any(x => x is not ("" or "0"));

    /// <summary>The antennas a signal box picked; null when its antenna slot is not a pick.</summary>
    private static HashSet<int>? Antennas(WiredBoxSettingsSnapshot box)
    {
        var sources = box.FurniSources.IsEmpty ? [PICKED] : box.FurniSources[0];

        if (sources.Contains(PICKED))
            return [.. box.StuffIds];

        if (sources.Contains(SECOND_PICKED))
            return [.. box.StuffIds2];

        return null;
    }

    private static void CheckVariables(
        List<WiredBoxSettingsSnapshot> boxes,
        IReadOnlyCollection<HotelWiredVariable> variables,
        Action<string, string, WiredBoxSettingsSnapshot, string> add
    )
    {
        var known = variables.Select(x => x.Id).ToHashSet(StringComparer.Ordinal);

        foreach (var box in boxes)
        foreach (var id in box.VariableIds.Distinct())
        {
            // Unset ("" or 0), a built-in (-N) or smart one (~N), or a box's sub-variable (s...):
            // only a variable a box makes can be gone.
            if (id is "" or "0" || id[0] is '-' or '~' or 's')
                continue;

            if (!known.Contains(id))
                add(ERROR, "undefined_variable", box, $"Variable {id} is not made by any variable box here.");
        }
    }
}

/// <summary>Client to server: check the wired of the room I am in.</summary>
[PluginMessage("wiredbench.check.run")]
public sealed record CheckRunMessage() : IPluginMessage;

/// <summary>Server to client: the room checked (0 for none), what was found, and a line to show.</summary>
[PluginMessage("wiredbench.check.state")]
public sealed record CheckStateMessage(int RoomId, int Boxes, ImmutableArray<RoomIssue> Issues, string Message)
    : IPluginMessage;

/// <summary>Checks the room the player is in, if they may read its wired.</summary>
public sealed class CheckRunHandler(IHotel hotel) : IPluginMessageHandler<CheckRunMessage>
{
    public async ValueTask HandleAsync(CheckRunMessage message, PluginMessageContext ctx, CancellationToken ct)
    {
        await ctx.ReplyAsync(await RunAsync(ctx.PlayerId, ct).ConfigureAwait(false), ct).ConfigureAwait(false);
    }

    public async Task<CheckStateMessage> RunAsync(Turbo.Primitives.Players.PlayerId player, CancellationToken ct)
    {
        if (await hotel.Players.CurrentRoomAsync(player, ct).ConfigureAwait(false) is not { } room)
            return new CheckStateMessage(0, 0, [], "Enter a room first.");

        if (await hotel.Wired.ReadBoxesAsync(room, player, ct).ConfigureAwait(false) is not { } boxes)
            return new CheckStateMessage(room.Value, 0, [], "You may not read the wired of this room.");

        var furni = await hotel.Rooms.FurniAsync(room, ct).ConfigureAwait(false);
        var variables = await hotel.Wired.ReadVariablesAsync(room, player, ct).ConfigureAwait(false) ?? [];
        var issues = RoomChecker.Check([.. furni], boxes, variables);
        var errors = issues.Count(x => x.Severity == RoomChecker.ERROR);

        var text = issues.IsEmpty
            ? $"No problems found in {Count(boxes.Length, "wired box", "wired boxes")}."
            : $"{Count(errors, "error", "errors")} and {Count(issues.Length - errors, "warning", "warnings")} in {Count(boxes.Length, "wired box", "wired boxes")}.";

        return new CheckStateMessage(room.Value, boxes.Length, issues, text);
    }

    private static string Count(int n, string one, string many) => $"{n} {(n == 1 ? one : many)}";
}
