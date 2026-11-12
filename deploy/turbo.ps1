# Windows twin of turbo.sh: runs the vendored Turbo in Development with the Wiredbench plugin
# loaded from turbo-plugin\ (hot-reloaded as its files change). Stop any other Turbo first: they
# share the database and ports. Its console takes commands (`help`), so run it in a terminal you
# can type into.
#   pwsh -File deploy\turbo.ps1
. (Join-Path $PSScriptRoot 'common.ps1')

Assert-PathSetting WB_TURBO_SETTINGS file
Assert-PathSetting WB_ASSETS_DIR dir

$devSettings = Join-Path $Turbo 'appsettings.Development.json'
if (-not (Test-Path -LiteralPath $devSettings) -and $env:WB_TURBO_SETTINGS) {
    Copy-Item -LiteralPath $env:WB_TURBO_SETTINGS -Destination $devSettings
}

$env:DOTNET_ENVIRONMENT = 'Development'
$env:TURBO__Turbo__Plugin__DevPluginPaths__0 = $Plugin

# The hotel's name (Turbo:Web:HotelName): the public site shows it, and gamedata variables bound to
# it in the panel take it. WB_HOTEL_NAME changes it.
$env:TURBO__Turbo__Web__HotelName = if ($env:WB_HOTEL_NAME) { $env:WB_HOTEL_NAME } else { 'Wiredbench' }

if ($env:WB_DB_CONNECTION) { $env:TURBO__Turbo__Database__ConnectionString = $env:WB_DB_CONNECTION }
if ($env:WB_OWNER_NAME) { $env:TURBO__Turbo__Owner__Name = $env:WB_OWNER_NAME }
if ($env:WB_ASSETS_DIR) { $env:TURBO__Turbo__Assets__Directory = $env:WB_ASSETS_DIR }

# Where clients reach the gamedata host. Left empty, Turbo hands out addresses on the origin a
# request came to; deploy\client.ps1 proxies /gamedata there, so the client loads plugin modules
# from its own origin. Set it only when clients reach gamedata elsewhere.
if ($env:WB_GAMEDATA_URL) { $env:TURBO__Turbo__Gamedata__PublicUrl = $env:WB_GAMEDATA_URL }

Set-Location $Turbo
& dotnet run --no-build --project Turbo.Main\Turbo.Main.csproj
exit $LASTEXITCODE
