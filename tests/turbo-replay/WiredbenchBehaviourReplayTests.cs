using System.Collections.Immutable;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Turbo.Primitives.Action;
using Turbo.Primitives.Messages.Outgoing.Room.Chat;
using Turbo.Primitives.Rooms.Enums;
using Turbo.Primitives.Rooms.Enums.Wired;
using Turbo.Primitives.Rooms.Events.Wired;
using Turbo.Primitives.Rooms.Object;
using Turbo.Primitives.Rooms.Object.Furniture.Floor;
using Turbo.Primitives.Rooms.Object.Logic;
using Turbo.Primitives.Rooms.Object.Logic.Avatars;
using Turbo.Primitives.Rooms.Snapshots.Wired;
using Turbo.Primitives.Rooms.Wired.Variable;
using Turbo.Primitives.Rooms.Wired.WebApi;
using Turbo.Rooms.Configuration;
using Turbo.Rooms.Grains.Modules;
using Turbo.Rooms.Grains.Systems;
using Turbo.Rooms.Object.Avatars.Bot;
using Turbo.Rooms.Object.Logic.Furniture.Floor.Wired;
using Turbo.Rooms.Object.Logic.Furniture.Floor.Wired.Addons;
using Turbo.Tests.Support;
using Xunit;

namespace Turbo.Tests.Rooms;

/// <summary>
/// Wiredbench's behaviour comparison (wiredbench <c>scripts/behaviour.py</c>): each room the old
/// Python engine's tests build, replayed here as a player would make it, and what could be seen
/// noted at the same checkpoints (just before each input, and at the end). It compares nothing
/// itself: it writes what Turbo did, and the script compares the two. Skipped unless
/// <c>WB_BEHAVIOUR_SCENARIOS</c> names the scenario file; it writes to <c>WB_BEHAVIOUR_OUT</c>.
/// <para>
/// The room is flat; each box is saved as the client would save it (the scenario carries the
/// G-Presets export of its settings), variable boxes first and the rest once the room lists their
/// variables (an echo once its source is listed); a user's move puts them straight on the tile,
/// telling the furni as a walk does (the Python engine's move), unless they are frozen; wired runs
/// every 50 ms, and a room with a Teleport To is given time for it to land before the last look.
/// </para>
/// </summary>
public sealed class WiredbenchBehaviourReplayTests
{
    private const int TICK_MS = 50;

    // The Python engine's time 0 is this instant (its EPOCH_SECONDS); the room is built in the
    // second before it, so creation and update times read the same in both.
    private const long PYTHON_EPOCH_MS = 1_700_000_000_000;
    private const int SETUP_MS = 1_000;

    // The wired ticks the boxes are saved over (the boxes naming no variable of the room's, then
    // echoes, add-ons and the rest): the clock is set back that far, so the room's wired starts
    // where the Python engine's time 0 is, give or take these ticks.
    private const int SETUP_TICKS = 4;

    private static readonly int AVATAR_TICK_MS = new RoomConfig().AvatarTickMs;

    // Where a room that is written to over the Web API keeps its Web API add-on, out of the way.
    private const int WEB_API_ADDON = 999_999;
    private static readonly string? SCENARIOS = Environment.GetEnvironmentVariable(
        "WB_BEHAVIOUR_SCENARIOS"
    );
    private static readonly string? OUT = Environment.GetEnvironmentVariable("WB_BEHAVIOUR_OUT");

    private static readonly Dictionary<string, Type> BOX_LOGICS = typeof(FurnitureWiredLogic)
        .Assembly.GetTypes()
        .Where(t => typeof(FurnitureWiredLogic).IsAssignableFrom(t) && !t.IsAbstract)
        .Select(t => (Type: t, Key: t.GetCustomAttribute<RoomObjectLogicAttribute>(false)?.Key))
        .Where(x => x.Key is not null)
        .GroupBy(x => x.Key!)
        .ToDictionary(x => x.Key, x => x.First().Type);

    private static readonly Dictionary<string, WiredVariableTargetType> SCOPES = new()
    {
        ["wf_var_user"] = WiredVariableTargetType.User,
        ["wf_var_furni"] = WiredVariableTargetType.Furni,
        ["wf_var_room"] = WiredVariableTargetType.Global,
    };

