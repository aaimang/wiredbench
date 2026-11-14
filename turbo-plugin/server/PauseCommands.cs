using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Hotel;
using Turbo.Primitives.Commands;
using Turbo.Primitives.Players.Permissions;

namespace Wiredbench;

/// <summary><c>:pause</c>, <c>:pause on</c> or <c>:pause off</c>.</summary>
public sealed record PauseArguments(
    [CommandParameter(Description = "on or off; left out, it flips the pause")] string? State = null
);

/// <summary><c>:step</c> or <c>:step 3</c>.</summary>
public sealed record StepArguments(
    [CommandParameter(Description = "how many effects to run; 1 when left out")] int Count = 1
);

/// <summary>
/// <c>:pause</c> holds the effects of the room's wired, <c>:pause off</c> lets them run on: the
/// Trace window's Pause and Resume, from chat. The node lets a rank type it; whether the player
/// may change this room's wired is still the hotel's to say.
/// </summary>
[Command("pause", Description = "Hold the room's wired effects: :pause [on|off]")]
[RequiresPermission(PausePermissions.PAUSE)]
public sealed class PauseCommand(IHotel hotel) : ICommand<PauseArguments>
{
    public const string PAUSED = "paused";
    public const string RESUMED = "resumed";
    public const string BAD_STATE = "bad_state";
    public const string REFUSED = "refused";

    public IReadOnlyDictionary<string, string> DefaultTexts { get; } =
        new Dictionary<string, string>
        {
            [PAUSED] = "Wired paused: effects wait. :step runs the next one, :pause off lets them run.",
            [RESUMED] = "Wired running again.",
            [BAD_STATE] = "Use :pause, :pause on or :pause off.",
            [REFUSED] = "You may not change the wired of this room.",
        };

    public async ValueTask<CommandResult> ExecuteAsync(ICommandContext ctx, PauseArguments arguments, CancellationToken ct)
    {
        var state = arguments.State?.Trim();

        bool paused;

        if (string.IsNullOrEmpty(state))
        {
            if (await hotel.Wired.GetPauseAsync(ctx.RoomId, ctx.Action.PlayerId, ct).ConfigureAwait(false) is not { } now)
                return CommandResult.Fail(REFUSED);

            paused = !now.Paused;
        }
        else if (state.Equals("on", StringComparison.OrdinalIgnoreCase))
            paused = true;
        else if (state.Equals("off", StringComparison.OrdinalIgnoreCase))
            paused = false;
        else
            return CommandResult.Fail(BAD_STATE);

        return await hotel.Wired.SetPausedAsync(ctx.RoomId, ctx.Action.PlayerId, paused, ct).ConfigureAwait(false)
            ? CommandResult.Done(paused ? PAUSED : RESUMED)
            : CommandResult.Fail(REFUSED);
    }
}

/// <summary><c>:step</c> runs the next held effect, <c>:step 3</c> the next three.</summary>
[Command("step", Description = "Run held wired effects: :step [count]")]
[RequiresPermission(PausePermissions.STEP)]
public sealed class StepCommand(IHotel hotel) : ICommand<StepArguments>
{
    /// <summary>The Trace window asks for the same few at most.</summary>
    public const int MAX = 50;

    public const string STEPPED = "stepped";
    public const string NOT_PAUSED = "not_paused";
    public const string REFUSED = "refused";

    public IReadOnlyDictionary<string, string> DefaultTexts { get; } =
        new Dictionary<string, string>
        {
            [STEPPED] = "Ran %0% effect(s); %1% still waiting.",
            [NOT_PAUSED] = "The wired is not paused: :pause first.",
            [REFUSED] = "You may not change the wired of this room.",
        };

    public async ValueTask<CommandResult> ExecuteAsync(ICommandContext ctx, StepArguments arguments, CancellationToken ct)
    {
        if (await hotel.Wired.GetPauseAsync(ctx.RoomId, ctx.Action.PlayerId, ct).ConfigureAwait(false) is not { } before)
            return CommandResult.Fail(REFUSED);

        if (!before.Paused)
            return CommandResult.Fail(NOT_PAUSED);

        var after = await hotel
            .Wired.StepAsync(ctx.RoomId, ctx.Action.PlayerId, Math.Clamp(arguments.Count, 1, MAX), ct)
            .ConfigureAwait(false);

        return after is null
            ? CommandResult.Fail(REFUSED)
            : CommandResult.Done(STEPPED, after.Stepped.ToString(), after.Held.Length.ToString());
    }
}

/// <summary>Who may type <c>:pause</c> and <c>:step</c>: everyone, unless a rank is denied them.</summary>
public sealed class PausePermissions : IPermissionNodeSource
{
    public const string PAUSE = "wiredbench.command.pause";
    public const string STEP = "wiredbench.command.step";

    public string? Prefix => "wiredbench";

    public IEnumerable<PermissionNodeDefinition> Nodes =>
        [
            new(PAUSE, "Hold the room's wired with :pause", GrantedByDefault: true),
            new(STEP, "Step through held wired effects with :step", GrantedByDefault: true),
        ];

    public IEnumerable<PermissionMetaDefinition> MetaKeys => [];
}
