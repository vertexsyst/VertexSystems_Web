console.log("🚀 APP.JS LOADED FRESH AT:", new Date().toLocaleTimeString());

// ==========================================
// GLOBAL CONFIG & DATASETS
// ==========================================
const SYS_TOOLS = [
    { name: "Active Directory Users & Computers", cmd: "dsa.msc", category: "Identity", desc: "Manage domain users, groups, and OU structures." },
    { name: "DNS Manager", cmd: "dnsmgmt.msc", category: "Networking", desc: "Manage forward/reverse lookups and DNS forwarders." },
    { name: "Hyper-V Manager", cmd: "virtmgmt.msc", category: "Virtualization", desc: "Control panel for lab virtual machines and vSwitches." },
    { name: "Group Policy Management", cmd: "gpmc.msc", category: "Security", desc: "Deploy domain-wide GPOs and security policies." },
    { name: "DHCP Manager", cmd: "dhcpmgmt.msc", category: "Networking", desc: "Manage IP address pools, scopes, and leases." },
    { name: "Computer Management", cmd: "compmgmt.msc", category: "System", desc: "Access Task Scheduler, Event Viewer, and Disk Management." },
    { name: "Event Viewer", cmd: "eventvwr.msc", category: "Diagnostics", desc: "Review security audits, system logs, and application warnings." }
];


window.loadDirectoryDirectory = loadDirectoryDirectory;

