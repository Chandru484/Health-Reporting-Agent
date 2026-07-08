"""Deterministic RAG scoring logic for project health assessment."""

from __future__ import annotations

from dataclasses import dataclass, field

from .utils import safe_text


@dataclass(slots=True)
class ProjectMetrics:
    """Normalized project-level metrics used by the scoring engine."""

    project_name: str = "Unknown Project"
    project_manager: str = "Unknown"
    schedule_variance_days: float | None = None
    schedule_health: str = "Unknown"
    completion_fraction: float | None = None
    milestone_completion_fraction: float | None = None
    open_blockers: int = 0
    total_blockers: int = 0
    risks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    sentiment_score: float = 0.5
    budget_burn_fraction: float | None = None
    budget_variance_fraction: float | None = None
    status_values: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    milestones_total: int = 0
    milestones_done: int = 0
    tasks_total: int = 0
    tasks_done: int = 0
    delayed_items: list[str] = field(default_factory=list)
    latest_end_date: str = ""
    latest_start_date: str = ""


@dataclass(slots=True)
class ProjectAssessment:
    """Result of the RAG engine evaluation."""

    project_name: str
    overall_status: str
    overall_score: int
    reason_codes: list[str]
    recommendations: list[str]
    positive_indicators: list[str]
    risk_indicators: list[str]
    component_scores: dict[str, int]
    explanation: str


