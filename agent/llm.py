"""Offline LLM wrapper using Ollama with graceful fallback."""

from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Any

try:
    import ollama
except Exception:  # pragma: no cover - dependency/runtime fallback
    ollama = None

from .rag_engine import ProjectAssessment, ProjectMetrics

LOGGER = logging.getLogger(__name__)


class PMOAgent:
    """Generate executive-language commentary from deterministic assessment data."""

    def __init__(self, model: str = "llama2", host: str | None = None) -> None:
        self.model = model
        self.host = host

    def generate_narrative(self, metrics: ProjectMetrics, assessment: ProjectAssessment) -> dict[str, Any]:
        """Return structured narrative content, using Ollama when available."""

        prompt = self._build_prompt(metrics, assessment)
        response_text = self._call_ollama(prompt)
        if response_text:
            return self._parse_sections(response_text, assessment)
        return self._fallback_response(assessment)

    def _call_ollama(self, prompt: str) -> str:
        if ollama is None:
            return ""
        if not self._model_available():
            LOGGER.warning("Ollama model '%s' is not available locally; using fallback narrative.", self.model)
            return ""
        try:
            kwargs: dict[str, Any] = {"model": self.model, "prompt": prompt}
            if self.host:
                kwargs["host"] = self.host
            response = ollama.generate(**kwargs)
            return str(response.get("response", "")).strip()
        except Exception as exc:  # pragma: no cover - runtime fallback
            LOGGER.warning("Ollama generation failed: %s", exc)
            return ""

    def _model_available(self) -> bool:
        try:
            listing = ollama.list()
        except Exception:
            return False

        if isinstance(listing, dict):
            models = listing.get("models", [])
        else:
            models = getattr(listing, "models", [])
        for model in models:
            name = ""
            if isinstance(model, dict):
                name = str(model.get("name", ""))
            else:
                name = str(getattr(model, "model", "") or getattr(model, "name", ""))
            if name.split(":", 1)[0] == self.model:
                return True
        return False

    def _build_prompt(self, metrics: ProjectMetrics, assessment: ProjectAssessment) -> str:
        metrics_blob = asdict(metrics)
        assessment_blob = asdict(assessment)
        return (
            "You are a Senior PMO Director writing for executive leadership. "
            "Use crisp, plain-English, board-ready language. "
            "Return exactly five sections with labels: Project Health, Why, Positive observations, Major risks, Recommendations, Next actions. "
            f"Project metrics: {metrics_blob}. "
            f"Deterministic assessment: {assessment_blob}."
        )

    def _parse_sections(self, response_text: str, assessment: ProjectAssessment) -> dict[str, Any]:
        return {
            "project_health": assessment.overall_status,
            "why": assessment.explanation,
            "positive_observations": assessment.positive_indicators,
            "major_risks": assessment.risk_indicators,
            "recommendations": assessment.recommendations,
            "next_actions": assessment.recommendations,
            "raw_response": response_text,
        }

    def _fallback_response(self, assessment: ProjectAssessment) -> dict[str, Any]:
        return {
            "project_health": assessment.overall_status,
            "why": assessment.explanation,
            "positive_observations": assessment.positive_indicators,
            "major_risks": assessment.risk_indicators,
            "recommendations": assessment.recommendations,
            "next_actions": assessment.recommendations,
            "raw_response": "",
        }
