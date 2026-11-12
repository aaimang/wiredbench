using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Turbo.Contracts.Hotel;
using Turbo.Contracts.Plugins;
using Turbo.Primitives.Players;
using Turbo.Primitives.Plugins.Messages;
using Turbo.Primitives.Rooms;
using Turbo.Primitives.Rooms.Snapshots.Furniture;

namespace Wiredbench;

// The sandbox: the room the player is in, saved as it is built and put back after a test moved
// and switched its furni (IHotelRooms.CaptureLayoutAsync / RestoreLayoutAsync, the
// wiredbench-seams change in turbo-cloud), and a kit of every wired box the hotel can place.

/// <summary>Client to server: the sandbox state of the room I am in.</summary>
[PluginMessage("wiredbench.sandbox.read")]
public sealed record SandboxReadMessage() : IPluginMessage;

/// <summary>Client to server: save the room I am in as it stands now.</summary>
[PluginMessage("wiredbench.sandbox.save")]
public sealed record SandboxSaveMessage() : IPluginMessage;

/// <summary>
/// Client to server: put the room I am in back as it was saved; with
/// <paramref name="PutBackPickedUp"/>, saved furni I picked up since are placed again from my
/// inventory.
/// </summary>
[PluginMessage("wiredbench.sandbox.reset")]
public sealed record SandboxResetMessage(bool PutBackPickedUp) : IPluginMessage;

/// <summary>
/// Client to server: give me one of each wired furni of <paramref name="Kind"/> (a key of
/// data/wired-kit.json: triggers, effects, conditions, selectors, addons, variables, furni).
/// </summary>
[PluginMessage("wiredbench.sandbox.kit")]
public sealed record SandboxKitMessage(string Kind) : IPluginMessage;

/// <summary>
/// Server to client: the room the player is in (0 for none), whether they may save and reset it,
/// whether it has a saved layout, when it was saved and how many furni it holds, whether they may
/// take kits, the kits there are, and what the last request did.
/// </summary>
[PluginMessage("wiredbench.sandbox.state")]
public sealed record SandboxStateMessage(
    int RoomId,
    bool Allowed,
    bool HasSaved,
    string SavedAt,
    int SavedItems,
    bool CanTakeKits,
    ImmutableArray<SandboxKit> Kits,
    string Message
) : IPluginMessage;

/// <summary>A kit the player can take: its key and how many furni it gives.</summary>
public sealed record SandboxKit(string Kind, int Count);

/// <summary>The wired furni of each kit, from data/wired-kit.json, as the hotel knows them.</summary>
public sealed class WiredKits(IPluginFiles files, IHotel hotel, ILogger<WiredKits> logger)
{
    private const string FILE = "data/wired-kit.json";

    private readonly Lazy<IReadOnlyDictionary<string, ImmutableArray<int>>> _kits = new(() =>
    {
        using var stream = files.OpenRead(FILE);

        if (stream is null)
        {
            logger.LogWarning("Wiredbench has no {File}: no wired kits", FILE);

            return new Dictionary<string, ImmutableArray<int>>();
        }

        var names =
            JsonSerializer.Deserialize<Dictionary<string, string[]>>(stream)
            ?? new Dictionary<string, string[]>();

        // A name this hotel has no furni for is left out, so a kit only gives what can be made.
        return names.ToDictionary(
            x => x.Key,
            x =>
                x.Value.Select(name => hotel.Inventory.FindFurniture(name))
                    .Where(furni => furni is { IsWallItem: false })
                    .Select(furni => furni!.DefinitionId)
                    .ToImmutableArray()
        );
    });

    public IReadOnlyDictionary<string, ImmutableArray<int>> All => _kits.Value;
}

