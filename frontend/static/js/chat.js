// MedShield v2 - Chat Interface with Pipeline Tracking & Session Management

let sessionId = localStorage.getItem('medshield_session_id') || null;
let messageCount = 0;
let totalPiiRemoved = 0;
let totalCloudSafe = 0;

// ====== Initialisation ======
document.addEventListener('DOMContentLoaded', function () {
    const chatForm = document.getElementById('chatForm');
    const messageInput = document.getElementById('messageInput');

    // Auto-resize
    messageInput.addEventListener('input', autoResize);

    // Submit
    chatForm.addEventListener('submit', function (e) {
        e.preventDefault();
        handleSendMessage();
    });

    // Enter to send
    messageInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });

    // Panel toggles
    document.getElementById('leftToggle').addEventListener('click', function () {
        document.getElementById('leftPanel').classList.toggle('collapsed');
        document.getElementById('leftPanel').classList.toggle('open');
    });
    document.getElementById('rightToggle').addEventListener('click', function () {
        const rp = document.getElementById('rightPanel');
        rp.classList.toggle('collapsed');
        rp.classList.toggle('open');
    });
    document.getElementById('closeRightPanel').addEventListener('click', function () {
        const rp = document.getElementById('rightPanel');
        rp.classList.add('collapsed');
        rp.classList.remove('open');
    });

    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function (c) { c.classList.remove('active'); });
            btn.classList.add('active');
            document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
        });
    });

    // New session button
    document.getElementById('newSessionBtn').addEventListener('click', function () {
        sessionId = null;
        localStorage.removeItem('medshield_session_id');
        messageCount = 0;
        totalPiiRemoved = 0;
        totalCloudSafe = 0;
        updateSessionDisplay();
        updatePrivacyStats();

        // Clear messages except welcome
        const chatMessages = document.getElementById('chatMessages');
        const msgs = chatMessages.querySelectorAll('.message');
        msgs.forEach(function (m, i) { if (i > 0) m.remove(); });

        // Reset pipeline
        resetPipelinePanel();
    });

    // Health polling
    pollHealth();
    setInterval(pollHealth, 15000);

    updateSessionDisplay();
});

// ====== Health Polling ======
async function pollHealth() {
    const container = document.getElementById('healthItems');
    try {
        const res = await fetch('/health');
        const data = await res.json();
        const components = data.components || {};

        let html = '';
        const names = {
            identity_vault: 'Identity Vault',
            semantic_store: 'Semantic Store',
            gatekeeper_agent: 'Gatekeeper',
            coordinator_agent: 'Coordinator',
            worker_agent: 'Worker Agent'
        };

        for (const [key, status] of Object.entries(components)) {
            if (key === 'semantic_store_vectors') continue;
            const label = names[key] || key;
            const dotClass = status === 'operational' ? 'ok' : 'down';
            html += '<div class="health-row"><span class="health-dot ' + dotClass + '"></span><span class="health-label">' + escapeHtml(label) + '</span></div>';
        }
        container.innerHTML = html;
    } catch (_err) {
        container.innerHTML = '<div class="health-row"><span class="health-dot down"></span><span class="health-label">Backend offline</span></div>';
    }
}

// ====== Session ======
function updateSessionDisplay() {
    const el = document.getElementById('sessionIdDisplay');
    if (sessionId) {
        el.textContent = sessionId.substring(0, 8) + '...';
    } else {
        el.textContent = 'No active session';
    }
}

