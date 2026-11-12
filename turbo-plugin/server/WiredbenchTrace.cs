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

// The Trace window's messages. The hotel records the trace of the room the player is in
// (IHotelWired.SetTraceAsync / GetTraceAsync, the wiredbench-seams change in turbo-cloud); the
// window turns it on and reads the steps after the last one it has, about once a second.

/// <summary>Client to server: turn the trace of the room I am in on or off.</summary>
[PluginMessage("wiredbench.trace.set")]
public sealed record TraceSetMessage(bool Enabled) : IPluginMessage;

/// <summary>Client to server: the trace steps of the room I am in after <paramref name="AfterId"/>.</summary>
[PluginMessage("wiredbench.trace.read")]
public sealed record TraceReadMessage(long AfterId) : IPluginMessage;

/// <summary>One step of the trace, as the window lists it.</summary>
public sealed record TraceStep(
    long Id,
    long RunId,
    int StackId,
    WiredTraceStepType Step,
    WiredTraceOutcomeType Outcome,
    int BoxId,
    string BoxLogic,
    int BoxCode,
    string Detail,
    string Time
);

/// <summary>
/// Server to client: the trace of the room the player is in (<paramref name="RoomId"/> 0 when in
/// none) and its name, the room's wired time zone each step's time is in, whether they may read
/// it, whether it is on, the last step the room recorded and the steps after the one asked for.
/// </summary>
[PluginMessage("wiredbench.trace.state")]
public sealed record TraceStateMessage(
    int RoomId,
    string RoomName,
    string TimeZone,
    bool Allowed,
    bool Enabled,
    long LastId,
    ImmutableArray<TraceStep> Steps
) : IPluginMessage;

/// <summary>Turns the trace on or off for the room the player is in, then answers with its state.</summary>
public sealed class TraceSetHandler(IHotel hotel) : IPluginMessageHandler<TraceSetMessage>
{
    public async ValueTask HandleAsync(
        TraceSetMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    )
    {
        if (await hotel.Players.CurrentRoomAsync(ctx.PlayerId, ct).ConfigureAwait(false) is { } room)
            await hotel.Wired.SetTraceAsync(room, ctx.PlayerId, message.Enabled, ct).ConfigureAwait(false);

        await TraceReply.SendAsync(hotel, ctx, afterId: long.MaxValue, ct).ConfigureAwait(false);
    }
}

/// <summary>Answers with the steps of the player's room after the one the window has.</summary>
public sealed class TraceReadHandler(IHotel hotel) : IPluginMessageHandler<TraceReadMessage>
{
    public ValueTask HandleAsync(
        TraceReadMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    ) => TraceReply.SendAsync(hotel, ctx, message.AfterId, ct);
}

internal static class TraceReply
{
    // The newest steps a reply carries; a window that fell further behind skips the older ones.
    private const int MAX_STEPS_PER_REPLY = 200;

    public static async ValueTask SendAsync(
        IHotel hotel,
        PluginMessageContext ctx,
        long afterId,
        CancellationToken ct
    )
    {
        var room = await hotel.Players.CurrentRoomAsync(ctx.PlayerId, ct).ConfigureAwait(false);
        var trace = room is { } id
            ? await hotel.Wired.GetTraceAsync(id, ctx.PlayerId, afterId, ct).ConfigureAwait(false)
            : null;

        await ctx.ReplyAsync(
                new TraceStateMessage(
                    room?.Value ?? 0,
                    room is { } named ? (await hotel.Rooms.GetAsync(named, ct).ConfigureAwait(false))?.Name ?? string.Empty : string.Empty,
                    trace?.TimeZone ?? string.Empty,
                    trace is not null,
                    trace?.Enabled ?? false,
                    trace?.LastId ?? 0,
                    trace is null ? [] : [.. trace.Entries.TakeLast(MAX_STEPS_PER_REPLY).Select(ToStep)]
                ),
                ct
            )
            .ConfigureAwait(false);
    }

    private static TraceStep ToStep(WiredTraceEntrySnapshot x) =>
        new(x.Id, x.RunId, x.StackId, x.Step, x.Outcome, x.BoxId, x.BoxLogic, x.BoxCode, x.Detail, x.AtText);
}