    [Fact]
    public async Task Replays_wiredbench_scenarios()
    {
        Assert.SkipUnless(
            !string.IsNullOrEmpty(SCENARIOS) && !string.IsNullOrEmpty(OUT),
            "WB_BEHAVIOUR_SCENARIOS and WB_BEHAVIOUR_OUT are not set"
        );

        var scenarios = JsonNode.Parse(await File.ReadAllTextAsync(SCENARIOS!))!.AsArray();
        var results = new JsonArray();

        foreach (var scenario in scenarios)
        {
            var id = (string)scenario!["id"]!;

            try
            {
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
                var replay = new Replay(scenario.AsObject(), timeout.Token);

                results.Add(await replay.RunAsync());
            }
            catch (Exception ex)
            {
                results.Add(
                    new JsonObject
                    {
                        ["id"] = id,
                        ["error"] = $"{ex.GetType().Name}: {ex.Message}".Split('\n')[0],
                        ["stack"] = string.Join(
                            " | ",
                            (ex.InnerException ?? ex)
                                .ToString()
                                .Split('\n')
                                .Where(l =>
                                    l.TrimStart().StartsWith("at ", StringComparison.Ordinal)
                                )
                                .Take(4)
                                .Select(l => l.Trim())
                        ),
                    }
                );
            }
        }

        await File.WriteAllTextAsync(
            OUT!,
            results.ToJsonString(new JsonSerializerOptions { WriteIndented = true })
        );
    }

    private sealed class Replay(JsonObject scenario, CancellationToken ct)
    {
        private readonly WiredRoom _room = new(
            (int)scenario["width"]!,
            (int)scenario["height"]!,
            clock: new ManualTimeProvider(
                DateTimeOffset.FromUnixTimeMilliseconds(PYTHON_EPOCH_MS - SETUP_MS)
            )
        );
        private readonly SortedDictionary<int, RoomBotAvatar> _bots = [];
        private (string Read, string Write)? _webApiKeys;
        private readonly HashSet<int> _boxes = [];
        private readonly Dictionary<string, WiredVariableTargetType> _variables = new(
            StringComparer.Ordinal
        );
        private readonly JsonArray _refused = [];
        private readonly JsonArray _missing = [];
        private int _whispersSeen;
        private readonly List<string> _carried = [];
        private long _t;
        private bool _pending;

        private RoomWiredSystem Wired => _room.Harness.Module<RoomWiredSystem>();

