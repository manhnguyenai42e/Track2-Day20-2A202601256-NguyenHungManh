#!/usr/bin/env python3
"""Probe the laptop and write hardware.json.

Stdlib only -- this runs before any pip install. Every other track reads
hardware.json to pick thread counts, GPU offload, and the llama.cpp backend.
"""
from __future__ import annotations

import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "lib"))
import labkit  # noqa: E402


def run(cmd: list[str], timeout: int = 5) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, check=False)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 127, ""


def detect_cpu() -> dict:
    info = {"arch": platform.machine(), "cores_logical": os.cpu_count() or 1}
    if sys.platform == "darwin":
        rc, out = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        info["model"] = out.strip() if rc == 0 and out.strip() else "Apple Silicon"
        rc, out = run(["sysctl", "-n", "hw.physicalcpu"])
        info["cores_physical"] = int(out.strip()) if rc == 0 and out.strip().isdigit() else None
        info["apple_silicon"] = info["arch"] in ("arm64", "aarch64")
        info["neon"] = info["apple_silicon"]
    elif sys.platform.startswith("linux"):
        try:
            cpuinfo = pathlib.Path("/proc/cpuinfo").read_text()
            for line in cpuinfo.splitlines():
                if line.startswith("model name"):
                    info["model"] = line.split(":", 1)[1].strip()
                    break
            flags_line = next(
                (l for l in cpuinfo.splitlines() if l.startswith(("flags", "Features"))), ""
            )
            flags = flags_line.split(":", 1)[1].split() if ":" in flags_line else []
            info["avx2"] = "avx2" in flags
            info["avx512"] = any(f.startswith("avx512") for f in flags)
            info["neon"] = "neon" in flags or "asimd" in flags
            # Physical cores = unique (physical id, core id) pairs; fall back to logical.
            cores = {
                tuple(
                    l.split(":", 1)[1].strip()
                    for l in block.splitlines()
                    if l.startswith(("physical id", "core id"))
                )
                for block in cpuinfo.split("\n\n")
                if "core id" in block
            }
            info["cores_physical"] = len(cores) or None
        except OSError:
            info["model"] = "unknown"
    elif sys.platform == "win32":
        rc, out = run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor | Select-Object -First 1 "
             "Name,NumberOfCores | ConvertTo-Json -Compress)"],
            timeout=20,
        )
        if rc == 0 and out.strip().startswith("{"):
            try:
                data = json.loads(out.strip().splitlines()[-1])
                info["model"] = str(data.get("Name", "unknown")).strip()
                info["cores_physical"] = int(data.get("NumberOfCores") or 0) or None
            except (ValueError, KeyError):
                pass
    info.setdefault("model", "unknown")
    if not info.get("cores_physical"):
        info["cores_physical"] = info["cores_logical"]
    return info


def detect_ram_gb() -> float:
    if sys.platform == "darwin":
        rc, out = run(["sysctl", "-n", "hw.memsize"])
        if rc == 0 and out.strip().isdigit():
            return round(int(out.strip()) / 1024**3, 1)
    elif sys.platform.startswith("linux"):
        try:
            for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024**2, 1)
        except OSError:
            pass
    elif sys.platform == "win32":
        rc, out = run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
            timeout=20,
        )
        digits = "".join(c for c in out if c.isdigit())
        if digits:
            return round(int(digits) / 1024**3, 1)
    return 0.0


def detect_gpu() -> dict:
    backends = {
        "nvidia_cuda": False,
        "amd_rocm": False,
        "apple_metal": False,
        "vulkan": False,
        "cpu_only": False,
    }
    details: dict[str, str] = {}

    if shutil.which("nvidia-smi"):
        rc, out = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if rc == 0 and out.strip():
            backends["nvidia_cuda"] = True
            details["nvidia"] = out.strip().splitlines()[0]

    if shutil.which("rocminfo"):
        rc, out = run(["rocminfo"], timeout=10)
        if rc == 0 and "AMD" in out:
            backends["amd_rocm"] = True
            gfx = [w for w in out.split() if w.startswith("gfx")]
            details["amd_rocm"] = gfx[0] if gfx else "available"

    if sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64"):
        backends["apple_metal"] = True
        details["apple_metal"] = "Apple Silicon (Metal built into the release binary)"

    for tool in ("vulkaninfo", "vulkaninfoSDK"):
        if shutil.which(tool):
            rc, out = run([tool, "--summary"], timeout=10)
            if rc == 0 and "devicename" in out.lower():
                backends["vulkan"] = True
                details["vulkan"] = "device present"
                break

    if not any(v for k, v in backends.items() if k != "cpu_only"):
        backends["cpu_only"] = True
    return {"backends": backends, "details": details}


def pick_model(ram: float) -> tuple[str, str]:
    """(model key, why). Small model when RAM cannot comfortably hold the default."""
    default = labkit.MODELS[labkit.DEFAULT_MODEL]
    if (os.environ.get("LAB_MODEL") or "").strip():
        return labkit.model_key(), "chosen with LAB_MODEL"
    if ram >= default["min_ram_gb"]:
        return labkit.DEFAULT_MODEL, "enough RAM for the default model"
    return labkit.SMALL_MODEL, f"{ram} GB RAM is under the {default['min_ram_gb']} GB the default model wants"


