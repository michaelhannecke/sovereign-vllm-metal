# CLAUDE.md — sovereign-vllm-metal

## Project Overview

Companion repository for the **Sovereign LLM Inference on Apple Silicon** blog article series (3 parts). Contains all scripts, configuration files, and tutorial articles for running a production-grade, security-hardened LLM inference server on Mac Studio M4 using vLLM Metal.

**Author:** Michael Hannecke — [bluetuple.ai](https://www.bluetuple.ai)

## Repository Structure

```
sovereign-vllm-metal/
├── scripts/
│   ├── verify_model.py            # SHA256 model integrity verification (Python 3.12, stdlib only)
│   ├── sovereign_chat.py          # Interactive chatbot client (requires: openai)
│   └── integrity_check.sh         # Daily runtime integrity monitor (bash, runs as llm-service)
├── config/
│   ├── vllm-metal.env.example     # Environment variable template
│   ├── ai.bluetuple.vllm-metal.plist           # launchd daemon for vLLM server
│   └── ai.bluetuple.vllm-metal-integrity.plist # launchd daemon for daily integrity checks
├── _final-sovereign-llm-tutorial-part-1-revised.md  # Article: Why sovereign inference
├── _final-sovereign-llm-tutorial-part-2-revised.md  # Article: Hands-on installation & chatbot
├── _final-sovereign-llm-tutorial-part-3.md          # Article: Security hardening & production ops
└── README.md
```

## Technology Stack

- **Inference engine:** vLLM v0.13.0 with vllm-metal plugin v0.1.0 (official Apple Silicon plugin)
- **ML backend:** MLX (Apple's ML framework for Metal GPU)
- **Python:** 3.12, virtual environment at `~/.venv-vllm-metal`
- **Target hardware:** Mac Studio M4 with 64GB unified memory
- **OS:** macOS 14 Sonoma / 15 Sequoia
- **Primary model:** Llama 3.2 3B Instruct (~6GB FP16)
- **Bonus model:** gpt-oss-20b (~16GB, MoE architecture, Apache 2.0)
- **API:** OpenAI-compatible (localhost:8000/v1)
- **Service management:** macOS launchd (LaunchDaemons, not LaunchAgents)
- **Service account:** `llm-service` (non-admin, no outbound network)

## Key Conventions

- All inference runs on **localhost only** (`--host 127.0.0.1`) — no network exposure
- Environment variables are stored in `~/.vllm-metal-env` (chmod 600)
- API keys generated via `openssl rand -hex 16`, stored in file or Keychain
- Model weights verified via SHA256 checksums (`CHECKSUMS.sha256` in model directory)
- Offline mode enforced: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`
- Logs go to `/var/log/vllm-metal/`
- The `_final-*.md` files are blog articles (markdown), not code — treat as content

## Scripts Detail

### verify_model.py
- Stdlib only (hashlib, os, sys) — no external dependencies
- Reads `CHECKSUMS.sha256` from model directory, compares SHA256 hashes
- Exit code 1 on any failure or missing file

### sovereign_chat.py
- Depends on `openai` package
- Uses env vars: `VLLM_BASE_URL`, `VLLM_API_KEY`, `VLLM_MODEL`
- Logs conversation turns to JSONL in `~/.local/share/sovereign-chat/`
- Commands: `/clear`, `/status`, `/quit`

### integrity_check.sh
- Runs as `llm-service` user via launchd
- Checks model weight checksums AND pip freeze against frozen requirements
- Failures logged to `/var/log/vllm-metal/` and syslog (`local0.alert`)
- Configurable via env vars: `MODEL_DIR`, `VENV_DIR`, `FROZEN_REQ`

## Config Detail

### LaunchDaemons (plist files)
- Install to `/Library/LaunchDaemons/` (requires sudo)
- Run as `llm-service` user, not the admin user
- `ai.bluetuple.vllm-metal.plist`: starts vLLM on boot, KeepAlive=true
- `ai.bluetuple.vllm-metal-integrity.plist`: daily integrity check at 06:00

## Content Guidelines

- This is a **blog companion repo** — clarity and security are paramount
- Scripts should remain simple, self-contained, and copy-pasteable
- No unnecessary dependencies — stdlib preferred where possible
- Security posture: defense-in-depth (service accounts, firewall, integrity checks, offline mode)
- The articles use a direct, opinionated technical writing style

## License

Apache 2.0
