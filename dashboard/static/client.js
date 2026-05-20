
// NeuralIO Dashboard Client
// (c) 2026 NeuralIO

// --- Global State ---
let topologyData = { nodes: [], links: [], active: false };
let isSimulation = false;

// --- Tab Logic ---
function switchTab(tabId) {
    document.querySelectorAll('.view-panel').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.nav-links a').forEach(el => el.classList.remove('active'));

    document.getElementById(`view-${tabId}`).style.display = 'block';
    document.getElementById(`nav-${tabId}`).classList.add('active');

    const titles = {
        'dashboard': 'Operational Overview',
        'settings': 'System Configuration',
        'logs': 'Audit Logs'
    };
    document.getElementById('page-title').innerText = titles[tabId];
}

// --- Chart Init ---
const ctx = document.getElementById('speedChart').getContext('2d');
const gradient = ctx.createLinearGradient(0, 0, 0, 400);
gradient.addColorStop(0, 'rgba(0, 242, 255, 0.4)');
gradient.addColorStop(1, 'rgba(0, 242, 255, 0)');

const speedChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'Speed',
            data: [],
            borderColor: '#00f2ff',
            borderWidth: 2,
            backgroundColor: gradient,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHoverRadius: 6
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, beginAtZero: true, ticks: { color: '#8b9bb4' } },
            x: { display: false }
        },
        interaction: { intersect: false, mode: 'index' }
    }
});

// --- Visualizer Logic ---
const canvas = document.getElementById('topologyCanvas');
const c = canvas.getContext('2d');
let width, height;

function resizeCanvas() {
    width = canvas.parentElement.offsetWidth;
    height = canvas.parentElement.offsetHeight;
    canvas.width = width;
    canvas.height = height;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// Animation Loop
function animate() {
    requestAnimationFrame(animate);
    c.clearRect(0, 0, width, height);

    // If backend reports idle, don't draw particles
    if (!topologyData.active) {
        c.font = "14px Inter";
        c.fillStyle = "rgba(255, 255, 255, 0.2)";
        c.textAlign = "center";
        c.fillText("System Idle", width / 2, height / 2);
        return;
    }

    // Draw Links
    c.strokeStyle = 'rgba(0, 242, 255, 0.15)';
    c.lineWidth = 1;

    // Map abstract IDs to canvas positions
    // Simple layout: Compute nodes on left, Storage on right
    const getPos = (id, type) => {
        // Deterministic pseudo-random position based on ID
        const y = (id * 12345 % 80) + 10;
        const x = type === 'COMPUTE' ? 20 : 80;
        return {
            x: (x / 100) * width,
            y: (y / 100) * height
        };
    };

    topologyData.links.forEach(link => {
        const start = getPos(link.source, 'COMPUTE');
        const end = getPos(link.target, 'STORAGE');

        c.beginPath();
        c.moveTo(start.x, start.y);
        // Bezier curve
        c.bezierCurveTo(start.x + 50, start.y, end.x - 50, end.y, end.x, end.y);
        c.stroke();

        // "Data Packet" particle
        const time = Date.now() / 1000;
        const offset = (time + link.source * 0.5) % 1;
        // Interpolate bezier approx (simplified linear for speed)
        const px = start.x + (end.x - start.x) * offset;
        const py = start.y + (end.y - start.y) * offset;

        c.fillStyle = '#00f2ff';
        c.beginPath();
        c.arc(px, py, 2, 0, Math.PI * 2);
        c.fill();
    });

    // Draw Nodes
    topologyData.nodes.forEach(node => {
        const pos = getPos(node.id, node.type);

        // Glow
        const glow = c.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, 20);
        glow.addColorStop(0, node.type === 'COMPUTE' ? 'rgba(189, 0, 255, 0.4)' : 'rgba(0, 242, 255, 0.4)');
        glow.addColorStop(1, 'rgba(0,0,0,0)');

        c.fillStyle = glow;
        c.beginPath();
        c.arc(pos.x, pos.y, 20, 0, Math.PI * 2);
        c.fill();

        // Core
        c.fillStyle = '#fff';
        c.beginPath();
        c.arc(pos.x, pos.y, 3, 0, Math.PI * 2);
        c.fill();
    });
}
animate();

