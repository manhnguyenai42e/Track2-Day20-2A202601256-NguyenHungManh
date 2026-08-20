# 01 - Measure: latency baseline

Model `Gemma 4 E2B` · host `Windows-AMD64` · llama.cpp `b10488`
Settings: `threads=8` `ngl=99` `ctx=2048`
`max_tokens=64` · warm-up discarded
Completed requests: `UD-Q4_K_XL` 10/10 · `UD-Q2_K_XL` 10/10

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|:--|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 6762 | 436 / 2022 | 16.2 / 22.1 | 1548 / 3109 / 3109 | 61.7 |
| UD-Q2_K_XL | 2.24 | 4925 | 1046 / 1579 | 14.3 / 15.6 | 1940 / 2528 / 2528 | 69.7 |

- **TTFT** = prefill. Short prompts keep it small; long-context RAG is where it explodes.
- **TPOT** = per-output-token decode cost, bounded by memory bandwidth. `decode tok/s = 1000 / TPOT_p50`.
- `UD-Q2_K_XL` decodes **1.13x faster** than `UD-Q4_K_XL` here, for 0.73 GB less on disk.

## Your observation

`UD-Q2_K_XL` decodes 1.13x faster (69.7 vs 61.7 tok/s) and is 0.73 GB smaller, but on
a real quality check it is **not worth it** for this model. I served both and asked
the identical question "Explain what a KV cache is, in 3 short sentences.":

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

A 1.13x speedup does not offset a technical answer becoming actively misleading. For
this model/task, `UD-Q4_K_XL` is the one worth shipping; `UD-Q2_K_XL` would only make
sense under real memory pressure (e.g. RAM-constrained cloud fallback), not for a
6 GB-VRAM laptop that already fits the 4-bit weights comfortably.