// ==========================================
// MASTER-DETAIL WORKSTATION LOADER
// ==========================================
async function loadClientNexusByName(clientId, clientName) {
    console.log("Loading Nexus for:", clientName, "(ID:", clientId + ")");

    const titleEl = document.getElementById('activeClientTitle');
    if (titleEl) titleEl.innerText = clientName + ` (ID: ${clientId})`;

    const container = document.getElementById('relationalTicketsContainer');
    if (container) {
        container.innerHTML = '<div style="color: #38bdf8;">// Synchronizing records for ' + clientName + '...</div>';
    }

    try {
        // 1. Fetch the single nexus workspace view (existing)
        const response = await fetch(`/api/v1/nexus/client/${encodeURIComponent(clientName)}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const data = await response.json();

        if (typeof renderVerticalRelationalWorkspace === 'function') {
            renderVerticalRelationalWorkspace(data);
        } else if (container) {
            container.innerHTML = '<pre style="color: #f8fafc; font-size: 11px;">' + JSON.stringify(data, null, 2) + '</pre>';
        }

        // 2. 🔥 ADD THIS: Simultaneously fetch and render the full historical ticket array!
        loadClientTickets(clientId, clientName);

    } catch (err) {
        console.error('Nexus error:', err);
        if (container) {
            container.innerHTML = `<div style="color: #ef4444;">[!] Error: ${err.message}</div>`;
        }
    }
}

async function loadDirectoryDirectory() {
    const container = document.getElementById('directory-drawer-container') || document.getElementById('directory-Drawer-container');
    if (container) {
        container.innerHTML = '<div style="color: #38bdf8; font-family: monospace; font-size: 12px;">🔄 Polling Microsoft Graph directory telemetry...</div>';
    }

    try {
        const response = await fetch('/api/v1/directory/sync');
        const data = await response.json();

        if (response.ok && data.status === 'success') {
            renderDirectoryCards(data.value || []);
            if (container && (!data.value || data.value.length === 0)) {
                container.innerHTML = '<div style="color: #f59e0b; font-family: monospace; font-size: 12px;">[!] Connected to Microsoft Graph, but 0 directory users were returned.</div>';
            }
        } else {
            const errMsg = typeof data.message === 'object' ? JSON.stringify(data.message) : (data.message || 'Unknown error');
            if (container) {
                container.innerHTML = `<div style="color: #ef4444; font-family: monospace; font-size: 12px;">[!] Graph Sync Error: ${errMsg}</div>`;
            }
        }
    } catch (err) {
        if (container) {
            container.innerHTML = `<div style="color: #ef4444; font-family: monospace; font-size: 12px;">[!] Network Error: ${err.message}</div>`;
        }
    }
}

async function syncDirectoryRecords() {
    const wrapper = document.getElementById('directory-table-wrapper');
    wrapper.innerHTML = `<p class="loading-text">Polling Microsoft Graph directory telemetry...</p>`;

    try {
        const response = await fetch('/api/v1/directory/sync'); // or your relative endpoint path
        const result = await response.json();

        // Assuming your backend returns an array of user objects under result.value or result.users
        const records = result.value || result.users || [];

        if (records.length === 0) {
            wrapper.innerHTML = `<p class="info-text">Successfully loaded 0 directory records.</p>`;
            return;
        }

        // Build a clean, styled HTML table
        let html = `
            <table class="nexus-data-table">
                <thead>
                    <tr>
                        <th>Display Name</th>
                        <th>User Principal Name (UPN)</th>
                        <th>Mail</th>
                        <th>Job Title</th>
                        <th>ID</th>
                    </tr>
                </thead>
                <tbody>
        `;

        records.forEach(user => {
            html += `
                <tr>
                    <td><strong>${user.displayName || 'N/A'}</strong></td>
                    <td>${user.userPrincipalName || 'N/A'}</td>
                    <td>${user.mail || user.userPrincipalName || 'N/A'}</td>
                    <td>${user.jobTitle || 'N/A'}</td>
                    <td><code>${user.id || 'N/A'}</code></td>
                </tr>
            `;
        });

        html += `
                </tbody>
            </table>
        `;

        wrapper.innerHTML = html;
        console.log(`Successfully loaded ${result.value ? result.value.length : 0} directory records.`);

    } catch (error) {
        console.error("Directory sync failed:", error);
        wrapper.innerHTML = `<p class="error-text">❌ Directory sync failed: ${error.message}</p>`;
    }
}

/**
 * Synchronizes and loads Microsoft Entra ID telemetry into the Master-Detail Workstation UI
 */
async function syncAndLoadDirectory() {
    const wrapper = document.getElementById('directory-table-wrapper');
    if (wrapper) {
        wrapper.innerHTML = `<p class="loading-text">Polling Microsoft Graph directory telemetry...</p>`;
    }

    try {
        const response = await fetch('/api/v1/directory/sync', {
            method: 'POST', // or GET depending on your Flask route configuration
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            console.log("Successfully loaded directory records:", result.value);

            // Render the fetched records into your workstation UI
            renderDirectoryUI(result.value);
        } else {
            console.error("Server sync error:", result.message);
            if (wrapper) {
                wrapper.innerHTML = `<p class="error-text">Sync Failed: ${result.message}</p>`;
            }
        }
    } catch (error) {
        console.error("Network or parsing exception:", error);
        if (wrapper) {
            wrapper.innerHTML = `<p class="error-text">Network Error: Could not reach Flask backend.</p>`;
        }
    }
}

/**
 * Helper to dynamically inject records into your master-detail view
 */
function renderDirectoryUI(users) {
    // Example rendering logic for your sidebar / table wrapper
    // You can map through 'users' (displayName, userPrincipalName, jobTitle, etc.)
    console.log(`Rendering ${users.length} records into the workstation interface.`);
}

function renderDirectoryCards(records) {
    const container = document.getElementById('directory-drawer-container') || document.getElementById('directory-Drawer-container');
    if (!container) return;

    container.innerHTML = ''; // Clear previous view

    // Fallback protection if records is undefined/null
    const list = records || [];

    list.forEach((record, index) => {
        const card = document.createElement('div');
        card.className = 'directory-card';
        card.style = "background: #0b0f19; border: 1px solid #334155; padding: 12px; border-radius: 6px; margin-bottom: 8px; font-family: monospace;";

        // Map fields safely from your Flask response keys
        const displayName = record.displayName || record.name || 'Unknown User';
        const mail = record.mail || record.email || 'No email';
        const jobTitle = record.jobTitle || record.title || 'General Staff';

        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="color: #f8fafc; font-weight: bold; font-size: 13px;">👤 ${displayName}</span>
                <span style="background: #38bdf8; color: #0f172a; font-size: 10px; padding: 2px 6px; border-radius: 3px; font-weight: bold;">Entra ID</span>
            </div>
            <div style="font-size: 11px; color: #94a3b8; display: grid; gap: 3px;">
                <div>📧 Email: <span style="color: #f8fafc;">${mail}</span></div>
                <div>💼 Title: <span style="color: #f8fafc;">${jobTitle}</span></div>
            </div>
        `;
        container.appendChild(card);
    });
}

