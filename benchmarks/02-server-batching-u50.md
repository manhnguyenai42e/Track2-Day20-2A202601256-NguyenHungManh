# 02 - Continuous batching under load (u50)

Host `Windows-AMD64` · `--parallel 4` · 12 samples over
60s at 2.0s intervals · raw CSV: `02-server-metrics-u50.csv`

| Gauge | Peak observed |
|:--|--:|
| `n_busy_slots_per_decode` (avg/decode) | 3.97 of 4 slots (99%) |
| `requests_processing` | 4 |
| `requests_deferred` | 45 |
| `kv_cache_usage_ratio` | n/a — not exported by llama.cpp `b10488` |
| `tokens_predicted_total` (final) | 9831 |

Highest sampled value was **3.97 of 4** slots. Note this gauge is llama.cpp's *average* busy slots per decode step, so the number below is the highest average we sampled, not an instantaneous maximum batch width. A peak near 1 means
requests were served one at a time -- either the load was too light to overlap, or
they arrived too far apart. A peak approaching `--parallel` means the scheduler was
genuinely packing concurrent requests into shared decode steps.
`requests_deferred` went above zero: more requests arrived than there were slots, so some waited. That wait is the queue time in your P95.

## Your observation

Peak batch width was **3.97 of 4 slots** here, vs. an effective concurrency of
**39.7** in `02-server-results.md` (re-measured after the base-track run, then again
for screenshots; earlier passes on this same machine read 34.5 and 38.7 — see note
below) -- those look like a huge disagreement, but they are not measuring the same
thing, so I trust both, for different questions.

- `n_busy_slots_per_decode` is the server's own gauge of how many slots were doing
  *actual GPU decode work* at once, capped at `--parallel 4` by construction -- it can
  never exceed 4. I trust this one for "how much real concurrent compute happened":
  the answer is essentially all of it, all the time (3.97/4 = 99%).
- Effective concurrency (Little's Law, `RPS x avg latency`) counts every request
  *currently in the system*, including the ~44 sitting in the deferred queue behind
  those 4 busy slots (matches `requests_deferred` ~= 43-45 in the CSV almost exactly:
  44 + 4 busy is in the same ballpark as 38.7 once you account for it being an average
  over the whole 60s window, not a snapshot). I trust this one for "how much queueing
  pressure was building up": a lot.

So the two numbers agree on the underlying story rather than contradict it: the GPU
side was maxed out at 4/4 slots essentially continuously, and the extra requests
Little's Law counts are exactly the ones queued waiting for one of those 4 slots to
free up. Batch width tells you the server was never under-utilizing its slots;
effective concurrency tells you 4 slots was not enough.

*Note on the effective-concurrency values:* this gauge table (`n_busy_slots`,
`requests_deferred`) is from the original `load-50` + `make metrics` run captured
together earlier in this session. `02-server-results.md`'s effective-concurrency
number was recomputed twice more from fresh `load-10`/`load-50` re-runs (done to
produce screenshots), landing at 38.7 and then 39.7 instead of the original 34.5 --
every run tells the same saturation story (throughput flat, P95 way up, concurrency
far above 4 slots), the exact figure just moves run-to-run the way this lab's README
says it will.
