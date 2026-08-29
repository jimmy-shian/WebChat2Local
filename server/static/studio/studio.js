// WebChat2Local Studio - Core Client Controller

const state = {
    workspacePath: '',
    openFiles: [], // { name, path, content, isDirty }
    activeFile: null,
    editorInstance: null,
    diffEditorInstance: null,
    agentMode: 'AGENT',
    chatHistory: [],
    sessionId: null,
    isDiffMode: false
};

// --- DOM Elements ---
const fileTreeEl = document.getElementById('file-tree');
const editorTabsEl = document.getElementById('editor-tabs');
const editorContainer = document.getElementById('editor-container');
const fallbackEditor = document.getElementById('fallback-editor');
const basicTextarea = document.getElementById('basic-textarea');
const terminalOutput = document.getElementById('terminal-output');
const terminalInput = document.getElementById('terminal-input');
const chatHistoryEl = document.getElementById('chat-history');
const chatInput = document.getElementById('chat-input');
const chatModeBtns = document.querySelectorAll('.mode-btn');

// --- Modals Setup ---
const setupModals = () => {
    const bindModal = (btnId, modalId) => {
        const btn = document.getElementById(btnId);
        const modal = document.getElementById(modalId);
        if (btn && modal) {
            btn.addEventListener('click', () => {
                modal.classList.remove('hidden');
                if (btnId === 'btn-settings') refreshProviderStatus();
            });
        }
    };
    bindModal('btn-docs', 'modal-docs');
    bindModal('btn-settings', 'modal-settings');

    document.querySelectorAll('.btn-close-modal').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.closest('.modal').classList.add('hidden');
        });
    });

    document.querySelectorAll('.modal').forEach(m => {
        m.addEventListener('click', (e) => {
            if (e.target === m) m.classList.add('hidden');
        });
    });

    // Tab switcher in Docs modal
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const tabs = e.target.closest('.tabs');
            const targetId = e.target.dataset.tab;
            tabs.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            
            const modalBody = e.target.closest('.modal-body');
            modalBody.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
            const targetContent = document.getElementById(targetId);
            if (targetContent) targetContent.classList.add('active');
        });
    });
};

// --- Provider Status in Settings ---
async function refreshProviderStatus() {
    try {
        const res = await fetch('/api/providers');
        const data = await res.json();
        const container = document.querySelector('.provider-status');
        if (!container) return;
        container.innerHTML = '';
        const providers = data.providers || [];
        if (providers.length === 0) {
            container.innerHTML = '<span class="badge disconnected">無在線 Provider（請開啟 ChatGPT / Gemini / DeepSeek 網頁版）</span>';
            return;
        }
        providers.forEach(p => {
            const badge = document.createElement('span');
            badge.className = `badge ${p.active ? 'connected' : 'disconnected'}`;
            badge.textContent = `${p.name}: ${p.active ? '🟢 連線中' : '🔴 離線'}`;
            container.appendChild(badge);
        });
    } catch(e) {
        console.warn('Failed to fetch providers', e);
    }
}

// --- Monaco Editor Initialization ---
const initEditor = () => {
    function createMonaco() {
        if (window.monaco) {
            state.editorInstance = monaco.editor.create(editorContainer, {
                value: "// 歡迎使用 WebChat2Local Studio\n// 點擊左側檔案即可開啟編輯，或在右側向 AI Agent 下達指令。\n",
                language: "javascript",
                theme: "vs-dark",
                automaticLayout: true,
                fontSize: 13,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                renderWhitespace: "selection"
            });
            
            state.editorInstance.onDidChangeModelContent(() => {
                if (state.activeFile) {
                    const f = state.openFiles.find(f => f.path === state.activeFile);
                    if (f && f.content !== state.editorInstance.getValue()) {
                        f.isDirty = true;
                        f.content = state.editorInstance.getValue();
                        renderTabs();
                    }
                }
            });
        }
    }

    if (window.require && typeof window.require === 'function') {
        window.require(['vs/editor/editor.main'], function () {
            createMonaco();
        });
    } else if (window.monaco) {
        createMonaco();
    } else {
        editorContainer.style.display = 'none';
        fallbackEditor.style.display = 'block';
        basicTextarea.addEventListener('input', () => {
            if (state.activeFile) {
                const f = state.openFiles.find(f => f.path === state.activeFile);
                if (f && f.content !== basicTextarea.value) {
                    f.isDirty = true;
                    f.content = basicTextarea.value;
                    renderTabs();
                }
            }
        });
    }
};

