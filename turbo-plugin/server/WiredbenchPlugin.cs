using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Turbo.Contracts.Plugins;
using Turbo.Contracts.Plugins.Admin;

namespace Wiredbench;

/// <summary>
/// Wiredbench inside a Turbo hotel. The hotel finds the rest as the plugin loads: its key and
/// version in manifest.json, its messages, handlers and the :copy command in the assembly, and its client module,
/// built from client/src/index.tsx. Its admin pages are <see cref="WiredbenchAdmin"/>. Once the hotel is
/// up, the preset library gets the tutorial rooms it lacks.
/// </summary>
public sealed class WiredbenchPlugin : TurboPlugin
{
    protected override void Services(IServiceCollection services)
    {
        services.AddSingleton<IPluginAdmin, WiredbenchAdmin>();
        services.AddSingleton<WiredKits>();
        services.AddSingleton<Sandbox>();
        services.AddSingleton<Presets.PresetLibrary>();
        services.AddSingleton<Presets.PresetTransfer>();
        services.AddSingleton<Presets.PresetPicks>();
        services.AddSingleton<Presets.TutorialPresets>();
        services.AddSingleton<ParityReport>();
        services.AddSingleton<WiredUsage>();
        services.AddSingleton(_ => new Looks.HabboLookup());
        services.AddSingleton<Looks.LookCopier>();
        services.AddSingleton<Inventory.InventoryWipe>();
    }

    /// <summary>The library gets the tutorial rooms it lacks (data/presets).</summary>
    protected override Task HotelReadyAsync(IPluginContext context, CancellationToken ct) =>
        context.Services.GetRequiredService<Presets.TutorialPresets>().AddMissingAsync(ct);
}
