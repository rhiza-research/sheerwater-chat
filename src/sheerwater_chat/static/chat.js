import { marked } from 'https://cdn.jsdelivr.net/npm/marked@17/+esm';
import hljs from 'https://cdn.jsdelivr.net/npm/highlight.js@11/+esm';
import { markedHighlight } from 'https://cdn.jsdelivr.net/npm/marked-highlight@2/+esm';

const form = document.getElementById('chat-form');
const input = document.getElementById('message-input');
const messagesDiv = document.getElementById('messages');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat');
const conversationIdInput = document.getElementById('conversation-id');
const rateLimitStatus = document.getElementById('rate-limit-status');
const rateLimitFill = document.getElementById('rate-limit-fill');
const rateLimitRemaining = document.getElementById('rate-limit-remaining');
const rateLimitTotal = document.getElementById('rate-limit-total');
const rateLimitResetTime = document.getElementById('rate-limit-reset-time');

// Global state for rate limit countdown
let rateLimitResetTimestamp = null;
let rateLimitCountdownInterval = null;

// Configure marked.js with highlight.js for code syntax highlighting
marked.use(markedHighlight({
    langPrefix: 'hljs language-',
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    }
}));

marked.setOptions({
    breaks: true,
    gfm: true
});

// Render markdown content safely
function renderMarkdown(content) {
    try {
        return marked.parse(content);
    } catch (e) {
        console.error('Markdown parse error:', e);
        return content;
    }
}

// Update countdown timer display
function updateCountdownDisplay() {
    if (!rateLimitResetTimestamp) return;

    const now = new Date();
    const diffMs = rateLimitResetTimestamp - now;
    const diffSec = Math.floor(diffMs / 1000);

    if (diffSec > 0) {
        rateLimitResetTime.textContent = `${diffSec}s`;
    } else {
        rateLimitResetTime.textContent = '0s';

        // Reset to full limit when window expires
        const limit = parseInt(rateLimitTotal.textContent.replace(/,/g, ''));
        if (!isNaN(limit)) {
            rateLimitRemaining.textContent = limit.toLocaleString();
            rateLimitFill.style.width = '100%';
            rateLimitFill.style.background = '#4a90d9'; // Blue
        }

        if (rateLimitCountdownInterval) {
            clearInterval(rateLimitCountdownInterval);
            rateLimitCountdownInterval = null;
        }
    }
}

// Update rate limit status bar
function updateRateLimitStatus(rateLimitData) {
    if (!rateLimitData) return;

    const remaining = parseInt(rateLimitData.input_tokens_remaining);
    const limit = parseInt(rateLimitData.input_tokens_limit);

    if (isNaN(remaining) || isNaN(limit)) return;

    // Show the status bar
    rateLimitStatus.classList.remove('hidden');

    // Update values
    rateLimitRemaining.textContent = remaining.toLocaleString();
    rateLimitTotal.textContent = limit.toLocaleString();

    // Update progress bar
    const percentage = (remaining / limit) * 100;
    rateLimitFill.style.width = `${percentage}%`;

    // Color based on remaining percentage
    if (percentage < 20) {
        rateLimitFill.style.background = '#e74c3c'; // Red
    } else if (percentage < 50) {
        rateLimitFill.style.background = '#f39c12'; // Orange
    } else {
        rateLimitFill.style.background = '#4a90d9'; // Blue
    }

    // Set up countdown timer
    if (rateLimitData.input_tokens_reset) {
        rateLimitResetTimestamp = new Date(rateLimitData.input_tokens_reset);

        // Clear existing interval if any
        if (rateLimitCountdownInterval) {
            clearInterval(rateLimitCountdownInterval);
        }

        // Update display immediately
        updateCountdownDisplay();

        // Start countdown interval (updates every second)
        rateLimitCountdownInterval = setInterval(updateCountdownDisplay, 1000);
    }
}

// Render all existing messages on page load
document.querySelectorAll('.message-content.needs-render').forEach(el => {
    const rawContent = el.textContent;
    if (rawContent) {
        el.innerHTML = renderMarkdown(rawContent);
        el.classList.remove('needs-render');
    }
});

// Auto-resize textarea
input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 200) + 'px';
});

