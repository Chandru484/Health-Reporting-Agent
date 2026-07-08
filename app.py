"""Command-line entry point for the Project Health Reporting Agent."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from agent.analyzer import WorkbookAnalyzer
from agent.llm import PMOAgent
from agent.ppt_generator import PowerPointGenerator
from agent.rag_engine import RAGEngine
from agent.report_generator import ReportGenerator
from agent.utils import ensure_directory, write_text_file


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project Health Reporting Agent")
    parser.add_argument("--data-dir", default="data", help="Folder containing Excel project plans")
    parser.add_argument("--output-dir", default="output", help="Folder to write reports and presentation")
    parser.add_argument("--model", default="llama2", help="Ollama model name")
    parser.add_argument("--host", default="", help="Optional Ollama host")
    return parser


def main() -> int:
    configure_logging()
    parser = build_argument_parser()
    args = parser.parse_args()

    base_dir = Path(args.data_dir)
    output_dir = ensure_directory(Path(args.output_dir))
    methodology_dir = ensure_directory(Path("methodology"))

    analyzer = WorkbookAnalyzer()
    rag_engine = RAGEngine()
    llm = PMOAgent(model=args.model, host=args.host or None)
    report_generator = ReportGenerator(output_dir=output_dir, llm=llm)

    workbooks = sorted(base_dir.glob("*.xlsx"))
    if not workbooks:
        logging.error("No Excel files found in %s", base_dir)
        return 1

    generated_reports = []
    for index, workbook_path in enumerate(workbooks, start=1):
        metrics = analyzer.analyze_file(workbook_path)
        assessment = rag_engine.assess(metrics)
        report_paths = report_generator.generate_weekly_report(project_id=chr(64 + index), metrics=metrics, assessment=assessment)
        generated_reports.append({"workbook": workbook_path, "metrics": metrics, "assessment": assessment, "paths": report_paths})
        logging.info("Generated weekly report for %s", workbook_path.name)

    monthly_summary = report_generator.generate_monthly_summary_from_files([item["paths"]["txt"] for item in generated_reports])
    write_text_file(output_dir / "monthly_summary.txt", monthly_summary)
    ppt_path = PowerPointGenerator(output_dir).build(monthly_summary)
    logging.info("Generated presentation at %s", ppt_path)

    methodology_text = _methodology_document()
    write_text_file(methodology_dir / "RAG_Methodology.md", methodology_text)

    return 0


def _methodology_document() -> str:
    return """# RAG Methodology

## Purpose
This framework provides a consistent, explainable project health assessment using a 0-10 risk score mapped to Red, Amber, and Green.

## Inputs
- Schedule slippage
- Budget burn
- Milestone health
- Task completion percentage
- Blockers
- Stakeholder sentiment
- Risks
- Dependencies

## Scoring Approach
The engine evaluates five weighted dimensions:
- Schedule: 30%
- Progress: 20%
- Milestones: 20%
- Risks: 15%
- Stakeholder sentiment: 15%

Each dimension is translated into a sub-score from 0 to 2. These are combined into a weighted 0-10 risk score.

## Status Mapping
- 0-2: Green
- 3-5: Amber
- 6-10: Red

## Assumptions
- Missing values should not break the assessment.
- If budget information is not available, budget signals are treated as neutral.
- Comments are used as a proxy for stakeholder sentiment when formal survey data is not available.
- A project can still be Amber even with a green schedule if open blockers or sentiment indicate concern.

## Decision Rules
- Schedule slippage drives risk upward quickly when dates are late or schedule health is red.
- Progress and milestone completion prevent false Greens when execution is slow.
- Open blockers, heavy risk logs, and dependency pressure add incremental risk.
- Negative comments or repeated concern language lower sentiment and increase the overall score.

## Interpretation
The RAG color is the executive summary. The reason codes and recommendations provide the operational detail needed to act.
"""


if __name__ == "__main__":
    raise SystemExit(main())
