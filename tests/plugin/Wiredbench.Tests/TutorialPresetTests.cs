using Turbo.Testing;
using Wiredbench.Presets;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// The tutorial rooms ship as G-Presets files beside the plugin (data/presets), each one listed in
/// <see cref="TutorialPresets.TUTORIALS"/>: they read as G-Presets files, and one imported into a
/// room is set up whole and passes the room check.
/// </summary>
public sealed class TutorialPresetTests
{
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    private static string Plugin()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            var plugin = Path.Combine(dir.FullName, "turbo-plugin");

            if (File.Exists(Path.Combine(plugin, "manifest.json")))
                return plugin;
        }

        throw new DirectoryNotFoundException("turbo-plugin was not found above the test's folder.");
    }

    private static string Read(string file) => File.ReadAllText(Path.Combine(Plugin(), file));

    [Fact]
    public void Every_tutorial_is_a_g_presets_file_with_wired_in_it()
    {
        foreach (var (name, file) in TutorialPresets.TUTORIALS)
        {
            var preset = GPresetFile.Parse(Read(file));

            Assert.True(preset.Boxes.Length > 0, $"{name} has no wired boxes.");
            Assert.True(name.Length <= PresetLibrary.MAX_NAME_LENGTH, $"{name} is too long a name.");
        }

        var listed = TutorialPresets.TUTORIALS.Select(x => Path.GetFileName(x.File)).Order();
        var shipped = Directory.GetFiles(Path.Combine(Plugin(), "data", "presets"), "*.json").Select(Path.GetFileName).Order();
        Assert.Equal(shipped, listed);
    }

    public static TheoryData<string> Files() => [.. TutorialPresets.TUTORIALS.Select(x => x.File)];

    [Theory]
    [MemberData(nameof(Files))]
    public async Task A_tutorial_imports_whole_and_passes_the_room_check(string file)
    {
        var hotel = new FakeHotel();
        var alice = hotel.Players.Add("alice", online: true);
        var room = hotel.Rooms.Add("Lab", alice);
        hotel.Rooms.Enter(room, alice);
        alice.Permissions.Add("command.giveitem");

        var json = Read(file);
        var preset = GPresetFile.Parse(json);

        foreach (var name in preset.Furni.Select(x => x.ClassName).Distinct())
            hotel.Inventory.AddFurniture(name);

        var result = await new PresetTransfer(hotel, null!).ImportAsync(alice, json, newRoom: false, "Lab", Ct);

        Assert.Contains($"Placed {preset.Furni.Length} of {preset.Furni.Length} furni.", result.Message);
        Assert.Contains($"Set up {preset.Boxes.Length} of {preset.Boxes.Length} wired boxes.", result.Message);

        var state = await new CheckRunHandler(hotel).RunAsync(alice.Id, Ct);
        Assert.Empty(state.Issues.Select(x => $"{x.Code} {x.Logic} ({x.X}, {x.Y}): {x.Message}"));
    }
}