// --- Workspace Tree ---
const loadWorkspaceTree = async (path = '.') => {
    try {
        const res = await fetch(`/api/workspace/tree?path=${encodeURIComponent(path)}`);
        if (!res.ok) throw new Error('API Error');
        const data = await res.json();
        renderTree(data.entries || [], fileTreeEl, path === '.' ? '' : path);
    } catch (e) {
        console.warn('Workspace tree fetch failed:', e);
    }
};

const renderTree = (entries, container, basePath) => {
    container.innerHTML = '';
    
    // Sort directories first, then files alphabetically
    const sorted = [...entries].sort((a, b) => {
        if (a.type === b.type) return a.name.localeCompare(b.name);
        return a.type === 'directory' ? -1 : 1;
    });

    sorted.forEach(entry => {
        const item = document.createElement('div');
        item.className = 'tree-item';
        
        const isDir = entry.type === 'directory';
        const icon = isDir ? '📁' : getFileIcon(entry.name);
        const fullPath = basePath ? `${basePath}/${entry.name}` : entry.name;
        
        item.innerHTML = `
            <span class="tree-icon">${icon}</span>
            <span class="tree-name">${entry.name}</span>
            ${entry.size ? `<span class="tree-size">${formatBytes(entry.size)}</span>` : ''}
        `;
        
        item.addEventListener('click', async () => {
            document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('active'));
            item.classList.add('active');
            
            if (isDir) {
                // Toggle expand or load subdirectory
                let childContainer = item.nextElementSibling;
                if (childContainer && childContainer.classList.contains('tree-children')) {
                    childContainer.remove();
                } else {
                    const subRes = await fetch(`/api/workspace/tree?path=${encodeURIComponent(fullPath)}`);
                    const subData = await subRes.json();
                    childContainer = document.createElement('div');
                    childContainer.className = 'tree-children';
                    childContainer.style.paddingLeft = '14px';
                    renderTree(subData.entries || [], childContainer, fullPath);
                    item.after(childContainer);
                }
            } else {
                await openFile(fullPath, entry.name);
            }
        });
        container.appendChild(item);
    });
};

function getFileIcon(filename) {
    if (filename.endsWith('.py')) return '🐍';
    if (filename.endsWith('.js') || filename.endsWith('.ts')) return '📜';
    if (filename.endsWith('.html')) return '🌐';
    if (filename.endsWith('.css')) return '🎨';
    if (filename.endsWith('.json')) return '⚙️';
    if (filename.endsWith('.md')) return '📝';
    return '📄';
}

function formatBytes(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes}B`;
    return `${(bytes / 1024).toFixed(1)}K`;
}

// --- Editor Tabs & File Handling ---
const openFile = async (path, name) => {
    let file = state.openFiles.find(f => f.path === path);
    if (!file) {
        try {
            const res = await fetch(`/api/workspace/file?path=${encodeURIComponent(path)}`);
            const data = await res.json();
            file = {
                path,
                name,
                content: data.content || '',
                revision: data.revision,
                isDirty: false
            };
            state.openFiles.push(file);
        } catch (e) {
            console.error('Failed to load file content', e);
            file = { path, name, content: `// Error reading ${name}`, isDirty: false };
            state.openFiles.push(file);
        }
    }
    state.activeFile = path;
    
    // Set Editor content & syntax
    if (state.editorInstance && window.monaco) {
        const ext = name.split('.').pop().toLowerCase();
        const langMap = {
            'js': 'javascript', 'ts': 'typescript', 'py': 'python',
            'html': 'html', 'css': 'css', 'json': 'json', 'md': 'markdown'
        };
        const lang = langMap[ext] || 'plaintext';
        const model = monaco.editor.createModel(file.content, lang);
        state.editorInstance.setModel(model);
    } else {
        basicTextarea.value = file.content;
    }
    renderTabs();
};

