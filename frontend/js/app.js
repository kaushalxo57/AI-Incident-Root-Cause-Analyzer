// AI Incident & Root-Cause Analyzer Client Logic

// Application State
let currentTab = 'dashboard';
let incidentsList = [];
let selectedIncidentId = null;
let errorRateChart = null;
let severityChart = null;

// API Base URL (relative since we serve frontend from FastAPI)
const API_BASE = "";

// Initialize App
document.addEventListener("DOMContentLoaded", () => {
    // Setup Ingest file upload listeners
    setupUploadHandlers();
    
    // Initial fetch of data
    refreshData();

    // Refresh telemetry every 30 seconds
    setInterval(refreshTelemetryOnly, 30000);
});

// Switch Tab Panes
function switchTab(tabName) {
    currentTab = tabName;
    
    // Toggle active classes on tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    const activeBtn = document.getElementById(`tab-${tabName}`);
    if (activeBtn) activeBtn.classList.add('active');

    // Toggle active classes on content panes
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    const activePane = document.getElementById(`pane-${tabName}`);
    if (activePane) activePane.classList.add('active');

    // Fetch tab-specific data
    if (tabName === 'dashboard') {
        refreshData();
    } else if (tabName === 'incidents') {
        loadIncidents();
    } else if (tabName === 'services') {
        loadServices();
    }
}

// Refresh all telemetry and details
async function refreshData() {
    updateConnectionStatus("CHECKING...");
    try {
        await fetchAnalytics();
        updateConnectionStatus("ESTABLISHED");
    } catch (err) {
        console.error("Failed to load analytics: ", err);
        updateConnectionStatus("OFFLINE");
    }
}

// Minimal background checks
async function refreshTelemetryOnly() {
    try {
        const response = await fetch(`${API_BASE}/api/analytics`);
        if (response.ok) {
            const data = await response.json();
            updateGlobalTelemetry(data);
        }
    } catch (err) {
        console.warn("Liveness ping failed: ", err);
    }
}

function updateConnectionStatus(status) {
    const footer = document.getElementById("footer-connection-status");
    if (footer) {
        footer.textContent = `CONNECTION: ${status}`;
        if (status === "OFFLINE") {
            footer.style.color = "var(--color-error)";
        } else if (status === "ESTABLISHED") {
            footer.style.color = "var(--color-ok)";
        } else {
            footer.style.color = "var(--color-text-mute)";
        }
    }
}

// Fetch Analytics Summary and populate Dashboard
async function fetchAnalytics() {
    const response = await fetch(`${API_BASE}/api/analytics`);
    if (!response.ok) throw new Error("API call failed");
    const data = await response.json();

    // 1. Update KPI widgets
    document.getElementById("metric-health").textContent = data.system_health_score;
    document.getElementById("metric-health-bar").style.width = `${data.system_health_score}%`;
    document.getElementById("metric-incidents").textContent = data.active_incidents;
    document.getElementById("metric-services").textContent = data.total_services;
    document.getElementById("metric-events").textContent = formatNumber(data.total_events);

    updateGlobalTelemetry(data);

    // Update active incidents preview list in Dashboard
    loadActiveIncidentsPreview();

    // Update mini service statuses
    renderMiniServicesGrid(data.service_health);

    // 2. Render Charts
    renderErrorRateChart(data.error_rate_timeline);
    renderSeverityChart(data.severity_distribution);
}

function updateGlobalTelemetry(data) {
    const globalCount = document.getElementById("global-active-count");
    if (globalCount) globalCount.textContent = data.active_incidents;

    const globalIndicator = document.getElementById("global-status-indicator");
    if (globalIndicator) {
        globalIndicator.classList.remove('status-ok', 'status-degraded', 'status-critical');
        if (data.active_incidents === 0) {
            globalIndicator.textContent = "OPERATIONAL";
            globalIndicator.classList.add('status-ok');
        } else {
            // Check severity of active incidents
            const hasCritical = data.service_health.some(s => s.status === "CRITICAL");
            if (hasCritical) {
                globalIndicator.textContent = "CRITICAL DEGRADATION";
                globalIndicator.classList.add('status-critical');
            } else {
                globalIndicator.textContent = "DEGRADED TELEMETRY";
                globalIndicator.classList.add('status-degraded');
            }
        }
    }
}

