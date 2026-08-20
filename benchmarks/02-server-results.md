# 02 - Serve: load test + saturation reading

Host `Windows-AMD64` · llama.cpp `b10488` ·
`--parallel 4` · `ctx=2048` · `threads=8` ·
`ngl=99`

| Users | Reqs | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|:--|--:|--:|--:|--:|--:|--:|--:|
| 10 | 134 | 2.29 | 3300 | 5800 | 6900 | 7.9 | 0.0% |
| 50 | 155 | 2.60 | 17000 | 19000 | 20000 | 39.7 | 0.0% |

*Effective concurrency = RPS x average latency (Little's Law) -- how many requests were
really in flight, regardless of how many users locust simulated. It counts queued requests
too, so the occupancy/slot ratio can legitimately exceed 1.0; it is occupancy, not
utilisation. For true slot utilisation use the server's own gauges (`make metrics`).*

## What these two runs say

| Going from 10 to 50 users | |
|:--|--:|
| Offered load | 5x |
| Throughput actually delivered | **1.14x** (23% of linear) |
| P95 latency | **3.28x** |
| Effective concurrency at 50 users | 39.7 vs `--parallel 4` slots (occupancy/slot ratio 9.92) |

**Saturated.** Throughput delivered only 1.14x for 5x the offered load, and effective concurrency (39.7) is at or above all 4 decode slots. Saturation sets in somewhere at or below 50 users; the load you added beyond that point became queue time rather than throughput.

Throughput moved 1.14x while P95 moved 3.28x. That gap is the goodput argument: past saturation you buy throughput by spending latency, and if your SLO is a P95 target then the requests you added are no longer being served within it. (This lab does not fix an SLO number for you -- pick one in your write-up and state how much goodput you keep at it.)

## Your reading

The server is saturated well **at or below 50 users**. RPS barely moved (2.29 ->
2.60, 1.14x for 5x the offered load) while P95 grew 3.28x (5800ms -> 19000ms) and
effective concurrency at 50 users (39.7) sits nearly 10x the `--parallel 4` slot
count. A separate `make metrics` run sampled concurrently with `load-50` (see
`02-server-batching-u50.md`) showed `n_busy_slots_per_decode` pinned at 3.97 of 4
slots essentially the whole window, with `requests_deferred` sitting around 43-45
the entire time — that busy/deferred pair is the number that actually convinced me:
4 slots were continuously full and roughly 44 requests were queued behind them at
any moment, so P95 had nowhere to go but up while throughput had nowhere left to
grow. The added latency at 50 users is **queue time, not compute time** — decode
itself did not get slower, requests were standing in line for one of 4 slots.

**What I would change first: raise `--parallel`** (e.g. 4 -> 8), not threads or
quantization. The evidence points straight at slot count as the bottleneck: busy
slots were pinned at the ceiling while GPU decode itself is fast (61-79 tok/s
depending on run, see `01-quickstart-results.md` and REFLECTION §5) and VRAM has
headroom (a ~3 GB model on a 6 GB card). More slots let more requests share the
GPU's already-fast decode concurrently instead of queueing for it. I would not
reach for quantization first, since per-request decode speed was never the limiting
factor here, and CPU threads are close to irrelevant once decode runs on the GPU
(`-ngl 99`, flat thread-sweep in `01-tuning-tg128.md`). Caveat: each extra
`--parallel` slot reserves more KV cache out of the shared `--ctx-size`, so this
trades VRAM headroom for concurrency and would need re-testing at 8+ slots to
confirm it does not itself start truncating context or exhausting VRAM.
