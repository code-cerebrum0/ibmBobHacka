# EgressProof — Implementation Plan

## Top-Level Overview

**Goal:** Build a working hackathon prototype called EgressProof that demonstrates an automated
detect-diagnose-repair-verify loop for hidden runtime internet dependencies in Dockerized applications.

**Core demonstration arc:**
1. LocalDocQA (demo app) runs successfully with internet access.
2. Under Docker network isolation, a meaningful user workflow fails because the app tries to
   download a Hugging Face model at runtime.
3. EgressProof collects logs and produces a structured failure report.
4. IBM Bob inspects the evidence and repairs the application packaging.
5. EgressProof rebuilds and re-runs the same workflow under the same isolation.
6. The final report shows VERIFIED — zero unexpected external dependencies.

**Scope:** MVP prototype only. No Kubernetes, no eBPF, no cloud, no large dashboard.

**Key technical decisions (rationale in each sub-task):**
- Network isolation: `docker network create --internal` (internal bridge — containers reach each
  other, none reach the public internet).
- Runner ↔ app communication: runner process runs on the host and publishes one port from the
  app container; internal network used for isolation check, published port for workflow execution.
  See Sub-Task 3 for the exact pattern.
- Evidence: container logs (`docker logs`) + Python traceback capture. No packet inspection needed
  for MVP; the HuggingFace error is always in the application log.
- Determinism: model is NOT baked into the demo image (Dockerfile intentionally omits the
  download step). Docker image is always built fresh, no host-side HuggingFace cache volume.

---

## Sub-Task 1 — LocalDocQA Demo Application

**Status:** `[ ] pending`

**Intent:**
Build the smallest Python/FastAPI application that exposes a realistic document-question-answering
workflow AND contains one realistic hidden runtime dependency that will fail under network isolation.

The hidden dependency: `SentenceTransformer("all-MiniLM-L6-v2")` is instantiated on the first
POST /ask request (lazy init), not at startup. This means the app starts and stays healthy, but
the first real workflow step that needs embeddings triggers a download from huggingface.co.

**Expected Outcomes:**
- GET /health → 200
- POST /upload (multipart file) → 200, document stored in memory
- POST /ask {"question": "..."} → 200 with answer text **when internet is available**
- POST /ask → traceback containing "huggingface.co" or "ConnectionError" in container logs
  **when internet is blocked**
- Application passes a local smoke test (`pytest tests/test_local_app.py`) with internet available

**Todo List:**
1. Create `demo-app/backend/main.py` — FastAPI app with /health, /upload, /ask endpoints.
   - /upload: accept a `.txt` file, read as UTF-8 text, store in a module-level dict keyed by filename.
   - /ask: lazy-load SentenceTransformer, embed query + stored doc chunks, return top match as answer.
   - Use simple keyword/cosine search over stored chunks; no FAISS needed for MVP.
2. Create `demo-app/backend/requirements.txt` — fastapi, uvicorn, sentence-transformers, python-multipart. No PDF library needed.
3. Create `demo-app/sample-data/sample.txt` — a short plain-text document (5–10 sentences).
4. Create `demo-app/Dockerfile` — intentionally does NOT download the model during build.
   Sets TRANSFORMERS_CACHE to /app/models (empty at runtime on first broken run).
5. Create `demo-app/docker-compose.yml` — single service, port 8000 exposed.
6. Create `tests/test_local_app.py` — smoke tests: health, upload sample.txt, ask a question,
   assert 200 responses. Run against a live local uvicorn process.

**Relevant Context:**
- `demo-app/backend/main.py` is the only source file that matters for the hidden dependency.
- The lazy-load pattern: `_model = None` at module level; `def get_model(): global _model; if _model is None: _model = SentenceTransformer(...)`.
- Only `.txt` files are supported. The `/upload` endpoint reads the file as UTF-8 text directly — no format conversion needed.
- The model name `all-MiniLM-L6-v2` is ~90 MB — small enough to download during repair but large enough to be realistic.

---

## Sub-Task 2 — Docker Isolation Mechanism

**Status:** `[ ] pending`

