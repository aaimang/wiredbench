using System.Text.Json.Nodes;
using Wiredbench.Presets;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// G-Presets files read and written back. The sample is WiredBench's own made-up preset
/// (backend/tests/test_exchange.py): the shapes seen in real files, with fields nobody knows
/// (<c>somethingNew</c>, an add-on's <c>futureField</c>, a box with no furni), which must survive.
/// </summary>
public sealed class GPresetFileTests
{
    private static string Sample() =>
        File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "fixtures", "odd-fields.gpreset.json"));

    [Fact]
    public void An_untouched_file_comes_back_exactly()
    {
        var json = Sample();

        var written = GPresetFile.Parse(json).ToJson();

        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(json), JsonNode.Parse(written)), written);
    }

    [Fact]
    public void The_furni_and_boxes_are_read_in_the_file_s_terms()
    {
        var file = GPresetFile.Parse(Sample());

        Assert.Equal(6, file.Furni.Length);
        Assert.Equal("000\r000\r000", file.FloorPlan);

        var fridge = file.Furni.Single(x => x.Id == 1);
        Assert.Equal(new GPresetFurni(1, "ktchn_fridge", 0, 2, 0, 4, "0"), fridge);
        Assert.Equal(1.15, file.Furni.Single(x => x.Id == 3).Z);

        var trigger = file.Boxes.Single(x => x.Section == "triggers");
        Assert.Equal(2, trigger.WiredId);
        Assert.Equal([1], trigger.Items);
        Assert.Equal([100], trigger.FurniSources);

        var give = file.Boxes.Single(x => x.WiredId == 6);
        Assert.Equal("effects", give.Section);
        Assert.Equal([1, 0, 0, 0], give.Options);
        Assert.Equal(["700"], give.VariableIds);
        Assert.Equal([200], give.UserSources);

        Assert.Equal(5, file.Boxes.Single(x => x.WiredId == 3).Delay);
        Assert.Equal("clock", file.Boxes.Single(x => x.Section == "variables").Config);
    }

    [Fact]
    public void An_edit_is_written_over_its_entry_and_keeps_what_the_code_cannot_read()
    {
        var file = GPresetFile.Parse(Sample());

        file.Furni = [.. file.Furni.Select(x => x.Id == 1 ? x with { X = 5, State = "3" } : x)];
        file.Boxes = [.. file.Boxes.Select(x => x.WiredId == 5 ? x with { Options = [1, 2] } : x)];

        var written = JsonNode.Parse(file.ToJson())!;
        var fridge = written["furni"]!.AsArray().Single(x => (int)x!["id"]! == 1)!;
        var addon = written["wired"]!["addons"]!.AsArray().Single(x => (int)x!["wiredId"]! == 5)!;

        Assert.Equal(5, (int)fridge["location"]!["x"]!);
        Assert.Equal("3", (string)fridge["state"]!);
        Assert.Equal("fridge[0]", (string)fridge["name"]!);
        Assert.Equal("[1,2]", addon["options"]!.ToJsonString());
        Assert.Equal("{\"a\":1}", addon["futureField"]!.ToJsonString());
        Assert.Equal("[1,2]", written["somethingNew"]!.ToJsonString());
        Assert.Equal("{\"clock\":\"700\",\"other\":\"701\"}", written["wired"]!["variables_map"]!.ToJsonString());
    }

    [Fact]
    public void A_new_file_has_every_section_g_presets_needs_and_each_box_s_switches()
    {
        var file = GPresetFile.Create(
            "00\r00",
            [new GPresetFurni(1, "wf_act_toggle_state", 0, 0, 0, 0, "0")],
            [new GPresetBox("effects", 1, [], "", [], [], [], [], [], 0, 0, false, false)]
        );

        var written = JsonNode.Parse(file.ToJson())!;

        foreach (var section in new[] { "triggers", "conditions", "effects" })
            Assert.NotNull(written["wired"]![section]);

        Assert.Equal(0, (int)written["wired"]!["effects"]![0]!["delay"]!);
        Assert.Equal("wf_act_toggle_state[1]", (string)written["furni"]![0]!["name"]!);
        Assert.Equal("00\r00", GPresetFile.Parse(file.ToJson()).FloorPlan);
    }

    [Fact]
    public void A_wired_only_file_is_read_and_comes_back_without_a_furni_list()
    {
        const string json = "{\"wired\":{\"addons\":[{\"wiredId\":22,\"options\":[],\"config\":\"0=150\"}]}}";

        var file = GPresetFile.Parse(json);

        Assert.Empty(file.Furni);
        Assert.Equal("0=150", Assert.Single(file.Boxes).Config);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(json), JsonNode.Parse(file.ToJson())));
    }

    [Theory]
    [InlineData("not json", "not JSON")]
    [InlineData("[1]", "not a JSON object")]
    [InlineData("{}", "no furni list")]
    [InlineData("{\"furni\":\"nope\"}", "no furni list")]
    [InlineData("{\"furni\":[{\"className\":\"a\",\"location\":{\"x\":1,\"y\":1}}]}", "has no id")]
    [InlineData("{\"furni\":[{\"id\":1,\"location\":{\"x\":1,\"y\":1}}]}", "no class name")]
    [InlineData("{\"furni\":[{\"id\":1,\"className\":\"a\"}]}", "has no tile")]
    [InlineData("{\"furni\":[{\"id\":1,\"className\":\"a\",\"location\":{\"x\":1,\"y\":1}},{\"id\":1,\"className\":\"b\",\"location\":{\"x\":2,\"y\":1}}]}", "the id 1")]
    public void A_file_that_cannot_be_imported_says_why(string json, string because)
    {
        var problem = Assert.Throws<GPresetException>(() => GPresetFile.Parse(json));

        Assert.Contains(because, problem.Message);
    }
}
