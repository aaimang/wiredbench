using Turbo.Primitives.Action;
using Turbo.Primitives.Commands;
using Turbo.Primitives.Rooms;
using Turbo.Primitives.Players;
using Turbo.Primitives.Players.Permissions;
using Turbo.Primitives.Rooms.Object.Avatars;
using Turbo.Testing;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>:pause and :step are the Trace window's Pause, Resume and Step, typed in chat.</summary>
public sealed class PauseCommandTests
{
    private sealed class Typed(PlayerId player, RoomId room) : ICommandContext
    {
        public ActionContext Action { get; } = ActionContext.CreateForPlayer(player, room);

        public IRoomPlayer Executor => throw new NotSupportedException();

        public RoomId RoomId { get; } = room;

        public ICommandRoom Room => throw new NotSupportedException();

        public string ArgumentText => string.Empty;
    }

    private readonly FakeHotel _hotel = new();
    private readonly FakePlayer _alice;
    private readonly FakeRoom _room;

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    public PauseCommandTests()
    {
        _alice = _hotel.Players.Add("alice", online: true);
        _room = _hotel.Rooms.Add("Lab", _alice);
        _hotel.Rooms.Enter(_room, _alice);
    }

    private Typed Ctx => new(_alice.Id, _room.Id);

    private async Task<bool> PausedAsync() => (await _hotel.Wired.GetPauseAsync(_room.Id, _alice.Id, Ct))!.Paused;

    [Fact]
    public async Task Pause_flips_the_pause_and_on_and_off_set_it()
    {
        var pause = new PauseCommand(_hotel);

        Assert.Equal(PauseCommand.PAUSED, (await pause.ExecuteAsync(Ctx, new PauseArguments(), Ct)).Status);
        Assert.True(await PausedAsync());

        Assert.Equal(PauseCommand.RESUMED, (await pause.ExecuteAsync(Ctx, new PauseArguments(), Ct)).Status);
        Assert.False(await PausedAsync());

        await pause.ExecuteAsync(Ctx, new PauseArguments("ON"), Ct);
        Assert.True(await PausedAsync());

        await pause.ExecuteAsync(Ctx, new PauseArguments("off"), Ct);
        Assert.False(await PausedAsync());
    }

    [Fact]
    public async Task Pause_with_a_word_it_does_not_know_changes_nothing()
    {
        var result = await new PauseCommand(_hotel).ExecuteAsync(Ctx, new PauseArguments("maybe"), Ct);

        Assert.Equal(PauseCommand.BAD_STATE, result.Status);
        Assert.False(await PausedAsync());
    }

    [Fact]
    public async Task Step_waits_for_a_pause()
    {
        var result = await new StepCommand(_hotel).ExecuteAsync(Ctx, new StepArguments(), Ct);

        Assert.Equal(StepCommand.NOT_PAUSED, result.Status);
    }

    [Fact]
    public async Task Step_in_a_paused_room_reports_what_it_ran()
    {
        await new PauseCommand(_hotel).ExecuteAsync(Ctx, new PauseArguments("on"), Ct);

        var result = await new StepCommand(_hotel).ExecuteAsync(Ctx, new StepArguments(3), Ct);

        Assert.Equal(StepCommand.STEPPED, result.Status);
    }
}

/// <summary>
/// The hotel refuses to load a plugin with a command that names no permission node, which took
/// the whole plugin down once; so every command the plugin has names one, and a source offers it.
/// </summary>
public sealed class CommandDeclarationTests
{
    private static readonly System.Reflection.Assembly PLUGIN = typeof(PauseCommand).Assembly;

    private static IEnumerable<Type> Commands =>
        PLUGIN.GetTypes().Where(x => x.GetCustomAttributes(typeof(CommandAttribute), false).Length > 0);

    [Fact]
    public void Every_command_names_a_permission_node()
    {
        Assert.NotEmpty(Commands);

        foreach (var command in Commands)
            Assert.True(
                command.GetCustomAttributes(typeof(RequiresPermissionAttribute), false).Length > 0,
                $"{command.Name} has no [RequiresPermission]"
            );
    }

    [Fact]
    public void Every_node_a_command_names_is_offered_by_a_source()
    {
        var offered = PLUGIN
            .GetTypes()
            .Where(x => typeof(IPermissionNodeSource).IsAssignableFrom(x) && x is { IsAbstract: false, IsInterface: false })
            .SelectMany(x => ((IPermissionNodeSource)Activator.CreateInstance(x)!).Nodes)
            .Select(x => x.Node)
            .ToHashSet();

        foreach (var command in Commands)
        foreach (var node in command.GetCustomAttributes(typeof(RequiresPermissionAttribute), false).Cast<RequiresPermissionAttribute>().SelectMany(x => x.Nodes))
            Assert.True(offered.Contains(node), $"{command.Name} needs {node}, which no source offers");
    }
}
