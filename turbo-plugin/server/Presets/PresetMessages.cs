using System.Collections.Immutable;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Hotel;
using Turbo.Contracts.Plugins;
using Turbo.Primitives.Players;
using Turbo.Primitives.Plugins.Messages;

namespace Wiredbench.Presets;

// The Sandbox window's preset list: the library (filled in the admin panel or by an export), an
// import into the room the player is in or a new one, and an export of the room to the library.

/// <summary>Client to server: the preset library, and whether I may import into the room I am in.</summary>
[PluginMessage("wiredbench.presets.read")]
public sealed record PresetsReadMessage() : IPluginMessage;

/// <summary>Client to server: import preset <paramref name="Id"/> into the room I am in, or into a new room.</summary>
[PluginMessage("wiredbench.presets.import")]
public sealed record PresetsImportMessage(int Id, bool NewRoom) : IPluginMessage;

/// <summary>Client to server: save the room I am in to the library as <paramref name="Name"/>.</summary>
[PluginMessage("wiredbench.presets.export")]
public sealed record PresetsExportMessage(string Name) : IPluginMessage;

/// <summary>
/// Client to server: delete preset <paramref name="Id"/> from the library; for players holding
/// <c>plugin.wiredbench.presets</c>, as the panel's Delete.
/// </summary>
[PluginMessage("wiredbench.presets.delete")]
public sealed record PresetsDeleteMessage(int Id) : IPluginMessage;

/// <summary>A preset as the window lists it.</summary>
public sealed record PresetItem(int Id, string Name, int Furni, int Boxes, string SavedAt);

/// <summary>Server to client: the room the player is in (0 for none), the library and what the last request did.</summary>
[PluginMessage("wiredbench.presets.state")]
public sealed record PresetsStateMessage(
    int RoomId,
    ImmutableArray<PresetItem> Presets,
    string Message,
    bool CanDelete
) : IPluginMessage;

internal static class PresetsReply
{
    /// <summary>Who may delete presets: the panel's own node for the library.</summary>
    public const string MANAGE_PERMISSION = "plugin.wiredbench.presets";

    // The newest presets the window lists.
    private const int MAX_LISTED = 30;

    public static ValueTask SendAsync(
        IHotel hotel,
        PresetLibrary library,
        PluginMessageContext ctx,
        string message,
        CancellationToken ct
    ) => SendAsync(hotel, library, ctx.PlayerId, message, ct);

    /// <summary>The state sent to the player, from a handler or after a picked import.</summary>
    public static async ValueTask SendAsync(
        IHotel hotel,
        PresetLibrary library,
        PlayerId player,
        string message,
        CancellationToken ct
    )
    {
        var room = await hotel.Players.CurrentRoomAsync(player, ct).ConfigureAwait(false);
        var presets = await library.ListAsync(ct).ConfigureAwait(false);

        await hotel
            .Players.SendAsync(
                player,
                new PresetsStateMessage(
                    room?.Value ?? 0,
                    [
                        .. presets
                            .Take(MAX_LISTED)
                            .Select(x => new PresetItem(x.Id, x.Name, x.FurniCount, x.BoxCount, x.SavedAt.ToString("yyyy-MM-dd HH:mm"))),
                    ],
                    message,
                    await hotel.Players.HasPermissionAsync(player, MANAGE_PERMISSION, ct).ConfigureAwait(false)
                ),
                ct
            )
            .ConfigureAwait(false);
    }
}

public sealed class PresetsReadHandler(IHotel hotel, PresetLibrary library)
    : IPluginMessageHandler<PresetsReadMessage>
{
    public ValueTask HandleAsync(PresetsReadMessage message, PluginMessageContext ctx, CancellationToken ct) =>
        PresetsReply.SendAsync(hotel, library, ctx, string.Empty, ct);
}

public sealed class PresetsImportHandler(IHotel hotel, PresetLibrary library, PresetTransfer transfer)
    : IPluginMessageHandler<PresetsImportMessage>
{
    public async ValueTask HandleAsync(PresetsImportMessage message, PluginMessageContext ctx, CancellationToken ct)
    {
        string report;

        if (await library.GetAsync(message.Id, ct).ConfigureAwait(false) is not { } preset)
            report = "That preset is no longer in the library.";
        else if (message.NewRoom)
        {
            // Left running: the player's client can only enter the new room once this handler is
            // done (see StartNewRoomImport), and the report comes when the import is over.
            _ = transfer.StartNewRoomImport(
                ctx.PlayerId,
                preset.Json,
                preset.Name,
                (text, token) => PresetsReply.SendAsync(hotel, library, ctx.PlayerId, text, token).AsTask()
            );

            return;
        }
        else
            report = (
                await transfer
                    .ImportAsync(ctx.PlayerId, preset.Json, message.NewRoom, preset.Name, ct)
                    .ConfigureAwait(false)
            ).Message;

        await PresetsReply.SendAsync(hotel, library, ctx, report, ct).ConfigureAwait(false);
    }
}

public sealed class PresetsExportHandler(IHotel hotel, PresetLibrary library, PresetTransfer transfer)
    : IPluginMessageHandler<PresetsExportMessage>
{
    public async ValueTask HandleAsync(PresetsExportMessage message, PluginMessageContext ctx, CancellationToken ct)
    {
        var report = await transfer.ExportAsync(ctx.PlayerId, message.Name, ct).ConfigureAwait(false);

        await PresetsReply.SendAsync(hotel, library, ctx, report, ct).ConfigureAwait(false);
    }
}

public sealed class PresetsDeleteHandler(IHotel hotel, PresetLibrary library)
    : IPluginMessageHandler<PresetsDeleteMessage>
{
    public async ValueTask HandleAsync(PresetsDeleteMessage message, PluginMessageContext ctx, CancellationToken ct)
    {
        string report;

        if (!await hotel.Players.HasPermissionAsync(ctx.PlayerId, PresetsReply.MANAGE_PERMISSION, ct).ConfigureAwait(false))
            report = "You may not delete presets.";
        else if (await library.GetAsync(message.Id, ct).ConfigureAwait(false) is not { } preset)
            report = "That preset is no longer in the library.";
        else
            report = await library.DeleteAsync(preset.Id, ct).ConfigureAwait(false)
                ? $"Deleted \"{preset.Name}\"."
                : "That preset is no longer in the library.";

        await PresetsReply.SendAsync(hotel, library, ctx, report, ct).ConfigureAwait(false);
    }
}
