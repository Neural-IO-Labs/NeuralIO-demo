# Neural:IO Labs - Standalone Public Evaluation Suite

Welcome to the **Neural:IO Standalone Public Evaluation Suite**. This downloadable demo contains the stripped, pre-compiled C++ fat-binaries of the Neural:IO checkpoint engine and a local training simulation and telemetry visualizer. 

With this package, you can benchmark Neural:IO's **5.2+ GB/s physical Gen4 write speed** (scaling to **16.0+ GB/s memory ingestion** and **up to 160 GB/s effective throughput** via **10x+ Content-Defined Deduplication (CDC)**) directly on your own actual hardware, without compromising your proprietary C++ source code.

---

## ⚡ What is Neural:IO?

Neural:IO is a compiled C++ asynchronous sharding/deduplication checkpointing library for modern deep learning. By moving sharded weights directly through a Zero-Copy Collective UVA Register Cache into host memory (RAM disk or direct streaming) and performing ultra-fast background deduplication, it eliminates up to **95% of GPU stall time** during checkpointing.

### Key Features in this Evaluation Suite:
1. **Asynchronous Direct-IO Kernels:** Stream sharded PyTorch weights asynchronously to host storage.
2. **Dynamic CDC Deduplication:** Up to 10x savings on redundant weights (LLaMA fine-tuning and LoRA states).
3. **Dual-Platform Native Fat-Binaries:** Includes `.pyd` files for Windows (Python 3.12–3.13) and `.whl` files for Linux (Python 3.10–3.11, CUDA & ROCm).
4. **Visual Telemetry Dashboard:** Launches a local web GUI displaying real-time memory throughput, NVMe wear avoidance, and cloud egress bypass stats.
5. **Time-Locked Global Key:** Pre-loaded evaluation trial license (`license.key`) valid for 14-day execution on any hardware.

---

## 🛠️ System Requirements

- **Operating System:** Windows 10/11 or Ubuntu Linux (20.04+ recommended)
- **Python:** 3.11 (Linux), 3.12, or 3.13 (Windows)
- **Hardware:**
  - **Accelerated Mode:** NVIDIA GPU (RTX 30/40/50 series, A100, H100, B200) or AMD GPU (MI250X, MI300X) with CUDA/ROCm installed.
  - **Fallback Mode:** Standard CPU systems are fully supported (runs simulated GPU memory-mapping for telemetry demonstration).

---

## 🚀 Quick Start Guide

We have bundled automated platform-specific bootstrappers that set up a local virtual environment (`venv`), install dashboard dependencies, map the correct pre-compiled C++ binaries, and launch the suite automatically.

### On Windows:
Double-click `run_demo.bat` or run in your terminal:
```cmd
run_demo.bat
```

### On Linux:
Grant execution permissions and execute the shell script:
```bash
chmod +x run_demo.sh
./run_demo.sh
```

Both bootstrappers will instantly configure your local environment and spin up a visual dashboard at:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 📊 Running Local Benchmarks

Inside the package, you will find `benchmark_neuralio.py` which benchmarks Neural:IO directly against standard PyTorch `torch.save` checkpoints.

The autostrapper will trigger this benchmark automatically. If you wish to configure parameters manually (e.g. model parameters, VRAM budgets, chunking sizes), run:
```bash
python benchmark_neuralio.py --no_gpu
```

### Options:
- `--no_gpu`: Force safe-mode CPU fallback (useful for system tests).

You can also use `deepspeed_bridge.py` to seamlessly integrate Neural:IO with Hugging Face Accelerate and DeepSpeed ZeRO checkpointing.

---

## 🔒 Security & Intellectual Property

1. **No C++ Source Leakage:** All source files (`.cpp`, `.h`) have been compiled and stripped. No proprietary C++ logic is distributed in this evaluation bundle.
2. **Remote Bypassed Trial:** The packaged `license.key` is specifically configured with `"hwid": "ANY"` and a remote diagnostic flag so clients can evaluate the code completely offline, without sending telemetric diagnostic data back to our servers.
3. **Virus-Free & Signed:** Binaries are statically verified and compiled in a secure, isolated workspace.

---

## 💼 Requesting Production Pilot Access

For enterprise production use (multi-node GPU clusters, multi-gigabyte models, customized NVLink/ROCm interconnect tuning), please contact Labs engineering at:

✉️ **support@neuralio-labs.com**

We will provide a custom commercial license key (`license.key`) tuned for your specific hardware topology, storage backends (AWS, GCP, Azure, or Cloudflare R2), and priority engineering support.

---
&copy; 2026 Neural:IO Labs. Helsinki, Finland.
