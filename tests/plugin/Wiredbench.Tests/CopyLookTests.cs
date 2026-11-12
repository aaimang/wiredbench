using System.Net;
using System.Text;
using Turbo.Primitives.Rooms.Enums;
using Turbo.Testing;
using Wiredbench.Looks;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>
/// :copy reads a user's figure from a Habbo hotel's public API, dresses the player and keeps the
/// look in their wardrobe; what goes wrong is whispered, never thrown.
/// </summary>
public sealed class CopyLookTests
{
    private const string FIGURE = "hd-600-1.ch-630-62.lg-700-82";

    private sealed class Answer(HttpStatusCode status, string body = "", bool hang = false) : HttpMessageHandler
    {
        public Uri? Asked { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Asked = request.RequestUri;

            if (hang)
                await Task.Delay(Timeout.Infinite, ct);

            return new HttpResponseMessage(status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
        }
    }

    private readonly FakeHotel _hotel = new();

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    private (LookCopier Copier, FakePlayer Player) Copier(Answer answer)
    {
        var player = _hotel.Players.Add("Alice");

        return (new LookCopier(_hotel, new HabboLookup(answer), Microsoft.Extensions.Logging.Abstractions.NullLogger<LookCopier>.Instance), player);
    }

    [Fact]
    public async Task A_found_look_is_worn_and_kept_in_the_wardrobe()
    {
        var answer = new Answer(HttpStatusCode.OK, $$"""{"name":"GenzX","figureString":"{{FIGURE}}","motto":"hi"}""");
        var (copier, player) = Copier(answer);
        _hotel.Players.FigureGenders[FIGURE] = AvatarGenderType.Female;

        var text = await copier.RunAsync(player.Id, 1, HabboLookup.Hotel("br")!, "GenzX", Ct);

        Assert.Equal("https://www.habbo.com.br/api/public/users?name=GenzX", answer.Asked!.ToString());
        Assert.Equal("You now wear GenzX's look from Habbo.com.br. Saved to wardrobe slot 1.", text);
        Assert.Equal(FIGURE, player.Figure);
        Assert.Equal(AvatarGenderType.Female, player.Gender);
        Assert.Equal(FIGURE, player.Wardrobe[1].Figure);
    }

    [Fact]
    public async Task The_wardrobe_keeps_the_look_as_worn_without_what_the_player_may_not_wear()
    {
        const string WORN = "hd-600-1.lg-700-82";
        var (copier, player) = Copier(new Answer(HttpStatusCode.OK, $$"""{"name":"GenzX","figureString":"{{FIGURE}}"}"""));
        _hotel.Players.FiguresFitted[FIGURE] = WORN;

        var text = await copier.RunAsync(player.Id, 1, HabboLookup.Hotel("COM")!, "GenzX", Ct);

        Assert.Equal("You now wear GenzX's look from Habbo.com, without the pieces you may not wear. Saved to wardrobe slot 1.", text);
        Assert.Equal(WORN, player.Figure);
        Assert.Equal(WORN, player.Wardrobe[1].Figure);
    }

    [Fact]
    public async Task A_look_already_in_the_wardrobe_is_not_saved_twice()
    {
        var (copier, player) = Copier(new Answer(HttpStatusCode.OK, $$"""{"name":"GenzX","figureString":"{{FIGURE}}"}"""));
        await _hotel.Players.SaveOutfitAsync(player.Id, 3, FIGURE, AvatarGenderType.Female, Ct);

        var text = await copier.RunAsync(player.Id, 1, HabboLookup.Hotel("COM")!, "GenzX", Ct);

        Assert.EndsWith("It is already in your wardrobe.", text);
        Assert.Single(player.Wardrobe);
    }

    [Fact]
    public async Task A_full_wardrobe_still_dresses_the_player()
    {
        var (copier, player) = Copier(new Answer(HttpStatusCode.OK, $$"""{"name":"GenzX","figureString":"{{FIGURE}}"}"""));
        _hotel.Players.WardrobeSlots = 1;
        await _hotel.Players.SaveOutfitAsync(player.Id, 1, "hd-180-1", AvatarGenderType.Male, Ct);

        var text = await copier.RunAsync(player.Id, 1, HabboLookup.Hotel("COM")!, "GenzX", Ct);

        Assert.EndsWith("Your wardrobe is full, so it was not saved there.", text);
        Assert.Equal(FIGURE, player.Figure);
    }

    [Theory]
    [InlineData(HttpStatusCode.NotFound, "", "User 'Nobody' could not be found on Habbo.fr.")]
    [InlineData(HttpStatusCode.OK, """{"error":"not-found"}""", "User 'Nobody' could not be found on Habbo.fr.")]
    [InlineData(HttpStatusCode.ServiceUnavailable, "", "Habbo.fr could not be reached. Try again later.")]
    [InlineData(HttpStatusCode.OK, "not json", "Habbo.fr could not be reached. Try again later.")]
    [InlineData(HttpStatusCode.OK, """{"name":"Nobody","figureString":"<script>"}""", "Nobody's look on Habbo.fr could not be read.")]
    public async Task What_goes_wrong_is_said_and_nothing_changes(HttpStatusCode status, string body, string said)
    {
        var (copier, player) = Copier(new Answer(status, body));
        var before = player.Figure;

        Assert.Equal(said, await copier.RunAsync(player.Id, 1, HabboLookup.Hotel("FR")!, "Nobody", Ct));
        Assert.Equal(before, player.Figure);
        Assert.Empty(player.Wardrobe);
    }

    [Fact]
    public void A_second_copy_waits_for_the_first()
    {
        var (copier, player) = Copier(new Answer(HttpStatusCode.OK, "", hang: true));

        Assert.True(copier.TryStart(player.Id, 1, HabboLookup.Hotel(null)!, "GenzX"));
        Assert.False(copier.TryStart(player.Id, 1, HabboLookup.Hotel(null)!, "GenzX"));

        copier.Dispose();
    }

    [Theory]
    [InlineData("com", "Habbo.com")]
    [InlineData(null, "Habbo.com")]
    [InlineData("ES", "Habbo.es")]
    [InlineData(".nl", "Habbo.nl")]
    public void Hotels_are_named_by_their_code(string? code, string name) => Assert.Equal(name, HabboLookup.Hotel(code)!.Name);

    [Fact]
    public void An_unknown_hotel_is_none() => Assert.Null(HabboLookup.Hotel("XX"));

    [Theory]
    [InlineData("hr-891-40.hd-180-1.ch-3971-73-73.lg-3078-73.sh-290-1408.ha-3300-73.fa-1206-1408.ca-1813.wa-2001", true)]
    [InlineData("hd-180-1", true)]
    [InlineData("hd-180-1.", false)]
    [InlineData("HD-180-1", false)]
    [InlineData("hd-180-1;drop", false)]
    public void Figures_as_habbo_writes_them(string figure, bool ok) => Assert.Equal(ok, HabboLookup.IsFigure(figure));

    [Theory]
    [InlineData("GenzX", true)]
    [InlineData("-=x=-", true)]
    [InlineData("a b", false)]
    [InlineData("", false)]
    public void Habbo_names(string name, bool ok) => Assert.Equal(ok, CopyCommand.IsHabboName(name));
}
