using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Plugins;
using Turbo.Primitives.Plugins.Messages;

namespace Wiredbench;

// What the client module and the plugin say to each other: named messages (turbo-cloud
// docs/plugin-messages.md). The client reads and sends them by name (client/src/messages.ts); the
// fields are the record's, in order, camelCase on the client.

/// <summary>Client to server: the Wiredbench window opened and wants the plugin's status.</summary>
[PluginMessage("wiredbench.hello")]
public sealed record HelloMessage() : IPluginMessage;

/// <summary>Server to client: the plugin's version and the player it answered.</summary>
[PluginMessage("wiredbench.status")]
public sealed record StatusMessage(string Version, int PlayerId) : IPluginMessage;

/// <summary>Answers the session that asked; found as the plugin loads.</summary>
public sealed class HelloHandler(PluginManifest manifest) : IPluginMessageHandler<HelloMessage>
{
    public async ValueTask HandleAsync(
        HelloMessage message,
        PluginMessageContext ctx,
        CancellationToken ct
    ) =>
        await ctx.ReplyAsync(new StatusMessage(manifest.Version, ctx.PlayerId.Value), ct)
            .ConfigureAwait(false);
}
