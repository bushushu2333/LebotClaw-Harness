'use strict';
const $ = id => document.getElementById(id);
let token='', state={}, current=null, permission={mode:'plan'}, running=null, events=[], cursor=0, polling=false, sending=false;
let uiMode='chat', promoteFrom='';
let selectedFile='', fileContent='', sourceMode=false, previewUrl='', attachments=[], slot='chat';
let lastMessages='', latestFiles='', lastApprovals='', recorder=null, recordTimer=null, previewBlob='';
document.querySelector('.conversation').classList.add('empty-conversation');
const welcome=$('messages').innerHTML;
let sessionData=null, panelOpen=false, autoPreviewed='', noticeTimer=null, folderPath='', pendingGrantStart=false, checkedModel=false, viewingProject=false;
const toolLabels={files_list:'查看项目文件',file_read:'读取文件',file_write:'保存文件',file_patch:'修改文件',files_search:'搜索内容',file_info:'检查文件',image_generate:'生成图片',document_read:'阅读文档',document_create:'制作文档',browser_check:'打开浏览器检查作品',command_run:'运行项目命令'};
function activeModel(){return running?.model||state.active_model;}
function modelReady(){return !!state.model_health?.[activeModel()]?.ready;}
function isActive(){return !!running&&['running','queued'].includes(running.status);}
function showFiles(show=true){if(uiMode==='chat')show=false;panelOpen=show;localStorage.setItem('lebot-panel',show?'1':'0');$('artifacts').hidden=!show;$('workarea').classList.toggle('with-files',show);}
function applyMode(){
  document.body.classList.toggle('chat-mode',uiMode==='chat');
  $('mode-chat').classList.toggle('selected',uiMode==='chat');
  $('mode-work').classList.toggle('selected',uiMode==='work');
  $('mode-chat').setAttribute('aria-selected',uiMode==='chat'?'true':'false');
  $('mode-work').setAttribute('aria-selected',uiMode==='work'?'true':'false');
  if(uiMode==='chat')showFiles(false);
  updateComposer();
}
function updateComposer(){const ready=modelReady();$('send').disabled=sending||isActive()||!ready||(uiMode==='work'&&!current);$('prompt').placeholder=!ready?'先连接一个可用模型':uiMode==='chat'?'和超级小博聊聊，问问题、聊想法都可以……':!current?'先选择一个项目，再开始对话':permission.mode==='plan'?'告诉超级小博你的想法，先一起讨论和规划……':'告诉超级小博，你想完成什么……';$('project-button').textContent=current?'▱ '+(sessionData?.session.title||'当前项目'):'▱ 选择项目';$('setup-strip').hidden=!!current&&ready;$('setup-model').textContent=(ready?'✓':'1')+' 连接模型';$('setup-model').classList.toggle('done',ready);$('setup-project').textContent=(current?'✓':'2')+' 选择项目';$('setup-project').classList.toggle('done',!!current);$('setup-chat').textContent=uiMode==='chat'?'2 开始对话':'3 开始对话';$('activity').hidden=!running;$('record').hidden=!state.capabilities?.asr;}
const labels={queued:'等待开始',running:'超级小博正在工作',completed:'本轮已结束',cancelled:'已停止',interrupted:'上次运行中断，可以继续',failed:'运行遇到问题',incomplete:'达到预算，可以继续'};
const modes={plan:'Plan · 规划模式',ask:'逐次批准',auto:'自动执行',full:'不需要批准'};
const slotHints={chat:'必需 · 用于理解需求、编写代码和调用工具。DeepSeek、GLM 及提供兼容接口的 Kimi、Qwen 或中转站均可配置。',image:'推荐配置 · 制作游戏角色、场景和 PPT 插图。需提供兼容 images/generations 的生图服务；文字模型与生图模型可以来自不同平台。',asr:'可选 · 把录音转成文字。需提供兼容 audio/transcriptions 的服务。录音只在点击识别时发送到你配置的接口。',tts:'可选 · 朗读超级小博的回复。需提供兼容 audio/speech 的服务；点击播报才发起调用。'};
function el(tag,text,cls){const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;}
function inline(parent,text){
  for(const part of text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)){
    if(part.startsWith('**')&&part.endsWith('**'))parent.append(el('strong',part.slice(2,-2)));
    else if(part.startsWith('`')&&part.endsWith('`'))parent.append(el('code',part.slice(1,-1)));
    else parent.append(document.createTextNode(part));
  }
}
function markdown(text){
  const root=el('div',null,'body markdown'),lines=text.split('\n');let code=null,list=null;
  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    if(line.startsWith('```')){if(code){root.append(el('pre',code.join('\n')));code=null;}else code=[];list=null;continue;}
    if(code){code.push(line);continue;}
    if(line.trim().startsWith('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3}/.test(lines[i+1])){
      const table=el('table'),row=(str,tag)=>{const tr=el('tr');for(const cell of str.trim().replace(/^\||\|$/g,'').split('|')){const td=el(tag);inline(td,cell.trim());tr.append(td);}return tr;};
      table.append(row(line,'th'));i++;while(i+1<lines.length&&lines[i+1].trim().startsWith('|'))table.append(row(lines[++i],'td'));const wrap=el('div',null,'table-scroll');wrap.append(table);root.append(wrap);list=null;continue;
    }
    const heading=line.match(/^#{1,6}\s+(.+)/),bullet=line.match(/^\s*(?:[-*]|\d+\.)\s+(.+)/);
    if(heading){const h=el('h3');inline(h,heading[1]);root.append(h);list=null;}
    else if(bullet){if(!list){list=el('ul');root.append(list);}const li=el('li');inline(li,bullet[1]);list.append(li);}
    else{list=null;if(line.trim()){const p=el('p');inline(p,line);root.append(p);}}
  }
  if(code)root.append(el('pre',code.join('\n')));return root;
}
function notify(message){clearTimeout(noticeTimer);$('notice').textContent=message;$('notice').hidden=!message;if(message)noticeTimer=setTimeout(()=>{$('notice').hidden=true;},7000);}
async function api(path,body){const r=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{'X-Lebot-Token':token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'请求未完成');return data;}
function fileQuery(path){return 'session='+encodeURIComponent(current)+'&path='+encodeURIComponent(path);}
async function blobFile(path){const r=await fetch('/api/artifact?'+fileQuery(path),{headers:{'X-Lebot-Token':token}});if(!r.ok)throw Error((await r.json()).error);return r.blob();}
function drawState(){
  $('sessions').replaceChildren();$('mobile-sessions').replaceChildren();$('task-count').textContent=state.sessions.length;
  for(const s of state.sessions){const b=el('button',(s.kind==='chat'?'💬 ':'')+s.title,s.id===current?'selected':'');b.title=s.title+(s.workspace?'\n'+s.workspace:'\n聊天模式 · 不保存文件');b.onclick=()=>selectSession(s.id);$('sessions').append(b);const mobile=b.cloneNode(true);mobile.onclick=()=>{$('history-dialog').close();selectSession(s.id);};$('mobile-sessions').append(mobile);}
  const name=activeModel(),profile=state.models[name],health=state.model_health?.[name];
  $('model-button').textContent=profile?(health?.ready?'':'⚠ ')+profile.model+' ⌄':'连接模型';
  $('model-button').title=health?.message||'模型与能力设置';
  const old=$('existing-model').value;$('existing-model').replaceChildren(new Option('＋ 添加另一个模型',''));
  for(const name of Object.keys(state.models))$('existing-model').add(new Option(name,name));
  $('existing-model').value=old in state.models?old:'';
  updateComposer();
}
async function refreshState(){state=await api('state');drawState();}
function renderPermission(){
  $('mode-label').textContent=permission.mode==='plan'?'Plan · 先聊想法':modes[permission.mode];
  $('permission-summary').textContent=permission.mode==='plan'?'制作前需要授权':(permission.remember?'此项目已授权':'本轮有效，结束后回到 Plan');
  updateComposer();
}
function renderMessages(messages){
  document.querySelector('.conversation').classList.toggle('empty-conversation',!messages.length);const signature=JSON.stringify(messages);if(signature===lastMessages)return;lastMessages=signature;
  const nearBottom=$('chat-scroll').scrollHeight-$('chat-scroll').scrollTop-$('chat-scroll').clientHeight<160;
  $('messages').replaceChildren();if(!messages.length){$('messages').innerHTML=welcome;bindSuggestions();}
  for(const m of messages){
    const box=el('article',null,'message '+m.role);box.append(el('div',m.role==='user'?'我':'超级小博','byline'));
    const content=Array.isArray(m.content)?m.content.filter(c=>c.type==='text').map(c=>c.text).join('\n'):m.content;
    if(content)box.append(m.role==='assistant'?markdown(content):el('div',content,'body'));
    if(Array.isArray(m.content)&&m.content.some(c=>c.type==='image_url'))box.append(el('small','附有图片材料'));
    if(m.tool_calls?.length){box.classList.add('has-tools');box.append(el('small',m.tool_calls.map(c=>toolLabels[c.function.name]||c.function.name).join(' · '),'tool-summary'));}
    if(m.role==='assistant'&&content&&state.capabilities.tts){const b=el('button','播报','quiet');b.onclick=()=>speak(content,b);box.append(b);}
    $('messages').append(box);
  }
  if(nearBottom||messages.length<=2)$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight;
}
function eventTitle(e){
  let title=e.kind;
  if(e.kind==='tool.started')title=toolLabels[e.data.name]||e.data.name;
  else if(e.kind==='tool.finished')title=e.data.result.ok?'工具返回结果':'工具返回错误';
  else if(e.kind.startsWith('run.'))title=labels[e.kind.slice(4)]||e.kind;
  else if(e.kind==='approval.requested')title='等待批准：'+e.data.tool;
  else if(e.kind==='approval.decided')title=e.data.approved?'已批准操作':'已拒绝操作';
  else if(e.kind==='permission.changed')title='授权更新：'+modes[e.data.mode];
  else if(e.kind==='usage.estimated')title='服务商未返回用量，本轮使用估算控制预算';
  else if(e.kind==='media.request')title='发起第 '+e.data.attempt+' 次生图调用';
  return title;
}
function drawEvents(){
  $('events').replaceChildren();const visible=events.filter(e=>/^(tool\.|run\.|approval\.|permission\.|usage\.|media\.|recovery\.)/.test(e.kind));
  $('event-count').textContent=visible.length?visible.length+' 条记录':'查看工作记录';
  for(const e of visible.slice(-80)){
    const li=el('li');let title=eventTitle(e);
    li.append(el('span',title));const d=el('details');d.append(el('summary','详情'),el('pre',JSON.stringify(e.data,null,2)));li.append(d);$('events').append(li);
  }
}
function drawApprovals(items){
  const sig=JSON.stringify(items);if(sig===lastApprovals)return;lastApprovals=sig;$('approvals').replaceChildren();
  for(const a of items){const card=el('section',null,'approval-card');card.append(el('b','需要你批准 · '+(toolLabels[a.tool]||a.tool)));if(a.arguments.path)card.append(el('p','文件：'+a.arguments.path));if(a.arguments.prompt)card.append(el('p',a.arguments.prompt.slice(0,240)));if(a.arguments.command)card.append(el('pre',a.arguments.command));
    if(a.tool==='image_generate')card.append(el('p','将调用 '+(state.capabilities.image||'生图服务')+'；按服务商规则计费，具体金额以服务商账单为准。'));
    const d=el('details');d.open=false;d.append(el('summary','查看完整操作'),el('pre',JSON.stringify(a.arguments,null,2)));card.append(d);
    const actions=el('div',null,'dialog-actions');for(const [label,approved] of [['拒绝',false],['批准此操作',true]]){const b=el('button',label,approved?'primary':'quiet');b.onclick=async()=>{try{b.disabled=true;await api('approval',{id:a.id,approved});await loadSession();}catch(e){notify(e.message);b.disabled=false;}};actions.append(b);}card.append(actions);$('approvals').append(card);
  }
}
async function loadSession(){
  if(!current||polling)return;polling=true;const sid=current,scroller=$('chat-scroll'),firstRender=!lastMessages,stickToEnd=scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<160;
  try{const data=await api('session?id='+encodeURIComponent(sid)+'&after='+cursor);if(sid!==current)return;
    sessionData=data;$('task-title').textContent=data.session.title;$('workspace').textContent=data.session.workspace;
    if(data.session.kind==='chat'){$('project-location').textContent='聊天模式 · 对话不保存文件';$('project-location').title='聊天模式只对话；开始制作后才有项目文件。';}
    else{$('project-location').textContent='项目 · '+data.session.workspace.split('/').pop();$('project-location').title=data.session.workspace;}
    $('convert-bar').hidden=!(data.session.kind==='chat'&&data.messages.length&&!isActive());
    permission=data.permission;running=data.session.last_run;renderPermission();$('stop').hidden=!isActive();
    $('run-status').textContent=data.approvals.length?'等待批准':running?(labels[running.status]||running.status):'准备开始';
    $('usage').textContent=running&&running.tokens?'本轮 '+running.tokens.toLocaleString()+' token':'';
    renderMessages(data.messages);drawApprovals(data.approvals);
    if(data.events.length){events.push(...data.events);cursor=data.events.at(-1).seq;drawEvents();
      if(data.events.some(e=>e.kind==='tool.finished'&&e.data.result?.ok&&['file_write','file_patch','document_create','image_generate'].includes(toolName(e))))hotReload();
      if(panelTab==='work'){drawDiff();drawTerm();drawLog();}}
    const signature=JSON.stringify(data.files);$('file-count').textContent=data.files.length+' 个文件';$('files-button').hidden=!current;$('files-button').textContent='项目文件'+(data.files.length?' · '+data.files.length:'');
    if(signature!==latestFiles){latestFiles=signature;drawFiles(data.files);workFiles=data.files;if(panelTab==='work')drawTree(data.files);}if(!data.files.length&&!selectedFile)$('preview').replaceChildren(el('div',permission.read?'项目中还没有文件。授权制作后，生成的作品会出现在这里。':'查看本项目文件需要只读授权。','empty'));
    if(!selectedFile&&panelOpen&&data.files.length){const saved=localStorage.getItem('lebot-file-'+sid);if(saved&&data.files.includes(saved))openFile(saved);}
    $('live').hidden=!isActive()||!!data.approvals.length;
    const latest=events.filter(e=>e.run_id===running?.id).at(-1),tool=latest?.kind==='tool.started'?latest.data.name:null;
    $('live-status').textContent=tool?(toolLabels[tool]||tool)+'…':data.live?.text?'正在回复…':'正在思考…';
    const nearBottom=$('chat-scroll').scrollHeight-$('chat-scroll').scrollTop-$('chat-scroll').clientHeight<160;
    $('live-text').replaceChildren(data.live?.text?markdown(data.live.text):el('span','● ● ●','thinking'));
    if(isActive()&&nearBottom)$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight;
    const failed=running&&['failed','incomplete','interrupted'].includes(running.status);$('run-error').hidden=!failed;
    if(failed){const reason=events.filter(e=>e.run_id===running.id&&e.kind==='run.'+running.status).at(-1);$('error-heading').textContent=running.status==='failed'?'这次没有完成':'任务已暂停';$('error-detail').textContent=reason?.data.message||'运行中断，已保存的文件仍在。可以继续刚才的需求。';$('retry').textContent=permission.mode==='plan'?'在 Plan 中重试':'继续刚才的需求';}
    if(!permission.read&&selectedFile)resetPreview();
    renderNextAction(data);drawModelLabel();if(firstRender||stickToEnd)requestAnimationFrame(()=>{if(current===sid)scroller.scrollTop=scroller.scrollHeight;});
  }catch(e){notify(e.message);}finally{polling=false;}
}
function drawModelLabel(){const name=activeModel();$('model-button').textContent=(modelReady()?'':'⚠ ')+(state.models[name]?.model||'连接模型')+' ⌄';}
function renderNextAction(data){
  const node=$('next-action');node.hidden=true;if(isActive())return;
  let title='',desc='',label='',action=null;
  if(!modelReady()){title='先修复模型连接';desc=state.model_health?.[activeModel()]?.message||'输入 API Key 并测试连接后，就可以继续。';label='连接模型';action=()=>openModels();}
  else if(data.files.length){title='项目中已有 '+data.files.length+' 个文件';desc='打开文件查看实际成果；需要调整时，直接在下方告诉超级小博。';label='查看作品';action=()=>{showFiles();const entry=data.files.find(f=>f==='index.html')||data.files.find(f=>/\.html?$/i.test(f))||data.files[0];openFile(entry);};
    if(running?.status==='completed'&&autoPreviewed!==running.id){autoPreviewed=running.id;action();}
  }else if(running?.status==='completed'&&permission.mode==='plan'){title='准备动手时，再授权制作';desc='目前是 Plan，只会对话和规划。授权后，超级小博才能把想法做成本地文件。';label='授权并继续';action=()=>openGrant(true);}
  if(!action)return;node.hidden=false;$('next-heading').textContent=title;$('next-description').textContent=desc;$('next-button').textContent=label;$('next-button').onclick=action;
}
function drawFiles(files){$('files').replaceChildren();for(const f of files){const b=el('button',f,f===selectedFile?'selected':'');b.title=f;b.onclick=()=>openFile(f);$('files').append(b);}}
function resetPreview(){selectedFile='';fileContent='';previewUrl='';if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('preview').replaceChildren(el('div','选择项目文件，查看内容或运行作品。','empty'));$('filename').textContent='作品预览';$('preview-toggle').hidden=true;$('open-preview').hidden=true;$('device-switch').hidden=true;$('download').hidden=true;}
async function selectSession(id){
  if(id===current)return;current=id;localStorage.setItem('lebot-session',id);events=[];cursor=0;lastMessages='';latestFiles='';lastApprovals='';running=null;permission={mode:'plan'};
  const meta=state.sessions.find(s=>s.id===id);uiMode=meta?.kind==='chat'?'chat':'work';applyMode();
  sessionData=null;showFiles(localStorage.getItem('lebot-panel')==='1');autoPreviewed='';resetPreview();workFile='';workFiles=[];if(workBlob){URL.revokeObjectURL(workBlob);workBlob='';}$('work-code').replaceChildren();$('activity').open=false;$('approvals').replaceChildren();$('run-error').hidden=true;$('next-action').hidden=true;$('convert-bar').hidden=true;notify('');drawState();renderPermission();await loadSession();
}
async function newChat(){
  current=null;localStorage.removeItem('lebot-session');events=[];cursor=0;lastMessages='';latestFiles='';lastApprovals='';running=null;permission={mode:'plan'};sessionData=null;
  uiMode='chat';applyMode();resetPreview();$('task-title').textContent='新对话';$('project-location').textContent='聊天模式 · 对话不保存文件';$('activity').hidden=true;$('approvals').replaceChildren();$('run-error').hidden=true;$('next-action').hidden=true;$('convert-bar').hidden=true;notify('');renderMessages([]);drawState();renderPermission();$('prompt').focus();
}
function setMode(mode){
  if(mode===uiMode&&current)return;
  if(mode==='chat'){
    const latest=state.sessions.find(s=>s.kind==='chat');
    if(latest&&latest.id!==current)selectSession(latest.id);
    else if(!latest)newChat();
  }else{
    if(sessionData?.session.kind==='chat'||!current)openTask(!!current);
    else{const latest=state.sessions.find(s=>s.kind!=='chat');if(latest&&latest.id!==current)selectSession(latest.id);else if(!latest)openTask();}
  }
}
$('mode-chat').onclick=()=>setMode('chat');
$('mode-work').onclick=()=>setMode('work');
async function openFile(file){
  showFiles(true);selectedFile=file;sourceMode=false;$('open-preview').hidden=true;$('device-switch').hidden=true;const sid=current;localStorage.setItem('lebot-file-'+sid,file);$('filename').textContent=file;$('download').hidden=false;$('preview').replaceChildren(el('div','正在读取作品……','empty'));
  try{
    if(/\.html?$/i.test(file)){const result=await api('preview?'+fileQuery(file));if(current!==sid||selectedFile!==file)return;previewUrl=result.url;fileContent='';renderPreview();}
    else if(/\.(png|jpe?g|webp|gif)$/i.test(file)){const blob=await blobFile(file);if(current!==sid||selectedFile!==file)return;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob=URL.createObjectURL(blob);const im=el('img');im.src=previewBlob;im.alt=file;$('preview').replaceChildren(im);$('preview-toggle').hidden=true;}
    else if(/\.(pptx|docx|pdf|zip|mp3|wav|xlsx)$/i.test(file)){$('preview').replaceChildren(el('div','已保存在项目目录中。点击“下载”，即可用对应应用打开。','empty'));$('preview-toggle').hidden=true;}
    else {const r=await api('file?'+fileQuery(file));if(current!==sid||selectedFile!==file)return;fileContent=r.content;renderPreview();}
    for(const b of $('files').children)b.classList.toggle('selected',b.textContent===file);
  }catch(e){notify(e.message);$('preview').replaceChildren(el('div',e.message,'empty'));}
}
function renderPreview(){
  const html=/\.html?$/i.test(selectedFile),md=/\.(md|markdown)$/i.test(selectedFile);
  $('preview-toggle').hidden=!(html||md);$('open-preview').hidden=!html;$('open-preview').href=previewUrl;
  $('preview-toggle').textContent=html?(sourceMode?'运行作品':'查看源文件'):(sourceMode?'渲染视图':'查看源文件');
  $('device-switch').hidden=!(html&&!sourceMode);
  $('preview').replaceChildren();
  if(md&&!sourceMode){const view=markdown(fileContent);view.classList.add('doc-view');$('preview').append(view);return;}
  if(!html||sourceMode){$('preview').append(codeView(fileContent,selectedFile));return;}
  const wrap=el('div',null,'frame-wrap dev-'+deviceFrame);
  const frame=el('iframe');frame.title='项目作品预览';frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-forms allow-downloads allow-modals');frame.referrerPolicy='no-referrer';frame.src=previewUrl;
  wrap.append(frame);$('preview').append(wrap);
}
let deviceFrame='desktop';
for(const b of document.querySelectorAll('#device-switch button'))b.onclick=()=>{deviceFrame=b.dataset.dev;for(const x of document.querySelectorAll('#device-switch button'))x.classList.toggle('selected',x===b);const w=$('preview').querySelector('.frame-wrap');if(w)w.className='frame-wrap dev-'+deviceFrame;};

/* 轻量代码视图：行号 + 语法高亮（无外部依赖，符合 CSP self 限制） */
const CODE_KEYWORDS={js:'const let var function return if else for while class new async await import export from try catch throw typeof of in switch case break continue this null true false undefined',py:'def return if elif else for while class import from as try except raise with lambda pass break continue True False None and or not in is global nonlocal yield assert async await',css:'import media supports keyframes font-face important'};
const CODE_ALIAS={mjs:'js',ts:'js',jsx:'js',tsx:'js',vue:'js',java:'js',c:'js',cpp:'js',h:'js',yml:'py',yaml:'py',toml:'py',ini:'py',cfg:'py',sh:'py',bash:'py',zsh:'py',rb:'py',lua:'py',pl:'py'};
function highlightLine(line,ext){
  ext=CODE_ALIAS[ext]||ext;
  const words=CODE_KEYWORDS[ext],frag=document.createDocumentFragment();let rest=line,guard=0;
  const pat=ext==='py'?/^#[^\n]*/:ext==='html'?/^<!--[^\n]*/:/^\/\/[^\n]*/;
  while(rest&&guard++<60){
    const comment=rest.match(pat),str=rest.match(/^('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`)/),num=rest.match(/^\d+(?:\.\d+)?\b/),word=rest.match(/^[A-Za-z_$][\w$]*/),tag=ext==='html'&&rest.match(/^<\/?[a-zA-Z][\w-]*|^\/?>/);
    let node=null,eat=0;
    if(comment&&comment[0]){node=el('span',comment[0],'tok-com');eat=comment[0].length;}
    else if(str){node=el('span',str[0],'tok-str');eat=str[0].length;}
    else if(tag){node=el('span',tag[0],'tok-kw');eat=tag[0].length;}
    else if(num){node=el('span',num[0],'tok-num');eat=num[0].length;}
    else if(word){node=el('span',word[0],words&&new RegExp('\\b'+word[0].replace(/\$/g,'\\$')+'\\b').test(words)?'tok-kw':null);eat=word[0].length;}
    else{node=document.createTextNode(rest[0]);eat=1;}
    frag.append(node);rest=rest.slice(eat);
  }
  if(rest)frag.append(document.createTextNode(rest));
  return frag;
}
function codeView(text,file){
  const ext=(file.split('.').pop()||'').toLowerCase(),box=el('div',null,'code-view'),lines=text.split('\n');
  const shown=lines.slice(0,4000);
  for(let i=0;i<shown.length;i++){
    const row=el('div',null,'code-line');
    row.append(el('span',String(i+1),'ln'));
    const lc=el('span',null,'lc');lc.append(highlightLine(shown[i],ext));row.append(lc);box.append(row);
  }
  if(lines.length>shown.length)box.append(el('div','…… 其余 '+(lines.length-shown.length)+' 行从略，请下载查看完整文件。','code-more'));
  return box;
}
function toolName(e){if(e.kind==='tool.started')return e.data.name;return events.find(x=>x.kind==='tool.started'&&x.data.action_id===e.data.action_id)?.data.name;}
function hotReload(){
  if(!selectedFile||!panelOpen)return;
  if(/\.html?$/i.test(selectedFile)&&!sourceMode){const f=$('preview').querySelector('iframe');if(f)f.src=f.src;}
  else openFile(selectedFile);
}

/* ===== 工作台（R4）：文件树 / 代码 / Diff / 终端 / 运行记录 ===== */
let panelTab='preview',workFile='',workFiles=[],workBlob='';
function setPanelTab(tab){
  panelTab=tab;localStorage.setItem('lebot-panel-tab',tab);
  $('tab-preview').classList.toggle('selected',tab==='preview');$('tab-work').classList.toggle('selected',tab==='work');
  $('tab-preview').setAttribute('aria-selected',tab==='preview'?'true':'false');$('tab-work').setAttribute('aria-selected',tab==='work'?'true':'false');
  $('panel-preview').hidden=tab!=='preview';$('panel-work').hidden=tab!=='work';
  if(tab==='work'){drawTree(workFiles);drawDiff();drawTerm();drawLog();}
}
$('tab-preview').onclick=()=>setPanelTab('preview');
$('tab-work').onclick=()=>setPanelTab('work');
function setWtab(name){
  for(const b of document.querySelectorAll('.work-tabs button'))b.classList.toggle('selected',b.dataset.wtab===name);
  for(const p of document.querySelectorAll('.work-page'))p.hidden=p.id!=='work-'+name;
}
for(const b of document.querySelectorAll('.work-tabs button'))b.onclick=()=>setWtab(b.dataset.wtab);

const TREE_ICON={html:'🌐',htm:'🌐',js:'📜',css:'🎨',py:'🐍',json:'🧾',md:'📝',txt:'📝',csv:'🧾',png:'🖼',jpg:'🖼',jpeg:'🖼',webp:'🖼',gif:'🖼',svg:'🖼',mp3:'🎵',pptx:'📊',docx:'📄',pdf:'📕',zip:'📦'};
function drawTree(files){
  const root={dirs:new Map(),files:[]};
  for(const f of files){const parts=f.split('/');let node=root;
    for(let i=0;i<parts.length-1;i++){if(!node.dirs.has(parts[i]))node.dirs.set(parts[i],{dirs:new Map(),files:[]});node=node.dirs.get(parts[i]);}
    node.files.push({name:parts[parts.length-1],path:f});}
  const box=$('file-tree');box.replaceChildren();
  if(!files.length){box.append(el('div','项目中还没有文件。','tree-empty'));return;}
  const addNode=(parent,node,depth)=>{
    for(const [name,dir] of [...node.dirs.entries()].sort((a,b)=>a[0].localeCompare(b[0]))){
      const d=el('details');d.open=depth<1;const s=el('summary','📁 '+name);s.style.paddingLeft=(8+depth*14)+'px';d.append(s);
      const inner=el('div');addNode(inner,dir,depth+1);d.append(inner);parent.append(d);}
    for(const f of node.files.sort((a,b)=>a.name.localeCompare(b.name))){
      const ext=f.name.includes('.')?f.name.split('.').pop().toLowerCase():'';
      const b=el('button',(TREE_ICON[ext]||'📄')+' '+f.name,f.path===workFile?'selected':'');
      b.type='button';b.style.paddingLeft=(8+depth*14+20)+'px';b.title=f.path;b.onclick=()=>openWorkFile(f.path);parent.append(b);}};
  addNode(box,root,0);
}
async function openWorkFile(path){
  workFile=path;setWtab('code');drawTree(workFiles);
  const pane=$('work-code');pane.replaceChildren(el('div','正在读取……','empty'));
  try{
    if(/\.(png|jpe?g|webp|gif)$/i.test(path)){
      const blob=await blobFile(path);if(workFile!==path)return;
      if(workBlob)URL.revokeObjectURL(workBlob);workBlob=URL.createObjectURL(blob);
      const im=el('img');im.src=workBlob;im.alt=path;pane.replaceChildren(im);return;}
    if(/\.(pptx|docx|pdf|zip|mp3|wav|xlsx)$/i.test(path)){pane.replaceChildren(el('div','二进制文件：请切到「预览」页签下载，或用对应应用打开。','empty'));return;}
    const r=await api('file?'+fileQuery(path));if(workFile!==path)return;
    pane.replaceChildren(codeView(r.content,path));
  }catch(e){pane.replaceChildren(el('div',e.message,'empty'));}
}
function diffLine(sign,text){const row=el('div',null,sign==='+'?'diff-add':'diff-del');row.textContent=sign+' '+text;return row;}
function drawDiff(){
  const pane=$('work-diff');pane.replaceChildren();
  const patches=events.filter(e=>e.kind==='tool.started'&&(e.data.name==='file_patch'||e.data.name==='file_write')&&e.data.arguments?.path);
  if(!patches.length){pane.append(el('div','还没有文件修改记录；小博开始制作后，这里会显示每处改动。','empty'));return;}
  patches.slice().reverse().forEach((e,i)=>{
    const a=e.data.arguments,card=el('details',null,'diff-card');card.open=i===0;
    card.append(el('summary',(e.data.name==='file_patch'?'✏️ 修改  ':'📄 新建  ')+a.path));
    const body=el('div',null,'diff-body');
    if(e.data.name==='file_write'){
      for(const line of String(a.content??'').split('\n').slice(0,300))body.append(diffLine('+',line));
      if(String(a.content??'').split('\n').length>300)body.append(el('div','…… 内容较长，其余从略。','diff-dim'));
    }else{
      body.append(el('div','修改前：','diff-dim'));
      for(const line of String(a.old??'').split('\n').slice(0,120))body.append(diffLine('-',line));
      body.append(el('div','修改后：','diff-dim'));
      for(const line of String(a.new??'').split('\n').slice(0,120))body.append(diffLine('+',line));
    }
    card.append(body);pane.append(card);
  });
}
function drawTerm(){
  const pane=$('work-term');pane.replaceChildren();
  const runs=events.filter(e=>e.kind==='tool.started'&&e.data.name==='command_run');
  if(!runs.length){pane.append(el('div','还没有运行过命令；小博检查作品、安装依赖时，输出会显示在这里。','empty'));return;}
  for(const s of runs){
    const fin=events.find(e=>e.kind==='tool.finished'&&e.data.action_id===s.data.action_id);
    const block=el('div',null,'term-block');
    block.append(el('div','$ '+(s.data.arguments?.argv||[]).join(' '),'term-cmd'));
    const r=fin?.data.result;
    if(!fin)block.append(el('div','（等待结果……）','term-dim'));
    else{
      const trim=t=>{const lines=String(t).split('\n');return lines.length>200?'……（前面从略）\n'+lines.slice(-200).join('\n'):String(t);};
      if(r.stdout)block.append(el('pre',trim(r.stdout),'term-out'));
      if(r.stderr)block.append(el('pre',trim(r.stderr),'term-err'));
      block.append(el('div','退出码 '+r.exit_code+(r.timed_out?' · 已超时':''),r.exit_code===0?'term-ok':'term-bad'));}
    pane.append(block);}
  pane.scrollTop=pane.scrollHeight;
}
function drawLog(){
  const pane=$('work-log');pane.replaceChildren();
  const visible=events.filter(e=>/^(tool\.|run\.|approval\.|permission\.|usage\.|media\.|recovery\.)/.test(e.kind));
  if(!visible.length){pane.append(el('div','还没有运行记录。','empty'));return;}
  for(const e of visible.slice(-100)){
    const row=el('div',null,'log-row');
    row.append(el('span',eventTitle(e),'log-title'));
    const d=el('details');d.append(el('summary','详情'),el('pre',JSON.stringify(e.data,null,2)));row.append(d);
    pane.append(row);}
}
$('download-project').onclick=async()=>{try{const r=await fetch('/api/project.zip?session='+encodeURIComponent(current),{headers:{'X-Lebot-Token':token}});if(!r.ok)throw Error((await r.json()).error);const url=URL.createObjectURL(await r.blob()),a=el('a');a.href=url;a.download=(sessionData.session.title||'项目')+'.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);notify('项目已打包下载，包含网页与图片等资源。');}catch(e){notify(e.message);}};
$('preview-toggle').onclick=async()=>{try{if(!sourceMode)fileContent=(await api('file?'+fileQuery(selectedFile))).content;sourceMode=!sourceMode;renderPreview();}catch(e){notify(e.message);}};
$('download').onclick=async()=>{try{const blob=await blobFile(selectedFile),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=selectedFile.split('/').pop();a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){notify(e.message);}};
function openModels(kind='chat'){slot=kind;$('model-error').classList.remove('success');$('model-error').textContent='';setSlot();if(!$('model-dialog').open)$('model-dialog').showModal();}
function setSlot(){
  document.querySelectorAll('[data-slot]').forEach(b=>{b.classList.toggle('selected',b.dataset.slot===slot);b.setAttribute('aria-selected',b.dataset.slot===slot?'true':'false');});
  $('model-save').hidden=false;$('model-continue').hidden=true;$('model-save').textContent=slot==='chat'?'保存并测试连接':'保存此能力';$('slot-hint').textContent=slotHints[slot];$('chat-options').hidden=slot!=='chat';$('image-options').hidden=slot!=='image';$('tts-options').hidden=slot!=='tts';$('model-test').hidden=true;$('disable-capability').hidden=slot==='chat';
  $('existing-model').value=slot==='chat'?(activeModel()||''):(state.capabilities[slot]||'');fillModel();
}
function fillModel(){const name=$('existing-model').value,p=state.models[name],options=state.media_options[slot]||{};
  $('model-name').value=name;$('provider').value=p?.provider||(slot==='chat'?'deepseek':'openai-compatible');$('model-id').value=p?.model||'';$('base-url').value=p?.base_url||'';$('key-env').value=p?.key_env||'';$('vision').checked=!!p?.vision;$('api-key').value='';$('save-key').checked=false;$('output-tokens').value=p?.max_output_tokens||8192;$('reasoning').value=p?.reasoning_effort||'';$('image-protocol').value=options.protocol||'openai';$('image-size').value=options.size||'';$('image-quality').value=options.quality||'';$('image-format').value=options.response_format||'';$('voice').value=options.voice||'';if(!p)applyProvider();$('config-name-label').hidden=true;$('existing-model').parentElement.hidden=!Object.keys(state.models).length;
}
for(const b of document.querySelectorAll('[data-slot]'))b.onclick=()=>{slot=b.dataset.slot;$('model-error').textContent='';setSlot();};
$('existing-model').onchange=fillModel;$('settings').onclick=()=>openModels();$('model-button').onclick=()=>openModels();$('provider').onchange=applyProvider;
function applyProvider(){const kind=$('provider').value;$('base-url').value=kind==='glm'?'https://open.bigmodel.cn/api/paas/v4':kind==='deepseek'?'https://api.deepseek.com/v1':'';if(!$('existing-model').value){let name=kind+'-'+slot,n=2;while(state.models[name])name=kind+'-'+slot+'-'+n++;$('model-name').value=name;$('model-id').value='';}$('model-id').placeholder=kind==='glm'?'例如 glm-5.3，按服务商填写':kind==='deepseek'?'填写你要使用的 DeepSeek 模型 ID':'服务商提供的模型 ID';}
for(const b of document.querySelectorAll('dialog .close'))b.onclick=()=>b.closest('dialog').close();
$('model-form').addEventListener('input',()=>{$('model-continue').hidden=true;$('model-save').hidden=false;$('model-error').textContent='';$('model-error').classList.remove('success');});
$('model-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{
  const options=slot==='image'?{protocol:$('image-protocol').value,size:$('image-size').value,quality:$('image-quality').value,response_format:$('image-format').value}:slot==='tts'?{voice:$('voice').value}:{};
  const result=await api('model',{slot,name:$('model-name').value,provider:$('provider').value,model:$('model-id').value,base_url:$('base-url').value,key:$('api-key').value,save_key:$('save-key').checked,key_env:$('key-env').value,vision:$('vision').checked,max_output_tokens:Number($('output-tokens').value),reasoning_effort:$('reasoning').value,options});
  $('api-key').value='';$('save-key').checked=false;await refreshState();setSlot();lastMessages='';if(slot==='chat')await testModel();else{$('model-error').textContent='已保存，可以回到对话使用。';$('model-continue').textContent='返回对话';$('model-continue').hidden=false;}
}catch(error){$('model-error').classList.remove('success');$('model-error').textContent=error.message;}finally{b.disabled=false;}};
async function testModel(){const b=$('model-test');b.disabled=true;$('model-error').textContent='正在验证对话和工具调用，请稍候…';try{const r=await api('model/test',{name:$('existing-model').value||state.active_model});checkedModel=true;await refreshState();$('model-error').textContent=r.tool_call?'连接成功 · 对话、工具调用均可用。':'对话连接成功，但未通过工具调用检查，请确认模型支持工具调用。';$('model-error').classList.toggle('success',r.tool_call);$('model-continue').hidden=!r.tool_call;$('model-continue').textContent=current?'返回项目，继续对话':'继续 → 选择项目';$('model-save').hidden=r.tool_call;}catch(e){$('model-error').classList.remove('success');$('model-error').textContent=e.message;}finally{b.disabled=false;}}
$('model-test').onclick=testModel;
$('model-continue').onclick=()=>{$('model-dialog').close();if(!current)openTask();else{loadSession();$('prompt').focus();}};

$('disable-capability').onclick=async()=>{try{await api('capability/disable',{slot});await refreshState();setSlot();$('model-error').textContent='已停用此可选能力。';}catch(e){$('model-error').textContent=e.message;}};
function openTask(promote=false){if(!modelReady()){openModels();return;}promoteFrom=promote&&current&&sessionData?.session.kind==='chat'?current:'';if(promoteFrom)$('new-title').value=sessionData.session.title.replace(/^💬\s*/,'').slice(0,60);$('task-error').textContent='';$('task-dialog').showModal();}
$('convert-start').onclick=()=>openTask(true);
$('new-task').onclick=()=>{if(uiMode==='chat')newChat();else openTask();};$('mobile-new').onclick=()=>{if(uiMode==='chat')newChat();else openTask();};$('project-button').onclick=()=>openTask();$('setup-project').onclick=()=>openTask();$('setup-model').onclick=()=>openModels();
$('workspace-choice').onchange=()=>{$('existing-workspace').hidden=$('workspace-choice').value!=='existing';};
$('task-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{const workspace=$('workspace-choice').value==='existing'?$('new-workspace').value.trim():'';if($('workspace-choice').value==='existing'&&!workspace)throw Error('请选择一个本机文件夹。');const promoting=promoteFrom;promoteFrom='';const s=promoting?await api('session/promote',{session:promoting,title:$('new-title').value||'新项目',workspace}):await api('session',{title:$('new-title').value||'新项目',workspace});await refreshState();await selectSession(s.id);$('task-dialog').close();$('prompt').focus();if(promoting)await sendText('请阅读上面的需求背景，先给出制作方案让我确认，先不要动手改文件。');}catch(error){$('task-error').textContent=error.message;}finally{e.submitter.disabled=false;}};
$('mobile-menu').onclick=()=>$('history-dialog').showModal();
$('files-button').onclick=()=>{if(!permission.read){openGrant(false);viewingProject=true;$('grant-heading').textContent='查看项目文件';$('grant-mode').value='plan';$('grant-read').checked=true;grantFields();$('grant-submit').textContent='允许读取本项目文件';return;}showFiles(!panelOpen);};$('close-files').onclick=()=>showFiles(false);
$('reveal-project').onclick=async()=>{try{await api('workspace/open',{session:current});}catch(e){notify(e.message);}};
async function browseFolders(path=''){try{const data=await api('folders?path='+encodeURIComponent(path));folderPath=data.path;$('folder-current').textContent=folderPath;$('folder-list').replaceChildren();if(data.parent){const up=el('button','↑ 上一级');up.type='button';up.onclick=()=>browseFolders(data.parent);$('folder-list').append(up);}for(const f of data.folders){const b=el('button','▱ '+f.name);b.type='button';b.onclick=()=>browseFolders(f.path);$('folder-list').append(b);}$('folder-browser').hidden=false;}catch(e){$('task-error').textContent=e.message;}}
$('browse-folders').onclick=()=>browseFolders($('new-workspace').value);$('folder-use').onclick=()=>{$('new-workspace').value=folderPath;$('folder-browser').hidden=true;};
function openGrant(start=false){
 if(!current){openTask();return;}if(isActive()){notify('先停止当前任务，再修改授权。');return;}
 viewingProject=false;$('grant-heading').textContent='让超级小博开始制作';pendingGrantStart=start;$('permission-error').textContent='';$('grant-workspace').textContent=sessionData.session.workspace;$('grant-mode').value=permission.mode==='plan'?'auto':permission.mode;
 for(const key of ['read','write','execute','images','network','remember'])$('grant-'+key).checked=!!permission[key];
 if(permission.mode==='plan'){$('grant-read').checked=true;$('grant-write').checked=true;}
 $('grant-images').disabled=!state.capabilities.image;
 $('grant-execution').value=permission.execution==='host'?'host':'docker';$('acknowledge-host').checked=false;
 $('grant-image-limit').value=permission.image_limit??4;$('grant-steps').value=permission.max_steps??40;$('grant-seconds').value=permission.max_seconds??1200;$('grant-tokens').value=permission.max_tokens??150000;
 $('start-after-grant').checked=start;$('start-after-label').hidden=!running;grantFields();$('permission-dialog').showModal();
}
$('authorize').onclick=()=>openGrant(false);

function grantFields(){const mode=$('grant-mode').value,plan=mode==='plan';
  $('grant-description').textContent={plan:'只讨论和规划。可单独允许阅读材料；不会制作文件、运行命令或生图。',ask:'每次写文件、运行命令、生成素材前，先显示操作内容供你批准。',auto:'项目内常规制作自动执行。生图和未隔离的本机命令仍需单独批准。Docker 命令在已授权的环境内自动执行。',full:'已授权范围内连续执行，不再逐项询问。达到本次预算时停止新的调用。'}[mode];
  for(const key of ['write','execute','images']){$('grant-'+key).disabled=plan||(key==='images'&&!state.capabilities.image);if(plan)$('grant-'+key).checked=false;}
  $('execution-options').hidden=!$('grant-execute').checked;$('host-consent').hidden=$('grant-execution').value!=='host';$('start-after-label').hidden=plan||!running;$('grant-submit').textContent=plan?'保持 Plan':$('start-after-grant').checked?'授权并开始制作':'保存授权';
}
$('grant-mode').onchange=()=>{if($('grant-mode').value!=='plan'){$('grant-read').checked=true;$('grant-write').checked=true;}grantFields();};$('start-after-grant').onchange=grantFields;$('grant-execute').onchange=grantFields;$('grant-execution').onchange=grantFields;
$('permission-form').onsubmit=async e=>{e.preventDefault();const value={mode:$('grant-mode').value,execution:$('grant-execution').value,acknowledge_host:$('acknowledge-host').checked};
  for(const key of ['read','write','execute','images','network','remember'])value[key]=$('grant-'+key).checked;
  Object.assign(value,{image_limit:Number($('grant-image-limit').value),max_steps:Number($('grant-steps').value),max_seconds:Number($('grant-seconds').value),max_tokens:Number($('grant-tokens').value)});
  const b=e.submitter;b.disabled=true;try{permission=await api('permission',{session:current,permission:value});renderPermission();$('permission-dialog').close();notify('');if(value.mode!=='plan'&&$('start-after-grant').checked)await sendText('请按照刚才讨论的需求和方案开始制作。先检查已有文件，再完成制作与验证。');else{await loadSession();if(viewingProject&&value.read)showFiles(true);notify(value.mode==='plan'?'当前是 Plan，可以继续讨论和规划。':'已授权。现在发送需求，超级小博就会开始制作。');}}catch(e){$('permission-error').textContent=e.message;}finally{b.disabled=false;}
};
$('revoke').onclick=async()=>{try{permission=await api('permission',{session:current,permission:{mode:'plan'}});resetPreview();renderPermission();$('permission-dialog').close();await loadSession();notify('已撤销授权并停止当前执行；已保存的成果仍在项目目录中。');}catch(e){$('permission-error').textContent=e.message;}};
async function sendText(text,withAttachments=false){if(!text||sending||isActive())return;if(!modelReady()){openModels();return;}if(!current){if(uiMode==='work'){openTask();return;}const s=await api('session',{kind:'chat',title:text.slice(0,24)||'新聊天'});await refreshState();await selectSession(s.id);}sending=true;updateComposer();notify('');try{await api('run',{session:current,text,model:activeModel(),attachments:withAttachments?attachments.map(({kind,data})=>({kind,data})):[]});if(withAttachments){$('prompt').value='';attachments=[];drawAttachments();}$('run-error').hidden=true;$('next-action').hidden=true;await loadSession();}catch(e){notify(e.message);$('run-error').hidden=false;$('error-heading').textContent='未能开始';$('error-detail').textContent=e.message;}finally{sending=false;updateComposer();}}
$('composer').onsubmit=async e=>{e.preventDefault();await sendText($('prompt').value.trim(),true);};
$('retry').onclick=()=>{if(running)sendText(running.status==='failed'&&running.steps===0?running.goal:'继续刚才未完成的需求，先检查已保存的文件与状态，再继续。');};
$('error-settings').onclick=()=>openModels();

$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!$('send').disabled)$('composer').requestSubmit();}};
$('stop').onclick=async()=>{if(running)try{await api('cancel',{run:running.id});await loadSession();}catch(e){notify(e.message);}};
function bindSuggestions(){for(const b of document.querySelectorAll('[data-prompt]'))b.onclick=()=>{$('prompt').value=b.dataset.prompt;$('prompt').focus();};}bindSuggestions();
function drawAttachments(){$('attachment-list').replaceChildren(...attachments.map((a,i)=>{const b=el('button',a.name+' ×');b.type='button';b.onclick=()=>{attachments.splice(i,1);drawAttachments();};return b;}));}
function asDataURL(blob){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(blob);});}
$('attachments').onchange=async e=>{try{for(const f of e.target.files){if(attachments.length>=3)throw Error('一次最多添加 3 份材料。');if(f.type.startsWith('image/')){if(f.size>1000000)throw Error('图片须小于 1 MB。');attachments.push({name:f.name,kind:'image',data:await asDataURL(f)});}else{if(f.size>25000)throw Error('文本材料须小于 25 KB。');attachments.push({name:f.name,kind:'text',data:await f.text()});}}drawAttachments();}catch(e){notify(e.message);}finally{e.target.value='';}};
$('record').onclick=async()=>{
  if(recorder?.state==='recording'){recorder.stop();return;}
  if(!state.capabilities.asr){openModels('asr');return;}
  let stream;
  try{stream=await navigator.mediaDevices.getUserMedia({audio:true});recorder=new MediaRecorder(stream);const chunks=[];recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=async()=>{clearTimeout(recordTimer);stream.getTracks().forEach(t=>t.stop());$('record').disabled=true;$('record').textContent='识别中…';try{const blob=new Blob(chunks,{type:recorder.mimeType});if(blob.size>4000000)throw Error('录音超过 4 MB，请缩短录音。');const data=await asDataURL(blob),r=await api('audio/transcribe',{audio:data.split(',')[1],mime:recorder.mimeType.split(';')[0]});$('prompt').value+=($('prompt').value?'\n':'')+r.text;$('prompt').focus();notify('语音已转成文字，请检查后发送。');}catch(e){notify(e.message);}finally{$('record').disabled=false;$('record').textContent='语音输入';}};recorder.start();$('record').textContent='结束录音';recordTimer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},90000);}catch(e){stream?.getTracks().forEach(t=>t.stop());notify('无法开始录音：'+e.message);}
};
async function speak(text,button){button.disabled=true;try{if(text.length>4000)notify('本次播报前 4000 字。');const data=await api('audio/speech',{text:text.slice(0,4000)}),bytes=Uint8Array.from(atob(data.audio),c=>c.charCodeAt(0)),url=URL.createObjectURL(new Blob([bytes],{type:data.mime})),audio=new Audio(url);audio.onended=()=>URL.revokeObjectURL(url);audio.onerror=()=>URL.revokeObjectURL(url);await audio.play();}catch(e){notify(e.message);}finally{button.disabled=false;}}
(async()=>{try{const r=await fetch('/api/bootstrap');state=await r.json();if(!state.token)throw Error('无法连接本机运行时。');token=state.token;drawState();const saved=localStorage.getItem('lebot-session');if(state.sessions.some(s=>s.id===saved))await selectSession(saved);else if(state.sessions.length)await selectSession(state.sessions[0].id);applyMode();setPanelTab(localStorage.getItem('lebot-panel-tab')||'preview');if(!modelReady())openModels();updateComposer();setInterval(loadSession,1000);}catch(e){notify(e.message);}})();
