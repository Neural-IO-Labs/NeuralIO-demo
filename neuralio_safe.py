# Copyright (c) 2026 Tuomas Valtteri Lehto
# neuralio_safe.py (formerly neurovault_safe.py) - WARP VELOCITY v2.2.5.9

import torch
import os
import struct
import warnings
import json
import time as _time  
import datetime
import glob
import shutil
import urllib.request
import urllib.error
import socket
from collections import deque
from neuralio_impl import NeuralIOStorage
import threading

# Capture original torch.save BEFORE any monkey patching happens
_REAL_TORCH_SAVE = torch.save

class CloudStorageClient:
    def __init__(self, endpoint_url, bucket):
        self.endpoint_url = endpoint_url
        self.bucket = bucket
        
    def upload_file(self, local_path, cloud_key):
        import requests
        try:
            url = f"{self.endpoint_url}/bucket/{cloud_key}"
            with open(local_path, 'rb') as f:
                response = requests.put(url, data=f, headers={'Content-Type': 'application/octet-stream'})
            return response.status_code == 200
        except Exception as e:
            warnings.warn(f"[NeuralIO] Cloud Upload Error for {cloud_key}: {e}")
            return False
            
    def download_file(self, cloud_key, local_path):
        try:
            url = f"{self.endpoint_url}/bucket/{cloud_key}"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req) as response:
                data = response.read()
            with open(local_path, 'wb') as f:
                f.write(data)
            return True
        except Exception as e:
            warnings.warn(f"[NeuralIO] Cloud Download Error for {cloud_key}: {e}")
            return False

