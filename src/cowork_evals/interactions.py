"""The answers a case gives to CoWork's approval boxes. docs/eval_format.md.

An approval box before a tool runs writes a `permission_request` record to audit.jsonl, and
the answer a `permission_response`. docs/cowork_desktop.md. A case lists its answers in
`interactions.yaml`, in order: each box takes the next answer when it matches.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import CoWorkError

INTERACTIONS_FILE = "interactions.yaml"


class Approval(BaseModel):
    """Allow once or deny. `match` is a regular expression over the tool name and its input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: Literal["allow", "deny"]
    match: str | None = None

    @field_validator("match")
    @classmethod
    def _compiles(cls, value: str | None) -> str | None:
        if value is not None:
            re.compile(value)
        return value

    def matches(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        if self.match is None:
            return True
        searched = f"{tool_name} {json.dumps(tool_input, ensure_ascii=False, sort_keys=True)}"
        return re.search(self.match, searched) is not None


class InteractionsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    approvals: list[Approval] = Field(min_length=1)


def read(path: Path | str) -> list[Approval]:
    """The approvals in one `interactions.yaml`. A file outside the format is code 2."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return InteractionsFile.model_validate(data).approvals
    except (OSError, yaml.YAMLError, ValidationError, re.error) as error:
        raise CoWorkError(2, f"{path}: {error}") from error
