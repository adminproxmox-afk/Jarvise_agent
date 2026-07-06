from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccessMode(str, Enum):
    SAFE = "safe"
    DEVELOPER = "developer"
    FULL_CONTROL = "full_control"


@dataclass(slots=True)
class SecurityDecision:
    allowed: bool
    requires_confirmation: bool = False
    reason: str = "allowed"


class SecurityPolicy:
    destructive_tokens = (
        "rm ",
        "remove-item",
        "del ",
        "delete",
        "rmdir",
        "format",
        "shutdown",
        "restart-computer",
        "git reset",
        "drop database",
    )

    def __init__(self, mode: AccessMode = AccessMode.DEVELOPER) -> None:
        self.mode = mode

    def decide(self, tool: str, action: str, command: str = "") -> SecurityDecision:
        normalized = f"{tool} {action} {command}".lower()
        destructive = any(token in normalized for token in self.destructive_tokens)

        if self.mode == AccessMode.SAFE and action not in {"list", "read", "status", "describe", "test"}:
            return SecurityDecision(False, reason="safe_mode_read_only")

        if destructive and self.mode != AccessMode.FULL_CONTROL:
            return SecurityDecision(False, requires_confirmation=True, reason="dangerous_action_requires_full_control")

        if destructive and self.mode == AccessMode.FULL_CONTROL:
            return SecurityDecision(True, requires_confirmation=True, reason="dangerous_action_requires_confirmation")

        return SecurityDecision(True)
