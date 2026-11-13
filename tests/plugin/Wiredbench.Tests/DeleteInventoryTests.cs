using Turbo.Testing;
using Wiredbench.Inventory;
using Xunit;

namespace Wiredbench.Tests;

/// <summary>:deleteinventory asks twice, and deletes only after the second yes.</summary>
public sealed class DeleteInventoryTests
{
    private readonly FakeHotel _hotel = new();
    private readonly FakePlayer _alice;
    private readonly FakePlayer _bob;
    private readonly InventoryWipe _wipe;

    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    public DeleteInventoryTests()
    {
        _alice = _hotel.Players.Add("alice", online: true);
        _bob = _hotel.Players.Add("bob", online: true);
        _hotel.Inventory.Hold(_alice.Id, 7, 3);
        _hotel.Inventory.Hold(_bob.Id, 7, 2);
        _wipe = new InventoryWipe(_hotel);
    }

    private int Held(FakePlayer player) => _hotel.Inventory.Held(player.Id, 7);

    [Fact]
    public async Task The_command_asks_first_and_deletes_nothing()
    {
        Assert.True(await _wipe.BeginAsync(_alice.Id, Ct));

        var ask = _hotel.Players.AssertSent<InventoryAskMessage>(_alice.Id);

        Assert.Equal(1, ask.Step);
        Assert.Equal(3, ask.Count);
        Assert.Equal(3, Held(_alice));
    }

    [Fact]
    public async Task One_yes_leads_to_the_second_question_not_the_deleting()
    {
        await _wipe.BeginAsync(_alice.Id, Ct);
        await _wipe.ConfirmAsync(_alice.Id, Ct);

        Assert.Equal(2, _hotel.Players.AssertSent<InventoryAskMessage>(_alice.Id).Step);
        Assert.Equal(3, Held(_alice));
    }

    [Fact]
    public async Task Two_yeses_delete_that_player_s_furni_and_only_theirs()
    {
        await _wipe.BeginAsync(_alice.Id, Ct);
        await _wipe.ConfirmAsync(_alice.Id, Ct);
        await _wipe.ConfirmAsync(_alice.Id, Ct);

        Assert.Equal(0, Held(_alice));
        Assert.Equal(2, Held(_bob));
        Assert.Equal(3, _hotel.Players.AssertSent<InventoryDoneMessage>(_alice.Id).Deleted);
    }

    [Fact]
    public async Task A_yes_with_no_question_asked_deletes_nothing()
    {
        await _wipe.ConfirmAsync(_alice.Id, Ct);
        await _wipe.ConfirmAsync(_alice.Id, Ct);

        Assert.Equal(3, Held(_alice));
    }

    [Fact]
    public async Task A_no_drops_the_questions()
    {
        await _wipe.BeginAsync(_alice.Id, Ct);
        _wipe.Cancel(_alice.Id);
        await _wipe.ConfirmAsync(_alice.Id, Ct);
        await _wipe.ConfirmAsync(_alice.Id, Ct);

        Assert.Equal(3, Held(_alice));
    }

    [Fact]
    public async Task Another_player_s_yes_does_not_count()
    {
        await _wipe.BeginAsync(_alice.Id, Ct);
        await _wipe.ConfirmAsync(_bob.Id, Ct);
        await _wipe.ConfirmAsync(_bob.Id, Ct);

        Assert.Equal(3, Held(_alice));
        Assert.Equal(2, Held(_bob));
    }

    [Fact]
    public async Task A_question_left_too_long_is_dropped()
    {
        await _wipe.BeginAsync(_alice.Id, Ct);
        await _wipe.ConfirmAsync(_alice.Id, Ct);
        _hotel.Clock.Advance(InventoryWipe.WAIT + TimeSpan.FromSeconds(1));
        await _wipe.ConfirmAsync(_alice.Id, Ct);

        Assert.Equal(3, Held(_alice));
        Assert.Equal(0, _hotel.Players.AssertSent<InventoryDoneMessage>(_alice.Id).Deleted);
        Assert.Contains("too long", _hotel.Players.AssertSent<InventoryDoneMessage>(_alice.Id).Message);
    }

    [Fact]
    public async Task An_empty_inventory_asks_nothing()
    {
        var carol = _hotel.Players.Add("carol", online: true);

        Assert.False(await _wipe.BeginAsync(carol.Id, Ct));
        Assert.Equal(0, _hotel.Players.AssertSent<InventoryDoneMessage>(carol.Id).Deleted);
        Assert.DoesNotContain(_hotel.Players.SentTo(carol.Id), x => x is InventoryAskMessage);
    }
}
