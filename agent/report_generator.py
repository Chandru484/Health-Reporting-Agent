"""Generate weekly TXT/Markdown reports and monthly synthesis text."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .llm import PMOAgent
from .rag_engine import ProjectAssessment, ProjectMetrics
from .utils import ensure_directory, write_text_file


class ReportGenerator:
    """Create executive-ready reports from project assessments."""

    def __init__(self, output_dir: Path, llm: PMOAgent) -> None:
        self.output_dir = ensure_directory(output_dir)
        self.llm = llm

    def generate_weekly_report(
        self,
        project_id: str,
        metrics: ProjectMetrics,
        assessment: ProjectAssessment,
    ) -> dict[str, Path]:
        """Save TXT and Markdown weekly reports for a project."""

        narrative = self.llm.generate_narrative(metrics, assessment)
        text_content = self._build_text_report(metrics, assessment, narrative)
        markdown_content = self._build_markdown_report(metrics, assessment, narrative)

        text_path = self.output_dir / f"weekly_report_{project_id}.txt"
        markdown_path = self.output_dir / f"weekly_report_{project_id}.md"
        write_text_file(text_path, text_content)
        write_text_file(markdown_path, markdown_content)
        return {"txt": text_path, "md": markdown_path}

    def generate_monthly_summary(self, weekly_reports: list[dict[str, Any]]) -> str:
        """Build portfolio-level synthesis across weekly report artifacts."""

        report_paths = [report["paths"]["txt"] for report in weekly_reports]
        return self.generate_monthly_summary_from_files(report_paths)

    def generate_monthly_summary_from_files(self, weekly_report_paths: list[Path]) -> str:
        """Read saved weekly reports and synthesize cross-project trends."""

        parsed_reports = [self._parse_weekly_report_file(path) for path in weekly_report_paths if path.exists()]

        total = len(parsed_reports)
        greens = sum(1 for report in parsed_reports if report["overall_status"] == "Green")
        ambers = sum(1 for report in parsed_reports if report["overall_status"] == "Amber")
        reds = sum(1 for report in parsed_reports if report["overall_status"] == "Red")
        average_score = self._average_score(parsed_reports)
        average_completion = self._average_completion(parsed_reports)
        common_risks = self._top_items(parsed_reports, "risk_indicators")
        common_recommendations = self._top_items(parsed_reports, "recommendations")
        delayed_items = self._top_items(parsed_reports, "delayed_items")
        red_projects = [report["project_name"] for report in parsed_reports if report["overall_status"] == "Red"]
        amber_projects = [report["project_name"] for report in parsed_reports if report["overall_status"] == "Amber"]
        trend_lines = [
            f"- {reds} project(s) are Red, {ambers} are Amber, and {greens} are Green",
            "- Schedule slippage is the dominant cross-project risk",
        ]
        risk_bullets = [f"- {item}" for item in common_risks[:5]] or ["- None identified"]
        delayed_bullets = [f"- {item}" for item in delayed_items[:5]] or ["- No delayed milestones were explicitly reported"]
        red_bullets = [f"- {name}" for name in red_projects] or ["- None identified"]
        amber_bullets = [f"- {name}" for name in amber_projects] or ["- None identified"]
        recommendation_bullets = [f"- {item}" for item in common_recommendations[:5]] or ["- Continue proactive monitoring"]

        lines = [
            "MONTHLY PORTFOLIO SYNTHESIS",
            "",
            f"Projects reviewed: {total}",
            f"Portfolio health: {greens} Green, {ambers} Amber, {reds} Red",
            f"Average score: {average_score:.1f}/10" if average_score is not None else "Average score: Unavailable",
            f"Average completion: {average_completion:.0%}" if average_completion is not None else "Average completion: Unavailable",
            "",
            "Trend snapshot:",
            *trend_lines,
            "",
            "Common risks:",
            *risk_bullets,
            "",
            "Most delayed milestones:",
            *delayed_bullets,
            "",
            "Red projects:",
            *red_bullets,
            "",
            "Amber projects:",
            *amber_bullets,
            "",
            "Recommendations:",
            *recommendation_bullets,
            "",
            "Next Month Outlook:",
            "- Stabilize schedule-critical workstreams and remove blockers before the next steering review",
        ]
        return "\n".join(lines)

    def _build_text_report(
        self,
        metrics: ProjectMetrics,
        assessment: ProjectAssessment,
        narrative: dict[str, Any],
    ) -> str:
        sections = [
            "===================================",
            "PROJECT HEALTH REPORT",
            "===================================",
            f"Project Name: {metrics.project_name}",
            f"Overall Status: {assessment.overall_status}",
            f"Overall Score: {assessment.overall_score}/10",
            "",
            "Metrics Snapshot:",
            f"Project Manager: {metrics.project_manager}",
            f"Completion: {metrics.completion_fraction:.0%}" if metrics.completion_fraction is not None else "Completion: Unavailable",
            f"Milestones: {metrics.milestones_done}/{metrics.milestones_total}" if metrics.milestones_total else "Milestones: Unavailable",
            f"Schedule Health: {metrics.schedule_health}",
            f"Open Blockers: {metrics.open_blockers}",
            f"Delayed Items: {', '.join(metrics.delayed_items) if metrics.delayed_items else 'None reported'}",
            "",
            "Reasoning:",
            assessment.explanation,
            "",
            "Positive Indicators:",
            *[f"- {item}" for item in narrative["positive_observations"]],
            "",
            "Risk Indicators:",
            *[f"- {item}" for item in narrative["major_risks"]],
            "",
            "Most Delayed Items:",
            *([f"- {item}" for item in metrics.delayed_items] or ["- None reported"]),
            "",
            "Recommendations:",
            *[f"- {item}" for item in narrative["recommendations"]],
            "",
            "Next Week Actions:",
            *[f"- {item}" for item in narrative["next_actions"]],
            "",
            "Assessment Data:",
            str(asdict(assessment)),
        ]
        return "\n".join(sections)

    def _build_markdown_report(
        self,
        metrics: ProjectMetrics,
        assessment: ProjectAssessment,
        narrative: dict[str, Any],
    ) -> str:
        lines = [
            "# Project Health Report",
            "",
            f"**Project Name:** {metrics.project_name}",
            f"**Overall Status:** {assessment.overall_status}",
            f"**Overall Score:** {assessment.overall_score}/10",
            "",
            "## Metrics Snapshot",
            f"**Project Manager:** {metrics.project_manager}",
            f"**Completion:** {metrics.completion_fraction:.0%}" if metrics.completion_fraction is not None else "**Completion:** Unavailable",
            f"**Milestones:** {metrics.milestones_done}/{metrics.milestones_total}" if metrics.milestones_total else "**Milestones:** Unavailable",
            f"**Schedule Health:** {metrics.schedule_health}",
            f"**Open Blockers:** {metrics.open_blockers}",
            f"**Delayed Items:** {', '.join(metrics.delayed_items) if metrics.delayed_items else 'None reported'}",
            "",
            "## Reasoning",
            assessment.explanation,
            "",
            "## Positive Indicators",
            *[f"- {item}" for item in narrative["positive_observations"]],
            "",
            "## Risk Indicators",
            *[f"- {item}" for item in narrative["major_risks"]],
            "",
            "## Most Delayed Items",
            *([f"- {item}" for item in metrics.delayed_items] or ["- None reported"]),
            "",
            "## Recommendations",
            *[f"- {item}" for item in narrative["recommendations"]],
            "",
            "## Next Week Actions",
            *[f"- {item}" for item in narrative["next_actions"]],
        ]
        return "\n".join(lines)

    def _top_items(self, weekly_reports: list[dict[str, Any]], key: str) -> list[str]:
        counts: dict[str, int] = {}
        for report in weekly_reports:
            if isinstance(report, dict) and key in report:
                items = report.get(key, [])
            elif isinstance(report, dict) and "assessment" in report:
                items = getattr(report["assessment"], key, [])
            else:
                items = []
            for item in items:
                counts[item] = counts.get(item, 0) + 1
        return [item for item, _count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]

    def _average_completion(self, weekly_reports: list[dict[str, Any]]) -> float | None:
        completions = [report["completion_fraction"] for report in weekly_reports if report.get("completion_fraction") is not None]
        if not completions:
            return None
        return sum(completions) / len(completions)

    def _average_score(self, weekly_reports: list[dict[str, Any]]) -> float | None:
        scores = [report["overall_score"] for report in weekly_reports if report.get("overall_score") is not None]
        if not scores:
            return None
        return sum(scores) / len(scores)

    def _parse_weekly_report_file(self, path: Path) -> dict[str, Any]:
        report: dict[str, Any] = {
            "project_name": path.stem,
            "overall_status": "Unknown",
            "overall_score": None,
            "completion_fraction": None,
            "risk_indicators": [],
            "recommendations": [],
            "delayed_items": [],
        }
        section = ""
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if line.startswith("Project Name:"):
                report["project_name"] = line.split(":", 1)[1].strip() or report["project_name"]
            elif line.startswith("Overall Status:"):
                report["overall_status"] = line.split(":", 1)[1].strip() or report["overall_status"]
            elif line.startswith("Overall Score:"):
                score_text = line.split(":", 1)[1].strip().split("/", 1)[0]
                try:
                    report["overall_score"] = int(score_text)
                except ValueError:
                    pass
            elif lower == "metrics snapshot:":
                section = "metrics"
            elif lower == "reasoning:":
                section = "reasoning"
            elif lower == "positive indicators:":
                section = "positive"
            elif lower == "risk indicators:":
                section = "risk"
            elif lower == "most delayed items:":
                section = "delayed"
            elif lower == "recommendations:":
                section = "recommendations"
            elif lower == "next week actions:":
                section = "next_actions"
            elif line.startswith("-"):
                value = line.lstrip("- ").strip()
                if section == "risk":
                    report["risk_indicators"].append(value)
                elif section == "recommendations":
                    report["recommendations"].append(value)
                elif section == "delayed":
                    report["delayed_items"].append(value)
            elif section == "metrics" and line.startswith("Completion:"):
                completion_text = line.split(":", 1)[1].strip().rstrip("%")
                try:
                    report["completion_fraction"] = float(completion_text) / 100.0
                except ValueError:
                    report["completion_fraction"] = None
            elif section == "metrics" and line.startswith("Delayed Items:"):
                delayed_text = line.split(":", 1)[1].strip()
                if delayed_text and delayed_text.lower() != "none reported":
                    report["delayed_items"].extend([item.strip() for item in delayed_text.split(",") if item.strip()])
        return report
