using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Wiredbench.Database.Migrations
{
    /// <inheritdoc />
    public partial class AddSavedLayouts : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // The plugin makes its own table only; the database's settings are the hotel's.
            migrationBuilder.CreateTable(
                name: "wiredbench_layouts",
                columns: table => new
                {
                    RoomId = table.Column<int>(type: "int", nullable: false),
                    LayoutJson = table.Column<string>(type: "longtext", maxLength: 512, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    ItemCount = table.Column<int>(type: "int", nullable: false),
                    SavedBy = table.Column<int>(type: "int", nullable: false),
                    SavedAt = table.Column<DateTime>(type: "datetime(6)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_wiredbench_layouts", x => x.RoomId);
                })
                .Annotation("MySql:CharSet", "utf8mb4");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "wiredbench_layouts");
        }
    }
}
