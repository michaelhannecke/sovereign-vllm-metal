# Why Sovereign LLM Inference on Apple Silicon

> Your desk is the data center. No cloud. No API keys. No "we updated our privacy policy" emails. Just you, your Mac Studio, and a model that runs entirely on localhost.

> **TL;DR:** Apple Silicon's unified memory makes Mac Studios viable inference servers. This series uses vLLM Metal — not because it's the fastest option today, but because it's the official vLLM plugin for Apple Silicon, and that ecosystem bet matters for enterprise adoption. No tokens leave your machine. Part 1 of 3 covering the why, the how, and the hardening.
>
> **Series overview:**
> - **Part 1 (this article):** Why this approach, architecture choices, hardware sizing
> - **Part 2:** Hands-on installation, model setup, building a chatbot
> - **Part 3:** Security hardening, service accounts, production ops
>
> **Companion repository:** [sovereign-vllm-metal](https://github.com/yourorg/sovereign-vllm-metal) (all scripts and config files)

---

## The Pitch

OpenAI released gpt-oss-20b under Apache 2.0. It fits in 16GB of memory. And as of this writing, vLLM Metal lets you serve it on Apple Silicon with a proper production-grade inference API.

That last part matters. Running a model locally with Ollama is fine for poking around. But if you want an OpenAI-compatible API server with a scheduler, paged attention, and the ability to handle multiple concurrent requests? That's what vLLM does. And vllm-metal is the official plugin that brings it to Apple Silicon. (It's not the only option — more on that in the stack comparison below.)

**The sovereignty angle is simple.** If the weights live on your disk, the inference runs on your CPU/GPU, and the API binds to localhost, then no token ever leaves your machine. No Data Processing Agreement needed. No GDPR Article 28 headaches. No awkward conversations with your DPO about where the prompts go.

---

## The Architecture

Here's what runs on your Mac Studio:

```
┌─────────────────────────────────────────────────────────────┐
│                        Your Chatbot Client                  │
│              (curl, Python, any OpenAI SDK)                  │
└─────────────────────────┬───────────────────────────────────┘
                          │  HTTP (localhost:8000)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      vLLM Core (v0.13.0)                    │
│         Engine, Scheduler, OpenAI-compatible API Server      │
└─────────────────────────┬───────────────────────────────────┘
                          │  Plugin interface
                          ▼
┌─────────────────────────────────────────────────────────────┐
│               vllm-metal Plugin (v0.1.0)                    │
│         MetalPlatform → MetalWorker → MetalModelRunner       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    MLX Backend (Primary)                     │
│        SDPA Attention, RMSNorm, RoPE, Cache Ops             │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Apple Silicon Metal GPU Layer                   │
│           Unified Memory (64GB, shared CPU + GPU)            │
└─────────────────────────────────────────────────────────────┘
```

The key insight is **unified memory**. On a regular PC with an NVIDIA GPU, data typically travels across the PCIe bus between system RAM and VRAM (though NVLink reduces this). On Apple Silicon, CPU and GPU share the same memory pool. No copies needed. This is why a Mac Studio with "only" 64GB can punch above its weight for inference workloads.

## Choosing Your Inference Stack (and Why This Series Picks vLLM Metal)

Let's be upfront about something. If you're choosing purely on today's features and benchmarks, **vllm-mlx is the stronger option.** It has higher throughput (21–87% over llama.cpp in published benchmarks), broader model support including vision and audio, MCP tool calling, an Anthropic Messages API endpoint, continuous batching, and prefix caching that cuts multimodal latency from 21 seconds to under a second. It has an academic paper behind it. It works today.

So why does this series focus on vLLM Metal?

**The answer is ecosystem positioning, not performance.**

vllm-metal lives under `vllm-project/vllm-metal` — it's the *official* community plugin for Apple Silicon maintained within the vLLM project itself. That distinction matters in three ways:

1. **Upstream convergence.** When vLLM Core ships new features — speculative decoding, improved PagedAttention, new scheduling strategies — vllm-metal is the designated path to bring them to Apple Silicon. It plugs into vLLM's platform abstraction through a proper entry-point system. vllm-mlx is a standalone server that happens to expose a compatible API.

