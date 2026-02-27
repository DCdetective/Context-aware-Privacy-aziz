// MedShield Chat - Premium ChatGPT-like Interface

let chatHistory = [];
let currentSessionId = null;

document.addEventListener('DOMContentLoaded', function() {
    const chatForm = document.getElementById('chatForm');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');

    // Auto-resize textarea
    messageInput.addEventListener('input', autoResize);

    // Form submission
    chatForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        await handleSendMessage();
    });

    // Enter to send (Shift+Enter for new line)
    messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });

    // Initial animation for welcome message
    const welcomeMessage = document.querySelector('.message.assistant');
    if (welcomeMessage) {
        welcomeMessage.style.animationDelay = '0.1s';
    }
});

function autoResize() {
    const messageInput = document.getElementById('messageInput');
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
}

async function handleSendMessage() {
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const message = messageInput.value.trim();

    if (!message) return;

    // Add user message to chat
    addUserMessage(message);

    // Clear input and reset height
    messageInput.value = '';
    messageInput.style.height = 'auto';

    // Disable input while processing
    messageInput.disabled = true;
    sendButton.disabled = true;

    // Show typing indicator
    showTypingIndicator();

    try {
        // Send to API
        const payload = { message: message };
        if (currentSessionId) {
            payload.session_id = currentSessionId;
        }

        const response = await fetch('/api/chat/message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        // Track session ID from response for multi-turn conversations
        if (data.session_id) {
            currentSessionId = data.session_id;
        } else if (data.result && data.result.session_id) {
            currentSessionId = data.result.session_id;
        }

        // Hide typing indicator
        hideTypingIndicator();

        if (response.ok && data.success !== false) {
            // Add bot response
            addBotMessage(data);
        } else {
            // Handle error responses (including 400, 422, 500)
            const errorMsg = data.message || data.detail || 'Sorry, I encountered an error. Please try again.';
            addBotMessage({
                message: errorMsg,
                intent: 'error',
                result: {},
                workflow_steps: []
            });
        }

    } catch (error) {
        console.error('Error:', error);
        hideTypingIndicator();
        addBotMessage({
            message: 'Sorry, I encountered a connection error. Please try again.',
            intent: 'error'
        });
    } finally {
        // Re-enable input
        messageInput.disabled = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

function addUserMessage(text) {
    const chatMessages = document.getElementById('chatMessages');

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    messageDiv.innerHTML = `
        <div class="bubble">
            <p>${escapeHtml(text)}</p>
        </div>
    `;

    chatMessages.appendChild(messageDiv);
    scrollToBottom();

    // Add to history
    chatHistory.push({
        type: 'user',
        text: text,
        timestamp: new Date().toISOString()
    });
}

function addBotMessage(data) {
    const chatMessages = document.getElementById('chatMessages');

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';

    let bubbleContent = `<p>${escapeHtml(data.message)}</p>`;

    // Add result card based on intent
    if (data.result) {
        bubbleContent += formatResultCard(data.intent, data.result);
    }

    messageDiv.innerHTML = `
        <div class="bubble">
            ${bubbleContent}
        </div>
    `;

    chatMessages.appendChild(messageDiv);
    
    // Display privacy report if available
    if (data.result && data.result.privacy_details && data.result.privacy_details.transformations) {
        displayPrivacyReport(data.result.privacy_details, messageDiv);
    }
    
    // Display workflow steps if available
    if (data.workflow_steps && data.workflow_steps.length > 0) {
        displayWorkflowSteps(data.workflow_steps, messageDiv);
    }
    
    // Handle disambiguation
    if (data.intent === 'disambiguation_required' && data.result && data.result.disambiguation_data) {
        displayDisambiguation(data.result.disambiguation_data, messageDiv);
    }
    
    // Handle confirmation required (new patient creation)
    if (data.intent === 'confirmation_required') {
        displayConfirmationButtons(messageDiv);
    }
    
    // Handle confirmation summary (appointment booking etc.)
    if (data.intent === 'awaiting_confirmation' && data.message.toLowerCase().includes('confirm')) {
        displayConfirmationSummary(data.message, messageDiv);
    }
    
    scrollToBottom();

    // Add to history
    chatHistory.push({
        type: 'bot',
        data: data,
        timestamp: new Date().toISOString()
    });

    // Update privacy visualization with details
    if (window.updatePrivacyVisualization && data.workflow_steps) {
        // Use privacy_details from result (which comes from privacy_report)
        const privacyDetails = data.result?.privacy_details || null;
        window.updatePrivacyVisualization(data.workflow_steps, privacyDetails);
        
        // Auto-open sidebar when there are privacy transformations
        if (privacyDetails && privacyDetails.transformations && privacyDetails.transformations.length > 0) {
            const sidebar = document.getElementById('privacySidebar');
            const showBtn = document.getElementById('showPrivacyButton');
            if (sidebar && sidebar.classList.contains('collapsed')) {
                sidebar.classList.remove('collapsed');
                if (showBtn) showBtn.style.display = 'none';
            }
        }
    }
}

function formatResultCard(intent, result) {
    // Get patient name from result (coordinator always sets it now)
    const patientName = result.patient_name || 'N/A';
    
    if (intent === 'appointment') {
        return `
            <div class="result-card">
                <h4>Appointment Details</h4>
                <div class="result-detail">
                    <span class="result-label">Patient</span>
                    <span class="result-value">${escapeHtml(patientName)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Time</span>
                    <span class="result-value">${formatDateTime(result.appointment_time)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Duration</span>
                    <span class="result-value">${result.consultation_duration || 30} minutes</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Urgency</span>
                    <span class="result-value urgency-${result.urgency_level || 'routine'}">${capitalizeFirst(result.urgency_level || 'routine')}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Specialty</span>
                    <span class="result-value">${result.recommended_specialty || 'General'}</span>
                </div>
            </div>
        `;
    } else if (intent === 'followup') {
        return `
            <div class="result-card">
                <h4>Follow-up Details</h4>
                <div class="result-detail">
                    <span class="result-label">Patient</span>
                    <span class="result-value">${escapeHtml(patientName)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Time</span>
                    <span class="result-value">${formatDateTime(result.followup_time)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Previous Visits</span>
                    <span class="result-value">${result.previous_visits || 0}</span>
                </div>
            </div>
        `;
    } else if (intent === 'summary') {
        return `
            <div class="result-card">
                <h4>Medical Summary</h4>
                <div class="result-detail">
                    <span class="result-label">Patient</span>
                    <span class="result-value">${escapeHtml(patientName)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Total Visits</span>
                    <span class="result-value">${result.summary?.total_visits || 0}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Record Types</span>
                    <span class="result-value">${result.summary?.record_types?.join(', ') || 'None'}</span>
                </div>
            </div>
        `;
    } else if (intent === 'general' && result.suggestions) {
        return `
            <div class="result-card">
                <h4>Suggestions</h4>
                <ul>
                    ${result.suggestions.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    return '';
}

function showTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    indicator.style.display = 'block';
    scrollToBottom();
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    indicator.style.display = 'none';
}

function scrollToBottom() {
    const chatMessages = document.getElementById('chatMessages');
    // Use requestAnimationFrame for smoother scrolling
    requestAnimationFrame(() => {
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    });
}

function formatDateTime(isoString) {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function capitalizeFirst(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

/**
 * Display privacy transformation report
 */
function displayPrivacyReport(privacyReport, messageDiv) {
    if (!privacyReport || !privacyReport.transformations) {
        return;
    }
    
    // Create privacy panel
    const privacyPanel = document.createElement('div');
    privacyPanel.className = 'privacy-panel';
    
    const header = document.createElement('div');
    header.className = 'privacy-header';
    header.innerHTML = '<span class="privacy-icon">🔒</span> Privacy Protection Applied';
    
    const transformList = document.createElement('div');
    transformList.className = 'privacy-transforms';
    
    privacyReport.transformations.forEach(transform => {
        const item = document.createElement('div');
        item.className = 'privacy-item';
        
        const field = document.createElement('span');
        field.className = 'privacy-field';
        field.textContent = transform.field + ':';
        
        const transformation = document.createElement('span');
        transformation.className = 'privacy-transformation';
        transformation.innerHTML = `${escapeHtml(transform.original)} → <strong>${escapeHtml(transform.transformed)}</strong>`;
        
        const method = document.createElement('span');
        method.className = 'privacy-method';
        method.textContent = `(${transform.method})`;
        
        item.appendChild(field);
        item.appendChild(transformation);
        item.appendChild(method);
        transformList.appendChild(item);
    });
    
    privacyPanel.appendChild(header);
    privacyPanel.appendChild(transformList);
    
    messageDiv.querySelector('.bubble').appendChild(privacyPanel);
}

/**
 * Display workflow steps
 */
function displayWorkflowSteps(steps, messageDiv) {
    if (!steps || steps.length === 0) {
        return;
    }
    
    const workflowPanel = document.createElement('div');
    workflowPanel.className = 'workflow-panel collapsed';
    
    const header = document.createElement('div');
    header.className = 'workflow-header';
    header.innerHTML = '<span class="workflow-icon">⚙️</span> Agent Workflow <span class="workflow-toggle">▼</span>';
    header.onclick = () => {
        workflowPanel.classList.toggle('collapsed');
    };
    
    const stepsList = document.createElement('div');
    stepsList.className = 'workflow-steps';
    
    steps.forEach((step, index) => {
        const stepItem = document.createElement('div');
        stepItem.className = 'workflow-step';
        stepItem.innerHTML = `<span class="step-number">${index + 1}</span> ${escapeHtml(step)}`;
        stepsList.appendChild(stepItem);
    });
    
    workflowPanel.appendChild(header);
    workflowPanel.appendChild(stepsList);
    
    messageDiv.querySelector('.bubble').appendChild(workflowPanel);
}

/**
 * Display disambiguation options
 */
function displayDisambiguation(disambiguationData, messageDiv) {
    if (!disambiguationData || !disambiguationData.candidates) {
        return;
    }
    
    const disambigPanel = document.createElement('div');
    disambigPanel.className = 'disambiguation-panel';
    
    const header = document.createElement('div');
    header.className = 'disambig-header';
    header.textContent = '👥 Multiple Patients Found - Please Select:';
    
    const candidatesList = document.createElement('div');
    candidatesList.className = 'candidate-list';
    
    disambiguationData.candidates.forEach(candidate => {
        const card = document.createElement('div');
        card.className = 'candidate-card';
        card.onclick = () => selectPatient(candidate.patient_uuid);
        
        const name = document.createElement('div');
        name.className = 'candidate-name';
        name.textContent = candidate.patient_name;
        
        const details = document.createElement('div');
        details.className = 'candidate-details';
        details.innerHTML = `
            UUID: ${candidate.patient_uuid.substring(0, 8)}...<br>
            Age: ${candidate.age || 'N/A'} | Gender: ${candidate.gender || 'N/A'}<br>
            Last seen: ${candidate.last_accessed ? new Date(candidate.last_accessed).toLocaleDateString() : 'Never'}
        `;
        
        card.appendChild(name);
        card.appendChild(details);
        candidatesList.appendChild(card);
    });
    
    disambigPanel.appendChild(header);
    disambigPanel.appendChild(candidatesList);
    
    messageDiv.querySelector('.bubble').appendChild(disambigPanel);
}

/**
 * Select patient from disambiguation
 */
function selectPatient(patientUuid) {
    const messageInput = document.getElementById('messageInput');
    messageInput.value = patientUuid;
    document.getElementById('chatForm').dispatchEvent(new Event('submit'));
}

/**
 * Display confirmation summary
 */
function displayConfirmationSummary(message, messageDiv) {
    // Parse the message for confirmation details
    const confirmPanel = document.createElement('div');
    confirmPanel.className = 'confirmation-panel';
    
    const messageText = document.createElement('div');
    messageText.className = 'confirmation-message';
    messageText.textContent = message;
    
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'confirmation-buttons';
    
    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'confirm-btn';
    confirmBtn.textContent = '✓ Confirm';
    confirmBtn.onclick = () => sendConfirmation('yes');
    
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'cancel-btn';
    cancelBtn.textContent = '✗ Cancel';
    cancelBtn.onclick = () => sendConfirmation('no');
    
    buttonContainer.appendChild(confirmBtn);
    buttonContainer.appendChild(cancelBtn);
    
    confirmPanel.appendChild(messageText);
    confirmPanel.appendChild(buttonContainer);
    
    messageDiv.querySelector('.bubble').appendChild(confirmPanel);
}

/**
 * Display Yes/No confirmation buttons (for new patient creation etc.)
 */
function displayConfirmationButtons(messageDiv) {
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'confirmation-buttons';
    buttonContainer.style.marginTop = '12px';
    
    const yesBtn = document.createElement('button');
    yesBtn.className = 'confirm-btn';
    yesBtn.textContent = '✓ Yes, create patient';
    yesBtn.onclick = () => {
        // Disable buttons after click
        yesBtn.disabled = true;
        noBtn.disabled = true;
        sendConfirmation('yes');
    };
    
    const noBtn = document.createElement('button');
    noBtn.className = 'cancel-btn';
    noBtn.textContent = '✗ No, cancel';
    noBtn.onclick = () => {
        yesBtn.disabled = true;
        noBtn.disabled = true;
        sendConfirmation('no');
    };
    
    buttonContainer.appendChild(yesBtn);
    buttonContainer.appendChild(noBtn);
    
    messageDiv.querySelector('.bubble').appendChild(buttonContainer);
}

/**
 * Send confirmation response
 */
function sendConfirmation(response) {
    const messageInput = document.getElementById('messageInput');
    messageInput.value = response;
    document.getElementById('chatForm').dispatchEvent(new Event('submit'));
}
