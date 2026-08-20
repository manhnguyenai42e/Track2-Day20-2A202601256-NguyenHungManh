# 01 - Tune: thread-count sweep

Model `gemma-4-E2B-it-UD-Q4_K_XL.gguf` · host `Windows-AMD64` · llama.cpp `b10488`
CPU: **8 physical · 12 logical** cores · `ngl=99` · metric `tg128`

| threads (-t) | tg128 (tok/s) | vs best |
|:--|--:|--:|
| 1 | 75.1 | 94% |
| 4 | 75.3 | 94% |
| 8 | 78.9 | 99% |
| 12 | 79.5 | 99% |
| 24 | 80.1 | 100% |

**Best**: `-t 24` at 80.1 tok/s
**Slowest tested**: `-t 1` at 75.1 tok/s (1.07x spread)
**Against the physical-core default** (`-t 8`, 78.9 tok/s): 1.02x

Use this in your run:

```bash
LAB_N_THREADS=24 make bench
```

## Your explanation

The curve is **flat, not a knee**: 75.1 tok/s at `-t 1` up to 80.1 tok/s at `-t 24`,
a total spread of only 1.07x across a 24x range of thread counts. That contradicts the
deck's default expectation (throughput climbs to the physical core count, then drops
as threads fight over shared memory bandwidth) — but only because that expectation is
for **CPU-only** decode, and mine is not.

`hardware.json`/`make probe` picked up my RTX 4050 Laptop GPU, and `make bench`/`tune`
run with `-ngl 99`, i.e. every transformer layer is offloaded to the GPU. The actual
matrix multiplies that dominate decode cost happen on the GPU's own compute units and
are bound by **GPU memory bandwidth (VRAM)**, not CPU threads at all. The CPU threads
`llama-bench` is sweeping here only do light glue work between GPU calls — sampling,
KV-cache bookkeeping, dispatching the next batch — none of which is expensive enough
for more of them to matter. That is why 1 thread and 24 threads land within noise of
each other: I am not testing the bottleneck, because CPU threads stopped being the
bottleneck the moment `-ngl 99` moved decode onto the GPU.

The one real signal in the table is that `tg128` still edges up slightly past the
12 logical-core count (24 threads: 80.1 tok/s, the max) instead of dropping off — the
oversubscription penalty the deck describes for CPU-bound decode never appears, again
because there is no CPU memory-bandwidth contention to oversubscribe. If I wanted to
see the classic knee shape, I would need to force CPU-only decode (`LAB_N_GPU_LAYERS=0
make tune`) and re-sweep — GPU offload is the actual "single change that mattered
most" on this machine, not thread count (see REFLECTION §5).
