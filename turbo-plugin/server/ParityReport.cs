using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Turbo.Contracts.Plugins;

namespace Wiredbench;

/// <summary>One wired code of the parity report as the panel lists it.</summary>
public sealed record ParityRow(
    string Kind,
    int Code,
    string Name,
    bool Client,
    int Editors,
    string Boxes,
    string Logics,
    string Furni,
    string Gaps
);

/// <summary>
/// The WIRED box parity report (data/parity.json, written by <c>python scripts/parity.py</c>):
/// every wired code the Habbo client knows against Turbo's boxes, nitro-next's editors and the
/// hotel's furni. Read from the plugin's own files each time the panel asks, so a new report shows
/// as soon as the plugin reloads.
/// </summary>
public sealed class ParityReport(IPluginFiles files)
{
    private const string FILE = "data/parity.json";

    /// <summary>The report as the tiles show it: label and value; empty without a report.</summary>
    public IReadOnlyList<object> Summary()
    {
        if (Read() is not { } report)
            return [new { label = "Report", value = "Run python scripts/parity.py" }];

        var summary = report.GetProperty("summary");
        var gaps = summary.GetProperty("gaps");
        var source = report.GetProperty("clientSource");
        var hotel = report.GetProperty("hotelChecked").GetBoolean();

        return
        [
            new { label = "Client codes", value = summary.GetProperty("client").GetInt32().ToString() },
            new { label = "With a Turbo box", value = summary.GetProperty("boxes").GetInt32().ToString() },
            new { label = "With a Nitro editor", value = summary.GetProperty("editors").GetInt32().ToString() },
            new
            {
                label = "Boxes without furni",
                value = hotel ? gaps.GetProperty("boxWithoutFurni").GetInt32().ToString() : "not checked",
            },
            new { label = "Codes claimed twice", value = gaps.GetProperty("codeClaimedTwice").GetInt32().ToString() },
            new
            {
                label = "Client build",
                value = source.TryGetProperty("file", out var file) ? file.GetString() ?? "?" : "?",
            },
        ];
    }

    /// <summary>Every code, newest kind order, narrowed by kind and to the ones with a gap.</summary>
    public IReadOnlyList<ParityRow> Rows(string? kind, bool gapsOnly)
    {
        if (Read() is not { } report)
            return [];

        var gapsByCode = new Dictionary<(string, int), List<string>>();

        foreach (var gap in report.GetProperty("gaps").EnumerateObject())
        {
            foreach (var found in gap.Value.EnumerateArray())
            {
                var key = (found.GetProperty("kind").GetString() ?? "", found.GetProperty("code").GetInt32());

                if (!gapsByCode.TryGetValue(key, out var list))
                    gapsByCode[key] = list = [];

                list.Add(GapLabel(gap.Name));
            }
        }

        var rows = new List<ParityRow>();

        foreach (var k in report.GetProperty("kinds").EnumerateObject())
        {
            if (!string.IsNullOrEmpty(kind) && !string.Equals(k.Name, kind, StringComparison.OrdinalIgnoreCase))
                continue;

            foreach (var row in k.Value.GetProperty("rows").EnumerateArray())
            {
                var code = row.GetProperty("code").GetInt32();
                var gaps = gapsByCode.GetValueOrDefault((k.Name, code)) ?? [];

                if (gapsOnly && gaps.Count == 0)
                    continue;

                var boxes = row.GetProperty("boxes").EnumerateArray().ToList();
                var furni = row.GetProperty("furni");

                rows.Add(
                    new ParityRow(
                        k.Name,
                        code,
                        row.TryGetProperty("name", out var name) ? name.GetString() ?? "" : "",
                        row.GetProperty("client").GetArrayLength() > 0,
                        row.GetProperty("editors").GetArrayLength(),
                        string.Join(", ", boxes.Select(x => x.GetProperty("box").GetString())),
                        string.Join(", ", boxes.Select(x => x.GetProperty("logic").GetString()).Where(x => x is not null)),
                        furni.ValueKind == JsonValueKind.Array
                            ? string.Join(", ", furni.EnumerateArray().Select(x => x.GetString()))
                            : "not checked",
                        string.Join(", ", gaps)
                    )
                );
            }
        }

        return rows;
    }

    private static string GapLabel(string gap) =>
        gap switch
        {
            "clientWithoutBox" => "no Turbo box",
            "clientWithoutEditor" => "no Nitro editor",
            "boxWithoutClient" => "box the client does not know",
            "editorWithoutClient" => "editor the client does not know",
            "codeClaimedTwice" => "claimed by two boxes",
            "boxWithoutFurni" => "no furni in the hotel",
            _ => gap,
        };

    private JsonElement? Read()
    {
        using var stream = files.OpenRead(FILE);

        if (stream is null)
            return null;

        using var document = JsonDocument.Parse(stream);

        return document.RootElement.Clone();
    }
}
