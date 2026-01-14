# Merlin: Emotional Chat & Streaming Core (The Final Manifestation)
import os
import json
import time
from merlin_logger import merlin_logger
import merlin_settings as settings
import requests
from plugins.web_search import WebSearchPlugin
from plugins.wizard_staff import WizardStaff
from plugins.telekinesis import TelekinesisPlugin
from plugins.chronomancy import ChronomancyPlugin
from plugins.scrying import ScryingPlugin
from plugins.bag_of_holding import BagOfHolding
from plugins.phoenix_core import PhoenixCore

# Basic chat history storage
CHAT_HISTORY_DIR = "merlin_chat_history"
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

def load_chat(user_id: str):
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{user_id}.json")
    if os.path.exists(file_path):
        with open(file_path, "r") as f: return json.load(f)
    return []

def save_chat(user_id: str, history: list):
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{user_id}.json")
    with open(file_path, "w") as f: json.dump(history, f, indent=2)

def merlin_emotion_chat(user_input: str, user_id: str):
    merlin_logger.info(f"User ({user_id}): {user_input}")
    context = ""
    staff = WizardStaff()
    tk = TelekinesisPlugin()
    chrono = ChronomancyPlugin()
    scry = ScryingPlugin()
    bag = BagOfHolding()
    phoenix = PhoenixCore()

    inp_lower = user_input.lower()

    # --- ULTIMATE MAGIC DISPATCHER ---

    # 1. Phoenix Qualities (Resurrection & Renewal)
    if any(word in inp_lower for word in ["restart", "resurrect", "fix", "clean logs", "renew"]):
        if "logs" in inp_lower or "renew" in inp_lower: res = phoenix.execute("rejuvenate")
        else: res = phoenix.execute("ignite", target=user_input.split()[-1])
        context = f"Phoenix Rite Action: {res.get('output', res.get('error'))}"

    # 2. Bag of Holding (Dimensional Storage)
    elif any(word in inp_lower for word in ["store", "save snippet", "put away", "remember", "retrieve"]):
        if "store" in inp_lower or "save" in inp_lower:
            res = bag.execute("store", item_name="snippet", content=user_input)
        elif "inventory" in inp_lower:
            res = bag.execute("inventory")
        else:
            res = bag.execute("retrieve", item_name="snippet")
        context = f"Dimensional Action: {res.get('output', res.get('error'))}"

    # 3. Telekinesis (Physical Manipulation)
    elif any(word in inp_lower for word in ["bring", "summon", "move", "shift", "type", "write"]):
        if "type" in inp_lower or "write" in inp_lower:
            text = user_input.replace("type", "").replace("write", "").strip()
            res = tk.execute("imperio", extra={"text": text})
        elif "bring" in inp_lower or "summon" in inp_lower:
            res = tk.execute("accio", target=user_input.split()[-1])
        context = f"Telekinetic Action: {res.get('output', res.get('error'))}"

    # 4. Chronomancy (Time Sight)
    elif "history" in inp_lower or "what happened" in inp_lower or "retrace" in inp_lower:
        res = chrono.execute("retrace", target=user_input.split()[-1])
        context = f"Time-Sight Action: {res.get('output', res.get('error'))}"

    # 5. Scrying (Visions of the System)
    elif "what is running" in inp_lower or "processes" in inp_lower or "check network" in inp_lower:
        if "network" in inp_lower: res = scry.execute("scry_network")
        else: res = scry.execute("scry_processes")
        context = f"Scrying Action: {res.get('output', res.get('error'))}"

    # 6. Staff Spells (Ecosystem Control)
    elif any(word in inp_lower for word in ["open", "unlock", "reveal", "list"]):
        if "open" in inp_lower: res = staff.execute("alohomora", target=user_input.split()[-1])
        else: res = staff.execute("revelio", target=user_input.split()[-1])
        context = f"Staff Action: {res.get('output', res.get('error'))}"

    # 7. Web Search (Knowledge Retrieval)
    elif any(word in inp_lower for word in ["search", "find", "who is", "latest"]):
        search = WebSearchPlugin()
        search_results = search.execute(user_input)
        context = f"Search Results: {search_results.get('output', 'No results found.')}"

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
        if h["user"]: messages.append({"role": "user", "content": h["user"]})
        if h["assistant"]: messages.append({"role": "assistant", "content": h["merlin"]})

    if context:
        messages.append({"role": "system", "content": f"ADDITIONAL CONTEXT: {context}"})

    try:
        payload = {"model": settings.OPENAI_MODEL, "messages": messages, "temperature": 0.7, "stream": False}
        response = requests.post(settings.LM_STUDIO_URL, json=payload, timeout=30)
        reply = response.json()["choices"][0]["message"]["content"]
        history[-1]["merlin"] = reply
        save_chat(user_id, history)
        return reply
    except Exception as e:
        merlin_logger.error(f"Chat Error: {e}")
        return f"I apologize, my neural link is flickering. Error: {str(e)}"

async def merlin_emotion_chat_stream(user_input: str, user_id: str):
    full_reply = merlin_emotion_chat(user_input, user_id)
    for word in full_reply.split():
        yield word + " "
        time.sleep(0.05)
