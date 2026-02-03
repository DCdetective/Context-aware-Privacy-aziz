// Chat functionality

let chatHistory = [];

document.addEventListener('DOMContentLoaded', function() {
    const chatForm = document.getElementById('chatForm');
    const messageInput = document.getElementById('messageInput');
    const chatMessages = document.getElementById('chatMessages');
    const sendButton = document.getElementById('sendButton');
    
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
});

async function handleSendMessage() {
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const message = messageInput.value.trim();
    
    if (!message) return;
    
    // Add user message to chat
    addUserMessage(message);
    
    // Clear input
    messageInput.value = '';
    
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
            
            // Update privacy visualization
            if (window.updatePrivacyVisualization) {
                window.updatePrivacyVisualization(data.workflow_steps);
            }
        } else {
            addBotMessage({
                message: data.message || 'Sorry, I encountered an error.',
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
    const timestamp = new Date().toLocaleTimeString();
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user-message';
    messageDiv.innerHTML = `
        <div class="message-avatar">👤</div>
        <div class="message-content">
            <div class="message-text">
                <p>${escapeHtml(text)}</p>
            </div>
            <div class="message-meta">${timestamp}</div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
    
    // Add to history
    chatHistory.push({
        type: 'user',
        text: text,
        timestamp: timestamp
    });
}

function addBotMessage(data) {
    const chatMessages = document.getElementById('chatMessages');
    const timestamp = new Date().toLocaleTimeString();
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot-message';
    
    let content = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="message-text">
                <p>${escapeHtml(data.message)}</p>
            </div>
    `;
    
    // Add result card based on intent
    if (data.result) {
        content += formatResultCard(data.intent, data.result);
    }
    
    content += `
            <div class="message-meta">${timestamp}</div>
        </div>
    `;
    
    messageDiv.innerHTML = content;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
    
    // Add to history
    chatHistory.push({
        type: 'bot',
        data: data,
        timestamp: timestamp
    });
}

function formatResultCard(intent, result) {
    if (intent === 'appointment') {
        return `
            <div class="result-card">
                <h4>📅 Appointment Details</h4>
                <div class="result-detail">
                    <span class="result-label">Patient:</span>
                    <span class="result-value">${escapeHtml(result.patient_name || 'N/A')}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Time:</span>
                    <span class="result-value">${formatDateTime(result.appointment_time)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Duration:</span>
                    <span class="result-value">${result.consultation_duration} minutes</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Urgency:</span>
                    <span class="result-value urgency-${result.urgency_level}">${result.urgency_level}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Specialty:</span>
                    <span class="result-value">${result.recommended_specialty || 'General'}</span>
                </div>
            </div>
        `;
    } else if (intent === 'followup') {
        return `
            <div class="result-card">
                <h4>🔄 Follow-up Details</h4>
                <div class="result-detail">
                    <span class="result-label">Patient:</span>
                    <span class="result-value">${escapeHtml(result.patient_name || 'N/A')}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Time:</span>
                    <span class="result-value">${formatDateTime(result.followup_time)}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Previous Visits:</span>
                    <span class="result-value">${result.previous_visits}</span>
                </div>
            </div>
        `;
    } else if (intent === 'summary') {
        return `
            <div class="result-card">
                <h4>📋 Medical Summary</h4>
                <div class="result-detail">
                    <span class="result-label">Patient:</span>
                    <span class="result-value">${escapeHtml(result.patient_name || 'N/A')}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Total Visits:</span>
                    <span class="result-value">${result.summary?.total_visits || 0}</span>
                </div>
                <div class="result-detail">
                    <span class="result-label">Record Types:</span>
                    <span class="result-value">${result.summary?.record_types?.join(', ') || 'None'}</span>
                </div>
            </div>
        `;
    } else if (intent === 'general' && result.suggestions) {
        return `
            <div class="result-card">
                <h4>💡 Suggestions</h4>
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
    indicator.style.display = 'flex';
    scrollToBottom();
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    indicator.style.display = 'none';
}

function scrollToBottom() {
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function formatDateTime(isoString) {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
        weekday: 'short',
        year: 'numeric',
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