def recommend(cpu: dict, ram: float, gpu: dict) -> dict:
    b = gpu["backends"]
    if b["nvidia_cuda"]:
        backend, cmake = "CUDA", "-DGGML_CUDA=ON"
    elif b["apple_metal"]:
        backend, cmake = "Metal", "-DGGML_METAL=ON"
    elif b["amd_rocm"]:
        backend, cmake = "ROCm/HIP", "-DGGML_HIPBLAS=ON"
    elif b["vulkan"]:
        backend, cmake = "Vulkan", "-DGGML_VULKAN=ON"
    else:
        backend, cmake = "CPU", ""

    model_key, why = pick_model(ram)
    spec = labkit.model_spec(model_key)
    ram_ok = ram >= spec["min_ram_gb"]
    paths = ["01-measure", "02-serve", "03-integrate", "bonus/sweeps"]
    if b["apple_metal"]:
        paths.append("bonus/mlx")

    return {
        "recommended_paths": paths,
        "model_key": model_key,
        "model_choice_reason": why,
        "model_label": spec["label"],
        "model_repo": spec["repo"],
        "primary_model_file": spec["primary"][1],
        "compare_model_file": spec["compare"][1],
        "llama_cpp_backend": backend,
        "llama_cpp_cmake_flag": cmake,
        "llama_cpp_build": labkit.LLAMA_CPP_BUILD,
        "ram_sufficient": ram_ok,
        "fallback": None if ram_ok else "cloud/ notebook (Colab or Kaggle)",
    }


def main() -> int:
    cpu, ram, gpu = detect_cpu(), detect_ram_gb(), detect_gpu()
    rec = recommend(cpu, ram, gpu)

    line = "─" * 64
    print(line)
    print(f"  Platform : {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  CPU      : {cpu['model']}")
    print(f"             {cpu['cores_physical']} physical · {cpu['cores_logical']} logical cores")
    exts = [n for n, k in (("AVX-512", "avx512"), ("AVX2", "avx2"), ("NEON", "neon")) if cpu.get(k)]
    if exts:
        print(f"             extensions: {', '.join(exts)}")
    print(f"  RAM      : {ram} GB")
    print("  GPU      : ", end="")
    active = [k for k, v in gpu["backends"].items() if v and k != "cpu_only"]
    print(", ".join(active) if active else "none detected (CPU only)")
    for k, v in gpu["details"].items():
        print(f"             - {k}: {v}")
    print(line)
    spec = labkit.model_spec(rec["model_key"])
    print(f"\n  Model         : {spec['label']}  [LAB_MODEL={rec['model_key']}]")
    print(f"                  {spec['repo']}  (~{spec['download_gb']} GB)")
    print(f"                  primary  {spec['primary'][1]}  ({spec['primary'][2]} GB)")
    print(f"                  compare  {spec['compare'][1]}  ({spec['compare'][2]} GB)")
    print(f"                  chosen because: {rec['model_choice_reason']}")
    alt = next(k for k in labkit.MODELS if k != rec["model_key"])
    a = labkit.MODELS[alt]
    print(f"  Other option  : LAB_MODEL={alt}  ->  {a['label']}, ~{a['download_gb']} GB, "
          f"needs {a['min_ram_gb']} GB RAM")
    # The prebuilt asset is chosen at `make setup` from what upstream actually
    # publishes for this OS -- which is NOT always the backend your GPU vendor
    # implies. Upstream ships no Linux CUDA build, so an NVIDIA box on Linux gets
    # the Vulkan one. Report the two facts separately instead of merging them into
    # a single claim that is wrong on that platform.
    runtime_meta = labkit.repo_root() / "runtime" / "active.json"
    if runtime_meta.exists():
        try:
            asset = json.loads(runtime_meta.read_text()).get("asset", "?")
        except (ValueError, OSError):
            asset = "?"
        print(f"  llama.cpp     : prebuilt release {labkit.LLAMA_CPP_BUILD}  ({asset})")
        live, why = labkit.gpu_offload_is_live()
        print(f"  GPU offload   : {'ACTIVE -- ' + why if live else 'OFF -- ' + why}")
        if not live and rec["llama_cpp_backend"] != "CPU":
            print(f"                  base track is unaffected (100 pts need no GPU).")
            print(f"                  to use the {rec['llama_cpp_backend']} you have, build from source:")
            print(f"                  LLAMA_CMAKE_FLAGS={rec['llama_cpp_cmake_flag']} make build-llama")
    else:
        print(f"  llama.cpp     : prebuilt release {labkit.LLAMA_CPP_BUILD}  (asset picked by `make setup`)")
    print(f"  source build  : {rec['llama_cpp_cmake_flag'] or 'CPU only'}  (bonus B1 -- not used by the base track)")
    print(f"  Tracks open   : {', '.join(rec['recommended_paths'])}")
    env = os.environ.get("LAB_RUNTIME_ENV")
    if env:
        print(f"  Running on    : {env}  (declare this in REFLECTION section 1)")

    if not rec["ram_sufficient"]:
        print(f"\n  !! {ram} GB RAM is below the {spec['min_ram_gb']} GB floor even for "
              f"{spec['label']}.")
        print("     Run the lab in cloud/Day20-lab.ipynb (Colab or Kaggle) instead,")
        print("     and say so in REFLECTION.md section 1. Grading is unaffected.")
    print(line)

    out = {
        # "local" unless the cloud notebook sets LAB_RUNTIME_ENV (colab / kaggle).
        # Rubric item 1 asks you to declare where you ran; this records it for you.
        "runtime_environment": os.environ.get("LAB_RUNTIME_ENV", "local"),
        "cpu": cpu,
        "ram_gb": ram,
        "gpu": gpu,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "recommendation": rec,
    }
    labkit.hardware_json().write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved {labkit.hardware_json().name} -- every other track reads this.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