// --- Data Fetching ---
async function fetchData() {
    let finalRatio; // Declare in function scope

    try {
        // 1. System Stats
        const sysRes = await fetch('/api/system');
        const sysData = await sysRes.json();

        document.getElementById('gpu-name').innerText = sysData.gpu_name;
        document.getElementById('io-backend').innerText = sysData.io_backend;
        document.getElementById('money-saved').innerText = `$${sysData.lifetime_roi_usd.toFixed(2)}`;

        // Dedupe Ratio: Defer update until we check history
        finalRatio = sysData.dedup_ratio;
        // document.getElementById('dedup-ratio').innerText = ...

        // Check Simulation Mode (If ratio is basically 1.0 logic)
        // In full production mode, we calculate ratio truthfully but don't show the 'Simulation' badge warning.
        document.getElementById('sim-badge').style.display = 'none';

        // 2. Topology Mock Data
        const topRes = await fetch('/api/topology');
        const topData = await topRes.json();
        topologyData = topData; // Swap data for visualizer

        // 3. History
        const histRes = await fetch('/api/history');
        const histData = await histRes.json();

        if (histData.length > 0) {
            const latest = histData[histData.length - 1];
            document.getElementById('speed-val').innerText = latest.effective_speed_gbs.toFixed(2);

            // FIX: Prioritize the Ratio from the actual logs -> DISABLED
            // We want Lifetime Ratio (from System Stats), not Instantaneous Ratio of the last chunk
            /*
            if (latest.metrics) {
                // Check multiple casing variants just in case
                const r = latest.metrics.dedup_ratio || latest.metrics.deduplication_ratio;
                if (typeof r === 'number' && r > 0) {
                    finalRatio = r;
                }
            }
            */

            // Update Chart
            const labels = histData.map(d => d.timestamp.split('T')[1].split('.')[0]);
            speedChart.data.labels = labels;
            speedChart.data.datasets[0].data = histData.map(d => d.effective_speed_gbs);
            speedChart.update('none'); // No anim for update performance

            // Recent Table
            const tbody = document.getElementById('log-table-body');
            tbody.innerHTML = histData.slice(-5).reverse().map(row => `
                <tr>
                    <td>${row.timestamp.split('T')[1].split('.')[0]}</td>
                    <td style="opacity:0.8">${row.file}</td>
                    <td>${row.written_mb.toFixed(0)} MB</td>
                </tr>
            `).join('');

            // Full Table
            if (document.getElementById('view-logs').style.display !== 'none') {
                document.getElementById('full-log-body').innerHTML = histData.reverse().map(row => `
                    <tr>
                        <td>${row.timestamp.replace('T', ' ').split('.')[0]}</td>
                        <td>${row.file}</td>
                        <td>${row.written_mb.toFixed(1)}</td>
                        <td>${row.effective_speed_gbs.toFixed(2)}</td>
                        <td>${row.metrics?.compute_time_ms ? row.metrics.compute_time_ms.toFixed(1) : '--'}</td>
                    </tr>
                `).join('');
            }
        }

    } catch (e) {
        console.warn("Fetch Error", e);
    }

    // Final Render (After both System and History checks)
    const el = document.getElementById('dedup-ratio');
    if (el && typeof finalRatio !== 'undefined') {
        el.innerText = `${finalRatio.toFixed(1)}x`;
    }
}

// Init
setInterval(fetchData, 1000);
fetchData();
loadSettings(); // Reuse existing logic key

