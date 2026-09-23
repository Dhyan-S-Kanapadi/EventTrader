"""Bounded public evidence collection. Provider content is always untrusted data."""

import hashlib
import ipaddress
import socket
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID
from xml.etree import ElementTree

import httpx

from eventtrader.domain.research import EvidenceCreate


class EvidenceError(RuntimeError):
    pass


class EvidenceProvider(Protocol):
    async def collect(self, market_id: UUID) -> list[EvidenceCreate]: ...


class ManualEvidenceProvider:
    def __init__(self, documents: list[EvidenceCreate]):
        self.documents = documents

    async def collect(self, market_id: UUID) -> list[EvidenceCreate]:
        del market_id
        return self.documents


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript", "template"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "template"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sanitize_html(value: str) -> str:
    parser = _VisibleText()
    parser.feed(value)
    return " ".join(parser.parts)


class HttpEvidenceFetcher:
    def __init__(self, *, timeout: float, max_bytes: int):
        self.timeout = timeout
        self.max_bytes = max_bytes

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise EvidenceError("INVALID_PUBLIC_URL")
        try:
            addresses = socket.getaddrinfo(
                parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise EvidenceError("SOURCE_UNAVAILABLE") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise EvidenceError("NON_PUBLIC_SOURCE")

    async def fetch(self, source: EvidenceCreate) -> EvidenceCreate:
        url = str(source.source_url)
        await __import__("asyncio").to_thread(self._validate_public_url, url)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                headers={"User-Agent": "EventTrader/0.2 read-only research"},
            ) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    media_type = response.headers.get("content-type", "").split(";", 1)[0]
                    if media_type not in {
                        "text/html",
                        "text/plain",
                        "application/xhtml+xml",
                        "application/xml",
                        "text/xml",
                        "application/rss+xml",
                        "application/atom+xml",
                    }:
                        raise EvidenceError("UNSUPPORTED_CONTENT_TYPE")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > self.max_bytes:
                            raise EvidenceError("SOURCE_TOO_LARGE")
        except httpx.HTTPError as exc:
            raise EvidenceError("SOURCE_UNAVAILABLE") from exc
        decoded = bytes(data).decode(response.encoding or "utf-8", errors="replace")
        text = sanitize_html(decoded) if "html" in media_type else decoded
        text = " ".join(text.split())
        if not text:
            raise EvidenceError("EMPTY_SOURCE")
        return source.model_copy(
            update={
                "extracted_text": text,
                "source_type": "webpage",
                "published_at": source.published_at,
            }
        )


class RSSEvidenceProvider:
    """Collect up to 20 timestamped items from each configured public RSS/Atom feed."""

    def __init__(self, urls: list[str], fetcher: HttpEvidenceFetcher):
        self.urls = urls
        self.fetcher = fetcher

    @staticmethod
    def _published(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)

    async def collect(self, market_id: UUID) -> list[EvidenceCreate]:
        del market_id
        documents: list[EvidenceCreate] = []
        for url in self.urls:
            seed = EvidenceCreate.model_validate(
                {
                    "source_url": url,
                    "publisher": urlparse(url).hostname,
                    "source_type": "webpage",
                    "trust_level": "standard",
                }
            )
            fetched = await self.fetcher.fetch(seed)
            try:
                root = ElementTree.fromstring(fetched.extracted_text or "")
            except ElementTree.ParseError as exc:
                raise EvidenceError("INVALID_RSS") from exc
            channel_title = root.findtext("./channel/title") or fetched.publisher
            items = root.findall("./channel/item")
            if not items:
                items = root.findall("{*}entry")
            for item in items[:20]:
                title = item.findtext("title") or item.findtext("{*}title")
                link = item.findtext("link")
                if not link:
                    link_node = item.find("{*}link")
                    link = link_node.get("href") if link_node is not None else None
                published = self._published(
                    item.findtext("pubDate")
                    or item.findtext("{*}published")
                    or item.findtext("{*}updated")
                )
                body = (
                    item.findtext("description")
                    or item.findtext("{*}summary")
                    or item.findtext("{*}content")
                    or ""
                )
                text = sanitize_html(body)
                if not link or not published or not text:
                    continue
                try:
                    document = EvidenceCreate.model_validate(
                        {
                            "source_url": link,
                            "publisher": channel_title,
                            "title": title,
                            "published_at": published,
                            "extracted_text": text,
                            "source_type": "rss",
                            "trust_level": "standard",
                        }
                    )
                except ValueError:
                    continue
                documents.append(document)
        return documents