// ====== Send Message ======
async function handleSendMessage() {
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const message = messageInput.value.trim();
    if (!message) return;

    addUserMessage(message);
    messageInput.value = '';
    messageInput.style.height = 'auto';
    messageInput.disabled = true;
    sendButton.disabled = true;
    showTypingIndicator();

    // Show processing pipeline in right panel
    showPipelineProcessing();

    try {
        const body = { message: message };
        if (sessionId) body.session_id = sessionId;

        const response = await fetch('/api/chat/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const data = await response.json();
        hideTypingIndicator();

        // Track session
        if (data.result && data.result.session_id) {
            sessionId = data.result.session_id;
            localStorage.setItem('medshield_session_id', sessionId);
            updateSessionDisplay();
        }

        if (response.ok && data.success !== false) {
            messageCount++;
            addBotMessage(data);
            updatePipelineComplete(data);
            updatePrivacyPanel(data);
            updateMcpPanel();
        } else {
            const errMsg = data.detail || data.message || 'An error occurred';
            addBotMessage({ message: errMsg, intent: 'error', workflow_steps: [], result: {} });
            updatePipelineError(errMsg);
        }
    } catch (error) {
        hideTypingIndicator();
        addBotMessage({
            message: 'Connection error: could not reach the backend. Is the server running?',
            intent: 'error', workflow_steps: [], result: {}
        });
        updatePipelineError('Connection failed');
    } finally {
        messageInput.disabled = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

// ====== Chat Messages ======
function addUserMessage(text) {
    const chatMessages = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'message user';
    div.innerHTML = '<div class="bubble"><p>' + escapeHtml(text) + '</p></div>';
    chatMessages.appendChild(div);
    scrollToBottom();
}

function addBotMessage(data) {
    const chatMessages = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'message assistant';

    let bubbleContent = '<p>' + escapeHtml(data.message || '') + '</p>';

    // Result card
    if (data.result && data.intent) {
        bubbleContent += formatResultCard(data.intent, data.result);
    }

    div.innerHTML =
        '<div class="avatar assistant-avatar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 22C12 22 20 18 20 12V5L12 2L4 5V12C4 18 12 22 12 22Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 8V16M8 12H16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></div>' +
        '<div class="bubble">' + bubbleContent + '</div>';

    chatMessages.appendChild(div);

    const bubble = div.querySelector('.bubble');

    // Privacy report inside message
    if (data.result && data.result.privacy_details && data.result.privacy_details.transformations && data.result.privacy_details.transformations.length > 0) {
        displayPrivacyReport(data.result.privacy_details, bubble);
    }

    // Workflow steps inside message (collapsed)
    if (data.workflow_steps && data.workflow_steps.length > 0) {
        displayWorkflowSteps(data.workflow_steps, bubble);
    }

    // Disambiguation
    if (data.intent === 'disambiguation_required' && data.result && data.result.disambiguation_data) {
        displayDisambiguation(data.result.disambiguation_data, bubble);
    }

    // Confirmation
    if (data.intent === 'awaiting_confirmation') {
        displayConfirmation(bubble);
    }

    scrollToBottom();
}

function formatResultCard(intent, result) {
    if (intent === 'appointment' && result.recommended_doctor) {
        return '<div class="result-card"><h4>Appointment Details</h4>' +
            resultRow('Doctor', result.recommended_doctor || 'TBD') +
            resultRow('Specialty', result.recommended_specialty || 'General') +
            resultRow('Time', formatDateTime(result.appointment_time)) +
            resultRow('Duration', (result.consultation_duration || result.estimated_duration || 30) + ' min') +
            resultRow('Urgency', capitalizeFirst(result.urgency_level || result.urgency_assessment || 'routine')) +
            '</div>';
    }
    if (intent === 'followup' && result.followup_time) {
        return '<div class="result-card"><h4>Follow-up Details</h4>' +
            resultRow('Time', formatDateTime(result.followup_time)) +
            resultRow('Previous Visits', result.previous_visits || '0') +
            '</div>';
    }
    if (intent === 'summary' && result.summary) {
        return '<div class="result-card"><h4>Medical Summary</h4>' +
            resultRow('Total Visits', result.summary.total_visits || 0) +
            resultRow('Records', (result.summary.record_types || []).join(', ') || 'None') +
            '</div>';
    }
    return '';
}

function resultRow(label, value) {
    return '<div class="result-detail"><span class="result-label">' + escapeHtml(label) + '</span><span class="result-value">' + escapeHtml(String(value)) + '</span></div>';
}

// ====== In-bubble privacy / workflow displays ======
function displayPrivacyReport(pd, bubble) {
    const panel = document.createElement('div');
    panel.className = 'privacy-panel';
    let html = '<div class="privacy-panel-header">Privacy Protection Applied</div><div class="privacy-transforms">';

    pd.transformations.forEach(function (t) {
        html += '<div class="privacy-item">' +
            '<span class="privacy-field">' + escapeHtml(t.field) + ':</span>' +
            '<span class="privacy-transformation">' + escapeHtml(t.original) + ' &rarr; <strong>' + escapeHtml(t.transformed) + '</strong></span>' +
            '<span class="privacy-method">(' + escapeHtml(t.method) + ')</span></div>';
    });
    html += '</div>';
    panel.innerHTML = html;
    bubble.appendChild(panel);
}

function displayWorkflowSteps(steps, bubble) {
    const panel = document.createElement('div');
    panel.className = 'workflow-panel collapsed';

    let html = '<div class="workflow-header" onclick="this.parentElement.classList.toggle(\'collapsed\')"><span><span class="workflow-icon">&#9881;</span> Agent Workflow (' + steps.length + ' steps)</span><span class="workflow-toggle">&#9660;</span></div><div class="workflow-steps">';
    steps.forEach(function (step, i) {
        html += '<div class="workflow-step"><span class="step-number">' + (i + 1) + '</span> ' + escapeHtml(step) + '</div>';
    });
    html += '</div>';
    panel.innerHTML = html;
    bubble.appendChild(panel);
}

function displayDisambiguation(disambData, bubble) {
    if (!disambData || !disambData.candidates) return;
    const panel = document.createElement('div');
    panel.className = 'disambiguation-panel';

    let html = '<div class="disambig-header">Multiple Patients Found - Please Select:</div><div class="candidate-list">';
    disambData.candidates.forEach(function (c) {
        html += '<div class="candidate-card" onclick="selectPatient(\'' + escapeHtml(c.patient_uuid) + '\')">' +
            '<div class="candidate-name">' + escapeHtml(c.patient_name) + '</div>' +
            '<div class="candidate-details">UUID: ' + c.patient_uuid.substring(0, 8) + '...' +
            '<br>Age: ' + (c.age || 'N/A') + ' | Gender: ' + (c.gender || 'N/A') + '</div></div>';
    });
    html += '</div>';
    panel.innerHTML = html;
    bubble.appendChild(panel);
}

function displayConfirmation(bubble) {
    const panel = document.createElement('div');
    panel.className = 'confirmation-panel';
    panel.innerHTML =
        '<div class="confirmation-buttons">' +
        '<button class="confirm-btn" onclick="sendConfirmation(\'yes\')">Confirm</button>' +
        '<button class="cancel-btn" onclick="sendConfirmation(\'no\')">Cancel</button>' +
        '</div>';
    bubble.appendChild(panel);
}

function selectPatient(uuid) {
    document.getElementById('messageInput').value = uuid;
    handleSendMessage();
}

function sendConfirmation(response) {
    document.getElementById('messageInput').value = response;
    handleSendMessage();
}

// ====== Pipeline Panel (Right Side) ======
function showPipelineProcessing() {
    const container = document.getElementById('pipelineStatus');
    const steps = [
        { name: 'Gatekeeper Agent', detail: 'Detecting and extracting PII...' },
        { name: 'Identity Resolution', detail: 'Resolving patient identity via UUID...' },
        { name: 'MCP Bridge (Outgoing)', detail: 'Validating payload for cloud safety...' },
        { name: 'Context Agent', detail: 'RAG-based context refinement...' },
        { name: 'MCP Bridge (Incoming)', detail: 'Validating cloud response...' },
        { name: 'Execution Agent', detail: 'Processing task...' },
        { name: 'MCP Bridge (Response)', detail: 'Final privacy validation...' },
        { name: 'Re-identification', detail: 'Restoring patient identity for output...' }
    ];

    let html = '';
    steps.forEach(function (s, i) {
        html += '<div class="pipeline-step active" style="animation-delay: ' + (i * 0.1) + 's">' +
            '<div class="step-icon">&#9679;</div>' +
            '<div class="step-info"><div class="step-name">' + escapeHtml(s.name) + '</div>' +
            '<div class="step-detail">' + escapeHtml(s.detail) + '</div></div></div>';
    });
    container.innerHTML = html;

    // Activate pipeline tab
    document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
    document.querySelectorAll('.tab-content').forEach(function (c) { c.classList.remove('active'); });
    document.querySelector('[data-tab="pipeline"]').classList.add('active');
    document.getElementById('tab-pipeline').classList.add('active');
}

function updatePipelineComplete(data) {
    const container = document.getElementById('pipelineStatus');
    const steps = data.workflow_steps || [];
    if (steps.length === 0) {
        container.innerHTML = '<div class="pipeline-idle"><p>No pipeline data available for this response.</p></div>';
        return;
    }

    let html = '';
    steps.forEach(function (s, i) {
        html += '<div class="pipeline-step done" style="animation-delay: ' + (i * 0.08) + 's">' +
            '<div class="step-icon">&#10003;</div>' +
            '<div class="step-info"><div class="step-name">' + escapeHtml(s) + '</div></div></div>';
    });
    container.innerHTML = html;
}

function updatePipelineError(msg) {
    const container = document.getElementById('pipelineStatus');
    container.innerHTML = '<div class="pipeline-step error"><div class="step-icon">&#10007;</div><div class="step-info"><div class="step-name">Error</div><div class="step-detail">' + escapeHtml(msg) + '</div></div></div>';
}

function resetPipelinePanel() {
    document.getElementById('pipelineStatus').innerHTML =
        '<div class="pipeline-idle"><svg width="40" height="40" viewBox="0 0 24 24" fill="none"><path d="M12 22C12 22 20 18 20 12V5L12 2L4 5V12C4 18 12 22 12 22Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg><p>Send a message to see the agent processing pipeline here.</p></div>';
}

// ====== Privacy Panel ======
function updatePrivacyPanel(data) {
    const pd = data.result && data.result.privacy_details;
    if (!pd) return;

    if (pd.pii_removed) totalPiiRemoved += pd.pii_removed;
    if (pd.cloud_safe) totalCloudSafe++;
    updatePrivacyStats();

    // Transformations
    const container = document.getElementById('privacyTransformations');
    if (pd.transformations && pd.transformations.length > 0) {
        // Prepend new card
        const card = document.createElement('div');
        card.className = 'transform-card';

        let html = '<div class="transform-card-header">Message #' + messageCount + '</div>';
        pd.transformations.forEach(function (t) {
            html += '<div class="transform-row">' +
                '<span class="transform-original">' + escapeHtml(t.original) + '</span>' +
                '<span class="transform-arrow">&rarr;</span>' +
                '<span class="transform-result">' + escapeHtml(t.transformed) + '</span>' +
                '<span class="transform-method">' + escapeHtml(t.method) + '</span></div>';
        });
        card.innerHTML = html;

        // Remove empty state if present
        const empty = container.querySelector('.empty-state');
        if (empty) empty.remove();

        container.prepend(card);
    }
}

function updatePrivacyStats() {
    document.getElementById('privTotalOps').textContent = messageCount;
    document.getElementById('privPiiRemoved').textContent = totalPiiRemoved;
    document.getElementById('privCloudSafe').textContent = totalCloudSafe;
}

// ====== MCP Panel ======
async function updateMcpPanel() {
    try {
        const res = await fetch('/api/chat/privacy-report');
        const data = await res.json();
        if (!data.success) return;

        const container = document.getElementById('mcpStatus');
        let html = '';

        // Identity vault report
        if (data.report) {
            html += '<div class="mcp-card"><div class="mcp-card-title">Identity Vault</div>' +
                mcpRow('Total Patients', data.report.total_patients || 0) +
                mcpRow('Total Operations', data.report.total_operations || 0) +
                mcpRow('Cloud Exposed', data.report.cloud_exposed_count || 0, data.report.cloud_exposed_count > 0 ? 'warn' : 'safe') +
                mcpRow('Compliant', data.report.privacy_compliant ? 'YES' : 'NO', data.report.privacy_compliant ? 'safe' : 'warn') +
                '</div>';
        }

        // MCP bridge report
        if (data.mcp_bridge) {
            const mb = data.mcp_bridge;
            html += '<div class="mcp-card"><div class="mcp-card-title">MCP Bridge</div>' +
                mcpRow('Total Calls', mb.total_calls || 0) +
                mcpRow('Violations', mb.total_violations || 0, mb.total_violations > 0 ? 'warn' : 'safe') +
                mcpRow('Compliance Rate', mb.compliance_rate + '%', mb.compliance_rate >= 100 ? 'safe' : 'warn') +
                mcpRow('Bridge Active', mb.bridge_active ? 'YES' : 'NO', mb.bridge_active ? 'safe' : 'warn') +
                '<div class="mcp-rate-bar"><div class="mcp-rate-fill" style="width:' + mb.compliance_rate + '%"></div></div>';

            if (mb.agent_breakdown) {
                html += '<div style="margin-top:10px">';
                for (const [agent, stats] of Object.entries(mb.agent_breakdown)) {
                    html += '<div class="mcp-row"><span class="mcp-label">' + escapeHtml(agent) + '</span><span class="mcp-value ' + (stats.unsafe > 0 ? 'warn' : 'safe') + '">' + stats.safe + '/' + stats.total + ' safe</span></div>';
                }
                html += '</div>';
            }

            html += '</div>';
        }

        container.innerHTML = html || '<p class="empty-state">No compliance data available yet.</p>';
    } catch (_err) {
        // Silently ignore; panel just keeps its current content
    }
}

document.getElementById('refreshMcpBtn')?.addEventListener('click', updateMcpPanel);

function mcpRow(label, value, cls) {
    return '<div class="mcp-row"><span class="mcp-label">' + escapeHtml(label) + '</span><span class="mcp-value ' + (cls || '') + '">' + escapeHtml(String(value)) + '</span></div>';
}

// ====== Utilities ======
function showTypingIndicator() {
    document.getElementById('typingIndicator').style.display = 'block';
    scrollToBottom();
}

function hideTypingIndicator() {
    document.getElementById('typingIndicator').style.display = 'none';
}

function scrollToBottom() {
    const el = document.getElementById('chatMessages');
    requestAnimationFrame(function () {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });
}

function autoResize() {
    const el = document.getElementById('messageInput');
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function formatDateTime(iso) {
    if (!iso) return 'N/A';
    return new Date(iso).toLocaleString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function capitalizeFirst(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}