**Intent:**
Implement reliable network isolation for the demo app container so that outbound internet traffic
is blocked while the EgressProof runner (on the host) can still communicate with the container.

**Chosen approach: Docker internal network + published port**

Docker's `--internal` flag on a bridge network prevents the bridge from getting a default gateway
route, so containers on that network cannot reach any IP outside the Docker host. The host can
still reach containers via published ports (`-p 8000:8000`). This gives us:
- App container: can talk to other containers on the same network, cannot reach internet.
- EgressProof runner: sends HTTP to `localhost:8000` — works because port is published to host.
- Zero iptables expertise required; no root-level firewall rules beyond what Docker manages.

**Alternative considered and rejected:** `--network none` — prevents all communication including
from the runner, requiring a sidecar container or docker exec, adding complexity.

**Expected Outcomes:**
- `egressproof/isolation.py` provides `create_isolated_network()` and `remove_isolated_network()`.
- A container started with this network cannot resolve `huggingface.co` or reach any external IP.
- The runner on the host can reach the container on its published port.
- Manual verification: `docker run --network egressproof-isolated alpine ping 8.8.8.8` → fails.

**Todo List:**
1. Create `egressproof/isolation.py`:
   - `create_isolated_network(name)`: runs `docker network create --internal --driver bridge {name}`;
     idempotent (skip if already exists).
   - `remove_isolated_network(name)`: runs `docker network rm {name}` (ignore if not found).
   - `start_isolated_container(image, network, port, name)`: runs
     `docker run -d --name {name} --network {name} -p {port}:{port} {image}`;
     returns container id.
   - `stop_and_remove_container(name)`: runs `docker stop {name} && docker rm {name}`.
   - `get_container_logs(name)`: returns stdout+stderr of `docker logs {name}`.
2. Write a manual verification note in `docs/isolation-verification.md` describing how to confirm
   the network is truly isolated (the `ping 8.8.8.8` test).

**Relevant Context:**
- All Docker operations use `subprocess.run(["docker", ...], ...)` — no Docker SDK dependency.
- Keep isolation.py free of business logic; it is a pure Docker wrapper.

---

## Sub-Task 3 — Workflow Runner

**Status:** `[ ] pending`

**Intent:**
Implement a configuration-driven HTTP workflow runner that executes a sequence of steps against
the app and records PASS/FAIL for each, along with response details.

**Expected Outcomes:**
- `workflows/document-qa.yaml` defines health, upload, and ask steps.
- `egressproof/workflow.py` loads the YAML and executes each step.
- Each step result contains: step name, status (pass/fail), HTTP status code, response body
  (truncated), and error message if any.
- A failed step does not abort the run; all steps are attempted and results collected.
- The runner returns a structured `WorkflowResult` object (dataclass or dict).

**Todo List:**
1. Create `workflows/document-qa.yaml`:
   ```yaml
   name: document-question-answering
   base_url: "http://localhost:8000"
   steps:
     - name: health
       method: GET
       path: /health
       expect_status: 200
     - name: upload-document
       method: POST
       path: /upload
       file: demo-app/sample-data/sample.txt
       expect_status: 200
     - name: ask-question
       method: POST
       path: /ask
       json:
         question: "What is this document about?"
       expect_status: 200
   ```
2. Create `egressproof/workflow.py`:
   - `load_workflow(path)`: parses YAML, returns workflow dict.
   - `execute_step(step, base_url)`: dispatches GET/POST with file or JSON body using `requests`.
     Catches `requests.exceptions.ConnectionError` and `Timeout`; marks step FAIL on exception.
     Returns `StepResult` dataclass.
   - `run_workflow(workflow, base_url, timeout_per_step)`: iterates steps, calls execute_step,
     collects results. Adds a startup-wait loop (poll /health up to 30 s before starting).
   - `WorkflowResult` dataclass: workflow name, list of StepResult, overall pass/fail.
3. Create `egressproof/startup_wait.py`: simple retry loop for the health endpoint with
   configurable max_retries and interval.

**Relevant Context:**
- `requests` is the only HTTP dependency needed — already available in any Python environment.
- Keep `base_url` as a parameter, not hardcoded, so the same runner works for both the
  online smoke test and the isolated run.
