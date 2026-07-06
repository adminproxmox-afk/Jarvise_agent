from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class JarvisPlugin(Protocol):
    name: str

    async def setup(self) -> None:
        ...


@dataclass(slots=True)
class LoadedPlugin:
    name: str
    path: Path
    instance: JarvisPlugin


class PluginManager:
    def __init__(self, plugin_dir: Path) -> None:
        self.plugin_dir = plugin_dir
        self.plugins: list[LoadedPlugin] = []

    def discover(self) -> list[Path]:
        if not self.plugin_dir.exists():
            return []
        return sorted(path for path in self.plugin_dir.glob("*/plugin.py") if path.is_file())

    def load_all(self) -> list[LoadedPlugin]:
        self.plugins.clear()
        for path in self.discover():
            module_name = f"jarvis_plugin_{path.parent.name}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            factory = getattr(module, "create_plugin", None)
            if callable(factory):
                instance = factory()
                self.plugins.append(LoadedPlugin(name=instance.name, path=path, instance=instance))
        return self.plugins
