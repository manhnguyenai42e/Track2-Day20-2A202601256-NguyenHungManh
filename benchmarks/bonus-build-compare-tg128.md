# Bonus B1 - Prebuilt vs source build

Host `Windows-AMD64` · CPU `12th Gen Intel(R) Core(TM) i5-12450H`
Vector extensions detected: none
llama.cpp `b10488` both sides · `threads=8` ·
**both pinned to `ngl=0`** so this isolates the compiler ·
metric `tg128`, 3 repetitions

> **Backend mismatch, handled.** The prebuilt binary sees
> `['CUDA0: NVIDIA GeForce RTX 4050 Laptop GPU (6140 MiB, 5075 MiB free)']` and your source build sees `(no devices)`.
> Left at `-ngl 99` this comparison would have measured the accelerator and printed
> it under a compiler headline, so both sides were pinned to `-ngl 0`.

| Binary | Built for | tg128 (tok/s) | Relative |
|:--|--:|--:|--:|
| prebuilt release | runtime CPU dispatch | 13.8 | 1.00x |
| your source build | this CPU (`-DGGML_NATIVE=ON`) | 12.7 | 0.92x |

On this machine, the prebuilt binary is **1.09x faster**.

before: 13.8 tok/s (prebuilt release)
after:  12.7 tok/s (source build, -DGGML_NATIVE=ON)
speedup: 0.92x

Same source revision, same model, same backend, same `-ngl` -- the only difference
is what the compiler was allowed to assume about the CPU.



## Your explanation

The prebuilt binary won, by a small but real margin (1.09x, outside measurement
noise territory). Two things explain how that is possible.

**First, "Vector extensions detected: none" above is a probe gap, not reality.**
`hardware.json` on this Windows/Intel box does not currently populate an
avx2/avx512 field, so this script has nothing to report — it is not saying the CPU
lacks them. The i5-12450H is 12th-gen Alder Lake and does support AVX2 (and
AVX-VNNI). More telling: every run of the *prebuilt* binary all lab long printed
`load_backend: loaded CPU backend from ...\ggml-cpu-alderlake.dll` — the release
already ships a **microarchitecture-specific** CPU kernel selected by CPUID
dispatch at runtime, not one generic least-common-denominator build. `-DGGML_NATIVE=ON`
on my own build targets the same instruction set that `ggml-cpu-alderlake.dll`
already targets, so there was no untapped vector-width headroom for my build to
claim — both binaries were already running on equivalent Alder-Lake-tuned code.

**Second, this workload is memory-bandwidth-bound, not instruction-bound**, which is
the same finding from every other measurement in this lab (`01-tuning-tg128.md`,
REFLECTION §5): decode has to stream the model's weights through memory for every
token, and once that transfer is the bottleneck, having better vectorized dot-product
instructions buys little — the CPU spends most of its time waiting on RAM, not
executing math. When the ceiling is bandwidth rather than FLOPs, a compiler flag that
only helps instruction throughput has almost nothing to work with, which is
consistent with a near-zero (and here slightly negative) net effect.

The 8% loss itself I attribute to noise and build-flag parity, not to `-DGGML_NATIVE`
making things worse: my local build used only `-DGGML_NATIVE=ON
-DCMAKE_BUILD_TYPE=Release`, while the official release CI likely applies additional
tuning (link-time optimization, a newer/pinned MSVC toolset, possibly PGO) that a
plain local `cmake --build` does not reproduce — and this measurement also ran on a
laptop that had been under sustained GPU/CPU load most of the session, so some of
the 8% may be thermal, not compiler. Either way, the headline result stands: on a
bandwidth-bound workload with an already-microarchitecture-tuned prebuilt binary,
compiling it myself bought nothing on this machine — a very different story from a
CPU-only laptop, which is exactly why the bonus README flags B1 as the biggest win
on *weak* hardware and not here.
