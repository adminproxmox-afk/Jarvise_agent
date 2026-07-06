from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        elif isinstance(value, list) and _is_id_list(value) and _is_id_list(merged.get(key)):
            merged[key] = _merge_id_lists(merged[key], value)
        else:
            merged[key] = value
    return merged


def _is_id_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) and "id" in item for item in value)


def _merge_id_lists(base: list[dict[str, Any]], override: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged_by_id = {str(item["id"]): dict(item) for item in base}
    order = [str(item["id"]) for item in base]
    for item in override:
        item_id = str(item["id"])
        if item_id in merged_by_id:
            merged_by_id[item_id] = _deep_merge(merged_by_id[item_id], item)
        else:
            order.append(item_id)
            merged_by_id[item_id] = dict(item)
    return [merged_by_id[item_id] for item_id in order]


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


@dataclass(slots=True)
class Settings:
    raw: dict[str, Any]
    root_dir: Path = field(default_factory=lambda: Path.cwd())

    @property
    def assistant_name(self) -> str:
        return self.raw.get("assistant", {}).get("name", "JARVIS")

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    def get(self, dotted_path: str, default: Any = None) -> Any:
        current: Any = self.raw
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def path(self, dotted_path: str, default: str) -> Path:
        value = self.get(dotted_path, default)
        path = Path(str(value))
        return path if path.is_absolute() else self.root_dir / path


def load_settings(config_path: str | os.PathLike[str] = "config/default.yaml") -> Settings:
    root_dir = Path.cwd()
    default_path = root_dir / "config" / "default.yaml"
    selected_path = Path(config_path)
    if not selected_path.is_absolute():
        selected_path = root_dir / selected_path

    with default_path.open("r", encoding="utf-8") as handle:
        base = yaml.safe_load(handle) or {}

    if selected_path.resolve() != default_path.resolve() and selected_path.exists():
        with selected_path.open("r", encoding="utf-8") as handle:
            override = yaml.safe_load(handle) or {}
        base = _deep_merge(base, override)

    return Settings(raw=_expand(base), root_dir=root_dir)
