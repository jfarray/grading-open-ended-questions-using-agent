"""Typed application configuration loaded from environment variables."""

from dataclasses import dataclass
import os
from typing import Literal

DEFAULT_CHECKPOINT_DB_PATH = "agentCheckpoints.sqlite"
DEFAULT_METRICS_DB_PATH = "metrics.sqlite"
ExamGraderMode = Literal["test", "llm"]


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(
        f"Invalid boolean value for {name}: {value!r}. "
        "Use true/false, 1/0, yes/no, or on/off."
    )


def _get_exam_grader_mode() -> ExamGraderMode:
    mode = os.environ.get("EXAM_GRADER_MODE", "llm").strip().lower()
    if mode not in {"test", "llm"}:
        raise ValueError("EXAM_GRADER_MODE must be either 'test' or 'llm'.")
    return mode  # type: ignore[return-value]


@dataclass(frozen=True)
class AppSettings:
    cohere_api_key: str
    langgraph_debug: bool = False
    exam_grader_mode: ExamGraderMode = "llm"
    checkpoint_db_path: str = DEFAULT_CHECKPOINT_DB_PATH
    metrics_db_path: str = DEFAULT_METRICS_DB_PATH

    @classmethod
    def from_environment(cls) -> "AppSettings":
        cohere_api_key = os.environ.get("COHERE_API_KEY", "").strip()
        if not cohere_api_key:
            raise RuntimeError(
                "Define la variable de entorno COHERE_API_KEY antes de iniciar el agente."
            )

        return cls(
            cohere_api_key=cohere_api_key,
            langgraph_debug=_get_bool("LANGGRAPH_DEBUG"),
            exam_grader_mode=_get_exam_grader_mode(),
            checkpoint_db_path=os.environ.get(
                "AGENT_CHECKPOINT_DB", DEFAULT_CHECKPOINT_DB_PATH
            ),
            metrics_db_path=os.environ.get("AGENT_METRICS_DB", DEFAULT_METRICS_DB_PATH),
        )


settings = AppSettings.from_environment()