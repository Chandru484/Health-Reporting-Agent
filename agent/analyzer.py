"""Workbook ingestion and project metric extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .rag_engine import ProjectMetrics
from .utils import (
    deduplicate_dicts,
    expand_merged_cells,
    is_blank_row,
    load_workbook_safely,
    normalize_date,
    normalize_key,
    normalize_percentage,
    normalize_whitespace,
    parse_number,
    safe_text,
)


@dataclass(slots=True)
class SheetData:
    """Structured representation of a worksheet."""

    sheet_name: str
    headers: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)


class WorkbookAnalyzer:
    """Load every worksheet and infer project-level metrics."""

    COLUMN_ALIASES = {
        "project_name": ["project name", "program name"],
        "project_manager": ["project manager", "pm", "owner", "lead"],
        "task_name": ["task name", "task", "activity", "work item"],
        "milestone": ["milestone", "phase/milestone", "phase", "stage"],
        "start_date": ["start date", "start", "baseline start", "planned start"],
        "end_date": ["end date", "finish", "baseline finish", "planned finish"],
        "completion": ["% complete", "percent complete", "completion", "progress"],
        "status": ["status", "rag", "schedule health", "health"],
        "comments": ["comments", "comment", "status comment", "description", "notes"],
        "budget": ["budget", "budget burn", "cost", "spent", "burn"],
        "dependencies": ["dependencies", "predecessors", "dependency"],
        "blocker": ["blocked", "blocker", "on hold?", "at risk?", "critical ?"],
    }

    def analyze_file(self, workbook_path: Path) -> ProjectMetrics:
        """Convert a workbook into normalized project metrics."""

        workbook = load_workbook_safely(workbook_path)
        sheet_data = [self._read_sheet(sheet) for sheet in workbook.worksheets]
        project_name = self._project_name(sheet_data, workbook_path)
        project_manager = self._project_manager(sheet_data)
        records = [record for sheet in sheet_data for record in sheet.rows]
        records = deduplicate_dicts(records)

        completion_values = self._collect_column_values(records, ["completion"])
        completion_fraction = self._best_percentage(completion_values)
        status_values = self._collect_text_values(records, ["status"])
        schedule_health = self._best_schedule_health(status_values)
        start_dates = self._collect_column_values(records, ["start_date"])
        end_dates = self._collect_column_values(records, ["end_date"])
        comments = self._collect_comments(sheet_data, records)
        risks = self._collect_risk_items(records, comments)
        dependencies = self._collect_dependencies(records)
        delayed_items = self._delayed_items(records)
        milestones_total, milestones_done = self._milestone_counts(records)
        tasks_total, tasks_done = self._task_counts(records)
        open_blockers = self._open_blocker_count(records)
        budget_burn = self._budget_burn(records)
        schedule_variance_days = self._schedule_variance(records)
        sentiment_score = self._sentiment_score(comments)

        return ProjectMetrics(
            project_name=project_name,
            project_manager=project_manager,
            schedule_variance_days=schedule_variance_days,
            schedule_health=schedule_health,
            completion_fraction=completion_fraction,
            milestone_completion_fraction=(milestones_done / milestones_total) if milestones_total else None,
            open_blockers=open_blockers,
            total_blockers=max(open_blockers, self._count_blockers(records)),
            risks=risks,
            dependencies=dependencies,
            sentiment_score=sentiment_score,
            budget_burn_fraction=budget_burn,
            budget_variance_fraction=None,
            status_values=status_values,
            comments=comments,
            milestones_total=milestones_total,
            milestones_done=milestones_done,
            tasks_total=tasks_total,
            tasks_done=tasks_done,
            delayed_items=delayed_items,
            latest_end_date=self._latest_date(end_dates),
            latest_start_date=self._latest_date(start_dates),
        )

    def _read_sheet(self, sheet) -> SheetData:
        expand_merged_cells(sheet)
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return SheetData(sheet_name=sheet.title)

        header_index = self._detect_header_row(rows)
        headers = [normalize_whitespace(value) or f"column_{index + 1}" for index, value in enumerate(rows[header_index])]
        data_rows: list[dict[str, Any]] = []
        comments: list[str] = []
        for raw_row in rows[header_index + 1 :]:
            if is_blank_row(raw_row):
                continue
            row_map = {headers[index]: raw_row[index] if index < len(raw_row) else None for index in range(len(headers))}
            normalized = self._normalize_row(row_map)
            data_rows.append(normalized)
            comment_values = [safe_text(row_map[key]) for key in row_map if key and self._is_comment_column(key) and safe_text(row_map[key])]
            if comment_values:
                comments.extend(comment_values)
            elif sheet.title.lower() == "comments":
                text_values = [safe_text(value) for value in raw_row if isinstance(value, str) and len(safe_text(value)) > 10]
                if text_values:
                    comments.append(max(text_values, key=len))
        return SheetData(sheet_name=sheet.title, headers=headers, rows=data_rows, comments=comments)

    def _detect_header_row(self, rows: list[tuple[Any, ...]]) -> int:
        best_index = 0
        best_score = -1
        alias_set = {alias for aliases in self.COLUMN_ALIASES.values() for alias in aliases}
        for index, row in enumerate(rows[:10]):
            score = 0
            for value in row:
                text = normalize_key(value)
                if not text:
                    continue
                if text in alias_set:
                    score += 3
                elif len(text.split()) <= 4:
                    score += 1
            if score > best_score:
                best_score = score
                best_index = index
        return best_index

    def _normalize_row(self, row_map: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in row_map.items():
            normalized_key = normalize_key(key)
            normalized[normalized_key] = value
        return normalized

    def _project_name(self, sheets: list[SheetData], workbook_path: Path) -> str:
        for sheet in sheets:
            if sheet.sheet_name.lower() == "summary":
                for record in sheet.rows:
                    value = self._match_value(record, ["project_name"])
                    if self._is_valid_project_label(value):
                        return value
        for sheet in sheets:
            for record in sheet.rows:
                value = self._match_value(record, ["task_name"])
                if self._is_valid_project_label(value):
                    return value
        for sheet in sheets:
            for record in sheet.rows:
                value = self._match_value(record, ["project_name"])
                if self._is_valid_project_label(value):
                    return value
        return workbook_path.stem

    def _project_manager(self, sheets: list[SheetData]) -> str:
        for sheet in sheets:
            if sheet.sheet_name.lower() == "summary":
                for record in sheet.rows:
                    value = self._match_value(record, ["project_manager"])
                    if self._is_valid_project_label(value):
                        return value
        for sheet in sheets:
            for record in sheet.rows:
                value = self._match_value(record, ["project_manager"])
                if self._is_valid_project_label(value):
                    return value
        return "Unknown"

    def _match_value(self, record: dict[str, Any], semantic_keys: list[str]) -> str:
        columns = self._semantic_columns(record.keys(), semantic_keys)
        for column in columns:
            value = safe_text(record.get(column))
            if self._is_valid_project_label(value):
                return value
        return ""

    def _semantic_columns(self, columns: Iterable[str], semantic_keys: list[str]) -> list[str]:
        aliases = [alias for key in semantic_keys for alias in self.COLUMN_ALIASES.get(key, [key])]
        matches: list[str] = []
        for column in columns:
            normalized = normalize_key(column)
            if normalized in aliases:
                matches.append(column)
                continue
            if any(alias in normalized for alias in aliases):
                matches.append(column)
        return matches

    def _collect_column_values(self, records: list[dict[str, Any]], semantic_keys: list[str]) -> list[Any]:
        columns_seen: list[str] = []
        for record in records:
            columns_seen.extend(self._semantic_columns(record.keys(), semantic_keys))
        values: list[Any] = []
        for record in records:
            for column in columns_seen:
                if column in record and record[column] not in (None, ""):
                    values.append(record[column])
        return values

    def _collect_text_values(self, records: list[dict[str, Any]], semantic_keys: list[str]) -> list[str]:
        return [safe_text(value) for value in self._collect_column_values(records, semantic_keys) if safe_text(value)]

    def _best_percentage(self, values: list[Any]) -> float | None:
        percentages = [normalize_percentage(value) for value in values]
        percentages = [value for value in percentages if value is not None]
        if not percentages:
            return None
        return max(percentages)

    def _best_schedule_health(self, values: list[str]) -> str:
        for status in values:
            lowered = status.lower()
            if lowered in {"red", "amber", "yellow", "green"}:
                return "Amber" if lowered == "yellow" else lowered.title()
        return "Unknown"

    def _collect_comments(self, sheets: list[SheetData], records: list[dict[str, Any]]) -> list[str]:
        comments: list[str] = []
        for sheet in sheets:
            comments.extend(sheet.comments)
        for record in records:
            for key in self._semantic_columns(record.keys(), ["comments"]):
                value = safe_text(record.get(key))
                if self._is_valid_comment(value):
                    comments.append(value)
        return [normalize_whitespace(comment) for comment in comments if normalize_whitespace(comment)]

    def _collect_risk_items(self, records: list[dict[str, Any]], comments: list[str]) -> list[str]:
        risks: list[str] = []
        for record in records:
            for key in self._semantic_columns(record.keys(), ["blocker"]):
                value = safe_text(record.get(key))
                if self._is_valid_risk_signal(value):
                    risks.append(f"{key}: {value}")
        for comment in comments:
            lowered = comment.lower()
            if any(token in lowered for token in ("risk", "delay", "blocked", "issue", "late", "concern", "impact")):
                risks.append(comment)
        unique_risks = [item for item in dict.fromkeys(risks)]
        return unique_risks[:10]

    def _collect_dependencies(self, records: list[dict[str, Any]]) -> list[str]:
        dependencies: list[str] = []
        for record in records:
            for key in self._semantic_columns(record.keys(), ["dependencies"]):
                value = safe_text(record.get(key))
                if self._is_valid_dependency(value):
                    dependencies.append(value)
        unique_dependencies = [item for item in dict.fromkeys(dependencies)]
        return unique_dependencies[:10]

    def _milestone_counts(self, records: list[dict[str, Any]]) -> tuple[int, int]:
        milestones = 0
        completed = 0
        for record in records:
            milestone = self._match_value(record, ["milestone"])
            if milestone:
                milestones += 1
                status = self._match_value(record, ["status"]).lower()
                completion = self._match_completion(record)
                if status in {"completed", "done", "closed"} or (completion is not None and completion >= 0.99):
                    completed += 1
        return milestones, completed

    def _task_counts(self, records: list[dict[str, Any]]) -> tuple[int, int]:
        tasks = 0
        done = 0
        for record in records:
            task = self._match_value(record, ["task_name"])
            if task:
                tasks += 1
                status = self._match_value(record, ["status"]).lower()
                completion = self._match_completion(record)
                if status in {"completed", "done", "closed"} or (completion is not None and completion >= 0.99):
                    done += 1
        return tasks, done

    def _open_blocker_count(self, records: list[dict[str, Any]]) -> int:
        count = 0
        for record in records:
            for key in self._semantic_columns(record.keys(), ["blocker"]):
                value = safe_text(record.get(key)).lower()
                if value in {"yes", "true", "1", "red", "amber", "yellow", "at risk"}:
                    count += 1
                elif value and any(token in value for token in ("block", "hold", "risk", "issue", "delay")):
                    count += 1
        return count

    def _count_blockers(self, records: list[dict[str, Any]]) -> int:
        return self._open_blocker_count(records)

    def _budget_burn(self, records: list[dict[str, Any]]) -> float | None:
        values: list[float] = []
        for record in records:
            for key in self._semantic_columns(record.keys(), ["budget"]):
                numeric = parse_number(record.get(key))
                if numeric is not None:
                    values.append(numeric)
        if not values:
            return None
        value = max(values)
        return value if value <= 1 else value / 100.0 if value <= 100 else None

    def _schedule_variance(self, records: list[dict[str, Any]]) -> float | None:
        variances: list[float] = []
        for record in records:
            for key in record:
                normalized = normalize_key(key)
                if "variance" not in normalized:
                    continue
                numeric = parse_number(record.get(key))
                if numeric is not None:
                    variances.append(numeric)
        if not variances:
            return None
        return min(variances)

    def _sentiment_score(self, comments: list[str]) -> float:
        if not comments:
            return 0.5
        positive_tokens = ("good", "great", "on track", "resolved", "aligned", "completed", "progress")
        negative_tokens = ("delay", "late", "blocked", "issue", "risk", "impact", "concern")
        positive = sum(any(token in comment.lower() for token in positive_tokens) for comment in comments)
        negative = sum(any(token in comment.lower() for token in negative_tokens) for comment in comments)
        total = positive + negative
        if total == 0:
            return 0.5
        return max(0.0, min(1.0, 0.5 + ((positive - negative) / max(1, total)) * 0.5))

    def _match_completion(self, record: dict[str, Any]) -> float | None:
        columns = self._semantic_columns(record.keys(), ["completion"])
        for column in columns:
            value = normalize_percentage(record.get(column))
            if value is not None:
                return value
        return None

    def _latest_date(self, values: list[Any]) -> str:
        date_values = [normalize_date(value) for value in values if normalize_date(value)]
        if not date_values:
            return ""
        return max(date_values)

    def _delayed_items(self, records: list[dict[str, Any]]) -> list[str]:
        delayed: list[tuple[float, str]] = []
        for record in records:
            item_name = self._match_value(record, ["task_name"]) or self._match_value(record, ["milestone"])
            if not item_name:
                continue
            negative_variances: list[float] = []
            for key, value in record.items():
                normalized = normalize_key(key)
                if "variance" not in normalized and "float" not in normalized:
                    continue
                numeric = parse_number(value)
                if numeric is not None and numeric < 0:
                    negative_variances.append(numeric)
            if not negative_variances:
                continue
            worst_delay = min(negative_variances)
            delayed.append((worst_delay, f"{item_name} ({abs(worst_delay):.0f}d behind)"))
        delayed.sort(key=lambda pair: pair[0])
        return [label for _score, label in delayed[:5]]

    def _is_comment_column(self, key: str) -> bool:
        normalized = normalize_key(key)
        return any(alias in normalized for alias in self.COLUMN_ALIASES["comments"])

    def _is_valid_project_label(self, value: str) -> bool:
        lowered = safe_text(value).strip().lower()
        if not lowered:
            return False
        if lowered in {"owner", "pm", "lead", "project", "project name", "#unparseable", "none", "n/a"}:
            return False
        return lowered != "unknown"

    def _is_valid_comment(self, value: str) -> bool:
        lowered = safe_text(value).strip().lower()
        return bool(lowered) and lowered not in {"#unparseable", "none", "n/a", "na"}

    def _is_valid_risk_signal(self, value: str) -> bool:
        lowered = safe_text(value).strip().lower()
        if not lowered or lowered in {"no", "false", "0", "green", "#unparseable", "none", "n/a", "na"}:
            return False
        return any(token in lowered for token in ("risk", "delay", "blocked", "issue", "late", "concern", "impact", "hold", "at risk", "red", "amber", "yellow"))

    def _is_valid_dependency(self, value: str) -> bool:
        lowered = safe_text(value).strip().lower()
        if not lowered or lowered in {"none", "n/a", "na", "#unparseable"}:
            return False
        if len(lowered) > 120:
            return False
        return any(char.isalpha() for char in lowered) or any(sep in lowered for sep in (",", ";", "+", "-", "/"))


def build_metrics_from_workbook(workbook_path: Path) -> ProjectMetrics:
    """Convenience wrapper for single-workbook analysis."""

    return WorkbookAnalyzer().analyze_file(workbook_path)


def metrics_to_frame(metrics: ProjectMetrics) -> pd.DataFrame:
    """Convert metrics into a one-row dataframe for downstream processing."""

    return pd.DataFrame([metrics.__dict__])
