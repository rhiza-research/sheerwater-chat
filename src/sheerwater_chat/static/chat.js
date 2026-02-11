import { marked } from 'https://cdn.jsdelivr.net/npm/marked@17/+esm';
import hljs from 'https://cdn.jsdelivr.net/npm/highlight.js@11/+esm';
import { markedHighlight } from 'https://cdn.jsdelivr.net/npm/marked-highlight@2/+esm';

const form = document.getElementById('chat-form');
const input = document.getElementById('message-input');
const messagesDiv = document.getElementById('messages');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat');
const conversationIdInput = document.getElementById('conversation-id');

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
        addMessage('assistant', data.response, false, data.tool_calls);

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
function addMessage(role, content, loading = false, toolCalls = null) {
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
