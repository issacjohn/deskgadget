"""News module: headlines for the topics and region picked in the dashboard.

Uses Google News RSS, which needs no API key and supports per-country editions.
Tapping a row opens the article on the Mac and brings the browser forward.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from core.base import Module as BaseModule

log = logging.getLogger("deskgadget.news")

SUFFIX = re.compile(r"\s+(?:-\s+[^-]{2,40}|By\s+[^-]{2,40})$")

# country -> (language tag, hl, gl, ceid) for Google News editions
REGIONS = {
    "AR": ("es-419", "AR", "AR:es-419"),
    "AT": ("de", "AT", "AT:de"),
    "AU": ("en-AU", "AU", "AU:en"),
    "BE": ("nl", "BE", "BE:nl"),
    "BG": ("bg", "BG", "BG:bg"),
    "BR": ("pt-419", "BR", "BR:pt-419"),
    "CA": ("en-CA", "CA", "CA:en"),
    "CH": ("de", "CH", "CH:de"),
    "CL": ("es-419", "CL", "CL:es-419"),
    "CN": ("zh-CN", "CN", "CN:zh-Hans"),
    "CO": ("es-419", "CO", "CO:es-419"),
    "CZ": ("cs", "CZ", "CZ:cs"),
    "DE": ("de", "DE", "DE:de"),
    "DK": ("da", "DK", "DK:da"),
    "EG": ("ar", "EG", "EG:ar"),
    "ES": ("es", "ES", "ES:es"),
    "FI": ("fi", "FI", "FI:fi"),
    "FR": ("fr", "FR", "FR:fr"),
    "GB": ("en-GB", "GB", "GB:en"),
    "GR": ("el", "GR", "GR:el"),
    "HK": ("zh-HK", "HK", "HK:zh-Hant"),
    "HU": ("hu", "HU", "HU:hu"),
    "ID": ("id", "ID", "ID:id"),
    "IE": ("en-IE", "IE", "IE:en"),
    "IL": ("he", "IL", "IL:he"),
    "IN": ("en-IN", "IN", "IN:en"),
    "IT": ("it", "IT", "IT:it"),
    "JP": ("ja", "JP", "JP:ja"),
    "KR": ("ko", "KR", "KR:ko"),
    "LT": ("lt", "LT", "LT:lt"),
    "LV": ("lv", "LV", "LV:lv"),
    "MX": ("es-419", "MX", "MX:es-419"),
    "MY": ("en-MY", "MY", "MY:en"),
    "NL": ("nl", "NL", "NL:nl"),
    "NO": ("no", "NO", "NO:no"),
    "NZ": ("en-NZ", "NZ", "NZ:en"),
    "PE": ("es-419", "PE", "PE:es-419"),
    "PH": ("en-PH", "PH", "PH:en"),
    "PK": ("en-PK", "PK", "PK:en"),
    "PL": ("pl", "PL", "PL:pl"),
    "PT": ("pt-PT", "PT", "PT:pt-PT"),
    "RO": ("ro", "RO", "RO:ro"),
    "RS": ("sr", "RS", "RS:sr"),
    "RU": ("ru", "RU", "RU:ru"),
    "SA": ("ar", "SA", "SA:ar"),
    "SE": ("sv", "SE", "SE:sv"),
    "SG": ("en-SG", "SG", "SG:en"),
    "SI": ("sl", "SI", "SI:sl"),
    "SK": ("sk", "SK", "SK:sk"),
    "TH": ("th", "TH", "TH:th"),
    "TR": ("tr", "TR", "TR:tr"),
    "TW": ("zh-TW", "TW", "TW:zh-Hant"),
    "UA": ("uk", "UA", "UA:uk"),
    "US": ("en-US", "US", "US:en"),
    "VE": ("es-419", "VE", "VE:es-419"),
    "VN": ("vi", "VN", "VN:vi"),
    "ZA": ("en-ZA", "ZA", "ZA:en"),
}

# Google News has eight official section feeds; everything else is a query
TOPIC_SLUGS = {
    "TECH": "headlines/section/topic/TECHNOLOGY",
    "BUSINESS": "headlines/section/topic/BUSINESS",
    "WORLD": "headlines/section/topic/WORLD",
    "NATION": "headlines/section/topic/NATION",
    "SPORTS": "headlines/section/topic/SPORTS",
    "SCIENCE": "headlines/section/topic/SCIENCE",
    "HEALTH": "headlines/section/topic/HEALTH",
    "ENTERTAINMENT": "headlines/section/topic/ENTERTAINMENT",
}

TOPIC_QUERIES = {
    "STOCKS": "stock market",
    "CRYPTO": "cryptocurrency",
    "AI": "artificial intelligence",
    "GAMING": "video games",
    "STARTUPS": "startups",
    "POLITICS": "politics",
    "CLIMATE": "climate change",
    "SPACE": "space exploration",
    "MOVIES": "movies",
    "MUSIC": "music",
    "CRICKET": "cricket",
    "FOOTBALL": "football",
    "ELECTIONS": "elections",
}


def _feed_url(topic: str, hl: str, gl: str, ceid: str) -> str:
    key = topic.strip().upper()
    if key in TOPIC_QUERIES:
        query = requests.utils.quote(TOPIC_QUERIES[key])
        return (
            f"https://news.google.com/rss/search?q={query}"
            f"&hl={hl}&gl={gl}&ceid={ceid}"
        )
    slug = TOPIC_SLUGS.get(key)
    if slug is not None:
        return f"https://news.google.com/rss/{slug}?hl={hl}&gl={gl}&ceid={ceid}"
    # anything the user typed under "Other topics" is just a search
    if topic.strip():
        query = requests.utils.quote(topic.strip())
        return (
            f"https://news.google.com/rss/search?q={query}"
            f"&hl={hl}&gl={gl}&ceid={ceid}"
        )
    return ""


def _topic_label(topic: str) -> str:
    key = topic.strip().upper()
    if key in TOPIC_QUERIES or key in TOPIC_SLUGS:
        return key.replace("_", " ")
    return topic.strip()


def _ago(published: datetime | None) -> str:
    if published is None:
        return ""
    delta = (datetime.now(timezone.utc) - published).total_seconds()
    if delta < 3600:
        return f"{max(1, int(delta // 60))}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}d"


class Module(BaseModule):
    refreshable = True

    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.items: list[dict] = []
        self.error: str | None = None
        self.updated_at = 0.0
        self._country: str | None = None
        self._country_at = 0.0

    async def on_start(self) -> None:
        # migrate the old single-region setting to the new multi-select
        if not self.settings.get("regions") and self.settings.get("region"):
            old = str(self.settings["region"]).upper()
            if old in REGIONS:
                self.settings["regions"] = [old]
                self.settings.pop("region", None)
                try:
                    self.hub.store.set_module_settings(self.id, self.settings)
                except Exception:
                    pass

    async def on_settings(self) -> None:
        self.items = []
        self.error = None
        await self.update()
        self.push()

    async def update(self) -> None:
        try:
            self.items = await asyncio.to_thread(self._fetch)
            self.error = None
            self.updated_at = time.time()
        except Exception as exc:
            self.error = str(exc)[:120]
            log.warning("news fetch failed: %s", exc)

    # -- fetch -------------------------------------------------------------
    def _topics(self) -> list[str]:
        raw = self.settings.get("topics")
        if isinstance(raw, list):
            topics = [str(t).upper() for t in raw]
        elif isinstance(raw, str) and raw.strip():
            topics = [t.strip().upper() for t in raw.split(",")]
        else:
            topics = []
        return topics

    def _custom_topics(self) -> list[str]:
        """Free-text topics typed under "Other topics"."""
        raw = self.settings.get("custom")
        if isinstance(raw, list):
            parts = [str(p) for p in raw]
        else:
            parts = re.split(r"[,\n;]+", str(raw or ""))
        out: list[str] = []
        for part in parts:
            text = part.strip()
            if not text:
                continue
            # don't duplicate a preset the user also ticked
            if text.upper() in TOPIC_SLUGS or text.upper() in TOPIC_QUERIES:
                text = text.upper()
            if text not in out:
                out.append(text)
        return out[:6]

    def _all_topics(self) -> list[str]:
        topics = self._topics()
        for custom in self._custom_topics():
            if custom.upper() not in {t.upper() for t in topics}:
                topics.append(custom)
        return topics or ["TECH", "BUSINESS"]

    def _detect_country(self) -> str:
        """Country from the public IP, cached for a day."""
        if self._country and time.time() - self._country_at < 86400:
            return self._country
        try:
            r = requests.get(
                "http://ip-api.com/json/?fields=status,countryCode",
                timeout=6,
            )
            data = r.json()
            if data.get("status") == "success":
                code = str(data.get("countryCode", "")).upper()
                if code in REGIONS:
                    self._country = code
                    self._country_at = time.time()
                    return code
        except Exception:
            log.warning("country detection failed")
        return "US"

    def _regions(self) -> list[str]:
        raw = self.settings.get("regions")
        if isinstance(raw, list) and raw:
            codes = [str(r).upper() for r in raw]
        elif isinstance(raw, str) and raw.strip():
            codes = [r.strip().upper() for r in raw.split(",")]
        else:
            codes = []
        codes = [c for c in codes if c in REGIONS]
        if not codes:
            # nothing picked: use wherever this Mac actually is
            codes = [self._detect_country()]
        return codes[:6]

    def _fetch(self) -> list[dict]:
        limit = int(self.settings.get("limit", 8) or 8)
        topics = self._all_topics()
        regions = self._regions()

        rows: list[dict] = []
        seen: set[str] = set()

        for region in regions:
            hl, gl, ceid = REGIONS[region]
            for topic in topics:
                url = _feed_url(topic, hl, gl, ceid)
                if not url:
                    continue
                try:
                    response = requests.get(
                        url,
                        timeout=12,
                        headers={"User-Agent": "Mozilla/5.0 (DeskGadget)"},
                    )
                    response.raise_for_status()
                    root = ET.fromstring(response.content)
                except Exception:
                    log.warning("feed failed: %s/%s", region, topic)
                    continue

                for item in root.findall(".//item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    if not title or not link:
                        continue
                    title = SUFFIX.sub("", title).strip()
                    key = title.lower()
                    if key in seen:
                        continue
                    seen.add(key)

                    source_el = item.find("source")
                    source = (source_el.text if source_el is not None else "") or ""
                    domain = ""
                    if source_el is not None:
                        try:
                            from urllib.parse import urlparse

                            domain = urlparse(source_el.get("url", "")).netloc
                        except Exception:
                            domain = ""
                    image = (
                        f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
                        if domain
                        else ""
                    )
                    published = None
                    pub = item.findtext("pubDate")
                    if pub:
                        try:
                            published = parsedate_to_datetime(pub)
                            if published.tzinfo is None:
                                published = published.replace(tzinfo=timezone.utc)
                        except Exception:
                            published = None

                    rows.append(
                        {
                            "title": title,
                            "sub": source.strip() or topic.title(),
                            "value": _ago(published),
                            "url": link,
                            "image": image,
                            "ts": published.timestamp() if published else 0,
                        }
                    )

        rows.sort(key=lambda r: r["ts"], reverse=True)
        return rows[:limit]

    # -- actions -----------------------------------------------------------
    async def on_action(self, action: str, payload: dict) -> None:
        if action == "refresh":
            await self.update()
            self.push()
            return
        if action != "open":
            return
        url = str(payload.get("url", ""))
        # only open links this module actually served
        allowed = {row["url"] for row in self.items}
        if url not in allowed:
            await self.hub.notify("That link is not from the feed")
            return
        try:
            from core.web import open_url

            open_url(url)
            await self.hub.notify("Opened on the Mac")
        except Exception:
            log.exception("could not open %s", url)

    # -- render ------------------------------------------------------------
    def page(self) -> dict:
        regions = self._regions()
        topics = self._all_topics()

        if not self.items:
            return {
                "blocks": [
                    {
                        "type": "hero",
                        "label": "NEWS",
                        "value": "--",
                        "unit": "",
                        "sub": self.error or "Fetching headlines…",
                        "accent": "#FFB86B",
                    }
                ]
            }

        region_label = " · ".join(regions)
        return {
            "blocks": [
                {
                    "type": "news",
                    "title": f"{region_label} · {' / '.join(_topic_label(t) for t in topics)}",
                    "items": [
                        {
                            "title": row["title"],
                            "source": row["sub"],
                            "ago": row["value"],
                            "url": row["url"],
                            "image": row.get("image", ""),
                            "action": "open",
                        }
                        for row in self.items
                    ],
                }
            ]
        }