- File upload step: `requests.post(url, files={"file": open(path, "rb")})`.

---

## Sub-Task 4 — Evidence Collection

**Status:** `[ ] pending`

**Intent:**
After a workflow run (pass or fail), collect structured evidence: container logs, failed step
details, and any detectable external hostname from the error output. Write this to a JSON evidence
file and a human-readable text report.

**Evidence strategy:**
- Container logs are the primary evidence source. Python's `sentence-transformers` library logs
  the download URL before attempting it. A ConnectionError traceback will contain the hostname.
- Parse logs for patterns: `huggingface.co`, `ConnectionError`, `socket.gaierror`,
  `requests.exceptions`, model download progress lines.
- Do NOT claim to detect the hostname if the pattern is not found in logs — report "hostname not
  detected from logs" instead.

**Expected Outcomes:**
- `egressproof/evidence.py` produces an `EvidenceBundle` with: container logs (raw), parsed
  suspicious patterns, failed steps, network policy description.
- `egressproof/reporter.py` writes a structured text report and a JSON file to `reports/`.
- Report file name: `reports/{timestamp}-{app-name}-{pass|fail}.txt` and `.json`.
- The text report matches the format shown in the project spec.

**Todo List:**
1. Create `egressproof/evidence.py`:
   - `collect_evidence(container_name, workflow_result, network_policy)`: fetches container logs,
     scans for suspicious patterns, returns `EvidenceBundle` dataclass.
   - Suspicious pattern list: `["huggingface.co", "ConnectionError", "socket.gaierror",
     "requests.exceptions.ConnectionError", "HTTPSConnectionPool", "No route to host",
     "Name or service not known"]`.
   - `EvidenceBundle` fields: container_logs, matched_patterns, failed_steps, network_policy,
     timestamp, app_name.
2. Create `egressproof/reporter.py`:
   - `write_report(evidence_bundle, output_dir)`: writes `.txt` and `.json` reports.
   - Text format: matches the spec — PASS/FAIL per step, matched patterns, result verdict.
   - JSON format: full EvidenceBundle as dict.
3. Create `reports/.gitkeep` so the directory is tracked.

**Relevant Context:**
- `get_container_logs(name)` from Sub-Task 2 provides the raw log string.
- Pattern matching is simple `substring in log_text` — no regex needed for MVP.
- The JSON report is what IBM Bob will be directed to read when diagnosing the failure.

---

## Sub-Task 5 — EgressProof CLI Orchestrator

**Status:** `[ ] pending`

**Intent:**
Wire all components into a single CLI command that drives the full end-to-end flow:
build → isolate → run workflow → collect evidence → report.

**Expected Outcomes:**
- `python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml` executes the
  full flow and prints a structured report.
- Exit code 0 for VERIFIED, non-zero for FAILED.
- The CLI also supports `--no-isolation` flag for the online smoke test (Sub-Task 1 validation).

**Todo List:**
1. Create `egressproof/__init__.py` and `egressproof/cli.py` using `argparse` or `click`:
   - Subcommand `run`:
     - `--app`: path to app directory containing Dockerfile.
     - `--workflow`: path to workflow YAML.
     - `--no-isolation`: skip network isolation (use for online smoke test).
     - `--keep`: don't tear down container after run (useful for debugging).
   - Orchestration sequence:
     a. Build Docker image (`docker build -t egressproof-app {app_dir}`).
     b. If isolation: create isolated network.
     c. Start container (isolated network or default bridge).
     d. Wait for /health.
     e. Run workflow.
     f. Collect evidence.
     g. Write report.
     h. Stop and remove container.
     i. If isolation: remove network.
     j. Print report path and summary.
     k. Exit with appropriate code.
2. Create `egressproof/builder.py`:
   - `build_image(app_dir, tag)`: runs `docker build -t {tag} {app_dir}`, streams output, raises
     on non-zero exit.
3. Create `__main__.py` at project root or `egressproof/__main__.py` for `python -m egressproof`.

