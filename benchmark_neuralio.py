# Copyright (c) 2026 Tuomas Valtteri Lehto
# benchmark_neuralio.py

import torch
import time
import os
import sys
import argparse
from neuralio_safe import NeuralIOManager

def format_size(bytes_val):
    if bytes_val < 1024**2: return f"{bytes_val/1024:.2f} KB"
    return f"{bytes_val/1024**2:.2f} MB"

def run_benchmark(no_gpu=False):
    parser = argparse.ArgumentParser(description="NeuralIO Performance Benchmark")
    parser.add_argument('--no_gpu', action='store_true', help="Run in CPU-only safe mode")
    args = parser.parse_args()
    
    use_gpu = not args.no_gpu and torch.cuda.is_available()
    device = 'cuda' if use_gpu else 'cpu'
    
    gpu_name = "CPU (Safe Mode)"
    if use_gpu:
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except: pass

    print("==================================================")
    print(f"   NEURALIO PERFORMANCE BENCHMARK ({gpu_name})")
    print("==================================================")
    print(f"Python Executable: {sys.executable}")
    print(f"Python Version: {sys.version}")
    try:
        import neuralio_final
        print(f"Extension Status: LOADED ({neuralio_final.__file__})")
    except ImportError:
        print("Extension Status: MISSING (Fallback Mode)")
    print("--------------------------------------------------")

    # Settings
    TENSOR_SIZE_MB = 2048 if use_gpu else 512  # Smaller tensor for CPU mode
    FILENAME_TORCH = "bench_torch.pt"
    FILENAME_NIO = "bench_neuralio.nio"
    
    # Initialize
    if os.path.exists(FILENAME_TORCH): os.remove(FILENAME_TORCH)
    if os.path.exists(FILENAME_NIO): os.remove(FILENAME_NIO)
    
    # Ensure dashboard doesn't start again if it's already running
    nio = NeuralIOManager(config_path="neuralio_config.json", start_dashboard=False)
    
    print(f"Allocating {TENSOR_SIZE_MB} MB Tensor on {device}...", end="", flush=True)
    num_elements = (TENSOR_SIZE_MB * 1024**2) // 4
    tensor = torch.randn(num_elements, device=device, dtype=torch.float32)
    if use_gpu: torch.cuda.synchronize()
    print(" Done.\n")

    # ---------------------------------------------------------
    # ROUND 1: Standard PyTorch Save (Baseline)
    # ---------------------------------------------------------
    print(f"1. Running Standard torch.save()...")
    start = time.perf_counter()
    torch.save(tensor, FILENAME_TORCH)
    if use_gpu: torch.cuda.synchronize()
    end = time.perf_counter()
    
    time_torch = end - start
    size_torch = os.path.getsize(FILENAME_TORCH) if os.path.exists(FILENAME_TORCH) else 1
    print(f"   -> Time: {time_torch:.4f} s")
    print(f"   -> Size: {format_size(size_torch)}")
    print(f"   -> Speed: {TENSOR_SIZE_MB / time_torch:.2f} MB/s")

    # ---------------------------------------------------------
    # ROUND 2: NeuralIO Cold Save (First Run)
    # ---------------------------------------------------------
    print(f"\n2. Running NeuralIO Save (Cold/Full)...")
    start = time.perf_counter()
    nio.save(tensor, FILENAME_NIO)
    end = time.perf_counter()
    
    time_nio_cold = end - start
    size_nio_cold = os.path.getsize(FILENAME_NIO) if os.path.exists(FILENAME_NIO) else size_torch
    print(f"   -> Time: {time_nio_cold:.4f} s")
    print(f"   -> Size: {format_size(size_nio_cold)}")
    print(f"   -> Speed: {TENSOR_SIZE_MB / max(time_nio_cold, 0.001):.2f} MB/s")

    # ---------------------------------------------------------
    # SIMULATE TRAINING (Modify 5% of weights)
    # ---------------------------------------------------------
    print(f"\n[Simulating Training Step: Modifying 5% of weights...]")
    limit = int(num_elements * 0.05)
    tensor[:limit] += 0.01
    if use_gpu: torch.cuda.synchronize()

    # ---------------------------------------------------------
    # ROUND 3: NeuralIO Hot Save (Incremental)
    # ---------------------------------------------------------
    print(f"3. Running NeuralIO Save (Incremental)...")
    start = time.perf_counter()
    nio.save(tensor, FILENAME_NIO)
    end = time.perf_counter()
    
    time_nio_hot = end - start
    size_nio_hot = os.path.getsize(FILENAME_NIO) if os.path.exists(FILENAME_NIO) else size_torch
    
    # Calculate Metrics safely
    speedup = time_torch / max(time_nio_hot, 0.001)
    space_saving = 100 * (1 - (size_nio_hot / max(size_torch, 1)))
    
    print(f"   -> Time: {time_nio_hot:.4f} s")
    print(f"   -> Size: {format_size(size_nio_hot)}")
    print(f"   -> Effective Speed: {TENSOR_SIZE_MB / max(time_nio_hot, 0.001):.2f} MB/s")

    print("\n==================================================")
    print("               FINAL SCORECARD                    ")
    print("==================================================")
    print(f"Standard Save Time    : {time_torch:.4f} s")
    print(f"NeuralIO (Hot) Time   : {time_nio_hot:.4f} s")
    print(f"--------------------------------------------------")
    print(f"SPEEDUP               : {speedup:.1f}x FASTER")
    print(f"STORAGE SAVED         : {space_saving:.1f}%")
    print("==================================================")

    # Cleanup
    try:
        if os.path.exists(FILENAME_TORCH): os.remove(FILENAME_TORCH)
        if os.path.exists(FILENAME_NIO): os.remove(FILENAME_NIO)
    except: pass

if __name__ == "__main__":
    run_benchmark()
