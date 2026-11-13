using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Hotel;
using Turbo.Contracts.Plugins;
using Turbo.Primitives.Commands;
using Turbo.Primitives.Players;
using Turbo.Primitives.Players.Permissions;
using Turbo.Primitives.Plugins.Messages;

namespace Wiredbench.Inventory;

// `:deleteinventory` deletes every furni in the player's own inventory, after two questions in two
// popups. The server keeps where each player is in the questions, so a client that sends a confirm
// out of turn, or late, deletes nothing.

/// <summary>Server to client: ask the player to confirm. <paramref name="Step"/> is 1 or 2 of 2.</summary>
[PluginMessage("wiredbench.inventory.ask")]
public sealed record InventoryAskMessage(int Step, int Count, int Seconds) : IPluginMessage;

/// <summary>Server to client: it is over: how many were deleted, and a line to show.</summary>
[PluginMessage("wiredbench.inventory.done")]
public sealed record InventoryDoneMessage(int Deleted, string Message) : IPluginMessage;

/// <summary>Client to server: yes, go on to the next question, or delete after the second.</summary>
[PluginMessage("wiredbench.inventory.confirm")]
public sealed record InventoryConfirmMessage() : IPluginMessage;

/// <summary>Client to server: no, leave the inventory as it is.</summary>
[PluginMessage("wiredbench.inventory.cancel")]
public sealed record InventoryCancelMessage() : IPluginMessage;

/// <summary>Where each player is in the questions, and the deleting itself.</summary>
public sealed class InventoryWipe(IHotel hotel)
{
    /// <summary>The movement log's cause for what this deletes.</summary>
    public const string CAUSE = "wiredbench.deleteinventory";

    /// <summary>How long a question waits for its answer before the whole thing is dropped.</summary>
    public static readonly TimeSpan WAIT = TimeSpan.FromSeconds(60);

    private readonly Dictionary<PlayerId, (int Step, DateTimeOffset Until)> _asked = [];
    private readonly Lock _lock = new();

    /// <summary>The first question. Answers false, asking nothing, when the inventory is empty.</summary>
    public async Task<bool> BeginAsync(PlayerId player, CancellationToken ct)
    {
        var count = (await hotel.Inventory.FurnitureOfAsync(player, ct).ConfigureAwait(false)).Count;

        if (count == 0)
        {
            await SendDoneAsync(player, 0, "Your inventory is already empty.", ct).ConfigureAwait(false);

            return false;
        }

        lock (_lock)
            _asked[player] = (1, hotel.Clock.GetUtcNow() + WAIT);

        await hotel.Players.SendAsync(player, new InventoryAskMessage(1, count, (int)WAIT.TotalSeconds), ct).ConfigureAwait(false);

        return true;
    }

    /// <summary>A yes: the second question after the first, the deleting after the second.</summary>
    public async Task ConfirmAsync(PlayerId player, CancellationToken ct)
    {
        int step;

        lock (_lock)
        {
            if (!_asked.TryGetValue(player, out var at) || at.Until < hotel.Clock.GetUtcNow())
            {
                _asked.Remove(player);

                return;
            }

            step = at.Step;

            if (step == 1)
                _asked[player] = (2, hotel.Clock.GetUtcNow() + WAIT);
            else
                _asked.Remove(player);
        }

        if (step == 1)
        {
            var count = (await hotel.Inventory.FurnitureOfAsync(player, ct).ConfigureAwait(false)).Count;

            await hotel.Players.SendAsync(player, new InventoryAskMessage(2, count, (int)WAIT.TotalSeconds), ct).ConfigureAwait(false);

            return;
        }

        var deleted = await hotel.Inventory.DeleteAllFurnitureAsync(player, CAUSE, ct).ConfigureAwait(false);

        await SendDoneAsync(player, deleted, deleted == 0 ? "Nothing was deleted." : $"Deleted {deleted} furni from your inventory.", ct).ConfigureAwait(false);
    }

    /// <summary>A no: forget the questions.</summary>
    public void Cancel(PlayerId player)
    {
        lock (_lock)
            _asked.Remove(player);
    }

    private Task SendDoneAsync(PlayerId player, int deleted, string message, CancellationToken ct) =>
        hotel.Players.SendAsync(player, new InventoryDoneMessage(deleted, message), ct);
}

public sealed class InventoryConfirmHandler(InventoryWipe wipe) : IPluginMessageHandler<InventoryConfirmMessage>
{
    public async ValueTask HandleAsync(InventoryConfirmMessage message, PluginMessageContext ctx, CancellationToken ct) =>
        await wipe.ConfirmAsync(ctx.PlayerId, ct).ConfigureAwait(false);
}

public sealed class InventoryCancelHandler(InventoryWipe wipe) : IPluginMessageHandler<InventoryCancelMessage>
{
    public ValueTask HandleAsync(InventoryCancelMessage message, PluginMessageContext ctx, CancellationToken ct)
    {
        wipe.Cancel(ctx.PlayerId);

        return ValueTask.CompletedTask;
    }
}

/// <summary><c>:deleteinventory</c>: opens the first of two popups; nothing is deleted yet.</summary>
[Command("deleteinventory", Description = "Delete every furni in your inventory, after two confirmations")]
[RequiresPermission(InventoryPermissions.DELETE)]
public sealed class DeleteInventoryCommand(InventoryWipe wipe) : ICommand<NoArguments>
{
    public const string ASKED = "asked";
    public const string EMPTY = "empty";

    public IReadOnlyDictionary<string, string> DefaultTexts { get; } =
        new Dictionary<string, string>
        {
            [ASKED] = "Confirm in the window that opened: nothing is deleted until you have said yes twice.",
            [EMPTY] = "Your inventory is already empty.",
        };

    public async ValueTask<CommandResult> ExecuteAsync(ICommandContext ctx, NoArguments arguments, CancellationToken ct) =>
        await wipe.BeginAsync(ctx.Action.PlayerId, ct).ConfigureAwait(false)
            ? CommandResult.Done(ASKED)
            : CommandResult.Done(EMPTY);
}

/// <summary>Who may use <c>:deleteinventory</c> (on their own inventory): everyone, unless a rank is denied it.</summary>
public sealed class InventoryPermissions : IPermissionNodeSource
{
    public const string DELETE = "wiredbench.command.deleteinventory";

    public string? Prefix => "wiredbench";

    public IEnumerable<PermissionNodeDefinition> Nodes =>
        [new(DELETE, "Delete everything in your own inventory with :deleteinventory", GrantedByDefault: true)];

    public IEnumerable<PermissionMetaDefinition> MetaKeys => [];
}