        public async Task<JsonObject> RunAsync()
        {
            // Time passes before the room is built, with no wired running yet: wired starts its
            // timers on its first tick, which is the first tick below.
            _t = SETUP_MS - SETUP_TICKS * TICK_MS;
            _room.Clock.AdvanceMs(_t);

            // The chat path publishes every line and matches commands first, as the chat tests set up.
            _room.Harness.Room.UseEventSystem(new TestEventBus().System);
            _room.Harness.Room.UseCommands(
                new Turbo.Commands.CommandRegistryProvider(
                    new CapturingLogger<Turbo.Primitives.Commands.ICommandRegistryProvider>()
                )
            );

            foreach (var furni in scenario["furni"]!.AsArray())
                await PlaceAsync(furni!.AsObject());

            foreach (var user in scenario["users"]!.AsArray().Select(x => x!.AsObject()))
            {
                if (user["bot"] is { } isBot && (bool)isBot)
                {
                    AddBot(user);
                    continue;
                }

                var avatar = _room.Enter(
                    (int)user["id"]!,
                    (int)user["x"]!,
                    (int)user["y"]!,
                    name: (string)user["name"]!,
                    rotation: (Rotation)((int)user["dir"]! % 8)
                );

                if (user["handItem"] is { } handItem && (int)handItem > 0)
                    await _room
                        .Harness.Module<RoomAvatarModule>()
                        .SetHandItemAsync(avatar, (int)handItem, ct);
            }

            foreach (
                var idx in _boxes
                    .Select(id => _room.Harness.State.ItemsById[id])
                    .Select(b => _room.Map.ToIdx(b.X, b.Y))
                    .Distinct()
            )
                await Wired.OnRoomEventAsync(
                    new RoomWiredStackChangedEvent
                    {
                        RoomId = 1,
                        CausedBy = ActionContext.CreateForSystem(1),
                        StackIds = [idx],
                    },
                    ct
                );

            var boxes = scenario["boxes"]!.AsArray().Select(x => x!.AsObject()).ToList();

            // A box is saved before the room's first wired tick, so a repeater is scheduled with
            // its own period, unless it names a variable of the room's: a variable is listed from
            // the next tick, so those are saved after, an echo once its source is listed and an
            // add-on deriving sub-variables (a Time Utility) before the boxes reading them.
            static bool NamesRoomVariable(JsonObject box) =>
                box["variables"]!.AsArray().Any(v => ((string)v!).StartsWith('='));

            var later = boxes.Where(NamesRoomVariable).ToList();

            foreach (var box in boxes.Where(x => !NamesRoomVariable(x)))
                await SaveAsync(box);

            await TickAsync();

            foreach (var box in later.Where(x => (string)x["kind"]! == "variable"))
                await SaveAsync(box);

            await TickAsync();

            foreach (var box in later.Where(x => (string)x["kind"]! == "addon"))
                await SaveAsync(box);

            await TickAsync();

            foreach (var box in later.Where(x => (string)x["kind"]! is not ("variable" or "addon")))
                await SaveAsync(box);

            await TickAsync();

            if (scenario["inputs"]!.AsArray().Any(i => (string)i!["type"]! == "api_set"))
                await OpenWebApiAsync();

            await TickToAsync(SETUP_MS);
            TakeWhispers();

            var checkpoints = new JsonArray();
            var started = _t;

            foreach (var input in scenario["inputs"]!.AsArray())
            {
                await TickToAsync(started + (long)input!["at_ms"]!);
                checkpoints.Add(await ObserveAsync());
                await ApplyAsync(input.AsObject());
            }

            // A Teleport To lands up to TeleportDelayMs after it fires, where the Python engine's
            // is at once: such a room is given that long before the last look.
            var settle = scenario["furni"]!
                .AsArray()
                .Any(f => (string)f!["classname"]! == "wf_act_teleport_to")
                ? new WiredConfig().TeleportDelayMs + TICK_MS
                : 0;

            await TickToAsync(started + (long)scenario["until"]! + settle);
            checkpoints.Add(await ObserveAsync());

            return new JsonObject
            {
                ["id"] = (string)scenario["id"]!,
                ["checkpoints"] = checkpoints,
                ["refused"] = _refused,
                ["missing"] = _missing,
            };
        }

        private async Task PlaceAsync(JsonObject furni)
        {
            var id = (int)furni["id"]!;
            var classname = (string)furni["classname"]!;
            var (x, y) = ((int)furni["x"]!, (int)furni["y"]!);
            IRoomObject item;

            if (classname.StartsWith("wf_", StringComparison.Ordinal))
            {
                _boxes.Add(id);

                if (BOX_LOGICS.TryGetValue(classname, out var logic))
                {
                    typeof(WiredRoom)
                        .GetMethod(nameof(WiredRoom.AddBox))!
                        .MakeGenericMethod(logic)
                        .Invoke(_room, [id, x, y, classname]);
                    item = _room.FloorItem(id);
                }
                else
                {
                    _missing.Add(classname);
                    item = _room.AddFloorItem(id, x, y, className: classname);
                }
            }
            else
            {
                item = _room.AddFloorItem(
                    id,
                    x,
                    y,
                    canWalk: (bool)furni["walk"]! || (bool)furni["sit"]! || (bool)furni["lay"]!,
                    canSit: (bool)furni["sit"]!,
                    canLay: (bool)furni["lay"]!,
                    totalStates: (int)furni["states"]!,
                    className: classname,
                    width: (int)furni["width"]!,
                    length: (int)furni["length"]!
                );
            }

            var floor = _room.FloorItem(id);
            var rotation = (Rotation)((int)furni["rot"]! % 8);
            var z = Altitude.FromValue((double)furni["z"]!);

            if (rotation != floor.Rotation || z != floor.Z)
                _room.Map.MoveFloorItem(floor, _room.Map.ToIdx(x, y), z, rotation);

            var state = (int)furni["state"]!;

            if (state != 0 && !_boxes.Contains(id))
                await floor.Logic.SetStateAsync(state);
        }

