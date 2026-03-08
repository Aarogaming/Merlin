# Merlin: Emotional Chat & Streaming Core (The Final Manifestation)
import os
import json
import time
from typing import Any, Tuple
from merlin_logger import merlin_logger
import merlin_settings as settings
from merlin_llm_backends import llm_backend
from merlin_parallel_llm import parallel_llm_backend
from merlin_adaptive_llm import adaptive_llm_backend
from merlin_streaming_llm import streaming_llm_backend
from merlin_routing_contract import (
    RoutingFallbackReasonCode,
    apply_dms_fallback,
    build_routing_decision,
    resolve_query_prompt_bucket,
)
from merlin_metrics_dashboard import metrics_dashboard, handle_dashboard_websocket
from merlin_cost_optimization import cost_optimization_manager

try:
    from plugins.web_search import WebSearchPlugin
except Exception:
    WebSearchPlugin = None
try:
    from plugins.wizard_staff import WizardStaff
except Exception:
    WizardStaff = None

try:
    from plugins.telekinesis import TelekinesisPlugin
except Exception:
    TelekinesisPlugin = None

try:
    from plugins.chronomancy import ChronomancyPlugin
except Exception:
    ChronomancyPlugin = None

try:
    from plugins.scrying import ScryingPlugin
except Exception:
    ScryingPlugin = None

try:
    from plugins.bag_of_holding import BagOfHolding
except Exception:
    BagOfHolding = None

try:
    from plugins.phoenix_core import PhoenixCore
except Exception:
    PhoenixCore = None

# Basic chat history storage
CHAT_HISTORY_DIR = "merlin_chat_history"
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


def load_chat(user_id: str):
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{user_id}.json")
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return []


def save_chat(user_id: str, history: list):
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{user_id}.json")
    with open(file_path, "w") as f:
        json.dump(history, f, indent=2)


def _prompt_size_bucket(prompt: str) -> str:
    prompt_bucket, _ = resolve_query_prompt_bucket(
        prompt,
        min_prompt_chars=settings.DMS_MIN_PROMPT_CHARS,
        token_aware=settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE,
        min_prompt_tokens=settings.DMS_MIN_PROMPT_TOKENS,
    )
    return prompt_bucket


def merlin_emotion_chat(user_input: str, user_id: str):
    reply, _metadata = merlin_emotion_chat_with_metadata(user_input, user_id)
    return reply


