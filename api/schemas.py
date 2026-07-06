from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ActivateRequest(BaseModel):
    trigger: str = "manual"


class TaskCreateRequest(BaseModel):
    request: str = Field(min_length=3, max_length=4000)
    title: str | None = Field(default=None, max_length=120)
    agent: str | None = Field(default=None, max_length=40)


class ModelSelectRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=160)


class MemoryWriteRequest(BaseModel):
    section: str = Field(min_length=1, max_length=60)
    key: str = Field(min_length=1, max_length=120)
    value: Any
    tags: list[str] = Field(default_factory=list)


class ToolExecuteRequest(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class ApiResponse(BaseModel):
    ok: bool = True
    data: dict[str, Any] | list[Any] | str | None = None