        private async Task SaveAsync(JsonObject box)
        {
            var id = (int)box["id"]!;

            if (!_room.Harness.State.ItemsById.TryGetValue(id, out var item))
                return;

            var classname = item is IRoomFloorItem floor ? floor.Definition.Name : "";

            // A setting the export kept as text ("5") is its number; anything else is 0.
            static int Int(JsonNode? x) =>
                x?.GetValueKind() switch
                {
                    JsonValueKind.Number => (int)Math.Round((double)x),
                    JsonValueKind.String when int.TryParse((string)x!, out var n) => n,
                    JsonValueKind.True => 1,
                    _ => 0,
                };

            static ImmutableArray<int> Ints(JsonNode? node) =>
                [.. (node?.AsArray() ?? []).Select(Int)];

            var settings = new WiredBoxSettingsSnapshot
            {
                ItemId = id,
                WiredType = WiredType.None,
                WiredCode = 0,
                LogicName = string.Empty,
                IntParams = Ints(box["ints"]),
                StringParam = (string)box["string"]!,
                StuffIds = Ints(box["stuff"]),
                StuffIds2 = Ints(box["stuff2"]),
                VariableIds = [.. box["variables"]!.AsArray().Select(x => VariableId((string)x!))],
                FurniSources = [.. Ints(box["furniSources"]).Select(x => ImmutableArray.Create(x))],
                UserSources = [.. Ints(box["userSources"]).Select(x => ImmutableArray.Create(x))],
                Delay = Int(box["delay"]),
                Quantifier = Int(box["quantifier"]),
                Filter = Int(box["filter"]) != 0,
                Invert = (bool)box["invert"]!,
            };

            var result = await _room.Harness.Room.SaveWiredBoxSettingsAsync(
                ActionContext.CreateForSystem(1),
                settings,
                ct
            );

            if (!result.IsSaved)
                _refused.Add(classname);

            if (SCOPES.TryGetValue(classname, out var scope) && settings.StringParam.Length > 0)
                _variables[settings.StringParam] = scope;

            // An echo is read as the variable it echoes.
            if (
                classname == "wf_var_echo"
                && settings.StringParam.Length > 0
                && box["variables"]!.AsArray().FirstOrDefault() is { } source
                && ((string)source!).StartsWith('=')
                && _variables.TryGetValue(((string)source!)[1..], out var echoed)
            )
                _variables[settings.StringParam] = echoed;
        }

        /// <summary>A variable the room made, by its name (<c>=name</c>); any other id as it is.</summary>
        private string VariableId(string sent)
        {
            if (!sent.StartsWith('='))
                return sent;

            var name = sent[1..];

            return Wired
                    .GetAllVariables()
                    .Select(v => v.GetVarSnapshot())
                    .FirstOrDefault(v => v.VariableName == name)
                    ?.VariableId.ToString()
                ?? "0";
        }

        private async Task ApplyAsync(JsonObject input)
        {
            var type = (string)input["type"]!;
            var user =
                input["user"] is { } u && u.GetValueKind() == JsonValueKind.Number ? (int)u : -1;
            var avatar = _room.Avatars.GetValueOrDefault(user);

            switch (type)
            {
                // A frozen user's walk is refused (RoomAvatarModule.TryStartWalk), so the move is.
                case "move" when avatar is not null && avatar.IsFrozen:
                    return;
                case "move" when avatar is not null:
                    await _room
                        .Harness.Module<RoomAvatarModule>()
                        .RelocateAvatarAsync(
                            avatar,
                            _room.Map.ToIdx((int)input["x"]!, (int)input["y"]!),
                            ct
                        );
                    break;
                case "say" when avatar is not null:
                {
                    var text = (string?)input["text"] ?? "";

                    _carried.AddRange(TakeWhispers());
                    await _room.Harness.Room.ChatSystem.SendChatFromPlayerAsync(
                        _room.ContextFor(avatar),
                        RoomChatType.Chat,
                        text,
                        0,
                        -1,
                        null,
                        ct
                    );

                    // A line a keyword trigger hides comes back to its speaker as a whisper (Habbo's
                    // echo): the speaker's own line, not a wired message, so it is not counted.
                    var said = TakeWhispers();

                    // The echo is the line as the room keeps it, trimmed.
                    if (!said.Remove(text))
                        said.Remove(text.Trim());
                    _carried.AddRange(said);
                    break;
                }
                case "click" when avatar is not null:
                    await _room.Harness.Room.ClickItemByIdAsync(
                        _room.ContextFor(avatar),
                        (int)input["furni"]!,
                        ct
                    );
                    break;
                case "use" when avatar is not null:
                    await _room.Harness.Room.UseItemByIdAsync(
                        _room.ContextFor(avatar),
                        (int)input["furni"]!,
                        ct,
                        0
                    );
                    break;
                case "api_set":
                    await WebApiSetAsync(input);
                    break;
                case "leave" when avatar is not null:
                    _room.Avatars.Remove(user);
                    await _room.Harness.Room.RemoveAvatarFromPlayerAsync(
                        _room.ContextFor(avatar),
                        avatar.PlayerId,
                        ct
                    );
                    break;
                default:
                    return;
            }

            // What the input set off runs on the next tick, even when the next input is at once.
            _pending = true;
        }