class NeuralIOManager:
    # Build Flags (Modified by build pipeline)
    IS_EDU_BUILD = False 
    TELEMETRY_ENDPOINT = "https://api.neural.io/heartbeat"

    def __init__(self, config_path="neuralio_config.json", **kwargs):
        self.acceleration_enabled = True # Master Switch
        
        # 1. Hardware Auto-Detection
        defaults = self._detect_optimal_settings()
        
        self.config = {
            "chunk_size": defaults["chunk_size"],
            "vram_budget_mb": defaults["vram_budget_mb"],
            "io_threads": defaults["io_threads"],
            "io_strategy": defaults["io_strategy"],
            "max_retries": 1,
            "strict_mode_default": True,
            "retention_count": 5,        
            "webhook_url": None,         
            "straggler_threshold": 2.0,
            "stagger_write_ms": 50,
            "warp_sustain": True, # New Performance Tier
            "s3_bucket": None,
            "s3_endpoint_url": None,
            "zero_disk_cloud": False,
            "compression_algo": "none",
            "vault_dirs": []
        }

        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    self.config.update(json.load(f))
            except Exception as e:
                warnings.warn(f"[NeuralIO] Config load failed: {e}. Using detected defaults.")

        self.config.update(kwargs)

        self.max_retries = self.config["max_retries"]
        self.chunk_size = self.config["chunk_size"]
        self.vram_budget_mb = self.config["vram_budget_mb"]
        self.webhook_url = self.config["webhook_url"]
        self.io_history = deque(maxlen=20) 
        
        # Cloud setup
        self.s3_bucket = self.config["s3_bucket"]
        self.s3_endpoint_url = self.config["s3_endpoint_url"]
        self.zero_disk_cloud = self.config["zero_disk_cloud"]
        self.cloud_client = None
        if self.s3_endpoint_url and self.s3_bucket:
            self.cloud_client = CloudStorageClient(self.s3_endpoint_url, self.s3_bucket)
            print(f"[NeuralIO] 🚀 Multi-Cloud Direct Streaming Enabled -> Endpoint: {self.s3_endpoint_url}, Bucket: {self.s3_bucket}")
        
        self.gpu_name = "Unknown GPU"
        self.io_backend = self.config.get("io_strategy", "BUFFERED")
        if torch.cuda.is_available():
            try: self.gpu_name = torch.cuda.get_device_name(0)
            except: pass
        
        vram_bytes = int(self.vram_budget_mb * 1024**2)
        self.engine = NeuralIOStorage(
            self.chunk_size, 
            vram_bytes,
            io_strategy=self.io_backend,
            io_threads=self.config.get("io_threads", 4),
            compression_algo=self.config.get("compression_algo", "none"),
            vault_dirs=self.config.get("vault_dirs", [])
        )

        import uuid
        self.session_id = str(uuid.uuid4())
        
        if kwargs.get("start_dashboard", True):
             self._launch_dashboard()

    def _launch_dashboard(self):
        import subprocess
        import sys
        dash_port = int(os.environ.get("NEURALIO_DASHBOARD_PORT", 8000))
        port_to_use = dash_port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', dash_port)) == 0:
                for p in range(dash_port + 1, dash_port + 20):
                    if s.connect_ex(('localhost', p)) != 0:
                        port_to_use = p
                        break
        dash_port = port_to_use
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dashboard_script = os.path.join(base_dir, "dashboard", "main.py")
            if os.path.exists(dashboard_script):
                env = os.environ.copy()
                env["NEURALIO_DASHBOARD_PORT"] = str(dash_port)
                subprocess.Popen([sys.executable, dashboard_script], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        except Exception: pass

    def _detect_optimal_settings(self):
        settings = {"chunk_size": 33554432, "vram_budget_mb": 256, "io_threads": 4, "io_strategy": "BUFFERED"}
        try:
            cpu_count = os.cpu_count() or 4
            settings["io_threads"] = max(2, min(cpu_count - 2, 8)) # Cap threads on tight systems
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                total_mem_gb = props.total_memory / (1024**3)
                if total_mem_gb >= 40: # H100/A100
                    settings["chunk_size"] = 134217728
                    settings["vram_budget_mb"] = 1024
            if os.name == 'posix': settings["io_strategy"] = "DIRECT"
        except: pass
        return settings

    def sync(self):
        """Blocks until all asynchronous C++ I/O is finalized."""
        if hasattr(self.engine, 'sync'): self.engine.sync()

    def _reset_engine(self):
        vram_bytes = int(self.vram_budget_mb * 1024**2)
        self.engine = NeuralIOStorage(
            self.chunk_size, 
            vram_bytes,
            io_strategy=self.io_backend,
            io_threads=self.config.get("io_threads", 4),
            compression_algo=self.config.get("compression_algo", "none"),
            vault_dirs=self.config.get("vault_dirs", [])
        )

    def _log_receipt(self, filename, metrics, total_bytes, rank=None):
        warnings_list = []
        io_time = metrics.get('io_time_ms', 0)
        if io_time > 0:
            if len(self.io_history) > 5:
                avg_io = sum(self.io_history) / len(self.io_history)
                if io_time > avg_io * self.config.get("straggler_threshold", 2.0):
                    warnings_list.append(f"Straggler: {io_time:.1f}ms")
        return warnings_list

    def save(self, obj, filename, rank=None):
        if rank is None:
            rank = -1
            if torch.distributed.is_available() and torch.distributed.is_initialized():
                rank = torch.distributed.get_rank()
            elif "RANK" in os.environ:
                try: rank = int(os.environ["RANK"])
                except: pass
        
        total_bytes = 0
        if isinstance(obj, torch.Tensor):
            total_bytes = obj.numel() * obj.element_size()
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, torch.Tensor):
                    total_bytes += v.numel() * v.element_size()
        
        # Multi-cloud direct streaming setup
        if self.cloud_client:
            import tempfile
            # Check for high-speed POSIX RAM-disk fallback
            temp_dir = "/dev/shm" if os.name == "posix" and os.path.exists("/dev/shm") else tempfile.gettempdir()
            target_file = os.path.join(temp_dir, os.path.basename(filename))
        else:
            target_file = filename

        for attempt in range(self.max_retries + 1):
            try:
                # WARP SUSTAIN: Only stagger if it's the first time
                if rank and rank > 0:
                    stagger = self.config.get("stagger_write_ms", 50)
                    if stagger > 0: _time.sleep((rank * stagger) / 1000.0)

                if not isinstance(obj, torch.Tensor):
                    raise ValueError("NeuralIO engine only supports single torch.Tensor saving. Falling back.")

                # HANDOFF: C++ Broker starts working 
                self.engine.save(obj, target_file, rank)
                
                try:
                    # Async Metrics: These report what the Broker just SAW (Dedupe stats)
                    raw_metrics = dict(getattr(self.engine, 'last_save_metrics', {}))
                    self._log_receipt(filename, raw_metrics, total_bytes, rank)
                except: pass
                
                # If cloud client is configured, run uploader asynchronously in background
                if self.cloud_client:
                    def _bg_cloud_upload(local_recipe, original_filename, rank_idx):
                        self.sync() # Wait for background C++ AsyncIO task to finish writing to local RAM cache
                        
                        vault_name = f"neuralio_shared_vault_rank_{rank_idx}.bin" if rank_idx >= 0 else "neuralio_shared_vault.bin"
                        local_vault = os.path.join(os.path.dirname(local_recipe), vault_name)
                        
                        recipe_cloud_key = os.path.basename(original_filename)
                        
                        # Stream unique vault blocks to Cloud Storage
                        if os.path.exists(local_vault):
                            self.cloud_client.upload_file(local_vault, vault_name)
                        # Stream tiny recipe mapping to Cloud Storage
                        if os.path.exists(local_recipe):
                            self.cloud_client.upload_file(local_recipe, recipe_cloud_key)
                            
                        # Zero-Disk Cloud Cleanup (Clean up recipes, keep vault as active write-through cache)
                        if self.zero_disk_cloud:
                            try:
                                os.remove(local_recipe)
                            except: pass
                            
                    threading.Thread(target=_bg_cloud_upload, args=(target_file, filename, rank), daemon=True).start()
                
                return 

            except Exception as e:
                if attempt < self.max_retries:
                    warnings.warn(f"[NeuralIO] Retry: {e}")
                    self._reset_engine()
                else:
                    warnings.warn(f"[NeuralIO] Final Failure: {e}")

        # Fallback to standard torch.save if everything fails
        _REAL_TORCH_SAVE(obj, filename)

    def load(self, filename, tensor):
        """Accelerated restoration of a tensor from a NeuralIO recipe."""
        if self.acceleration_enabled and self.engine:
            try:
                # If cloud streaming is active, fetch from multi-cloud storage bucket first
                if self.cloud_client:
                    import tempfile
                    temp_dir = "/dev/shm" if os.name == "posix" and os.path.exists("/dev/shm") else tempfile.gettempdir()
                    target_file = os.path.join(temp_dir, os.path.basename(filename))
                    
                    # Determine sharded files names
                    rank = -1
                    if torch.distributed.is_available() and torch.distributed.is_initialized():
                        rank = torch.distributed.get_rank()
                    vault_name = f"neuralio_shared_vault_rank_{rank}.bin" if rank >= 0 else "neuralio_shared_vault.bin"
                    local_vault = os.path.join(temp_dir, vault_name)
                    
                    # Stream down sharded recipe and vault from mock/real cloud bucket
                    recipe_cloud_key = os.path.basename(filename)
                    self.cloud_client.download_file(recipe_cloud_key, target_file)
                    self.cloud_client.download_file(vault_name, local_vault)
                    
                    # Direct VRAM accelerated reconstruction
                    self.engine.load(target_file, tensor)
                    
                    # Clean up RAM Cache (Keep vault intact in write-through cache)
                    if self.zero_disk_cloud:
                        try:
                            os.remove(target_file)
                        except: pass
                    return
                else:
                    self.engine.load(filename, tensor)
                    return
            except Exception as e:
                warnings.warn(f"[NeuralIO] Accelerated load failed: {e}. Falling back to standard torch.load.")
        
        # Fallback to standard torch.load
        data = torch.load(filename)
        tensor.copy_(data)

    def disable(self):
        torch.save = _REAL_TORCH_SAVE
        self.acceleration_enabled = False

    def enable(self):
        _mgr = self
        def _patched_save(obj, f, *args, **kwargs): _mgr.save(obj, f)
        torch.save = _patched_save
        self.acceleration_enabled = True
