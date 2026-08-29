// WebChat2Local Studio v4.2 - Core Client Controller

const state = {
    workspacePath: 'WebChat2Local',
    openFiles: [], // { name, path, content, revision, isDirty, model }
    activeFile: null,
    editorInstance: null,
    diffEditorInstance: null,
    agentMode: 'AGENT',
    chatHistory: [],
    sessionId: null,
    pendingProposal: null,
    cmdHistory: [],
    cmdHistoryIndex: -1
};

// --- Helper Functions ---
function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function copyCode(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    navigator.clipboard.writeText(el.innerText || el.textContent).then(() => {
        alert('設定範例已複製到剪貼簿！');
    }).catch(err => {
        console.error('Copy failed:', err);
    });
}
window.copyCode = copyCode;

// --- Monaco Editor Initialization ---
function initMonaco() {
    const container = document.getElementById('monaco-editor-container');
    const fallback = document.getElementById('fallback-editor');
    const textarea = document.getElementById('basic-textarea');

    function createEditor() {
        if (window.monaco && container) {
            state.editorInstance = monaco.editor.create(container, {
                value: "// 歡迎使用 WebChat2Local Studio (v4.2)\n// 點擊左側檔案開啟代碼，或於右側向 AI Agent 下達需求。\n",
                language: "javascript",
                theme: "vs-dark",
                fontSize: 13,
                automaticLayout: true,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                renderWhitespace: "selection"
            });

            state.editorInstance.onDidChangeModelContent(() => {
                if (state.activeFile) {
                    const f = state.openFiles.find(item => item.path === state.activeFile);
                    if (f && f.content !== state.editorInstance.getValue()) {
                        f.isDirty = true;
                        f.content = state.editorInstance.getValue();
                        renderTabs();
                    }
                }
            });

            // Add Ctrl+S save keybinding
            state.editorInstance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
                saveActiveFile();
            });
        }
    }

    if (window.require && typeof window.require === 'function') {
        window.require(['vs/editor/editor.main'], function () {
            createEditor();
        });
    } else if (window.monaco) {
        createEditor();
    } else {
        if (container) container.style.display = 'none';
        if (fallback) fallback.style.display = 'block';
        if (textarea) {
            textarea.addEventListener('input', () => {
                if (state.activeFile) {
                    const f = state.openFiles.find(item => item.path === state.activeFile);
                    if (f) {
                        f.isDirty = true;
                        f.content = textarea.value;
                        renderTabs();
                    }
                }
            });
        }
    }
}

// --- Workspace File Tree ---
async function loadWorkspaceTree(path = '.') {
    const container = document.getElementById('file-tree');
    if (!container) return;
    try {
        const res = await fetch(`/api/workspace/tree?path=${encodeURIComponent(path)}`);
        const data = await res.json();
        renderTree(data.entries || [], container, path === '.' ? '' : path);
    } catch (e) {
        console.error('Failed to load workspace tree', e);
    }
}

function renderTree(entries, container, basePath) {
    container.innerHTML = '';
    
    // Sort directories first
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
                let childContainer = item.nextElementSibling;
                if (childContainer && childContainer.classList.contains('tree-children')) {
                    childContainer.remove();
                } else {
                    const subRes = await fetch(`/api/workspace/tree?path=${encodeURIComponent(fullPath)}`);
                    const subData = await subRes.json();
                    childContainer = document.createElement('div');
                    childContainer.className = 'tree-children';
                    childContainer.style.paddingLeft = '12px';
                    renderTree(subData.entries || [], childContainer, fullPath);
                    item.after(childContainer);
                }
            } else {
                await openFile(fullPath, entry.name);
            }
        });
        container.appendChild(item);
    });
}

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

