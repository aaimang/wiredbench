using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Hotel;
using Turbo.Contracts.Plugins;
using Turbo.Primitives.Plugins.Messages;

namespace Wiredbench;

// What the client module and the plugin say to each other: named messages (turbo-cloud
// docs/plugin-messages.md). The client reads and sends them by name (client/src/messages.ts); the
// fields are the record's, in order, camelCase on the client.

/// <summary>Client to server: the Wiredbench window opened and wants the plugin's status.</summary>
[PluginMessage("wiredbench.hello")]
public sealed record HelloMessage() : IPluginMessage;

/// <summary>Server to client: the plugin's version and the player it answered, by id and name.</summary>
[PluginMessage("wiredbench.status")]
public sealed record StatusMessage(string Version, int PlayerId, string PlayerName) : IPluginMessage;

/// <summary>Answers the session that asked; found as the plugin loads.</summary>
public sealed class HelloHandler(PluginManifest manifest, IHotel hotel) : IPluginMessageHandler<HelloMessage>
{
    public async ValueTask HandleAsync(
        HelloMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    )
    {
        var player = await hotel.Players.GetAsync(ctx.PlayerId, ct).ConfigureAwait(false);

        await ctx.ReplyAsync(
                new StatusMessage(manifest.Version, ctx.PlayerId.Value, player?.Name ?? string.Empty),
                ct
            )
            .ConfigureAwait(false);
    }
}
