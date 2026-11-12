"""OnCall Agent dashboard: file-backed background jobs and explicit approvals."""
from __future__ import annotations
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import streamlit as st
from actions.approval import decide

st.set_page_config(page_title="OnCall Agent", page_icon="📟", layout="wide")
st.title("OnCall Agent")
st.caption("Investigate alerts, review evidence, and approve recovery actions.")


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def trace_rows(path):
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def job(command):
    directory = ROOT / "data/jobs"
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / f"{uuid.uuid4().hex}.log"
    with log.open("w") as file:
        child = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=file, stderr=file,
                                 start_new_session=True)
    st.session_state["job"] = {"pid": child.pid, "log": str(log)}
    return log


with st.sidebar:
    st.subheader("Lab controls")
    st.caption("These operator buttons change the demo service directly.")
    scenario = st.selectbox("Fault", ["bad_deploy", "pool_exhaustion", "memory_leak"])
    if st.button("Start healthy lab"):
        job(["scripts/devctl.py", "reset"])
    if st.button("Inject selected fault"):
        job(["scripts/devctl.py", "inject", scenario])
    if st.button("Reset to healthy"):
        job(["scripts/devctl.py", "reset"])
    if st.button("Stop lab"):
        job(["scripts/devctl.py", "down"])
    if st.session_state.get("job"):
        log = Path(st.session_state["job"]["log"])
        with st.expander("Latest operator job"):
            st.code(log.read_text()[-3000:] if log.exists() else "Starting…")

live, replay = st.tabs(["Investigations", "Recorded replay"])
with live:
    model = st.selectbox("Model", ["openai/gpt-oss-20b", "openai/gpt-oss-120b"])
    st.caption("Capture checks the measured 2-minute HTTP error rate. Wait for enough failing traffic after injection.")
    if st.button("Capture alert and investigate", type="primary"):
        job(["scripts/start_incident.py", "--model", model])
        st.success("Investigation started in the background. Refresh to see progress.")
    @st.fragment(run_every=3)
    def render_incidents():
        runs = sorted((ROOT / "runs").glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if runs:
            selected = st.selectbox("Incident", runs, format_func=lambda p: p.parent.name)
            directory = selected.parent
            metadata = read_json(selected) or {}
            st.write(f"**Status:** {metadata.get('status', 'starting')} · **Model:** {metadata.get('model', '')}")
            if metadata.get("error"):
                st.error(metadata["error"])
            for row in trace_rows(directory / "trace.jsonl"):
                kind = row["kind"]
                if kind == "plan":
                    st.caption("Model-written investigation plan")
                    st.info("Plan: " + " → ".join(row["steps"]) + "\n\n" + row["reason"])
                elif kind == "model":
                    st.caption(f"Model call {row['step'] + 1} · {'CACHED' if row['cached'] else 'LIVE'}")
                elif kind == "tool":
                    with st.expander(f"{row['tool_call_id']} · {row['name']} · read-only"):
                        st.json({"arguments": row["arguments"], "result": row["result"]})
                elif kind in {"waiting", "validation_error", "error"}:
                    st.warning(row.get("reason") or row.get("detail") or row.get("message"))
            report = read_json(directory / "report.json")
            if report:
                st.subheader("Incident report")
                st.write(report["summary"])
                st.write(f"**Likely cause:** {report['failure_type']} · {report['culprit']} · **Confidence:** {report['confidence']}")
                st.dataframe(report["timeline"], use_container_width=True)
                for item in report["evidence"]:
                    st.code(f"{item['tool_call_id']}: {item['quote']}")
                st.write("Next steps: " + "; ".join(report["next_steps"]))
                st.download_button("Download report", json.dumps(report, indent=2), file_name="incident-report.json")
                actor = st.text_input("Human approver", value="aman01k")
                can_approve = (metadata.get("status") == "completed" and metadata.get("mode") == "agent"
                               and report.get("failure_type") != "unknown"
                               and Path(metadata.get("source", "/")).resolve().is_relative_to(ROOT / "data/snapshots"))
                captured = read_json(Path(metadata.get("source", "/")) / "deployment-state.json") or {}
                st.caption("Captured release: " + captured.get("version", "unknown"))
                deployments = read_json(ROOT / "data/deploys.json") or []
                current = deployments[-1] if deployments else {}
                same_deployment = bool(captured.get("id") == current.get("id") and captured.get("sha") == current.get("sha"))
                for index, action in enumerate(report.get("proposed_actions", [])):
                    st.write(f"**Proposed {action['kind']}** → {action.get('target') or 'current release'}: {action['reason']}")
                    decision = read_json(directory / f"decision-{index}.json")
                    if decision:
                        st.json(decision)
                        continue
                    if not can_approve or not same_deployment:
                        st.caption("Remediation disabled: this is an evaluation, incomplete report or an older deployment. Capture a new incident before further actions.")
                        continue
                    a, b = st.columns(2)
                    for column, label, approval in [(a, "Approve and execute", True), (b, "Reject", False)]:
                        if column.button(label, key=f"{directory.name}-{index}-{approval}"):
                            try:
                                with st.spinner("Recording decision and checking recovery…"):
                                    st.json(decide(directory, index, approval, actor))
                            except (OSError, ValueError) as exc:
                                st.error(str(exc))

        else:
            st.info("No investigations yet. Inject a fault, then capture an alert.")
        st.button("Refresh progress")
    render_incidents()

with replay:
    recordings = sorted((ROOT / "traces/recorded").glob("*/run.json"))
    if recordings:
        recording = st.selectbox("Recording", recordings, format_func=lambda p: p.parent.name)
        meta = read_json(recording) or {}
        st.warning(f"REPLAY · recorded {meta.get('started_at', '')} · model {meta.get('model', '')}. No remediation controls.")
        for row in trace_rows(recording.parent / "trace.jsonl"):
            if row["kind"] in {"plan", "tool", "report", "approval", "action_result"}:
                with st.expander(row["kind"] + " · " + row.get("name", row.get("ts", ""))):
                    st.json(row)
    else:
        st.info("No recorded investigation yet. Recordings will appear after the first validated run.")
