# Bonus C6 / B4 / B5 - Vulkan vs CUDA on the same GPU

Host `Windows-AMD64` · GPU `NVIDIA GeForce RTX 4050 Laptop GPU` (6 GB VRAM) ·
Model `gemma-4-E2B-it-UD-Q4_K_XL.gguf` (2.95 GiB, 4.65 B params) ·
`threads=8` `ngl=99` (full offload, both backends) · metric `tg128` · 3 repetitions

No compiler needed for this comparison: llama.cpp ships **both** a CUDA and a Vulkan
prebuilt binary for Windows x64 (`llama-b10488-bin-win-cuda-12.4-x64.zip` and
`llama-b10488-bin-win-vulkan-x64.zip`), so both sides of this test are prebuilt
releases, same build `b10488`, same commit, same model file, same `-ngl 99`.

**Gotcha caught mid-test:** this laptop's Vulkan backend enumerates **two** devices —
`Vulkan0 = Intel(R) UHD Graphics` (integrated) and `Vulkan1 = NVIDIA RTX 4050 Laptop
GPU` (discrete). `llama-bench`'s default `--main-gpu 0` silently picked the Intel
iGPU, producing an apples-to-oranges 22.3 tok/s that would have made the comparison
meaningless. Fixed with `-dev Vulkan1` to force the same RTX 4050 the CUDA run used.

| Backend | Device | tg128 (tok/s) | Relative |
|:--|:--|--:|--:|
| CUDA | RTX 4050 (only device CUDA sees) | 66.9 ± 3.4 | 1.00x |
| Vulkan (wrong device, default `-mg 0`) | Intel UHD Graphics (iGPU) | 22.3 ± 1.1 | 0.33x — not a real GPU comparison |
| Vulkan (`-dev Vulkan1`, correct) | RTX 4050 | 28.3 ± 7.6 | 0.42x |

**On the same physical GPU, CUDA is 2.36x faster than Vulkan** (66.9 vs 28.3 tok/s).

## Why: vendor-specific kernels vs a shared cross-vendor API

CUDA and Vulkan are not the same distance from the hardware. CUDA is NVIDIA's own
compute API — llama.cpp's CUDA backend (`ggml-cuda.dll`) ships hand-tuned kernels
(matrix-multiply, dequantization, attention) written and profiled specifically
against NVIDIA's warp scheduler, tensor cores, and memory hierarchy for each compute
capability (this card: 8.9, Ada Lovelace). The Vulkan backend has to work across
*every* vendor's GPU — AMD, Intel, NVIDIA, mobile Mali/Adreno — through one shared
compute-shader abstraction, so its kernels target the lowest common denominator of
what SPIR-V compute shaders can express portably, not this specific card's tensor
cores. The device listing itself shows the gap: Vulkan reports `matrix cores: none`
for the Intel iGPU but `matrix cores: KHR_coopmat` for the RTX 4050 — Vulkan *can* see
that this GPU has cooperative-matrix (tensor-core-like) hardware, but going through
`KHR_coopmat` is still a portable extension path, not NVIDIA's native tensor-core
instruction set that CUDA's kernels call directly.

This is the same trade-off the deck's FA3-vs-FA4-vs-TRTLLM-MHA discussion makes at
datacenter scale: vLLM and SGLang ship separate attention kernels per accelerator
generation (FA3 for Hopper, FA4 for Blackwell, FlashMLA, TRTLLM-MHA) instead of one
generic path, because a kernel that assumes a specific SM architecture, warp size, and
memory hierarchy can use instructions and scheduling tricks that a portable API
cannot express. Vulkan's `KHR_coopmat` here is the small-scale version of "the
portable path leaves real hardware capability on the table" — 2.36x of it, on this
card, for this workload. A shared-API approach buys you one binary that runs on any
GPU vendor (which is exactly why the lab's prebuilt default falls back to Vulkan on
hardware with no CUDA release, or on Linux where llama.cpp ships no CUDA binary at
all); a vendor-specific path buys you the performance that portability leaves behind.
Production serving engines pick per-request winner: use the vendor kernel when you
know the hardware (CUDA here, or FA3/FA4 at datacenter scale), and reserve the
portable path for whatever you cannot pin down in advance.

## What this means for this lab's config

The lab's own `make setup` already made the right call for this machine without being
told to: hardware detection preferred `cuda` over `vulkan` in `hardware.json`, so every
number reported elsewhere in this submission (`01-quickstart-results.md`,
`01-tuning-tg128.md`, `02-server-results.md`) already used the 2.36x-faster CUDA path.
The GPU-offload story in REFLECTION §5 (10.89 -> 68.8-70.9 tok/s, ~6.3-6.0x) is CPU vs
CUDA; had this laptop been Linux (where upstream ships no CUDA release and Vulkan is
the default fallback) or had `make setup` picked Vulkan, that same offload win would
have landed at roughly `10.89 -> ~28` tok/s instead — still a large win, just a
noticeably smaller one, entirely because of the backend, not the accelerator decision
itself.