2. **Enterprise procurement.** If you're in a regulated environment and need to justify your inference stack to security review or architecture governance, "official plugin of the vLLM project, led by an engineer at Docker, Inc." is a simpler conversation than "independent project by a single maintainer." This isn't a quality judgment — it's a reality of how enterprise approval processes work.

3. **Long-term bet.** vLLM is the dominant open-source inference engine. As Apple Silicon gains traction for inference workloads, vLLM's investment in the Metal plugin is likely to accelerate. Betting on the canonical path means your setup, scripts, and operational knowledge stay relevant as the ecosystem matures.

**That said — here's the honest comparison:**

| | Ollama | mlx-lm | vLLM Metal | vllm-mlx |
|---|---|---|---|---|
| Ease of setup | Dead simple | Simple | Moderate | Moderate |
| OpenAI-compatible API | Yes | No (needs wrapper) | Yes (native) | Yes (native) |
| Anthropic Messages API | No | No | No | Yes |
| Request scheduler | Basic | None | Full (paged attention) | Continuous batching |
| Concurrent users | Limited | Single user | Multiple | Multiple |
| Vision / Audio models | Limited | Yes | No | Yes |
| MCP tool calling | No | No | No | Yes |
| Prefix caching | No | Session-scoped | No | Yes (content-based) |
| Benchmarked throughput | 20–40 tok/s | ~230 tok/s | Good (no published benchmarks) | Up to 525 tok/s (Qwen3-0.6B) |
| Maturity | Stable | Stable | v0.1.0 (young) | Active development |
| Governance story | Commercial product | Apple-backed | Official vLLM plugin | Independent maintainer |

Read that table honestly: vllm-mlx wins on features and measured performance. vLLM Metal wins on ecosystem position and the governance narrative.

**My recommendation:** If you need multimodal support, MCP integration, or maximum throughput today, start with vllm-mlx. If you're building for an enterprise context where the vLLM ecosystem alignment matters, or you want to track the official upstream path, vLLM Metal is the right choice. The security hardening and operational patterns in Parts 2 and 3 of this series apply to both — the `vllm serve` command is nearly identical.

---

## Hardware: What 64GB Actually Gets You

You've got a Mac Studio M4 with 64GB unified memory. Let's do the math on what fits.

**Models that work well on 64GB:**

| Model | Total Params | Active Params | Memory (approx) | License |
|---|---|---|---|---|
| Llama 3.2 3B Instruct | 3B | 3B | ~6GB (FP16) | Llama 3.2 CL |
| Qwen 2.5 7B Instruct | 7B | 7B | ~14GB (FP16) | Apache 2.0 |
| gpt-oss-20b (MXFP4) | 21B | ~3.6B | ~16GB | Apache 2.0 |
| gpt-oss-20b (MLX 4-bit) | 21B | ~3.6B | ~11GB | Apache 2.0 |

A quick note on gpt-oss-20b's "Active Params." It's a Mixture-of-Experts model. 21 billion parameters total, but only a fraction are active for any given token. OpenAI reports 3.6B active parameters; NVIDIA lists 4B. The difference likely reflects rounding or whether shared layers are counted. Either way, the routing network picks which experts to use for each input. This is why it's fast despite being "21B": most of the model is sleeping at any given moment. Very relatable.

**Memory bandwidth matters too.** The M4 Max in the Mac Studio (64GB config) pushes about 546 GB/s of memory bandwidth. Token generation speed is largely bandwidth-bound (you need to read the model weights for each token). Rough napkin math: 11GB of weights at 546 GB/s means you can theoretically read the full model ~50 times per second. In practice, expect 20-50 tokens/sec depending on the model and batch size. Not H100 speeds, but very usable for a local chatbot.

---

## Compliance Context

For when your CISO asks "but is this allowed?"

| Concern | Status | Why |
|---|---|---|
| Data residency | On-prem | All tokens processed and stored on the Mac Studio |
| Need a DPA? | No | No third-party data processor involved |
| Model transparency | Full | Open weights, documented architecture |
| CoT auditability | Available | gpt-oss-20b exposes full reasoning trace |
| EU AI Act | Check | Deployer obligations still apply |

