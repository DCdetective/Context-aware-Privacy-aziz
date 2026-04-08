const EVENT_TYPES = new Set([
  'user_message', 'assistant_message', 'stream_chunk', 'workflow_step', 'privacy_mask',
  'appointment_card', 'followup_card', 'summary_card', 'hitl_prompt', 'system_notice', 'error_event'
]);

const state = {
  sessionId: null,
  events: [],
  workflow: [],
  activeAgent: null,
  activeAgentResponsibility: null,
  streamingBubble: null,
  lastAssistantBubble: null,
  privacyCollapsed: false,
};

const AGENT_RESPONSIBILITIES = {
  Gatekeeper: 'privacy masking',
  Coordinator: 'routing/planning',
  'Context Agent': 'context retrieval',
  'Execution Agent': 'task execution',
  'Memory Manager': 'save/retrieve history',
  'HITL Manager': 'waiting for user confirmation',
};

const els = {};

document.addEventListener('DOMContentLoaded', async () => {
  bindElements();
  bindEvents();
  await initSession();
  await restoreSession();
  if (!els.chatMessages.children.length) {
    renderAssistantMessage('Hello, I\'m MedShield. Ask me about appointments, follow-ups, or summaries.');
  }
});

function bindElements() {
  els.chatForm = document.getElementById('chatForm');
  els.messageInput = document.getElementById('messageInput');
  els.sendButton = document.getElementById('sendButton');
  els.chatMessages = document.getElementById('chatMessages');
  els.workflowTimeline = document.getElementById('workflowTimeline');
  els.agentActivity = document.getElementById('agentActivity');
  els.privacyPanel = document.getElementById('privacyPanel');
  els.sessionBadge = document.getElementById('sessionBadge');
  els.memoryBadge = document.getElementById('memoryBadge');
  els.toggleWorkflow = document.getElementById('toggleWorkflow');
  els.workflowPanel = document.getElementById('workflowPanel');
  els.togglePrivacy = document.getElementById('togglePrivacy');
}

function bindEvents() {
  els.chatForm.addEventListener('submit', onSubmit);
  els.messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      els.chatForm.dispatchEvent(new Event('submit'));
    }
  });
  els.messageInput.addEventListener('input', autoResize);

  els.toggleWorkflow.addEventListener('click', () => {
    const hidden = els.workflowPanel.style.display === 'none';
    els.workflowPanel.style.display = hidden ? '' : 'none';
    els.toggleWorkflow.textContent = hidden ? 'Hide' : 'Show';
  });

  els.togglePrivacy.addEventListener('click', () => {
    state.privacyCollapsed = !state.privacyCollapsed;
    els.privacyPanel.style.display = state.privacyCollapsed ? 'none' : 'flex';
    els.togglePrivacy.textContent = state.privacyCollapsed ? 'Expand' : 'Collapse';
  });
}

async function initSession() {
  const cachedSessionId = localStorage.getItem('medshield_session_id');
  if (cachedSessionId) {
    state.sessionId = cachedSessionId;
    updateSessionBadge();
    return;
  }

  const response = await fetch('/api/chat/sessions', { method: 'POST' });
  const data = await response.json();
  state.sessionId = data.session_id;
  localStorage.setItem('medshield_session_id', state.sessionId);
  updateSessionBadge();
}

async function restoreSession() {
  if (!state.sessionId) return;
  try {
    const response = await fetch(`/api/chat/sessions/${state.sessionId}`);
    if (!response.ok) return;
    const data = await response.json();
    const events = data?.snapshot?.events || [];
    if (!Array.isArray(events)) return;

    state.events = [];
    clearView();

    for (const event of events) {
      if (event.event_type === 'stream_chunk') continue;
      applyEvent(event, { restoring: true });
    }
  } catch (error) {
    console.error('Failed restoring session:', error);
  }
}

async function onSubmit(e) {
  e.preventDefault();
  const message = els.messageInput.value.trim();
  if (!message) return;

  renderUserMessage(message);
  els.messageInput.value = '';
  autoResize();
  setInputDisabled(true);

  try {
    await streamMessage(message);
  } catch (error) {
    console.error(error);
    applyEvent({
      event_type: 'error_event',
      status: 'failed',
      payload: { message: 'Connection error. Please try again.' },
    });
  } finally {
    setInputDisabled(false);
    els.messageInput.focus();
  }
}