// Format integers
function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num;
}

// Render active incidents on dashboard
async function loadActiveIncidentsPreview() {
    const container = document.getElementById("active-incidents-list");
    try {
        const res = await fetch(`${API_BASE}/api/incidents?status=OPEN`);
        if (!res.ok) throw new Error();
        const incidents = await res.json();
        
        container.innerHTML = "";
        if (incidents.length === 0) {
            container.innerHTML = `
                <div class="incident-item" style="cursor: default; justify-content: center; background-color: transparent; border-style: dashed;">
                    <span style="color: var(--color-text-mute); font-family: var(--font-heading); font-size: 11px;">
                        NO ACTIVE INCIDENTS CURRENTLY LOGGED // SYSTEM CLEAR
                    </span>
                </div>
            `;
            return;
        }

        incidents.forEach(inc => {
            const timeStr = formatRelativeTime(inc.start_time);
            const item = document.createElement("div");
            item.className = "incident-item";
            item.onclick = () => {
                switchTab('incidents');
                selectIncident(inc.id);
            };

            item.innerHTML = `
                <div class="incident-left">
                    <div class="incident-header-row">
                        <span class="badge badge-${inc.severity.toLowerCase()}">${inc.severity}</span>
                        <span class="incident-title-text">${inc.title}</span>
                    </div>
                    <div class="incident-summary-text">${inc.summary}</div>
                </div>
                <div class="incident-right">
                    <div>RC: ${inc.root_cause || "UNKNOWN"}</div>
                    <div style="font-size: 10px; color: var(--color-text-mute); margin-top: 3px;">DETECTED: ${timeStr}</div>
                </div>
            `;
            container.appendChild(item);
        });
    } catch (e) {
        container.innerHTML = `<div class="loading-placeholder term-err">FAILED TO FETCH INCIDENTS.</div>`;
    }
}