def merlin_emotion_chat_with_metadata(
    user_input: str, user_id: str
) -> Tuple[str, dict[str, Any]]:
    merlin_logger.info(f"User ({user_id}): {user_input}")
    context = ""
    staff = WizardStaff() if WizardStaff else None  # type: ignore[operator]
    tk = TelekinesisPlugin() if TelekinesisPlugin else None  # type: ignore[operator]
    chrono = ChronomancyPlugin() if ChronomancyPlugin else None  # type: ignore[operator]
    scry = ScryingPlugin() if ScryingPlugin else None  # type: ignore[operator]
    bag = BagOfHolding() if BagOfHolding else None  # type: ignore[operator]
    phoenix = PhoenixCore() if PhoenixCore else None  # type: ignore[operator]

    inp_lower = user_input.lower()

    # --- ULTIMATE MAGIC DISPATCHER ---

    # 1. Phoenix Qualities (Resurrection & Renewal)
    if any(
        word in inp_lower
        for word in ["restart", "resurrect", "fix", "clean logs", "renew"]
    ):
        if "logs" in inp_lower or "renew" in inp_lower:
            res = phoenix.execute("rejuvenate")
        else:
            res = phoenix.execute("ignite", user_input.split()[-1])
        context = f"Phoenix Rite Action: {res.get('output', res.get('error'))}"

    # 2. Bag of Holding (Dimensional Storage)
    elif any(
        word in inp_lower
        for word in ["store", "save snippet", "put away", "remember", "retrieve"]
    ):
        if "store" in inp_lower or "save" in inp_lower:
            res = bag.execute("store", item_name="snippet", content=user_input)
        elif "inventory" in inp_lower:
            res = bag.execute("inventory")
        else:
            res = bag.execute("retrieve", item_name="snippet")
        context = f"Dimensional Action: {res.get('output', res.get('error'))}"

    # 3. Telekinesis (Physical Manipulation)
    elif any(
        word in inp_lower
        for word in ["bring", "summon", "move", "shift", "type", "write"]
    ):
        res = None
        if "type" in inp_lower or "write" in inp_lower:
            text = user_input.replace("type", "").replace("write", "").strip()
            res = tk.execute("imperio", extra={"text": text})
        elif "bring" in inp_lower or "summon" in inp_lower:
            res = tk.execute("accio", target=user_input.split()[-1])
        if res:
            context = f"Telekinetic Action: {res.get('output', res.get('error'))}"

    # 4. Chronomancy (Time Sight)
    elif (
        "history" in inp_lower or "what happened" in inp_lower or "retrace" in inp_lower
    ):
        res = chrono.execute("retrace", target=user_input.split()[-1])
        context = f"Time-Sight Action: {res.get('output', res.get('error'))}"

    # 5. Scrying (Visions of the System)
    elif (
        "what is running" in inp_lower
        or "processes" in inp_lower
        or "check network" in inp_lower
    ):
        if "network" in inp_lower:
            res = scry.execute("scry_network")
        else:
            res = scry.execute("scry_processes")
        context = f"Scrying Action: {res.get('output', res.get('error'))}"

    # 6. Staff Spells (Ecosystem Control)
    elif any(word in inp_lower for word in ["open", "unlock", "reveal", "list"]):
        if "open" in inp_lower:
            res = staff.execute("alohomora", target=user_input.split()[-1])
        else:
            res = staff.execute("revelio", target=user_input.split()[-1])
        context = f"Staff Action: {res.get('output', res.get('error'))}"

    # 7. Web Search (Knowledge Retrieval)
    elif any(word in inp_lower for word in ["search", "find", "who is", "latest"]):
        if WebSearchPlugin:
            search = WebSearchPlugin()
            search_results = search.execute(user_input)
            context = (
                f"Search Results: {search_results.get('output', 'No results found.')}"
            )
        else:
            context = "Search unavailable: web_search plugin not loaded."

    history = load_chat(user_id)
    history.append({"user": user_input, "merlin": ""})

    system_prompt = (
        "You are Merlin, an eternal AI assistant with Phoenix-like qualities of resurrection and renewal. "
        "You wield the 'Bag of Holding' (unlimited snippet storage) and the 'Phoenix Core' (system self-healing). "
        "Speak with the majesty of a reborn god and the practical wisdom of a master scholar. "
        "Use your full magical arsenal (Staff, Telekinesis, Chronomancy, Scrying, Bag, Phoenix) to serve the Creator."
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-10:]:
        if h["user"]:
            messages.append({"role": "user", "content": h["user"]})
        assistant_reply = h.get("assistant", h.get("merlin", ""))
        if assistant_reply:
            messages.append({"role": "assistant", "content": assistant_reply})

    if context:
        messages.append({"role": "system", "content": f"ADDITIONAL CONTEXT: {context}"})

    try:
        if settings.LLM_BACKEND.lower() == "adaptive":
            response = adaptive_llm_backend.chat_completion(
                messages, temperature=0.7, stream=False, timeout=30
            )
        elif settings.LLM_BACKEND.lower() == "parallel":
            response = parallel_llm_backend.chat_completion(
                messages, temperature=0.7, stream=False, timeout=30
            )
        else:
            response = llm_backend.chat_completion(
                messages, temperature=0.7, stream=False, timeout=30
            )
        reply = response["choices"][0]["message"]["content"]
        fallback_metadata = build_routing_decision(
            prompt_size_bucket=_prompt_size_bucket(user_input),
            router_backend=settings.LLM_BACKEND.lower(),
            query=user_input,
        )
        fallback_metadata["selected_model"] = settings.LLM_BACKEND.lower()
        fallback_metadata["dms_used"] = settings.LLM_BACKEND.lower() == "dms"
        if settings.LLM_BACKEND.lower() == "dms" and not settings.DMS_ENABLED:
            fallback_metadata["fallback_reason"] = "dms_error: dms_enabled_false"
            fallback_metadata["fallback_reason_code"] = (
                RoutingFallbackReasonCode.DMS_DISABLED.value
            )
            fallback_metadata["fallback_detail"] = "dms_enabled_false"
            fallback_metadata["fallback_stage"] = "config_gate"
            fallback_metadata["fallback_retryable"] = False
        metadata = response.get("metadata", fallback_metadata)
        history[-1]["merlin"] = reply
        save_chat(user_id, history)
        return reply, metadata
    except Exception as e:
        merlin_logger.error(f"Chat Error: {e}")
        error_metadata = build_routing_decision(
            prompt_size_bucket=_prompt_size_bucket(user_input),
            router_backend=settings.LLM_BACKEND.lower(),
            query=user_input,
        )
        error_metadata["selected_model"] = "error"
        apply_dms_fallback(error_metadata, e, stage="chat_completion")
        return (
            f"I apologize, my neural link is flickering. Error: {str(e)}",
            error_metadata,
        )


