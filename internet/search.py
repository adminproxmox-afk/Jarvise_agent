from __future__ import annotations

import asyncio
import html
import re
import time
from typing import Any
from urllib.parse import quote_plus

import httpx

try:  # Optional extras expand research quality when installed.
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None

try:  # pragma: no cover - optional dependency
    import feedparser
except Exception:  # pragma: no cover - optional dependency
    feedparser = None

try:  # pragma: no cover - optional dependency
    from cachetools import TTLCache
except Exception:  # pragma: no cover - optional dependency
    TTLCache = None

try:  # pragma: no cover - optional dependency
    from tenacity import retry, stop_after_attempt, wait_exponential
except Exception:  # pragma: no cover - optional dependency
    def retry(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    def stop_after_attempt(*args: Any, **kwargs: Any):
        return None

    def wait_exponential(*args: Any, **kwargs: Any):
        return None

from ai.gateway import AIMessage


DUCKDUCKGO_API = "https://api.duckduckgo.com/"


class InternetService:
    """Simple internet facade for search and documentation lookups."""

    def __init__(self) -> None:
        self._search_cache: Any = TTLCache(maxsize=256, ttl=300) if TTLCache else {}
        self._headers = {
            "User-Agent": "Jarvise/1.0 (+https://duckduckgo.com/; research assistant)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    async def search(self, query: str) -> dict[str, Any]:
        cached = self._cache_get(query)
        if cached is not None:
            return cached

        if self._is_news_query(query):
            result = await self._news_answer(query)
            self._cache_set(query, result)
            return result

        params = {
            "q": query,
            "format": "json",
            "no_redirect": 1,
            "no_html": 1,
            "skip_disambig": 1,
            "t": "jarvis",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(DUCKDUCKGO_API, params=params)
            response.raise_for_status()
            data = response.json()

        sources = self._extract_sources(data)
        snippets = await self._collect_page_snippets(sources)
        summary = self._build_summary(data, snippets)
        result = {
            "query": query,
            "summary": summary,
            "raw": {**data, "page_snippets": snippets},
            "sources": sources,
            "snippets": snippets,
        }
        self._cache_set(query, result)
        return result

    async def _news_answer(self, query: str) -> dict[str, Any]:
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=uk&gl=UA&ceid=UA:uk"
        entries: list[dict[str, str]] = []

        if feedparser is not None:
            try:
                feed = await asyncio.to_thread(feedparser.parse, rss_url)
                for entry in getattr(feed, "entries", [])[:5]:
                    if not isinstance(entry, dict):
                        continue
                    title = str(entry.get("title") or "").strip()
                    url = str(entry.get("link") or "").strip()
                    published = str(entry.get("published") or entry.get("updated") or "").strip()
                    if title or url:
                        entries.append({"title": title or url, "url": url, "published": published})
            except Exception:
                entries = []

        summary = self._build_news_summary(query, entries)
        sources = [
            {"title": item["title"], "url": item["url"]}
            for item in entries
            if item.get("url")
        ]
        return {
            "query": query,
            "summary": summary,
            "answer": summary,
            "sources": sources,
            "snippets": entries,
            "raw": {"query": query, "rss_url": rss_url, "entries": entries},
        }

    async def answer(
        self,
        query: str,
        *,
        gateway: Any | None = None,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        if self._is_weather_query(query):
            return await self._weather_answer(query)

        search_result = await self.search(query)
        raw = search_result["raw"]
        sources = self._extract_sources(raw)
        snippets = search_result.get("snippets", [])
        answer = ""

        if gateway is not None:
            messages = [
                AIMessage(
                    role="system",
                    content=(
                        (system_prompt.strip() + "\n\n") if system_prompt.strip() else ""
                        + "You are a web research assistant for Jarvise. Answer in the user's language using only the"
                        " search context below. If the results are incomplete, say so briefly instead of guessing."
                        " Keep the answer concise and useful."
                    ),
                ),
                AIMessage(
                    role="user",
                    content=(
                        f"Question: {query}\n\n"
                        f"Search summary: {search_result['summary'] or 'none'}\n\n"
                        f"Sources:\n{self._format_sources(sources)}\n\n"
                        f"Page snippets:\n{self._format_page_snippets(snippets)}\n\n"
                        f"Raw context:\n{self._format_raw_context(raw)}"
                    ),
                ),
            ]
            try:
                response = await gateway.chat(messages, task_type="search", temperature=0.1)
            except Exception:
                response = None
            if response and str(getattr(response, "text", "")).strip():
                answer = str(response.text).strip()

        if not answer:
            answer = str(search_result["summary"] or "").strip()
        if not answer:
            answer = "Не вдалося знайти точну відповідь. Спробуйте уточнити запит."

        return {
            "query": query,
            "answer": answer,
            "summary": search_result["summary"],
            "sources": sources,
            "snippets": snippets,
            "raw": raw,
        }

    async def _weather_answer(self, query: str) -> dict[str, Any]:
        location = self._extract_location(query)
        if not location:
            search_result = await self.search(f"{query} weather")
            return {
                "query": query,
                "answer": search_result["summary"],
                "summary": search_result["summary"],
                "sources": self._extract_sources(search_result["raw"]),
                "raw": search_result["raw"],
            }

        location_data = await self._geocode_location(location)
        if not location_data:
            search_result = await self.search(f"{location} weather")
            return {
                "query": query,
                "answer": search_result["summary"],
                "summary": search_result["summary"],
                "sources": self._extract_sources(search_result["raw"]),
                "raw": search_result["raw"],
            }

        forecast = await self._fetch_current_weather(location_data["latitude"], location_data["longitude"])
        current = forecast.get("current") if isinstance(forecast, dict) else {}
        if not isinstance(current, dict):
            current = {}

        city_name = ", ".join(
            part
            for part in (
                str(location_data.get("name") or "").strip(),
                str(location_data.get("admin1") or "").strip(),
                str(location_data.get("country") or "").strip(),
            )
            if part
        )
        weather_code = int(current.get("weather_code") or 0)
        description = self._weather_code_description(weather_code)
        temperature = current.get("temperature_2m")
        feels_like = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind_speed = current.get("wind_speed_10m")
        precipitation = current.get("precipitation")
        time_value = str(current.get("time") or "").strip()

        answer_parts = [f"Зараз у {city_name or location}:"]
        if temperature is not None:
            answer_parts.append(f"температура {self._format_number(temperature)}°C")
        if feels_like is not None:
            answer_parts.append(f"відчувається як {self._format_number(feels_like)}°C")
        if humidity is not None:
            answer_parts.append(f"вологість {self._format_number(humidity)}%")
        if wind_speed is not None:
            answer_parts.append(f"вітер {self._format_number(wind_speed)} км/год")
        if precipitation is not None:
            answer_parts.append(f"опади {self._format_number(precipitation)} мм")
        if description:
            answer_parts.append(f"стан: {description}")
        if time_value:
            answer_parts.append(f"час оновлення: {time_value}")

        return {
            "query": query,
            "location": location_data,
            "answer": ", ".join(answer_parts).rstrip(", "),
            "summary": description,
            "sources": [
                {
                    "title": "Open-Meteo Forecast",
                    "url": "https://open-meteo.com/en/docs",
                }
            ],
            "raw": {"location": location_data, "forecast": forecast},
        }

    async def _geocode_location(self, location: str) -> dict[str, Any] | None:
        candidates = self._location_candidates(location)
        async with httpx.AsyncClient(timeout=10.0) as client:
            for candidate in candidates:
                response = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={
                        "name": candidate,
                        "count": 1,
                        "language": "en",
                        "format": "json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("results")
                if isinstance(results, list) and results:
                    first = results[0]
                    if isinstance(first, dict):
                        return first
        return None

    async def _fetch_current_weather(self, latitude: float, longitude: float) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
                    "timezone": "auto",
                    "wind_speed_unit": "kmh",
                    "temperature_unit": "celsius",
                    "precipitation_unit": "mm",
                },
            )
            response.raise_for_status()
            return response.json()

    def _cache_get(self, query: str) -> dict[str, Any] | None:
        key = self._cache_key(query)
        if TTLCache is not None:
            return self._search_cache.get(key)

        item = self._search_cache.get(key)
        if not item:
            return None
        created_at, value = item
        if time.monotonic() - float(created_at) > 300:
            self._search_cache.pop(key, None)
            return None
        return value

    def _cache_set(self, query: str, value: dict[str, Any]) -> None:
        key = self._cache_key(query)
        if TTLCache is not None:
            self._search_cache[key] = value
            return
        self._search_cache[key] = (time.monotonic(), value)

    @staticmethod
    def _cache_key(query: str) -> str:
        return re.sub(r"\s+", " ", query.strip().lower())

    async def _collect_page_snippets(self, sources: list[dict[str, Any]]) -> list[dict[str, str]]:
        snippets: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for source in sources[:3]:
            url = str(source.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                snippet = await self._fetch_page_snippet(url)
            except Exception:
                continue
            if snippet:
                snippets.append(
                    {
                        "title": str(source.get("title") or url).strip() or url,
                        "url": url,
                        "snippet": snippet,
                    }
                )
        return snippets

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.4, min=1, max=4), reraise=True)
    async def _fetch_page_snippet(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=self._headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = str(response.headers.get("content-type") or "").lower()
            if "html" not in content_type and "xml" not in content_type and "text" not in content_type:
                return ""
            return self._extract_html_snippet(response.text)

    @staticmethod
    def _extract_html_snippet(html_text: str) -> str:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            pieces: list[str] = []
            title = str(getattr(soup.title, "get_text", lambda **_: "")()).strip() if soup.title else ""
            if title:
                pieces.append(title)
            for element in soup.find_all(["p", "li"]):
                text = element.get_text(" ", strip=True)
                if len(text) >= 40:
                    pieces.append(text)
                if sum(len(part) for part in pieces) >= 1400:
                    break
            combined = " ".join(pieces)
        else:
            combined = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
            combined = re.sub(r"<[^>]+>", " ", combined)
        combined = html.unescape(re.sub(r"\s+", " ", combined)).strip()
        return combined[:1400]

    @staticmethod
    def _is_news_query(query: str) -> bool:
        normalized = query.lower().replace("ё", "е")
        return any(
            keyword in normalized
            for keyword in (
                "news",
                "latest",
                "breaking",
                "новини",
                "новости",
                "останні",
                "останні новини",
                "свіжі новини",
                "свежие новости",
            )
        )

    @staticmethod
    def _build_summary(data: dict[str, Any], snippets: list[dict[str, Any]] | None = None) -> str:
        if text := str(data.get("AbstractText") or "").strip():
            return html.unescape(text)
        if answer := str(data.get("Answer") or "").strip():
            return html.unescape(answer)
        if related := data.get("RelatedTopics"):
            if isinstance(related, list) and related:
                first = related[0]
                if isinstance(first, dict):
                    if topic_text := str(first.get("Text") or "").strip():
                        return html.unescape(topic_text)
                    if topic_topics := first.get("Topics"):
                        if isinstance(topic_topics, list) and topic_topics:
                            nested = topic_topics[0]
                            if isinstance(nested, dict):
                                return html.unescape(str(nested.get("Text") or "").strip())
        if snippets:
            first_snippet = str((snippets[0] or {}).get("snippet") or "").strip()
            if first_snippet:
                return first_snippet
        if url := str(data.get("AbstractURL") or data.get("AnswerURL") or "").strip():
            return f"Немає чіткого короткого відповіді. Спробуйте відкрити: {url}"

        if results := data.get("Results"):
            if isinstance(results, list) and results:
                first = results[0]
                if isinstance(first, dict) and first.get("FirstURL"):
                    return f"Немає чіткого короткого відповіді. Спробуйте відкрити: {first['FirstURL']}"
        return "Не вдалося знайти коротку відповідь. Спробуйте уточнити запит."

    @staticmethod
    def _build_news_summary(query: str, entries: list[dict[str, str]]) -> str:
        if not entries:
            return f"Не вдалося знайти свіжі новини за запитом: {query}."
        lines = [f"Останні новини за запитом: {query}."]
        for item in entries[:5]:
            title = str(item.get("title") or "").strip()
            published = str(item.get("published") or "").strip()
            if published:
                lines.append(f"- {title} ({published})")
            else:
                lines.append(f"- {title}")
        return "\n".join(lines)

    @staticmethod
    def _is_weather_query(query: str) -> bool:
        normalized = query.lower().replace("ё", "е")
        return any(
            keyword in normalized
            for keyword in ("погода", "weather", "прогноз", "температура", "rain", "snow", "wind", "дощ", "сніг", "вітер")
        )

    @staticmethod
    def _extract_location(query: str) -> str | None:
        text = query.strip()
        normalized = text.lower().replace("ё", "е")

        patterns = [
            r"(?:погода|weather|прогноз(?: погоди)?|температура)\s+(?:в|у|на|для)\s+(.+)$",
            r"(?:в|у|на|для)\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1)
                candidate = re.sub(
                    r"\b(?:сьогодні|зараз|today|now|на\s+сьогодні|на\s+завтра|tomorrow|сьогоднішня|поточна)\b",
                    "",
                    candidate,
                    flags=re.IGNORECASE,
                )
                candidate = re.sub(r"[?.!,;:]+$", "", candidate).strip()
                if candidate:
                    return candidate
        return None

    @staticmethod
    def _location_candidates(location: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", location).strip()
        candidates = [cleaned]
        stripped = re.sub(r"^(?:в|у|на|для)\s+", "", cleaned, flags=re.IGNORECASE).strip()
        if stripped and stripped not in candidates:
            candidates.append(stripped)

        transliterated = InternetService._transliterate_ukrainian(stripped or cleaned)
        for candidate in (
            transliterated,
            f"{transliterated}, Ukraine" if transliterated else "",
            f"{stripped}, Ukraine" if stripped else "",
        ):
            candidate = candidate.strip()
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _transliterate_ukrainian(text: str) -> str:
        mapping = {
            "а": "a",
            "б": "b",
            "в": "v",
            "г": "h",
            "ґ": "g",
            "д": "d",
            "е": "e",
            "є": "ie",
            "ж": "zh",
            "з": "z",
            "и": "y",
            "і": "i",
            "ї": "i",
            "й": "i",
            "к": "k",
            "л": "l",
            "м": "m",
            "н": "n",
            "о": "o",
            "п": "p",
            "р": "r",
            "с": "s",
            "т": "t",
            "у": "u",
            "ф": "f",
            "х": "kh",
            "ц": "ts",
            "ч": "ch",
            "ш": "sh",
            "щ": "shch",
            "ь": "",
            "ю": "iu",
            "я": "ia",
            "’": "",
            "'": "",
            " ": " ",
            "-": "-",
        }
        transliterated = "".join(mapping.get(char, char) for char in text.lower())
        transliterated = re.sub(r"\s+", " ", transliterated).strip()
        return transliterated.title() if transliterated else ""

    @staticmethod
    def _weather_code_description(code: int) -> str:
        descriptions = {
            0: "ясне небо",
            1: "переважно ясно",
            2: "мінлива хмарність",
            3: "хмарно",
            45: "туман",
            48: "туман з памороззю",
            51: "легка мжичка",
            53: "помірна мжичка",
            55: "сильна мжичка",
            56: "легка крижана мжичка",
            57: "сильна крижана мжичка",
            61: "слабкий дощ",
            63: "помірний дощ",
            65: "сильний дощ",
            66: "легкий крижаний дощ",
            67: "сильний крижаний дощ",
            71: "слабкий сніг",
            73: "помірний сніг",
            75: "сильний сніг",
            77: "снігові зерна",
            80: "слабкі зливи",
            81: "помірні зливи",
            82: "сильні зливи",
            85: "слабкий снігопад",
            86: "сильний снігопад",
            95: "гроза",
            96: "гроза з градом",
            99: "сильна гроза з градом",
        }
        return descriptions.get(code, f"код погоди {code}")

    @staticmethod
    def _format_number(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number.is_integer():
            return str(int(number))
        return f"{number:.1f}"

    @staticmethod
    def _extract_sources(data: dict[str, Any]) -> list[dict[str, str]]:
        sources: list[dict[str, str]] = []

        def add(url: str, title: str) -> None:
            clean_url = str(url or "").strip()
            clean_title = str(title or "").strip()
            if not clean_url or any(item["url"] == clean_url for item in sources):
                return
            sources.append({"title": clean_title or clean_url, "url": clean_url})

        if url := str(data.get("AbstractURL") or "").strip():
            add(url, str(data.get("Heading") or data.get("AbstractSource") or "Abstract"))
        if url := str(data.get("AnswerURL") or "").strip():
            add(url, "Answer")

        related = data.get("RelatedTopics")
        if isinstance(related, list):
            for item in related:
                if not isinstance(item, dict):
                    continue
                if url := str(item.get("FirstURL") or "").strip():
                    add(url, str(item.get("Text") or item.get("Name") or "Related topic"))
                nested = item.get("Topics")
                if isinstance(nested, list):
                    for nested_item in nested:
                        if not isinstance(nested_item, dict):
                            continue
                        if url := str(nested_item.get("FirstURL") or "").strip():
                            add(url, str(nested_item.get("Text") or nested_item.get("Name") or "Related topic"))

        entries = data.get("entries")
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                if url := str(item.get("url") or item.get("link") or "").strip():
                    add(url, str(item.get("title") or "News item"))

        return sources[:5]

    @staticmethod
    def _format_sources(sources: list[dict[str, str]]) -> str:
        if not sources:
            return "- none"
        return "\n".join(f"- {item['title']}: {item['url']}" for item in sources)

    @staticmethod
    def _format_page_snippets(snippets: list[dict[str, Any]]) -> str:
        if not snippets:
            return "- none"
        lines: list[str] = []
        for item in snippets[:3]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            url = str(item.get("url") or "").strip()
            if title or snippet or url:
                lines.append(f"- {title or url}: {snippet or url}")
        return "\n".join(lines) if lines else "- none"

    @staticmethod
    def _format_raw_context(data: dict[str, Any]) -> str:
        pieces: list[str] = []
        for key in ("AbstractText", "Answer", "Definition"):
            value = str(data.get(key) or "").strip()
            if value:
                pieces.append(f"{key}: {html.unescape(value)}")
        snippets = data.get("page_snippets")
        if isinstance(snippets, list):
            for item in snippets[:3]:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("snippet") or "").strip()
                url = str(item.get("url") or "").strip()
                if text or url:
                    pieces.append(f"SNIPPET: {text} {url}".strip())
        entries = data.get("entries")
        if isinstance(entries, list):
            for item in entries[:3]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                published = str(item.get("published") or "").strip()
                url = str(item.get("url") or item.get("link") or "").strip()
                if title or url:
                    pieces.append(f"NEWS: {title} {published} {url}".strip())
        related = data.get("RelatedTopics")
        if isinstance(related, list):
            for item in related[:3]:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("Text") or "").strip()
                url = str(item.get("FirstURL") or "").strip()
                if text or url:
                    pieces.append(f"- {text} {url}".strip())
        return "\n".join(pieces) if pieces else "No useful raw snippets available."
