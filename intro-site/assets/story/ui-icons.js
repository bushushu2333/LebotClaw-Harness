/* LebotWorld 统一 PNG 图标适配层。
 * 保留旧数据中的 Emoji 字段，渲染后自动替换为平台图标，避免各页面重复维护映射。
 */
(function () {
  'use strict';

  var script = document.currentScript;
  var iconBase = script && script.dataset.iconBase
    ? new URL(script.dataset.iconBase, document.baseURI).href
    : new URL('../icons/', script && script.src ? script.src : location.href).href;
  var aliases = {
    '☀': 'theme-day', '☀️': 'theme-day', '🌞': 'theme-day', '🌙': 'theme-night', '🌿': 'theme-eye', '🍃': 'theme-eye',
    '🔊': 'sound', '🔈': 'sound', '🔇': 'sound', '⚙': 'settings', '⚙️': 'settings',
    '🎤': 'microphone', '🎙': 'microphone', '🎙️': 'microphone', '📎': 'attachment',
    '☰': 'menu', '⋯': 'menu', '✕': 'close', '➤': 'send', '▶': 'send', '▶️': 'send', '↩': 'route', '↩️': 'route', '↺': 'route',
    '🎴': 'skills', '🧩': 'skills', '🛠': 'skills', '🛠️': 'skills',
    '🐾': 'dossier', '📁': 'materials', '📂': 'materials', '📄': 'materials', '📜': 'materials',
    '📚': 'library', '🏫': 'library', '🏰': 'library', '🗺': 'route', '🗺️': 'route', '🧠': 'ai-model', '🤖': 'ai-model', '👨‍💻': 'profile', '💻': 'ai-model',
    '⚡': 'running', '🚀': 'running', '⏳': 'running', '💬': 'history', '📝': 'edit', '✏': 'edit', '✏️': 'edit',
    '✍': 'edit', '✍️': 'edit', '✂': 'edit', '✂️': 'edit', '👁': 'preview', '👁️': 'preview', '📽': 'preview', '📽️': 'preview',
    '👤': 'profile', '🪪': 'profile', '📈': 'growth', '📊': 'growth', '💡': 'learn', '🎓': 'learn',
    '👩‍🏫': 'learn', '📒': 'mistakes', '📌': 'target', '🎯': 'target', '❓': 'target',
    '📖': 'dictionary', '🎨': 'create', '🎭': 'create', '🔍': 'search', '🪐': 'explore', '🎮': 'explore',
    '🏕': 'explore', '🏕️': 'explore', '🔬': 'explore', '🧪': 'explore', '📐': 'calculator', '🧮': 'calculator',
    '⏱': 'timer', '⏱️': 'timer', '🔒': 'locked', '⚔': 'running', '⚔️': 'running',
    '✅': 'success', '❌': 'failure', '⚠': 'failure', '⚠️': 'failure', '🌱': 'learned',
    '🔀': 'route', '🔄': 'route', '☁': 'route', '☁️': 'route', '🎂': 'achievement', '🏆': 'achievement',
    '🏅': 'achievement', '🎖': 'achievement', '🎖️': 'achievement', '⭐': 'achievement', '🌟': 'achievement',
    '✨': 'achievement', '🎉': 'achievement', '🇨🇳': 'achievement', '💌': 'letter', '💾': 'save',
    '🛡': 'safety', '🛡️': 'safety', '🤝': 'safety', '📞': 'phone', '📤': 'upload', '📥': 'upload',
    '⬇': 'upload', '⬇️': 'upload', '🗑': 'delete', '🗑️': 'delete', '📋': 'copy', '🔧': 'settings',
    '🔤': 'vocabulary', '🔠': 'vocabulary', '🎒': 'library', '🖨': 'save', '🖨️': 'save',
  };
  var keys = Object.keys(aliases).sort(function (a, b) { return b.length - a.length; });
  var pattern = new RegExp(keys.map(function (s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|'), 'gu');
  var blocked = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, OPTION: 1, CODE: 1, PRE: 1 };
  var preserveSelector = '[data-keep-emoji],.chat-bubble,.bubble,.message,.msg,.ap-log';

  function src(name) { return iconBase + name + '.png'; }
  function image(name) {
    var img = document.createElement('img');
    img.className = 'lb-ui-icon'; img.src = src(name); img.alt = '';
    img.setAttribute('aria-hidden', 'true'); img.draggable = false;
    return img;
  }
  function upgradeText(node) {
    var parent = node.parentElement;
    if (!parent || blocked[parent.tagName] || parent.closest(preserveSelector + ',.lb-ui-icon')) return;
    var value = node.nodeValue || '';
    pattern.lastIndex = 0;
    if (!pattern.test(value)) return;
    pattern.lastIndex = 0;
    var frag = document.createDocumentFragment(), last = 0, match;
    while ((match = pattern.exec(value))) {
      if (match.index > last) frag.appendChild(document.createTextNode(value.slice(last, match.index)));
      frag.appendChild(image(aliases[match[0]]));
      last = match.index + match[0].length;
    }
    if (last < value.length) frag.appendChild(document.createTextNode(value.slice(last)));
    node.replaceWith(frag);
  }
  function upgrade(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) return upgradeText(root);
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var nodes = [], current;
    while ((current = walker.nextNode())) nodes.push(current);
    nodes.forEach(upgradeText);
  }

  var style = document.createElement('style');
  style.textContent = '.lb-ui-icon{display:inline-block;width:1.18em;height:1.18em;object-fit:contain;vertical-align:-.22em;flex:0 0 auto;user-select:none;pointer-events:none}.pn-icon>.lb-ui-icon,.mh-medal>.lb-ui-icon,.award-lv>.lb-ui-icon,.feature-emoji>.lb-ui-icon,.scenario-emoji>.lb-ui-icon,.product-emoji>.lb-ui-icon,.ap-emoji>.lb-ui-icon{width:1em;height:1em}button>.lb-ui-icon,.btn>.lb-ui-icon{margin-right:.28em}button>.lb-ui-icon:only-child,.btn>.lb-ui-icon:only-child{margin-right:0}';
  document.head.appendChild(style);

  var observer = new MutationObserver(function (records) {
    records.forEach(function (record) { record.addedNodes.forEach(upgrade); });
  });
  function start() {
    upgrade(document.body);
    observer.observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true }); else start();

  window.LB_UI_ICONS = { upgrade: upgrade, src: src, image: image, aliases: aliases };
})();
