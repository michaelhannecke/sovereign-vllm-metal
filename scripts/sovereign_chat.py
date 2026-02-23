#!/usr/bin/env python3
"""
sovereign_chat.py
Local chatbot client for vLLM Metal. All inference on localhost.

Requires:
    pip install openai

Environment variables:
    VLLM_BASE_URL  — API base URL (default: http://127.0.0.1:8000/v1)
    VLLM_API_KEY   — API key (required)
    VLLM_MODEL     — Model name (default: llama-3.2-3b)

Usage:
    source ~/.vllm-metal-env
    python sovereign_chat.py
"""

import os
import json
import readline
from datetime import datetime
from openai import OpenAI

# Config
VLLM_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")
API_KEY = os.getenv("VLLM_API_KEY", "changeme")
MODEL = os.getenv("VLLM_MODEL", "llama-3.2-3b")

SYSTEM_PROMPT = """You are a helpful assistant running on sovereign infrastructure.
No data from this conversation leaves this machine. Be concise."""

# Setup
client = OpenAI(base_url=VLLM_URL, api_key=API_KEY)
history = [{"role": "system", "content": SYSTEM_PROMPT}]

# Local conversation log
LOG_DIR = os.path.expanduser("~/.local/share/sovereign-chat")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"chat-{datetime.now():%Y%m%d-%H%M%S}.jsonl")


def log_turn(role: str, content: str):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps({
            "ts": datetime.utcnow().isoformat() + "Z",
            "role": role,
            "content": content,
        }) + "\n")


def chat(msg: str) -> str:
    history.append({"role": "user", "content": msg})
    log_turn("user", msg)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=history,
            temperature=0.7,
            max_tokens=1024,
        )
        reply = resp.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        log_turn("assistant", reply)
        return reply
    except Exception as e:
        return f"[Error: {e}]"


def main():
    print()
    print("  Sovereign Chat (vLLM Metal)")
    print(f"  Server: {VLLM_URL}  |  Model: {MODEL}")
    print(f"  Log: {LOG_FILE}")
    print("  Commands: /clear /status /quit")
    print()

    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not msg:
            continue
        if msg in ("/quit", "/exit", "/q"):
            break
        if msg == "/clear":
            history.clear()
            history.append({"role": "system", "content": SYSTEM_PROMPT})
            print("  [cleared]\n")
            continue
        if msg == "/status":
            try:
                models = client.models.list()
                print(f"  Connected. Models: {[m.id for m in models.data]}\n")
            except Exception as e:
                print(f"  Offline: {e}\n")
            continue

        print(f"AI: {chat(msg)}\n")


if __name__ == "__main__":
    main()
