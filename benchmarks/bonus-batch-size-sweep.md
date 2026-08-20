# Bonus - Batch-size sweep (chunked prefill)

Host `Windows-AMD64` · llama.cpp `b10488` ·
`threads=8` `ngl=99` · metric `pp512`

| -b (logical) | -ub (micro) | pp512 (tok/s) | vs best |
|:--|--:|--:|--:|
| 128 | 128 | 3089.2 | 82% |
| 256 | 256 | 3667.0 | 97% |
| 512 | 256 | 3781.3 | 100% |
| 512 | 512 | 3599.3 | 95% |
| 1024 | 512 | 3582.8 | 95% |
| 2048 | 512 | 3535.0 | 93% |

Best: `-b 512 -ub 256` at 3781.3 tok/s
(1.22x the slowest point tested).

This sweep only measures the throughput half of the trade. The cost it hides is
TTFT for queued requests: a larger micro-batch holds the device longer per step,
so anything waiting behind it waits longer. To see both halves, re-run
`make load-50` with your best and worst settings via
`.venv/bin/python labs/02-serve/serve.py -- -b N -ub M` and compare P95.

## Your finding

I would **not** ship the raw winner (`-b 512 -ub 256`, 3781 tok/s) just because it
tops the table — it beats the next two candidates (`-b 256 -ub 256` at 97%, `-b 512
-ub 512` at 95%) by only 3-5%, and the table only measures throughput. Given what
§3 already found on this server — saturation at 50 users was caused by **queueing
behind 4 slots**, and P95 blew up 4.44x while throughput barely moved — a bigger
micro-batch (`-ub`) is the same failure mode at a smaller scale: it holds the GPU for
longer per decode step, so every other request's next token is delayed by however
long that step takes. A 3-5% throughput win is not worth trading away queued-request
latency for, especially once `--parallel` is raised (the change I'd try first from
§3) and more requests are actually competing for each step.

**What I would run:** `-b 256 -ub 256` — essentially tied for best (97% of peak
throughput) with a smaller micro-batch, so less time any one decode step can hold up
requests waiting behind it.

**What I would measure to be sure:** re-run `make load-50` twice, once at `-ub 256`
and once at `-ub 512` (via `.venv/bin/python labs/02-serve/serve.py -- -b 512 -ub
256` vs `-ub 512`), and compare **P95, not RPS**, from `benchmarks/02-server-results.md`
for each. If `-ub 512`'s P95 grows by more than its ~5% throughput edge over `-ub
256`, that confirms the larger micro-batch is trading tail latency for a throughput
number that will not survive contact with a loaded server — the same goodput@SLO
argument from §3, just applied to a different knob.
