using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Turbo.Contracts.Hotel;
using Turbo.Primitives.Rooms.Snapshots.Wired;

namespace Wiredbench;

/// <summary>One loaded room's wired load as the panel lists it.</summary>
public sealed record WiredUsageRow(
    int RoomId,
    string Name,
    int Boxes,
    int Stacks,
    double UsagePercent,
    bool Heavy,
    long Executions,
    long RunMs,
    double AverageMs,
    long LongestMs,
    int Errors,
    bool TraceOn
);

/// <summary>
/// WIRED use across the hotel's loaded rooms, for the panel's Wiredbench page: each room's boxes,
/// stacks, usage against its cap, executions and their server time since it loaded, and errors
/// (<c>IHotelWired.UsageAsync</c>, the wiredbench-seams change in turbo-cloud).
/// </summary>
public sealed class WiredUsage(IHotel hotel)
{
    /// <summary>A room whose usage is at least this share of its cap is counted as near it.</summary>
    public const double NEAR_CAP_PERCENT = 75;

    /// <summary>
    /// The loaded rooms with wired, busiest first (server time, then executions); <paramref name="filter"/>
    /// keeps rooms whose id is it or whose name holds it.
    /// </summary>
    public async Task<IReadOnlyList<WiredUsageRow>> RoomsAsync(string? filter, CancellationToken ct)
    {
        var usage = await hotel.Wired.UsageAsync(ct).ConfigureAwait(false);
        var rows = new List<WiredUsageRow>(usage.Length);

        foreach (var room in usage)
        {
            if (room.WiredBoxes == 0)
                continue;

            var name = (await hotel.Rooms.GetAsync(room.RoomId, ct).ConfigureAwait(false))?.Name ?? string.Empty;

            rows.Add(ToRow(room, name));
        }

        return [.. Filter(rows, filter).OrderByDescending(x => x.RunMs).ThenByDescending(x => x.Executions)];
    }

    /// <summary>The figures over <paramref name="rows"/>, as the panel's stats block lists them.</summary>
    public static IReadOnlyList<object> Summary(IReadOnlyList<WiredUsageRow> rows)
    {
        var executions = rows.Sum(x => x.Executions);
        var runMs = rows.Sum(x => x.RunMs);

        return
        [
            new { label = "Rooms with wired", value = rows.Count.ToString(CultureInfo.InvariantCulture) },
            new { label = "Wired boxes", value = rows.Sum(x => x.Boxes).ToString(CultureInfo.InvariantCulture) },
            new { label = "Stacks", value = rows.Sum(x => x.Stacks).ToString(CultureInfo.InvariantCulture) },
            new { label = "Executions", value = executions.ToString(CultureInfo.InvariantCulture) },
            new { label = "Wired running time", value = Duration(runMs) },
            new
            {
                label = "Average execution",
                value = executions > 0 ? $"{(double)runMs / executions:0.##} ms" : "-",
            },
            new { label = "Longest execution", value = rows.Count > 0 ? $"{rows.Max(x => x.LongestMs)} ms" : "-" },
            new { label = "Heavy rooms", value = rows.Count(x => x.Heavy).ToString(CultureInfo.InvariantCulture) },
            new
            {
                label = $"Rooms at {NEAR_CAP_PERCENT:0}% of their usage cap",
                value = rows.Count(x => x.UsagePercent >= NEAR_CAP_PERCENT).ToString(CultureInfo.InvariantCulture),
            },
            new { label = "Wired errors", value = rows.Sum(x => x.Errors).ToString(CultureInfo.InvariantCulture) },
        ];
    }

    public static WiredUsageRow ToRow(WiredRoomUsageSnapshot room, string name)
    {
        var cap = room.Stats.ExecutionCostCap;

        return new WiredUsageRow(
            room.RoomId,
            name,
            room.WiredBoxes,
            room.Stacks,
            cap > 0 ? Math.Round(room.Stats.ExecutionCost * 100 / cap, 1) : 0,
            room.Stats.IsHeavy,
            room.Executions,
            room.ExecutionMsTotal,
            room.Executions > 0 ? Math.Round((double)room.ExecutionMsTotal / room.Executions, 2) : 0,
            room.ExecutionMsMax,
            room.Errors,
            room.TraceOn
        );
    }

    public static IEnumerable<WiredUsageRow> Filter(IEnumerable<WiredUsageRow> rows, string? filter)
    {
        filter = filter?.Trim();

        if (string.IsNullOrEmpty(filter))
            return rows;

        return int.TryParse(filter, NumberStyles.None, CultureInfo.InvariantCulture, out var id)
            ? rows.Where(x => x.RoomId == id || x.Name.Contains(filter, StringComparison.OrdinalIgnoreCase))
            : rows.Where(x => x.Name.Contains(filter, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>Milliseconds as staff read them: "850 ms", "12.4 s", "3 min 05 s".</summary>
    public static string Duration(long ms) =>
        ms switch
        {
            < 1000 => $"{ms} ms",
            < 60_000 => string.Create(CultureInfo.InvariantCulture, $"{ms / 1000.0:0.#} s"),
            _ => $"{ms / 60_000} min {ms / 1000 % 60:00} s",
        };
}
