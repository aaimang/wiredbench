using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace Wiredbench.Looks;

/// <summary>One of Habbo's hotels: the code a player types, its site and the name it goes by.</summary>
public sealed record HabboHotel(string Code, string Domain, string Name);

/// <summary>What asking a Habbo hotel for a user's look came to.</summary>
public enum HabboLookupStatus
{
    Found,
    NotFound,
    Unavailable,
    TimedOut,
    BadFigure,
}

/// <summary>A user's look on a Habbo hotel, or why there is none.</summary>
public sealed record HabboLook(HabboLookupStatus Status, string Name = "", string Figure = "");

/// <summary>
/// Reads a user's figure from a Habbo hotel's public API (<c>/api/public/users?name=</c>), with a
/// short time limit; it never throws for what the network or the hotel does.
/// </summary>
public sealed partial class HabboLookup(HttpMessageHandler? handler = null)
{
    /// <summary>The hotels <c>:copy</c> knows, by the code typed after the name.</summary>
    public static readonly ImmutableArray<HabboHotel> HOTELS =
    [
        new("COM", "habbo.com", "Habbo.com"),
        new("BR", "habbo.com.br", "Habbo.com.br"),
        new("TR", "habbo.com.tr", "Habbo.com.tr"),
        new("DE", "habbo.de", "Habbo.de"),
        new("ES", "habbo.es", "Habbo.es"),
        new("FI", "habbo.fi", "Habbo.fi"),
        new("FR", "habbo.fr", "Habbo.fr"),
        new("IT", "habbo.it", "Habbo.it"),
        new("NL", "habbo.nl", "Habbo.nl"),
    ];

    /// <summary>How long a lookup may take before it is given up.</summary>
    public static readonly TimeSpan TIME_LIMIT = TimeSpan.FromSeconds(8);

    /// <summary>The longest figure taken: what a player's figure column holds.</summary>
    public const int MAX_FIGURE_LENGTH = 255;

    private readonly HttpClient _http = CreateClient(handler);

    public static HabboHotel? Hotel(string? code) =>
        HOTELS.FirstOrDefault(x => string.Equals(x.Code, (code ?? "COM").Trim().TrimStart('.'), StringComparison.OrdinalIgnoreCase));

    /// <summary>A figure as Habbo writes one: <c>hd-180-1.ch-210-66</c>, nothing else.</summary>
    public static bool IsFigure(string? figure) =>
        !string.IsNullOrEmpty(figure) && figure.Length <= MAX_FIGURE_LENGTH && Figure().IsMatch(figure);

    public async Task<HabboLook> FindAsync(HabboHotel hotel, string name, CancellationToken ct)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TIME_LIMIT);

        try
        {
            using var response = await _http
                .GetAsync(
                    $"https://www.{hotel.Domain}/api/public/users?name={Uri.EscapeDataString(name)}",
                    HttpCompletionOption.ResponseHeadersRead,
                    timeout.Token
                )
                .ConfigureAwait(false);

            if (response.StatusCode is HttpStatusCode.NotFound)
                return new(HabboLookupStatus.NotFound);

            if (!response.IsSuccessStatusCode)
                return new(HabboLookupStatus.Unavailable);

            await using var body = await response.Content.ReadAsStreamAsync(timeout.Token).ConfigureAwait(false);
            using var json = await JsonDocument.ParseAsync(body, cancellationToken: timeout.Token).ConfigureAwait(false);

            return Read(json.RootElement);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return new(HabboLookupStatus.TimedOut);
        }
        catch (Exception ex) when (ex is HttpRequestException or JsonException or InvalidOperationException)
        {
            return new(HabboLookupStatus.Unavailable);
        }
    }

    /// <summary>The API's answer: a user with a <c>figureString</c>, or an error object (not found).</summary>
    public static HabboLook Read(JsonElement user)
    {
        if (user.ValueKind != JsonValueKind.Object)
            return new(HabboLookupStatus.Unavailable);

        if (!user.TryGetProperty("figureString", out var figure) || figure.ValueKind != JsonValueKind.String)
            return new(user.TryGetProperty("error", out _) ? HabboLookupStatus.NotFound : HabboLookupStatus.Unavailable);

        var text = figure.GetString() ?? string.Empty;
        var name = user.TryGetProperty("name", out var n) && n.ValueKind == JsonValueKind.String ? n.GetString() ?? string.Empty : string.Empty;

        return IsFigure(text) ? new(HabboLookupStatus.Found, name, text) : new(HabboLookupStatus.BadFigure, name);
    }

    private static HttpClient CreateClient(HttpMessageHandler? handler)
    {
        var http = handler is null ? new HttpClient() : new HttpClient(handler, disposeHandler: false);

        // The limit is the lookup's own (TIME_LIMIT), so a slow hotel cannot hold a player's request.
        http.Timeout = Timeout.InfiniteTimeSpan;
        http.DefaultRequestHeaders.UserAgent.ParseAdd("Wiredbench/1.0");
        http.DefaultRequestHeaders.Accept.ParseAdd("application/json");

        return http;
    }

    [GeneratedRegex(@"^[a-z]{2}-\d{1,6}(-\d{1,6}){0,3}(\.[a-z]{2}-\d{1,6}(-\d{1,6}){0,3})*$")]
    private static partial Regex Figure();
}
