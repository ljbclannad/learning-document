---
name: interview-summary-doc
description: Create structured interview summary, debrief, and candidate evaluation documents from interview notes, transcripts, scorecards, or hiring feedback. Use when Codex needs to write a 面试总结, 面试纪要, 面试评价, 候选人评估, panel debrief, hiring recommendation, or next-round focus note from one or more interview artifacts.
---

# Interview Summary Doc

## Overview

Turn raw interview artifacts into decision-ready summary documents. Separate observed evidence from inference, highlight signal and risk, and end with a clear recommendation or next step.

## Workflow

1. Collect the minimum context before drafting.
   - Prefer interview notes or transcript first.
   - Pull role context when available: job description, target level, interview round, interviewer role, and evaluation dimensions.
   - State assumptions explicitly when critical context is missing.
2. Build an evidence matrix before writing prose.
   - Group evidence by dimension such as technical depth, problem solving, communication, collaboration, ownership, and role fit.
   - Distinguish between observed behavior, candidate self-report, and interviewer inference.
   - Keep contradictory evidence instead of averaging it away.
3. Choose the output mode.
   - Use the standard summary for a single interviewer or single round.
   - Use the panel rollup when combining multiple interviewers or rounds.
   - Use the candidate feedback version only when the user explicitly asks for external-facing feedback.
   - Use the next-round focus note when the goal is to guide later interviews instead of making a final recommendation.
4. Draft in evidence-first order.
   - Lead with overall recommendation and confidence.
   - Follow with strengths, risks, competency assessment, and open questions.
   - Keep each judgment tied to a concrete example, answer, or behavioral signal.
5. Run a final sanity check.
   - Remove vague praise without evidence.
   - Mark uncertainty when the source material is thin or conflicting.
   - Exclude protected characteristics, speculation about personal background, and comparative comments that are not job-relevant.

## Writing Rules

- Prefer concise, decision-oriented prose over long narrative recap.
- Use calibrated recommendations such as `strong hire`, `hire`, `mixed`, `no hire`, or `insufficient signal`.
- Preserve uncertainty. If the evidence is weak, say so directly.
- Avoid fabricating examples, scores, or quotes that are not present in the source material.
- Collapse duplicate observations from multiple interviewers unless disagreement matters.
- If notes are sparse, produce a shorter memo plus explicit follow-up questions instead of padding the document.

## Default Output Shape

- Header: role, candidate, interview round, interviewer, source materials used
- Recommendation: decision plus confidence and one-sentence rationale
- Evidence summary: strongest positive signals and main concerns
- Competency assessment: dimension-by-dimension view with evidence
- Open questions: gaps that still need validation
- Suggested next step: hire decision, additional round focus, or data needed

## References

- Read [references/templates.md](references/templates.md) when choosing a summary format or when the user asks for a reusable template.
- Read [references/evaluation-guide.md](references/evaluation-guide.md) when you need evaluation dimensions, recommendation calibration, or examples of strong evidence-first phrasing.

## Output Format Notes

- Deliver in Markdown by default unless the user asks for another format.
- If the user asks for a `.docx` artifact, use the `doc` skill after drafting the content.