// --- Tabs & Editor Handling ---
async function openFile(path, name) {
    let file = state.openFiles.find(f => f.path === path);
    if (!file) {
        try {
            const res = await fetch(`/api/workspace/file?path=${encodeURIComponent(path)}`);
            const data = await res.json();
            file = {
                path,
                name,
                content: data.content || '',
                revision: data.revision || '',
                isDirty: false
            };
            state.openFiles.push(file);
        } catch (e) {
            console.error('Failed to load file', e);
            file = { path, name, content: `// Error loading ${name}`, isDirty: false };
            state.openFiles.push(file);
        }
    }
    state.activeFile = path;
    
    // Update Active File context badge
    const activeFileTag = document.getElementById('active-file-tag');
    if (activeFileTag) activeFileTag.textContent = `當前分頁: ${name}`;

    // Set Monaco Content
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
        const textarea = document.getElementById('basic-textarea');
        if (textarea) textarea.value = file.content;
    }
    renderTabs();
}

function renderTabs() {
    const tabsBar = document.getElementById('editor-tabs');
    if (!tabsBar) return;
    tabsBar.innerHTML = '';
    
    if (state.openFiles.length === 0) {
        tabsBar.innerHTML = '<div class="tab-placeholder">尚無開啟檔案</div>';
        return;
    }

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
        tabsBar.appendChild(tab);
    });
}

function closeFile(path) {
    state.openFiles = state.openFiles.filter(f => f.path !== path);
    if (state.activeFile === path) {
        state.activeFile = state.openFiles.length ? state.openFiles[0].path : null;
        if (state.activeFile) {
            const next = state.openFiles[0];
            openFile(next.path, next.name);
        } else if (state.editorInstance) {
            state.editorInstance.setValue('');
            const activeFileTag = document.getElementById('active-file-tag');
            if (activeFileTag) activeFileTag.textContent = '未選取檔案';
        }
    }
    renderTabs();
}

async function saveActiveFile() {
    if (!state.activeFile) {
        alert('請先在左側檔案樹選擇或新增檔案！');
        return;
    }
    const content = state.editorInstance ? state.editorInstance.getValue() : (document.getElementById('basic-textarea')?.value || '');
    try {
        const res = await fetch('/api/workspace/file/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: state.activeFile, content: content })
        });
        const data = await res.json();
        if (data.success) {
            const file = state.openFiles.find(f => f.path === state.activeFile);
            if (file) {
                file.isDirty = false;
                file.revision = data.revision;
                renderTabs();
            }
            appendTerminal(`[檔案已儲存] ${state.activeFile} (Revision: ${data.revision ? data.revision.slice(0, 16) : ''}...)`, 'sys');
        } else {
            alert('儲存失敗: ' + (data.error || '未知錯誤'));
        }
    } catch(e) {
        alert('儲存失敗: ' + e.message);
    }
}
window.saveActiveFile = saveActiveFile;

async function createNewFile() {
    const filename = prompt('請輸入新檔案名稱 (例如: src/index.js 或 demo.py):');
    if (!filename || !filename.trim()) return;
    const cleanPath = filename.trim();
    try {
        const res = await fetch('/api/workspace/file/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: cleanPath, content: '' })
        });
        const data = await res.json();
        if (data.success) {
            await loadWorkspaceTree();
            await openFile(cleanPath, cleanPath.split('/').pop());
            appendTerminal(`[檔案已建立] ${cleanPath}`, 'sys');
        } else {
            alert('建立失敗: ' + (data.error || '檔案可能已存在'));
        }
    } catch(e) {
        alert('建立失敗: ' + e.message);
    }
}
window.createNewFile = createNewFile;

