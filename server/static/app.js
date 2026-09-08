let isStreaming=false,lastLogs=[];const $=id=>document.getElementById(id);
function esc(s){
  const M={
    '&':String.fromCharCode(38)+'amp;',
    '<':String.fromCharCode(38)+'lt;',
    '>':String.fromCharCode(38)+'gt;',
    '"':String.fromCharCode(38)+'quot;',
    "'":String.fromCharCode(38)+'#39;'
  };
  return String(s??'').replace(/[&<>"']/g,c=>M[c]);
}
function relative(ts){if(!ts)return '—';const d=Math.max(0,Date.now()/1000-ts);return d<2?'剛剛':`${Math.round(d)} 秒前`;}

const MODE_LABEL={auto:'自動',direct:'直連 (Cookie)',extension:'Web 視窗'};

async function fetchTransport(){
  try{
    const r=await fetch('/v1/transport',{cache:'no-store'});
    if(!r.ok)throw 0;
    const d=await r.json();
    const sel=$('transportMode');
    if(sel.value!==d.mode)sel.value=d.mode;
    $('transportState').textContent=MODE_LABEL[d.mode]||d.mode;
    $('transportState').className=d.direct_configured||d.browser_connected?'green':'red';
    $('directState').textContent=d.direct_configured?'已設定':'未設定';
    $('directState').className=d.direct_configured?'green':'red';
    const hints=[];
    if(d.mode==='direct'&&!d.direct_configured)hints.push('直連模式需要 cookie：開啟 gemini.google.com 讓擴充套件自動同步，或手動設定 gemini_cookies.json。');
    if(d.mode==='extension'&&!d.browser_connected)hints.push('Web 視窗模式需要開啟 https://gemini.google.com 分頁。');
    if(d.mode==='auto'&&!d.direct_configured&&!d.browser_connected)hints.push('尚未有任何通道可用：開啟 gemini.google.com 或設定 cookie。');
    if(!hints.length)hints.push('目前模式：'+MODE_LABEL[d.mode]+'。Cookie 由擴充套件背景自動同步，Google 輪替 1PSIDTS 時不需手動更新。');
    $('modeMsg').textContent=hints.join(' ');
  }catch(e){
    $('modeMsg').textContent='無法讀取傳輸狀態（伺服器未啟動？）。';
  }
}

async function setTransportMode(){
  const mode=$('transportMode').value;
  try{
    const r=await fetch('/v1/transport',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})});
    if(!r.ok){const e=await r.json().catch(()=>({}));$('modeMsg').textContent=e.detail||'切換失敗。';return;}
    fetchTransport();
  }catch(e){$('modeMsg').textContent='切換失敗: '+e.message;}
}

async function fetchStatus(){
  try{
    const r=await fetch('/v1/status',{cache:'no-store'});
    if(!r.ok)throw 0;
    const d=await r.json(),b=d.browser_info||{},connected=!!d.browser_connected,s=$('status');
    s.className='status '+((connected||d.transport?.direct_configured)?(d.has_active_turn?'busy':'ok'):'bad');
    $('statusText').textContent=d.has_active_turn?'生成中':(connected?'Web Chat 已連線':(d.transport?.direct_configured?'直連就緒（Cookie）':'等待連線'));
    $('browserState').textContent=connected?'Connected':'Disconnected';
    $('browserState').className=connected?'green':'red';
    $('tabs').textContent=d.active_tabs??0;
    $('page').textContent=b.page_url||'—';
    $('lastSeen').textContent=relative(b.last_seen);
    if(d.transport){
      const t=d.transport;
      $('transportState').textContent=MODE_LABEL[t.mode]||t.mode;
      $('directState').textContent=t.direct_configured?'已設定':'未設定';
      $('directState').className=t.direct_configured?'green':'red';
    }
  }catch(e){
    $('status').className='status bad';$('statusText').textContent='本機服務無回應';
  }
}

async function fetchLogs(){
  try{
    const r=await fetch('/v1/logs?limit=80',{cache:'no-store'});
    if(!r.ok)return;
    const d=await r.json();lastLogs=d.logs||[];
    $('logContainer').innerHTML=lastLogs.length?lastLogs.map(x=>'<div class="event"><div class="meta">'+esc(x.time)+' · '+esc(x.level)+' · '+esc(x.source)+'</div><div class="msg">'+esc(x.message)+'</div>'+(Object.keys(x.details||{}).length?'<div class="detail">'+esc(JSON.stringify(x.details,null,2))+'</div>':'')+'</div>').join(''):'<div class="event"><div class="meta">尚無事件</div></div>';
    $('logContainer').scrollTop=$('logContainer').scrollHeight;
  }catch(e){}
}

