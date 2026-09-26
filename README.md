# EgressProof

> **Detect → Diagnose → Repair → Verify**
>
> Automated detection of hidden runtime internet dependencies in Dockerized applications.

Built for the **IBM Bob 2.0 Hackathon** — demonstrating Agent mode, parallel subagents,
document understanding, debugging, and automated developer workflows.

---

## The Problem

Applications that appear self-contained can still have hidden runtime internet dependencies.
An AI application may claim to run locally but, on its first real request, silently attempt to:

- Download a Hugging Face model
- Contact an external API
- Load an asset from a CDN
- Send telemetry

This is only discovered **after** deployment into an environment with restricted egress —
far too late.

Simply checking whether a container starts is not enough.

---

## What EgressProof Does

1. **Builds** your Dockerized application.
2. **Starts** it under a restricted network environment (`docker network create --internal`).
3. **Executes** a predefined meaningful user workflow (configuration-driven YAML).
4. **Detects** when the workflow fails due to a hidden external dependency.
5. **Collects** evidence: failed step, container logs, matched suspicious patterns.
6. **Produces** a structured PASS/FAIL report.
7. **Invokes IBM Bob** to diagnose the root cause and repair the application packaging.
8. **Rebuilds** and **re-runs** the same workflow to produce a VERIFIED result.

---

## Demo Application: LocalDocQA

A small FastAPI document question-answering service with a realistic hidden runtime dependency:

```
SentenceTransformer("all-MiniLM-L6-v2")
```

The model is loaded **lazily on the first `/ask` request** — NOT at startup. The app starts
and passes health checks, but the first real workflow step that needs embeddings triggers
a download from `huggingface.co`.

Under network isolation: **workflow fails**.
After Bob's repair (model baked into image): **workflow passes**.

---

## Prerequisites

- **Docker** (Desktop or Engine) — running and accessible on the command line
- **Python 3.11+**
- Internet access on the build machine (for the baseline run and model bake-in)

```bash
pip install -e ".[dev]"
```

---

## Quick Start

### 1. Online Baseline (all steps should PASS)

```bash
python -m egressproof run \
  --app demo-app \
  --workflow workflows/document-qa.yaml \
  --no-isolation
```

Expected output:
```
  [PASS] health
  [PASS] upload-document
  [PASS] ask-question
Result: VERIFIED
```

### 2. Isolated Run (ask-question should FAIL)

```bash
python -m egressproof run \
  --app demo-app \
  --workflow workflows/document-qa.yaml
```

Expected output:
```
  [PASS] health
  [PASS] upload-document
  [FAIL] ask-question — Expected status 200, got 503

Suspicious patterns detected in container logs:
  - huggingface.co
  - EGRESS_BLOCKED

Result: FAILED
```

### 3. Bob Repair

Open **IBM Bob in Agent mode** and paste:

```
Read reports/<latest>-localdocqa-fail.txt, demo-app/Dockerfile,
demo-app/backend/main.py, and demo-app/backend/requirements.txt.

The application failed the 'ask-question' workflow step under network isolation.
The failure evidence is in the report.

Identify the root cause and modify demo-app/Dockerfile so that the application
no longer requires internet access during runtime to serve the /ask endpoint.
Do not change the application logic. Only change the packaging/build steps.
```

Bob will identify the missing model download in the Dockerfile and add:

```dockerfile
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')"
```

### 4. Re-Verification (all steps should PASS under isolation)

```bash
python -m egressproof run \
  --app demo-app \
  --workflow workflows/document-qa.yaml
```

Expected output:
```
  [PASS] health
  [PASS] upload-document
  [PASS] ask-question

External dependencies detected in logs: 0
Result: VERIFIED
```

---

## Repository Structure

```
egressproof/
├── egressproof/         # Core tool
│   ├── cli.py           # CLI entry point and orchestration
│   ├── builder.py       # docker build wrapper
│   ├── isolation.py     # internal network + container lifecycle
│   ├── workflow.py      # YAML workflow loader and HTTP executor
│   ├── evidence.py      # log collection and pattern scanning
│   └── reporter.py      # text + JSON report writer
│
├── demo-app/            # LocalDocQA demo application
│   ├── backend/main.py  # FastAPI app (contains the hidden dependency)
│   ├── Dockerfile       # intentionally missing model bake-in (before repair)
│   └── sample-data/     # sample.txt used by the workflow
│
├── workflows/
│   └── document-qa.yaml # workflow definition (health → upload → ask)
│
├── reports/             # generated reports (committed for demo evidence)
├── tests/               # unit and integration tests
├── evidence/            # Bob session screenshots
└── docs/                # isolation verification guide
```

---

## Network Isolation

EgressProof uses `docker network create --internal` — a Docker-native approach requiring
no iptables expertise:

- Containers on the internal bridge have **no default gateway** → cannot reach external IPs.
- The host can still reach containers via **published ports** (`-p 8000:8000`).
- The EgressProof runner sends HTTP to `localhost:8000` (host-side) → works fine.
- The app container tries to reach `huggingface.co` → blocked.

See [`docs/isolation-verification.md`](docs/isolation-verification.md) for manual verification steps.

---

## IBM Bob Usage

| Task | Bob Role |
|---|---|
| Write `isolation.py` | Agent — parallel subagent |
| Write `workflow.py` | Agent — parallel subagent |
| Diagnose failure report | **Agent — core demo** (reads report + Dockerfile) |
| Repair Dockerfile | **Agent — applies minimal diff** |
| Re-verification run | Agent — runs CLI command |

The `evidence/bob-session-summaries/` directory contains screenshots of Bob's
diagnosis and repair session for hackathon documentation.

---

## Tests

```bash
# Fast unit tests (no Docker, no internet)
pytest tests/test_workflow.py tests/test_reporter.py -v

# Integration tests (requires Docker)
pytest tests/test_isolation.py -v -m requires_docker

# Full app integration (requires Docker + internet)
pytest tests/test_local_app.py -v -m requires_internet
```

---

## Future Extensions

- eBPF-based network telemetry for precise per-process egress capture
- Kubernetes NetworkPolicy enforcement testing
- Multi-step repair with dependency tree analysis
- Web dashboard for report visualization
- Support for docker-compose multi-service applications
- CI/CD integration (GitHub Actions)
- Automatic dependency patching beyond Dockerfile model baking
