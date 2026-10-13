"""An HTTP transport that will only talk to the public internet.

The crawler fetches addresses a person typed in: a client's domain, its
sitemap URL, and whatever those documents list. Nothing stopped one of those
being `169.254.169.254` (the cloud metadata service), `localhost`, or a
hostname on Railway's private network — and the worker that makes the request
holds the database URL and every integration key. What came back was kept
(page titles, JSON-LD, error text), so it was a way to read from inside.

The check is in the transport, not the caller, because the caller does not
see every request: httpx follows redirects below it, and a public address
that redirects to an internal one is the standard way round a check made only
on the first URL. Every hop passes through here.

Resolving a name and then letting the client resolve it again is also a gap:
a DNS server can answer "public" the first time and "internal" the second.
So the connection is made to the address that was checked, and the original
name is kept for the Host header and TLS.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Iterable

import httpx

#: Where a crawl may connect. Ordinary sites use 80 and 443; the two
#: alternates are the usual staging ports and cost nothing to allow.
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})


class UnsafeDestination(httpx.TransportError):
    """The address is not one the crawler may contact.

    A subclass of httpx's own error so every existing `except httpx.HTTPError`
    in the crawler records it as a fetch failure instead of crashing the job.
    """


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    # ::ffff:10.0.0.1 is 10.0.0.1 wearing an IPv6 coat.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_addresses(host: str, addresses: Iterable[str]) -> list[str]:
    """The addresses to use, or UnsafeDestination if any is not public.

    One non-public answer rejects the lot. A name that resolves to a public
    and a private address is a name somebody has arranged, and picking the
    public one would be a coin toss the attacker can re-flip.
    """
    found = list(dict.fromkeys(addresses))
    if not found:
        raise UnsafeDestination(f"{host} did not resolve")
    for address in found:
        if not _public(address):
            raise UnsafeDestination(f"{host} is not a public address")
    return found


async def _resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeDestination(f"{host} did not resolve") from exc
    return [info[4][0] for info in infos]


class PublicOnlyTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport | None = None, **kwargs) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport(**kwargs)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.scheme not in ("http", "https"):
            raise UnsafeDestination(f"scheme {url.scheme!r} is not allowed")
        host = url.host
        if not host:
            raise UnsafeDestination("no host")
        port = url.port or (443 if url.scheme == "https" else 80)
        if port not in ALLOWED_PORTS:
            raise UnsafeDestination(f"port {port} is not allowed")

        try:
            ipaddress.ip_address(host)
            addresses = [host]
        except ValueError:
            addresses = await _resolve(host, port)
        chosen = check_addresses(host, addresses)[0]

        # Connect to the address that was checked. The Host header httpx already
        # set carries the name, and `sni_hostname` makes TLS verify the
        # certificate against the name rather than the number.
        #
        # A copy, never the caller's request: httpx resolves a relative
        # Location against that object and reports `response.url` from it, so
        # rewriting it in place would turn every redirect into one on the
        # bare IP.
        if chosen != host:
            request = httpx.Request(
                request.method,
                url.copy_with(host=chosen),
                headers=request.headers,
                stream=request.stream,
                extensions={**request.extensions, "sni_hostname": host},
            )
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()