const renderTabs = () => {
    editorTabsEl.innerHTML = '';
    state.openFiles.forEach(file => {
        const tab = document.createElement('div');
        tab.className = `tab ${file.path === state.activeFile ? 'active' : ''} ${file.isDirty ? 'dirty' : ''}`;
        tab.innerHTML = `
            <span>${file.name}</span>
            <button class="tab-close" data-path="${file.path}">×</button>
        `;
        tab.addEventListener('click', (e) => {
            if (e.target.classList.contains('tab-close')) {
                closeFile(file.path);
            } else {
                openFile(file.path, file.name);
            }
        });
        editorTabsEl.appendChild(tab);
    });
};

const closeFile = (path) => {
    state.openFiles = state.openFiles.filter(f => f.path !== path);
    if (state.activeFile === path) {
        state.activeFile = state.openFiles.length ? state.openFiles[0].path : null;
        if (state.activeFile) {
            const next = state.openFiles[0];
            openFile(next.path, next.name);
        } else if (state.editorInstance) {
            state.editorInstance.setValue('');
        } else {
            basicTextarea.value = '';
        }
    }
    renderTabs();
};

// --- Terminal Execution ---
const setupTerminal = () => {
    if (!terminalInput) return;
    terminalInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            const cmd = terminalInput.value.trim();
            if (!cmd) return;
            terminalInput.value = '';
            appendTerminal(`PS> ${cmd}`, 'user');
            
            try {
                const res = await fetch('/api/terminal/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: cmd, cwd: '.' })
                });
                const data = await res.json();
                if (data.stdout) appendTerminal(data.stdout, 'output');
                if (data.stderr) appendTerminal(data.stderr, 'error');
                if (data.exit_code !== 0 && data.exit_code !== undefined) {
                    appendTerminal(`[Process exited with code ${data.exit_code}]`, 'error');
                }
            } catch (err) {
                appendTerminal(`Execution failed: ${err.message}`, 'error');
            }
        }
    });

    const clearBtn = document.getElementById('btn-term-clear');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            terminalOutput.innerHTML = '<div class="term-line welcome">WebChat2Local Studio Terminal Initialized.</div>';
        });
    }
};

const appendTerminal = (text, type = 'output') => {
    if (!terminalOutput) return;
    const line = document.createElement('div');
    line.className = `term-line ${type}`;
    line.textContent = text;
    terminalOutput.appendChild(line);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
};

// --- Agent Chat & Multi-turn Execution ---
const setupChat = () => {
    chatModeBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            chatModeBtns.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            state.agentMode = e.target.dataset.mode;
        });
    });

    const sendBtn = document.getElementById('btn-send-chat');
    if (sendBtn) sendBtn.addEventListener('click', sendChat);

    if (chatInput) {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChat();
            }
        });
    }
};

const sendChat = async () => {
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = '';
    appendChat(text, 'user');
    
    // Create session if not present
    if (!state.sessionId) {
        try {
            const sRes = await fetch('/api/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: state.agentMode })
            });
            const sData = await sRes.json();
            state.sessionId = sData.session_id;
        } catch(e) {
            console.error('Session creation failed', e);
        }
    }

    const agentMsg = appendChat('思考中...', 'agent');
    const msgContent = agentMsg.querySelector('.msg-content');

    try {
        const res = await fetch('/api/agent/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: state.sessionId || 'default',
                prompt: text,
                active_file: state.activeFile,
                mode: state.agentMode,
                model: 'auto'
            })
        });

        if (!res.ok) {
            msgContent.textContent = `[錯誤: ${res.statusText}] 請確認 ChatGPT / Gemini / DeepSeek 網頁版已開啟並連線。`;
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let accumulated = '';
        msgContent.textContent = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6).trim();
                    if (dataStr === '[DONE]') continue;
                    try {
                        const event = JSON.parse(dataStr);
                        if (event.type === 'message.chunk') {
                            accumulated += (event.delta || '');
                            msgContent.textContent = accumulated;
                        } else if (event.type === 'edit.proposed') {
                            appendToolCard('edit_file', event.proposal);
                        } else if (event.type === 'tool.request') {
                            appendToolCard(event.tool, event.arguments);
                        } else if (event.type === 'terminal.output') {
                            appendTerminal(event.stdout || event.stderr || '');
                        } else if (event.type === 'agent.completed') {
                            if (event.summary && !accumulated) {
                                msgContent.textContent = event.summary;
                            }
                        }
                    } catch (e) {
                        // plain text chunk fallback
                        if (dataStr) {
                            accumulated += dataStr;
                            msgContent.textContent = accumulated;
                        }
                    }
                }
            }
        }

        if (!msgContent.textContent) {
            msgContent.textContent = accumulated || '已收到回應。';
        }
    } catch(err) {
        msgContent.textContent = `連線錯誤: ${err.message}`;
    }
};