function loadClientTickets(userId, clientName) {
    console.log(`Fetching tickets for ${clientName} (ID: ${userId})...`);

    fetch(`/api/v1/clients/${userId}/tickets`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log(`Loaded ${data.tickets.length} tickets for ${clientName}`);
                // Render your tickets into the detail view panel here
                renderClientTickets(data.tickets);
            } else {
                console.error("Failed to load client tickets:", data.message);
            }
        })
        .catch(error => console.error("Network error fetching client tickets:", error));
}

function renderClientTickets(tickets) {
    // Target the exact container your search script is looking for!
    const container = document.getElementById('ticketContainer') || document.querySelector('.workspace-detail-panel');
    if (!container) return;

    container.innerHTML = ''; // Clear previous view

    if (!tickets || tickets.length === 0) {
        container.innerHTML = `
            <div class="ticket-card" style="background: #0b0f19; border: 1px solid #334155; padding: 16px; border-radius: 6px; font-family: monospace; color: #94a3b8; text-align: center;">
                [ ℹ️ NO HISTORICAL TICKETS FOUND FOR THIS CLIENT ]
            </div>
        `;
        return;
    }

    // Loop through every single ticket in the array and give each one the '.ticket-card' class
    tickets.forEach((ticket, index) => {
        const card = document.createElement('div');
        card.className = 'ticket-card'; // Matches your search query selector!
        card.style = "background: #0b0f19; border: 1px solid #334155; padding: 14px; border-radius: 6px; margin-bottom: 12px; font-family: monospace;";

        const priorityColor = ticket.priority === 'HIGH' ? '#f43f5e' : '#38bdf8';
        const statusColor = ticket.status === 'NEW' ? '#10b981' : '#f59e0b';
        const labelText = index === 0 ? '★ LATEST TICKET' : `HISTORICAL TICKET #${ticket.id}`;

        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="color: #f8fafc; font-weight: bold; font-size: 13px;">[ ${labelText} ] ${ticket.title || 'Security Incident'}</span>
                <span style="background: ${statusColor}; color: #0f172a; font-size: 10px; padding: 2px 6px; border-radius: 3px; font-weight: bold;">Status: ${ticket.status}</span>
            </div>
            <div style="display: flex; gap: 15px; font-size: 11px; color: #94a3b8; margin-bottom: 10px;">
                <div>Priority: <span style="color: ${priorityColor}; font-weight: bold;">${ticket.priority}</span></div>
                <div>Timestamp: <span style="color: #f8fafc;">${ticket.timestamp}</span></div>
            </div>
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">📝 WORK DONE / ENGINEERING ACTIONS:</div>
            <div style="background: #1e293b; color: #f8fafc; padding: 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; white-space: pre-wrap;">${ticket.work_done || 'No actions logged yet.'}</div>
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">💡 TECHNICAL RECOMMENDATIONS:</div>
            <div style="background: #1e293b; color: #f8fafc; padding: 8px; border-radius: 4px; font-size: 12px; white-space: pre-wrap;">${ticket.recommendations || 'No recommendations logged yet.'}</div>
        `;
        container.appendChild(card);
    });
}


// ==========================================
// IMMEDIATE ROBUST EVENT DELEGATION
// ==========================================
if (!window._nexusDelegationInitialized) {
    window._nexusDelegationInitialized = true;

    document.addEventListener('click', (e) => {
        // 1. Check for client/entity nexus buttons
        const nexusBtn = e.target.closest('.client-nexus-btn');
        if (nexusBtn) {
            const id = nexusBtn.getAttribute('data-id') || 1;
            const name = nexusBtn.getAttribute('data-name') || nexusBtn.textContent.trim();

            console.log("🟢 Nexus Button Clicked:", name, "| ID:", id);
            if (typeof loadClientNexusByName === 'function') {
                loadClientNexusByName(id, name);
            }
            return;
        }

        // 2. Check for dynamic ticket cards
        const ticketCard = e.target.closest('.ticket-card');
        if (ticketCard) {
            const titleEl = ticketCard.querySelector('.ticket-title') || ticketCard.querySelector('h4');
            const deviceName = titleEl ? titleEl.textContent.trim() : "Infrastructure Device";
            const ticketId = ticketCard.getAttribute('data-id') || 1;

            console.log("🟢 Ticket Card Clicked - ID:", ticketId, "| Device:", deviceName);
            if (typeof loadClientNexusByName === 'function') {
                loadClientNexusByName(ticketId, deviceName);
            }
            return;
        }
    }, true); // Capture phase active to intercept everything instantly

    console.log("✅ Immediate Nexus Click Delegation Active");
}

// ==========================================
// MULTI-TICKET HISTORY LOADER & RENDERER
// ==========================================

window.loadClientTickets = async function (clientId, clientName) {
    console.log(`Fetching historical tickets for ${clientName}...`);

    try {
        const response = await fetch(`/api/v1/clients/${clientId}/tickets`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const data = await response.json();

        if (data.status === 'success') {
            console.log(`Loaded ${data.tickets.length} tickets for ${clientName}`);
            window.renderClientTickets(data.tickets);
        } else {
            console.error("Failed to load client tickets:", data.message);
        }
    } catch (error) {
        console.error("Network error fetching client tickets:", error);
    }
};

window.renderClientTickets = function (tickets) {
    // Target your main ticket container
    const container = document.getElementById('ticketContainer') || document.getElementById('relationalTicketsContainer');
    if (!container) return;

    container.innerHTML = ''; // Clear previous view

    if (!tickets || tickets.length === 0) {
        container.innerHTML = `
            <div class="ticket-card" style="background: #0b0f19; border: 1px solid #334155; padding: 16px; border-radius: 6px; font-family: monospace; color: #94a3b8; text-align: center;">
                [ ℹ️ NO HISTORICAL TICKETS FOUND FOR THIS CLIENT ]
            </div>
        `;
        return;
    }

    // Loop through every single record in the historical array
    tickets.forEach((ticket, index) => {
        const card = document.createElement('div');
        card.className = 'ticket-card';
        card.style = "background: #0b0f19; border: 1px solid #334155; padding: 14px; border-radius: 6px; margin-bottom: 12px; font-family: monospace;";

        const priorityColor = ticket.priority === 'HIGH' ? '#f43f5e' : '#38bdf8';
        const statusColor = ticket.status === 'NEW' ? '#10b981' : '#f59e0b';
        const labelText = index === 0 ? '★ LATEST TICKET' : `HISTORICAL TICKET #${ticket.id}`;

        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="color: #f8fafc; font-weight: bold; font-size: 13px;">[ ${labelText} ] ${ticket.title || 'Security Incident'}</span>
                <span style="background: ${statusColor}; color: #0f172a; font-size: 10px; padding: 2px 6px; border-radius: 3px; font-weight: bold;">Status: ${ticket.status}</span>
            </div>
            <div style="display: flex; gap: 15px; font-size: 11px; color: #94a3b8; margin-bottom: 10px;">
                <div>Priority: <span style="color: ${priorityColor}; font-weight: bold;">${ticket.priority}</span></div>
                <div>Timestamp: <span style="color: #f8fafc;">${ticket.timestamp}</span></div>
            </div>
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">📝 WORK DONE / ENGINEERING ACTIONS:</div>
            <div style="background: #1e293b; color: #f8fafc; padding: 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; white-space: pre-wrap;">${ticket.work_done || 'No actions logged yet.'}</div>
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">💡 TECHNICAL RECOMMENDATIONS:</div>
            <div style="background: #1e293b; color: #f8fafc; padding: 8px; border-radius: 4px; font-size: 12px; white-space: pre-wrap;">${ticket.recommendations || 'No recommendations logged yet.'}</div>
        `;
        container.appendChild(card);
    });
};


// ==========================================
// TELEMETRY & DASHBOARD METRICS
// ==========================================

function pollTelemetry() {
    fetch('/api/v1/telemetry')
        .then(response => response.json())
        .then(data => {
            if (data.status) {
                const statusEl = document.getElementById('tel-status');
                if (statusEl) {
                    statusEl.textContent = `[ ${data.status} ]`;
                    statusEl.style.color = data.status === 'NOMINAL' ? '#10b981' : '#ef4444';
                    statusEl.style.background = data.status === 'NOMINAL' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)';
                }
            }
            if (data.cpu) { const cpuEl = document.getElementById('tel-cpu'); if (cpuEl) cpuEl.textContent = data.cpu; }
            if (data.memory) { const memEl = document.getElementById('tel-mem'); if (memEl) memEl.textContent = data.memory; }
        })
        .catch(err => console.error('Telemetry polling error:', err));
}

function updateStrategicDashboard() {
    const activeLaptopsInAD = 65;
    const physicalServerHosts = 6;
    const provisionedVMs = 24;

    if (document.getElementById('phys-desktop-box')) document.getElementById('phys-desktop-box').innerText = 5;
    if (document.getElementById('phys-desktop-avail')) document.getElementById('phys-desktop-avail').innerText = 16;
    if (document.getElementById('phys-desktop-repair')) document.getElementById('phys-desktop-repair').innerText = 2;
    if (document.getElementById('phys-desktop-action')) document.getElementById('phys-desktop-action').innerText = 42;
    if (document.getElementById('virt-desktop-vms')) document.getElementById('virt-desktop-vms').innerText = 15;

    if (document.getElementById('phys-laptop-box')) document.getElementById('phys-laptop-box').innerText = 8;
    if (document.getElementById('phys-laptop-avail')) document.getElementById('phys-laptop-avail').innerText = 24;
    if (document.getElementById('phys-laptop-repair')) document.getElementById('phys-laptop-repair').innerText = 4;
    if (document.getElementById('phys-laptop-action')) document.getElementById('phys-laptop-action').innerText = activeLaptopsInAD;
    if (document.getElementById('virt-laptop-vms')) document.getElementById('virt-laptop-vms').innerText = 72;

    if (document.getElementById('phys-switch-box')) document.getElementById('phys-switch-box').innerText = 1;
    if (document.getElementById('phys-switch-avail')) document.getElementById('phys-switch-avail').innerText = 2;
    if (document.getElementById('phys-switch-repair')) document.getElementById('phys-switch-repair').innerText = 0;
    if (document.getElementById('phys-switch-action')) document.getElementById('phys-switch-action').innerText = 8;
    if (document.getElementById('virt-switch-vms')) document.getElementById('virt-switch-vms').innerText = 12;

    if (document.getElementById('phys-server-box')) document.getElementById('phys-server-box').innerText = 2;
    if (document.getElementById('phys-server-avail')) document.getElementById('phys-server-avail').innerText = 4;
    if (document.getElementById('phys-server-repair')) document.getElementById('phys-server-repair').innerText = 1;
    if (document.getElementById('phys-server-action')) document.getElementById('phys-server-action').innerText = physicalServerHosts;
    if (document.getElementById('virt-server-vms')) document.getElementById('virt-server-vms').innerText = provisionedVMs;

    if (document.getElementById('health-index')) document.getElementById('health-index').innerText = "99.4%";
    if (document.getElementById('threat-tracker')) document.getElementById('threat-tracker').innerText = "1,420";
    if (document.getElementById('financial-value')) document.getElementById('financial-value').innerText = "$42,600";
}

async function loadDashboardTickets() {
    const displayContainer = document.getElementById("ticketContainer");
    if (!displayContainer) return;

    try {
        const response = await fetch('/api/dashboard/tickets');
        if (!response.ok) throw new Error(`HTTP network error: ${response.status}`);
        const tickets = await response.json();

        if (!tickets || tickets.length === 0) {
            displayContainer.innerHTML = `<div class="sql-loader"><span class="loader-text" style="color: #ef4444;">No active security alerts logged.</span></div>`;
            return;
        }

        displayContainer.innerHTML = "";
        tickets.forEach(ticket => {
            const card = document.createElement("div");
            card.className = "ticket-card";
            card.setAttribute("data-tenant", ticket.tenant || "ALL");
            card.setAttribute("data-id", ticket.id || 1);
            card.innerHTML = `
                <div class="ticket-header">
                    <span class="ticket-serial">#${ticket.id || 'TK-000'}</span>
                    <span class="ticket-status-badge ${ticket.status === 'Resolved' ? 'status-active' : 'status-pending'}">● ${ticket.status || 'Active'}</span>
                </div>
                <h4 class="ticket-title">${ticket.deviceName || 'Infrastructure Device'}</h4>
                <p class="ticket-details">${ticket.alertType || 'No additional log details provided.'}</p>
                <div class="ticket-footer"><span>Domain: ${ticket.tenant || 'Global'}</span><span>SQL Persisted</span></div>
            `;
            displayContainer.appendChild(card);
        });
    } catch (error) {
        console.error("❌ Dashboard Sync Failure:", error);
    }
}

function initSysTools() {
    const listContainer = document.getElementById('systools-list');
    if (!listContainer) return;

    listContainer.innerHTML = SYS_TOOLS.map(t => `
        <div class="systool-card">
            <div class="systool-info">
                <h4>${t.name}</h4>
                <p>${t.desc}</p>
                <span class="systool-cmd">${t.cmd}</span>
            </div>
            <div class="systool-actions" style="display: flex; flex-direction: column; gap: 8px; align-items: flex-end;">
                <button class="copy-btn" onclick="launchTool('${t.cmd}')" style="background: rgba(0,255,204,0.15); border: 1px solid #00ffcc; color: #00ffcc; cursor: pointer; padding: 4px 10px; width: 100%;">LAUNCH</button>
                <button class="copy-btn" onclick="copyToClipboard('${t.cmd}', this)" style="padding: 4px 10px; width: 100%;">COPY</button>
            </div>
        </div>
    `).join('');
}

function copyToClipboard(text, btnElement) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = btnElement.textContent;
        btnElement.textContent = 'COPIED!';
        setTimeout(() => { btnElement.textContent = originalText; }, 1500);
    });
}

async function launchTool(cmd) {
    try {
        const response = await fetch(`/api/launch/${cmd}`, { method: 'POST' });
        const result = await response.json();
        console.log(`[SYS LAUNCH]`, result);
    } catch (err) {
        console.error('[SYS LAUNCH ERROR]', err);
    }
}

// ==========================================
// UNIFIED INITIALIZATION & CASE-SAFE ALIASES
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    // 1. Start live telemetry polling immediately
    if (typeof pollTelemetry === 'function') {
        pollTelemetry();
        setInterval(pollTelemetry, 5000);
    }

    // 2. Load SQL Server tickets into #ticketContainer
    if (typeof loadDashboardTickets === 'function') {
        loadDashboardTickets();
    }
});

// Ensure both uppercase and lowercase client buttons trigger Nexus
document.addEventListener('click', (e) => {
    const nexusBtn = e.target.closest('.client-nexus-Btn, .client-nexus-btn');
    if (nexusBtn) {
        const id = nexusBtn.getAttribute('data-id') || 1;
        const name = nexusBtn.getAttribute('data-name') || nexusBtn.textContent.replace(/\[.*?\]/g, '').trim();
        if (typeof loadClientNexusByName === 'function') {
            loadClientNexusByName(id, name);
        }
    }
});

window.openSysToolsDrawer = () => document.getElementById('systools-drawer')?.classList.add('open');
window.closeSysToolsDrawer = () => document.getElementById('systools-drawer')?.classList.remove('open');
window.launchTool = launchTool;
window.copyToClipboard = copyToClipboard;
window.loadDirectoryDirectory = loadDirectoryDirectory;
window.renderDirectoryCards = renderDirectoryCards;