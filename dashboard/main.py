
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
import time
import glob
from typing import List, Dict, Optional
from datetime import datetime
from fastapi.responses import FileResponse

# --- Config ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(BASE_DIR, "neuralio_dashboard.jsonl")
DEBUG_MODE = False

app = FastAPI(title="NeuralIO Inspector")

# Fix CORS for development (though we serve static files directly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class SystemStats(BaseModel):
    vram_used_mb: float
    vram_total_mb: float
    gpu_name: str
    io_backend: str
    lifetime_saved_mb: float
    lifetime_roi_usd: float
    dedup_ratio: float
    savings_rate_hr: float
    active: bool

class SettingsModel(BaseModel):
    io_strategy: str
    chunk_size_mb: int
    vram_budget_mb: int
    io_threads: int = 4
    retention_count: int
    webhook_url: Optional[str] = None
    straggler_threshold: float

class TransferLog(BaseModel):
    timestamp: str
    file: str
    effective_speed_gbs: float
    written_mb: float
    metrics: dict

class RenameRequest(BaseModel):
    old_name: str
    new_name: str

# --- Helpers ---

def get_config():
    # 1. Defaults
    config = {
        "io_strategy": "BUFFERED",
        "chunk_size": 1048576 * 4, # 4MB
        "vram_budget_mb": 4096,
        "io_threads": 4,
        "retention_count": 5,
        "webhook_url": None,
        "straggler_threshold": 2.0
    }
    
    # 2. Sync with Disk
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                disk_cfg = json.load(f)
                config.update(disk_cfg)
    except:
        pass
        
    return config

def save_config(new_settings: SettingsModel):
    current = get_config()
    current["io_strategy"] = new_settings.io_strategy
    current["chunk_size"] = new_settings.chunk_size_mb * 1024 * 1024
    current["vram_budget_mb"] = new_settings.vram_budget_mb
    current["io_threads"] = new_settings.io_threads
    current["retention_count"] = new_settings.retention_count
    current["webhook_url"] = new_settings.webhook_url
    current["straggler_threshold"] = new_settings.straggler_threshold
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(current, f, indent=4)

import hashlib
import platform
import socket

def get_gpu_hourly_rate(gpu_name: str) -> float:
    gpu_upper = gpu_name.upper()
    if "5080" in gpu_upper:
        return 1.20
    elif "4090" in gpu_upper:
        return 0.90
    elif "3090" in gpu_upper:
        return 0.50
    elif "H100" in gpu_upper:
        return 2.50
    elif "B200" in gpu_upper or "BLACKWELL" in gpu_upper:
        return 4.50
    elif "A100" in gpu_upper:
        return 2.20
    return 1.00

def get_system_hwid() -> str:
    try:
        gpu_name = ""
        if HAS_TORCH and torch.cuda.is_available():
            try:
                gpu_name = torch.cuda.get_device_name(0)
            except:
                pass
    except:
        gpu_name = ""
    raw = f"{platform.processor()}-{socket.gethostname()}-{platform.system()}-{gpu_name}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16].upper()

