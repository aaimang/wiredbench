using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Plugins;

namespace Wiredbench.Presets;

/// <summary>
/// The example rooms WiredBench's own app taught with, as G-Presets files in data/presets: a
/// switch, a signal relay, a score counter, a visitor view and baikal's time tracking system.
/// The library gets each one it does not have by name as the plugin loads, so a deleted one comes
/// back at the next load. A copy that is still exactly an earlier version of a tutorial (see
/// <see cref="SUPERSEDED"/>) is replaced by the current file; one that was edited is left alone.
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

    /// <summary>
    /// SHA-256 of each earlier file a tutorial shipped as, by tutorial file. 0.13.0: the variables
    /// were made without "has value", so a score or counter had nothing to give or change.
    /// </summary>
    private static readonly ImmutableDictionary<string, ImmutableHashSet<string>> SUPERSEDED =
        new Dictionary<string, ImmutableHashSet<string>>
        {
            ["data/presets/tutorial-score-counter.json"] = ["b9f5dcb8d904835d4228abb2e604f431e4d5718238dc64357848ab9dc48dfa52"],
            ["data/presets/tutorial-time-tracking.json"] = ["5b6a408e1bc3ff6efa238ff863122a4e7667efe1a17241283140d43f79adfacd"],
            ["data/presets/tutorial-visitor-view.json"] = ["4bdfaa8f0b2962a0f1843894d1abc33a4f159c53c72cc7e6902e6645ef4cd522"],
        }.ToImmutableDictionary();

    /// <summary>Adds the tutorials the library lacks and refreshes outdated ones; the names of those added or refreshed.</summary>
    public async Task<IReadOnlyList<string>> AddMissingAsync(CancellationToken ct)
    {
        var listed = await library.ListAsync(ct).ConfigureAwait(false);
        var have = listed.Select(x => x.Name).ToHashSet();
        var added = new List<string>();

        foreach (var (name, file) in TUTORIALS)
        {
            if (files.OpenRead(file) is not { } stream)
                continue;

            string json;

            using (var reader = new StreamReader(stream))
                json = await reader.ReadToEndAsync(ct).ConfigureAwait(false);

            if (!have.Contains(name))
            {
                await library.AddAsync(name, json, 0, ct).ConfigureAwait(false);
                added.Add(name);

                continue;
            }

            if (!SUPERSEDED.TryGetValue(file, out var old))
                continue;

            foreach (var info in listed.Where(x => x.Name == name))
            {
                var row = await library.GetAsync(info.Id, ct).ConfigureAwait(false);

                if (row is null || !old.Contains(Hash(row.Json)))
                    continue;

                await library.UpdateAsync(info.Id, null, json, ct).ConfigureAwait(false);
                added.Add(name);
            }
        }

        return added;
    }

    private static string Hash(string json) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(json))).ToLowerInvariant();
}