class RAGEngine:
    """Weighted RAG scoring engine with human-readable reasoning."""

    def __init__(self) -> None:
        self.weights = {
            "schedule": 30,
            "progress": 20,
            "milestones": 20,
            "risks": 15,
            "sentiment": 15,
        }

    def assess(self, metrics: ProjectMetrics) -> ProjectAssessment:
        """Return a RAG assessment for the supplied metrics."""

        schedule_score, schedule_notes = self._schedule_score(metrics)
        progress_score, progress_notes = self._progress_score(metrics)
        milestone_score, milestone_notes = self._milestone_score(metrics)
        risk_score, risk_notes = self._risk_score(metrics)
        sentiment_score, sentiment_notes = self._sentiment_score(metrics)

        weighted_total = (
            schedule_score * self.weights["schedule"]
            + progress_score * self.weights["progress"]
            + milestone_score * self.weights["milestones"]
            + risk_score * self.weights["risks"]
            + sentiment_score * self.weights["sentiment"]
        )
        overall_score = int(round(weighted_total / 20.0))
        overall_score = max(0, min(10, overall_score))
        if overall_score <= 2:
            status = "Green"
        elif overall_score <= 5:
            status = "Amber"
        else:
            status = "Red"

        reason_codes = [
            *schedule_notes,
            *progress_notes,
            *milestone_notes,
            *risk_notes,
            *sentiment_notes,
        ]
        positive_indicators = self._positive_indicators(metrics)
        risk_indicators = self._risk_indicators(metrics, reason_codes)
        recommendations = self._recommendations(metrics, overall_score, status)

        explanation = self._compose_explanation(status, overall_score, reason_codes, positive_indicators, risk_indicators, recommendations)

        return ProjectAssessment(
            project_name=metrics.project_name,
            overall_status=status,
            overall_score=overall_score,
            reason_codes=reason_codes,
            recommendations=recommendations,
            positive_indicators=positive_indicators,
            risk_indicators=risk_indicators,
            component_scores={
                "schedule": schedule_score,
                "progress": progress_score,
                "milestones": milestone_score,
                "risks": risk_score,
                "sentiment": sentiment_score,
            },
            explanation=explanation,
        )

    def _schedule_score(self, metrics: ProjectMetrics) -> tuple[int, list[str]]:
        notes: list[str] = []
        variance = metrics.schedule_variance_days
        health = safe_text(metrics.schedule_health).lower()
        if variance is not None:
            if variance <= -7:
                notes.append(f"Schedule is slipping by {abs(variance):.0f} days")
                return 2, notes
            if variance < 0:
                notes.append(f"Schedule is slightly behind by {abs(variance):.0f} days")
                return 1, notes
            if variance >= 7:
                notes.append(f"Schedule has at least {variance:.0f} days of buffer")
                return 0, notes
        if health in {"red", "yellow", "amber"}:
            notes.append(f"Schedule health marked as {metrics.schedule_health}")
        if health == "red":
            return 2, notes
        if health in {"yellow", "amber"}:
            return 1, notes
        if health == "green":
            return 0, notes
        notes.append("Schedule data is incomplete")
        return 1, notes

    def _progress_score(self, metrics: ProjectMetrics) -> tuple[int, list[str]]:
        notes: list[str] = []
        completion = metrics.completion_fraction
        if completion is None:
            notes.append("Completion percentage is unavailable")
            return 1, notes
        if completion >= 0.85:
            notes.append(f"Completion is strong at {completion:.0%}")
            return 0, notes
        if completion >= 0.60:
            notes.append(f"Completion is tracking at {completion:.0%}")
            return 1, notes
        notes.append(f"Completion is low at {completion:.0%}")
        return 2, notes

    def _milestone_score(self, metrics: ProjectMetrics) -> tuple[int, list[str]]:
        notes: list[str] = []
        total = metrics.milestones_total
        done = metrics.milestones_done
        if total <= 0:
            notes.append("Milestone data is missing")
            return 1, notes
        ratio = done / total if total else 0.0
        if ratio >= 0.85:
            notes.append(f"Milestones are mostly complete ({done}/{total})")
            return 0, notes
        if ratio >= 0.60:
            notes.append(f"Milestones are progressing ({done}/{total})")
            return 1, notes
        notes.append(f"Milestones are behind ({done}/{total})")
        return 2, notes

    def _risk_score(self, metrics: ProjectMetrics) -> tuple[int, list[str]]:
        notes: list[str] = []
        open_blockers = metrics.open_blockers
        risks = len(metrics.risks)
        dependencies = len(metrics.dependencies)
        score = 0
        if open_blockers > 0:
            score += 1
            notes.append(f"{open_blockers} open blocker(s) remain")
        if risks >= 3:
            score += 1
            notes.append(f"{risks} risk item(s) are logged")
        if dependencies >= 3:
            score += 1
            notes.append(f"{dependencies} dependency item(s) need attention")
        return min(2, score), notes or ["Risk indicators are limited"]

    def _sentiment_score(self, metrics: ProjectMetrics) -> tuple[int, list[str]]:
        notes: list[str] = []
        sentiment = metrics.sentiment_score
        comments = [safe_text(comment).lower() for comment in metrics.comments if safe_text(comment)]
        if comments:
            positive = sum(any(token in comment for token in ("good", "great", "on track", "completed", "resolved", "aligned")) for comment in comments)
            negative = sum(any(token in comment for token in ("delay", "blocked", "risk", "issue", "late", "impacted", "concern")) for comment in comments)
            if positive > negative:
                sentiment = min(1.0, sentiment + 0.2)
            elif negative > positive:
                sentiment = max(0.0, sentiment - 0.2)
        if sentiment >= 0.7:
            notes.append("Stakeholder comments are constructive")
            return 0, notes
        if sentiment >= 0.45:
            notes.append("Stakeholder sentiment is neutral")
            return 1, notes
        notes.append("Stakeholder comments indicate concern")
        return 2, notes

    def _positive_indicators(self, metrics: ProjectMetrics) -> list[str]:
        indicators: list[str] = []
        if metrics.completion_fraction is not None and metrics.completion_fraction >= 0.6:
            indicators.append(f"{metrics.completion_fraction:.0%} of the work is complete")
        if metrics.schedule_health.lower() == "green":
            indicators.append("Schedule health is green")
        if metrics.milestones_total and metrics.milestones_done >= metrics.milestones_total * 0.6:
            indicators.append("Milestones are tracking")
        if not metrics.open_blockers:
            indicators.append("No open blockers were identified")
        return indicators or ["No strong positive indicators detected"]

    def _risk_indicators(self, metrics: ProjectMetrics, reason_codes: list[str]) -> list[str]:
        indicators: list[str] = []
        if metrics.schedule_variance_days is not None and metrics.schedule_variance_days < 0:
            indicators.append(f"Schedule variance is {metrics.schedule_variance_days:.0f} days behind")
        if metrics.open_blockers:
            indicators.append(f"{metrics.open_blockers} blocker(s) are still open")
        if metrics.budget_burn_fraction is not None and metrics.budget_burn_fraction > 0.85:
            indicators.append(f"Budget burn is high at {metrics.budget_burn_fraction:.0%}")
        if metrics.risks:
            indicators.append(f"Risks logged: {', '.join(metrics.risks[:3])}")
        if metrics.dependencies:
            indicators.append(f"Dependencies: {', '.join(metrics.dependencies[:3])}")
        indicators.extend(note for note in reason_codes if "behind" in note.lower() or "slipping" in note.lower())
        return indicators[:6] or ["No material risks were detected"]

    def _recommendations(self, metrics: ProjectMetrics, score: int, status: str) -> list[str]:
        recommendations: list[str] = []
        if status == "Red":
            recommendations.append("Escalate the delivery risk and agree on a recovery plan within 48 hours")
        elif status == "Amber":
            recommendations.append("Tighten weekly tracking and remove the top blocker")
        else:
            recommendations.append("Maintain the current cadence and continue proactive monitoring")
        if metrics.open_blockers:
            recommendations.append("Assign clear owners and due dates for every blocker")
        if metrics.completion_fraction is not None and metrics.completion_fraction < 0.5:
            recommendations.append("Reconfirm scope, dependencies, and near-term milestones")
        if metrics.budget_burn_fraction is not None and metrics.budget_burn_fraction > 0.9:
            recommendations.append("Review budget assumptions before the next steering update")
        return recommendations[:4]

    def _compose_explanation(
        self,
        status: str,
        score: int,
        reason_codes: list[str],
        positive_indicators: list[str],
        risk_indicators: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [f"Overall status: {status} with a risk score of {score}/10."]
        if reason_codes:
            lines.append("Key reasons: " + "; ".join(reason_codes[:5]) + ".")
        if positive_indicators:
            lines.append("Positive signals: " + "; ".join(positive_indicators[:3]) + ".")
        if risk_indicators:
            lines.append("Risk signals: " + " | ".join(risk_indicators[:3]) + ".")
        if recommendations:
            lines.append("Recommended actions: " + "; ".join(recommendations[:3]) + ".")
        return " ".join(lines)