def calculate_lifetime_and_status():
    """Reads logs to calculate total savings and infer current status."""
    total_mb = 0.0
    total_roi = 0.0

    # Load configurable storage cost rate ($/GB/month)
    # Default: $0.07 = RunPod NVMe baseline (more accurate than S3 for GPU workloads)
    storage_rate = 0.07
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as _cf:
                storage_rate = json.load(_cf).get("roi_storage_cost_per_gb", 0.07)
    except: pass
    
    # Defaults
    status = {
        "active": False,
        "gpu": "Detecting...", 
        "backend": "AsyncIO (Idle)", 
        "speed": 0.0,
        "hwid": get_system_hwid()
    }

    # 1. Try IPC Status File (Strongest Signal for Realtime)
    if os.path.exists("neuralio_status.json"):
        try:
            mtime = os.path.getmtime("neuralio_status.json")
            if time.time() - mtime < 30: # 30s freshness
                with open("neuralio_status.json", 'r') as f:
                    ipc = json.load(f)
                    status["active"] = True
                    status["gpu"] = ipc.get("gpu_name", "Active GPU")
                    status["backend"] = ipc.get("io_backend", "AsyncIO (Active)")
                    status["speed"] = ipc.get("effective_speed_gbs", 0.0)
                    status["dedup"] = ipc.get("dedup_ratio", 1.0)
        except: pass

    # 2. Iterate Logs for ROI and Fallback Status
    total_seen_mb = 0.0

    if os.path.exists(LOG_FILE):
        try:
             with open(LOG_FILE, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        metrics = data.get('metrics', {})
                        saved = metrics.get('saved_mb', 0.0)
                        
                        # Total ROI calculation
                        # Track Total Throughput to calc average dedupe
                        size_bytes = data.get('size_bytes', 0) or 0
                        size_mb = size_bytes / 1024.0 / 1024.0
                        total_seen_mb += size_mb

                        # Use reported skipped_mb if available
                        deduped = metrics.get('skipped_mb', metrics.get('deduped_mb', 0.0))
                        written = metrics.get('written_mb', metrics.get('saved_mb', 0.0))
                        
                        if deduped > 0:
                            avoided_mb = deduped
                        else:
                            avoided_mb = size_mb - written
                            if avoided_mb < 0: avoided_mb = 0
                        
                        total_mb += avoided_mb # ROI metric shows AVOIDED mb
                        
                        # Compute exact GPU hourly cost rate based on active GPU
                        active_gpu = status.get("gpu", "GeForce RTX 5080")
                        gpu_rate = get_gpu_hourly_rate(active_gpu)
                        
                        # Storage savings
                        storage_savings = (avoided_mb / 1024.0 * storage_rate)
                        
                        # GPU Compute Stall savings
                        # Baseline standard save speed is ~0.25 GB/s
                        t_standard = size_mb / 256.0
                        t_nio = metrics.get("io_time_ms", 1000.0) / 1000.0
                        t_saved = max(0.0, t_standard - t_nio)
                        compute_savings = (t_saved / 3600.0) * gpu_rate
                        
                        total_roi += (storage_savings + compute_savings)
                        
                        # Fallback Status Inference (Log Tail Check)
                        if not status["active"]:
                            ts_str = data.get('timestamp')
                            if ts_str:
                                ts = datetime.fromisoformat(ts_str)
                                if (datetime.now() - ts).total_seconds() < 30: # 30s
                                    status["active"] = True
                                    status["gpu"] = "Active (Log Inference)"
                                    status["backend"] = "AsyncIO (Active)"
                                    status["speed"] = metrics.get('effective_speed_gbs', 0.0)
                                    status["dedup"] = metrics.get('dedup_ratio', 1.0)
                    except: continue
        except: pass

    written_mb = total_seen_mb - total_mb
    if written_mb < 0.1: written_mb = 0.1
    
    global_ratio = total_seen_mb / written_mb
    status["dedup"] = global_ratio

    return total_mb, total_roi, status

# --- API ---

@app.get("/api/system")
def api_system():
    saved_mb, roi_usd, status = calculate_lifetime_and_status()
    
    return {
        "vram_used_mb": 0.0, # We don't have direct GPU access in dashboard proc usually
        "vram_total_mb": 0.0,
        "gpu_name": status["gpu"],
        "hwid": status.get("hwid", "UNKNOWN"),
        "gpu_rate": get_gpu_hourly_rate(status["gpu"]),
        "io_backend": status["backend"],
        "lifetime_saved_mb": saved_mb,
        "lifetime_roi_usd": roi_usd,
        "dedup_ratio": status.get("dedup", 1.0),
        "savings_rate_hr": status["speed"] * 3600.0 * 0.01, # Mock rate
        "effective_speed_gbs": status["speed"],
        "active": status["active"]
    }

@app.get("/api/topology")
def api_topology():
    _, _, status = calculate_lifetime_and_status()
    is_active = status["active"]
    speed_ratio = min(status["speed"] / 10.0, 1.0) # Map 0-10GB/s to 0-1
    
    nodes = []
    # GPU
    nodes.append({"id": 0, "type": "COMPUTE", "label": "GPU", "activity": 1.0 if is_active else 0.0})
    # Host
    nodes.append({"id": 1, "type": "COMPUTE", "label": "HOST", "activity": 0.8 if is_active else 0.0})
    
    # Dynamic Storage Nodes
    num_threads = 4
    active_threads = max(1, int(num_threads * speed_ratio)) if is_active else 0
    
    links = []
    if is_active:
        links.append({"source": 0, "target": 1, "intensity": 1.0})
    
    for i in range(num_threads):
        node_active = 0.0
        if is_active and i < active_threads:
            node_active = 0.5 + (speed_ratio * 0.5)
            links.append({"source": 1, "target": 2+i, "intensity": speed_ratio})
            
        nodes.append({
            "id": 2 + i, "type": "STORAGE", "label": f"IO-{i}", "activity": node_active
        })

    return {
        "nodes": nodes,
        "links": links,
        "active": is_active
    }

@app.get("/api/settings")
def api_get_settings():
    c = get_config()
    return {
        "io_strategy": c.get("io_strategy", "BUFFERED"),
        "chunk_size_mb": c.get("chunk_size", 4194304) // (1024*1024),
        "vram_budget_mb": c.get("vram_budget_mb", None),  # None = auto-detected
        "io_threads": c.get("io_threads", 4),
        "retention_count": c.get("retention_count", 5),
        "webhook_url": c.get("webhook_url"),
        "straggler_threshold": c.get("straggler_threshold", 2.0)
    }

@app.post("/api/settings")
def api_set_settings(s: SettingsModel):
    try:
        save_config(s)
        return {"status": "ok", "message": "Settings saved. Restart application to apply."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history", response_model=List[TransferLog])
def api_history():
    data = []
    if not os.path.exists(LOG_FILE):
        return []
    
    try:
        with open(LOG_FILE, 'r') as f:
            for line in f:
                try:
                    raw = json.loads(line)
                    metrics = raw.get('metrics', {})
                    entry = TransferLog(
                        timestamp=raw.get('timestamp'),
                        file=raw.get('file'),
                        effective_speed_gbs=metrics.get('effective_speed_gbs', 0.0),
                        written_mb=metrics.get('written_mb', metrics.get('saved_mb', 0.0)),
                        metrics=metrics
                    )
                    data.append(entry)
                except: continue
    except: pass
    return data[-50:] # Return last 50

@app.delete("/api/history")
def api_clear_history():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    return {"status": "ok"}

# --- Audit & File Explorer ---

@app.get("/api/audit/files")
async def list_audit_files():
    try:
        # Get all CSVs in current directory (where dashboard runs)
        # This handles the case where they are generated in CWD
        files = glob.glob("*.csv") 
        audit_files = []
        for f in files:
            stat = os.stat(f)
            audit_files.append({
                "name": f,
                "size_kb": stat.st_size / 1024,
                "mtime": stat.st_mtime,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
        audit_files.sort(key=lambda x: x["mtime"], reverse=True)
        return audit_files
    except:
        return []

@app.get("/api/audit/content/{filename}")
async def get_audit_content(filename: str):
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not os.path.exists(filename):
        # Fallback: Check if it exists with .csv extension if missing
        if os.path.exists(filename + ".csv"):
            filename += ".csv"
        else:
             raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    try:
        rows = []
        with open(filename, "r") as f:
            header = f.readline().strip()
            count = 0
            for line in f:
                if count > 1000: break
                rows.append(line.strip())
                count += 1
        return {"header": header, "rows": rows, "truncated": count > 1000}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audit/download/{filename}")
async def download_audit_file(filename: str):
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Robust Path Check
    target_path = os.path.abspath(filename)
    if not os.path.exists(target_path):
         raise HTTPException(status_code=404, detail=f"File not found: {filename}")
         
    return FileResponse(target_path, media_type='text/csv', filename=filename)

@app.post("/api/audit/rename")
async def rename_audit_file(req: RenameRequest):
    if ".." in req.old_name or "/" in req.old_name:
         raise HTTPException(status_code=400, detail="Invalid filename")
    if not os.path.exists(req.old_name):
        raise HTTPException(status_code=404, detail="File not found")
        
    if not req.new_name.endswith(".csv"):
        req.new_name += ".csv"
    
    os.rename(req.old_name, req.new_name)
    return {"status": "success", "new_name": req.new_name}

# --- VRAM Auto-Detect ---

@app.get("/api/vram/autodetect")
def api_vram_autodetect():
    """Returns the VRAM budget NeuralIO would auto-detect for the current GPU."""
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            total_mem_gb = props.total_memory / (1024**3)
            budget_mb = max(512, int(min(total_mem_gb * 0.10, 16.0) * 1024))
            return {
                "gpu_name": props.name,
                "total_vram_mb": int(total_mem_gb * 1024),
                "recommended_budget_mb": budget_mb,
                "formula": "10% of VRAM, max 16 GB"
            }
        else:
            return {"gpu_name": "No CUDA GPU", "total_vram_mb": 0, "recommended_budget_mb": 512, "formula": "fallback"}
    except Exception as e:
        return {"error": str(e), "recommended_budget_mb": 512}

@app.post("/api/settings/vram-auto")
def api_vram_set_auto():
    """Removes manual vram_budget_mb override from config — restores auto-detection."""
    try:
        c = get_config()
        c.pop("vram_budget_mb", None)  # Remove override key entirely
        with open("neuralio_config.json", 'w') as f:
            json.dump(c, f, indent=4)
        return {"status": "ok", "message": "VRAM budget reset to auto-detection."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Static Mount (Last)
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("NEURALIO_DASHBOARD_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

