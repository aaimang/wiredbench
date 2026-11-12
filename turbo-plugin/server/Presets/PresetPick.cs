using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Turbo.Contracts.Hotel;
using Turbo.Contracts.Plugins;
using Turbo.Primitives.Messages.Incoming.Room.Engine;
using Turbo.Messages.Registry;
using Turbo.Primitives.Players;
using Turbo.Primitives.Plugins.Messages;

namespace Wiredbench.Presets;

/// <summary>
/// Client to server: import preset <paramref name="Id"/> at the next floor tile I click in the
/// room I am in, as G-Presets places a preset where its user clicks.
/// </summary>
[PluginMessage("wiredbench.presets.pick")]
public sealed record PresetsPickMessage(int Id) : IPluginMessage;

/// <summary>
/// The imports waiting for their player's next floor click, one per player, each for
/// <see cref="WAIT"/>. A new pick replaces the one before.
/// </summary>
public sealed class PresetPicks(IHotel hotel)
{
    public static readonly TimeSpan WAIT = TimeSpan.FromSeconds(30);

    private readonly ConcurrentDictionary<PlayerId, (int PresetId, DateTimeOffset Until)> _waiting = new();

    public void Start(PlayerId player, int presetId) =>
        _waiting[player] = (presetId, hotel.Clock.GetUtcNow() + WAIT);

    /// <summary>The preset the player picks a tile for, taken out so one click places it once; null when none waits.</summary>
    public int? Take(PlayerId player) =>
        _waiting.TryRemove(player, out var pick) && pick.Until > hotel.Clock.GetUtcNow()
            ? pick.PresetId
            : null;
}

/// <summary>Arms a pick: the player's next floor click places the preset.</summary>
public sealed class PresetsPickHandler(IHotel hotel, PresetLibrary library, PresetPicks picks)
    : IPluginMessageHandler<PresetsPickMessage>
{
    public async ValueTask HandleAsync(PresetsPickMessage message, PluginMessageContext ctx, CancellationToken ct)
    {
        string report;

        if (await library.GetAsync(message.Id, ct).ConfigureAwait(false) is not { } preset)
            report = "That preset is no longer in the library.";
        else if (await hotel.Players.CurrentRoomAsync(ctx.PlayerId, ct).ConfigureAwait(false) is null)
            report = "Enter a room first.";
        else
        {
            picks.Start(ctx.PlayerId, preset.Id);
            report = $"Click a floor tile to place \"{preset.Name}\" there, as G-Presets places a preset at its root. Within {PresetPicks.WAIT.TotalSeconds:0} seconds.";
        }

        await PresetsReply.SendAsync(hotel, library, ctx.PlayerId, report, ct).ConfigureAwait(false);
    }
}

/// <summary>
/// The walk click a pick waits for: the clicked tile becomes the preset's root (its (0, 0)), and the avatar
/// stays where it is (the click was for the pick). Any other walk goes on as usual. The import
/// runs after the click is handled, so the session is not held while furni are placed.
/// </summary>
public sealed class PresetPickWalkBehavior(
    IHotel hotel,
    PresetLibrary library,
    PresetTransfer transfer,
    PresetPicks picks,
    ILogger<PresetPickWalkBehavior> logger
) : IMessageBehavior<MoveAvatarMessage>
{
    public async ValueTask InvokeAsync(
        MoveAvatarMessage env,
        MessageContext ctx,
        Func<ValueTask> next,
        CancellationToken ct
    )
    {
        if (picks.Take(ctx.PlayerId) is not { } presetId)
        {
            await next().ConfigureAwait(false);

            return;
        }

        var player = ctx.PlayerId;
        var tile = (env.TargetX, env.TargetY);

        _ = Task.Run(() => PlaceAsync(player, presetId, tile), CancellationToken.None);
    }

    private async Task PlaceAsync(PlayerId player, int presetId, (int X, int Y) tile)
    {
        try
        {
            string report;

            if (await library.GetAsync(presetId, CancellationToken.None).ConfigureAwait(false) is not { } preset)
                report = "That preset is no longer in the library.";
            else
                report = (
                    await transfer
                        .ImportAsync(player, preset.Json, false, preset.Name, CancellationToken.None, tile)
                        .ConfigureAwait(false)
                ).Message;

            await PresetsReply.SendAsync(hotel, library, player, report, CancellationToken.None).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Wiredbench could not import preset {PresetId} for player {PlayerId}", presetId, player);
        }
    }
}