async function streamMessage(message) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: state.sessionId }),
  });

  if (!response.ok || !response.body) {
    throw new Error('Stream failed');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() || '';

    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith('data:')) continue;
      const raw = line.replace(/^data:\s*/, '');
      try {
        const event = JSON.parse(raw);
        applyEvent(event);
      } catch {
        // ignore malformed chunk
      }
    }
  }
}

function applyEvent(event, options = {}) {
  if (!event || !EVENT_TYPES.has(event.event_type)) return;

  state.events.push(event);

  switch (event.event_type) {
    case 'workflow_step':
      renderWorkflowStep(event);
      updateAgent(event.agent, event.payload?.responsibility);
      break;
    case 'privacy_mask':
      renderPrivacyEvent(event);
      updateAgent('Gatekeeper', AGENT_RESPONSIBILITIES.Gatekeeper);
      break;
    case 'stream_chunk':
      renderStreamChunk(event.payload?.chunk || '');
      updateAgent('Execution Agent', AGENT_RESPONSIBILITIES['Execution Agent']);
      break;
    case 'assistant_message':
      finalizeStreamMessage(event.payload?.content || '');
      break;
    case 'appointment_card':
    case 'followup_card':
    case 'summary_card':
      renderResultCard(event.event_type, event.payload || {});
      break;
    case 'hitl_prompt':
      renderHitlPrompt(event.payload?.prompt || 'Action required');
      updateAgent('HITL Manager', AGENT_RESPONSIBILITIES['HITL Manager']);
      break;
    case 'system_notice':
      handleSystemNotice(event.payload || {});
      if (!options.restoring) {
        if (event.payload?.session_id) {
          state.sessionId = event.payload.session_id;
          localStorage.setItem('medshield_session_id', state.sessionId);
          updateSessionBadge();
        }
      }
      break;
    case 'error_event':
      renderAssistantMessage(event.payload?.message || 'Unknown error', { error: true });
      break;
    default:
      break;
  }

  scrollToBottom();
}

function handleSystemNotice(payload) {
  const op = payload.operation;
  if (op === 'memory_read') {
    els.memoryBadge.textContent = 'Memory: read';
  } else if (op === 'memory_write') {
    els.memoryBadge.textContent = 'Memory: updated';
  } else if (payload.notice === 'stream_complete') {
    els.memoryBadge.textContent = 'Memory: synced';
  }
}

function renderUserMessage(text) {
  const message = document.createElement('div');
  message.className = 'message user';
  message.innerHTML = `<div class="bubble"><div>${escapeHtml(text)}</div></div>`;
  els.chatMessages.appendChild(message);
}

function renderAssistantMessage(text, options = {}) {
  const message = document.createElement('div');
  message.className = 'message assistant';
  const safe = escapeHtml(text).replace(/\n/g, '<br>');
  const color = options.error ? ' style="color:#fca5a5"' : '';
  message.innerHTML = `<div class="bubble"><div${color}>${safe}</div></div>`;
  els.chatMessages.appendChild(message);
  state.lastAssistantBubble = message.querySelector('.bubble');
}

function renderStreamChunk(chunk) {
  if (!chunk) return;
  if (!state.streamingBubble) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message assistant';
    wrapper.innerHTML = `<div class="bubble"><div class="streaming-cursor" id="streamText"></div></div>`;
    els.chatMessages.appendChild(wrapper);
    state.streamingBubble = wrapper.querySelector('#streamText');
    state.lastAssistantBubble = wrapper.querySelector('.bubble');
  }
  const current = state.streamingBubble.textContent || '';
  const normalizedChunk = String(chunk).trim();
  if (!normalizedChunk) return;
  state.streamingBubble.textContent = current
    ? `${current} ${normalizedChunk}`.replace(/\s+/g, ' ').trim()
    : normalizedChunk;
}

function finalizeStreamMessage(text) {
  if (state.streamingBubble) {
    state.streamingBubble.classList.remove('streaming-cursor');
    state.streamingBubble.innerHTML = escapeHtml(text).replace(/\n/g, '<br>');
    state.streamingBubble = null;
  } else {
    renderAssistantMessage(text);
  }
}