// Render microservices summary grid
function renderMiniServicesGrid(services) {
    const container = document.getElementById("dashboard-services-grid");
    container.innerHTML = "";

    if (!services || services.length === 0) {
        container.innerHTML = `<div class="loading-placeholder">NO MONITORED SERVICES DETECTED</div>`;
        return;
    }

    services.forEach(svc => {
        const card = document.createElement("div");
        card.className = "service-mini-card";
        card.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px;">
                <span class="service-mini-status status-${svc.status}"></span>
                <span class="service-mini-name">${svc.name}</span>
            </div>
            <div class="service-mini-metrics">
                <span>ERR_RATE: ${svc.error_rate}%</span>
                <span style="color: var(--color-text-mute)">|</span>
                <span>ANOMALIES: ${svc.anomaly_count}</span>
            </div>
        `;
        container.appendChild(card);
    });
}

// Render Error Rate Line Chart
function renderErrorRateChart(timelineData) {
    const ctx = document.getElementById('errorRateChart').getContext('2d');
    
    if (errorRateChart) {
        errorRateChart.destroy();
    }

    const labels = timelineData.map(d => {
        const date = new Date(d.timestamp);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });
    const rates = timelineData.map(d => d.rate);

    errorRateChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'ERROR_RATE (%)',
                data: rates,
                borderColor: '#d91a2a',
                borderWidth: 1.5,
                backgroundColor: 'rgba(217, 26, 42, 0.05)',
                fill: true,
                tension: 0.1,
                pointRadius: 2,
                pointBackgroundColor: '#d91a2a',
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: '#141416' },
                    ticks: { color: '#8e8e93', font: { family: 'Space Grotesk', size: 9 } }
                },
                y: {
                    grid: { color: '#141416' },
                    ticks: { color: '#8e8e93', font: { family: 'Space Grotesk', size: 9 } },
                    min: 0,
                    max: 100
                }
            }
        }
    });
}

// Render Incident Severity distribution
function renderSeverityChart(distribution) {
    const ctx = document.getElementById('severityChart').getContext('2d');
    
    if (severityChart) {
        severityChart.destroy();
    }

    const labels = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
    const counts = [0, 0, 0, 0];

    distribution.forEach(item => {
        const idx = labels.indexOf(item.severity.toUpperCase());
        if (idx !== -1) {
            counts[idx] = item.count;
        }
    });

    severityChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                data: counts,
                backgroundColor: ['#d91a2a', '#ea580c', '#f59e0b', '#71717a'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#8e8e93', font: { family: 'Space Grotesk', size: 9 } }
                },
                y: {
                    grid: { color: '#141416' },
                    ticks: { color: '#8e8e93', font: { family: 'Space Grotesk', size: 9 }, stepSize: 1 }
                }
            }
        }
    });
}

// --- INCIDENTS TAB LOGIC ---
async function loadIncidents() {
    const sidebar = document.getElementById("incidents-list");
    sidebar.innerHTML = `<div class="loading-placeholder">LOADING LOGS...</div>`;

    const searchQuery = document.getElementById("incidents-search").value;
    const severity = document.getElementById("filter-severity").value;
    const status = document.getElementById("filter-status").value;

    let url = `${API_BASE}/api/incidents?`;
    if (searchQuery) url += `search=${encodeURIComponent(searchQuery)}&`;
    if (severity) url += `severity=${severity}&`;
    if (status) url += `status=${status}&`;

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error();
        incidentsList = await res.json();

        sidebar.innerHTML = "";
        if (incidentsList.length === 0) {
            sidebar.innerHTML = `<div class="loading-placeholder">NO INCIDENTS MATCHING FILTERS</div>`;
            return;
        }

        incidentsList.forEach(inc => {
            const item = document.createElement("div");
            item.className = `sidebar-incident-item ${selectedIncidentId === inc.id ? 'active' : ''}`;
            item.id = `sidebar-inc-${inc.id}`;
            item.onclick = () => selectIncident(inc.id);

            const timeStr = new Date(inc.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            
            item.innerHTML = `
                <div class="sidebar-inc-title">${inc.title}</div>
                <div class="sidebar-inc-meta">
                    <span class="badge badge-${inc.severity.toLowerCase()}">${inc.severity}</span>
                    <span class="badge badge-${inc.status.toLowerCase()}">${inc.status}</span>
                    <span>${timeStr}</span>
                </div>
            `;
            sidebar.appendChild(item);
        });

        // Auto select first incident if none selected
        if (!selectedIncidentId && incidentsList.length > 0) {
            selectIncident(incidentsList[0].id);
        } else if (selectedIncidentId) {
            // Keep current selection if still in filtered list
            const stillExists = incidentsList.some(i => i.id === selectedIncidentId);
            if (stillExists) {
                selectIncident(selectedIncidentId);
            } else {
                selectIncident(incidentsList[0].id);
            }
        }
    } catch (e) {
        sidebar.innerHTML = `<div class="loading-placeholder term-err">FAILED TO LOAD RECORDS.</div>`;
    }
}

// Triggered when sidebar search inputs change
function filterIncidents() {
    loadIncidents();
}

// Select and load specific incident details
async function selectIncident(id) {
    selectedIncidentId = id;
    
    // Toggle active sidebar highlight
    document.querySelectorAll(".sidebar-incident-item").forEach(item => {
        item.classList.remove("active");
    });
    const activeItem = document.getElementById(`sidebar-inc-${id}`);
    if (activeItem) activeItem.classList.add("active");

    const detailContainer = document.getElementById("incident-detail-pane");
    detailContainer.innerHTML = `<div class="loading-placeholder">DECRYPTING LOG EVENTS...</div>`;

    try {
        const res = await fetch(`${API_BASE}/api/incidents/${id}`);
        if (!res.ok) throw new Error();
        const inc = await res.json();

        const startDateStr = new Date(inc.start_time).toLocaleString();
        const endDateStr = inc.end_time ? new Date(inc.end_time).toLocaleString() : "ACTIVE";

        detailContainer.innerHTML = `
            <div class="incident-detail-header">
                <div class="detail-title-row">
                    <h2 class="detail-title">${inc.title}</h2>
                    <div class="detail-badges">
                        <span class="badge badge-${inc.severity.toLowerCase()}">${inc.severity}</span>
                        <span class="badge badge-${inc.status.toLowerCase()}">${inc.status}</span>
                    </div>
                </div>
                <div class="detail-timestamp">
                    DETECTED: ${startDateStr} // RESOLVED: ${endDateStr}
                </div>
            </div>

            <div class="detail-analysis-grid">
                <!-- Root cause and summary -->
                <div class="rc-card">
                    <div class="rc-header">■ LIKELY_ROOT_CAUSE</div>
                    <div class="rc-value">${inc.root_cause || "UNKNOWN"}</div>
                    <div class="rc-summary">${inc.summary}</div>
                </div>

                <!-- Incident Telemetry Meta -->
                <div class="metadata-card">
                    <div class="rc-header" style="color: var(--color-text-mute)">■ RUN_METADATA</div>
                    <div class="meta-row">
                        <span class="meta-label">CONFIDENCE:</span>
                        <span class="meta-val" style="color: ${inc.confidence >= 0.8 ? 'var(--color-ok)' : 'var(--color-warning)'}">${(inc.confidence * 100).toFixed(0)}%</span>
                    </div>
                    <div class="meta-row">
                        <span class="meta-label">AFFECTED:</span>
                        <span class="meta-val">${inc.affected_services.join(", ")}</span>
                    </div>
                    <div class="meta-row">
                        <span class="meta-label">RECORD_ID:</span>
                        <span class="meta-val">#${inc.id}</span>
                    </div>
                </div>
            </div>

            <!-- Chronological Timeline -->
            <div class="section-container">
                <h3 class="section-title">■ PROPAGATION_CHRONICLE_TIMELINE</h3>
                <div class="timeline-container" id="incident-events-timeline">
                    <!-- Events will load here -->
                </div>
            </div>

            <!-- Related Log Details -->
            <div class="section-container">
                <h3 class="section-title">■ ANOMALOUS_LOG_DUMPS</h3>
                <div class="terminal-output" style="height: 180px;" id="incident-logs-dump">
                    <!-- Log dumps -->
                </div>
            </div>

            <!-- Action Status buttons -->
            <div class="status-updater">
                ${inc.status === "OPEN" || inc.status === "INVESTIGATING" ? `
                    <button class="action-btn" onclick="updateStatus(${inc.id}, 'RESOLVED')">MARK_AS_RESOLVED</button>
                ` : `
                    <span style="font-family: var(--font-heading); font-size: 10px; color: var(--color-ok);">
                        ✓ THIS INCIDENT HAS BEEN CLASSIFIED AS RESOLVED
                    </span>
                `}
            </div>
        `;

        // Render timeline events
        renderTimelineEvents(inc.events);

        // Render Log dump details
        renderIncidentLogsDump(inc.evidence);

    } catch (e) {
        detailContainer.innerHTML = `<div class="loading-placeholder term-err">FAILED TO RETRIEVE DETAILS.</div>`;
    }
}

function renderTimelineEvents(events) {
    const timeline = document.getElementById("incident-events-timeline");
    timeline.innerHTML = "";
    
    if (!events || events.length === 0) {
        timeline.innerHTML = `<div class="loading-placeholder">NO TIMELINE LOGGED</div>`;
        return;
    }

    // Sort chronologically
    const sorted = [...events].sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp));

    sorted.forEach(ev => {
        const evTime = new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const item = document.createElement("div");
        item.className = `timeline-event event-${ev.event_type}`;
        item.innerHTML = `
            <span class="timeline-dot"></span>
            <div class="timeline-event-header">
                <span class="timeline-event-time">${evTime}</span>
                <span class="timeline-event-svc">${ev.service_name.toUpperCase()}</span>
                <span class="badge badge-${ev.level.toLowerCase()}">${ev.level}</span>
            </div>
            <div class="timeline-event-msg">${ev.message}</div>
        `;
        timeline.appendChild(item);
    });
}

function renderIncidentLogsDump(evidence) {
    const term = document.getElementById("incident-logs-dump");
    term.innerHTML = "";
    
    if (!evidence || evidence.length === 0) {
        term.innerHTML = `<div class="term-line term-info">> No log evidence registered.</div>`;
        return;
    }

    evidence.forEach(ev => {
        const line = document.createElement("div");
        line.className = "term-line";
        
        let cls = "term-info";
        if (ev.level === "CRITICAL") cls = "term-err";
        else if (ev.level === "ERROR") cls = "term-err";
        else if (ev.level === "WARNING") cls = "term-warning";

        const shortTime = ev.timestamp ? ev.timestamp.substring(11, 19) : "";
        line.innerHTML = `
            <span style="color: var(--color-text-mute)">[${shortTime}]</span> 
            <span style="color: #f43f5e">[${ev.service_name}]</span> 
            <span class="${cls}">[${ev.level}]</span> 
            <span>${ev.message}</span>
        `;
        term.appendChild(line);
    });
}

// Update status of incident
async function updateStatus(incidentId, newStatus) {
    try {
        const res = await fetch(`${API_BASE}/api/incidents/${incidentId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (res.ok) {
            // Rerun loader and keep state
            await refreshData();
            await loadIncidents();
            await selectIncident(incidentId);
        } else {
            alert("Failed to update status on server.");
        }
    } catch (err) {
        alert("Server communication error.");
    }
}

// --- SERVICES HEALTH TAB LOGIC ---
async function loadServices() {
    const tableBody = document.getElementById("services-table-body");
    tableBody.innerHTML = `<tr><td colspan="6" class="loading-placeholder">GATHERING HEALTH SIGNALS...</td></tr>`;

    try {
        const res = await fetch(`${API_BASE}/api/services`);
        if (!res.ok) throw new Error();
        const services = await res.json();

        tableBody.innerHTML = "";
        if (services.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" class="loading-placeholder">NO REGISTERED MICROSERVICES FOUND</td></tr>`;
            return;
        }

        services.forEach(svc => {
            const tr = document.createElement("tr");
            
            let statusClass = "status-ok";
            if (svc.status === "CRITICAL") statusClass = "status-critical";
            else if (svc.status === "DEGRADED") statusClass = "status-degraded";

            const lastUpdated = new Date(svc.updated_at).toLocaleString();

            tr.innerHTML = `
                <td style="font-weight: bold; color: #fff;">${svc.name}</td>
                <td>${svc.type.toUpperCase()}</td>
                <td>
                    <span class="status-indicator ${statusClass}">${svc.status}</span>
                </td>
                <td style="color: ${svc.error_rate > 5.0 ? 'var(--color-error)' : (svc.error_rate > 1.0 ? 'var(--color-warning)' : 'var(--color-text-main)')}">
                    ${svc.error_rate}%
                </td>
                <td>${svc.anomaly_count}</td>
                <td style="color: var(--color-text-mute); font-size: 10px;">${lastUpdated}</td>
            `;
            tableBody.appendChild(tr);
        });
    } catch (e) {
        tableBody.innerHTML = `<tr><td colspan="6" class="loading-placeholder term-err">FAILED TO DECRYPT SYSTEM SIGNAL.</td></tr>`;
    }
}

// --- UPLOAD LOG INGESTION LOGIC ---
function setupUploadHandlers() {
    const dropZone = document.getElementById("log-drop-zone");
    
    // Prevent browser defaults
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    // Toggle dragover highlight
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    // Handle dropped files
    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            processUpload(files[0]);
        }
    });

    // Handle clicked browse
    dropZone.addEventListener('click', () => {
        document.getElementById("log-file-input").click();
    });
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        processUpload(files[0]);
    }
}