        /// <summary>A bot standing in the room, as Turbo's bot box tests stand one.</summary>
        private void AddBot(JsonObject user)
        {
            var id = (int)user["id"]!;
            var bot = new RoomBotAvatar
            {
                ObjectId = id,
                BotId = id,
                OwnerId = 1,
                OwnerName = "owner",
                RoomId = 1,
                Skills = [],
            };

            bot.SetName((string)user["name"]!);
            bot.SetPosition((int)user["x"]!, (int)user["y"]!);
            bot.SetLogic(_room.Harness.Fakes.Create<IRoomBotLogic>(id));
            _room.Harness.State.AvatarsByObjectId[id] = bot;
            _room.Harness.State.Bots.Add(bot);
            _room.Map.AddAvatar(bot, false);
            _bots[id] = bot;
        }

        /// <summary>
        /// The room's Web API, opened by a Variable Global Add-on: Web API with a read and a write
        /// key, as the room's owner sets one up. The Python engine's API write needs none.
        /// </summary>
        private async Task OpenWebApiAsync()
        {
            _room.AddBox<WiredAddonVariablesWebApi>(WEB_API_ADDON, 0, 0, "wf_xtra_var_web_api");
            _boxes.Add(WEB_API_ADDON);

            var system = ActionContext.CreateForSystem(1);
            var read = await _room.Harness.Room.GenerateWiredWebApiKeyAsync(
                system,
                WEB_API_ADDON,
                true,
                ct
            );
            var write = await _room.Harness.Room.GenerateWiredWebApiKeyAsync(
                system,
                WEB_API_ADDON,
                false,
                ct
            );

            if (
                read is null
                || write is null
                || !await _room.SaveAsync<Turbo.Primitives.Messages.Incoming.Userdefinedroomevents.UpdateAddonMessage>(
                    WEB_API_ADDON,
                    intParams: [1],
                    stringParam: read + "\t" + write
                )
            )
            {
                _refused.Add("wf_xtra_var_web_api");
                return;
            }

            _webApiKeys = (read, write);
        }

        /// <summary>
        /// A value written over the Web API: a global with PATCH, a user's (by player id) or a
        /// furni's with PUT, which gives the variable to a holder without it as the Python
        /// engine's write does.
        /// </summary>
        private async Task WebApiSetAsync(JsonObject input)
        {
            if (_webApiKeys is not { } keys)
                return;

            var name = (string)input["variable"]!;
            var key = ((string)input["key"]!).Split(':', 2);
            var (scope, entity) = (key[0], key.Length > 1 ? key[1] : "");
            var value =
                input["value"] is { } raw && raw.GetValueKind() == JsonValueKind.Number ? (long)raw
                : long.TryParse((string?)input["value"], out var parsed) ? parsed
                : 0;
            var body = $$"""{"value":"{{value}}"}""";
            var request = scope switch
            {
                "global" => new WiredWebApiRequest
                {
                    Operation = WiredWebApiOperation.PatchGlobal,
                    VariableName = name,
                    WriteKey = keys.Write,
                    Body = body,
                },
                "user" when _room.Avatars.GetValueOrDefault(int.Parse(entity)) is { } user =>
                    new WiredWebApiRequest
                    {
                        Operation = WiredWebApiOperation.PutValue,
                        Scope = "user",
                        VariableName = name,
                        TargetKind = "users",
                        EntityId = user.PlayerId.ToString(),
                        WriteKey = keys.Write,
                        Body = body,
                    },
                "furni" => new WiredWebApiRequest
                {
                    Operation = WiredWebApiOperation.PutValue,
                    Scope = "furni",
                    VariableName = name,
                    TargetKind = "furni",
                    EntityId = entity,
                    WriteKey = keys.Write,
                    Body = body,
                },
                _ => null,
            };

            if (request is null)
                return;

            var response = await _room.Harness.Room.HandleWiredWebApiAsync(request, ct);

            if (response.Status >= 300)
                _refused.Add($"api_set {scope} {name}: {response.Status} {response.Json}");
        }

