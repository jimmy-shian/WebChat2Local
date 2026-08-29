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
        
        item.setAttribute('draggable', 'true');
        item.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('text/plain', '@' + fullPath);
            e.dataTransfer.setData('application/w2l-path', fullPath);
        });

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
    const file = state.openFiles.find(f => f.path === state.activeFile);
    if (!file) return;

    let targetPath = file.path;
    if (file.isVirtual) {
        const inputName = prompt('請輸入儲存路徑與檔案名稱 (例如: src/app.py 或 New.txt):', file.name);
        if (!inputName || !inputName.trim()) return;
        targetPath = inputName.trim();
        // Create file first
        await fetch('/api/workspace/file/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: targetPath, content: '' })
        });
        file.path = targetPath;
        file.name = targetPath.split('/').pop();
        file.isVirtual = false;
        state.activeFile = targetPath;
    }

    const content = state.editorInstance ? state.editorInstance.getValue() : (document.getElementById('basic-textarea')?.value || '');
    try {
        const res = await fetch('/api/workspace/file/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: targetPath, content: content })
        });
        const data = await res.json();
        if (data.success) {
            file.isDirty = false;
            file.revision = data.revision;
            file.content = content;
            renderTabs();
            await loadWorkspaceTree();
            appendTerminal(`[檔案已儲存] ${targetPath} (Revision: ${data.revision ? data.revision.slice(0, 16) : ''}...)`, 'sys');
        } else {
            alert('儲存失敗: ' + (data.error || '未知錯誤'));
        }
    } catch(e) {
        alert('儲存失敗: ' + e.message);
    }
}
window.saveActiveFile = saveActiveFile;

