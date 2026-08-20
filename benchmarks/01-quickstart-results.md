# 01 - Measure: latency baseline

Model `Gemma 4 E2B` · host `Windows-AMD64` · llama.cpp `b10488`
Settings: `threads=8` `ngl=99` `ctx=2048`
`max_tokens=64` · warm-up discarded
Completed requests: `UD-Q4_K_XL` 10/10 · `UD-Q2_K_XL` 10/10

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|:--|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 4065 | 234 / 369 | 13.3 / 13.7 | 1060 / 1203 / 1203 | 75.3 |
| UD-Q2_K_XL | 2.24 | 4362 | 234 / 378 | 12.7 / 13.0 | 1037 / 1175 / 1175 | 78.8 |

- **TTFT** = prefill. Short prompts keep it small; long-context RAG is where it explodes.
- **TPOT** = per-output-token decode cost, bounded by memory bandwidth. `decode tok/s = 1000 / TPOT_p50`.
- `UD-Q2_K_XL` decodes **1.05x faster** than `UD-Q4_K_XL` here, for 0.73 GB less on disk.

## Your observation

`UD-Q2_K_XL` decodes slightly faster (1.05x, 78.8 vs 75.3 tok/s) and is 0.73 GB
smaller, but on a real quality check it is **not worth it** for this model. I served
both and asked the identical question "Explain what a KV cache is, in 3 short
sentences.":

- **Q4_K_XL**: "A KV cache is a memory optimization technique used primarily in large
  language models during inference. It stores the key and value vectors computed
  during the attention mechanism to avoid redundant recalculations. This significantly
  speeds up the generation process by reusing previously computed attention states."
  — correct.
- **Q2_K_XL**: "A Key-Value (KV) cache is a high-speed, in-memory data structure used
  in machine learning, particularly for **training** large neural networks. It stores
  frequently accessed data, like **weights** or intermediate results..." — factually
  wrong on two counts: KV cache is an *inference*-time technique, not training, and it
  caches attention key/value tensors, not model weights.

A ~1.05x speedup does not offset a technical answer becoming actively misleading.
For this model/task, `UD-Q4_K_XL` is the one worth shipping; `UD-Q2_K_XL` would only
make sense under real memory pressure (e.g. RAM-constrained cloud fallback), not for
a 6 GB-VRAM laptop that already fits the 4-bit weights comfortably.

(Note: this table's absolute numbers are from a re-run of `make bench`, taken after
several hours of GPU warm-up and OS page-cache priming from earlier sweeps in this
session — TTFT in particular dropped a lot vs. the very first cold run. The
before/after used in REFLECTION section 5 is unaffected, since it comes from a
separate `llama-bench` A/B measured back-to-back on the same warm machine.)
