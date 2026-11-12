using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;
using Turbo.Primitives.Plugins.Messages;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// The client module and the server plugin name the same messages and fields, and the version a
/// player sees is the manifest's, with its changelog entry.
/// </summary>
public sealed partial class PluginBindingTests
{
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

    private static string ClientSources() =>
        string.Join('\n', Directory.GetFiles(Path.Combine(Plugin(), "client", "src"), "*.ts*").Select(File.ReadAllText));

    private static IEnumerable<Type> ServerMessages() =>
        typeof(WiredbenchAdmin).Assembly.GetTypes().Where(x => x.GetCustomAttribute<PluginMessageAttribute>() is not null);

    [GeneratedRegex(@"=\s*'(wiredbench\.[a-z_.]+)'")]
    private static partial Regex ClientMessage();

    [Fact]
    public void Every_message_the_client_names_is_one_the_server_knows_and_back()
    {
        var client = ClientMessage().Matches(ClientSources()).Select(x => x.Groups[1].Value).ToHashSet();
        var server = ServerMessages().Select(x => x.GetCustomAttribute<PluginMessageAttribute>()!.Name).ToHashSet();

        Assert.Empty(client.Except(server));
        Assert.Empty(server.Except(client));
    }

    [Fact]
    public void The_status_schema_is_the_status_message_s_fields()
    {
        var schema = Regex.Match(ClientSources(), @"STATUS_SCHEMA = \[(.*?)\] as const").Groups[1].Value;
        var client = Regex.Matches(schema, @"\[ '(\w+)'").Select(x => x.Groups[1].Value).ToList();
        var server = typeof(StatusMessage).GetProperties().Select(x => JsonNamingPolicy.CamelCase.ConvertName(x.Name)).ToList();

        Assert.Equal(server.Order(), client.Order());
    }

    [Fact]
    public void The_manifest_s_version_has_its_changelog_entry()
    {
        using var manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(Plugin(), "manifest.json")));
        var version = manifest.RootElement.GetProperty("Version").GetString();
        var newest = Regex.Match(File.ReadAllText(Path.Combine(Plugin(), "CHANGELOG.md")), @"^## (\d+\.\d+\.\d+)", RegexOptions.Multiline);

        Assert.Matches(@"^\d+\.\d+\.\d+$", version);
        Assert.Equal(version, newest.Groups[1].Value);
    }
}
