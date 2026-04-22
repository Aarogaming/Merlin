import argparse
import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from nats.aio.client import Client as NATS
    HAS_NATS = True
except ImportError:
    HAS_NATS = False


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from validate_agent_artifacts import validate_repo


logging.basicConfig(level=logging.INFO, format="[SPARK] %(message)s")
logger = logging.getLogger("spark")


def _resolve_paths() -> dict:
    workspace_root = Path(os.environ.get("AAS_WORKSPACE_ROOT", str(REPO_ROOT.parent))).resolve()
    agent_zero_root = Path(os.environ.get("AAS_AGENT_ZERO_ROOT", str(REPO_ROOT))).resolve()
    maelstrom_root = Path(os.environ.get("AAS_MAELSTROM_ROOT", str(workspace_root / "Maelstrom"))).resolve()
    nats_bin = Path(
        os.environ.get(
            "AAS_NATS_BIN",
            str(agent_zero_root / "nats" / "bin" / "nats-server.exe"),
        )
    ).resolve()
    config_path = Path(
        os.environ.get(
            "AAS_SPARK_CONFIG",
            str(agent_zero_root / "config" / "spark_config.json"),
        )
    ).resolve()
    vault_path = Path(
        os.environ.get(
            "AAS_VAULT_PATH",
            str(workspace_root / "MyFortress" / ".env"),
        )
    ).resolve()
    return {
        "workspace_root": workspace_root,
        "agent_zero_root": agent_zero_root,
        "maelstrom_root": maelstrom_root,
        "nats_bin": nats_bin,
        "config_path": config_path,
        "vault_path": vault_path,
    }


