# EgressProof — Live Demo Guide

**Target duration:** 2–3 minutes  
**Audience:** Hackathon judges  
**What you are showing:** A tool that catches hidden runtime internet dependencies automatically, and IBM Bob repairing the problem from a generated evidence report.

---

## Prerequisites (do before the demo)

Open **PowerShell** or **Command Prompt** in the project root folder (`d:\coding2\ibmBobHacka`).

```powershell
# 1. Install EgressProof
pip install -e ".[dev]"

# 2. Confirm Docker is running
docker info --format "Docker: {{.ServerVersion}}"

# 3. Pre-pull the base image so the demo build is fast
docker pull python:3.11-slim

# 4. Confirm the repaired Dockerfile is in place (post-Bob state)
Select-String -Path "demo-app\Dockerfile" -Pattern "TRANSFORMERS_OFFLINE" -Quiet && Write-Host "Dockerfile: repaired OK"
```

---

## Step 0 — Set the scene (30 seconds)

> "EgressProof answers one question: does this Dockerized application actually work in an environment where it can't reach the internet?
>
> Not 'does the container start?' — that's easy. Does the *workflow* succeed?
>
> The demo app is a document Q&A service. It starts fine, passes health checks, but on the first real request it silently tries to download an AI model from Hugging Face. In production — where egress is blocked — that fails silently at 2 AM.
>
> Let's see EgressProof catch it."

---

## Step 1 — Baseline run (normal network) — ~30 seconds

```powershell
python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml --no-isolation
```

**Expected output:**

```
  ✓ health
  ✓ upload-document
  ✓ ask-question

Unexpected runtime dependencies detected: 0

RESULT: VERIFIED
```

> "Normal network — everything passes. The app works fine when it can reach the internet. Now let's apply the deployment boundary."

---

## Step 2 — Restricted-egress run — ~30 seconds

```powershell
python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml
```

> "Same app, same workflow, same Docker image. Only difference: `--dns 0.0.0.0` — the container's DNS resolver is broken, exactly like a restricted-egress production environment."

**Expected output:**

```
EGRESSPROOF

Application : LocalDocQA
Boundary    : Restricted egress

  ✓ health
  ✓ upload-document
  ✗ ask-question

Unexpected runtime dependencies:
  huggingface.co

Evidence:
  Runtime model download attempted while external name resolution was unavailable.

RESULT: FAILED
```

> "Health check passes. Upload passes. But `ask-question` fails with a 503.
>
> EgressProof collected the container logs, scanned them, and identified the exact hostname the app tried to reach: `huggingface.co`.
>
> It also wrote a structured report. That report is exactly what I give to IBM Bob."

---

## Step 3 — Show the evidence report (20 seconds)

```powershell
Get-Content reports\isolated-fail.txt
```

> "This is a real report from the run we just did — every field is grounded in actual collected evidence. Nothing fabricated."

---

## Step 4 — IBM Bob diagnosis and repair (30 seconds)

> "Now I open IBM Bob in Agent mode and paste this prompt:"

```
Read reports/isolated-fail.txt, demo-app/Dockerfile,
demo-app/backend/main.py, and demo-app/backend/requirements.txt.

The application failed the 'ask-question' workflow step under restricted egress.
The failure evidence is in the report.

Identify the root cause and modify demo-app/Dockerfile so that the application
no longer requires internet access during runtime to serve the /ask endpoint.
Do not change the application logic. Only change the packaging/build steps.
```

> "Bob reads the report, identifies that `all-MiniLM-L6-v2` is being downloaded at runtime, and adds a build step to bake the model into the image — plus sets `TRANSFORMERS_OFFLINE=1` so it never attempts a network call at runtime."

Show the repaired section of the Dockerfile:

```powershell
Select-String -Path "demo-app\Dockerfile" -Pattern "REPAIR" -Context 0,6
```

**Expected output:**

```dockerfile
# ── REPAIR: bake the embedding model into the image at build time ─────────────
RUN python - <<'EOF'
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")
EOF

ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1
```

> "That's the complete fix. No manual debugging. Bob read the evidence and applied the minimal correct change."

---

## Step 5 — Re-verification after repair — ~30 seconds

```powershell
python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml
```

> "Same restricted-egress boundary. Rebuilt image. Let's run the same workflow."

**Expected output:**

```
EGRESSPROOF

Application : LocalDocQA
Boundary    : Restricted egress

  ✓ health
  ✓ upload-document
  ✓ ask-question

Unexpected runtime dependencies detected: 0

RESULT: VERIFIED
```

> "All three steps pass. Zero runtime dependencies detected. VERIFIED."

---

## Step 6 — Wrap up (15 seconds)

> "What you just saw:
>
> 1. EgressProof detected a hidden runtime dependency that a container health check would never catch.
> 2. It produced structured evidence — not raw logs — pointing directly at the offending hostname.
> 3. IBM Bob read that evidence, diagnosed the root cause, and applied a minimal correct fix.
> 4. EgressProof confirmed the fix works under the same restricted-egress boundary.
>
> The whole loop — detect, diagnose, repair, verify — in under three minutes, with no manual debugging."

---

## Fallback: show committed reports (if live run is skipped)

If you want to skip the live Docker runs and just narrate from pre-recorded evidence:

```powershell
# Show the failure report
Get-Content reports\isolated-fail.txt

# Show the pass report
Get-Content reports\isolated-pass.txt

# Show the JSON evidence (first 40 lines)
Get-Content reports\isolated-fail.json | Select-Object -First 40
```

Point to the Bob session screenshots in `bob_sessions\`:
- `egressproof_build_and_detect.png` — Bob building the tool and detecting the failure
- `egressproof_repair.png` — Bob diagnosing and repairing the Dockerfile

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` | Start Docker Desktop and confirm `docker info` works |
| Build takes too long | Pre-pull `python:3.11-slim` before the demo |
| Port 8000 already in use | `docker rm -f egressproof-app` then retry |
| `pip install` fails | Run `pip install -e ".[dev]" --quiet` |
| Step 1 shows FAIL under `--no-isolation` | Check internet access; the model may not be baked in |
| PowerShell execution policy error | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
