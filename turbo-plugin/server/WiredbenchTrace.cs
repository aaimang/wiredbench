using System;
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

/// <summary>Client to server: pause or resume the wired of the room I am in; the reply carries the steps after <paramref name="AfterId"/>, which a resume may have run.</summary>
[PluginMessage("wiredbench.trace.pause")]
public sealed record TracePauseMessage(bool Paused, long AfterId) : IPluginMessage;

/// <summary>Client to server: run the next <paramref name="Count"/> held effects of the room I am in; the reply carries the steps after <paramref name="AfterId"/>.</summary>
[PluginMessage("wiredbench.trace.step")]
public sealed record TraceStepMessage(int Count, long AfterId) : IPluginMessage;

/// <summary>An effect a paused room holds back, as the window lists it.</summary>
public sealed record HeldEffect(int StackId, int BoxId, string BoxLogic, int Remaining);

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
    ImmutableArray<TraceStep> Steps,
    bool Paused,
    ImmutableArray<HeldEffect> Held
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

/// <summary>Pauses or resumes the wired of the room the player is in, then answers with its state.</summary>
public sealed class TracePauseHandler(IHotel hotel) : IPluginMessageHandler<TracePauseMessage>
{
    public async ValueTask HandleAsync(
        TracePauseMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    )
    {
        if (await hotel.Players.CurrentRoomAsync(ctx.PlayerId, ct).ConfigureAwait(false) is { } room)
            await hotel.Wired.SetPausedAsync(room, ctx.PlayerId, message.Paused, ct).ConfigureAwait(false);

        await TraceReply.SendAsync(hotel, ctx, afterId: message.AfterId, ct).ConfigureAwait(false);
    }
}

/// <summary>Steps the held effects of the player's room, then answers with its state.</summary>
public sealed class TraceStepHandler(IHotel hotel) : IPluginMessageHandler<TraceStepMessage>
{
    // A window asks for one or a few; the room is not left running for long in a single call.
    private const int MAX_STEP = 50;

    public async ValueTask HandleAsync(
        TraceStepMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    )
    {
        if (await hotel.Players.CurrentRoomAsync(ctx.PlayerId, ct).ConfigureAwait(false) is { } room)
            await hotel.Wired.StepAsync(room, ctx.PlayerId, Math.Clamp(message.Count, 1, MAX_STEP), ct).ConfigureAwait(false);

        await TraceReply.SendAsync(hotel, ctx, afterId: message.AfterId, ct).ConfigureAwait(false);
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

        var pause = room is { } paused
            ? await hotel.Wired.GetPauseAsync(paused, ctx.PlayerId, ct).ConfigureAwait(false)
            : null;

        await ctx.ReplyAsync(
                new TraceStateMessage(
                    room?.Value ?? 0,
                    room is { } named ? (await hotel.Rooms.GetAsync(named, ct).ConfigureAwait(false))?.Name ?? string.Empty : string.Empty,
                    trace?.TimeZone ?? string.Empty,
                    trace is not null,
                    trace?.Enabled ?? false,
                    trace?.LastId ?? 0,
                    trace is null ? [] : [.. trace.Entries.TakeLast(MAX_STEPS_PER_REPLY).Select(ToStep)],
                    pause?.Paused ?? false,
                    pause is null ? [] : [.. pause.Held.Select(x => new HeldEffect(x.StackId, x.BoxId, x.BoxLogic, x.Remaining))]
                ),
                ct
            )
            .ConfigureAwait(false);
    }

    private static TraceStep ToStep(WiredTraceEntrySnapshot x) =>
        new(x.Id, x.RunId, x.StackId, x.Step, x.Outcome, x.BoxId, x.BoxLogic, x.BoxCode, x.Detail, x.AtText);
}
