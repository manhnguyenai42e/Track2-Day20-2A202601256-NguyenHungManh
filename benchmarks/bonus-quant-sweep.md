# Bonus - Quantization sweep (Gemma 4 E2B, Unsloth Dynamic ladder)

Host `Windows-AMD64` · llama.cpp `b10488` ·
`threads=8` `ngl=99` · metric `tg128`

| Quantization | Size (GB) | tg128 (tok/s) | vs UD-Q4_K_XL | tok/s per GB |
|:--|--:|--:|--:|--:|
| UD-Q2_K_XL | 2.24 | 55.6 | 0.74x | 24.8 |
| UD-Q4_K_XL | 2.97 | 74.9 | 1.00x | 25.2 |
| UD-Q6_K_XL | 4.39 | 57.7 | 0.77x | 13.1 |

Decode is memory-bandwidth-bound, so fewer bytes per weight usually means more
tokens per second -- the "tok/s per GB" column shows how much of that you are
actually getting back per gigabyte spent.

Speed is only half the trade. The other half is quality, and no benchmark here
measures it. Serve two of these (`make serve` and
`.venv/bin/python labs/02-serve/serve.py --compare`) and ask each the same three questions
before you claim a winner.

## Your finding

I would ship **UD-Q4_K_XL** — and this ladder is exactly why the naive "smaller =
faster on a bandwidth-bound decode" story breaks here: throughput is **not
monotonic** in size. UD-Q2_K_XL (2.24 GB, smallest) decodes at 55.6 tok/s, but
UD-Q4_K_XL (2.97 GB, *larger*) is fastest at 74.9 tok/s, and UD-Q6_K_XL (4.39 GB,
largest) drops back to 57.7 tok/s — worse than the mid-size point despite moving
nearly 2x the bytes of Q4. If bytes-moved were the whole story, Q2 should have won.

The "tok/s per GB" column makes the real story visible: Q2 and Q4 both land near
~25 tok/s/GB, but Q6 drops to 13.1 — less than half. That points at the
**dequantization kernel**, not raw bandwidth, as the second variable. Unsloth
Dynamic quants are mixed-precision (different bit-widths per layer, not a uniform
2/4/6-bit cast), so each quant level runs through a different CUDA dequant kernel
with its own per-weight unpacking cost. Q2's kernel evidently has enough
unpack/branch overhead per weight to eat back its bandwidth advantage over Q4, and
Q6's is worse still. This matches the quality finding from `01-quickstart-results.md`
too: Q2 was already the "not worth it" quant on correctness grounds (wrong answer to
the KV-cache question); this sweep now shows it is not even the speed winner either.
UD-Q4_K_XL wins on both axes on this machine, so that is where I stop — I did not
observe a quality break beyond what was already documented for Q2 in the base track.
