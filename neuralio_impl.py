import torch
import time as _time
import os
import warnings

# CRITICAL: Capture original torch.save BEFORE any monkey patching happens
_ORIGINAL_TORCH_SAVE = torch.save

try:
    import neuralio_final as core
except ImportError as e_final:
    try:
        import neuralio_formula1 as core
    except ImportError as e_formula:
        core = None
        # DIAGNOSTIC: Print precisely why the extension failed.
        print(f"[NeuralIO DEBUG] C++ Extension Load Failure (neuralio_final): {e_final}")
        print(f"[NeuralIO DEBUG] C++ Extension Load Failure (neuralio_formula1): {e_formula}")
        print("[NeuralIO DEBUG] Environment check: LD_LIBRARY_PATH=", os.environ.get('LD_LIBRARY_PATH', 'None'))

class NeuralIOStorage:
    def __init__(self, chunk_size, vram_budget, **kwargs):
        if core:
            import json
            import tempfile
            
            session_config = {
                "calibrated": True, 
                "chunk_size": int(chunk_size),
                "vram_budget_mb": int(vram_budget / (1024**2)),
                "io_strategy": kwargs.get("io_strategy", "BUFFERED"),  
                "io_threads": kwargs.get("io_threads", 4),
                "compression": kwargs.get("compression", False),
                "compression_enabled": kwargs.get("compression_enabled", False),
                "vault_dirs": kwargs.get("vault_dirs", [])
            }
            
            fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="nio_session_")
            with os.fdopen(fd, 'w') as f:
                json.dump(session_config, f)
                
            self.temp_config_path = temp_path
            self.engine = core.NeuralIOEngine(self.temp_config_path)
            
            try: os.remove(temp_path)
            except: pass
        else:
            print("[NeuralIO] Warning: Accelerated engine not available. Standardizing to safe mode.")
            self.engine = None
        self.last_save_metrics = {}

    def save(self, tensor, filename, rank=-1):
        if self.engine is None:
             # Falling back to torch.save (usually standard PyTorch speed)
             final_name = filename
             if rank >= 0:
                 f_root, f_ext = os.path.splitext(filename)
                 final_name = f"{f_root}_rank_{rank}{f_ext}"
             
             t0 = _time.time()
             _ORIGINAL_TORCH_SAVE(tensor, final_name)
             dt = _time.time() - t0
             
             size = tensor.numel() * tensor.element_size()
             self.last_save_metrics = {
                "saved_mb": size / 1024**2,
                "compute_time_ms": dt * 1000.0,
                "io_time_ms": dt * 1000.0,
                "effective_speed_gbs": (size / 1e9) / dt if dt > 0 else 0
             }
             return
             
        if not tensor.is_cuda:
            raise ValueError("NeuralIO requires CUDA tensors for acceleration.")
        
        ptr = tensor.data_ptr()
        size = tensor.numel() * tensor.element_size()
        
        if tensor.is_cuda:
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            start_event.record()
            
            self.engine.save_tensor_sharded(ptr, size, filename, rank)
            
            end_event.record()
            torch.cuda.synchronize()
            elapsed_ms = start_event.elapsed_time(end_event)
            
            cpp_metrics = self.engine.last_save_metrics
            self.last_save_metrics = dict(cpp_metrics)
            self.last_save_metrics["compute_time_ms"] = elapsed_ms
        else:
            t0 = _time.perf_counter()
            self.engine.save_tensor_sharded(ptr, size, filename, rank)
            t1 = _time.perf_counter()
            self.last_save_metrics = self.engine.last_save_metrics
            self.last_save_metrics["compute_time_ms"] = (t1 - t0) * 1000.0

    def load(self, filename, tensor):
        if self.engine is None:
            data = torch.load(filename)
            tensor.copy_(data)
            return
        ptr = tensor.data_ptr()
        size = tensor.numel() * tensor.element_size()
        self.engine.load_tensor_sharded(filename, ptr, size)

    def sync(self):
        if self.engine:
            self.engine.sync()
