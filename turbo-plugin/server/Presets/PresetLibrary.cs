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
        name = CheckName(name);

        var file = CheckFile(json);
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

        return Info(row);
    }

    /// <summary>
    /// Renames a preset, replaces its file, or both (null or empty leaves that part as it is); the
    /// new file is read before it is kept, as a new one is. Null when there is no such preset;
    /// throws <see cref="GPresetException"/> for a name or file the library would not take.
    /// </summary>
    public async Task<PresetInfo?> UpdateAsync(int id, string? name, string? json, CancellationToken ct)
    {
        var newName = string.IsNullOrWhiteSpace(name) ? null : CheckName(name);
        var file = string.IsNullOrWhiteSpace(json) ? null : CheckFile(json);

        if (newName is null && file is null)
            throw new GPresetException("Change the name or choose a new file.");

        await using var scope = scopes.CreateAsyncScope();
        var db = scope.ServiceProvider.GetRequiredService<WiredbenchDb>();
        var row = await db.Presets.FindAsync([id], ct).ConfigureAwait(false);

        if (row is null)
            return null;

        if (newName is not null)
            row.Name = newName;

        if (file is not null)
        {
            row.Json = json!;
            row.FurniCount = file.Furni.Length;
            row.BoxCount = file.Boxes.Length;
        }

        await db.SaveChangesAsync(ct).ConfigureAwait(false);

        return Info(row);
    }

    private static PresetInfo Info(PresetRow row) =>
        new(row.Id, row.Name, row.FurniCount, row.BoxCount, row.SavedBy, row.SavedAt);

    private static string CheckName(string? name)
    {
        name = (name ?? string.Empty).Trim();

        if (name.Length == 0)
            throw new GPresetException("Give the preset a name.");

        return name.Length > MAX_NAME_LENGTH ? name[..MAX_NAME_LENGTH] : name;
    }

    /// <summary>The file read as an import reads it; throws for one it could not read.</summary>
    private static GPresetFile CheckFile(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
            throw new GPresetException("Choose or paste the preset's JSON file.");

        if (json.Length > MAX_JSON_LENGTH)
            throw new GPresetException("The file is too large for the library.");

        return GPresetFile.Parse(json);
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
