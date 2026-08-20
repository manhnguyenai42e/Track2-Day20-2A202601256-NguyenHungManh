# 02 - Serve: load test + saturation reading

Host `Windows-AMD64` · llama.cpp `b10488` ·
`--parallel 4` · `ctx=2048` · `threads=8` ·
`ngl=99`

| Users | Reqs | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|:--|--:|--:|--:|--:|--:|--:|--:|
| 10 | 86 | 1.46 | 5600 | 8100 | 10000 | 8.4 | 0.0% |
| 50 | 83 | 1.38 | 29000 | 36000 | 38000 | 34.5 | 0.0% |

*Effective concurrency = RPS x average latency (Little's Law) -- how many requests were
really in flight, regardless of how many users locust simulated. It counts queued requests
too, so the occupancy/slot ratio can legitimately exceed 1.0; it is occupancy, not
utilisation. For true slot utilisation use the server's own gauges (`make metrics`).*

## What these two runs say

| Going from 10 to 50 users | |
|:--|--:|
| Offered load | 5x |
| Throughput actually delivered | **0.94x** (19% of linear) |
| P95 latency | **4.44x** |
| Effective concurrency at 50 users | 34.5 vs `--parallel 4` slots (occupancy/slot ratio 8.62) |

**Saturated.** Throughput delivered only 0.94x for 5x the offered load, and effective concurrency (34.5) is at or above all 4 decode slots. Saturation sets in somewhere at or below 50 users; the load you added beyond that point became queue time rather than throughput.

Throughput moved 0.94x while P95 moved 4.44x. That gap is the goodput argument: past saturation you buy throughput by spending latency, and if your SLO is a P95 target then the requests you added are no longer being served within it. (This lab does not fix an SLO number for you -- pick one in your write-up and state how much goodput you keep at it.)

## Your reading

The server is saturated well **at or below 50 users**, and three independent numbers
agree: (1) RPS barely moved, 1.46 -> 1.38, actually *slightly down* for 5x the offered
load; (2) `make metrics`, sampled while `load-50` was running, showed
`n_busy_slots_per_decode` pinned at **3.97 of 4 slots** almost the entire 60s window --
every decode slot was doing useful work essentially continuously; (3) the same window
showed `requests_deferred` sitting around **43-45** the whole time, meaning roughly 44
requests were queued behind the 4 busy slots at any given moment. That is the number
that convinced me: with 4 slots occupied and ~44 requests waiting, P95 has nowhere to
go but up, and it went up 4.44x (8.1s -> 36s) while throughput moved essentially
nothing. The added latency at 50 users is **queue time, not compute time** -- the
per-token decode cost measured in `01-quickstart-results.md` did not change; requests
were simply standing in line for one of 4 slots.

**What I would change first: raise `--parallel`** (e.g. 4 -> 8), not threads or
quantization. The bottleneck evidence points straight at slot count: busy_slots was
pinned at the slot ceiling while GPU decode itself is fast (68.8 tok/s at `ngl=99`,
see REFLECTION §5) and VRAM has headroom (2.97 GB model on a 6 GB card). Raising
`--parallel` lets more requests share the GPU's already-fast decode throughput
concurrently instead of queueing for it, which is the direct fix for a
slot-occupancy bottleneck. I would *not* reach for quantization first -- decode speed
per request was never the limiting factor here, slot count was -- and I would not
reach for CPU threads either, since decode already runs on the GPU (`-ngl 99`) where
CPU thread count is close to irrelevant (see the flat thread-sweep in
`01-tuning-tg128.md`). The one caveat: each extra `--parallel` slot reserves more KV
cache out of the shared `--ctx-size`, so this trades VRAM headroom for concurrency and
would need re-testing to confirm it does not itself start truncating context or
running out of VRAM at 8+ slots.
