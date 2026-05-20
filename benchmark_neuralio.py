# Copyright (c) 2026 Tuomas Valtteri Lehto
# benchmark_neuralio.py

import torch
import time
import os
import sys
import numpy as np
from neuralio_safe import NeuralIOManager

def format_size(bytes_val):
    if bytes_val < 1024**2: return f"{bytes_val/1024:.2f} KB"
    return f"{bytes_val/1024**2:.2f} MB"

def run_benchmark():
    print("==================================================")
    print("   NEURALIO PERFORMANCE BENCHMARK (RTX 5080)      ")
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
    TENSOR_SIZE_MB = 2048  # 2GB Tensor
    FILENAME_TORCH = "bench_torch.pt"
    FILENAME_NIO = "bench_neuralio.nio"
    
    # Initialize
    if os.path.exists(FILENAME_TORCH): os.remove(FILENAME_TORCH)
    if os.path.exists(FILENAME_NIO): os.remove(FILENAME_NIO)
    
    nio = NeuralIOManager(config_path="neuralio_config.json")
    
    print(f"Allocating {TENSOR_SIZE_MB} MB Tensor on GPU...", end="", flush=True)
    # 2GB = 2 * 1024^3 bytes. Float32 = 4 bytes. 
    # Elements = (2 * 1024^3) / 4 = 536,870,912
    num_elements = (TENSOR_SIZE_MB * 1024**2) // 4
    tensor = torch.randn(num_elements, device='cuda', dtype=torch.float32)
    torch.cuda.synchronize()
    print(" Done.\n")

    # ---------------------------------------------------------
    # ROUND 1: Standard PyTorch Save (Baseline)
    # ---------------------------------------------------------
    print(f"1. Running Standard torch.save()...")
    start = time.perf_counter()
    torch.save(tensor, FILENAME_TORCH)
    torch.cuda.synchronize() # Wait for async CUDA ops if any
    end = time.perf_counter()
    
    time_torch = end - start
    size_torch = os.path.getsize(FILENAME_TORCH)
    print(f"   -> Time: {time_torch:.4f} s")
    print(f"   -> Size: {format_size(size_torch)}")
    print(f"   -> Speed: {TENSOR_SIZE_MB / time_torch:.2f} MB/s")

    # ---------------------------------------------------------
    # ROUND 2: NeuralIO Cold Save (First Run)
    # ---------------------------------------------------------
    print(f"\n2. Running NeuralIO Save (Cold/Full)...")
    start = time.perf_counter()
    nio.save(tensor, FILENAME_NIO)
    # Note: nio.save has internal synchronize
    end = time.perf_counter()
    
    time_nio_cold = end - start
    size_nio_cold = os.path.getsize(FILENAME_NIO)
    print(f"   -> Time: {time_nio_cold:.4f} s")
    print(f"   -> Size: {format_size(size_nio_cold)}")
    print(f"   -> Speed: {TENSOR_SIZE_MB / time_nio_cold:.2f} MB/s")

    # ---------------------------------------------------------
    # SIMULATE TRAINING (Modify 5% of weights)
    # ---------------------------------------------------------
    print(f"\n[Simulating Training Step: Modifying 5% of weights...]")
    # Modify contiguous block to simulate layer updates
    limit = int(num_elements * 0.05)
    tensor[:limit] += 0.01
    torch.cuda.synchronize()

    # ---------------------------------------------------------
    # ROUND 3: NeuralIO Hot Save (Incremental)
    # ---------------------------------------------------------
    print(f"3. Running NeuralIO Save (Incremental)...")
    start = time.perf_counter()
    nio.save(tensor, FILENAME_NIO)
    end = time.perf_counter()
    
    time_nio_hot = end - start
    size_nio_hot = os.path.getsize(FILENAME_NIO)
    
    # Calculate Metrics
    speedup = time_torch / time_nio_hot
    space_saving = 100 * (1 - (size_nio_hot / size_torch))
    
    print(f"   -> Time: {time_nio_hot:.4f} s")
    print(f"   -> Size: {format_size(size_nio_hot)}")
    print(f"   -> Effective Speed: {TENSOR_SIZE_MB / time_nio_hot:.2f} MB/s")

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
    if os.path.exists(FILENAME_TORCH): os.remove(FILENAME_TORCH)
    if os.path.exists(FILENAME_NIO): os.remove(FILENAME_NIO)

if __name__ == "__main__":
    run_benchmark()
