"""Two names on one address must not share a TLS connection.

nashvillehomeorganizers.com and www.nashvillehomeorganizers.com resolve to the same Cloudflare
address. The transport connects to the checked IP, so its one pool reused the connection opened for
www (SNI www) for requests to the bare name, and Cloudflare answers 403 when Host and SNI differ.
The sitemap lists the bare name, so every page but the home page was "forbidden".
"""

from __future__ import annotations

import asyncio

import httpx

from app.ingestion.crawler import safe_http


def test_each_hostname_gets_its_own_connection_pool_even_on_a_shared_address(monkeypatch):
    made: list["Pool"] = []

    class Pool(httpx.AsyncBaseTransport):
        def __init__(self, **kwargs):
            self.sni: list[str] = []
            self.closed = False
            made.append(self)

        async def handle_async_request(self, request):
            self.sni.append(request.extensions["sni_hostname"])
            return httpx.Response(200, text="ok")

        async def aclose(self):
            self.closed = True

    async def same_address(host, port):
        return ["104.21.0.1"]

    monkeypatch.setattr(safe_http.httpx, "AsyncHTTPTransport", Pool)
    monkeypatch.setattr(safe_http, "_resolve", same_address)

    async def go():
        async with httpx.AsyncClient(transport=safe_http.PublicOnlyTransport()) as client:
            for url in ("https://www.shop.example/", "https://shop.example/about.html", "https://www.shop.example/services.html"):
                await client.get(url)

    asyncio.run(go())
    assert [p.sni for p in made] == [["www.shop.example", "www.shop.example"], ["shop.example"]], "a connection only ever carries one name"
    assert all(p.closed for p in made)
