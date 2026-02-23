# Security Hardening & Production Ops for Sovereign LLM Inference

> "I'll secure it later" is the most popular last words in IT. Let's not join that club.

> **TL;DR:** Part 3 of the sovereign LLM series. You've got a working inference server from Part 2. Now we lock it down: dedicated service account, firewall rules, supply chain awareness, launchd auto-start (running as the service account), integrity monitoring, and an update strategy. The goal: a setup that survives reboots, detects tampering, and limits blast radius if something goes wrong.
>
> - **Part 1:** [Why Sovereign LLM Inference on Apple Silicon] (architecture, hardware, compliance)
> - **Part 2:** [Hands-On: vLLM Metal on Mac Studio M4] (installation, model setup, chatbot)
> - **Part 3 (this article):** Security hardening, production ops
>
> **Companion repository:** All config files and scripts referenced below are in the [sovereign-vllm-metal](https://github.com/yourorg/sovereign-vllm-metal) repo.

---

## Security Baseline

### macOS Checks

Run these. If any of them fail, fix them before proceeding. Seriously.

```bash
# Is your disk encrypted?
fdesetup status
# Expected: FileVault is On.

# Is System Integrity Protection active?
csrutil status
# Expected: System Integrity Protection status: enabled.

# Is Gatekeeper active?
spctl --status
# Expected: assessments enabled
```

If FileVault is off, turn it on now: System Settings -> Privacy & Security -> FileVault. On Apple Silicon, it uses the hardware AES engine, so the performance impact is negligible.

### Dedicated Service Account

Don't run the inference server as your daily user. Create a separate account with limited privileges.

```bash
sudo sysadminctl -addUser llm-service \
  -fullName "LLM Inference Service" \
  -password "$(openssl rand -base64 24)" \
  -home /Users/llm-service \
  -shell /bin/zsh

# Verify the account is NOT an admin
dscl . -read /Users/llm-service
# GroupMembership should NOT include "admin"
```

Why bother? If you're running a model that accepts arbitrary text input from users (which is exactly what a chatbot does), you've got an autonomous process that interprets untrusted input. Sound familiar? It should. It's the same threat model as a web server. You wouldn't run Apache as root. Don't run your inference server as your main user either.

> A dedicated service account limits blast radius. If something goes wrong, the attacker gets a locked-down account with no sudo access, not your entire system.

### Set Up the Service Account's Environment

```bash
# Create model and venv directories
sudo mkdir -p /Users/llm-service/models
sudo mkdir -p /Users/llm-service/.venv-vllm-metal
sudo mkdir -p /Users/llm-service/scripts
sudo chown -R llm-service:staff /Users/llm-service

# Copy model weights and venv to the service account
sudo -u llm-service cp -R ~/models/llama-3.2-3b /Users/llm-service/models/
sudo -u llm-service cp -R ~/.venv-vllm-metal/* /Users/llm-service/.venv-vllm-metal/

# Copy the frozen requirements for integrity checks
sudo -u llm-service cp ~/vllm-metal-setup/requirements-frozen.txt /Users/llm-service/

# Copy scripts from the companion repo
sudo -u llm-service cp sovereign-vllm-metal/scripts/integrity_check.sh /Users/llm-service/scripts/
sudo chmod +x /Users/llm-service/scripts/integrity_check.sh
```

### Network Isolation

The inference server should talk to exactly the machines you tell it to, and nothing else.

**Option A: Just bind to localhost (simplest)**

When we start vLLM, we use `--host 127.0.0.1`. Only processes on the same machine can reach it. Done.

**Option B: macOS pf firewall (belt and suspenders)**

Block the service account from making any outbound connections at all:

```bash
# Back up pf.conf first
sudo cp /etc/pf.conf /etc/pf.conf.bak

# Add the rule
echo 'block out quick proto { tcp udp } user llm-service' | sudo tee -a /etc/pf.conf

# Dry-run: validate syntax BEFORE loading
sudo pfctl -nf /etc/pf.conf
# If this shows errors, fix them. If it's silent, the syntax is valid.

# Reload the firewall (only after dry-run passes)
sudo pfctl -f /etc/pf.conf
sudo pfctl -e
```

> Editing `/etc/pf.conf` can break networking for the whole machine. Always back up first, always dry-run with `pfctl -nf` before loading. If you're not experienced with pf, stick with Option A.

### Kill the Phone-Home

Python ML packages love to call home. Let's make sure they can't.

```bash
sudo -u llm-service tee -a /Users/llm-service/.zshrc << 'EOF'
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export DO_NOT_TRACK=1
export PIP_NO_INPUT=1
export HOMEBREW_NO_ANALYTICS=1
EOF
```

Set `HF_HUB_OFFLINE=1` only AFTER you've downloaded your model. Timing matters.

### Supply Chain Awareness

The vLLM Metal install script downloads a helper script from GitHub, checks you're on Apple Silicon, installs `uv`, creates a virtual environment, builds vLLM v0.13.0 from source, and installs the vllm-metal wheel. The releases are built by GitHub Actions CI and signed with GitHub's verified GPG key (ID: `B5690EEEBB952194`). That's decent provenance. But `curl | bash` is still a trust exercise. Part 2 covered the "download first, read it, then run it" approach.

---

## Production Ops

### launchd Service (Start on Boot)

The companion repo includes `config/ai.bluetuple.vllm-metal.plist`, a LaunchDaemon that runs vLLM as the `llm-service` account. Note: LaunchDaemons (in `/Library/LaunchDaemons/`), not LaunchAgents, because this runs as a different user.

Key parts of the plist:

```xml
<!-- config/ai.bluetuple.vllm-metal.plist (excerpt) -->
<key>UserName</key>
<string>llm-service</string>
<key>ProgramArguments</key>
<array>
    <string>/Users/llm-service/.venv-vllm-metal/bin/vllm</string>
    <string>serve</string>
    <string>/Users/llm-service/models/llama-3.2-3b</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>8000</string>
    <string>--api-key-file</string>
    <string>/Users/llm-service/.vllm-api-key</string>
</array>
<key>RunAtLoad</key>
<true/>
<key>KeepAlive</key>
<true/>
```

Set up the API key and install:

```bash
# Store API key in a file readable only by llm-service
sudo -u llm-service sh -c 'openssl rand -hex 16 > /Users/llm-service/.vllm-api-key'
sudo chmod 400 /Users/llm-service/.vllm-api-key

# Read the key (you'll need it for client requests)
sudo cat /Users/llm-service/.vllm-api-key

# For even better security, also store it in Keychain
sudo -u llm-service security add-generic-password \
  -s vllm-api-key -a llm-service -w "$(sudo cat /Users/llm-service/.vllm-api-key)"

# Create log directory
sudo mkdir -p /var/log/vllm-metal
sudo chown llm-service:staff /var/log/vllm-metal

# Install the plist (full file in companion repo)
sudo cp sovereign-vllm-metal/config/ai.bluetuple.vllm-metal.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/ai.bluetuple.vllm-metal.plist

# Check status
sudo launchctl list | grep vllm
```

Now vLLM starts on boot, runs as `llm-service` (not your user), and restarts if it crashes.

### Runtime Integrity Checks

The companion repo includes `scripts/integrity_check.sh`, which verifies model weight checksums and Python environment packages haven't changed. On failure, it logs to `/var/log/vllm-metal/` and writes an alert to syslog via `logger`:

```bash
# scripts/integrity_check.sh (excerpt — full script in companion repo)
if cd "$MODEL_DIR" && shasum -a 256 -c CHECKSUMS.sha256 --quiet 2>/dev/null; then
    echo "$(date -u) Model weights: OK" >> "$LOGFILE"
else
    echo "$(date -u) MODEL WEIGHTS: FAILED" >> "$LOGFILE"
    logger -p local0.alert "vLLM Metal: model weight integrity check FAILED"
    FAIL=1
fi
```

The `logger` call writes to syslog, which works regardless of whether the service account has a GUI session. You can monitor these alerts with `log show --predicate 'subsystem == "local0"'` or forward them to your SIEM.

Schedule the check as a LaunchDaemon (not cron, to stay consistent with macOS conventions). The companion repo includes `config/ai.bluetuple.vllm-metal-integrity.plist`:

```bash
# Install the integrity check daemon
sudo cp sovereign-vllm-metal/config/ai.bluetuple.vllm-metal-integrity.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/ai.bluetuple.vllm-metal-integrity.plist
```

This runs the integrity check daily at 06:00 as `llm-service`. Two things get verified every morning: are the model weights the same files you downloaded (no tampering), and is the Python environment unchanged (no injected packages).

### Memory Monitoring

```bash
# Quick: is there memory pressure?
memory_pressure | head -3

# How much is vLLM eating?
ps aux | grep vllm | grep -v grep | awk '{printf "%.0f MB\n", $6/1024}'
```

If memory gets tight, edit the plist's EnvironmentVariables section and change `VLLM_METAL_MEMORY_FRACTION` from `auto` to `0.6`.

### Update Strategy

vllm-metal releases frequently (as of Feb 2026, multiple times per week). Here's how to update safely:

```bash
# Check latest release
curl -s https://api.github.com/repos/vllm-project/vllm-metal/releases/latest \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['tag_name'], d['published_at'][:10])"

# Stop the service
sudo launchctl unload /Library/LaunchDaemons/ai.bluetuple.vllm-metal.plist

# Back up current state
sudo -u llm-service cp /Users/llm-service/requirements-frozen.txt \
  /Users/llm-service/requirements-frozen.bak

# Update
sudo -u llm-service /Users/llm-service/.venv-vllm-metal/bin/uv pip install --upgrade vllm-metal

# Re-freeze
sudo -u llm-service /Users/llm-service/.venv-vllm-metal/bin/uv pip freeze \
  > /Users/llm-service/requirements-frozen.txt

# Test
sudo -u llm-service /Users/llm-service/.venv-vllm-metal/bin/python \
  -c "import vllm_metal; print('OK')"

# Restart the service
sudo launchctl load /Library/LaunchDaemons/ai.bluetuple.vllm-metal.plist
```

If the update breaks something, roll back:

```bash
sudo -u llm-service /Users/llm-service/.venv-vllm-metal/bin/uv pip install \
  -r /Users/llm-service/requirements-frozen.bak
```

---

## What You've Built (The Complete Picture)

Across all three parts, you now have:

- **A sovereign inference server** that processes every token locally (Part 1 explains why this matters)
- **Verified model weights** downloaded, checksummed, and integrity-checked (Part 2)
- **A working chatbot** with an OpenAI-compatible API (Part 2)
- **A dedicated service account** with no admin privileges and no outbound network access (this article)
- **A launchd daemon** that starts on boot, runs as the service account, and restarts on crash (this article)
- **Daily integrity monitoring** via launchd that detects model tampering and environment changes (this article)
- **An update strategy** with rollback capability (this article)

No cloud account. No data processing agreement. No "we updated our privacy policy" emails.

This isn't the only way to run local inference. It's not even the simplest. But if you need production-grade features, full control, and data sovereignty, this setup delivers.

> "If the weights live on your disk, the inference runs on your CPU/GPU, and the API binds to localhost, then no token ever leaves your machine."

---

This article reflects my professional perspective. Drafting was assisted by Claude, but the insights and final curation are entirely my own.

[Sovereign AI Strategist](https://www.linkedin.com/in/michaelhannecke/) @ [bluetuple.ai](https://www.bluetuple.ai) | Exploring autonomous AI systems, agentic architectures, and secure AI independence. Writing about what it takes to build AI that stays under your control.
