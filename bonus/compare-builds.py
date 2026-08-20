#!/usr/bin/env python3
"""BONUS B1 - Does compiling it yourself actually beat the prebuilt binary?

The prebuilt release you have been using all lab is compiled for a generic
baseline CPU, because it has to run on every machine that downloads it. Your
source build with -DGGML_NATIVE=ON is compiled for *your* CPU specifically, and
can use whatever vector extensions it actually has (AVX2, AVX-512, NEON).

This runs the same llama-bench workload through both binaries and reports the gap.
On CPU-only laptops the gap is usually the largest single win available in this
lab -- which is why the bonus track favours weaker hardware.

    make build-llama      # clone + compile (5-15 min)
    make compare-builds
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import labkit  # noqa: E402


def prebuilt_bench() -> pathlib.Path | None:
    """llama-bench from runtime/ only, ignoring the source build."""
    exe = "llama-bench.exe" if sys.platform == "win32" else "llama-bench"
    root = labkit.runtime_dir()
    if not root.exists():
        return None
    for cand in sorted(root.rglob(exe)):
        if cand.is_file():
            return cand
    return None


def run(bench: pathlib.Path, model: str, threads: int, ngl: int, metric: str, reps: int) -> float:
    is_prefill = metric.startswith("pp")
    shape = ["-p", metric[2:], "-n", "0"] if is_prefill else ["-p", "0", "-n", "128"]
    proc = subprocess.run(
        [str(bench), "-m", model, "-t", str(threads), "-ngl", str(ngl), *shape, "-r", str(reps)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, timeout=1800,
    )
    return labkit.bench_metric(proc.stdout + proc.stderr, metric)


def version_of(binary: pathlib.Path) -> str:
    proc = subprocess.run([str(binary), "--version"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    text = (proc.stdout + proc.stderr).strip().splitlines()
    return text[0] if text else "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Prebuilt vs source-built llama.cpp (bonus B1).")
    ap.add_argument("--metric", default="tg128", help="tg128 = decode, pp512 = prefill")
    ap.add_argument("--reps", type=int, default=3)
    args = ap.parse_args()

    pre = prebuilt_bench()
    src = labkit.source_build_bin("llama-bench")
    if not pre:
        labkit.die("No prebuilt llama-bench in runtime/.", "Run: make setup")
    if not src:
        labkit.die(
            "No source build found at bonus/llama.cpp/.",
            "Build it first: make build-llama",
        )

    hw = labkit.load_hardware()
    model = str(labkit.repo_root() / labkit.load_active()["primary_model"])
    threads = labkit.threads(hw)
    # B1 asks a COMPILER question, so both binaries must run on the same backend.
    # The prebuilt asset and your source build often differ there -- upstream ships
    # no Linux CUDA build, so an NVIDIA box gets Vulkan (frequently with no ICD, i.e.
    # CPU) while a -DGGML_CUDA=ON source build offloads. Benchmarking those two at
    # -ngl 99 measures the accelerator and prints it under a "-DGGML_NATIVE=ON"
    # headline. Pin both to CPU; report any offload separately below.
    ngl = 0
    pre_dev, src_dev = labkit.visible_devices(pre), labkit.visible_devices(src)
    backends_differ = bool(pre_dev) != bool(src_dev)
    cpu = hw.get("cpu", {})
    exts = [n for n, k in (("AVX-512", "avx512"), ("AVX2", "avx2"), ("NEON", "neon"))
            if cpu.get(k)]

    labkit.banner(f"Prebuilt vs source build ({args.metric})")
    print(f"  model   : {pathlib.Path(model).name}")
    print(f"  threads : {threads}   ngl: {ngl}")
    print(f"  CPU     : {cpu.get('model', '?')}  [{', '.join(exts) or 'no vector extensions detected'}]")
    print(f"\n  prebuilt: {pre.relative_to(labkit.repo_root())}")
    print(f"            {version_of(pre)}")
    print(f"  source  : {src.relative_to(labkit.repo_root())}")
    print(f"            {version_of(src)}\n")

    print(f"  devices : prebuilt {pre_dev or ['(none - CPU)']}")
    print(f"            source   {src_dev or ['(none - CPU)']}")
    if backends_differ:
        print("  NOTE    : the two binaries do NOT share a backend. Pinning both to")
        print("            -ngl 0 so this measures the compiler, not the accelerator.")
    print()

    print("  running prebuilt   (-ngl 0) ...", flush=True)
    a = run(pre, model, threads, ngl, args.metric, args.reps)
    print(f"    {a:.1f} tok/s")
    print("  running source build (-ngl 0) ...", flush=True)
    b = run(src, model, threads, ngl, args.metric, args.reps)
    print(f"    {b:.1f} tok/s")

    # Offload is a separate finding, reported as its own number so it can never be
    # mistaken for the compiler result.
    offload = 0.0
    if src_dev:
        print("  running source build (-ngl 99, offloaded) ...", flush=True)
        offload = run(src, model, threads, 99, args.metric, args.reps)
        print(f"    {offload:.1f} tok/s")

    if not a or not b:
        labkit.die("One of the binaries produced no number -- run each by hand to see why.")

    gain = b / a
    verdict = (
        f"the source build is **{gain:.2f}x faster**" if gain > 1.03 else
        f"the prebuilt binary is **{1 / gain:.2f}x faster**" if gain < 0.97 else
        "**they are within 3% -- no meaningful difference**"
    )

    table = labkit.md_table(
        ["Binary", "Built for", f"{args.metric} (tok/s)", "Relative"],
        [["prebuilt release", "runtime CPU dispatch", f"{a:.1f}", "1.00x"],
         ["your source build", f"this CPU (`-DGGML_NATIVE=ON`)", f"{b:.1f}", f"{gain:.2f}x"]],
    )
    offload_block = ""
    if offload:
        offload_block = f"""
