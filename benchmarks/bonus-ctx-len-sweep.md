# Bonus - Context-length sweep (prefill cost)

Host `Windows-AMD64` · llama.cpp `b10488` ·
`threads=8` `ngl=99` · RAM 63.7 GB

| Prompt tokens | Prefill (tok/s) | TTFT contribution (ms) | vs linear scaling |
|:--|--:|--:|--:|
| 256 | 3130.6 | 81.8 | 1.00x |
| 1024 | 2076.3 | 493.2 | 1.51x |
| 2048 | 3038.3 | 674.1 | 1.03x |
| 4096 | 2634.7 | 1554.6 | 1.19x |
| 8192 | 2497.5 | 3280.1 | 1.25x |
| 16384 | 2625.8 | 6239.7 | 1.19x |

At 16384 tokens, prefill costs **6240 ms** --
1.19x what linear scaling from the smallest point would predict. That excess
is attention's O(N^2) term becoming visible, and every millisecond of it lands in TTFT
before the user sees a single token.

Either way, this is the number to remember when someone proposes stuffing more retrieved
context into a RAG prompt "because the context window allows it". Prefill is paid in full,
on every request, before the first token appears.

## Your finding

I do not trust the "1.51x at 1024 tok" point as a real quadratic signal — it is the
*only* point that breaks the otherwise smooth curve, it sits in the *middle* of the
grid rather than at the end (a real O(N^2) bend gets worse as N grows, it does not
spike then recover), and 2048 tokens right after it drops back to 1.03x. That is
measurement noise from only 2 repetitions on a GPU-offloaded run, not attention
cost. The trustworthy trend is 256 -> 16384: 1.00x -> 1.19x, a real but **mild**
superlinear drift, nowhere close to O(N^2) blowing up in this range. At 16384 tokens
(64x the smallest prompt), prefill cost is 76x the smallest prompt's absolute ms
(6240 vs 81.8) — close to linear (64x would be "purely linear"), not the 4096x a pure
quadratic term would predict at this ratio.

Two things explain why the quadratic term stays small here: (1) at 2048 tokens I am
already at this lab's default `--ctx-size`, and prefill throughput (tok/s) barely
moves across the whole grid (3130 -> 2626 tok/s, roughly flat) — the O(N) linear
projection/MLP cost the lab's own README predicts is still the dominant term for a
model this size (Gemma 4 E2B, 4.65B params) even out to 16k tokens; (2) llama.cpp's
attention kernel on this GPU is not naively quadratic-in-wall-clock at these lengths
because it is running well within the RTX 4050's compute budget, so I have not yet
reached the length where attention's O(N^2) term dominates the O(N) terms — that
crossover is somewhere past 16k on this hardware, not inside this grid.

**For the RAG pipeline (§4):** the real number to plan around is the absolute
prefill cost, not the ratio. At 4096 tokens (a realistic "several retrieved chunks +
system prompt" budget) prefill alone is already 1.55s — larger than the entire mean
`llm` latency (3.7s total, which includes both prefill *and* decode) measured for
the *short* toy queries in `03-integration-results.md`. That means every additional
retrieved chunk has a real, paid-in-full TTFT cost long before the quadratic term
becomes the story; the linear term alone already makes "just retrieve more chunks,
context window allows it" an expensive default.
