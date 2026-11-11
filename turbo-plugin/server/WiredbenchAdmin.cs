using System.Threading.Tasks;
using Turbo.Contracts.Plugins;
using Turbo.Contracts.Plugins.Admin;

namespace Wiredbench;

/// <summary>
/// Wiredbench's pages in the Turbo admin panel. The panel draws them from this schema; no
/// Wiredbench code runs in the panel. Staff need <c>plugin.wiredbench.view</c> to see them.
/// </summary>
public sealed class WiredbenchAdmin(PluginManifest manifest) : IPluginAdmin
{
    public void Configure(IPluginAdminBuilder admin)
    {
        var view = admin.Node("view", "See the Wiredbench pages");

        admin.Map(
            "GET",
            "status",
            view,
            (_, _) =>
                Task.FromResult(
                    PluginAdminResult.Ok(
                        new[]
                        {
                            new { label = "Plugin version", value = manifest.Version },
                            new { label = "Client module", value = "On" },
                        }
                    )
                )
        );

        admin.Page(
            new PluginAdminPage(
                "overview",
                "Wiredbench",
                view,
                [
                    new PluginAdminBlock(
                        "text",
                        Text: "**Wiredbench** builds and debugs WIRED in this hotel's own client. "
                            + "Sandbox rooms, the trace and G-Presets import arrive in later phases."
                    ),
                    new PluginAdminBlock("stats", Title: "Status", Endpoint: "status"),
                ],
                Description: "WIRED sandbox tools"
            )
        );
    }
}