### Separately: what GPU offload is worth on the same binary

`{args.metric}` on the source build at `-ngl 99` instead of `-ngl 0`:

| Source build | {args.metric} (tok/s) | vs its own CPU run |
|:--|--:|--:|
| `-ngl 0` (CPU) | {b:.1f} | 1.00x |
| `-ngl 99` (offloaded to {src_dev[0]}) | {offload:.1f} | {offload / b:.2f}x |

This number is **not** part of the B1 comparison above -- it is a different knob.
Reporting it separately is the point: a compiler flag and an accelerator are not
interchangeable explanations for a speedup.
"""
    mismatch_block = ""
    if backends_differ:
        mismatch_block = f"""
> **Backend mismatch, handled.** The prebuilt binary sees
> `{pre_dev or '(no devices)'}` and your source build sees `{src_dev or '(no devices)'}`.
> Left at `-ngl 99` this comparison would have measured the accelerator and printed
> it under a compiler headline, so both sides were pinned to `-ngl 0`.
"""
    md = f"""# Bonus B1 - Prebuilt vs source build

Host `{labkit.host_tag()}` · CPU `{cpu.get('model', '?')}`
Vector extensions detected: {', '.join(exts) or 'none'}
llama.cpp `{labkit.LLAMA_CPP_BUILD}` both sides · `threads={threads}` ·
**both pinned to `ngl=0`** so this isolates the compiler ·
metric `{args.metric}`, {args.reps} repetitions
{mismatch_block}
{table}

On this machine, {verdict}.

before: {a:.1f} tok/s (prebuilt release)
after:  {b:.1f} tok/s (source build, -DGGML_NATIVE=ON)
speedup: {gain:.2f}x

Same source revision, same model, same backend, same `-ngl` -- the only difference
is what the compiler was allowed to assume about the CPU.
{"A gap this small usually means the prebuilt binary already dispatches to the right kernels at runtime (releases ship one libggml-cpu-*.so per microarchitecture and pick via CPUID), or that this workload is bandwidth-bound rather than instruction-bound. Both are real findings -- say which one you think it is." if 0.97 <= gain <= 1.03 else ""}
{offload_block}

## Your explanation (required -- replace this line)

_Why did the gap come out this size on your CPU? Tie it to something concrete --
which extensions your CPU has, and whether this workload is limited by
instructions or by memory bandwidth. If the prebuilt binary won, explain how that
is possible._
"""
    out = labkit.write_report(f"bonus-build-compare-{args.metric}.md", md,
                              {"prebuilt_tok_s": a, "source_tok_s": b, "speedup": round(gain, 3)})
    print("\n" + md)
    print(f"==> Wrote {out.relative_to(labkit.repo_root())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