function processUpload(file) {
    // Validate client-side size limit
    if (file.size > MAX_FILE_SIZE) {
        showTerminalLogs([`> Ingest Error: File size exceeds 10MB limit (File is ${(file.size/1024/1024).toFixed(1)}MB). Ingest terminated.`], true);
        return;
    }

    const progressArea = document.getElementById("upload-progress-area");
    const progressBar = document.getElementById("upload-progress-bar");
    const percentLabel = document.getElementById("upload-percent");
    const filenameLabel = document.getElementById("upload-filename");
    const statusText = document.getElementById("upload-status-text");

    filenameLabel.textContent = file.name;
    progressArea.style.display = "block";
    progressBar.style.width = "0%";
    percentLabel.textContent = "0%";
    statusText.textContent = "TRANSMITTING FILE DATA STREAM...";
    
    // Hide previous output
    document.getElementById("analysis-log-container").style.display = "none";

    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    // Monitor progress
    xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100);
            progressBar.style.width = `${percentComplete}%`;
            percentLabel.textContent = `${percentComplete}%`;
        }
    }, false);

    xhr.onreadystatechange = () => {
        if (xhr.readyState === 4) {
            progressArea.style.display = "none";
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                handleIngestionSuccess(response);
            } else {
                let errorMsg = "INTERNAL SERVER PIPELINE CRASH";
                try {
                    const errorObj = JSON.parse(xhr.responseText);
                    errorMsg = errorObj.detail || errorMsg;
                } catch(e) {}
                handleIngestionFailure(errorMsg);
            }
        }
    };

    xhr.open("POST", `${API_BASE}/api/logs/upload`, true);
    xhr.send(formData);
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