function renderWorkflowStep(event) {
  const payload = event.payload || {};
  const stepText = payload.step || `${payload.from_stage || '-'} → ${payload.to_stage || '-'}`;
  const item = document.createElement('div');
  item.className = `workflow-item ${event.status || 'completed'}`;
  item.innerHTML = `
    <div class="workflow-title">${escapeHtml(stepText)}</div>
    <div class="workflow-time">${escapeHtml((event.status || 'completed').toUpperCase())} • ${formatTime(payload.timestamp || event.created_at)}</div>
  `;
  els.workflowTimeline.appendChild(item);
}

function renderPrivacyEvent(event) {
  const p = event.payload || {};
  const item = document.createElement('div');
  item.className = 'privacy-item';
  item.innerHTML = `
    <div><strong>${escapeHtml(p.field || 'PII')}</strong></div>
    <div class="map">${escapeHtml(String(p.original ?? ''))} → ${escapeHtml(String(p.transformed ?? ''))}</div>
    <div>${escapeHtml(p.method || 'masking')}</div>
  `;
  els.privacyPanel.prepend(item);
}

function renderResultCard(type, payload) {
  if (!state.lastAssistantBubble) return;
  const card = document.createElement('div');
  card.className = 'result-card';
  const titleMap = {
    appointment_card: 'Appointment Progress',
    followup_card: 'Follow-up Progress',
    summary_card: 'Summary Progress',
  };
  card.innerHTML = `<h4>${titleMap[type] || 'Task'}</h4>${objectToRows(payload)}`;
  state.lastAssistantBubble.appendChild(card);
}

function renderHitlPrompt(prompt) {
  if (!state.lastAssistantBubble) return;
  const row = document.createElement('div');
  row.className = 'meta-row';
  row.innerHTML = `<span class="meta-pill">HITL required</span>`;

  const yes = document.createElement('button');
  yes.className = 'ghost-btn';
  yes.textContent = 'Confirm';
  yes.onclick = () => sendAction('hitl_response', 'confirm');

  const no = document.createElement('button');
  no.className = 'ghost-btn';
  no.textContent = 'Cancel';
  no.onclick = () => sendAction('hitl_response', 'cancel');

  const helper = document.createElement('div');
  helper.className = 'meta-row';
  helper.innerHTML = `<span class="meta-pill">${escapeHtml(prompt.slice(0, 80))}</span>`;

  row.appendChild(yes);
  row.appendChild(no);
  state.lastAssistantBubble.appendChild(helper);
  state.lastAssistantBubble.appendChild(row);
}

async function sendAction(action, value) {
  if (!state.sessionId) return;
  setInputDisabled(true);
  try {
    const response = await fetch(`/api/chat/sessions/${state.sessionId}/actions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Action failed');
    (data.events || []).forEach((event) => applyEvent(event));
    if (!data.events?.length) {
      finalizeStreamMessage(data.message || 'Action processed');
    }
  } catch (e) {
    renderAssistantMessage(e.message || 'Action failed', { error: true });
  } finally {
    setInputDisabled(false);
  }
}

function updateAgent(agent, responsibility) {
  if (!agent) return;
  const role = responsibility || AGENT_RESPONSIBILITIES[agent] || 'processing';
  state.activeAgent = agent;
  state.activeAgentResponsibility = role;
  els.agentActivity.innerHTML = `<strong>${escapeHtml(agent)}</strong> • ${escapeHtml(role)}`;
}

function updateSessionBadge() {
  const sid = state.sessionId ? `${state.sessionId.slice(0, 8)}…` : '-';
  els.sessionBadge.textContent = `Session: ${sid}`;
}

function setInputDisabled(disabled) {
  els.messageInput.disabled = disabled;
  els.sendButton.disabled = disabled;
}

function autoResize() {
  els.messageInput.style.height = 'auto';
  els.messageInput.style.height = `${Math.min(els.messageInput.scrollHeight, 180)}px`;
}

function formatTime(value) {
  if (!value) return 'now';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return 'now';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function objectToRows(data) {
  return Object.entries(data || {})
    .slice(0, 8)
    .filter(([k, v]) => v !== null && v !== undefined && typeof v !== 'object')
    .map(([k, v]) => `<p><strong>${escapeHtml(k)}:</strong> ${escapeHtml(String(v))}</p>`)
    .join('');
}

function clearView() {
  els.chatMessages.innerHTML = '';
  els.workflowTimeline.innerHTML = '';
  els.privacyPanel.innerHTML = '';
  state.lastAssistantBubble = null;
  state.streamingBubble = null;
}

function scrollToBottom() {
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value || '';
  return div.innerHTML;
}
