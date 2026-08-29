let currentSessionId = null;

async function init() {
    await loadTree();
    await createSession();
    
    document.querySelectorAll('.mode-pill').forEach(pill => {
        pill.addEventListener('click', (e) => {
            document.querySelectorAll('.mode-pill').forEach(p => p.classList.remove('active'));
            e.target.classList.add('active');
        });
    });
}

async function loadTree() {
    const res = await fetch('/api/workspace/tree');
    const data = await res.json();
    const treeEl = document.getElementById('file-tree');
    treeEl.innerHTML = '';
    
    function renderNode(node, container, pathPrefix = '') {
        for (const [key, val] of Object.entries(node)) {
            const el = document.createElement('div');
            el.className = 'tree-node';
            el.textContent = key;
            const fullPath = pathPrefix + (pathPrefix ? '/' : '') + key;
            el.onclick = async (e) => {
                e.stopPropagation();
                if (typeof val === 'string' || val === null || Object.keys(val).length === 0) {
                    await loadFile(fullPath);
                }
            };
            container.appendChild(el);
            if (typeof val === 'object' && val !== null) {
                const childContainer = document.createElement('div');
                childContainer.style.paddingLeft = '15px';
                renderNode(val, childContainer, fullPath);
                container.appendChild(childContainer);
            }
        }
    }
    
    if (data.tree) {
        renderNode(data.tree, treeEl);
    } else {
        renderNode(data, treeEl);
    }
}

async function loadFile(path) {
    try {
        const res = await fetch(`/api/workspace/file?path=${encodeURIComponent(path)}`);
        const data = await res.json();
        const editor = document.getElementById('editor');
        editor.value = data.content || data.file_content || '';
        document.getElementById('current-file').textContent = path;
    } catch(e) {
        console.error(e);
    }
}

async function createSession() {
    const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mode: 'ASK'})
    });
    const data = await res.json();
    currentSessionId = data.session_id;
}

function sendMessage() {
    const input = document.getElementById('chat-input');
    const msg = input.value;
    if(!msg) return;
    
    const container = document.getElementById('chat-messages');
    const el = document.createElement('div');
    el.className = 'chat-message';
    el.textContent = 'You: ' + msg;
    container.appendChild(el);
    input.value = '';
    
    // mock response
    setTimeout(() => {
        const reply = document.createElement('div');
        reply.className = 'chat-message';
        reply.textContent = 'Agent: Received.';
        container.appendChild(reply);
        container.scrollTop = container.scrollHeight;
    }, 500);
}

document.addEventListener('DOMContentLoaded', init);