function handleIngestionSuccess(data) {
    const logs = [
        `[INFO] Ingestion Channel: Connected successfully.`,
        `[INFO] File Received: ${data.file_name} (${(data.file_size/1024).toFixed(1)} KB)`,
        `[SUCCESS] Parse pipeline completed: ${data.logs_processed} log events mapped in PostgreSQL.`,
        `[INFO] Anomaly detection analyzer trigger execution...`,
        `[INFO] Detected anomalies: ${data.anomalies_detected} time-window spikes.`,
        `[INFO] Root cause scoring evaluator complete.`,
        `[SUCCESS] Incident registry updated: Created ${data.incidents_created} active incident alerts.`,
        `[SUCCESS] Service Health status metrics re-evaluated.`,
        `> TELEMETRY RE-ALIGNED. Pipeline active.`
    ];
    showTerminalLogs(logs, false);
    
    // Refresh dashboard stats
    refreshData();
}

function handleIngestionFailure(errorMsg) {
    const logs = [
        `[FATAL] Ingestion Channel: Upload aborted.`,
        `[ERROR] Server execution failed: "${errorMsg}"`,
        `> PIPELINE COLLAPSED.`
    ];
    showTerminalLogs(logs, true);
}

function showTerminalLogs(logLines, isError) {
    const container = document.getElementById("analysis-log-container");
    const output = document.getElementById("terminal-log-output");
    
    container.style.display = "block";
    output.innerHTML = "";

    // Sequential line insertion (simulates scrolling logs)
    let idx = 0;
    function printNextLine() {
        if (idx < logLines.length) {
            const line = logLines[idx];
            const div = document.createElement("div");
            div.className = "term-line";
            
            if (line.startsWith("[FATAL]") || line.startsWith("[ERROR]") || line.includes("Ingest Error")) {
                div.className = "term-line term-err";
            } else if (line.startsWith("[SUCCESS]")) {
                div.className = "term-line term-success";
            } else if (line.startsWith("[INFO]")) {
                div.className = "term-line term-info";
            } else {
                div.style.color = "var(--color-accent)";
            }
            
            div.textContent = line;
            output.appendChild(div);
            output.scrollTop = output.scrollHeight;
            
            idx++;
            setTimeout(printNextLine, 150);
        }
    }
    
    printNextLine();
}

// Format relative time helper
function formatRelativeTime(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.round(diffMs / 1000);
    const diffMin = Math.round(diffSec / 60);

    if (diffSec < 60) return "JUST NOW";
    if (diffMin < 60) return `${diffMin}m AGO`;
    
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