// --- Terminal Console ---
function setupTerminal() {
    const input = document.getElementById('terminal-input');
    const clearBtn = document.getElementById('btn-term-clear');
    if (!input) return;

    input.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            const cmd = input.value.trim();
            if (!cmd) return;
            state.cmdHistory.push(cmd);
            state.cmdHistoryIndex = state.cmdHistory.length;
            input.value = '';
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
                    appendTerminal(`[處理程序結束，Exit Code: ${data.exit_code}]`, 'error');
                }
            } catch (err) {
                appendTerminal(`執行失敗: ${err.message}`, 'error');
            }
        } else if (e.key === 'ArrowUp') {
            if (state.cmdHistoryIndex > 0) {
                state.cmdHistoryIndex--;
                input.value = state.cmdHistory[state.cmdHistoryIndex] || '';
            }
        } else if (e.key === 'ArrowDown') {
            if (state.cmdHistoryIndex < state.cmdHistory.length - 1) {
                state.cmdHistoryIndex++;
                input.value = state.cmdHistory[state.cmdHistoryIndex] || '';
            } else {
                state.cmdHistoryIndex = state.cmdHistory.length;
                input.value = '';
            }
        }
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            const out = document.getElementById('terminal-output');
            if (out) out.innerHTML = '<div class="term-line sys">WebChat2Local Studio Terminal Cleared.</div>';
        });
    }
}

function appendTerminal(text, type = 'output') {
    const out = document.getElementById('terminal-output');
    if (!out) return;
    const line = document.createElement('div');
    line.className = `term-line ${type}`;
    line.textContent = text;
    out.appendChild(line);
    out.scrollTop = out.scrollHeight;
}

// --- Agent Chat & SSE Streaming ---
function setupAgentChat() {
    document.querySelectorAll('.mode-pill').forEach(pill => {
        pill.addEventListener('click', (e) => {
            document.querySelectorAll('.mode-pill').forEach(p => p.classList.remove('active'));
            e.target.classList.add('active');
            state.agentMode = e.target.dataset.mode;
        });
    });

    const sendBtn = document.getElementById('btn-send-agent');
    const promptInput = document.getElementById('chat-prompt-input');

    if (sendBtn) sendBtn.addEventListener('click', sendAgentMessage);
    if (promptInput) {
        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendAgentMessage();
            }
        });
    }
}

async function sendAgentMessage() {
    const promptInput = document.getElementById('chat-prompt-input');
    const text = promptInput.value.trim();
    if (!text) return;
    promptInput.value = '';
    
    appendChatMessage('user', text);
    
    // Ensure session
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
            console.error('Failed to create session', e);
        }
    }

    const agentMsg = appendChatMessage('agent', '思考中...');
    const msgTextEl = agentMsg.querySelector('.msg-text');

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
            msgTextEl.innerHTML = `<span style="color:var(--red);">[錯誤] 連線失敗 (${res.statusText})。請開啟 ChatGPT / Gemini / DeepSeek 網頁版。</span>`;
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let accumulated = '';
        msgTextEl.innerHTML = '';

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
                            msgTextEl.innerHTML = formatMarkdown(accumulated);
                        } else if (event.type === 'edit.proposed') {
                            appendToolCard('edit_file', event.proposal);
                            showDiffReviewBar(event.proposal);
                        } else if (event.type === 'tool.request') {
                            appendToolCard(event.tool, event.arguments);
                        } else if (event.type === 'terminal.output') {
                            appendTerminal(event.stdout || event.stderr || '');
                        } else if (event.type === 'agent.completed') {
                            if (event.summary && !accumulated) {
                                msgTextEl.innerHTML = formatMarkdown(event.summary);
                            }
                        }
                    } catch(e) {
                        if (dataStr) {
                            accumulated += dataStr;
                            msgTextEl.innerHTML = formatMarkdown(accumulated);
                        }
                    }
                }
            }
        }

        if (!msgTextEl.innerHTML) {
            msgTextEl.innerHTML = formatMarkdown(accumulated || '已收到回應。');
        }
    } catch(err) {
        msgTextEl.innerHTML = `<span style="color:var(--red);">連線異常: ${err.message}</span>`;
    }
}