async function loadSettings() {
    try {
        // Fetch saved config
        const res = await fetch('/api/settings');
        const data = await res.json();
        document.getElementById('cfg-chunk').value = data.chunk_size_mb;
        document.getElementById('cfg-threads').value = data.io_threads;
        document.getElementById('cfg-strategy').value = data.io_strategy || 'BUFFERED';

        // VRAM: null means auto-detect mode
        const badge  = document.getElementById('vram-mode-badge');
        const input  = document.getElementById('cfg-vram');
        const hint   = document.getElementById('vram-hint');

        // Always fetch the GPU-detected value for the hint
        const adRes  = await fetch('/api/vram/autodetect');
        const adData = await adRes.json();
        const detectedMb = adData.recommended_budget_mb || 0;
        const gpuName    = adData.gpu_name || 'GPU';

        if (data.vram_budget_mb == null) {
            // AUTO mode
            input.value = '';
            input.placeholder = `${detectedMb} MB (auto)`;
            badge.textContent  = 'AUTO';
            badge.style.background = 'rgba(0,242,255,0.15)';
            badge.style.color = '#00f2ff';
            hint.textContent = `${gpuName}: ${adData.total_vram_mb || '?'} MB total → ${detectedMb} MB budget (10%)`;
        } else {
            // MANUAL mode
            input.value = data.vram_budget_mb;
            badge.textContent  = 'MANUAL';
            badge.style.background = 'rgba(255,160,0,0.15)';
            badge.style.color = '#ffa000';
            hint.textContent = `Auto would use ${detectedMb} MB — click ⟳ Auto to restore.`;
        }
    } catch (e) { }
}

function onVramManualEdit() {
    const badge = document.getElementById('vram-mode-badge');
    const val   = document.getElementById('cfg-vram').value;
    if (val && parseInt(val) > 0) {
        badge.textContent = 'MANUAL';
        badge.style.background = 'rgba(255,160,0,0.15)';
        badge.style.color = '#ffa000';
    }
}

async function resetVramToAuto() {
    try {
        await fetch('/api/settings/vram-auto', { method: 'POST' });
        await loadSettings(); // Refresh UI
        const msg = document.getElementById('cfg-msg');
        msg.innerText = 'VRAM reset to auto-detection.';
        msg.style.color = '#00f2ff';
        setTimeout(() => msg.innerText = '', 4000);
    } catch (e) {
        alert('Failed to reset VRAM: ' + e);
    }
}

// --- Features ---

async function saveSettings() {
    const vramInput = parseInt(document.getElementById('cfg-vram').value);
    const s = {
        io_strategy: document.getElementById('cfg-strategy').value,
        chunk_size_mb: parseInt(document.getElementById('cfg-chunk').value),
        io_threads: parseInt(document.getElementById('cfg-threads').value),
        retention_count: 5,
        webhook_url: null,
        straggler_threshold: 2.0
    };
    // Only include vram_budget_mb if it's a valid manual number
    // Leaving it absent = auto-detection continues
    if (!isNaN(vramInput) && vramInput > 0) {
        s.vram_budget_mb = vramInput;
    }

    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(s)
        });
        const data = await res.json();

        // UI Feedback
        const msg = document.getElementById('cfg-msg');
        if (res.ok) {
            msg.innerText = "Saved! Restart required.";
            msg.style.color = "#00f2ff";
        } else {
            msg.innerText = "Error: " + data.detail;
            msg.style.color = "#ff4444";
        }
        setTimeout(() => msg.innerText = "", 5000);

    } catch (e) {
        alert("Failed to save settings: " + e);
    }
}

// --- Export / Clear ---
function exportCSV() {
    // Legacy: Redirect to download the currently active log
    // Better workflow is using the Log Explorer tab.
    window.location.href = `/api/audit/download/neuralio_dashboard.jsonl`;
}

function clearLogs() {
    if (!confirm("Are you sure you want to clear all audit logs?")) return;

    fetch('/api/history', { method: 'DELETE' })
        .then(res => res.json())
        .then(() => {
            // UI Feedback: Reload Data
            fetchData();
            document.getElementById('full-log-body').innerHTML = '';
            document.getElementById('log-table-body').innerHTML = '';
            speedChart.data.labels = [];
            speedChart.data.datasets[0].data = [];
            speedChart.update();
        });
}