def _nats_target() -> tuple[str, int, str]:
    nats_url = os.environ.get("AAS_NATS_URL", "nats://localhost:4222")
    parsed = urlparse(nats_url)
    host = parsed.hostname or "localhost"
    port = int(parsed.port or 4222)
    return host, port, nats_url


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pct_to_unit(value: Any, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric > 1.0:
        numeric = numeric / 100.0
    return _clamp(numeric, 0.0, 1.0)


def load_runtime_spectrums() -> dict:
    epigenetics_path = REPO_ROOT / "genome" / "identity.epigenetics.json"
    fallback = {
        "autonomy_level": 3.0,
        "risk_tolerance": 0.35,
        "control_plane_write_aggression": 0.2,
        "delegation_bias": 0.5,
        "exploration_vs_stability": 0.45,
        "audit_strictness": 0.8,
    }
    if not epigenetics_path.exists():
        return fallback

    try:
        profile = json.loads(epigenetics_path.read_text(encoding="utf-8"))
    except Exception:
        return fallback

    if isinstance(profile.get("spectrums"), dict):
        spectrums = profile["spectrums"]
        return {
            "autonomy_level": _clamp(float(spectrums.get("autonomy_level", fallback["autonomy_level"])), 1.0, 5.0),
            "risk_tolerance": _pct_to_unit(spectrums.get("risk_tolerance"), fallback["risk_tolerance"]),
            "control_plane_write_aggression": _pct_to_unit(
                spectrums.get("control_plane_write_aggression"),
                fallback["control_plane_write_aggression"],
            ),
            "delegation_bias": _pct_to_unit(spectrums.get("delegation_bias"), fallback["delegation_bias"]),
            "exploration_vs_stability": _pct_to_unit(
                spectrums.get("exploration_vs_stability"),
                fallback["exploration_vs_stability"],
            ),
            "audit_strictness": _pct_to_unit(spectrums.get("audit_strictness"), fallback["audit_strictness"]),
        }

    cognitive_biases = profile.get("cognitive_biases", {}) if isinstance(profile, dict) else {}
    return {
        "autonomy_level": 3.0,
        "risk_tolerance": _pct_to_unit(cognitive_biases.get("risk_tolerance"), fallback["risk_tolerance"]),
        "control_plane_write_aggression": fallback["control_plane_write_aggression"],
        "delegation_bias": 0.5,
        "exploration_vs_stability": _pct_to_unit(
            cognitive_biases.get("exploration_vs_stability"),
            fallback["exploration_vs_stability"],
        ),
        "audit_strictness": _pct_to_unit(cognitive_biases.get("audit_strictness"), fallback["audit_strictness"]),
    }


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def ensure_nats_running(paths: dict) -> None:
    host, port, _ = _nats_target()
    if _is_port_open(host, port):
        logger.info(f"NATS already listening on {host}:{port}")
        return

    nats_bin = paths["nats_bin"]
    if not nats_bin.exists():
        raise FileNotFoundError(
            f"NATS binary not found: {nats_bin}. Set AAS_NATS_BIN to override."
        )

    logger.info(f"Starting NATS via {nats_bin}")
    subprocess.Popen(
        [str(nats_bin), "-js", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    time.sleep(2)
    if not _is_port_open(host, port):
        raise RuntimeError(f"NATS failed to start on {host}:{port}")


def run_preflight(clean_nats: bool, kill_python_listeners: bool) -> bool:
    try:
        from aas_kernel import AASKernel
    except ModuleNotFoundError as exc:
        logger.warning(f"Kernel preflight unavailable ({exc}). Continuing with Spark-only preflight.")
        return True

    kernel = AASKernel(repo_name=REPO_ROOT.name, repo_root=str(REPO_ROOT))
    return kernel.preflight(clean_nats=clean_nats, kill_python_listeners=kill_python_listeners)


def load_or_create_config(paths: dict, noninteractive: bool = False) -> dict:
    config_path = paths["config_path"]
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    default = {
        "llm_url": os.environ.get("AAS_LLM_URL", "http://127.0.0.1:11434/v1/chat/completions"),
        "llm_model": os.environ.get("AAS_LLM_MODEL", "llama3"),
        "requester": os.environ.get("AAS_REQUESTER", "spark"),
    }

    if noninteractive:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default

    print("\n=== Agent-Zero Spark Setup ===")
    llm_url = input(f"Local LLM URL [{default['llm_url']}]: ").strip() or default["llm_url"]
    llm_model = input(f"Model name [{default['llm_model']}]: ").strip() or default["llm_model"]
    requester = input(f"Requester identity [{default['requester']}]: ").strip() or default["requester"]
    cfg = {"llm_url": llm_url, "llm_model": llm_model, "requester": requester}
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def triage_subject_from_manifest() -> str:
    manifest_path = REPO_ROOT / "mcp-manifest.json"
    default_subject = "aaroneousautomationsuite.triage_user_request"
    if not manifest_path.exists():
        return default_subject
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for cap in manifest.get("capabilities", []):
            if cap.get("capability_id") == "aaroneousautomationsuite_triage_user_request":
                return str(cap.get("entry_point") or default_subject)
    except Exception:
        return default_subject
    return default_subject


def _keyword_score(text: str, words: list[str]) -> int:
    return sum(1 for w in words if w in text)


def build_interview_envelope(request_text: str, requester: str, spectrums: dict) -> dict:
    lowered = request_text.lower()
    words = [w for w in lowered.replace("\n", " ").split(" ") if w.strip()]

    sequence_signal = _keyword_score(lowered, [" then ", " after ", " before ", " sequence", " step", "first", "second", "finally"])
    parallel_signal = _keyword_score(lowered, [" across ", " parallel", " simultaneously", " in parallel", " and "])
    risk_signal = _keyword_score(lowered, ["delete", "drop", "prod", "production", "secret", "token", "credential", "billing", "security", "force"])
    ambiguity_signal = _keyword_score(lowered, ["something", "stuff", "it", "that", "this"]) + (1 if len(words) < 7 else 0)
    complexity_signal = max(0, len(words) // 12) + sequence_signal + parallel_signal

    mode = "single"
    if sequence_signal > 0 and parallel_signal > 0:
        mode = "sequential_parallel_spectrum"
    elif sequence_signal > 0:
        mode = "sequential"
    elif parallel_signal > 0:
        mode = "parallel"

    if mode == "single" and complexity_signal >= 3 and spectrums.get("delegation_bias", 0.5) >= 0.65:
        mode = "parallel"

    repo_keywords = {
        "MyFortress": ["security", "secret", "credential", "policy", "compliance"],
        "Maelstrom": ["ui", "ux", "screen", "visual", "screenshot", "frontend"],
        "Workbench": ["build", "test", "compile", "pipeline", "ci", "infra"],
        "Library": ["memory", "knowledge", "record", "query", "history"],
        "Guild": ["orchestrate", "dispatch", "workflow", "queue", "operation"],
        "Merlin": ["research", "analyze", "synthesize", "inference", "reason"],
    }
    repo_scores = {repo: _keyword_score(lowered, keys) for repo, keys in repo_keywords.items()}
    ranked = sorted(repo_scores.items(), key=lambda kv: kv[1], reverse=True)
    primary_repo = ranked[0][0] if ranked and ranked[0][1] > 0 else "Merlin"
    supporting_repos = [repo for repo, score in ranked[1:] if score > 0][:3]

    confidence = 0.8 - min(0.4, 0.08 * ambiguity_signal) - min(0.2, 0.05 * risk_signal)
    confidence = _clamp(confidence, 0.2, 0.95)

    clarification_depth = int(_clamp(round(1 + ambiguity_signal / 2 + risk_signal / 3), 1, 3))
    questions = []
    if ambiguity_signal > 0:
        questions.append("What concrete outcome should be considered success for this request?")
    if risk_signal > 0:
        questions.append("Does this request touch production, secrets, billing, or destructive operations?")
    if mode != "single":
        questions.append("Should execution prefer speed (parallel) or ordered safety (sequential)?")

    return {
        "trace_id": str(uuid.uuid4()),
        "requester": requester,
        "request": request_text,
        "interview": {
            "phase_sequence": ["discover", "clarify", "constrain", "plan", "dispatch"],
            "signals": {
                "sequence": sequence_signal,
                "parallel": parallel_signal,
                "risk": risk_signal,
                "ambiguity": ambiguity_signal,
                "complexity": complexity_signal,
            },
            "clarification_depth": clarification_depth,
            "questions": questions[:clarification_depth],
            "confidence": round(confidence, 3),
        },
        "routing_hint": {
            "execution_mode": mode,
            "primary_repo": primary_repo,
            "supporting_repos": supporting_repos,
        },
        "spectrums": spectrums,
    }


async def send_triage_request(payload: dict, timeout: float = 45.0) -> dict:
    if not HAS_NATS:
        return {"status": "error", "message": "nats-py is not installed."}

    _, _, nats_url = _nats_target()
    subject = triage_subject_from_manifest()

    nc = NATS()
    await nc.connect(nats_url, connect_timeout=5)
    try:
        reply = await nc.request(subject, json.dumps(payload).encode(), timeout=timeout)
        return json.loads(reply.data.decode())
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        await nc.close()


async def send_generic_capability_request(subject: str, payload: dict, timeout: float = 45.0) -> dict:
    if not HAS_NATS:
        return {"status": "error", "message": "nats-py is not installed."}

    _, _, nats_url = _nats_target()

    nc = NATS()
    await nc.connect(nats_url, connect_timeout=5)
    try:
        reply = await nc.request(subject, json.dumps(payload).encode(), timeout=timeout)
        return json.loads(reply.data.decode())
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        await nc.close()


def run_doctor(paths: dict) -> int:
    host, port, nats_url = _nats_target()
    report = {
        "paths": {
            "workspace_root": str(paths["workspace_root"]),
            "agent_zero_root": str(paths["agent_zero_root"]),
            "maelstrom_root": str(paths["maelstrom_root"]),
            "nats_bin": str(paths["nats_bin"]),
            "config_path": str(paths["config_path"]),
            "vault_path": str(paths["vault_path"]),
        },
        "runtime": {
            "nats_url": nats_url,
            "nats_port_open": _is_port_open(host, port),
            "has_nats_py": HAS_NATS,
        },
        "validation_errors": validate_repo(REPO_ROOT),
    }

    print(json.dumps(report, indent=2))
    return 1 if report["validation_errors"] else 0


async def interactive_loop(requester: str):
    spectrums = load_runtime_spectrums()
    print("\nSpark online. Type a request, or 'exit' to quit.")
    while True:
        prompt = await asyncio.get_event_loop().run_in_executor(None, input, "\n> ")
        if prompt.strip().lower() in {"exit", "quit"}:
            return
        if not prompt.strip():
            continue

        envelope = build_interview_envelope(prompt, requester=requester, spectrums=spectrums)
        answers = []
        for question in envelope.get("interview", {}).get("questions", []):
            answer = await asyncio.get_event_loop().run_in_executor(None, input, f"[clarify] {question}\n> ")
            if answer.strip():
                answers.append({"question": question, "answer": answer.strip()})
        if answers:
            envelope["interview"]["answers"] = answers
            clarifications = "\n".join([f"- {item['question']} => {item['answer']}" for item in answers])
            envelope["request"] = f"{prompt}\n\nClarifications:\n{clarifications}"

        response = await send_triage_request(envelope)
        print(json.dumps(response, indent=2))


def _request_from_file(path_str: str) -> str:
    path = Path(path_str).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Request file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Request file is empty: {path}")
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and data.get("request"):
                return str(data["request"])
        except json.JSONDecodeError:
            pass
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent-Zero Spark: preflight, diagnostics, and triage console.")
    parser.add_argument("--ignite-only", action="store_true", help="Ensure NATS is running, then exit.")
    parser.add_argument("--doctor", action="store_true", help="Run diagnostics and artifact validation.")
    parser.add_argument("--clean-nats", action="store_true", help="Use deep NATS cleanup during preflight.")
    parser.add_argument("--kill-python-listeners", action="store_true", help="Kill stale python listeners during preflight.")
    parser.add_argument("--noninteractive", action="store_true", help="Do not prompt for setup values.")
    parser.add_argument("--request", help="Single-shot user request for triage dispatch.")
    parser.add_argument("--request-file", help="Read request text from file (plain text or JSON with 'request').")
    parser.add_argument("--requester", default=None, help="Requester identity override.")
    parser.add_argument("--envelope-only", action="store_true", help="Print interview/routing envelope and skip dispatch.")
    parser.add_argument("--capability-id", help="Directly invoke a capability by its ID.")
    parser.add_argument("--subject", help="Directly publish to a NATS subject (overrides capability-id).")
    parser.add_argument("--payload", help="JSON payload for direct capability invocation.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = _resolve_paths()

    if args.doctor:
        return run_doctor(paths)

    try:
        if not run_preflight(args.clean_nats, args.kill_python_listeners):
            logger.warning("Kernel preflight reported instability.")
        ensure_nats_running(paths)
    except Exception as exc:
        logger.error(str(exc))
        return 1

    if args.ignite_only:
        logger.info("Ignition complete.")
        return 0

    config = load_or_create_config(paths, noninteractive=args.noninteractive)
    requester = args.requester or config.get("requester", "spark")
    spectrums = load_runtime_spectrums()

    request_text = args.request
    if not request_text and args.request_file:
        try:
            request_text = _request_from_file(args.request_file)
        except Exception as exc:
            logger.error(str(exc))
            return 1

    if args.request_text:
        envelope = build_interview_envelope(args.request_text, requester=requester, spectrums=spectrums)
        if args.envelope_only:
            print(json.dumps(envelope, indent=2))
            return 0

        response = asyncio.run(send_triage_request(envelope))
        print(json.dumps(response, indent=2))
        return 0 if response.get("status") == "success" else 1
    
    # New logic for direct capability invocation
    target_subject = None
    if args.subject:
        target_subject = args.subject
    elif args.capability_id:
        target_subject = args.capability_id.replace("_", ".")
    
    if target_subject and args.payload:
        try:
            payload_data = json.loads(args.payload)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
            return 1
        
        # Call a new function to send generic capability request
        response = asyncio.run(send_generic_capability_request(target_subject, payload_data))
        print(json.dumps(response, indent=2))
        return 0 if response.get("status") == "success" else 1

    try:
        asyncio.run(interactive_loop(requester=requester))
        return 0
    except KeyboardInterrupt:
        logger.info("Spark shutdown requested.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
