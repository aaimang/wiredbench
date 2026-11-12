using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Primitives.Commands;
using Turbo.Primitives.Players.Permissions;

namespace Wiredbench.Looks;

/// <summary><c>:copy &lt;name&gt; [hotel]</c>, or <c>:copy help</c>.</summary>
public sealed record CopyArguments(
    [CommandParameter(Description = "the Habbo's name, or help", MaxLength = 32)] string Name,
    [CommandParameter(Description = "COM, BR, TR, DE, ES, FI, FR, IT or NL")] string? Hotel = null
);

/// <summary>
/// Wear a Habbo's look: <c>:copy GenzX COM</c> reads GenzX's figure from Habbo.com, dresses the
/// player in it and keeps it in their wardrobe. The lookup runs after the command answers, so the
/// room never waits on another site (<see cref="LookCopier"/>); its result is whispered.
/// </summary>
[Command("copy", Description = "Wear a Habbo's look: :copy <name> <COM|BR|FR|ES...>")]
[RequiresPermission(LookPermissions.COPY)]
public sealed class CopyCommand(LookCopier copier) : ICommand<CopyArguments>
{
    public const string HELP = "help";
    public const string LOOKING = "looking";
    public const string UNKNOWN_HOTEL = "unknown_hotel";
    public const string BAD_NAME = "bad_name";
    public const string BUSY = "busy";

    private static readonly string CODES = string.Join(", ", HabboLookup.HOTELS.Select(x => x.Code));

    public IReadOnlyDictionary<string, string> DefaultTexts { get; } =
        new Dictionary<string, string>
        {
            [HELP] = $":copy <name> <hotel> wears a Habbo's look and keeps it in your wardrobe. Hotels: {CODES} (COM when left out). Example: :copy GenzX COM",
            [LOOKING] = "Looking up %0% on %1%...",
            [UNKNOWN_HOTEL] = $"There is no Habbo hotel '%0%'. Use one of {CODES}.",
            [BAD_NAME] = "'%0%' is not a Habbo name.",
            [BUSY] = "Wait a moment: your last :copy is still going or just ended.",
        };

    public ValueTask<CommandResult> ExecuteAsync(ICommandContext ctx, CopyArguments arguments, CancellationToken ct)
    {
        var name = arguments.Name.Trim();

        if (name.Equals(HELP, StringComparison.OrdinalIgnoreCase) && arguments.Hotel is null)
            return ValueTask.FromResult(CommandResult.Done(HELP));

        if (HabboLookup.Hotel(arguments.Hotel) is not { } habbo)
            return ValueTask.FromResult(CommandResult.Fail(UNKNOWN_HOTEL, arguments.Hotel ?? string.Empty));

        if (!IsHabboName(name))
            return ValueTask.FromResult(CommandResult.Fail(BAD_NAME, name));

        return ValueTask.FromResult(
            copier.TryStart(ctx.Action.PlayerId, ctx.RoomId, habbo, name)
                ? CommandResult.Done(LOOKING, name, habbo.Name)
                : CommandResult.Fail(BUSY)
        );
    }

    /// <summary>A name Habbo could have: 1 to 32 letters, digits and the marks its names use.</summary>
    public static bool IsHabboName(string name) =>
        name.Length is > 0 and <= 32 && name.All(c => char.IsLetterOrDigit(c) || "-=?!@:.,_~".Contains(c));
}

/// <summary>Who may use <c>:copy</c>: everyone, unless a rank is denied it.</summary>
public sealed class LookPermissions : IPermissionNodeSource
{
    public const string COPY = "wiredbench.command.copy";

    public string? Prefix => "wiredbench";

    public IEnumerable<PermissionNodeDefinition> Nodes =>
        [new(COPY, "Wear a Habbo's look with :copy", GrantedByDefault: true)];

    public IEnumerable<PermissionMetaDefinition> MetaKeys => [];
}
