# Bonus - GPU offload sweep

Host `Windows-AMD64` · backend(s) `nvidia_cuda, vulkan` ·
llama.cpp `b10488` · `threads=8` · metric `tg128`

| -ngl | tg128 (tok/s) | vs -ngl 0 | vs best |
|:--|--:|--:|--:|
| 0 | 11.9 | 1.00x | 17% |
| 8 | 14.2 | 1.20x | 20% |
| 16 | 19.6 | 1.65x | 28% |
| 24 | 34.0 | 2.86x | 48% |
| 32 | 54.9 | 4.62x | 77% |
| 99 | 70.9 | 5.97x | 100% |

Best: `-ngl 99` at 70.9 tok/s
-- 5.97x faster than CPU-only.

Where the curve flattens tells you the model ran out of layers to move. Where it
*peaks below* full offload tells you something did not fit and the accelerator
started paying to fetch weights it could not hold.

## Your finding

Full offload (`-ngl 99`) is unambiguously best on this machine: 70.9 tok/s, and the
curve never plateaus or dips before it — it climbs the whole way, with the *steepest*
gains in the second half (24->32: +1.76x, 32->99: +1.29x) rather than the first
(0->8: +1.20x, 8->16: +1.65x). Nothing ran out; the model (2.97 GB) fits comfortably
in the RTX 4050's 6 GB VRAM with room to spare, so this is not a "ran out of VRAM"
curve at all.

The shape makes sense once you think about which side is the bottleneck at each
point. At low `-ngl`, most layers still run on the CPU, which is the slow path
(10.89-14.2 tok/s territory from both this sweep and REFLECTION §5) — moving 8 or 16
of ~35 layers to the GPU barely helps because the *CPU-side work* is still the long
pole, and every token now additionally pays a host<->device transfer for activations
crossing the CPU/GPU boundary each layer. Only once enough layers have moved that the
remaining CPU portion stops being the bottleneck does total throughput start tracking
the GPU's speed instead of the CPU's — which is why the back half of the sweep
(24->32->99) shows accelerating, not diminishing, returns: each additional offloaded
layer chunk was removing time from the now-dominant CPU segment, not adding marginal
value to an already-fast GPU segment. Partial offload is worse than either pure mode
here because it pays the cross-device sync cost on top of still being bounded by
whichever side is slower — full offload is the only point on the curve that avoids
both penalties at once.