**Relevant Context:**
- Keep error handling minimal but useful: if docker build fails, print stdout/stderr and exit.
- The isolation network name should be deterministic: `egressproof-isolated-{timestamp}` to avoid
  collisions if two runs happen simultaneously.

---

## Sub-Task 6 — Online Smoke Test (Pre-Isolation Baseline)

**Status:** `[ ] pending`

**Intent:**
Prove that the demo workflow succeeds with internet access before demonstrating the failure.
This is the "before" baseline that makes the failure meaningful.

**Expected Outcomes:**
- `python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml --no-isolation`
  completes with all three steps PASS.
- A `reports/baseline-pass.txt` file is committed to the repo as evidence.
- `tests/test_workflow_online.py` automates this verification.

**Todo List:**
1. Run the CLI with `--no-isolation` and confirm all steps pass.
2. Save the report output as `reports/baseline-pass.txt` (commit this as demo evidence).
3. Create `tests/test_workflow_online.py` — pytest test that runs the CLI subprocess and asserts
   exit code 0. Mark with `@pytest.mark.requires_internet`.

**Relevant Context:**
- This step requires internet access on the build machine — document this in README.
- The baseline report is important hackathon evidence.

---

## Sub-Task 7 — Isolated Run and Failure Report

**Status:** `[ ] pending`

**Intent:**
Run EgressProof with isolation enabled and confirm the expected failure. Capture the failure
report. This is the key "broken state" evidence for the hackathon demo.

**Expected Outcomes:**
- `python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml` (with isolation)
  produces a FAILED report.
- health step: PASS
- upload step: PASS
- ask-question step: FAIL
- Container logs contain `huggingface.co` or a connection error referencing the model download.
- Report saved to `reports/` and also committed as `reports/isolated-fail.txt` for demo evidence.

**Todo List:**
1. Run the CLI with isolation (default).
2. Confirm the three expected step outcomes.
3. Confirm log evidence contains a recognizable external dependency marker.
4. Save report as `reports/isolated-fail.txt`.
5. If the evidence is not detectable from logs alone, add explicit error logging to the demo app's
   /ask endpoint: catch the ConnectionError and log `f"EGRESS_BLOCKED: {e}"`.

**Relevant Context:**
- If `sentence-transformers` raises an exception that is not logged by default, the `/ask` endpoint
  must catch and re-raise after logging, so container logs always contain useful evidence.
- The `TRANSFORMERS_CACHE` env var should point to an empty directory inside the container
  (`/app/models`) so there is no possibility of a cached model being found.

---

## Sub-Task 8 — Bob Diagnosis and Repair Session

**Status:** `[ ] pending`

**Intent:**
Use IBM Bob in Agent mode to read the failure report, inspect the source code and Dockerfile, and
repair the application so the model is bundled into the Docker image at build time.

**This is the core Bob productivity demonstration.**

**Expected Outcomes:**
- Bob reads: `reports/isolated-fail.txt`, `demo-app/Dockerfile`, `demo-app/backend/main.py`,
  `demo-app/backend/requirements.txt`.
- Bob identifies: the model is loaded lazily at runtime and not baked into the image.
- Bob modifies `demo-app/Dockerfile` to add a build-time model download step:
  ```dockerfile
  RUN python -c "from sentence_transformers import SentenceTransformer; \
      SentenceTransformer('all-MiniLM-L6-v2')"
  ```
- Bob sets `ENV TRANSFORMERS_CACHE=/app/models` in the Dockerfile so the baked model is found
  at the same path at runtime.
- A Bob session summary screenshot is saved to `evidence/bob-session-summaries/`.

**Todo List:**
1. Open a Bob Agent mode session.
2. Provide Bob with the context prompt (see Prompt Template below).
3. Bob reads the listed files and proposes the Dockerfile fix.
4. Review and approve Bob's change.
5. Screenshot the Bob session showing the diagnosis reasoning and the diff applied.
6. Save screenshot to `evidence/bob-session-summaries/01-diagnosis-and-repair.png`.