let untitledCounter = 1;
function createNewFile() {
    const virtualName = `未命名-${untitledCounter++}.txt`;
    const virtualFile = {
        path: virtualName,
        name: virtualName,
        content: '',
        revision: '',
        isDirty: true,
        isVirtual: true
    };
    state.openFiles.push(virtualFile);
    state.activeFile = virtualName;

    const activeFileTag = document.getElementById('active-file-tag');
    if (activeFileTag) activeFileTag.textContent = `當前分頁: ${virtualName}`;

    if (state.editorInstance && window.monaco) {
        const model = monaco.editor.createModel('', 'plaintext');
        state.editorInstance.setModel(model);
        state.editorInstance.focus();
    } else {
        const textarea = document.getElementById('basic-textarea');
        if (textarea) {
            textarea.value = '';
            textarea.focus();
        }
    }
    renderTabs();
    appendTerminal(`[建立虛擬佔位檔案] ${virtualName} (按 Ctrl+S 輸入名稱儲存)`, 'sys');
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
    const inputWrap = document.querySelector('.chat-input-wrapper');

    if (inputWrap && promptInput) {
        inputWrap.addEventListener('dragover', (e) => {
            e.preventDefault();
            inputWrap.style.borderColor = 'var(--accent)';
        });
        inputWrap.addEventListener('dragleave', (e) => {
            inputWrap.style.borderColor = 'var(--border)';
        });
        inputWrap.addEventListener('drop', (e) => {
            e.preventDefault();
            inputWrap.style.borderColor = 'var(--border)';
            const droppedPath = e.dataTransfer.getData('application/w2l-path') || e.dataTransfer.getData('text/plain');
            if (droppedPath) {
                const clean = droppedPath.startsWith('@') ? droppedPath : `@${droppedPath}`;
                promptInput.value = promptInput.value ? `${promptInput.value} ${clean}` : clean;
                promptInput.focus();
                const tag = document.getElementById('active-file-tag');
                if (tag) tag.textContent = `提及: ${clean}`;
            }
        });
    }

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

    const modelSelect = document.getElementById('chat-model-select');
    const selectedModel = modelSelect ? modelSelect.value : 'auto';

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
                model: selectedModel
            })
        });

        if (!res.ok) {
            msgTextEl.innerHTML = `<span style="color:var(--red);">[錯誤] 連線失敗 (${res.statusText})。請確認 Web Provider 已連線。</span>`;
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
                        } else if (event.type === 'tool.executed') {
                            appendToolCard('tool_executed', event);
                            if (event.tool === 'create_file' || event.tool === 'edit_file') {
                                await loadWorkspaceTree();
                                const p = event.arguments ? event.arguments.path : null;
                                if (p) await openFile(p, p.split('/').pop());
                            }
                        } else if (event.type === 'edit.proposed') {
                            appendToolCard(event.proposal.tool || 'edit_file', event.proposal);
                            showDiffReviewBar(event.proposal);
                        } else if (event.type === 'tool.request') {
                            appendToolCard(event.tool, event.arguments);
                        } else if (event.type === 'terminal.output') {
                            appendTerminal(event.stdout || event.stderr || '');
                        } else if (event.type === 'agent.completed') {
                            if (!accumulated && !msgTextEl.innerHTML) {
                                msgTextEl.innerHTML = formatMarkdown(event.summary || '已完成。');
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

        if (!msgTextEl.innerHTML && !accumulated) {
            msgTextEl.innerHTML = formatMarkdown('任務處理完成。');
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
    
    let header = '🛠️ 工具呼叫', body = '', actions = '';
    const proposalId = data.proposal_id || ('prop_' + Math.random().toString(36).substr(2, 9));

    if (type === 'tool_executed') {
        header = `✅ 工具執行成功: ${data.tool}`;
        const target = data.arguments ? (data.arguments.path || data.arguments.command) : '';
        body = `<div>目標: <code>${target}</code></div>`;
        if (data.arguments && data.arguments.content) {
            body += `<pre class="code-block" style="max-height:80px; margin-top:4px;">${escapeHtml(data.arguments.content)}</pre>`;
        }
    } else if (type === 'create_file' || type === 'edit_file' || type === 'write_file') {
        header = `📝 檔案修改提案: ${data.path || (data.arguments ? data.arguments.path : 'file')}`;
        const path = data.path || (data.arguments ? data.arguments.path : 'file.txt');
        const diff = data.diff || data.new_content || (data.arguments ? data.arguments.content : '');
        body = `<div>檔案: <code>${path}</code></div><pre class="code-block" style="max-height:100px; margin-top:4px;">${escapeHtml(diff)}</pre>`;
        actions = `
            <button class="btn btn-primary btn-sm" onclick="acceptProposal('${proposalId}')">批准套用 ✓</button>
            <button class="btn btn-secondary btn-sm" onclick="rejectProposal('${proposalId}')">捨棄 ✗</button>
        `;
    } else if (type === 'run_command') {
        header = `⚡ 終端命令請求`;
        const cmd = data.command || (data.arguments ? data.arguments.command : '');
        body = `<div>命令: <code>${cmd}</code></div>`;
        actions = `<button class="btn btn-secondary btn-sm" onclick="runInTerminal('${escapeHtml(cmd)}')">在終端執行 ▶</button>`;
    } else {
        body = `<div>${type}</div><pre class="code-block">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    }

    card.innerHTML = `
        <div class="tool-header">${header}</div>
        <div class="tool-body">${body}</div>
        ${actions ? `<div class="tool-actions">${actions}</div>` : ''}
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
    bar.style.display = 'flex';
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
        if (bar) {
            bar.style.display = 'none';
            bar.classList.add('hidden');
        }
        await loadWorkspaceTree();
        if (state.activeFile) await openFile(state.activeFile, state.activeFile.split('/').pop());
    } catch(e) {
        alert(`套用失敗: ${e.message}`);
    }
};

window.rejectProposal = async (proposalId) => {
    try {
        await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/reject`, { method: 'POST' });
        alert(`提案 ${proposalId} 已捨棄。`);
        const bar = document.getElementById('diff-review-bar');
        if (bar) {
            bar.style.display = 'none';
            bar.classList.add('hidden');
        }
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

    // Workspace Folder Modal Binding
    const wsBadge = document.getElementById('workspace-badge');
    const wsModal = document.getElementById('modal-workspace');
    const wsInput = document.getElementById('input-workspace-path');
    const wsSaveBtn = document.getElementById('btn-save-workspace');

    async function loadWorkspaceInfo() {
        try {
            const res = await fetch('/api/workspace/info');
            const data = await res.json();
            const wsPathEl = document.getElementById('workspace-path');
            if (wsPathEl && data.workspace_name) {
                wsPathEl.textContent = data.workspace_name;
            }
            if (wsInput && data.workspace_root) {
                wsInput.value = data.workspace_root;
            }
        } catch(e) {
            console.error('Failed to get workspace info', e);
        }
    }
    loadWorkspaceInfo();

    if (wsBadge && wsModal) {
        wsBadge.addEventListener('click', async () => {
            await loadWorkspaceInfo();
            wsModal.classList.remove('hidden');
        });
    }

    if (wsSaveBtn && wsInput) {
        wsSaveBtn.addEventListener('click', async () => {
            const newPath = wsInput.value.trim();
            if (!newPath) return;
            try {
                const res = await fetch('/api/workspace/set_root', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: newPath })
                });
                const data = await res.json();
                if (data.success) {
                    const wsPathEl = document.getElementById('workspace-path');
                    if (wsPathEl) wsPathEl.textContent = data.workspace_name;
                    wsModal.classList.add('hidden');
                    loadWorkspaceTree('.');
                }
            } catch(e) {
                alert('切換工作區失敗: ' + e);
            }
        });
    }

    const provMcp = document.getElementById('prov-mcp');
    if (provMcp) {
        provMcp.addEventListener('click', () => {
            const docsModal = document.getElementById('modal-docs');
            if (docsModal) {
                docsModal.classList.remove('hidden');
                document.querySelectorAll('.doc-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.doc-pane').forEach(p => p.classList.remove('active'));
                const mcpTab = document.querySelector('[data-tab="doc-tab-mcp"]');
                const mcpPane = document.getElementById('doc-tab-mcp');
                if (mcpTab) mcpTab.classList.add('active');
                if (mcpPane) mcpPane.classList.add('active');
            }
        });
    }

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
