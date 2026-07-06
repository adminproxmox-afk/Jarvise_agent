from __future__ import annotations

from core.decision_engine import DecisionEngine
from character.engine import CharacterEngine


def test_decision_engine_classifies_requests() -> None:
    engine = DecisionEngine()
    decision = engine.decide("создай проект на python")
    assert decision.needs_planning is True
    assert decision.needs_skill is True


def test_decision_engine_routes_search_requests_to_internet() -> None:
    engine = DecisionEngine()
    decision = engine.decide("пошукай хто такий Ada Lovelace")
    assert decision.needs_internet is True
    assert decision.needs_skill is True


def test_character_engine_builds_prompt() -> None:
    engine = CharacterEngine()
    prompt = engine.build_system_prompt()
    assert "Jarvise" in prompt
    assert "Rules:" in prompt