**Bob Prompt Template (to use in Agent mode):**
```
Read reports/isolated-fail.txt, demo-app/Dockerfile, demo-app/backend/main.py,
and demo-app/backend/requirements.txt.

The application failed the 'ask-question' workflow step under network isolation.
The failure evidence is in the report.

Identify the root cause and modify demo-app/Dockerfile so that the application
no longer requires internet access during runtime to serve the /ask endpoint.
Do not change the application logic. Only change the packaging/build steps.
```

**Relevant Context:**
- Bob should apply the fix using `apply_diff` or `search_and_replace` on the Dockerfile.
- The fix is a one- or two-line addition to the Dockerfile — keep it minimal.
- ENV TRANSFORMERS_CACHE must be consistent between the build-time download and the runtime load.

---

## Sub-Task 9 — Rebuild and Re-Verification Run

**Status:** `[ ] pending`

**Intent:**
After Bob's repair, rebuild the image and re-run the exact same isolated workflow.
The result must be VERIFIED (all steps PASS under isolation).

**Expected Outcomes:**
- `python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml` (with isolation,
  after repair) exits 0.
- All three steps: PASS.
- Report saved as `reports/verified-pass.txt` and committed.
- The report shows "Unexpected external dependencies: 0" (or equivalent language based on what
  the log scanner actually found).

**Todo List:**
1. Re-run `python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml`.
2. Confirm all steps PASS.
3. Confirm no suspicious patterns in container logs.
4. Save report as `reports/verified-pass.txt`.
5. Screenshot the terminal output for hackathon evidence.
6. Save screenshot to `evidence/bob-session-summaries/02-verified-pass.png`.

---

## Sub-Task 10 — Tests, README, and Hackathon Polish

**Status:** `[ ] pending`

**Intent:**
Write the minimum tests needed to make the demo reproducible by judges, and write a README that
clearly explains the project and how to run the demo.

**Expected Outcomes:**
- `tests/test_isolation.py` — verifies that `create_isolated_network` + `start_isolated_container`
  produces a container that cannot reach the internet.
- `tests/test_workflow.py` — unit tests for `load_workflow` and `execute_step` with a mock server.
- `tests/test_reporter.py` — verifies report output format.
- `README.md` — prerequisites, quick-start, demo walkthrough, and architecture diagram (text-based).
- `pyproject.toml` or `setup.py` — makes `egressproof` installable as a package.

**Todo List:**
1. Write `tests/test_isolation.py` using subprocess to verify isolation behavior.
2. Write `tests/test_workflow.py` using `pytest-httpserver` or a simple mock.
3. Write `tests/test_reporter.py`.
4. Write `README.md` with: overview, prerequisites (Docker, Python 3.10+), quick-start commands,
   demo script, architecture section, Bob usage section, future extensions section.
5. Create `pyproject.toml` with package metadata and dependencies.

---

## Repository Structure

```
egressproof/
├── egressproof/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py           # CLI entry point and orchestration
│   ├── builder.py       # docker build wrapper
│   ├── isolation.py     # network creation/teardown, container lifecycle
│   ├── workflow.py      # YAML workflow loader and HTTP executor
│   ├── evidence.py      # log collection and pattern scanning
│   └── reporter.py      # text + JSON report writer
│
├── demo-app/
│   ├── backend/
│   │   ├── main.py
│   │   └── requirements.txt
│   ├── Dockerfile       # intentionally broken (no model bake-in) before Sub-Task 8
│   ├── docker-compose.yml
│   └── sample-data/
│       └── sample.txt
│
├── workflows/
│   └── document-qa.yaml
│
├── reports/
│   ├── .gitkeep
│   ├── baseline-pass.txt       # committed after Sub-Task 6
│   ├── isolated-fail.txt       # committed after Sub-Task 7
│   └── verified-pass.txt       # committed after Sub-Task 9
│
├── tests/
│   ├── test_local_app.py
│   ├── test_isolation.py
│   ├── test_workflow.py
│   └── test_reporter.py
│
├── evidence/
│   └── bob-session-summaries/
│       ├── 01-diagnosis-and-repair.png
│       └── 02-verified-pass.png
│
├── docs/
│   └── isolation-verification.md
│
├── pyproject.toml
└── README.md
```