function appendChatMessage(role, text) {
    const conv = document.getElementById('chat-conversation');
    if (!conv) return;
    const msg = document.createElement('div');
    msg.className = `chat-msg ${role}`;
    const avatar = role === 'user' ? '👤' : '🤖';
    msg.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-bubble">
            <div class="msg-text">${formatMarkdown(text)}</div>
        </div>
    `;
    conv.appendChild(msg);
    conv.scrollTop = conv.scrollHeight;
    return msg;
}

function formatMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    html = html.replace(/```([\s\S]*?)```/g, '<pre class="code-block"><code>$1</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code style="background:#27272a; padding:2px 4px; border-radius:3px;">$1</code>');
    html = html.replace(/\n/g, '<br/>');
    return html;
}

function appendToolCard(type, data) {
    const conv = document.getElementById('chat-conversation');
    if (!conv) return;
    const card = document.createElement('div');
    card.className = 'tool-card';
    
    let body = '', actions = '';
    const proposalId = data.proposal_id || ('prop_' + Math.random().toString(36).substr(2, 9));

    if (type === 'edit_file' || type === 'write_file') {
        const path = data.path || data.target || 'file.txt';
        const diff = data.diff || data.new_content || '';
        body = `<div>檔案: <code>${path}</code></div><pre class="code-block" style="max-height:100px; margin-top:4px;">${escapeHtml(diff)}</pre>`;
        actions = `
            <button class="btn btn-primary btn-sm" onclick="acceptProposal('${proposalId}')">批准套用 ✓</button>
            <button class="btn btn-secondary btn-sm" onclick="rejectProposal('${proposalId}')">捨棄 ✗</button>
        `;
    } else if (type === 'run_command') {
        const cmd = data.command || '';
        body = `<div>命令: <code>${cmd}</code></div>`;
        actions = `<button class="btn btn-secondary btn-sm" onclick="runInTerminal('${escapeHtml(cmd)}')">在終端執行 ▶</button>`;
    } else {
        body = `<div>${type}</div><pre class="code-block">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    }

    card.innerHTML = `
        <div class="tool-header">🛠️ ${type}</div>
        <div class="tool-body">${body}</div>
        <div class="tool-actions">${actions}</div>
    `;
    conv.appendChild(card);
    conv.scrollTop = conv.scrollHeight;
}

function showDiffReviewBar(proposal) {
    const bar = document.getElementById('diff-review-bar');
    const pathEl = document.getElementById('diff-target-file');
    if (!bar) return;
    state.pendingProposal = proposal;
    if (pathEl) pathEl.textContent = proposal.path || 'file.txt';
    bar.classList.remove('hidden');

    const acceptBtn = document.getElementById('btn-diff-accept');
    const rejectBtn = document.getElementById('btn-diff-reject');
    if (acceptBtn) acceptBtn.onclick = () => acceptProposal(proposal.proposal_id);
    if (rejectBtn) rejectBtn.onclick = () => rejectProposal(proposal.proposal_id);
}

