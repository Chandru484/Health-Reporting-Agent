# RAG Methodology

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