const appendChat = (text, role) => {
    const msg = document.createElement('div');
    msg.className = `chat-message ${role}`;
    msg.innerHTML = `<div class="msg-content">${text}</div>`;
    chatHistoryEl.appendChild(msg);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
    return msg;
};

const appendToolCard = (type, data) => {
    const card = document.createElement('div');
    card.className = 'tool-card';
    
    let body = '', actions = '';
    const proposalId = data.proposal_id || ('prop_' + Math.random().toString(36).substr(2, 9));

    if (type === 'write_file' || type === 'edit_file') {
        const filePath = data.path || data.target || 'file.txt';
        const diffText = data.diff || data.new_content || '';
        body = `<strong>檔案修改提案:</strong> <code>${filePath}</code><pre style="max-height:120px; overflow:auto; margin-top:5px; background:#000; padding:5px; border-radius:4px; font-size:11px;">${escapeHtml(diffText)}</pre>`;
        actions = `
            <button class="btn-sm accept" onclick="acceptProposal('${proposalId}')">批准套用 ✓</button>
            <button class="btn-sm reject" onclick="rejectProposal('${proposalId}')">捨棄 ✗</button>
        `;
    } else if (type === 'run_command') {
        const cmd = data.command || '';
        body = `<strong>終端命令提案:</strong> <code>${cmd}</code>`;
        actions = `<button class="btn-sm" onclick="runInTerminal('${escapeHtml(cmd)}')">在終端執行 ▶</button>`;
    } else {
        body = `<strong>工具呼叫:</strong> ${type}<pre style="font-size:11px;">${JSON.stringify(data, null, 2)}</pre>`;
    }

    card.innerHTML = `
        <div class="tool-header">🛠️ ${type}</div>
        <div class="tool-body">${body}</div>
        <div class="tool-actions">${actions}</div>
    `;
    
    chatHistoryEl.appendChild(card);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
};

window.acceptProposal = async (proposalId) => {
    try {
        const res = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/accept`, { method: 'POST' });
        const data = await res.json();
        alert(`提案 ${proposalId} 已成功套用！`);
        loadWorkspaceTree();
        if (state.activeFile) openFile(state.activeFile, state.activeFile.split('/').pop());
    } catch(e) {
        alert(`套用失敗: ${e.message}`);
    }
};

window.rejectProposal = async (proposalId) => {
    try {
        await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/reject`, { method: 'POST' });
        alert(`提案 ${proposalId} 已捨棄。`);
    } catch(e) {
        alert(`操作失敗: ${e.message}`);
    }
};

window.runInTerminal = (cmd) => {
    if (terminalInput) {
        terminalInput.value = cmd;
        terminalInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    }
};

function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- App Initialization ---
window.addEventListener('DOMContentLoaded', () => {
    initEditor();
    loadWorkspaceTree();
    setupModals();
    setupTerminal();
    setupChat();
    refreshProviderStatus();

    const refreshBtn = document.getElementById('btn-refresh');
    if (refreshBtn) refreshBtn.addEventListener('click', () => loadWorkspaceTree());
});
