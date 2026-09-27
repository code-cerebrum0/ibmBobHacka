# Bob Task Session Screenshots

This directory contains IBM Bob Task Session screenshots captured during the EgressProof hackathon demonstration.
They serve as evidence of Bob's role in the detect → diagnose → repair → verify loop.

## Existing screenshots

| File | Content |
|---|---|
| `egressproof_build_and_detect.png` | Bob building the EgressProof tool (isolation.py, workflow.py, reporter.py) using Agent mode with parallel subagents |
| `egressproof_repair.png` | Bob reading the failure report (`isolated-fail.txt`) and repairing `demo-app/Dockerfile` — model bake-in + `TRANSFORMERS_OFFLINE=1` |

## How to add a new session summary

1. Complete your Bob task.
2. At the end of the session, ask Bob:
   > "Preserve the Bob Task Session Summary for this task as additional hackathon evidence."
3. Take a screenshot of the full task session (Bob sidebar showing the task tree and completed steps).
4. Save it here as `<short_description>.png` and add a row to the table above.

## This task's session summary

The session summary for the *hackathon presentation improvements* task (CLI output, README, DEMO.md)
should be saved here as `egressproof_presentation_polish.png` once the task is complete.

> **Note:** Do not fabricate screenshots. Only commit screenshots from actual Bob sessions.
