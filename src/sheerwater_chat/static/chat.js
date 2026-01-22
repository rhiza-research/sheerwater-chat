const form = document.getElementById('chat-form');
const input = document.getElementById('message-input');
const messagesDiv = document.getElementById('messages');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat');
const conversationIdInput = document.getElementById('conversation-id');

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
    contentDiv.textContent = content;
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
