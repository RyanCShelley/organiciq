"""The crawler may not be pointed at anything but the public internet.

It fetches whatever a person typed as a client's domain or sitemap, plus
whatever those documents list, from a worker that holds the database URL and
every integration key.
"""

from __future__ import annotations

import httpx
import pytest

from app.ingestion.crawler import safe_http
from app.ingestion.crawler.safe_http import PublicOnlyTransport, UnsafeDestination, check_addresses


class _Recorder(httpx.AsyncBaseTransport):
    """Stands in for the network and remembers what it was asked."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return httpx.Response(200, text="ok", request=request)


def _client(monkeypatch, dns: dict[str, list[str]]):
    recorder = _Recorder()

    async def fake_resolve(host: str, port: int) -> list[str]:
        if host not in dns:
            raise UnsafeDestination(f"{host} did not resolve")
        return dns[host]

    monkeypatch.setattr(safe_http, "_resolve", fake_resolve)
    return httpx.AsyncClient(transport=PublicOnlyTransport(recorder)), recorder


# ── Addresses ──


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",          # loopback
        "10.1.2.3",           # private
        "172.16.0.5",         # private
        "192.168.1.1",        # private
        "169.254.169.254",    # cloud metadata
        "100.64.0.1",         # carrier-grade NAT, which Railway's network uses
        "0.0.0.0",
        "::1",
        "fe80::1",            # link-local
        "fd00::1",            # unique local
        "::ffff:10.0.0.1",    # private IPv4 wearing an IPv6 coat
        "224.0.0.1",          # multicast
    ],
)
def test_a_non_public_address_is_refused(address):
    with pytest.raises(UnsafeDestination):
        check_addresses("x.test", [address])


@pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"])
def test_a_public_address_is_allowed(address):
    assert check_addresses("x.test", [address]) == [address]


def test_one_private_answer_rejects_the_name():
    """A name resolving to a public and a private address has been arranged."""
    with pytest.raises(UnsafeDestination):
        check_addresses("x.test", ["93.184.216.34", "10.0.0.5"])


def test_a_name_that_does_not_resolve_is_refused():
    with pytest.raises(UnsafeDestination):
        check_addresses("x.test", [])


# ── The transport ──


async def test_a_hostname_resolving_to_an_internal_address_is_never_contacted(monkeypatch):
    client, recorder = _client(monkeypatch, {"evil.test": ["169.254.169.254"]})
    with pytest.raises(UnsafeDestination):
        await client.get("https://evil.test/sitemap.xml")
    assert recorder.seen == []


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://10.0.0.5:8080/",
    ],
)
async def test_an_ip_literal_that_is_not_public_is_refused(monkeypatch, url):
    client, recorder = _client(monkeypatch, {})
    with pytest.raises(UnsafeDestination):
        await client.get(url)
    assert recorder.seen == []


async def test_a_redirect_to_an_internal_address_is_stopped_on_the_second_hop(monkeypatch):
    """Checking only the first URL is the standard way round a guard."""
    seen = []

    class Redirecting(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            seen.append(str(request.url))
            return httpx.Response(
                302, headers={"location": "http://169.254.169.254/latest/"}, request=request
            )

    async def fake_resolve(host, port):
        return {"good.test": ["93.184.216.34"]}[host]

    monkeypatch.setattr(safe_http, "_resolve", fake_resolve)
    client = httpx.AsyncClient(transport=PublicOnlyTransport(Redirecting()), follow_redirects=True)
    with pytest.raises(UnsafeDestination):
        await client.get("https://good.test/sitemap.xml")
    assert len(seen) == 1  # the metadata address was never contacted


@pytest.mark.parametrize("url", ["ftp://good.test/x", "file:///etc/passwd", "gopher://good.test/"])
async def test_only_http_and_https_are_allowed(monkeypatch, url):
    client, recorder = _client(monkeypatch, {"good.test": ["93.184.216.34"]})
    with pytest.raises((UnsafeDestination, httpx.UnsupportedProtocol)):
        await client.get(url)
    assert recorder.seen == []


async def test_an_unusual_port_is_refused(monkeypatch):
    """Database and cache ports on a public host are not a crawl target."""
    client, recorder = _client(monkeypatch, {"good.test": ["93.184.216.34"]})
    with pytest.raises(UnsafeDestination):
        await client.get("https://good.test:5432/")
    assert recorder.seen == []


async def test_the_connection_goes_to_the_address_that_was_checked(monkeypatch):
    """A name that resolved public once must not be resolved again by the client."""
    client, recorder = _client(monkeypatch, {"good.test": ["93.184.216.34"]})
    response = await client.get("https://good.test/robots.txt")
    assert response.status_code == 200
    sent = recorder.seen[0]
    assert sent.url.host == "93.184.216.34"
    assert sent.headers["host"] == "good.test"
    assert sent.extensions["sni_hostname"] == "good.test"
    # The caller's view is the name, so relative redirects and response.url
    # still resolve against the site and not against a bare IP.
    assert response.request.url.host == "good.test"


async def test_a_public_ip_literal_passes_through_unchanged(monkeypatch):
    client, recorder = _client(monkeypatch, {})
    await client.get("http://93.184.216.34/")
    assert recorder.seen[0].url.host == "93.184.216.34"


# ── Size ceilings ──


async def test_a_response_past_the_cap_is_abandoned():
    from app.ingestion.crawler.fetch import ResponseTooLarge, _get_capped

    big = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 5000))
    async with httpx.AsyncClient(transport=big) as client:
        status, _, body = await _get_capped(client, "https://good.test/a", 10_000)
        assert (status, len(body)) == (200, 5000)
        with pytest.raises(ResponseTooLarge):
            await _get_capped(client, "https://good.test/a", 1000)


def test_a_gzip_bomb_is_not_inflated():
    import gzip

    from app.ingestion.crawler.fetch import ResponseTooLarge, _gunzip_capped

    bomb = gzip.compress(b"0" * 5_000_000)  # a few KB that expands to 5 MB
    assert len(bomb) < 10_000
    with pytest.raises(ResponseTooLarge):
        _gunzip_capped(bomb, 1_000_000)
    assert len(_gunzip_capped(gzip.compress(b"<urlset/>"), 1_000_000)) == len(b"<urlset/>")


async def test_a_corrupt_gzip_sitemap_is_a_recorded_failure_not_a_crash():
    from app.ingestion.crawler.fetch import _load_sitemap_urls

    corrupt = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"\x1f\x8b" + b"not really gzip")
    )
    failures: list[tuple[str, str]] = []
    async with httpx.AsyncClient(transport=corrupt) as client:
        found = await _load_sitemap_urls(
            client, ["https://good.test/sitemap.xml.gz"], host="good.test", budget=10,
            failures=failures,
        )
    assert found == {}
    assert failures and "could not be fetched" in failures[0][1]


# ── Refused when saved ──


@pytest.mark.parametrize(
    "value",
    [
        "localhost", "http://localhost:8000", "127.0.0.1", "http://169.254.169.254/",
        "10.0.0.5", "https://[::1]/", "db.railway.internal", "http://printer.local/",
        "intranet", "ftp://example.com", "https://user:pass@example.com/",
    ],
)
def test_an_internal_domain_is_refused_when_saved(value):
    from app.core.urls import public_host_or_error

    assert public_host_or_error(value), value


@pytest.mark.parametrize(
    "value", ["example.com", "https://www.example.com/sitemap.xml", "sub.example.co.uk", "93.184.216.34", "", None]
)
def test_a_public_domain_is_accepted(value):
    from app.core.urls import public_host_or_error

    assert public_host_or_error(value) is None


def test_the_client_schemas_apply_it():
    from uuid import uuid4

    from pydantic import ValidationError

    from app.schemas import ClientCreate, ClientUpdate

    with pytest.raises(ValidationError):
        ClientUpdate(domain="169.254.169.254")
    with pytest.raises(ValidationError):
        ClientUpdate(sitemap_url="http://localhost/sitemap.xml")
    with pytest.raises(ValidationError):
        ClientCreate(client_name="x", domain="db.railway.internal", tier_id=uuid4())
    assert ClientUpdate(domain="example.com", sitemap_url="https://example.com/s.xml").domain == "example.com"
    assert ClientUpdate().domain is None
