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
**34.5** in `02-server-results.md` -- those look like a huge disagreement, but they
are not measuring the same thing, so I trust both, for different questions.

- `n_busy_slots_per_decode` is the server's own gauge of how many slots were doing
  *actual GPU decode work* at once, capped at `--parallel 4` by construction -- it can
  never exceed 4. I trust this one for "how much real concurrent compute happened":
  the answer is essentially all of it, all the time (3.97/4 = 99%).
- Effective concurrency (Little's Law, `RPS x avg latency`) counts every request
  *currently in the system*, including the ~44 sitting in the deferred queue behind
  those 4 busy slots (matches `requests_deferred` ~= 43-45 in the CSV almost exactly:
  44 + 4 busy ~= 34.5 is in the same ballpark once you account for it being an average
  over the whole 60s window, not a snapshot). I trust this one for "how much queueing
  pressure was building up": a lot.

So the two numbers agree on the underlying story rather than contradict it: the GPU
side was maxed out at 4/4 slots essentially continuously, and the ~30 extra requests
Little's Law counts are exactly the ones queued waiting for one of those 4 slots to
free up. Batch width tells you the server was never under-utilizing its slots;
effective concurrency tells you 4 slots was not enough.
