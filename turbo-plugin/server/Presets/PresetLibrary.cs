using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Turbo.Contracts.Hotel;

namespace Wiredbench.Presets;

/// <summary>A preset of the library as the panel and the Sandbox window list it.</summary>
public sealed record PresetInfo(int Id, string Name, int FurniCount, int BoxCount, int SavedBy, DateTime SavedAt);

/// <summary>
/// The preset library (<c>wiredbench_presets</c>): files pasted in the panel or exported from a
/// room, kept as the G-Presets JSON they are. Every file is read before it is kept, so the library
/// holds only files an import can read.
/// </summary>
public sealed class PresetLibrary(IServiceScopeFactory scopes, IHotel hotel)
{
    /// <summary>The longest name a preset keeps.</summary>
    public const int MAX_NAME_LENGTH = 64;

    /// <summary>The largest file the library takes, in characters (about 4 MB).</summary>
    public const int MAX_JSON_LENGTH = 4_000_000;

    public async Task<IReadOnlyList<PresetInfo>> ListAsync(CancellationToken ct)
    {
        await using var scope = scopes.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<WiredbenchDb>();

        return await db
            .Presets.AsNoTracking()
            .OrderByDescending(x => x.SavedAt)
            .Select(x => new PresetInfo(x.Id, x.Name, x.FurniCount, x.BoxCount, x.SavedBy, x.SavedAt))
            .ToListAsync(ct)
            .ConfigureAwait(false);
    }

    public async Task<PresetRow?> GetAsync(int id, CancellationToken ct)
    {
        await using var scope = scopes.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<WiredbenchDb>();

        return await db
            .Presets.AsNoTracking()
            .FirstOrDefaultAsync(x => x.Id == id, ct)
            .ConfigureAwait(false);
    }

    /// <summary>
    /// Keeps a file under a name; throws <see cref="GPresetException"/> for a file an import could
    /// not read, before anything is kept.
    /// </summary>
    public async Task<PresetInfo> AddAsync(string name, string json, int savedBy, CancellationToken ct)
    {
        name = (name ?? string.Empty).Trim();

        if (name.Length == 0)
            throw new GPresetException("Give the preset a name.");

        if (name.Length > MAX_NAME_LENGTH)
            name = name[..MAX_NAME_LENGTH];

        if (string.IsNullOrWhiteSpace(json))
            throw new GPresetException("Paste the preset's JSON.");

        if (json.Length > MAX_JSON_LENGTH)
            throw new GPresetException("The file is too large for the library.");

        var file = GPresetFile.Parse(json);
        var row = new PresetRow
        {
            Name = name,
            Json = json,
            FurniCount = file.Furni.Length,
            BoxCount = file.Boxes.Length,
            SavedBy = savedBy,
            SavedAt = hotel.Clock.GetUtcNow().UtcDateTime,
        };

        await using var scope = scopes.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<WiredbenchDb>();

        db.Presets.Add(row);
        await db.SaveChangesAsync(ct).ConfigureAwait(false);

        return new PresetInfo(row.Id, row.Name, row.FurniCount, row.BoxCount, row.SavedBy, row.SavedAt);
    }

    public async Task<bool> DeleteAsync(int id, CancellationToken ct)
    {
        await using var scope = scopes.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<WiredbenchDb>();
        var row = await db.Presets.FindAsync([id], ct).ConfigureAwait(false);

        if (row is null)
            return false;

        db.Presets.Remove(row);
        await db.SaveChangesAsync(ct).ConfigureAwait(false);

        return true;
    }
}
