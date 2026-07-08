# Project Health Reporting Agent

Offline AI agent for reading Excel project plans, scoring health with a RAG model, generating weekly executive reports, and producing a monthly PowerPoint synthesis.

## Project Overview

The agent scans every workbook in `data/`, reads each worksheet, normalizes messy project data, calculates a RAG score, and writes weekly TXT and Markdown reports plus a monthly executive presentation.

## Architecture Diagram


flowchart TD
    A[Excel workbooks in data/] --> B[WorkbookAnalyzer]
    B --> C[RAGEngine]
    C --> D[PMOAgent via Ollama]
    D --> E[Weekly report generator]
    E --> F[Monthly synthesis]
    F --> G[PowerPoint generator]

## Installation

1. Create and activate a Python 3.12 virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and adjust the Ollama host if needed.
4. Start Ollama locally and pull the model:

```bash
ollama pull llama2
```

## Requirements

- Python 3.12+
- pandas
- openpyxl
- python-pptx
- python-dotenv
- ollama

## How to Run

```bash
python app.py
```

The app automatically processes every `.xlsx` file in `data/` and writes outputs to `output/`.

## Folder Structure

- `agent/` core pipeline modules
- `data/` source Excel plans
- `methodology/` RAG methodology document
- `output/` generated reports and presentation
- `app.py` CLI entry point

## Sample Outputs

- `output/weekly_report_A.txt`
- `output/weekly_report_A.md`
- `output/weekly_report_B.txt`
- `output/weekly_report_B.md`
- `output/monthly_report.pptx`

## Scheduling

Use Windows Task Scheduler or Linux Cron to run `python app.py` weekly. The app is idempotent and regenerates the latest reports each run.

### Windows Task Scheduler

- Create a basic task.
- Trigger: weekly.
- Action: start a program.
- Program: path to the Python executable.
- Arguments: `app.py`.

### Linux Cron

```bash
0 8 * * 1 /path/to/python /path/to/Project-Health-Agent/app.py
```

## Future Improvements

- Add richer Excel pattern detection for more workbook variants.
- Persist historical runs for better trend analysis.
- Expand PowerPoint visuals with charts and portfolio heatmaps.
- Add automated tests for workbook inference and scoring.