// Handle form submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const message = input.value.trim();
    if (!message) return;

    // Disable input while sending
    input.disabled = true;
    sendBtn.disabled = true;

    // Clear welcome message if present
    const welcome = messagesDiv.querySelector('.welcome');
    if (welcome) welcome.remove();

    // Add user message to UI
    addMessage('user', message);
    input.value = '';
    input.style.height = 'auto';

    // Add loading indicator
    const loadingMsg = addMessage('assistant', 'Thinking', true);

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                conversation_id: conversationIdInput.value || null
            })
        });

        if (!response.ok) {
            throw new Error('Failed to send message');
        }

        const data = await response.json();

        // Update conversation ID for new conversations
        if (!conversationIdInput.value) {
            conversationIdInput.value = data.conversation_id;
            // Update URL without reload
            history.pushState({}, '', `/c/${data.conversation_id}`);
        }

        // Remove loading and add actual response
        loadingMsg.remove();
        addMessage('assistant', data.response, false, data.tool_calls, data.usage, data.chart_urls);

        // Update rate limit status bar
        if (data.rate_limit) {
            updateRateLimitStatus(data.rate_limit);
        }

    } catch (error) {
        loadingMsg.remove();
        addMessage('assistant', 'Error: ' + error.message);
    } finally {
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }
});

// Add message to UI
function addMessage(role, content, loading = false, toolCalls = null, usage = null, chartUrls = null) {
    const div = document.createElement('div');
    div.className = `message ${role}` + (loading ? ' loading' : '');

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    if (loading) {
        contentDiv.textContent = content;
    } else {
        contentDiv.innerHTML = renderMarkdown(content);
    }
    div.appendChild(contentDiv);

    // Render chart iframes
    if (chartUrls && chartUrls.length > 0) {
        const chartContainer = document.createElement('div');
        chartContainer.className = 'chart-container';
        chartUrls.forEach(url => {
            const iframe = document.createElement('iframe');
            iframe.className = 'chart-iframe';
            iframe.src = url;
            iframe.sandbox = 'allow-scripts';
            iframe.loading = 'lazy';
            chartContainer.appendChild(iframe);
        });
        div.appendChild(chartContainer);
    }

    if (toolCalls && toolCalls.length > 0) {
        const toolsDiv = document.createElement('div');
        toolsDiv.className = 'tool-calls';
        toolCalls.forEach(tc => {
            const tcDiv = document.createElement('div');
            tcDiv.className = 'tool-call';
            tcDiv.innerHTML = `<span class="tool-name">${tc.name}</span>`;
            toolsDiv.appendChild(tcDiv);
        });
        div.appendChild(toolsDiv);
    }

    if (usage && role === 'assistant') {
        const usageDiv = document.createElement('div');
        usageDiv.className = 'token-usage';
        usageDiv.innerHTML = `
            <span class="usage-label">Tokens:</span>
            <span class="usage-value">${usage.input_tokens.toLocaleString()} in</span>
            <span class="usage-sep">·</span>
            <span class="usage-value">${usage.output_tokens.toLocaleString()} out</span>
            <span class="usage-sep">·</span>
            <span class="usage-total">${usage.total_tokens.toLocaleString()} total</span>
        `;
        div.appendChild(usageDiv);
    }

    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    return div;
}

// New chat button
newChatBtn.addEventListener('click', () => {
    window.location.href = '/';
});

// Handle Enter key (submit) vs Shift+Enter (newline)
input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        form.dispatchEvent(new Event('submit'));
    }
});

// Settings modal
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const settingsForm = document.getElementById('settings-form');
const settingsCancel = document.getElementById('settings-cancel');
const modelSelect = document.getElementById('model-select');
const systemPrompt = document.getElementById('system-prompt');
const modalOverlay = settingsModal.querySelector('.modal-overlay');

async function openSettings() {
    try {
        const response = await fetch('/api/settings');
        if (response.ok) {
            const settings = await response.json();
            modelSelect.value = settings.model;
            systemPrompt.value = settings.system_prompt;
        }
    } catch (e) {
        console.error('Failed to load settings:', e);
    }
    settingsModal.classList.remove('hidden');
}

function closeSettings() {
    settingsModal.classList.add('hidden');
}

settingsBtn.addEventListener('click', openSettings);
settingsCancel.addEventListener('click', closeSettings);
modalOverlay.addEventListener('click', closeSettings);

settingsForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    try {
        const response = await fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: modelSelect.value,
                system_prompt: systemPrompt.value
            })
        });

        if (response.ok) {
            closeSettings();
        } else {
            console.error('Failed to save settings');
        }
    } catch (e) {
        console.error('Failed to save settings:', e);
    }
});
