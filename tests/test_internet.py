from __future__ import annotations

import asyncio
from types import SimpleNamespace

from config import Settings
from integrations.telegram import TelegramService
from internet.search import InternetService


class StubInternetService(InternetService):
    async def search(self, query: str) -> dict[str, object]:
        return {
            "query": query,
            "summary": "Ada Lovelace was an early computer programmer.",
            "raw": {
                "AbstractText": "Ada Lovelace wrote notes on the Analytical Engine.",
                "AbstractURL": "https://example.com/ada",
                "RelatedTopics": [
                    {"Text": "Ada Lovelace biography", "FirstURL": "https://example.com/bio"}
                ],
            },
        }


class StubWeatherService(InternetService):
    async def _geocode_location(self, location: str) -> dict[str, object] | None:
        assert "вінниц" in location.lower()
        return {
            "name": "Vinnytsia",
            "admin1": "Vinnytsia Oblast",
            "country": "Ukraine",
            "latitude": 49.2331,
            "longitude": 28.4682,
        }

    async def _fetch_current_weather(self, latitude: float, longitude: float) -> dict[str, object]:
        assert latitude == 49.2331
        assert longitude == 28.4682
        return {
            "current": {
                "time": "2026-06-29T21:30",
                "temperature_2m": 24.3,
                "apparent_temperature": 25.1,
                "relative_humidity_2m": 42,
                "wind_speed_10m": 12.4,
                "precipitation": 0.0,
                "weather_code": 1,
            }
        }


class DummyEventBus:
    def __init__(self) -> None:
        self.history = []

    async def publish(self, *args, **kwargs) -> None:
        return None


class DummyGateway:
    def __init__(self) -> None:
        self.last_messages = None

    async def chat(self, messages, *, task_type: str, temperature: float = 0.2):
        self.last_messages = messages
        return SimpleNamespace(text="Ada Lovelace pioneered programming.")


def test_internet_service_synthesizes_answer() -> None:
    async def run() -> tuple[dict[str, object], DummyGateway]:
        service = StubInternetService()
        gateway = DummyGateway()
        result = await service.answer("who is Ada Lovelace", gateway=gateway, system_prompt="Be concise.")
        return result, gateway

    result, gateway = asyncio.run(run())
    assert result["answer"] == "Ada Lovelace pioneered programming."
    assert result["sources"][0]["url"] == "https://example.com/ada"
    assert gateway.last_messages is not None


def test_telegram_replies_with_answer_and_sources() -> None:
    async def run() -> list[str]:
        settings = Settings(
            raw={
                "telegram": {
                    "enabled": True,
                    "bot_token": "123:token",
                    "chat_id": "999",
                    "progress_report_interval_seconds": 300,
                }
            }
        )
        service = TelegramService(settings, DummyEventBus())
        sent_messages: list[str] = []

        async def fake_send_message(text: str) -> dict[str, object]:
            sent_messages.append(text)
            return {"ok": True}

        service.send_message = fake_send_message  # type: ignore[method-assign]

        async def command_handler(text: str) -> dict[str, object]:
            return {
                "response": "Ada Lovelace pioneered programming.",
                "result": {
                    "sources": [
                        {"title": "Ada Lovelace biography", "url": "https://example.com/bio"},
                    ]
                },
            }

        async def status_provider() -> dict[str, object]:
            return {"active": True, "music": {"mode": "idle"}}

        async def task_provider(task_id: int) -> dict[str, object] | None:
            return None

        await service._handle_update(
            {"message": {"chat": {"id": "999"}, "text": "who is ada lovelace"}},
            command_handler,
            status_provider,
            task_provider,
        )
        return sent_messages

    sent_messages = asyncio.run(run())
    assert sent_messages
    assert "Ada Lovelace pioneered programming." in sent_messages[0]
    assert "Джерела:" in sent_messages[0]
    assert "https://example.com/bio" in sent_messages[0]


def test_telegram_weather_command_routes_to_weather_query() -> None:
    async def run() -> tuple[list[str], list[str]]:
        settings = Settings(
            raw={
                "telegram": {
                    "enabled": True,
                    "bot_token": "123:token",
                    "chat_id": "999",
                    "progress_report_interval_seconds": 300,
                }
            }
        )
        service = TelegramService(settings, DummyEventBus())
        sent_messages: list[str] = []
        received_queries: list[str] = []

        async def fake_send_message(text: str) -> dict[str, object]:
            sent_messages.append(text)
            return {"ok": True}

        service.send_message = fake_send_message  # type: ignore[method-assign]

        async def command_handler(text: str) -> dict[str, object]:
            received_queries.append(text)
            return {
                "response": "Зараз у Вінниці: температура 24.3°C",
                "result": {
                    "sources": [
                        {"title": "Open-Meteo Forecast", "url": "https://open-meteo.com/en/docs"},
                    ]
                },
            }

        async def status_provider() -> dict[str, object]:
            return {"active": True, "music": {"mode": "idle"}}

        async def task_provider(task_id: int) -> dict[str, object] | None:
            return None

        await service._handle_update(
            {"message": {"chat": {"id": "999"}, "text": "/weather Вінниця"}},
            command_handler,
            status_provider,
            task_provider,
        )
        return sent_messages, received_queries

    sent_messages, received_queries = asyncio.run(run())
    assert received_queries == ["яка щас погода в Вінниця"]
    assert sent_messages
    assert "температура 24.3°C" in sent_messages[0]
    assert "Open-Meteo Forecast" in sent_messages[0]


def test_weather_query_uses_weather_pipeline() -> None:
    async def run() -> dict[str, object]:
        service = StubWeatherService()
        return await service.answer("яка щас погода в вінниці")

    result = asyncio.run(run())
    assert "Vinnytsia" in str(result["answer"])
    assert "температура 24.3°C" in str(result["answer"])
    assert result["sources"][0]["title"] == "Open-Meteo Forecast"
