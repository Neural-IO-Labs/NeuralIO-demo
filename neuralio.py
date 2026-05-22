# NeuralIO - The "Zero Config" Entry Point
import sys
try:
    import torch
except ImportError:
    torch = None
import neuralio_safe
import time
import os

# Single Global Instance
MANAGER = None

def _get_manager():
    global MANAGER
    if MANAGER is None:
        print("[NeuralIO] Initializing Global Manager...")
        MANAGER = neuralio_safe.NeuralIOManager(start_dashboard=True)
    return MANAGER

import pickle

# --- Monkey Patch Logic ---
if torch is not None:
    _ORIGINAL_SAVE = torch.save
else:
    _ORIGINAL_SAVE = None

def neuralio_save(obj, f, *args, **kwargs):
    """
    Patched torch.save that accelerates large CUDA tensors via NeuralIO.
    Everything else falls back to standard torch.save.
    """
    # 1. Check eligibility for NeuralIO Acceleration
    # Condition: Object is a Tensor, is on CUDA, and "f" is a filename (string)
    is_acceleratable = False
    
    if torch is not None and isinstance(obj, torch.Tensor) and obj.is_cuda and isinstance(f, str):
        # Optional: Size threshold?
        # For now, accelerate all CUDA tensors.
        is_acceleratable = True
        
    if is_acceleratable:
        mgr = _get_manager()
        try:
            # print(f"[NeuralIO] Intercepted torch.save for CUDA Tensor -> {f}")
            mgr.save(obj, f)
            return
        except Exception as e:
            print(f"[NeuralIO] Acceleration failed ({e}). Falling back to standard save.")
            
    # 2. Fallback to original
    if _ORIGINAL_SAVE:
        return _ORIGINAL_SAVE(obj, f, *args, **kwargs)
    raise ImportError("torch is not available")

def save(obj, f, *args, **kwargs):
    """
    Explicit SDK wrapper for high-speed accelerated checkpointing.
    If the object is not eligible or saving fails, it transparently
    falls back to standard torch.save.
    """
    mgr = _get_manager()
    is_acceleratable = torch is not None and isinstance(obj, torch.Tensor) and obj.is_cuda and isinstance(f, str)
    if is_acceleratable:
        try:
            mgr.save(obj, f)
            return
        except Exception as e:
            print(f"[NeuralIO] SDK Save failed: {e}. Falling back to standard torch.save.")
            
    # Fallback to standard torch.save
    if _ORIGINAL_SAVE:
        return _ORIGINAL_SAVE(obj, f, *args, **kwargs)
    raise ImportError("torch is not available")

def patch():
    """Activates the monkey patch on torch.save."""
    print("[NeuralIO] patching torch.save...")
    torch.save = neuralio_save

def generate_billing_report():
    import json
    import os
    from datetime import datetime
    
    log_file = "neuralio_dashboard.jsonl"
    if not os.path.exists(log_file):
        print(f"❌ No billing data found ({log_file} missing).")
        return

    total_saved = 0.0
    total_chunks = 0
    start_date = None
    end_date = None
    
    print(f"Reading {log_file}...")
    try:
        with open(log_file, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    saved = data.get('metrics', {}).get('saved_mb', 0)
                    total_saved += saved
                    total_chunks += 1
                    ts = data.get('timestamp')
                    if not start_date: start_date = ts
                    end_date = ts
                except: continue
    except Exception as e:
        print(f"Error reading logs: {e}")
        return

    print("\n" + "="*40)
    print("   NEURAL:IO ENTERPRISE BILLING REPORT")
    print("="*40)
    print(f"Generated: {datetime.now().isoformat()}")
    print(f"Period:    {start_date} to {end_date}")
    print(f"Checkpoints: {total_chunks}")
    print(f"Storage Saved: {total_saved/1024.0:.2f} GB")
    print(f"Est. Value:    ${total_saved/1024.0 * 0.023:.2f}")
    print("="*40)
    print("Success: Report generated.")


# --- Auto-Initialization Logic ---
if __name__ == "__main__":
    # CLI Mode (python -m neuralio)
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "billing":
            generate_billing_report()
            
        elif cmd == "hwid":
             print("[CLI] Initializing for Hardware ID check...")
             _get_manager()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python -m neuralio [billing|hwid]")
    else:
        # Default: Print HWID
        print("[CLI] Initializing for Hardware ID check...")
        _get_manager()

else:
    # Import Mode (import neuralio)
    if os.environ.get("NEURALIO_DISABLED") == "1":
        print("[NeuralIO] ⚠️ EMERGENCY SAFE MODE ACTIVE. Acceleration Disabled. ⚠️")
    else:
        # 1. Initialize Manager (launches dashboard)
        _get_manager()

        # 2. Apply Monkey Patch
        patch()

# Expose useful classes directly
NeuralIOManager = neuralio_safe.NeuralIOManager

def init(**kwargs):
    """Explicitly initializes the NeuralIO engine with configuration parameters."""
    global MANAGER
    if MANAGER is not None:
        MANAGER.config.update(kwargs)
        MANAGER.s3_bucket = MANAGER.config.get("s3_bucket")
        MANAGER.s3_endpoint_url = MANAGER.config.get("s3_endpoint_url")
        MANAGER.zero_disk_cloud = MANAGER.config.get("zero_disk_cloud", False)
        if "chunk_size" in kwargs:
            MANAGER.chunk_size = kwargs["chunk_size"]
        if "vram_budget_mb" in kwargs:
            MANAGER.vram_budget_mb = kwargs["vram_budget_mb"]
        if "io_strategy" in kwargs:
            MANAGER.io_backend = kwargs["io_strategy"]
        
        # Reset/recreate the engine to apply new settings (like vault_dirs or compression)
        MANAGER._reset_engine()
        
        if MANAGER.s3_endpoint_url and MANAGER.s3_bucket:
            MANAGER.cloud_client = neuralio_safe.CloudStorageClient(MANAGER.s3_endpoint_url, MANAGER.s3_bucket)
            print(f"[NeuralIO] 🚀 Multi-Cloud Direct Streaming Enabled -> Endpoint: {MANAGER.s3_endpoint_url}, Bucket: {MANAGER.s3_bucket}")
    else:
        MANAGER = neuralio_safe.NeuralIOManager(start_dashboard=True, **kwargs)
    return MANAGER

def get_global_manager():
    """Returns the single active NeuralIOManager instance."""
    return _get_manager()

def patch_deepspeed():
    """Activates the collective sharded accelerator hook for DeepSpeed ZeRO."""
    import deepspeed_bridge
    return deepspeed_bridge.patch_deepspeed(get_global_manager())

def patch_accelerate(accelerator):
    """Activates the transparent save/load accelerator hook for Hugging Face Accelerate."""
    import deepspeed_bridge
    return deepspeed_bridge.patch_accelerate(accelerator, get_global_manager())

def disable():
    """Immediately restores standard torch.save and turns off acceleration."""
    if MANAGER:
        MANAGER.disable()

def enable():
    """Re-enables NeuralIO acceleration for torch.save."""
    if MANAGER:
        MANAGER.enable()

def __getattr__(name):
    """Proxy manager configuration attributes natively (like neuralio.chunk_size)."""
    if MANAGER and hasattr(MANAGER, name):
        return getattr(MANAGER, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