/// <summary>What the sandbox handlers share: who may do what, the saved layout, the reply.</summary>
public sealed class Sandbox(
    IHotel hotel,
    IServiceScopeFactory scopes,
    WiredKits kits,
    ILogger<Sandbox> logger
)
{
    /// <summary>Who may take kits: whoever may give furni with the hotel's own command.</summary>
    private const string KIT_PERMISSION = "command.giveitem";

    private const string KIT_CAUSE = "wiredbench.kit";

    public async ValueTask ReplyAsync(PluginMessageContext ctx, string message, CancellationToken ct)
    {
        var room = await hotel.Players.CurrentRoomAsync(ctx.PlayerId, ct).ConfigureAwait(false);
        var allowed =
            room is { } id
            && await hotel.Rooms.CaptureLayoutAsync(id, ctx.PlayerId, ct).ConfigureAwait(false)
                is not null;
        var saved = room is { } r ? await FindAsync(r, ct).ConfigureAwait(false) : null;
        var canTakeKits = await hotel
            .Players.HasPermissionAsync(ctx.PlayerId, KIT_PERMISSION, ct)
            .ConfigureAwait(false);

        await ctx.ReplyAsync(
                new SandboxStateMessage(
                    room?.Value ?? 0,
                    allowed,
                    saved is not null,
                    saved?.SavedAt.ToString("yyyy-MM-dd HH:mm") ?? string.Empty,
                    saved?.ItemCount ?? 0,
                    canTakeKits,
                    [.. kits.All.Select(x => new SandboxKit(x.Key, x.Value.Length))],
                    message
                ),
                ct
            )
            .ConfigureAwait(false);
    }

    /// <summary>Saves the room as it stands; what to tell the player.</summary>
    public async Task<string> SaveAsync(PlayerId player, CancellationToken ct)
    {
        if (await hotel.Players.CurrentRoomAsync(player, ct).ConfigureAwait(false) is not { } room)
            return "Enter a room first.";

        if (await hotel.Rooms.CaptureLayoutAsync(room, player, ct).ConfigureAwait(false) is not { } layout)
            return "You may not change the wired of this room.";

        await using var scope = scopes.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<WiredbenchDb>();
        var row = await db.Layouts.FindAsync([room.Value], ct).ConfigureAwait(false);

        if (row is null)
        {
            row = new SavedLayoutRow { RoomId = room.Value };
            db.Layouts.Add(row);
        }

        row.LayoutJson = JsonSerializer.Serialize(layout);
        row.ItemCount = layout.Items.Length;
        row.SavedBy = player.Value;
        row.SavedAt = hotel.Clock.GetUtcNow().UtcDateTime;

        await db.SaveChangesAsync(ct).ConfigureAwait(false);

        return $"Saved {layout.Items.Length} furni.";
    }

    /// <summary>Puts the room back as it was saved; what to tell the player.</summary>
    public async Task<string> ResetAsync(PlayerId player, bool putBackPickedUp, CancellationToken ct)
    {
        if (await hotel.Players.CurrentRoomAsync(player, ct).ConfigureAwait(false) is not { } room)
            return "Enter a room first.";

        if (await FindAsync(room, ct).ConfigureAwait(false) is not { } saved)
            return "Save the room first.";

        RoomLayoutSnapshot? layout;

        try
        {
            layout = JsonSerializer.Deserialize<RoomLayoutSnapshot>(saved.LayoutJson);
        }
        catch (JsonException ex)
        {
            logger.LogWarning(ex, "Wiredbench could not read the saved layout of room {RoomId}", room.Value);

            return "The saved layout could not be read; save the room again.";
        }

        if (layout is null)
            return "The saved layout could not be read; save the room again.";

        var result = await hotel
            .Rooms.RestoreLayoutAsync(room, player, layout, putBackPickedUp, ct)
            .ConfigureAwait(false);

        if (result is null)
            return "You may not change the wired of this room.";

        var missing = putBackPickedUp ? 0 : await CountMissingAsync(room, player, layout, ct).ConfigureAwait(false);
        var parts = new List<string>();

        if (result.Changed > 0)
            parts.Add($"Put {Furni(result.Changed)} back as saved.");

        if (result.PutBack > 0)
            parts.Add($"Placed {Furni(result.PutBack)} again from your inventory.");

        if (missing > 0)
            parts.Add($"{Furni(missing)} saved here {(missing == 1 ? "is" : "are")} no longer in the room.");

        return parts.Count > 0 ? string.Join(" ", parts) : "The room is already as saved.";
    }

    private static string Furni(int count) => count == 1 ? "1 furni" : $"{count} furni";

    /// <summary>How many saved furni are not in the room now.</summary>
    private async Task<int> CountMissingAsync(
        RoomId room,
        PlayerId player,
        RoomLayoutSnapshot layout,
        CancellationToken ct
    )
    {
        if (await hotel.Rooms.CaptureLayoutAsync(room, player, ct).ConfigureAwait(false) is not { } now)
            return 0;

        var inRoom = now.Items.Select(x => x.ItemId).ToHashSet();

        return layout.Items.Count(x => !inRoom.Contains(x.ItemId));
    }

    /// <summary>Gives the player one of each furni of the kit; what to tell them.</summary>
    public async Task<string> GiveKitAsync(PlayerId player, string kind, CancellationToken ct)
    {
        if (!await hotel.Players.HasPermissionAsync(player, KIT_PERMISSION, ct).ConfigureAwait(false))
            return "You may not take kits.";

        if (!kits.All.TryGetValue(kind, out var definitions))
            return $"There is no kit called {kind}.";

        var given = 0;

        foreach (var definition in definitions)
        {
            if (
                await hotel
                    .Inventory.GrantFurnitureAsync(player, definition, KIT_CAUSE, ct)
                    .ConfigureAwait(false)
            )
                given++;
        }

        return $"Gave {given} {kind} to your inventory.";
    }

    private async Task<SavedLayoutRow?> FindAsync(RoomId room, CancellationToken ct)
    {
        await using var scope = scopes.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<WiredbenchDb>();

        return await db
            .Layouts.AsNoTracking()
            .FirstOrDefaultAsync(x => x.RoomId == room.Value, ct)
            .ConfigureAwait(false);
    }
}

public sealed class SandboxReadHandler(Sandbox sandbox) : IPluginMessageHandler<SandboxReadMessage>
{
    public ValueTask HandleAsync(
        SandboxReadMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    ) => sandbox.ReplyAsync(ctx, string.Empty, ct);
}

public sealed class SandboxSaveHandler(Sandbox sandbox) : IPluginMessageHandler<SandboxSaveMessage>
{
    public async ValueTask HandleAsync(
        SandboxSaveMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    ) =>
        await sandbox
            .ReplyAsync(ctx, await sandbox.SaveAsync(ctx.PlayerId, ct).ConfigureAwait(false), ct)
            .ConfigureAwait(false);
}

public sealed class SandboxResetHandler(Sandbox sandbox)
    : IPluginMessageHandler<SandboxResetMessage>
{
    public async ValueTask HandleAsync(
        SandboxResetMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    ) =>
        await sandbox
            .ReplyAsync(
                ctx,
                await sandbox
                    .ResetAsync(ctx.PlayerId, message.PutBackPickedUp, ct)
                    .ConfigureAwait(false),
                ct
            )
            .ConfigureAwait(false);
}

public sealed class SandboxKitHandler(Sandbox sandbox) : IPluginMessageHandler<SandboxKitMessage>
{
    public async ValueTask HandleAsync(
        SandboxKitMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    ) =>
        await sandbox
            .ReplyAsync(
                ctx,
                await sandbox.GiveKitAsync(ctx.PlayerId, message.Kind, ct).ConfigureAwait(false),
                ct
            )
            .ConfigureAwait(false);
}
