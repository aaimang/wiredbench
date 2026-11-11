using Turbo.Contracts.Plugins;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// The panel's Parity page reads the committed report (turbo-plugin/data/parity.json, written by
/// scripts/parity.py) from the plugin's own files.
/// </summary>
public sealed class ParityReportTests
{
    private sealed class PluginFolder(string root) : IPluginFiles
    {
        public Stream? OpenRead(string path)
        {
            var full = Path.Combine(root, path);

            return File.Exists(full) ? File.OpenRead(full) : null;
        }
    }

    private static readonly string Plugin = Path.GetFullPath(
        Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "..", "turbo-plugin")
    );

    private static ParityReport Report() =>
        new(new PluginFolder(Directory.Exists(Plugin) ? Plugin : FindPlugin()));

    // The test project's output sits under /.build; the plugin folder is found from the repository root.
    private static string FindPlugin()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            var candidate = Path.Combine(dir.FullName, "turbo-plugin");

            if (File.Exists(Path.Combine(candidate, "manifest.json")))
                return candidate;
        }

        throw new DirectoryNotFoundException("turbo-plugin");
    }

    [Fact]
    public void The_summary_counts_the_committed_report()
    {
        var tiles = Report().Summary().Select(x => x.ToString()).ToList();

        Assert.Contains(tiles, x => x!.Contains("Client codes") && x.Contains("203"));
    }

    [Fact]
    public void The_codes_narrow_to_a_kind_and_to_those_with_a_gap()
    {
        var report = Report();

        Assert.Equal(29, report.Rows("trigger", false).Count);

        var gaps = report.Rows(null, true);
        Assert.Equal(6, gaps.Count);
        Assert.All(gaps, x => Assert.Equal("no furni in the hotel", x.Gaps));
        Assert.Contains(gaps, x => x is { Kind: "condition", Code: 44, Name: "USER_LEVEL" });
    }

    [Fact]
    public void Without_a_report_the_page_says_how_to_make_one()
    {
        var report = new ParityReport(new PluginFolder(Path.GetTempPath()));

        Assert.Contains("parity.py", Assert.Single(report.Summary()).ToString());
        Assert.Empty(report.Rows(null, false));
    }
}
