// MedShield Chat - Premium ChatGPT-like Interface

let chatHistory = [];

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
        const response = await fetch('/api/chat/message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message
            })
        });

        const data = await response.json();

        // Hide typing indicator
        hideTypingIndicator();

        if (data.success) {
            // Add bot response
            addBotMessage(data);
        } else {
            addBotMessage({
                message: data.message || 'Sorry, I encountered an error. Please try again.',
                intent: 'error'
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
    scrollToBottom();

    // Add to history
    chatHistory.push({
        type: 'bot',
        data: data,
        timestamp: new Date().toISOString()
    });

    // Update privacy visualization with details
    if (window.updatePrivacyVisualization && data.workflow_steps) {
        const privacyDetails = data.result?.privacy_details || null;
        window.updatePrivacyVisualization(data.workflow_steps, privacyDetails);
    }
}

function formatResultCard(intent, result) {
    if (intent === 'appointment') {
        return `
            <div class="result-card">
                <h4>Appointment Details</h4>
                <div class="result-detail">
                    <span class="result-label">Patient</span>
                    <span class="result-value">${escapeHtml(result.patient_name || 'N/A')}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Time</span>
                    <span class="result-value">${formatDateTime(result.appointment_time)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Duration</span>
                    <span class="result-value">${result.consultation_duration} minutes</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Urgency</span>
                    <span class="result-value urgency-${result.urgency_level}">${capitalizeFirst(result.urgency_level)}</span>
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
                    <span class="result-value">${escapeHtml(result.patient_name || 'N/A')}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Time</span>
                    <span class="result-value">${formatDateTime(result.followup_time)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Previous Visits</span>
                    <span class="result-value">${result.previous_visits}</span>
                </div>
            </div>
        `;
    } else if (intent === 'summary') {
        return `
            <div class="result-card">
                <h4>Medical Summary</h4>
                <div class="result-detail">
                    <span class="result-label">Patient</span>
                    <span class="result-value">${escapeHtml(result.patient_name || 'N/A')}</span>
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
