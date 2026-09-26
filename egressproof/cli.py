"""
EgressProof CLI — orchestrates the full detect → isolate → run → report loop.

Usage:
    python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml
    python -m egressproof run --app demo-app --workflow workflows/document-qa.yaml --no-isolation
"""

from __future__ import annotations

import argparse
import io
import sys
import time

# On Windows the default stdout encoding (cp1252) can't handle certain Unicode
# characters in report text.  Wrap stdout in a UTF-8 writer when needed.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from egressproof.builder import build_image
from egressproof.evidence import collect_evidence
from egressproof.isolation import (
    create_isolated_network,
    get_container_logs,
    remove_isolated_network,
    start_container,
    start_isolated_container,
    stop_and_remove_container,
)
from egressproof.reporter import format_text_report, write_report
from egressproof.workflow import load_workflow, run_workflow

IMAGE_TAG = "egressproof-localdocqa"
CONTAINER_NAME = "egressproof-app"
APP_PORT = 8000


def _run(args: argparse.Namespace) -> int:
    """Execute the full EgressProof flow.  Returns exit code."""
    isolation = not args.no_isolation
    network_policy = "External egress blocked" if isolation else "Full internet access (no isolation)"
    network_name = f"egressproof-isolated-{int(time.time())}"
    base_url = f"http://localhost:{APP_PORT}"

    # ── 1. Build image ────────────────────────────────────────────────────────
    try:
        build_image(args.app, IMAGE_TAG)
    except RuntimeError as exc:
        print(f"\n[egressproof] ERROR: {exc}", file=sys.stderr)
        return 2

    # ── 2. Create isolated network (if needed) ────────────────────────────────
    if isolation:
        print(f"\n[egressproof] Creating isolated network '{network_name}' ...")
        try:
            create_isolated_network(network_name)
        except RuntimeError as exc:
            print(f"\n[egressproof] ERROR: {exc}", file=sys.stderr)
            return 2

    # ── 3. Start container ────────────────────────────────────────────────────
    print(f"\n[egressproof] Starting container '{CONTAINER_NAME}' on port {APP_PORT} ...")
    try:
        if isolation:
            start_isolated_container(IMAGE_TAG, network_name, APP_PORT, CONTAINER_NAME)
        else:
            start_container(IMAGE_TAG, APP_PORT, CONTAINER_NAME)
    except RuntimeError as exc:
        print(f"\n[egressproof] ERROR: Failed to start container: {exc}", file=sys.stderr)
        _cleanup(isolation, network_name, keep=False)
        return 2

    # ── 4. Run workflow ───────────────────────────────────────────────────────
    workflow_result = None
    try:
        workflow = load_workflow(args.workflow)
        workflow_result = run_workflow(workflow, base_url)
    except RuntimeError as exc:
        print(f"\n[egressproof] ERROR: Workflow execution failed: {exc}", file=sys.stderr)
        # Fall through to evidence collection even on startup timeout
    except Exception as exc:  # noqa: BLE001
        print(f"\n[egressproof] ERROR: Unexpected error: {exc}", file=sys.stderr)

    # ── 5. Collect evidence ───────────────────────────────────────────────────
    if workflow_result is not None:
        bundle = collect_evidence(
            container_name=CONTAINER_NAME,
            workflow_result=workflow_result,
            network_policy=network_policy,
            app_name="LocalDocQA",
        )
    else:
        # Workflow never ran — print raw logs and exit
        print("\n[egressproof] Container logs:")
        print(get_container_logs(CONTAINER_NAME))
        _cleanup(isolation, network_name, keep=args.keep)
        return 2

    # ── 6. Write report ───────────────────────────────────────────────────────
    txt_path, json_path = write_report(bundle, output_dir="reports")
    report_text = format_text_report(bundle)
    print("\n" + report_text)
    print(f"\n[egressproof] Reports written:")
    print(f"  Text : {txt_path}")
    print(f"  JSON : {json_path}")

    # ── 7. Teardown ───────────────────────────────────────────────────────────
    _cleanup(isolation, network_name, keep=args.keep)

    return 0 if bundle.passed else 1


def _cleanup(isolation: bool, network_name: str, keep: bool) -> None:
    """Stop container and remove network unless --keep was passed."""
    if keep:
        print(f"\n[egressproof] --keep flag set; leaving container '{CONTAINER_NAME}' running.")
        return
    print(f"\n[egressproof] Stopping and removing container '{CONTAINER_NAME}' ...")
    stop_and_remove_container(CONTAINER_NAME)
    if isolation:
        print(f"[egressproof] Removing network '{network_name}' ...")
        remove_isolated_network(network_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="egressproof",
        description="Detect hidden runtime internet dependencies in Dockerized applications.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full EgressProof verification loop.")
    run_parser.add_argument(
        "--app",
        required=True,
        help="Path to the application directory containing a Dockerfile.",
    )
    run_parser.add_argument(
        "--workflow",
        required=True,
        help="Path to the workflow YAML file.",
    )
    run_parser.add_argument(
        "--no-isolation",
        action="store_true",
        default=False,
        help="Skip network isolation (use for online smoke test / baseline).",
    )
    run_parser.add_argument(
        "--keep",
        action="store_true",
        default=False,
        help="Do not stop/remove the container after the run (useful for debugging).",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        return _run(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