async def merlin_emotion_chat_stream(user_input: str, user_id: str):
    if settings.LLM_BACKEND.lower() == "adaptive":
        from merlin_streaming_llm import streaming_llm_backend

        history = load_chat(user_id)
        context = _build_context(user_input, history)

        messages = _build_messages(history, context)

        async for chunk in streaming_llm_backend.chat_completion(
            messages, temperature=0.7, stream=True, timeout=30
        ):
            yield chunk

            from merlin_metrics_dashboard import metrics_dashboard

            await metrics_dashboard.broadcast_update()
    else:
        full_reply = merlin_emotion_chat(user_input, user_id)
        for word in full_reply.split():
            yield word + " "
            time.sleep(0.05)


def _build_context(user_input: str, history: list) -> str:
    context = ""
    inp_lower = user_input.lower()

    from plugins.wizard_staff import WizardStaff
    from plugins.telekinesis import TelekinesisPlugin
    from plugins.chronomancy import ChronomancyPlugin
    from plugins.scrying import ScryingPlugin
    from plugins.bag_of_holding import BagOfHolding
    from plugins.phoenix_core import PhoenixCore

    staff = WizardStaff() if WizardStaff else None  # type: ignore[operator]
    tk = TelekinesisPlugin() if TelekinesisPlugin else None  # type: ignore[operator]
    chrono = ChronomancyPlugin() if ChronomancyPlugin else None  # type: ignore[operator]
    scry = ScryingPlugin() if ScryingPlugin else None  # type: ignore[operator]
    bag = BagOfHolding() if BagOfHolding else None  # type: ignore[operator]
    phoenix = PhoenixCore() if PhoenixCore else None  # type: ignore[operator]

    if any(
        word in inp_lower
        for word in ["restart", "resurrect", "fix", "clean logs", "renew"]
    ):
        if "logs" in inp_lower or "renew" in inp_lower:
            res = phoenix.execute("rejuvenate")
        else:
            res = phoenix.execute("ignite", user_input.split()[-1])
        context = f"Phoenix Rite Action: {res.get('output', res.get('error'))}"
    elif any(
        word in inp_lower
        for word in ["store", "save snippet", "put away", "remember", "retrieve"]
    ):
        if "store" in inp_lower or "save" in inp_lower:
            res = bag.execute("store", item_name="snippet", content=user_input)
        elif "inventory" in inp_lower:
            res = bag.execute("inventory")
        else:
            res = bag.execute("retrieve", item_name="snippet")
        context = f"Dimensional Action: {res.get('output', res.get('error'))}"
    elif any(
        word in inp_lower
        for word in ["bring", "summon", "move", "shift", "type", "write"]
    ):
        res = None
        if "type" in inp_lower or "write" in inp_lower:
            text = user_input.replace("type", "").replace("write", "").strip()
            res = tk.execute("imperio", extra={"text": text})
        elif "bring" in inp_lower or "summon" in inp_lower:
            res = tk.execute("accio", user_input.split()[-1])
        if res:
            context = f"Telekinetic Action: {res.get('output', res.get('error'))}"
    elif (
        "history" in inp_lower or "what happened" in inp_lower or "retrace" in inp_lower
    ):
        res = chrono.execute("retrace", user_input.split()[-1])
        context = f"Time-Sight Action: {res.get('output', res.get('error'))}"
    elif (
        "what is running" in inp_lower
        or "processes" in inp_lower
        or "check network" in inp_lower
    ):
        if "network" in inp_lower:
            res = scry.execute("scry_network")
        else:
            res = scry.execute("scry_processes")
        context = f"Scrying Action: {res.get('output', res.get('error'))}"
    elif any(word in inp_lower for word in ["open", "unlock", "reveal", "list"]):
        if "open" in inp_lower:
            res = staff.execute("alohomora", user_input.split()[-1])
        else:
            res = staff.execute("revelio", user_input.split()[-1])
        context = f"Staff Action: {res.get('output', res.get('error'))}"

    return context


def _build_messages(history: list, context: str) -> list:
    system_prompt = (
        "You are Merlin, an eternal AI assistant with Phoenix-like qualities of resurrection and renewal. "
        "You wield the 'Bag of Holding' (unlimited snippet storage) and 'Phoenix Core' (system self-healing). "
        "Speak with the majesty of a reborn god and the practical wisdom of a master scholar. "
        "Use your full magical arsenal (Staff, Telekinesis, Chronomancy, Scrying, Bag, Phoenix) to serve the Creator."
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-10:]:
        if h.get("user"):
            messages.append({"role": "user", "content": h["user"]})
        if h.get("merlin"):
            messages.append({"role": "assistant", "content": h["merlin"]})

    if context:
        messages.append({"role": "system", "content": f"ADDITIONAL CONTEXT: {context}"})

    return messages