window.acceptProposal = async (proposalId) => {
    try {
        const res = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/accept`, { method: 'POST' });
        const data = await res.json();
        alert(`提案 ${proposalId} 已成功寫入磁碟！`);
        const bar = document.getElementById('diff-review-bar');
        if (bar) bar.classList.add('hidden');
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
        const bar = document.getElementById('diff-review-bar');
        if (bar) bar.classList.add('hidden');
    } catch(e) {
        alert(`操作失敗: ${e.message}`);
    }
};

window.runInTerminal = (cmd) => {
    const input = document.getElementById('terminal-input');
    if (input) {
        input.value = cmd;
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    }
};

// --- Modals Setup ---
function setupModals() {
    // Open modal buttons
    const bindModal = (btnId, modalId) => {
        const btn = document.getElementById(btnId);
        const modal = document.getElementById(modalId);
        if (btn && modal) {
            btn.addEventListener('click', () => {
                modal.classList.remove('hidden');
                if (modalId === 'modal-settings') refreshSettingsModal();
            });
        }
    };
    bindModal('btn-docs', 'modal-docs');
    bindModal('btn-settings', 'modal-settings');

    // Close buttons
    document.querySelectorAll('.btn-close-modal').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetId = e.currentTarget.dataset.target;
            const modal = document.getElementById(targetId) || e.currentTarget.closest('.modal-overlay');
            if (modal) modal.classList.add('hidden');
        });
    });

    // Close on overlay background click
    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.add('hidden');
        });
    });

    // Docs tab switching
    document.querySelectorAll('.doc-tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.doc-tab-btn').forEach(b => b.classList.remove('active'));
            e.currentTarget.classList.add('active');
            
            const targetId = e.currentTarget.dataset.tab;
            document.querySelectorAll('.doc-pane').forEach(p => p.classList.remove('active'));
            const targetPane = document.getElementById(targetId);
            if (targetPane) targetPane.classList.add('active');
        });
    });

    // Recheck providers in settings
    const recheckBtn = document.getElementById('btn-recheck-providers');
    if (recheckBtn) recheckBtn.addEventListener('click', refreshSettingsModal);

    // Save settings
    const saveSettingsBtn = document.getElementById('btn-save-settings');
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', () => {
            const defaultMode = document.getElementById('setting-default-mode').value;
            state.agentMode = defaultMode;
            document.querySelectorAll('.mode-pill').forEach(pill => {
                pill.classList.toggle('active', pill.dataset.mode === defaultMode);
            });
            const modal = document.getElementById('modal-settings');
            if (modal) modal.classList.add('hidden');
            alert('設定已儲存！');
        });
    }
}

async function refreshSettingsModal() {
    try {
        const res = await fetch('/api/providers');
        const data = await res.json();
        const provs = data.providers || [];

        const updateBadge = (id, name) => {
            const badge = document.getElementById(id);
            if (!badge) return;
            const found = provs.find(p => p.name.toLowerCase().includes(name.toLowerCase()));
            if (found && found.active) {
                badge.className = 'badge connected';
                badge.textContent = '🟢 連線中 (Connected)';
            } else {
                badge.className = 'badge disconnected';
                badge.textContent = '🔴 離線 (Disconnected)';
            }
        };

        updateBadge('set-badge-chatgpt', 'chatgpt');
        updateBadge('set-badge-gemini', 'gemini');
        updateBadge('set-badge-deepseek', 'deepseek');

        // Header indicators
        const updateHeader = (id, name) => {
            const pill = document.getElementById(id);
            if (!pill) return;
            const found = provs.find(p => p.name.toLowerCase().includes(name.toLowerCase()));
            const dot = pill.querySelector('.dot');
            if (found && found.active) {
                pill.classList.add('active');
                if (dot) dot.className = 'dot online';
            } else {
                pill.classList.remove('active');
                if (dot) dot.className = 'dot';
            }
        };
        updateHeader('prov-chatgpt', 'chatgpt');
        updateHeader('prov-gemini', 'gemini');
        updateHeader('prov-deepseek', 'deepseek');
    } catch (e) {
        console.warn('Failed to refresh providers status', e);
    }
}

// --- App Initialization ---
window.addEventListener('DOMContentLoaded', () => {
    initMonaco();
    loadWorkspaceTree();
    setupTerminal();
    setupAgentChat();
    setupModals();
    refreshSettingsModal();

    const refreshTreeBtn = document.getElementById('btn-refresh-tree');
    if (refreshTreeBtn) refreshTreeBtn.addEventListener('click', () => loadWorkspaceTree());

    const newFileBtn = document.getElementById('btn-new-file');
    if (newFileBtn) newFileBtn.addEventListener('click', createNewFile);

    const saveFileBtn = document.getElementById('btn-save-file');
    if (saveFileBtn) saveFileBtn.addEventListener('click', saveActiveFile);

    // Global Ctrl+S keybinding
    window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            saveActiveFile();
        }
    });
});
