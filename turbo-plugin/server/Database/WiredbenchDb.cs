using System;
using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using Microsoft.EntityFrameworkCore;
using Turbo.Database.Context;

namespace Wiredbench;

/// <summary>
/// Wiredbench's tables, named with the manifest's TablePrefix (<c>wiredbench_</c>). Found as the
/// plugin loads, which runs its migrations (server/Database/Migrations). A handler is built once:
/// it takes IServiceScopeFactory and reads the tables in a scope of its own (turbo-cloud
/// docs/database.md).
/// </summary>
public sealed class WiredbenchDb : PluginDbContextBase<WiredbenchDb>
{
    public DbSet<SavedLayoutRow> Layouts => Set<SavedLayoutRow>();

    public DbSet<PresetRow> Presets => Set<PresetRow>();
}

/// <summary>A sandbox room's saved layout: what Reset puts the room back to.</summary>
[Table("layouts")]
public sealed class SavedLayoutRow
{
    [Key]
    [DatabaseGenerated(DatabaseGeneratedOption.None)]
    public int RoomId { get; set; }

    /// <summary>The room's <c>RoomLayoutSnapshot</c>, as JSON.</summary>
    [Column(TypeName = "longtext")]
    public string LayoutJson { get; set; } = string.Empty;

    public int ItemCount { get; set; }

    public int SavedBy { get; set; }

    public DateTime SavedAt { get; set; }
}

/// <summary>A G-Presets file in the preset library: pasted in the panel or exported from a room.</summary>
[Table("presets")]
public sealed class PresetRow
{
    [Key]
    public int Id { get; set; }

    [MaxLength(64)]
    public string Name { get; set; } = string.Empty;

    /// <summary>The file, as G-Presets JSON.</summary>
    [Column(TypeName = "longtext")]
    public string Json { get; set; } = string.Empty;

    public int FurniCount { get; set; }

    public int BoxCount { get; set; }

    /// <summary>The player who pasted or exported it.</summary>
    public int SavedBy { get; set; }

    public DateTime SavedAt { get; set; }
}
