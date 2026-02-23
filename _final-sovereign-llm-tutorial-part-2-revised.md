# Hands-On: vLLM Metal on Mac Studio M4

> From zero to a working sovereign chatbot in 30-60 minutes. Every command copy-pasteable, every step verified.

> **TL;DR:** This is Part 2 of a 3-part series on sovereign LLM inference. Here you'll install vLLM Metal, download and verify model weights, launch an OpenAI-compatible API, and build a Python chatbot client. Primary path: **Llama 3.2 3B Instruct** (proven). Bonus path: **gpt-oss-20b** (if MoE support works). This walkthrough uses vLLM Metal (see [Part 1] for why). If you chose vllm-mlx instead, the commands are nearly identical — swap the install step and the rest applies.
>
> - **Part 1:** [Why Sovereign LLM Inference on Apple Silicon] (architecture, hardware, compliance)
> - **Part 2 (this article):** Installation, model setup, chatbot
> - **Part 3:** Security hardening, production ops
>
> **Companion repository:** All scripts and config files from this series are available at [sovereign-vllm-metal](https://github.com/yourorg/sovereign-vllm-metal). Clone it to follow along.

---

## Installation: Step by Step

### Prerequisites

```bash
# Xcode Command Line Tools
xcode-select --install
# Already installed? Fine. It'll tell you.

# Python 3.12
python3 --version
# If not 3.12:
brew install python@3.12
```

### The Careful Way (Don't Pipe to Bash)

The official docs tell you to run:
```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
```

We're going to do it differently. Download first, read it, then run it.

```bash
# Create a working directory
mkdir -p ~/vllm-metal-setup && cd ~/vllm-metal-setup

# Pin to a specific release tag (not main, which changes constantly)
RELEASE_TAG="v0.1.0-20260204-122749"
BASE_URL="https://raw.githubusercontent.com/vllm-project/vllm-metal/${RELEASE_TAG}"

# Download both scripts
curl -fsSL "${BASE_URL}/install.sh" -o install.sh
curl -fsSL "${BASE_URL}/scripts/lib.sh" -o lib.sh

# Save checksums for your audit trail
shasum -a 256 install.sh lib.sh | tee install-checksums.sha256
```

Now read the scripts:

```bash
less install.sh   # About 90 lines. It's not scary.
less lib.sh       # Helper functions. Even less scary.
```

Things to look for: unexpected network calls, sudo usage, file modifications outside the venv. You should find none of these. If you're satisfied:

```bash
bash install.sh
```

This takes 5-15 minutes. Go get coffee. When it's done:

```
 Installation complete!
```

**Note on vLLM versions:** The installer builds vLLM 0.13.0 from source (pinned by vllm-metal for stability). The vLLM mainline is at v0.15.1 as of February 2026, but vllm-metal requires the older version. The vllm-metal plugin itself is at v0.1.0.

### Verify the Installation

```bash
source ~/.venv-vllm-metal/bin/activate

# vLLM version
python -c "import vllm; print(f'vLLM: {vllm.__version__}')"
# -> vLLM: 0.13.0

# vllm-metal plugin
python -c "import vllm_metal; print('vllm-metal: loaded')"

# MLX GPU
python -c "import mlx.core as mx; print(f'MLX device: {mx.default_device()}')"
# -> MLX device: gpu

# Quick compute test
python -c "
import mlx.core as mx
a = mx.ones((100, 100)); b = mx.ones((100, 100))
c = a @ b; mx.eval(c)
print(f'GPU matmul: OK ({c[0,0]:.0f})')
"
# -> GPU matmul: OK (100)
```

If any of these fail, stop. Fix the issue before continuing.

### Freeze Your Environment

```bash
uv pip freeze > ~/vllm-metal-setup/requirements-frozen.txt
shasum -a 256 ~/vllm-metal-setup/requirements-frozen.txt > ~/vllm-metal-setup/requirements-frozen.sha256
```

This is your "known good state." Part 3 uses it for runtime integrity checks.

---

## Model Acquisition and Integrity Verification

We're about to download several gigabytes of neural network weights from the internet. Let's be thorough about making sure they're legit.

### Download the Models

```bash
source ~/.venv-vllm-metal/bin/activate
mkdir -p ~/models

# Primary: Llama 3.2 3B Instruct (~6GB, proven on MLX)
huggingface-cli download meta-llama/Llama-3.2-3B-Instruct \
  --local-dir ~/models/llama-3.2-3b

# Bonus: gpt-oss-20b (~16GB, if MoE support works)
huggingface-cli download openai/gpt-oss-20b \
  --include "original/*" \
  --local-dir ~/models/gpt-oss-20b
```

Download both. Disk is cheap. Time spent debugging download issues later is not.

### Generate Baseline Checksums

Do this immediately after download. Before anything else. These checksums are your proof that the model hasn't been tampered with.

```bash
cd ~/models/llama-3.2-3b

# SHA256 every file that matters
find . -type f \( \
  -name "*.safetensors" \
  -o -name "*.json" \
  -o -name "*.model" \
  -o -name "*.txt" \
  -o -name "*.py" \
\) -exec shasum -a 256 {} \; | sort > CHECKSUMS.sha256

echo "Files checksummed: $(wc -l < CHECKSUMS.sha256)"
echo "Total model size: $(du -sh . | cut -f1)"
```

Repeat for gpt-oss-20b if you downloaded it. Save the `CHECKSUMS.sha256` files somewhere safe.

### Verify Model Integrity

Checksums tell you "the file is the same as when I downloaded it." The companion repo includes `verify_model.py`, which walks the model directory and checks every file against your stored checksums:

```python
# scripts/verify_model.py (excerpt — full script in companion repo)
def sha256_file(filepath: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
```

```bash
python scripts/verify_model.py ~/models/llama-3.2-3b
#   Model directory : /Users/yourname/models/llama-3.2-3b
#   Checking : ./model.safetensors... OK (5.72 GB)
#   ...
#   All files verified. Safe to serve.
```

This takes a few minutes for large models. That's the price of integrity verification. Worth it.

### Air-Gapped Transfer

If your Mac Studio should never touch the internet:

```bash
# On a connected machine: download + verify
huggingface-cli download meta-llama/Llama-3.2-3B-Instruct --local-dir /tmp/llama-3.2-3b
cd /tmp/llama-3.2-3b
find . -type f \( -name "*.safetensors" -o -name "*.json" \) -exec shasum -a 256 {} \; | sort > CHECKSUMS.sha256

# Copy to encrypted USB
rsync -avP /tmp/llama-3.2-3b/ /Volumes/SecureUSB/llama-3.2-3b/

# On the Mac Studio: copy and verify
rsync -avP /Volumes/SecureUSB/llama-3.2-3b/ ~/models/llama-3.2-3b/
cd ~/models/llama-3.2-3b && shasum -a 256 -c CHECKSUMS.sha256
# Every line should say: OK
```

### License Quick Reference

| Model | License | Commercial? | Fine-tuning? |
|---|---|---|---|
| Llama 3.2 3B | Llama 3.2 Community License | Yes | Yes |
| gpt-oss-20b | Apache 2.0 | Yes | Yes |
| Qwen 2.5 7B | Apache 2.0 | Yes | Yes |

For gpt-oss-20b (Apache 2.0 licensed), OpenAI's usage policy for their reasoning models is guidance/convention, not a legal requirement. You may adopt similar practices for responsible use.

### Go Dark

Models downloaded. Checksums created. Now lock it down.

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

From this point on, nothing calls Hugging Face. Everything the server needs is on disk.

---

## Configuration and Launch

### Environment Config

The companion repo includes a template at `config/vllm-metal.env.example`. Copy and adapt it:

```bash
cp sovereign-vllm-metal/config/vllm-metal.env.example ~/.vllm-metal-env
chmod 600 ~/.vllm-metal-env
```

### Generate and Save Your API Key

```bash
# Generate once, save it, reuse it
API_KEY=$(openssl rand -hex 16)
echo "export VLLM_API_KEY=${API_KEY}" >> ~/.vllm-metal-env
echo "Your API key: ${API_KEY}"
# Write this down. You need it for every request.
```

### Start the Server (Primary Path: Llama 3.2 3B)

```bash
source ~/.venv-vllm-metal/bin/activate
source ~/.vllm-metal-env

vllm serve ~/models/llama-3.2-3b \
  --host 127.0.0.1 \
  --port 8000 \
  --api-key "${VLLM_API_KEY}"
```

**Note:** The `vllm` command is installed in your virtual environment. Ensure you've activated it (see above).

Watch the output. You're looking for:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

That's your sovereign inference server. Running on your desk. On a machine you own.

### Bonus Path: gpt-oss-20b

If you want to try the 21B MoE model, the launch is the same:

```bash
vllm serve ~/models/gpt-oss-20b \
  --host 127.0.0.1 \
  --port 8000 \
  --api-key "${VLLM_API_KEY}"
```

**If it fails with `Unsupported model architecture`**, MoE support isn't ready yet. Stick with Llama 3.2 3B. No shame in that.

**Harmony format for gpt-oss-20b.** gpt-oss-20b uses Harmony format for its chat template. The standard `vllm serve` with the `/v1/chat/completions` endpoint handles this automatically via the model's `tokenizer_config.json`. You only need the `openai-harmony` package (`pip install openai-harmony`) if you're constructing prompts manually outside the standard chat completions format.

### Why `--host 127.0.0.1` Specifically

Some servers default to `0.0.0.0`, which means "listen on every network interface." That includes your Wi-Fi. If you're on a shared network, anyone can hit your API. `127.0.0.1` means localhost only. Nothing from the network reaches it.

If other machines on your LAN need access, set up a TLS reverse proxy with mkcert + Caddy. This is a niche setup, so I'll spare you the details here. The `mkcert` and `caddy` docs are solid.

### Request Logging

```bash
sudo mkdir -p /var/log/vllm-metal && sudo chown $(whoami) /var/log/vllm-metal

vllm serve ~/models/llama-3.2-3b \
  --host 127.0.0.1 \
  --port 8000 \
  --api-key "${VLLM_API_KEY}" \
  2>&1 | tee -a /var/log/vllm-metal/inference-$(date +%Y%m%d).log
```

Every request logged with timestamps. Your compliance team will thank you later. Or at least stop bothering you for a while.

---

## Building the Chatbot

### Smoke Test

Open a new terminal. Keep the server running in the first one.

```bash
source ~/.venv-vllm-metal/bin/activate
source ~/.vllm-metal-env

curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${VLLM_API_KEY}" \
  -d '{
    "model": "llama-3.2-3b",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain data sovereignty in one paragraph."}
    ],
    "temperature": 0.7,
    "max_tokens": 256
  }' | python -m json.tool
```

If you see a JSON response with the model's answer, you're done with the hard part. Everything from here is polish.

**Quick debugging tip:** if the model name is wrong, check what vLLM actually loaded:

```bash
curl -s http://127.0.0.1:8000/v1/models -H "Authorization: Bearer ${VLLM_API_KEY}" | python -m json.tool
```

### Python Chatbot Client

The companion repo includes `scripts/sovereign_chat.py`, a full interactive chatbot with conversation history and local JSONL logging. The core is straightforward OpenAI SDK usage:

```python
# scripts/sovereign_chat.py (excerpt — full client in companion repo)
from openai import OpenAI

client = OpenAI(
    base_url=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1"),
    api_key=os.getenv("VLLM_API_KEY"),
)

resp = client.chat.completions.create(
    model=os.getenv("VLLM_MODEL", "llama-3.2-3b"),
    messages=[{"role": "user", "content": "Hello!"}],
    temperature=0.7,
    max_tokens=1024,
)
print(resp.choices[0].message.content)
```

Run it:

```bash
source ~/.venv-vllm-metal/bin/activate
uv pip install openai
source ~/.vllm-metal-env
python scripts/sovereign_chat.py
```

The client maintains conversation history in memory and logs every turn to a local JSONL file. No databases. No cloud sync. Just a file on your disk. It supports `/clear`, `/status`, and `/quit` commands.

**For gpt-oss-20b users:** change the MODEL environment variable:
```bash
export VLLM_MODEL=gpt-oss-20b
python scripts/sovereign_chat.py
```

### Reasoning Effort (gpt-oss-20b Only)

gpt-oss-20b lets you control how hard it thinks. Put it in the system prompt:

```python
# Fast. Good for simple queries.
SYSTEM_PROMPT = "Reasoning: low\nYou are a helpful assistant."

# Balanced. The sensible default.
SYSTEM_PROMPT = "Reasoning: medium\nYou are a helpful assistant."

# Slow but thorough. For complex analysis, code gen, logic puzzles.
SYSTEM_PROMPT = "Reasoning: high\nYou are a helpful assistant."
```

The "high" setting makes the model produce a chain-of-thought before answering. Great for hard questions. Overkill for "what's the capital of France." Note: OpenAI's policy for their reasoning models suggests the reasoning output "is not intended to be shown to end users." For gpt-oss-20b (Apache 2.0 license), this is guidance rather than legal requirement, but keeping reasoning in logs rather than UI is good practice.

---

## What You've Built

You now have a sovereign LLM inference server on your desk. It serves an OpenAI-compatible API, every token stays on your machine, and you've verified the model weights haven't been tampered with.

**Part 3** covers the hardening: dedicated service accounts, firewall rules, launchd auto-start, integrity monitoring, and update strategy. The difference between "it works on my machine" and "it runs in production."

---

## Quick Reference

```bash
# Activate
source ~/.venv-vllm-metal/bin/activate && source ~/.vllm-metal-env

# Start server (Llama 3.2 3B)
vllm serve ~/models/llama-3.2-3b --host 127.0.0.1 --port 8000 --api-key "${VLLM_API_KEY}"

# Start server (gpt-oss-20b, if MoE works)
vllm serve ~/models/gpt-oss-20b --host 127.0.0.1 --port 8000 --api-key "${VLLM_API_KEY}"

# Health check
curl -s http://127.0.0.1:8000/v1/models -H "Authorization: Bearer ${VLLM_API_KEY}"

# Chat request
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${VLLM_API_KEY}" \
  -d '{"model":"llama-3.2-3b","messages":[{"role":"user","content":"Hello!"}]}'

# Verify model integrity
python scripts/verify_model.py ~/models/llama-3.2-3b

# View logs
tail -f /var/log/vllm-metal/inference-$(date +%Y%m%d).log
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: vllm_metal` | Activate the venv: `source ~/.venv-vllm-metal/bin/activate` |
| MLX shows `cpu` device | Uncheck "Open using Rosetta" in Terminal.app -> Get Info |
| Wrong model name in API | Check `curl /v1/models` for the actual registered name |
| Out of memory | Set `VLLM_METAL_MEMORY_FRACTION=0.5` or use a smaller model |
| `Unsupported model architecture` | MoE not supported yet. Use Llama 3.2 3B as fallback. |
| Slow first response | Normal. MLX compiles kernels on first request. Second request is faster. |
| 401 Unauthorized | API key mismatch between server and client |

---

This article reflects my professional perspective. Drafting was assisted by Claude, but the insights and final curation are entirely my own.

[Sovereign AI Strategist](https://www.linkedin.com/in/michaelhannecke/) @ [bluetuple.ai](https://www.bluetuple.ai) | Exploring autonomous AI systems, agentic architectures, and secure AI independence. Writing about what it takes to build AI that stays under your control.