---

## Bob Agent Usage Plan

| Sub-Task | Bob Role | Mode | Parallel? |
|---|---|---|---|
| 1 | Write LocalDocQA app | Agent | No — sequential build |
| 2 | Write isolation.py | Agent | Yes — parallel with Sub-Task 3 |
| 3 | Write workflow.py | Agent | Yes — parallel with Sub-Task 2 |
| 4 | Write evidence.py + reporter.py | Agent | No — depends on 2+3 design |
| 5 | Write cli.py orchestrator | Agent | No — depends on 1–4 |
| 6 | Online smoke test (manual run) | Agent (run commands) | No |
| 7 | Isolated failure run | Agent (run commands) | No |
| **8** | **Diagnose + repair (key Bob demo)** | **Agent** | **No — core demo** |
| 9 | Rebuild + verify | Agent (run commands) | No |
| 10 | Tests + README | Agent | Subtasks 10a/10b can be parallel |

**Sub-tasks 2 and 3 can be spawned as parallel Bob subagents** because `isolation.py` and
`workflow.py` have no dependencies on each other. This is a genuine productivity improvement and
worth demonstrating.

**Sub-task 8 (Bob diagnosis and repair) is the primary Bob productivity showcase.** It should be
done interactively in Agent mode so the reasoning is visible for screenshots.

---

## Acceptance Criteria by Milestone

| Milestone | Criterion |
|---|---|
| M1: Demo App | All three endpoints return 200 with internet access; POST /ask fails with connection error in logs when DNS is blocked |
| M2: Isolation | `docker network create --internal` verified to block outbound; runner reaches app via published port |
| M3: Workflow Runner | YAML workflow executes; each step result recorded; health poll works |
| M4: Evidence + Report | Failure report contains matched log patterns; JSON report parseable; text report matches spec format |
| M5: CLI | Single command drives full flow; clean teardown on success and failure |
| M6: Baseline | Online run exits 0; all steps PASS; baseline-pass.txt committed |
| M7: Failure | Isolated run exits non-zero; health+upload PASS, ask FAIL; isolated-fail.txt committed |
| M8: Bob Repair | Dockerfile modified by Bob; model baked into image; session screenshot captured |
| M9: Verified | Post-repair isolated run exits 0; all steps PASS; verified-pass.txt committed |
| M10: Polish | README complete; tests pass (online ones marked); repo ready for judges |

---

## Technical Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `sentence-transformers` caches model on host and mounts it into container | Medium | Set `TRANSFORMERS_CACHE=/app/models` (container-internal path only); never mount host cache |
| Model download error not visible in container logs | Low | Add explicit try/except in `/ask` endpoint that logs `EGRESS_BLOCKED: {exception}` |
| Docker internal network doesn't fully block DNS | Low | Test with `docker run --network egressproof-isolated alpine nslookup huggingface.co` and confirm NXDOMAIN or timeout |
| app starts but /health takes >30 s | Low | Use 60 s startup timeout; log each retry |
| Port collision on 8000 | Low | Make port configurable; default 8000 |
| Bob cannot find the root cause from logs alone | Very Low | Logs contain explicit error; Bob also reads the Dockerfile directly |

---

## Bob Session Summaries to Preserve

1. **01-diagnosis-and-repair** — Bob reading the failure report and Dockerfile, reasoning about
   the root cause, and applying the Dockerfile fix. This is the primary Bob productivity evidence.
2. **02-verified-pass** — Terminal output showing the post-repair isolated run passing all three
   steps. Demonstrates the full loop closed.
3. **03-parallel-subagents** (optional) — If Sub-tasks 2 and 3 are implemented with parallel
   Bob subagents, capture that session as evidence of parallel agent productivity.

---

## Future Extensions (Out of Scope for MVP)

- eBPF-based network telemetry for precise per-process egress capture
- Kubernetes NetworkPolicy enforcement testing
- Multi-step repair with dependency tree analysis
- Web dashboard for report visualization
- Support for docker-compose multi-service applications
- CI/CD integration (GitHub Actions workflow)
- Automatic dependency patching beyond Dockerfile model baking
