/* ============ 超级小博 · 第一次见面 · 剧情引擎 v3 ============ */
(function () {
  'use strict';
  /* v3 单独存档，避免旧版五学科剧情的 ptr 落进新脚本错误节点。 */
  const SAVE_KEY = 'lebotclaw-intro-v3';
  const $ = id => document.getElementById(id);
  const stage = $('stage'), dlg = $('dialog'), dlgText = $('dialog-text'), nameTag = $('name-tag');
  const narr = $('narr-box'), narrText = $('narr-text');
  const sprite = $('sprite'), spriteImg = $('sprite-img');
  const choiceLayer = $('choice-layer'), widgetLayer = $('widget-layer');
  const bgA = $('bg-a'), bgB = $('bg-b');

  const SCRIPT = window.PROLOGUE_SCRIPT;
  const LABELS = {};
  SCRIPT.forEach((n, i) => { if (n.t === 'label') LABELS[n.id] = i; });

  let ptr = 0, typing = false, typeTimer = null, fullText = '';
  let voiceOn = true, bgFlip = false, waiting = false;
  let revisiting = false; /* 回看模式：不覆盖真实存档，顶部条可随时返回最新进度 */

  /* ---------- 进度 ---------- */
  const save = () => { if (!revisiting) localStorage.setItem(SAVE_KEY, JSON.stringify({ ptr })); };
  const load = () => { try { return JSON.parse(localStorage.getItem(SAVE_KEY)); } catch (e) { return null; } };
  const reached = load();

  /* ---------- 语音（豆包炀炀2.0预生成mp3，按文本djb2哈希命名；缺失回退浏览器语音） ---------- */
  function djb2(s) { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0; return h.toString(16); }
  let curAudio = null;
  function stopAudio() { if (curAudio) { curAudio.pause(); curAudio = null; } }
  function speak(rawText) {
    stopAudio();
    if (!voiceOn) return;
    speechSynthesis.cancel();
    const a = new Audio(`assets/story/voice/${djb2(rawText)}.mp3`);
    curAudio = a;
    a.onerror = () => { /* 该句无预生成音频 → 浏览器语音兜底 */
      if (!voiceOn || !window.speechSynthesis) return;
      const u = new SpeechSynthesisUtterance(rawText.replace(/\*\*/g, '').replace(/[👋✨🎉📜🏰🎖️🐾]/g, ''));
      u.lang = 'zh-CN'; u.rate = 1.12; u.pitch = 1.35; u.volume = .9;
      const vs = speechSynthesis.getVoices().filter(v => v.lang.startsWith('zh'));
      if (vs.length) u.voice = vs.find(v => /Ting|Mei|Sinji|Xiao/i.test(v.name)) || vs[0];
      speechSynthesis.speak(u);
    };
    a.play().catch(() => { });
  }
  $('btn-voice').onclick = () => {
    voiceOn = !voiceOn;
    $('btn-voice').textContent = voiceOn ? '🔊 语音开' : '🔇 语音关';
    if (!voiceOn) { speechSynthesis.cancel(); stopAudio(); }
  };

  /* ---------- 背景 ---------- */
  function setBg(name) {
    const url = `url('assets/story/${name}.png')`;
    const showL = bgFlip ? bgA : bgB, hideL = bgFlip ? bgB : bgA;
    showL.style.backgroundImage = url; showL.classList.add('show'); hideL.classList.remove('show');
    bgFlip = !bgFlip;
  }

  /* ---------- 立绘 ---------- */
  function setSprite(name, pop) {
    if (!name) { sprite.classList.add('hidden'); return; }
    spriteImg.src = `assets/story/${name}.png`;
    sprite.classList.remove('hidden');
    if (pop) { sprite.classList.remove('pop'); void sprite.offsetWidth; sprite.classList.add('pop'); }
  }

  /* ---------- 打字机 ---------- */
  function typewrite(el, text, done) {
    fullText = text; typing = true;
    el.innerHTML = '';
    let i = 0;
    clearInterval(typeTimer);
    typeTimer = setInterval(() => {
      i += 2;
      el.innerHTML = fmt(text.slice(0, i));
      if (i >= text.length) finishType(el, done);
    }, 34);
  }
  function finishType(el, done) {
    clearInterval(typeTimer); typing = false;
    el.innerHTML = fmt(fullText);
    if (done) done();
  }
  const fmt = s => s.replace(/\*\*(.+?)\*\*/g, '<span class="hl">$1</span>');

  /* ---------- 主循环 ---------- */
  function step() {
    if (ptr >= SCRIPT.length) return;
    const node = SCRIPT[ptr];
    switch (node.t) {
      case 'label': ptr++; step(); break;
      case 'chapter': $('hud-chapter').textContent = node.text; ptr++; step(); break;
      case 'bg': setBg(node.bg); ptr++; step(); break;
      case 'sprite': setSprite(node.sp, node.pop); ptr++; step(); break;
      case 'clr-widget': widgetLayer.innerHTML = ''; ptr++; step(); break;
      case 'say':
        hideAll(); dlg.classList.remove('hidden');
        nameTag.textContent = node.who || '超级小博';
        if (node.sp) setSprite(node.sp, node.pop);
        speak(node.text);
        typewrite(dlgText, node.text);
        waitClick(dlg);
        break;
      case 'narr':
        hideAll(); narr.classList.remove('hidden');
        speak(node.text);
        typewrite(narrText, node.text);
        waitClick(narr);
        break;
      case 'button': showButton(node); break;
      case 'choice': showChoice(node); break;
      case 'cards': showCards(node); break;
      case 'widget': WIDGETS[node.kind](node); break;
      case 'kcard': showKcard(node); break;
      case 'award': showAward(node); break;
      case 'goto': ptr = LABELS[node.id] ?? ptr + 1; step(); break;
      case 'end': break;
    }
    save();
  }
  function stripMd(s) { return s.replace(/\*\*/g, ''); }
  function hideAll() { dlg.classList.add('hidden'); narr.classList.add('hidden'); choiceLayer.classList.add('hidden'); }
  function waitClick(el) {
    waiting = true;
    el.onclick = () => {
      if (typing) { finishType(el === dlg ? dlgText : narrText); return; }
      waiting = false; ptr++; step();
    };
  }

  /* ---------- 大按钮 ---------- */
  function showButton(node) {
    hideAll(); choiceLayer.classList.remove('hidden');
    choiceLayer.innerHTML = '';
    const b = document.createElement('button');
    b.className = 'choice-btn choice-confirm'; b.style.fontSize = 'calc(15px + .8vw)';
    b.textContent = node.label;
    b.onclick = () => { choiceLayer.classList.add('hidden'); ptr++; step(); };
    choiceLayer.appendChild(b);
  }

  /* ---------- 选项（单选/多选，含反馈） ---------- */
  function showChoice(node) {
    hideAll(); choiceLayer.classList.remove('hidden');
    // 清掉上次作答注入的反馈（目录回看会重跑本题）
    while (SCRIPT[ptr + 1] && SCRIPT[ptr + 1]._tmp) SCRIPT.splice(ptr + 1, 1);
    choiceLayer.innerHTML = '';
    if (node.q) {
      const q = document.createElement('div'); q.className = 'choice-q'; q.textContent = node.q;
      choiceLayer.appendChild(q);
    }
    const row = document.createElement('div'); row.className = 'multi-row';
    choiceLayer.appendChild(row);
    const picked = new Set();

    if (node.multi) {
      node.options.forEach((op, i) => {
        const b = document.createElement('button'); b.className = 'choice-btn'; b.textContent = op.label;
        b.onclick = () => { picked.has(i) ? (picked.delete(i), b.classList.remove('picked')) : (picked.add(i), b.classList.add('picked')); };
        row.appendChild(b);
      });
      const c = document.createElement('button'); c.className = 'choice-btn choice-confirm'; c.textContent = '✓ 选好啦';
      c.onclick = () => {
        const ans = node.answer || [];
        const ok = picked.size === ans.length && [...picked].every(i => ans.includes(i));
        [...row.children].forEach((b, i) => {
          b.disabled = true;
          if (ans.includes(i)) b.classList.add('correct');
          else if (picked.has(i)) b.classList.add('wrong');
        });
        c.remove();
        setTimeout(() => {
          choiceLayer.classList.add('hidden');
          inject(ok ? node.fbRight : node.fbWrong);
          ptr++; step();
        }, 1400);
      };
      choiceLayer.appendChild(c);
    } else {
      node.options.forEach(op => {
        const b = document.createElement('button'); b.className = 'choice-btn'; b.textContent = op.label;
        b.onclick = () => {
          [...row.children].forEach(x => x.disabled = true);
          setTimeout(() => {
            choiceLayer.classList.add('hidden');
            if (op.fb) inject(op.fb);
            ptr++; step();
          }, 260);
        };
        row.appendChild(b);
      });
    }
  }
  // 把反馈对话插到当前位置前（不消耗主线 ptr 的写法：直接以字符串播放后继续）
  function inject(fb) {
    if (typeof fb === 'string') {
      SCRIPT.splice(ptr + 1, 0, { t: 'say', text: fb, sp: 'sp_smile_ng_v3', _tmp: true });
    } else if (Array.isArray(fb)) {
      SCRIPT.splice(ptr + 1, 0, ...fb.map(x => typeof x === 'string' ? { t: 'say', text: x, sp: 'sp_smile_ng_v3', _tmp: true } : { ...x, _tmp: true }));
    }
  }

  /* ---------- 图片卡片（0-2） ---------- */
  function showCards(node) {
    const old = document.querySelector('.imgcard-row'); if (old) old.remove();
    const row = document.createElement('div'); row.className = 'imgcard-row';
    node.items.forEach((it, i) => {
      const c = document.createElement('div'); c.className = 'imgcard';
      if (node.reveal) c.classList.add(it.ai ? 'ai-yes' : 'ai-no');
      c.style.animationDelay = (i * 0.14) + 's';
      c.innerHTML = `<span class="ic-emoji">${it.emoji}</span>${it.label}${node.reveal ? (it.ai ? '<br>✅ 是 AI' : '<br>❌ 不是 AI') : ''}`;
      row.appendChild(c);
    });
    stage.appendChild(row);
    ptr++; step();
  }

  /* ---------- 知识卡片 ---------- */
  function showKcard(node) {
    $('kcard-title').textContent = node.title;
    $('kcard-body').textContent = node.body;
    $('kcard-points').innerHTML = (node.points || []).map(p => `<span>${p}</span>`).join('');
    $('kcard-mask').classList.remove('hidden');
    $('kcard-close').onclick = () => { $('kcard-mask').classList.add('hidden'); ptr++; step(); };
  }

  /* ---------- 互动组件 ---------- */
  const WIDGETS = {
    /* 序章：只收称呼；头像在回到主站后继续创建。 */
    meet() {
      widgetLayer.innerHTML = '';
      const p = panel('👋 我该怎么称呼你？');
      const input = document.createElement('input');
      input.className = 'w-input meet-name';
      input.maxLength = 12;
      input.placeholder = '请输入你想让我称呼的名字';
      // 每次进入名字环节都从空白开始，避免测试账号或上次填写的名字自动带出。
      input.value = '';
      const b = document.createElement('button');
      b.className = 'w-btn primary';
      b.textContent = '认识一下吧 ✨';
      const submit = () => {
        const name = input.value.trim();
        if (!name) { input.focus(); input.classList.add('shake'); setTimeout(() => input.classList.remove('shake'), 400); return; }
        localStorage.setItem('lc_intro_name', name);
        widgetLayer.innerHTML = '';
        const hello = document.createElement('div');
        hello.className = 'hello-card';
        hello.innerHTML = `<span>认识你真开心</span><b>${esc(name)}</b><small>名字已经收好啦 ✓</small>`;
        widgetLayer.appendChild(hello);
        setTimeout(() => { widgetLayer.innerHTML = ''; ptr++; step(); }, 1500);
      };
      b.onclick = submit;
      input.onkeydown = e => { if (e.key === 'Enter' && !e.isComposing) submit(); };
      p.append(input, document.createElement('br'), b);
      setTimeout(() => input.focus(), 150);
    },

    /* 第一站：选择一件事，演示按任务自动换模型，而不是切换学科 Agent。 */
    model_switch() {
      const TASKS = [
        { q: '🎨 帮我画一只住在月球的小猫', model: '豆包 Seedream 4.0', tool: 'AI 画图', color: '#ff8c42' },
        { q: '🖼️ 看看我发来的照片里有什么', model: 'Kimi K2.6', tool: '视觉理解', color: '#22c5c7' },
        { q: '🧩 陪我解开一道烧脑谜题', model: 'DeepSeek V4 Pro', tool: '深度推理', color: '#8b5cf6' },
        { q: '💬 我今天有点不开心，陪我聊聊', model: 'GLM 5.2', tool: '温暖回应', color: '#ef7aa8' },
      ];
      widgetLayer.innerHTML = '';
      const p = panel('🧠 选一件想和超级小博一起做的事');
      const note = document.createElement('div'); note.className = 'w-note'; note.textContent = '看看超级小博会自动换上哪种 AI 大脑';
      TASKS.forEach(item => {
        const b = document.createElement('button');
        b.className = 'w-btn model-task'; b.textContent = item.q;
        b.onclick = () => {
          [...p.querySelectorAll('.w-btn')].forEach(x => x.remove());
          note.textContent = '';
          const st = document.createElement('div'); st.className = 'route-stage';
          st.innerHTML = `<div class="route-q">${esc(item.q)}</div><div class="route-arrow">正在理解你想做什么…</div>`;
          p.insertBefore(st, note);
          setTimeout(() => { st.querySelector('.route-arrow').textContent = '自动选择最合适的 AI 模型…'; }, 700);
          setTimeout(() => {
            const badge = document.createElement('div'); badge.className = 'route-badge'; badge.style.borderColor = item.color;
            badge.innerHTML = `<span class="brain-orb" style="background:${item.color}">AI</span><br><b style="color:${item.color}">${item.model}</b> 已就位<br><small>接着调用：${item.tool}</small>`;
            st.appendChild(badge);
            note.textContent = '不用手动设置，超级小博会自己完成 ✓';
            setTimeout(() => { widgetLayer.innerHTML = ''; ptr++; step(); }, 2100);
          }, 1500);
        };
        p.appendChild(b);
      });
      p.appendChild(note);
    },

    /* 第二站：用一个例子展示“记忆透明 + 技能积累 + 陪伴成长”。 */
    growth() {
      widgetLayer.innerHTML = '';
      const p = panel('🌱 一起种下一段共同记忆');
      const choices = ['🦕 我最喜欢恐龙', '🌧️ 我有点怕打雷', '🎂 记住我的生日愿望'];
      const note = document.createElement('div'); note.className = 'w-note'; note.textContent = '随便选一个例子，看看它会去哪里';
      choices.forEach(text => {
        const b = document.createElement('button'); b.className = 'w-btn memory-choice'; b.textContent = text;
        b.onclick = () => {
          [...p.querySelectorAll('.w-btn')].forEach(x => x.disabled = true);
          widgetLayer.innerHTML = '';
          const wrap = document.createElement('div'); wrap.className = 'memcard-col growth-cards';
          const cards = [
            ['🧠 记住重要的你', text.replace(/^[^ ]+ /, ''), '#2f9bff'],
            ['👀 记忆透明可控', '随时查看 · 修改 · 忘掉', '#22c5c7'],
            ['🎒 积累新本领', '做成的事情会沉淀成技能', '#8b5cf6'],
            ['🐾 共同成长', '陪伴天数和共同经历会留下来', '#ff8c42'],
          ];
          cards.forEach((c, i) => {
            const d = document.createElement('div'); d.className = 'memcard'; d.style.borderColor = c[2]; d.style.animationDelay = (i * 0.42) + 's';
            d.innerHTML = `<b style="color:${c[2]}">${c[0]}</b><span>${esc(c[1])}</span>`;
            wrap.appendChild(d);
          });
          widgetLayer.appendChild(wrap);
          setTimeout(() => { widgetLayer.innerHTML = ''; ptr++; step(); }, 3500);
        };
        p.appendChild(b);
      });
      p.appendChild(note);
    },

    /* 终章：不发学员证，改成两个人的好朋友名牌。 */
    friendcard() {
      widgetLayer.innerHTML = '';
      const name = localStorage.getItem('lc_intro_name') || localStorage.getItem('lc_name') || '新朋友';
      const card = document.createElement('div'); card.className = 'friend-card';
      card.innerHTML = `<div class="friend-stars">✦　✧　✦</div>
        <h3>好 朋 友 名 牌</h3>
        <div class="friend-pair"><span>${esc(name)}</span><i>×</i><span>超级小博</span></div>
        <p>从今天开始，一起聊天、创造、探索和成长</p>
        <small>LebotClaw · 第一次见面</small>`;
      widgetLayer.appendChild(card);
      setTimeout(() => { widgetLayer.innerHTML = ''; ptr++; step(); }, 3000);
    },
  };

  function panel(title) {
    const p = document.createElement('div'); p.className = 'w-panel';
    p.innerHTML = `<div class="w-title">${title}</div>`;
    widgetLayer.appendChild(p);
    return p;
  }
  const esc = s => s.replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));

  /* ---------- 结算 ---------- */
  function showAward(node) {
    hideAll(); setSprite(null);
    const m = $('award-mask');
    m.innerHTML = `<div class="award-card">
      <div class="award-lv">${node.icon || '🎖️'}</div>
      <div class="award-title">${node.title}</div>
      <div class="award-sub">${node.sub || ''}</div>
      <div class="award-btns">
        <button class="again" id="aw-again">${revisiting ? '↩ 返回最新进度' : '↺ 再玩一次'}</button>
        ${revisiting ? '' : `<button class="next" id="aw-next">${node.nextLabel || '开启第一章 →'}</button>`}
      </div></div>`;
    m.classList.remove('hidden');
    $('aw-again').onclick = () => {
      if (revisiting) { backToLatest(); return; } /* 回看走到结算：不清存档，返回最新进度 */
      localStorage.removeItem(SAVE_KEY); location.reload();
    };
    if (!revisiting) {
      $('aw-next').onclick = () => {
        /* 完成第一次见面，把称呼交给主站继续创建头像。 */
        localStorage.setItem('lc_intro_seen_v3', '1');
        const nm = localStorage.getItem('lc_intro_name') || '';
        location.href = '../?from=intro' + (nm ? '&name=' + encodeURIComponent(nm) : '');
      };
    }
    save();
  }

  /* ---------- 目录 ---------- */
  const MENU = [
    ['start', '第一次见面 · 嗨，我是超级小博'],
    ['t01', '第一站 · 一起做很多有意思的事'],
    ['t02', '第二站 · 越用越懂你，也越用越会'],
    ['t03', '最后一站 · 我们就是好朋友了'],
  ];
  $('btn-menu').onclick = () => {
    const cur = load();
    $('menu-list').innerHTML = MENU.map(([id, name]) => {
      const ok = cur && cur.ptr > LABELS[id];
      return `<div class="menu-item ${ok ? '' : 'locked'}" data-id="${id}">
        <span>${name}</span><span class="st">${ok ? '✅ 可回看' : '🔒'}</span></div>`;
    }).join('');
    $('menu-mask').classList.remove('hidden');
    [...document.querySelectorAll('.menu-item:not(.locked)')].forEach(el => {
      el.onclick = () => {
        $('menu-mask').classList.add('hidden');
        startRevisit(LABELS[el.dataset.id]);
      };
    });
  };
  $('menu-close').onclick = () => $('menu-mask').classList.add('hidden');
  /* —— 回看模式：不覆盖真实存档，顶部条可随时返回最新进度 —— */
  function startRevisit(targetPtr) {
    widgetLayer.innerHTML = '';
    const old = document.querySelector('.imgcard-row'); if (old) old.remove();
    speechSynthesis.cancel(); stopAudio(); clearInterval(typeTimer); typing = false;
    choiceLayer.classList.add('hidden'); hideAll();
    revisiting = true;
    ptr = targetPtr; step();
    $('revisit-bar').classList.remove('hidden');
  }
  function backToLatest() {
    revisiting = false;
    $('revisit-bar').classList.add('hidden');
    $('award-mask').classList.add('hidden');
    widgetLayer.innerHTML = '';
    const old = document.querySelector('.imgcard-row'); if (old) old.remove();
    speechSynthesis.cancel(); stopAudio(); clearInterval(typeTimer); typing = false;
    choiceLayer.classList.add('hidden'); hideAll();
    const saved = load();
    ptr = (saved && saved.ptr != null) ? saved.ptr : 0;
    step();
  }
  $('rv-back').onclick = backToLatest;
  $('btn-restart').onclick = () => {
    if (confirm('从头开始第一次见面？')) { localStorage.removeItem(SAVE_KEY); location.reload(); }
  };

  /* ---------- 启动 ---------- */
  if (reached && reached.ptr > 3 && reached.ptr < SCRIPT.length) $('btn-continue').classList.remove('hidden');
  $('btn-start').onclick = () => { localStorage.removeItem(SAVE_KEY); begin(0); };
  $('btn-continue').onclick = () => begin((load() || {}).ptr || 0);
  function begin(p) {
    $('cover').classList.add('gone');
    speechSynthesis.getVoices(); // 预加载语音列表
    ptr = p; step();
  }

  /* 调试跳转：index.html#debug=t03 */
  const dbg = location.hash.match(/debug=(\w+)/);
  if (dbg && LABELS[dbg[1]] != null) begin(LABELS[dbg[1]]);
})();
