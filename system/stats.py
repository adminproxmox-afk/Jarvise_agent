from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any

import psutil


class SystemStatsService:
    def __init__(self) -> None:
        self._last_net = psutil.net_io_counters()
        self._last_net_at = time.monotonic()
        self._last_gpu_at = 0.0
        self._last_gpu: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        battery = psutil.sensors_battery()
        disk = psutil.disk_usage("/")
        network = self._network_snapshot()
        return {
            "cpu": round(psutil.cpu_percent(interval=None), 1),
            "memory": round(psutil.virtual_memory().percent, 1),
            "disk": round(disk.percent, 1),
            "network": network,
            "temperature": self._temperature_snapshot(),
            "gpu": self._gpu_snapshot(),
            "top_processes": self._top_processes(),
            "battery": None
            if battery is None
            else {
                "percent": round(battery.percent, 1),
                "plugged": battery.power_plugged,
            },
            "processes": len(psutil.pids()),
        }

    def _network_snapshot(self) -> dict[str, float]:
        current = psutil.net_io_counters()
        now = time.monotonic()
        elapsed = max(now - self._last_net_at, 0.001)
        sent = max(current.bytes_sent - self._last_net.bytes_sent, 0) / elapsed
        recv = max(current.bytes_recv - self._last_net.bytes_recv, 0) / elapsed
        self._last_net = current
        self._last_net_at = now
        return {"up_kbps": round(sent / 1024, 1), "down_kbps": round(recv / 1024, 1)}

    @staticmethod
    def _temperature_snapshot() -> dict[str, float] | None:
        try:
            temps = psutil.sensors_temperatures(fahrenheit=False)
        except (AttributeError, OSError):
            return None
        readings: dict[str, float] = {}
        for name, entries in temps.items():
            valid = [entry.current for entry in entries if entry.current is not None]
            if valid:
                readings[name] = round(max(valid), 1)
        return readings or None

    def _gpu_snapshot(self) -> dict[str, Any] | None:
        if time.monotonic() - self._last_gpu_at < 10:
            return self._last_gpu
        self._last_gpu_at = time.monotonic()
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            self._last_gpu = None
            return None
        try:
            completed = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=1.2,
                check=False,
            )
            line = completed.stdout.strip().splitlines()[0]
            name, util, mem_used, mem_total, temp = [part.strip() for part in line.split(",")]
            self._last_gpu = {
                "name": name,
                "utilization": float(util),
                "memory_used_mb": float(mem_used),
                "memory_total_mb": float(mem_total),
                "temperature": float(temp),
            }
            return self._last_gpu
        except Exception:
            self._last_gpu = None
            return None

    @staticmethod
    def _top_processes() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
            try:
                rows.append(
                    {
                        "name": proc.info.get("name") or "unknown",
                        "cpu": round(float(proc.info.get("cpu_percent") or 0), 1),
                        "memory": round(float(proc.info.get("memory_percent") or 0), 1),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        rows.sort(key=lambda item: (item["cpu"], item["memory"]), reverse=True)
        return rows[:5]
