using System;
using System.Collections.Concurrent;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Turbo.Contracts.Hotel;
using Turbo.Primitives.Players;
using Turbo.Primitives.Rooms;

namespace Wiredbench.Looks;

/// <summary>
/// <c>:copy</c>'s work, away from the room's turn: ask the Habbo hotel for the user's look, dress
/// the player in it, keep it in their wardrobe, and whisper how it went. One lookup per player at
/// a time, with a short wait between them; whatever fails is whispered, never thrown.
/// </summary>
public sealed class LookCopier(IHotel hotel, HabboLookup lookup, ILogger<LookCopier> logger) : IDisposable
{
    /// <summary>How long a player waits between two lookups.</summary>
    public static readonly TimeSpan COOLDOWN = TimeSpan.FromSeconds(5);

    private readonly ConcurrentDictionary<int, DateTimeOffset> _busy = new();
    private readonly CancellationTokenSource _stopping = new();

    /// <summary>
    /// Starts copying; false, with nothing started, while the player's last lookup is running or
    /// was too recent.
    /// </summary>
    public bool TryStart(PlayerId player, RoomId room, HabboHotel habbo, string name)
    {
        var now = hotel.Clock.GetUtcNow();

        if (_busy.TryGetValue(player.Value, out var since) && now - since < COOLDOWN + HabboLookup.TIME_LIMIT)
            return false;

        _busy[player.Value] = now;

        _ = Task.Run(() => RunAsync(player, room, habbo, name, _stopping.Token));

        return true;
    }

    /// <summary>The copy itself; what it whispers is its result, for tests.</summary>
    public async Task<string> RunAsync(PlayerId player, RoomId room, HabboHotel habbo, string name, CancellationToken ct)
    {
        string text;

        try
        {
            text = await CopyAsync(player, habbo, name, ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            return string.Empty;
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Could not copy {Name}'s look from {Hotel} for player {PlayerId}", name, habbo.Name, player.Value);
            text = $"Could not copy {name}'s look just now. Try again later.";
        }
        finally
        {
            // The wait starts when the lookup ends.
            _busy[player.Value] = hotel.Clock.GetUtcNow() - HabboLookup.TIME_LIMIT;
        }

        try
        {
            await hotel.Rooms.WhisperAsync(room, player, text, ct).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            logger.LogDebug(ex, "Could not whisper the copy's result to player {PlayerId}", player.Value);
        }

        return text;
    }

    private async Task<string> CopyAsync(PlayerId player, HabboHotel habbo, string name, CancellationToken ct)
    {
        var look = await lookup.FindAsync(habbo, name, ct).ConfigureAwait(false);

        switch (look.Status)
        {
            case HabboLookupStatus.NotFound:
                return $"User '{name}' could not be found on {habbo.Name}.";
            case HabboLookupStatus.TimedOut:
                return $"{habbo.Name} took too long to answer. Try again later.";
            case HabboLookupStatus.Unavailable:
                return $"{habbo.Name} could not be reached. Try again later.";
            case HabboLookupStatus.BadFigure:
                return $"{name}'s look on {habbo.Name} could not be read.";
        }

        var shown = look.Name.Length > 0 ? look.Name : name;
        var gender = await hotel.Players.SetFigureAsync(player, look.Figure, null, ct).ConfigureAwait(false);

        if (gender is not { } worn)
            return "Could not change your look.";

        // What the hotel put on, which leaves off what the player may not wear: the wardrobe keeps
        // that, so the outfit loads as it was worn and its picture matches it.
        var figure = (await hotel.Players.GetAsync(player, ct).ConfigureAwait(false))?.Figure is { Length: > 0 } fitted
            ? fitted
            : look.Figure;
        var wearing = figure == look.Figure
            ? $"You now wear {shown}'s look from {habbo.Name}."
            : $"You now wear {shown}'s look from {habbo.Name}, without the pieces you may not wear.";

        var wardrobe = await hotel.Players.WardrobeAsync(player, ct).ConfigureAwait(false);

        if (wardrobe.Any(x => x.Figure == figure))
            return $"{wearing} It is already in your wardrobe.";

        var used = wardrobe.Select(x => x.SlotId).ToHashSet();
        var slot = Enumerable.Range(1, Math.Max(0, hotel.Players.WardrobeSlots)).FirstOrDefault(x => !used.Contains(x));

        if (slot == 0)
            return $"{wearing} Your wardrobe is full, so it was not saved there.";

        return await hotel.Players.SaveOutfitAsync(player, slot, figure, worn, ct).ConfigureAwait(false)
            ? $"{wearing} Saved to wardrobe slot {slot}."
            : $"{wearing} It could not be saved to your wardrobe.";
    }

    public void Dispose()
    {
        _stopping.Cancel();
        _stopping.Dispose();
    }
}
