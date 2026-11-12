using System.Text.Json.Nodes;
using Wiredbench.Presets;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// Real G-Presets files, from the folders <c>WB_PRESET_SAMPLES</c> names (separated by the
/// system's path separator), as WiredBench's Python exchange tests read them. They are not kept in
/// the repository; with none named, the test is skipped.
/// </summary>
public sealed class GPresetSampleTests
{
    public static TheoryData<string> Samples()
    {
        var data = new TheoryData<string>();
        var folders = Environment.GetEnvironmentVariable("WB_PRESET_SAMPLES");

        // One placeholder row when none are named, which the skip below then skips.
        if (string.IsNullOrWhiteSpace(folders))
        {
            data.Add(string.Empty);

            return data;
        }

        foreach (var folder in folders.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        foreach (var file in Directory.EnumerateFiles(folder, "*.json").Order())
            data.Add(file);

        return data;
    }

    [Theory(SkipUnless = nameof(HasSamples), Skip = "Set WB_PRESET_SAMPLES to folders of G-Presets files.")]
    [MemberData(nameof(Samples))]
    public void A_real_file_comes_back_exactly(string path)
    {
        var json = File.ReadAllText(path);

        var file = GPresetFile.Parse(json);

        var written = file.ToJson();

        // WB_PRESET_DUMP: a folder to write each file as it came back, to diff a failure.
        if (Environment.GetEnvironmentVariable("WB_PRESET_DUMP") is { Length: > 0 } dump)
            File.WriteAllText(Path.Combine(dump, Path.GetFileName(path)), written);

        Assert.True(
            JsonNode.DeepEquals(JsonNode.Parse(json), JsonNode.Parse(written)),
            Path.GetFileName(path)
        );
    }

    public static bool HasSamples => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("WB_PRESET_SAMPLES"));
}
