using Turbo.Primitives.Rooms.Snapshots.Wired;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>The panel's WIRED usage figures: per room, filtered, and summed.</summary>
public sealed class WiredUsageTests
{
    private static WiredRoomUsageSnapshot Room(int id, double cost, long executions, long ms, bool heavy = false) =>
        new()
        {
            RoomId = id,
            Stats = new WiredRoomStatsSnapshot
            {
                ExecutionCost = cost,
                ExecutionCostCap = 4687.5,
                IsHeavy = heavy,
                FloorItemCount = 10,
                FloorItemCap = 4000,
                WallItemCount = 0,
                WallItemCap = 4000,
                PermanentFurniVariables = 0,
                MaxPermanentFurniVariables = 23,
                PermanentUserVariables = 0,
                MaxPermanentUserVariables = 93,
                PermanentGlobalVariables = 0,
                MaxPermanentGlobalVariables = 70,
            },
            WiredBoxes = 12,
            Stacks = 3,
            Executions = executions,
            ExecutionMsTotal = ms,
            ExecutionMsMax = 9,
            Errors = 1,
            TraceOn = false,
        };

    [Fact]
    public void A_row_gives_usage_as_a_share_of_the_cap_and_the_average_execution()
    {
        var row = WiredUsage.ToRow(Room(7, 3750, 40, 100), "Lab");

        Assert.Equal(80, row.UsagePercent);
        Assert.Equal(2.5, row.AverageMs);
        Assert.Equal("Lab", row.Name);
    }

    [Fact]
    public void The_filter_matches_a_room_id_or_part_of_a_name()
    {
        var rows = new[] { WiredUsage.ToRow(Room(7, 0, 0, 0), "Wired Lab"), WiredUsage.ToRow(Room(17, 0, 0, 0), "Cafe") };

        Assert.Equal([7], WiredUsage.Filter(rows, "7").Select(x => x.RoomId));
        Assert.Equal([7], WiredUsage.Filter(rows, "lab").Select(x => x.RoomId));
        Assert.Equal([17], WiredUsage.Filter(rows, "caf").Select(x => x.RoomId));
        Assert.Equal(2, WiredUsage.Filter(rows, " ").Count());
    }

    [Theory]
    [InlineData(850, "850 ms")]
    [InlineData(12_400, "12.4 s")]
    [InlineData(185_000, "3 min 05 s")]
    public void Durations_read_as_staff_read_them(long ms, string text) => Assert.Equal(text, WiredUsage.Duration(ms));

    [Fact]
    public void The_summary_sums_the_rooms_and_counts_those_near_their_cap()
    {
        var rows = new[]
        {
            WiredUsage.ToRow(Room(1, 4000, 10, 30, heavy: true), "A"),
            WiredUsage.ToRow(Room(2, 100, 30, 10), "B"),
        };

        var summary = WiredUsage.Summary(rows).Select(x => x.ToString()).ToList();

        Assert.Contains(summary, x => x!.Contains("Wired boxes") && x.Contains("24"));
        Assert.Contains(summary, x => x!.Contains("Executions") && x.Contains("40"));
        Assert.Contains(summary, x => x!.Contains("Average execution") && x.Contains("1 ms"));
        Assert.Contains(summary, x => x!.Contains("Heavy rooms") && x.Contains("= 1"));
        Assert.Contains(summary, x => x!.Contains("usage cap") && x.Contains("= 1"));
    }
}