        private async Task TickAsync()
        {
            _t += TICK_MS;
            _room.Clock.AdvanceMs(TICK_MS);

            var now = _room.Harness.NowMs();

            // Walks, a bot's included, step on the room's avatar cycle.
            if (_t % AVATAR_TICK_MS == 0)
            {
                await _room.Harness.Room.AvatarTickSystem.ProcessAvatarsAsync(now, ct);
                await _room.Harness.Room.BotTickSystem.ProcessBotsAsync(now, ct);
            }

            await Wired.ProcessWiredAsync(now, dormant: false, ct);
            _pending = false;
        }

        private async Task TickToAsync(long at)
        {
            while (_t + TICK_MS <= at || _pending)
                await TickAsync();
        }

        private List<string> TakeWhispers()
        {
            var whispers = _room
                .Harness.Fakes.Sent<WhisperMessageComposer>()
                .Select(w => w.Text)
                .ToList();
            var fresh = whispers.Skip(_whispersSeen).ToList();

            _whispersSeen = whispers.Count;

            return fresh;
        }

        private async Task<JsonObject> ObserveAsync()
        {
            var users = new JsonObject();

            foreach (var (id, avatar) in _room.Avatars.OrderBy(x => x.Key))
                users[id.ToString()] = new JsonArray(avatar.X, avatar.Y);

            foreach (var (id, bot) in _bots)
                users[id.ToString()] = new JsonArray(bot.X, bot.Y);

            var furni = new JsonObject();

            foreach (
                var item in _room
                    .Harness.State.ItemsById.Values.OfType<IRoomFloorItem>()
                    .Where(x => !_boxes.Contains(x.ObjectId.Value))
                    .OrderBy(x => x.ObjectId.Value)
            )
                furni[item.ObjectId.Value.ToString()] = new JsonArray(
                    item.X,
                    item.Y,
                    (int)item.Rotation,
                    item.Logic.GetState()
                );

            var names = Wired
                .GetAllVariables()
                .Select(v => v.GetVarSnapshot())
                .Where(v => _variables.ContainsKey(v.VariableName))
                .ToDictionary(v => v.VariableId, v => v.VariableName);
            var held = new SortedDictionary<string, SortedDictionary<string, string>>(
                StringComparer.Ordinal
            );

            async Task ReadAsync(WiredVariableTargetType type, int target, string key)
            {
                foreach (
                    var (id, value) in await Wired.GetAllVariablesForBindingAsync(
                        new WiredVariableBinding(type, target),
                        ct
                    )
                )
                {
                    if (!names.TryGetValue(id, out var name) || _variables[name] != type)
                        continue;

                    if (!held.TryGetValue(name, out var values))
                        held[name] = values = new SortedDictionary<string, string>(
                            StringComparer.Ordinal
                        );

                    values[key] = value.Value.ToString(
                        System.Globalization.CultureInfo.InvariantCulture
                    );
                }
            }

            foreach (var id in _room.Avatars.Keys)
                await ReadAsync(WiredVariableTargetType.User, id, $"user:{id}");

            foreach (var id in _room.Harness.State.ItemsById.Keys)
                await ReadAsync(WiredVariableTargetType.Furni, id, $"furni:{id}");

            await ReadAsync(WiredVariableTargetType.Global, 0, "global");

            var variables = new JsonObject();

            foreach (var (name, values) in held)
                variables[name] = new JsonObject(
                    values.Select(x => KeyValuePair.Create(x.Key, (JsonNode?)x.Value))
                );

            var messages = new JsonArray([
                .. _carried
                    .Concat(TakeWhispers())
                    .Order(StringComparer.Ordinal)
                    .Select(x => (JsonNode)x),
            ]);

            _carried.Clear();

            return new JsonObject
            {
                ["at"] = _t,
                ["users"] = users,
                ["furni"] = furni,
                ["variables"] = variables,
                ["messages"] = messages,
            };
        }
    }
}
