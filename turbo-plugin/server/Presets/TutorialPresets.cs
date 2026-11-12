using System.Collections.Generic;
using System.Collections.Immutable;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Plugins;

namespace Wiredbench.Presets;

/// <summary>
/// The example rooms WiredBench's own app taught with, as G-Presets files in data/presets: a
/// switch, a signal relay, a score counter, a visitor view and baikal's time tracking system.
/// The library gets each one it does not have by name as the plugin loads, so a deleted one comes
/// back at the next load.
/// </summary>
public sealed class TutorialPresets(IPluginFiles files, PresetLibrary library)
{
    /// <summary>Each tutorial's name in the library, and its file.</summary>
    public static readonly ImmutableArray<(string Name, string File)> TUTORIALS =
    [
        ("Tutorial: switch flips a switch", "data/presets/tutorial-switch-flip.json"),
        ("Tutorial: signal relay", "data/presets/tutorial-signal-relay.json"),
        ("Tutorial: score counter", "data/presets/tutorial-score-counter.json"),
        ("Tutorial: visitor view test", "data/presets/tutorial-visitor-view.json"),
        ("Tutorial: time tracking", "data/presets/tutorial-time-tracking.json"),
    ];

    /// <summary>Adds the tutorials the library lacks; the names of those added.</summary>
    public async Task<IReadOnlyList<string>> AddMissingAsync(CancellationToken ct)
    {
        var have = (await library.ListAsync(ct).ConfigureAwait(false)).Select(x => x.Name).ToHashSet();
        var added = new List<string>();

        foreach (var (name, file) in TUTORIALS)
        {
            if (have.Contains(name) || files.OpenRead(file) is not { } stream)
                continue;

            string json;

            using (var reader = new StreamReader(stream))
                json = await reader.ReadToEndAsync(ct).ConfigureAwait(false);

            await library.AddAsync(name, json, 0, ct).ConfigureAwait(false);
            added.Add(name);
        }

        return added;
    }
}