async function fetchDoctor(){
  try{
    const r=await fetch('/v1/doctor',{cache:'no-store'});
    const d=await r.json();
    $('doctor').innerHTML=(d.checks||[]).map(c=>'<div style="padding:6px 0;border-bottom:1px solid #eef0f3"><b class="'+(c.status==='ok'?'green':c.status==='warning'?'amber':'red')+'">'+esc(c.message)+'</b><div>'+esc(c.detail||'')+'</div></div>').join('')||'目前沒有診斷項目。';
  }catch(e){$('doctor').textContent='診斷端點無法讀取。';}
}

async function sendDevPrompt(){
  if(isStreaming)return;
  const input=$('promptInput'),prompt=input.value.trim();
  if(!prompt)return;
  const model=$('modelSelect')?$('modelSelect').value:'webchat/auto';
  isStreaming=true;$('sendBtn').disabled=true;input.value='';
  const out=$('chatOutput');
  out.insertAdjacentHTML('beforeend','<div class="msg"><div class="role">YOU</div><div class="bubble user">'+esc(prompt)+'</div></div><div class="msg" id="current"><div class="role">GEMINI · '+esc(model)+'</div><div id="thinking" class="thinking" style="display:none"></div><div id="answer" class="bubble assistant"></div></div>');
  out.scrollTop=out.scrollHeight;
  const answer=$('answer'),thinking=$('thinking');
  let text='',thought='';
  const started=performance.now();
  try{
    const r=await fetch('/v1/dev/turn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt,model})});
    if(!r.ok){
      const e=await r.json().catch(()=>({}));
      answer.textContent='[錯誤] '+(e.detail||'請求失敗');
      return;
    }
    const transport=r.headers.get('X-W2L-Transport');
    if(transport){
      const roleEl=$('current').querySelector('.role');
      if(roleEl)roleEl.textContent='ASSISTANT · '+esc(model)+' · '+(MODE_LABEL[transport]||transport);
    }
    const reader=r.body.getReader(),dec=new TextDecoder();
    let buf='';
    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\n');buf=lines.pop()||'';
      for(const line of lines){
        if(!line.startsWith('data: ')||line.includes('[DONE]'))continue;
        try{
          const d=JSON.parse(line.slice(6)),delta=d.choices?.[0]?.delta;
          if(delta?.reasoning_content){thought+=delta.reasoning_content;thinking.style.display='block';thinking.textContent=thought;}
          if(delta?.content){text+=delta.content;answer.textContent=text;}
        }catch{}
      }
      out.scrollTop=out.scrollHeight;
    }
  }catch(e){answer.textContent='[連線異常] '+e.message;}
  finally{
    const ms=Math.round(performance.now()-started),cur=$('current');
    if(cur)cur.insertAdjacentHTML('beforeend','<div class="role">完成 · '+ms+' ms</div>');
    isStreaming=false;$('sendBtn').disabled=false;
    setTimeout(fetchLogs,100);setTimeout(fetchStatus,100);
  }
}

function copyEndpoint(){navigator.clipboard.writeText('http://127.0.0.1:8765/v1');alert('已複製端點 URL: http://127.0.0.1:8765/v1');}
function copyClientConfig(){
  const cfg = {
    apiProvider: "openai",
    openAiBaseUrl: "http://127.0.0.1:8765/v1",
    openAiApiKey: "sk-local",
    openAiModelId: "webchat/auto",
    customModelInfo: {
      supportsPromptCache: false,
      maxTokens: 4096,
      contextWindow: 32768,
      supportsThinking: true
    }
  };
  navigator.clipboard.writeText(JSON.stringify(cfg, null, 2));
  alert('已複製 Kilo / Cline 配置 JSON (Context Window: 32k, Max Tokens: 4k)！');
}
function copyLogs(){navigator.clipboard.writeText(lastLogs.map(x=>'['+x.time+'] ['+x.level+'] ['+x.source+'] '+x.message+(Object.keys(x.details||{}).length?' '+JSON.stringify(x.details):'')).join('\n'));}
function refreshAll(){fetchStatus();fetchLogs();fetchDoctor();fetchTransport();}

if($('transportMode'))$('transportMode').addEventListener('change',setTransportMode);
setInterval(fetchStatus,1500);
setInterval(fetchLogs,1200);
setInterval(fetchTransport,4000);
refreshAll();