**On GDPR Article 25 (Privacy by Design).** Local inference is a strong foundation for Art. 25 compliance, but it's not the whole story. Art. 25 requires both *technical* and *organizational* measures. Running inference on localhost solves data residency and eliminates third-party processor risk. But a complete Art. 25 implementation also needs logging policies (what gets logged, how long it's retained), access control (who can query the model), deletion concepts (how to purge conversation data on request), and data minimization (collecting only what's necessary). This setup gives you the technical foundation. Your governance framework provides the organizational half.

**Good fit:** Prototyping with regulated data. Internal dev tools. Compliance environments (BaFin, healthcare, defense). Demos where you need to prove "nothing leaves the room."

**Bad fit:** More than ~5 concurrent users. Models bigger than ~30B dense params. Sub-100ms latency requirements. If you need gpt-oss-120b (~80GB, exceeds our 64GB).

| | This setup | Azure OpenAI | AWS Bedrock |
|---|---|---|---|
| Data leaves premises | No | Yes | Yes |
| Hardware cost | ~3K one-time | Per-token | Per-token |
| Monthly cost after HW | ~30 electricity | 100-10K+ | 100-10K+ |
| Concurrent users | 1-5 | Unlimited | Unlimited |
| Time to first request | 30 min (Part 2) | Hours (procurement) | Hours |
| Auditability | Full stack | Partial | Partial |

*Hardware cost excludes amortization, admin overhead, and opportunity cost. Assumes single-admin setup with no dedicated ops team. Cloud costs vary wildly with usage volume.*

---

## Known Limitations

**vllm-metal is v0.1.0.** Young project, fast-moving, expect breaking changes. The community is active (the project is led by Eric Curtin at Docker, Inc), but this isn't enterprise-stable software yet. The governance argument above is about trajectory, not current state.

**MoE support is the open question.** gpt-oss-20b uses a Mixture-of-Experts architecture with MXFP4 quantization. Whether vllm-metal's MLX backend handles MoE expert routing correctly is unconfirmed as of February 2026. The proven path is **Llama 3.2 3B Instruct**, which works reliably on vLLM Metal today. gpt-oss-20b is the aspirational target. Part 2 covers both paths: Llama 3.2 3B as the primary walkthrough, gpt-oss-20b as the bonus if MoE support works for you.

**Performance reality check.** M4 Max memory bandwidth (~546 GB/s) vs H100 (~3.35 TB/s). That's 6x less. Expect 20-50 tokens/sec, not 200+. Fine for chat. Not fine for batch processing. And as the comparison table above shows, vllm-mlx currently outperforms vllm-metal in published benchmarks — the trade-off is ecosystem alignment for measured throughput.

**On the M5.** Apple claims 4x peak GPU compute for AI (base M5 vs M4). That's raw compute, not inference throughput. The base M5 has 153 GB/s memory bandwidth, less than M4 Pro's 273 GB/s. An M5 Pro/Max for inference workloads hasn't been announced yet. File under "promising but speculative."

**If vllm-metal doesn't work for your use case**, the alternatives are well-trodden:
- **vllm-mlx** (waybarrios): see comparison above — stronger today on features and throughput.
- **mlx-lm**: Apple's own inference library. No scheduler, but rock-solid for single-user workloads.
- **Ollama**: simplest path. `ollama pull gpt-oss:20b` and go.
- **llama.cpp (Metal)**: battle-tested, fast, widest quantization format support.

---

## What's Next

**Part 2** walks you through installation, model acquisition, verification, and building a working chatbot. Copy-pasteable commands, primary path on Llama 3.2 3B, bonus path on gpt-oss-20b.

**Part 3** covers security hardening (service accounts, firewall rules, supply chain awareness) and production ops (launchd services, integrity checks, monitoring).

> "If the weights live on your disk, the inference runs on your CPU/GPU, and the API binds to localhost, then no token ever leaves your machine."

---

This article reflects my professional perspective. Drafting was assisted by Claude, but the insights and final curation are entirely my own.

[Sovereign AI Strategist](https://www.linkedin.com/in/michaelhannecke/) @ [bluetuple.ai](https://www.bluetuple.ai) | Exploring autonomous AI systems, agentic architectures, and secure AI independence. Writing about what it takes to build AI that stays under your control.