// --- Audit Explorer Logic ---
class NeuralIOClient {
    constructor() {
        this.currentFile = null;
        this.startPeriodicRefresh();
    }

    async loadAuditFiles() {
        try {
            const response = await fetch('/api/audit/files');
            const files = await response.json();
            this.renderFileList(files);
        } catch (e) {
            console.error("Failed to load audit files", e);
        }
    }

    renderFileList(files) {
        const listEl = document.getElementById('audit-file-list');
        if (!listEl) return;

        listEl.innerHTML = '';

        if (files.length === 0) {
            listEl.innerHTML = '<div style="padding:10px; color:var(--text-dim)">No logs found.</div>';
            return;
        }

        files.forEach(f => {
            const item = document.createElement('div');
            item.className = 'file-item';
            if (this.currentFile === f.name) item.classList.add('active');

            item.innerHTML = `
                <div class="file-name">${f.name}</div>
                <div class="file-meta">
                    <span>${f.size_kb.toFixed(1)} KB</span>
                    <span>${new Date(f.mtime * 1000).toLocaleTimeString()}</span>
                </div>
            `;
            item.onclick = () => this.selectFile(f.name);
            listEl.appendChild(item);
        });
    }

    async selectFile(filename) {
        this.currentFile = filename;
        const fnEl = document.getElementById('preview-filename');
        if (fnEl) fnEl.textContent = filename;

        this.loadAuditFiles(); // Re-render to update active class check (lazy way)

        const contentEl = document.getElementById('preview-content');
        contentEl.innerHTML = '<div style="padding:20px; text-align:center">Loading...</div>';

        try {
            const res = await fetch(`/api/audit/content/${filename}`);
            const data = await res.json();

            if (data.detail) throw new Error(data.detail);

            // Parse CSV lines to Table
            const headers = data.header.split(',');

            let html = '<table class="csv-table"><thead><tr>';
            headers.forEach(h => html += `<th>${h}</th>`);
            html += '</tr></thead><tbody>';

            data.rows.forEach(row => {
                if (!row) return;
                const cols = row.split(',');
                html += '<tr>';
                cols.forEach(c => html += `<td>${c}</td>`);
                html += '</tr>';
            });

            html += '</tbody></table>';

            if (data.truncated) {
                html += '<div style="padding:10px; text-align:center; color:var(--warning)">⚠️ Preview truncated (showing first 1000 lines). Download for full content.</div>';
            }

            contentEl.innerHTML = html;
        } catch (e) {
            contentEl.innerHTML = `<div style="padding:20px; color:var(--error)">Error: ${e.message}</div>`;
        }
    }

    async renameFile() {
        if (!this.currentFile) return;
        const newName = prompt("Rename file to:", this.currentFile);
        if (newName && newName !== this.currentFile) {
            try {
                const res = await fetch('/api/audit/rename', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ old_name: this.currentFile, new_name: newName })
                });
                if (res.ok) {
                    this.loadAuditFiles();
                    this.selectFile(newName.endsWith('.csv') ? newName : newName + '.csv');
                } else {
                    alert("Rename failed");
                }
            } catch (e) {
                alert("Error: " + e);
            }
        }
    }

    downloadFile() {
        if (!this.currentFile) return;
        window.location.href = `/api/audit/download/${this.currentFile}`;
    }

    refreshAuditFiles() {
        this.loadAuditFiles();
    }

    startPeriodicRefresh() {
        // Also setup tab listener to refresh when Audit tab is opened
        const auditTab = document.getElementById('nav-logs');
        if (auditTab) {
            auditTab.addEventListener('click', () => this.loadAuditFiles());
        }
        setInterval(() => this.loadAuditFiles(), 15000);
    }
}

// Initialize Global Controller
const globalClient = new NeuralIOClient();
window.globalClient = globalClient;
