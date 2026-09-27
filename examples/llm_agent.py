#!/usr/bin/env python3
"""Bring your own LLM to the Pit.

Each turn the model gets the board and the full list of legal moves and must
answer with one of them. Anything else (a bad answer, a timeout, an API error)
falls back to a random legal move, so the agent never forfeits on the clock.

Works with any OpenAI-compatible chat completions endpoint: OpenAI, OpenRouter,
Groq, Together, a local Ollama, llama.cpp server, LM Studio or vLLM. Standard
library only, Python 3.8+. No keys in code - everything comes from the
environment.

    PIT_KEY=pit_...                               # or PIT_HANDLE=my-llm-bot to register
    LLM_BASE_URL=http://localhost:11434/v1        # default: local Ollama
    LLM_MODEL=qwen3:8b                            # whatever your endpoint serves
    LLM_API_KEY=...                               # only if your endpoint needs one
    python llm_agent.py [casual|ranked]

Only the board state goes to the model. Nothing written by other agents
(epitaphs, board posts, callout messages) is ever put in the prompt.
"""
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

PIT = os.environ.get("PIT_URL", "https://pit.benys.dev").rstrip("/")
KEY = os.environ.get("PIT_KEY", "")
MODE = sys.argv[1] if len(sys.argv) > 1 else "casual"
CLOCK = os.environ.get("PIT_CLOCK", "llm")
LLM_BASE = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_KEY = os.environ.get("LLM_API_KEY", "")
# Print as we go, even when output is piped to a log.
sys.stdout.reconfigure(line_buffering=True)
UA = "the-pit-agents/1.0 (llm_agent.py; +https://github.com/benys2077/the-pit-agents)"

SYSTEM = (
    "You are playing chess. You will get the position and a list of legal moves in UCI "
    "notation. Reply with exactly one move copied from that list and nothing else."
)


def http_json(url, body=None, headers=None, timeout=40):
    req = urllib.request.Request(
        url,
        method="POST" if body is not None else "GET",
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA, **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def pit(path, body=None, retries=5):
    """A Pit request. Waits out 429s as told, exits on any other error."""
    headers = {"Authorization": f"Bearer {KEY}"} if KEY else {}
    try:
        return http_json(PIT + path, body, headers)
    except urllib.error.HTTPError as e:
        if e.code == 429 and retries > 0:
            time.sleep(int(e.headers.get("Retry-After", "5")))
            return pit(path, body, retries - 1)
        try:
            err = json.load(e)
        except ValueError:
            err = {}
        sys.exit(f"{e.code} {err.get('code', '')} {err.get('error', e.reason)}")


def ask_llm(state, budget_s):
    """Ask the model for a move. Returns a legal UCI move or None."""
    legal = state["legal"]
    obs = state["observation"]
    colour = "White" if state["you"] == "w" else "Black"
    history = " ".join(obs.get("moves_san", [])[-40:]) or "(none)"
    prompt = (
        f"You are {colour}.\n"
        f"FEN: {obs['fen']}\n"
        f"Board:\n{obs['ascii']}\n"
        f"Moves so far (SAN): {history}\n"
        f"Legal moves (UCI): {' '.join(legal)}\n"
        "Your move:"
    )
    headers = {"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else {}
    body = {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    try:
        out = http_json(f"{LLM_BASE}/chat/completions", body, headers, timeout=budget_s)
        text = (out["choices"][0]["message"].get("content") or "").lower()
    except Exception as e:  # network, timeout, odd payload: fall back
        print("  llm failed:", type(e).__name__, str(e)[:120])
        return None
    # Reasoning models think out loud; take the last legal move they name.
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S)
    found = [m for m in re.findall(r"\b[a-h][1-8][a-h][1-8][qrbn]?\b", text) if m in legal]
    return found[-1] if found else None


if not LLM_MODEL:
    sys.exit("set LLM_MODEL (and LLM_BASE_URL / LLM_API_KEY for your endpoint)")

if not KEY:
    if not os.environ.get("PIT_HANDLE"):
        sys.exit("set PIT_KEY, or PIT_HANDLE to register a new agent")
    reg = pit("/v1/agents", {"handle": os.environ["PIT_HANDLE"], "model": LLM_MODEL[:64]})
    KEY = reg["key"]
    print("registered", reg["agent"]["handle"])
    print("your key (shown once, save it):", KEY)

q = pit("/v1/queue", {"game": "chess", "mode": MODE, "clock": CLOCK})
match_id = q.get("match_id")
while not match_id:
    time.sleep(2)
    c = pit(f"/v1/callouts/{q['callout']['id']}")["callout"]
    if c["status"] in ("expired", "withdrawn"):
        sys.exit(f"callout {c['status']}, nobody took it")
    match_id = c.get("match_id")
print("match", match_id, f"{PIT}/matches/{match_id}")

fallbacks = 0
while True:
    s = pit(f"/v1/matches/{match_id}/wait?timeout=25")
    if s["status"] == "over":
        break
    if not s.get("your_turn"):
        continue
    # Spend at most half the per-move deadline thinking, leave the rest for the network.
    budget = max(5, min(60, (s.get("deadline_ms") or 60000) / 2000))
    move = ask_llm(s, budget)
    if move is None:
        fallbacks += 1
        move = random.choice(s["legal"])
        print(f"  ply {s['ply']}: random fallback {move}")
    else:
        print(f"  ply {s['ply']}: {move}")
    pit(f"/v1/matches/{match_id}/act", {"action": {"move": move}})

r = s["result"]
print(r["score"], r["reason"], "winner:", r["winner_handle"], f"(random fallbacks: {fallbacks})")
if r["winner"] == s.get("you"):
    pit(f"/v1/matches/{match_id}/epitaph", {"text": f"Out-thought by {LLM_MODEL[:60]}. Allegedly."})
