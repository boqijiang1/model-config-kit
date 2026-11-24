/* 模型配置组件（自包含，零依赖）。
 *
 * 用法：
 *   <model-config-panel api-base="/api/model-config"></model-config-panel>
 *   <script src="/static/model_config/model-config.js"></script>
 *
 * 可选属性：
 *   api-base          接口前缀，默认 /api/model-config
 *   css-href          样式文件地址，默认与本 js 同目录的 model-config.css
 *   show-thinking     "false" 时隐藏「思考深度」选择器
 *   heading           页面大标题，默认「模型设置」
 *
 * 对外事件：
 *   mc-change         每次状态刷新后触发，detail = 服务端 /status 回包
 *   mc-ready          首次加载完成后触发
 *
 * 颜色主题：在宿主页面给元素写 CSS 变量即可（--mc-brand / --mc-ink / ...）。
 */
(function () {
  'use strict';

  var scriptEl = document.currentScript;
  var DEFAULT_CSS = scriptEl && scriptEl.src
    ? scriptEl.src.replace(/model-config\.js(\?.*)?$/, 'model-config.css')
    : 'model-config.css';

  var JSON_HEADERS = { 'Content-Type': 'application/json' };
  var KEY_DOTS = '••••••••••••••••••••••••••••••••';
  var BRAND_LOGOS = { ark: 'logo-ark', deepseek: 'logo-deepseek', openai: 'logo-openai' };
  var LEGACY_PROVIDER_LABELS = {
    ark: '火山方舟（豆包）', deepseek: 'DeepSeek 官方', kimi: 'Kimi 官方',
    zhipu: '智谱开放平台', minimax: 'MiniMax 开放平台', dashscope: '阿里云百炼',
    'tencent-tokenhub': '腾讯 TokenHub'
  };
  var THINKING_LABELS = { off: '不思考', auto: '适当思考（推荐）', deep: '深度思考' };
  var HEALTH_POLL_DELAYS = [600, 1200, 2000, 3000, 5000];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function icon(name, cls) {
    return '<svg class="' + (cls || 'mc-icon') + '" aria-hidden="true"><use href="#i-'
      + name + '"/></svg>';
  }

  var SPRITE = ''
    + '<symbol id="i-more" viewBox="0 0 24 24"><circle cx="12" cy="5" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="12" cy="19" r="1.4"/></symbol>'
    + '<symbol id="i-plus" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="M12 5v14"/></symbol>'
    + '<symbol id="i-refresh" viewBox="0 0 24 24"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></symbol>'
    + '<symbol id="i-arrow-left" viewBox="0 0 24 24"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></symbol>'
    + '<symbol id="i-chev-right" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></symbol>'
    + '<symbol id="i-eye" viewBox="0 0 24 24"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></symbol>'
    + '<symbol id="i-eye-off" viewBox="0 0 24 24"><path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/></symbol>'
    + '<symbol id="i-plug" viewBox="0 0 24 24"><path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/></symbol>'
    + '<symbol id="i-pencil" viewBox="0 0 24 24"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/></symbol>'
    + '<symbol id="logo-ark" viewBox="0 0 24 24"><path fill="#1b5bff" d="M8.6 20.4 12.7 3.4 16.8 20.4Z"/><path fill="#24d4ff" d="M13.4 20.4 16 10.9 18.6 20.4Z"/><path fill="#24d4ff" d="M18.4 20.4 20 15.2 21.6 20.4Z"/><path fill="#24d4ff" d="M4.4 20.4 7.5 8.7 10.6 20.4Z"/><path fill="#24d4ff" d="M1.4 20.4 3.7 13.3 6 20.4Z"/><path fill="#24d4ff" d="M9.7 20.4 12.4 10.2 15.1 20.4Z"/></symbol>'
    + '<symbol id="logo-deepseek" viewBox="0 0 24 24"><path fill="#4d6bfe" d="M3.0 14.2C3.0 10.8 5.9 8.1 9.5 8.1c2.5 0 4.7 1.4 5.9 3.5.5-1.7 1.6-3.2 3.2-4.2-.3 1.1-.3 2.3 0 3.4.2.7.5 1.3.9 1.9.8-.6 1.7-.9 2.7-.9-.9 1.1-1.5 2.4-1.8 3.8-.3 1.2-.8 2.3-1.5 3.3-2.2 1-4.7 1.3-7.2.8C6.5 18.7 3.0 16.9 3.0 14.2Z"/><circle cx="8.3" cy="12.6" r=".95" fill="#fff"/></symbol>'
    + '<symbol id="logo-openai" viewBox="0 0 24 24"><g fill="none" stroke="#16181c" stroke-width="2.4" stroke-linecap="round">'
    + '<path d="M19.03 7.54L17.77 16.46"/>'
    + '<path d="M19.03 7.54L17.77 16.46" transform="rotate(60 12 12)"/>'
    + '<path d="M19.03 7.54L17.77 16.46" transform="rotate(120 12 12)"/>'
    + '<path d="M19.03 7.54L17.77 16.46" transform="rotate(180 12 12)"/>'
    + '<path d="M19.03 7.54L17.77 16.46" transform="rotate(240 12 12)"/>'
    + '<path d="M19.03 7.54L17.77 16.46" transform="rotate(300 12 12)"/>'
    + '</g></symbol>';

  var TEMPLATE = ''
    + '<svg class="mc-sprite" aria-hidden="true">' + SPRITE + '</svg>'
    + '<div class="mc-page">'
    + '  <header class="mc-head">'
    + '    <div class="mc-head-text">'
    + '      <h1 class="mc-title" id="mcTitle">模型设置</h1>'
    + '      <p class="mc-sub">管理模型供应商：加一家、把 Key 粘贴好，软件就能用它。</p>'
    + '    </div>'
    + '    <div class="mc-head-actions">'
    + '      <button type="button" class="mc-icon-square" id="mcRecheck"'
    + '        title="重新体检：把开着的供应商逐家重新查一遍，可能要十几秒" aria-label="重新体检">'
    + icon('refresh') + '</button>'
    + '      <button type="button" class="mc-primary" id="mcAddProvider"'
    + '        title="从目录里挑一家，或者接一个目录里没有的平台">'
    + icon('plus') + ' 添加供应商</button>'
    + '    </div>'
    + '  </header>'
    + '  <section class="mc-card mc-thinking" id="mcThinkingCard">'
    + '    <p class="mc-section-label">思考深度</p>'
    + '    <div class="mc-seg" role="radiogroup" aria-label="思考深度">'
    + '      <button type="button" class="mc-seg-btn" data-level="off" role="radio" aria-checked="false">不思考</button>'
    + '      <button type="button" class="mc-seg-btn on" data-level="auto" role="radio" aria-checked="true">适当思考（推荐）</button>'
    + '      <button type="button" class="mc-seg-btn" data-level="deep" role="radio" aria-checked="false">深度思考</button>'
    + '    </div>'
    + '    <p class="mc-note mc-thinking-hint">适当思考 = 软件推荐，跟各家默认一致；'
    + '      深度思考 = 更慢更贵，正文额度自动翻倍防被思考挤没。</p>'
    + '  </section>'
    + '  <section class="mc-card mc-active" id="mcActiveCard">'
    + '    <p class="mc-note" id="mcActiveLine" aria-live="polite">正在读取当前生效的模型…</p>'
    + '    <div class="mc-active-actions">'
    + '      <button type="button" class="mc-ghost" id="mcAutoBtn"'
    + '        title="软件按清单从上到下逐个试，挑第一个能调通的模型">自动（推荐）</button>'
    + '      <span class="mc-status-line" id="mcRecheckState" aria-live="polite"></span>'
    + '    </div>'
    + '  </section>'
    + '  <div class="mc-frame">'
    + '    <aside class="mc-side" aria-label="供应商清单">'
    + '      <p class="mc-side-title">供应商</p>'
    + '      <ul class="mc-list" id="mcProviderList"></ul>'
    + '    </aside>'
    + '    <div class="mc-main">'
    + '      <section id="mcDetail" hidden aria-labelledby="mcDetailTitle">'
    + '        <div class="mc-detail-head">'
    + '          <span id="mcDetailLogo"></span>'
    + '          <h2 id="mcDetailTitle"></h2>'
    + '          <div class="mc-detail-tools">'
    + '            <input type="checkbox" class="mc-switch" id="mcEnabled" aria-label="这家供应商的开关">'
    + '            <span class="mc-more-wrap">'
    + '              <button type="button" class="mc-icon-btn" id="mcMoreBtn"'
    + '                aria-haspopup="true" aria-expanded="false" title="更多：改名字、删除这家">'
    + icon('more') + '</button>'
    + '              <div class="mc-more-menu" id="mcMenu" hidden>'
    + '                <button type="button" class="mc-more-item" id="mcRenameBtn">改名字</button>'
    + '                <button type="button" class="mc-more-item mc-danger-text" id="mcDeleteProviderBtn">删除这家供应商</button>'
    + '              </div>'
    + '            </span>'
    + '          </div>'
    + '        </div>'
    + '        <p class="mc-help" id="mcMeta"></p>'
    + '        <div class="mc-field">'
    + '          <label class="mc-label" for="mcBaseUrl"><span>Base URL</span></label>'
    + '          <input type="text" class="mc-input mc-mono" id="mcBaseUrl" autocomplete="off"'
    + '            spellcheck="false" title="这家接口的入口地址。一般不用改；要改就直接改，光标离开时自动保存">'
    + '          <p class="mc-note" id="mcUrlOut" aria-live="polite"></p>'
    + '        </div>'
    + '        <div class="mc-field">'
    + '          <label class="mc-label" for="mcFormat"><span>API 格式</span></label>'
    + '          <select class="mc-input" id="mcFormat">'
    + '            <option value="openai">OpenAI 兼容（/chat/completions）</option>'
    + '          </select>'
    + '          <p class="mc-help">目前只支持这一种格式，目录里的供应商都用它。</p>'
    + '        </div>'
    + '        <div class="mc-field">'
    + '          <div class="mc-label"><label for="mcKeyInput">API Key</label>'
    + '            <span class="mc-aux"><a class="mc-linkbtn" id="mcKeyUrl" target="_blank"'
    + '              rel="noopener noreferrer">获取 API Key</a></span></div>'
    + '          <div class="mc-keyrow">'
    + '            <input type="password" class="mc-input" id="mcKeyInput" autocomplete="off"'
    + '              spellcheck="false" aria-label="这家的 API Key"'
    + '              title="粘贴这家的 Key：粘完自动验证并保存（手打的话，光标离开或按回车时保存）">'
    + '            <button type="button" class="mc-eye" id="mcKeyToggle" aria-pressed="false"'
    + '              aria-label="显示或隐藏这家的 Key（存过的 Key 点一下能看明文）">'
    + icon('eye') + '</button>'
    + '          </div>'
    + '          <p class="mc-note" id="mcKeyOut" aria-live="polite"></p>'
    + '        </div>'
    + '        <div class="mc-field mc-models" id="mcModelsBox">'
    + '          <div class="mc-label"><span>模型列表</span><span class="mc-aux">'
    + '            <button type="button" class="mc-mini" id="mcSyncBtn"'
    + '              title="从这家的账号里把能用的对话模型拉进清单（清单里已有的不动）">从账号同步</button>'
    + '            <button type="button" class="mc-mini" id="mcAddModelBtn"'
    + '              title="往这家清单里加一个模型">' + icon('plus') + ' 添加模型</button>'
    + '          </span></div>'
    + '          <p class="mc-help" id="mcModelsHint"></p>'
    + '          <div class="mc-model-list" id="mcModels"></div>'
    + '          <p class="mc-note" id="mcModelOut" aria-live="polite"></p>'
    + '        </div>'
    + '      </section>'
    + '      <section id="mcCatalog" hidden aria-labelledby="mcCatalogTitle">'
    + '        <div class="mc-catalog-head">'
    + '          <button type="button" class="mc-icon-square" id="mcCatalogBack" aria-label="返回">'
    + icon('arrow-left') + '</button>'
    + '          <h2 id="mcCatalogTitle">添加供应商</h2>'
    + '        </div>'
    + '        <p class="mc-catalog-sec">火山方舟（按你买的那种选，三个的接口地址各不相同）</p>'
    + '        <div class="mc-catalog-grid" id="mcCatalogArk"></div>'
    + '        <p class="mc-catalog-sec">其他</p>'
    + '        <div class="mc-catalog-grid" id="mcCatalogRest"></div>'
    + '      </section>'
    + '      <div class="mc-empty" id="mcEmpty" hidden>'
    + '        <strong>还没有供应商</strong>'
    + '        <span>挑一家，把它的 Key 粘贴进去，就能用它了。</span>'
    + '        <button type="button" class="mc-ghost" id="mcEmptyAdd">添加供应商</button>'
    + '      </div>'
    + '    </div>'
    + '  </div>'
    + '</div>'
    + dialog('mcDlgModelAdd', '添加模型', '添加模型', '把模型名字填进来，要和平台上写的一模一样。',
      'mcModelAddName', '比如 doubao-seed-2.1-pro', 'mcModelAddErr', [['mcModelAddCancel', '取消'], ['submit', '添加']])
    + dialog('mcDlgModelEdit', '编辑模型', '编辑模型', '改的是模型名字的写法；正在用这个模型的话，会跟着一起改。',
      'mcModelEditName', '', 'mcModelEditErr', [['mcModelEditDelete', '删除这个模型'], ['mcModelEditCancel', '取消'], ['submit', '保存']], true)
    + dialog('mcDlgModelDelete', '删除这个模型？', '', '', null, '', 'mcModelDeleteErr', [['mcModelDeleteCancel', '先不删'], ['submit', '确认删除']], false, true)
    + dialog('mcDlgCustom', '创建自定义供应商', '创建自定义供应商',
      '目录里没有的平台（比如中转站）从这里接：它也要提供 OpenAI 兼容的接口。',
      'mcCustomName', '比如：我的中转站', 'mcCustomErr', [['mcCustomCancel', '取消'], ['submit', '创建']], false, false, true)
    + dialog('mcDlgRename', '给这家改个名字', '给这家改个名字', '', 'mcRenameName', '', 'mcRenameErr', [['mcRenameCancel', '取消'], ['submit', '保存']])
    + dialog('mcDlgDeleteProvider', '删除这家供应商？', '', '', null, '', 'mcDeleteProviderErr', [['mcDeleteProviderCancel', '先不删'], ['submit', '确认删除']], false, true)
    + '<div class="mc-toast" id="mcToast" hidden></div>';

  // 拼一个弹窗的 HTML。kind: 普通表单 / split（左删右保存）/ 删除确认
  function dialog(id, title, heading, hint, inputId, placeholder, errId, buttons, split, confirm, withUrl) {
    var head = heading ? '<h2>' + heading + '</h2>' : '<h2>' + title + '</h2>';
    var body = '';
    if (hint) body += '<p class="mc-dialog-hint">' + hint + '</p>';
    if (withUrl) {
      body += '<label for="mcCustomName">名字</label>';
    }
    if (inputId) {
      body += '<input type="text" class="mc-input" id="' + inputId + '" autocomplete="off"'
        + ' spellcheck="false" placeholder="' + placeholder + '" autofocus>';
    }
    if (withUrl) {
      body += '<label for="mcCustomUrl">Base URL</label>'
        + '<input type="text" class="mc-input" id="mcCustomUrl" autocomplete="off"'
        + ' spellcheck="false" placeholder="https://…">';
    }
    body += '<p class="mc-err" id="' + errId + '" aria-live="polite"></p>';
    var btns = '';
    buttons.forEach(function (b) {
      var cls = b[0] === 'submit'
        ? (confirm ? 'mc-danger' : 'mc-primary')
        : (b[0].indexOf('Delete') >= 0 ? 'mc-mini mc-danger-text' : 'mc-ghost');
      var type = b[0] === 'submit' ? 'submit' : 'button';
      var idAttr = b[0] === 'submit' ? '' : ' id="' + b[0] + '"';
      btns += '<button type="' + type + '" class="' + cls + '"' + idAttr + '>' + b[1] + '</button>';
    });
    if (split) {
      // 第一个按钮单独一组放左边，其余靠右
      var first = btns.slice(0, btns.indexOf('</button>') + 9);
      var rest = btns.slice(btns.indexOf('</button>') + 9);
      btns = '<div class="group">' + first + '</div><div class="group">' + rest + '</div>';
      return '<dialog class="mc-dialog" id="' + id + '"><form id="' + id + 'Form">' + head + body
        + '<div class="mc-dialog-actions split">' + btns + '</div></form></dialog>';
    }
    var extra = confirm
      ? '<p class="mc-confirm-text">删除后，这家就不能再用它了。<strong>此操作无法撤回。</strong></p>'
      : '';
    return '<dialog class="mc-dialog" id="' + id + '"><form id="' + id + 'Form">' + head + extra + body
      + '<div class="mc-dialog-actions">' + btns + '</div></form></dialog>';
  }

  class ModelConfigPanel extends HTMLElement {
    static get observedAttributes() { return ['heading', 'show-thinking']; }

    constructor() {
      super();
      var root = this.attachShadow({ mode: 'open' });
      root.innerHTML = TEMPLATE;
      var link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = this.getAttribute('css-href') || DEFAULT_CSS;
      root.insertBefore(link, root.firstChild);
      this.status = null;
      this.selectedProvider = null;
      this.detailShownFor = null;
      this.catalogWanted = false;
      this.keyBusy = false;
      this.revealedKey = '';
      this.editingModel = null;
      this.deleteProviderId = null;
      this._timers = [];
      this._bound = false;
    }

    get apiBase() {
      return (this.getAttribute('api-base') || '/api/model-config').replace(/\/+$/, '');
    }

    $(id) { return this.shadowRoot.getElementById(id); }

    connectedCallback() {
      if (!this._bound) {
        this._bind();
        this._bound = true;
        this._firstLoad = true;
      }
      this._applyOptions();
      this.load();
    }

    disconnectedCallback() {
      this._timers.forEach(function (t) { clearTimeout(t); });
      this._timers = [];
    }

    attributeChangedCallback() {
      if (this._bound) this._applyOptions();
    }

    _applyOptions() {
      var heading = this.getAttribute('heading');
      this.$('mcTitle').textContent = heading || '模型设置';
      this.$('mcThinkingCard').hidden = this.getAttribute('show-thinking') === 'false';
    }

    /* ---------- 网络与提示 ---------- */

    async _api(path, opts) {
      var r = await fetch(this.apiBase + path, opts);
      if (!r.ok) {
        var data = await r.json().catch(function () { return {}; });
        throw new Error(data.detail || r.statusText || ('请求失败（' + r.status + '）'));
      }
      return r.json();
    }

    _toast(msg) {
      var t = this.$('mcToast');
      t.textContent = msg;
      t.hidden = false;
      var self = this;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(function () { t.hidden = true; }, 3500);
      this._timers.push(this._toastTimer);
    }

    _setNote(id, kind, text) {
      var el = this.$(id);
      el.className = 'mc-note' + (kind ? ' ' + kind : '');
      el.textContent = text;
    }

    _later(fn, ms) {
      var t = setTimeout(fn, ms);
      this._timers.push(t);
      return t;
    }

    /* ---------- 状态与渲染 ---------- */

    async load() {
      var self = this;
      try {
        this.status = await this._api('/status');
      } catch (err) {
        this._toast('没读到模型配置：' + err.message);
        return;
      }
      var providers = this.status.providers || [];
      if (!providers.length && this.selectedProvider === null && !this.catalogWanted) {
        this.catalogWanted = true;
      }
      if (!this.catalogWanted && !providers.some(function (p) { return p.id === self.selectedProvider; })) {
        var first = providers.find(function (p) { return p.id === self.status.model_provider; })
          || providers.find(function (p) { return p.has_key && p.enabled; })
          || providers[0];
        this.selectedProvider = first ? first.id : null;
        this.detailShownFor = null;
      }
      this.render();
      if (this._isChecking()) this._pollHealth();
      if (this._firstLoad) {
        this._firstLoad = false;
        this.dispatchEvent(new CustomEvent('mc-ready', { detail: this.status }));
      }
    }

    async refresh() {
      await this.load();
      return this.status;
    }

    render() {
      if (!this.status) return;
      this._renderThinking();
      this._renderActive();
      this._renderList();
      this._renderCatalog();
      this._renderMain();
      this.dispatchEvent(new CustomEvent('mc-change', { detail: this.status }));
    }

    _currentProvider() {
      var st = this.status || {};
      var id = this.selectedProvider;
      return (st.providers || []).find(function (p) { return p.id === id; }) || null;
    }

    _healthOkOf(id) {
      var d = (((this.status || {}).health || {}).providers || [])
        .find(function (x) { return x.provider === id; });
      return d ? !!d.ok : undefined;
    }

    _isChecking() {
      return ((this.status || {}).health || {}).state === 'pending';
    }

    async _afterChange() {
      await this.load();
      if (this._isChecking()) this._pollHealth();
    }

    _pollHealth() {
      var self = this;
      clearTimeout(this._pollTimer);
      var n = 0;
      function tick() {
        if (!self.isConnected) return;
        self.load().then(function () {
          if (!self.isConnected) return;
          if (self._isChecking() && n < 40) {
            self._pollTimer = setTimeout(tick, HEALTH_POLL_DELAYS[Math.min(n++, HEALTH_POLL_DELAYS.length - 1)]);
          }
        });
      }
      this._pollTimer = setTimeout(tick, HEALTH_POLL_DELAYS[0]);
    }

    _providerLabel(id) {
      var names = (this.status || {}).provider_labels || {};
      return names[id] || LEGACY_PROVIDER_LABELS[id] || id || '';
    }

    _logoMark(logo, name) {
      var symbol = BRAND_LOGOS[logo];
      if (symbol) {
        var ns = 'http://www.w3.org/2000/svg';
        var svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('class', 'mc-logo');
        svg.setAttribute('aria-hidden', 'true');
        var use = document.createElementNS(ns, 'use');
        use.setAttribute('href', '#' + symbol);
        svg.appendChild(use);
        return svg;
      }
      var tile = document.createElement('span');
      tile.className = 'mc-logo mc-logo-text';
      tile.setAttribute('aria-hidden', 'true');
      tile.textContent = (name || '?').trim().charAt(0);
      return tile;
    }

    _renderThinking() {
      var level = ((this.status || {}).thinking_level) || 'auto';
      var root = this.shadowRoot.querySelectorAll('#mcThinkingCard [data-level]');
      for (var i = 0; i < root.length; i++) {
        var btn = root[i];
        var on = btn.dataset.level === level;
        btn.classList.toggle('on', on);
        btn.setAttribute('aria-checked', on ? 'true' : 'false');
      }
    }

    _renderActive() {
      var st = this.status || {};
      var line = this.$('mcActiveLine');
      var enabled = st.enabled_providers || [];
      if (!enabled.length) {
        line.textContent = (st.providers || []).length
          ? '还没有能用的供应商：选中一家，把它的 Key 粘贴好（或打开它右上角的开关）。'
          : '还没有供应商：点右上角「添加供应商」，挑一家、填好 Key 就能用。';
      } else if (!st.model) {
        line.textContent = '还没定下用哪个模型：清单里一个打开着的模型都没有。'
          + '选中一家，给它「添加模型」，或打开模型右边的开关。';
      } else {
        var who = this._providerLabel(st.model_provider) || '供应商';
        var mode = st.model_auto ? '自动挑选' : '已指定';
        var tail = st.model_verified ? ' <span class="ok-mark">✓已验证</span>'
          : this._isChecking() ? '（正在体检…）' : '（还没验证：点右上角的 ↻ 重新体检）';
        line.innerHTML = '当前生效（' + mode + '）：<strong>'
          + esc(who + ' · ' + st.model) + '</strong>' + tail;
      }
      var autoBtn = this.$('mcAutoBtn');
      autoBtn.disabled = !enabled.length;
      autoBtn.classList.toggle('on', !!enabled.length && !!st.model_auto);
      this.$('mcRecheck').disabled = !enabled.length;
      this.$('mcRecheckState').textContent = this._isChecking() ? '正在体检，可能要十几秒…' : '';
    }

    _statusDot(p, checking, healthOk) {
      var dot = document.createElement('span');
      var state = '', title = '';
      if (!p.has_key) title = '还没填 Key';
      else if (!p.enabled) title = '已关掉（Key 还留着）';
      else if (checking) { state = 'busy'; title = '正在体检…'; }
      else if (healthOk === undefined) title = '还没体检：点右上角的 ↻ 重新体检';
      else if (healthOk) { state = 'ok'; title = '体检通过，能用'; }
      else { state = 'warn'; title = '上次体检没通过：检查 Key、网络或额度'; }
      dot.className = 'mc-dot' + (state ? ' dot-' + state : '');
      dot.title = title;
      dot.setAttribute('aria-label', title);
      dot.setAttribute('role', 'img');
      return dot;
    }

    _renderList() {
      var st = this.status || {};
      var providers = st.providers || [];
      var list = this.$('mcProviderList');
      var self = this;
      list.innerHTML = '';
      if (!providers.length) {
        var li = document.createElement('li');
        li.className = 'mc-list-empty';
        li.textContent = this.catalogWanted ? '点右边的卡片，把供应商加进来' : '还没有供应商';
        list.appendChild(li);
      }
      providers.forEach(function (p) {
        var on = p.id === self.selectedProvider && !self.catalogWanted;
        var row = document.createElement('button');
        row.type = 'button';
        row.className = 'mc-item' + (on ? ' selected' : '');
        row.dataset.provider = p.id;
        row.setAttribute('aria-pressed', on ? 'true' : 'false');
        row.title = p.name + '：点这里查看和修改它的设置';
        var name = document.createElement('span');
        name.className = 'mc-name';
        name.textContent = p.name;
        row.append(self._logoMark(p.logo, p.name), name,
          self._statusDot(p, self._isChecking(), self._healthOkOf(p.id)));
        var li = document.createElement('li');
        li.appendChild(row);
        list.appendChild(li);
      });
    }

    _renderCatalog() {
      var cards = (this.status || {}).catalog || [];
      var self = this;
      function fill(el, list, withCustom) {
        el.innerHTML = '';
        if (withCustom) el.appendChild(self._customCard());
        list.forEach(function (c) { el.appendChild(self._catalogCard(c)); });
      }
      fill(this.$('mcCatalogArk'), cards.filter(function (c) { return c.logo === 'ark'; }), false);
      fill(this.$('mcCatalogRest'), cards.filter(function (c) { return c.logo !== 'ark'; }), true);
    }

    _catalogCard(c) {
      var self = this;
      var card = document.createElement('button');
      card.type = 'button';
      card.className = 'mc-catalog-card';
      card.dataset.template = c.template;
      card.title = '添加「' + c.name + '」' + (c.hint ? '：' + c.hint : '');
      var text = document.createElement('span');
      text.className = 'mc-text';
      var title = document.createElement('b');
      title.textContent = c.name;
      text.appendChild(title);
      if (c.hint) {
        var small = document.createElement('small');
        small.textContent = c.hint;
        text.appendChild(small);
      }
      var chev = document.createElement('span');
      chev.className = 'mc-chev';
      chev.setAttribute('aria-hidden', 'true');
      chev.innerHTML = icon('chev-right');
      card.append(self._logoMark(c.logo, c.name), text, chev);
      return card;
    }

    _customCard() {
      var card = document.createElement('button');
      card.type = 'button';
      card.className = 'mc-catalog-card';
      card.dataset.act = 'custom-provider';
      card.title = '目录里没有的平台（比如中转站）从这里接：自己填名字和接口地址';
      var plus = document.createElement('span');
      plus.className = 'mc-logo mc-logo-text';
      plus.setAttribute('aria-hidden', 'true');
      plus.innerHTML = icon('plus');
      var text = document.createElement('span');
      text.className = 'mc-text';
      var title = document.createElement('b');
      title.textContent = '创建自定义供应商';
      var small = document.createElement('small');
      small.textContent = '目录里没有的平台：自己填名字和接口地址';
      text.append(title, small);
      var chev = document.createElement('span');
      chev.className = 'mc-chev';
      chev.setAttribute('aria-hidden', 'true');
      chev.innerHTML = icon('chev-right');
      card.append(plus, text, chev);
      return card;
    }

    _renderMain() {
      var p = this._currentProvider();
      var showDetail = !!p && !this.catalogWanted;
      this.$('mcCatalog').hidden = !this.catalogWanted;
      this.$('mcDetail').hidden = !showDetail;
      this.$('mcEmpty').hidden = this.catalogWanted || showDetail;
      if (showDetail) this._renderDetail(p);
    }

    _renderDetail(p) {
      var st = this.status || {};
      var checking = this._isChecking();
      var healthOk = this._healthOkOf(p.id);
      if (this.detailShownFor !== p.id) {
        this.detailShownFor = p.id;
        this.$('mcKeyInput').value = '';
        this.revealedKey = '';
        this._setKeyVisible(false);
        var self = this;
        ['mcKeyOut', 'mcUrlOut', 'mcModelOut'].forEach(function (id) {
          self._setNote(id, '', '');
        });
        this.$('mcBaseUrl').value = p.base_url;
        this._setMenu(false);
      }
      this.$('mcDetailTitle').textContent = p.name;
      this.$('mcDetailLogo').replaceChildren(this._logoMark(p.logo, p.name));

      var sw = this.$('mcEnabled');
      sw.checked = p.enabled;
      sw.title = p.enabled ? '点一下：暂时关掉这家（不参与挑选和体检，Key 还留着）' : '点一下：打开这家';
      sw.setAttribute('aria-label', '「' + p.name + '」的开关：关掉 = 暂时不参与挑选和体检（Key 还留着）');

      this.$('mcBaseUrl').placeholder = p.base_url;

      var keyInput = this.$('mcKeyInput');
      if (!keyInput.value) keyInput.placeholder = p.has_key ? KEY_DOTS : '输入 API Key';
      keyInput.title = p.has_key
        ? 'Key 已保存（圆点不是 Key 本身）。要换 Key：直接在这里粘贴新的，粘完自动验证并保存'
        : '粘贴这家的 Key：粘完自动验证并保存';
      var keyLink = this.$('mcKeyUrl');
      keyLink.hidden = !p.key_url;
      if (p.key_url) keyLink.href = p.key_url;

      var bits = [];
      bits.push(p.has_key ? 'Key 已保存' : '还没填 Key：粘贴到下面，粘完自动验证并保存');
      if (!p.enabled) bits.push('已关掉：暂时不参与挑选和体检');
      if (p.has_key && p.enabled) {
        if (checking) bits.push('正在体检…');
        else if (healthOk === undefined) bits.push('还没体检：点右上角的 ↻ 重新体检');
        else bits.push(healthOk ? '上次体检通过：Key 能用' : '上次体检没通过：检查 Key、网络或额度');
      }
      if (st.model_auto === false && st.model_provider === p.id && !p.enabled) {
        bits.push('现在指定的模型在这家：用之前记得把它打开');
      }
      this.$('mcMeta').textContent = bits.join(' · ');

      var manual = st.model_auto === false && st.model;
      var hints = [];
      if (manual) {
        hints.push(st.model_provider === p.id
          ? '已指定用「' + st.model + '」：想换一个，点别的模型的名字；点上方「自动（推荐）」回到自动挑选。'
          : '现在指定用的是「' + (this._providerLabel(st.model_provider) || '别家') + ' · ' + st.model
            + '」。点这里某个模型的名字，就换成用它。');
      } else {
        hints.push('自动挑选：软件按清单从上到下，挑第一个能调通的模型。想固定用某个，点它的名字。');
      }
      hints.push(p.supports_model_list
        ? '清单里没有的模型，点「添加模型」手动加，或点「从账号同步」自动拉取。'
        : '订阅套餐不提供在线模型列表：要加模型就点「添加模型」，名字照套餐页面上写的填。');
      hints.push('想确认某个模型能不能用，点它右边的插头实测一次，结果会标在名字旁边。');
      this.$('mcModelsHint').textContent = hints.join(' ');
      this.$('mcSyncBtn').hidden = !p.supports_model_list;
      this._renderModels(p);
    }

    _renderModels(p) {
      var box = this.$('mcModels');
      box.innerHTML = '';
      if (!p.models.length) {
        var empty = document.createElement('div');
        empty.className = 'mc-model-empty';
        empty.textContent = '这家还没有模型：点右上角的「添加模型」加一个。';
        box.appendChild(empty);
        return;
      }
      var self = this;
      p.models.forEach(function (m) { box.appendChild(self._modelRow(p, m)); });
    }

    _iconBtn(act, name, title) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'mc-icon-btn';
      b.dataset.act = act;
      b.title = title;
      b.setAttribute('aria-label', title);
      b.innerHTML = icon(name);
      return b;
    }

    _modelRow(p, m) {
      var st = this.status || {};
      var inUse = st.model_provider === p.id && st.model === m.id;
      var row = document.createElement('div');
      row.className = 'mc-model-row' + (inUse ? ' in-use' : '');
      row.dataset.model = m.id;

      var name = document.createElement('button');
      name.type = 'button';
      name.className = 'mc-model-name';
      name.textContent = m.id;
      name.dataset.act = 'use-model';
      name.title = inUse && st.model_auto === false ? '正在用这个模型'
        : m.enabled ? '点一下：指定都用这个模型（当场验证能不能调通）'
          : '这个模型的开关关着：先打开右边的开关，才能指定用它';
      row.appendChild(name);

      if (m.check === true || m.check === false) {
        var mark = document.createElement('span');
        mark.className = 'mc-check ' + (m.check ? 'ok' : 'fail');
        mark.textContent = m.check ? '✓实测通过' : '✗没调通';
        mark.title = m.check
          ? '本次运行里真调过「' + m.id + '」：能正常回话。想再确认一次就点右边的插头。'
          : '本次运行里真调过「' + m.id + '」：没调通（可能是名字不对、账号没开通、'
            + '额度不够或网络暂时不通）。点右边的插头再测一次会说明原因。';
        row.appendChild(mark);
      }

      if (inUse) {
        var badge = document.createElement('span');
        badge.className = 'mc-badge';
        badge.textContent = (st.model_auto === false ? '已指定' : '自动选中')
          + (st.model_verified ? '·✓已验证' : '·还没验证');
        row.appendChild(badge);
      }

      var tools = document.createElement('span');
      tools.className = 'mc-row-tools';
      tools.append(
        this._iconBtn('test-model', 'plug', '测试「' + m.id + '」：拿这家的 Key 发一次极小请求'),
        this._iconBtn('edit-model', 'pencil', '编辑「' + m.id + '」：改名字或删除')
      );
      var sw = document.createElement('input');
      sw.type = 'checkbox';
      sw.className = 'mc-switch';
      sw.checked = m.enabled;
      sw.dataset.act = 'toggle-model';
      sw.title = '开关：开 = 自动挑选时会考虑它；关 = 跳过它（清单里留着）';
      sw.setAttribute('aria-label', '「' + m.id + '」的开关：开 = 参与自动挑选，关 = 跳过它');
      tools.appendChild(sw);
      row.appendChild(tools);
      return row;
    }

    _setKeyVisible(show) {
      this.$('mcKeyInput').type = show ? 'text' : 'password';
      this.$('mcKeyToggle').setAttribute('aria-pressed', show ? 'true' : 'false');
      this.$('mcKeyToggle').innerHTML = icon(show ? 'eye-off' : 'eye');
    }

    _setMenu(open) {
      this.$('mcMenu').hidden = !open;
      this.$('mcMoreBtn').setAttribute('aria-expanded', String(open));
    }

    _providerUrl() {
      return '/providers/' + encodeURIComponent(this.selectedProvider);
    }

    /* ---------- 事件绑定 ---------- */

    _bind() {
      var self = this;

      this.$('mcProviderList').addEventListener('click', function (e) {
        var row = e.target.closest('.mc-item');
        if (!row) return;
        self.selectedProvider = row.dataset.provider;
        self.catalogWanted = false;
        self.detailShownFor = null;
        self.render();
      });

      this.$('mcAddProvider').addEventListener('click', function () {
        self.catalogWanted = true;
        self.render();
      });
      this.$('mcEmptyAdd').addEventListener('click', function () {
        self.catalogWanted = true;
        self.render();
      });
      this.$('mcCatalogBack').addEventListener('click', function () {
        self.catalogWanted = false;
        self.render();
      });

      this.$('mcCatalog').addEventListener('click', async function (e) {
        var card = e.target.closest('.mc-catalog-card');
        if (!card) return;
        if (card.dataset.act === 'custom-provider') {
          self.$('mcCustomName').value = '';
          self.$('mcCustomUrl').value = '';
          self.$('mcCustomErr').textContent = '';
          self.$('mcDlgCustom').showModal();
          return;
        }
        try {
          var r = await self._api('/providers', {
            method: 'POST', headers: JSON_HEADERS,
            body: JSON.stringify({ template: card.dataset.template })
          });
          self.selectedProvider = r.provider.id;
          self.catalogWanted = false;
          self.detailShownFor = null;
          await self._afterChange();
          self._toast('已添加「' + r.provider.name + '」：把它的 Key 粘贴到右边就能用');
          self.$('mcKeyInput').focus();
        } catch (err) {
          self._toast('没添加成功：' + err.message);
        }
      });

      // 自定义供应商
      this.$('mcCustomCancel').addEventListener('click', function () { self.$('mcDlgCustom').close(); });
      this.$('mcDlgCustomForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        var name = self.$('mcCustomName').value.trim();
        if (!name) { self.$('mcCustomErr').textContent = '先给这家起个名字'; return; }
        var submit = e.target.querySelector('button[type="submit"]');
        submit.disabled = true;
        self.$('mcCustomErr').textContent = '';
        try {
          var r = await self._api('/providers', {
            method: 'POST', headers: JSON_HEADERS,
            body: JSON.stringify({ name: name, base_url: self.$('mcCustomUrl').value.trim() })
          });
          self.$('mcDlgCustom').close();
          self.selectedProvider = r.provider.id;
          self.catalogWanted = false;
          self.detailShownFor = null;
          await self._afterChange();
          self._toast('已添加「' + r.provider.name + '」：把它的 Key 粘贴到右边就能用');
          self.$('mcKeyInput').focus();
        } catch (err) { self.$('mcCustomErr').textContent = err.message; }
        submit.disabled = false;
      });

      // 这家的开关
      this.$('mcEnabled').addEventListener('change', async function () {
        var sw = self.$('mcEnabled');
        var p = self._currentProvider();
        if (!p) return;
        try {
          await self._api(self._providerUrl(), {
            method: 'PATCH', headers: JSON_HEADERS,
            body: JSON.stringify({ enabled: sw.checked })
          });
          self._toast(sw.checked ? '已打开「' + p.name + '」：重新参与挑选和体检（Key 还留着）'
            : '已关掉「' + p.name + '」：暂时不参与挑选和体检，Key 还留着');
          await self._afterChange();
        } catch (err) {
          sw.checked = p.enabled;
          self._toast('没保存成功：' + err.message);
        }
      });

      // Base URL
      this.$('mcBaseUrl').addEventListener('change', async function () {
        var input = self.$('mcBaseUrl');
        var p = self._currentProvider();
        if (!p) return;
        var value = input.value.trim();
        if (value === p.base_url) { input.value = p.base_url; return; }
        self._setNote('mcUrlOut', '', '正在保存接口地址…');
        try {
          var r = await self._api(self._providerUrl(), {
            method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify({ base_url: value })
          });
          input.value = r.provider.base_url;
          self._setNote('mcUrlOut', 'ok', '接口地址已保存。');
          await self._afterChange();
        } catch (err) {
          input.value = p.base_url;
          self._setNote('mcUrlOut', 'fail', err.message);
        }
      });

      // 小眼睛
      this.$('mcKeyToggle').addEventListener('click', async function () {
        var input = self.$('mcKeyInput');
        var p = self._currentProvider();
        if (!p) return;
        if (input.type === 'text') {
          if (self.revealedKey && input.value === self.revealedKey) {
            input.value = '';
            input.placeholder = p.has_key ? KEY_DOTS : '输入 API Key';
          }
          self.revealedKey = '';
          self._setKeyVisible(false);
          return;
        }
        if (!input.value && p.has_key) {
          try {
            var r = await self._api(self._providerUrl() + '/key');
            if (p.id === self.selectedProvider && r.api_key) {
              self.revealedKey = r.api_key;
              input.value = r.api_key;
              self._setKeyVisible(true);
              return;
            }
          } catch (err) {
            self._toast('取 Key 没成功：' + err.message);
          }
        }
        self._setKeyVisible(true);
      });
      this.$('mcKeyInput').addEventListener('input', function () { self.revealedKey = ''; });
      this.$('mcKeyInput').addEventListener('paste', function () {
        self._later(function () { self._saveKey(); }, 0);
      });
      this.$('mcKeyInput').addEventListener('change', function () { self._saveKey(); });
      this.$('mcKeyInput').addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        self.$('mcKeyInput').blur();
      });

      // 模型行
      this.$('mcModels').addEventListener('click', function (e) {
        var btn = e.target.closest('[data-act]');
        if (!btn) return;
        var model = btn.closest('.mc-model-row').dataset.model;
        if (btn.dataset.act === 'use-model') self._useModel(model);
        else if (btn.dataset.act === 'test-model') self._testModel(model);
        else if (btn.dataset.act === 'edit-model') {
          self.editingModel = model;
          self.$('mcModelEditName').value = model;
          self.$('mcModelEditErr').textContent = '';
          self.$('mcDlgModelEdit').showModal();
        }
      });
      this.$('mcModels').addEventListener('change', function (e) {
        var sw = e.target.closest('input[data-act="toggle-model"]');
        if (sw) self._toggleModel(sw.closest('.mc-model-row').dataset.model, sw.checked);
      });

      // 添加模型
      this.$('mcAddModelBtn').addEventListener('click', function () {
        self.$('mcModelAddName').value = '';
        self.$('mcModelAddErr').textContent = '';
        self.$('mcDlgModelAdd').showModal();
      });
      this.$('mcModelAddCancel').addEventListener('click', function () { self.$('mcDlgModelAdd').close(); });
      this.$('mcDlgModelAddForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        var p = self._currentProvider();
        if (!p) return;
        var model = self.$('mcModelAddName').value.trim();
        if (!model) { self.$('mcModelAddErr').textContent = '先把模型名字填进来'; return; }
        try {
          await self._api(self._providerUrl() + '/models', {
            method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ model: model })
          });
          self.$('mcDlgModelAdd').close();
          self._toast('已添加「' + model + '」');
          await self._afterChange();
        } catch (err) { self.$('mcModelAddErr').textContent = err.message; }
      });

      // 编辑模型
      this.$('mcModelEditCancel').addEventListener('click', function () { self.$('mcDlgModelEdit').close(); });
      this.$('mcDlgModelEditForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        var p = self._currentProvider();
        if (!p || !self.editingModel) return;
        var next = self.$('mcModelEditName').value.trim();
        if (next === self.editingModel) { self.$('mcDlgModelEdit').close(); return; }
        try {
          await self._api(self._providerUrl() + '/models', {
            method: 'PATCH', headers: JSON_HEADERS,
            body: JSON.stringify({ model: self.editingModel, new_model: next })
          });
          self.$('mcDlgModelEdit').close();
          self._toast('模型名字已改');
          await self._afterChange();
        } catch (err) { self.$('mcModelEditErr').textContent = err.message; }
      });
      this.$('mcModelEditDelete').addEventListener('click', function () {
        self.$('mcDlgModelDelete').querySelector('.mc-confirm-text') &&
          (self.$('mcDlgModelDelete').querySelector('.mc-confirm-text').innerHTML =
            '删除「<strong>' + esc(self.editingModel) + '</strong>」后，这家就不能再用它了。'
            + '<strong>此操作无法撤回。</strong>');
        self.$('mcModelDeleteErr').textContent = '';
        self.$('mcDlgModelDelete').showModal();
      });
      this.$('mcModelDeleteCancel').addEventListener('click', function () { self.$('mcDlgModelDelete').close(); });
      this.$('mcDlgModelDeleteForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        var p = self._currentProvider();
        var model = self.editingModel;
        if (!p || !model) return;
        try {
          await self._api(self._providerUrl() + '/models?model=' + encodeURIComponent(model), { method: 'DELETE' });
          self.$('mcDlgModelDelete').close();
          self.$('mcDlgModelEdit').close();
          self._toast('已删除「' + model + '」');
          await self._afterChange();
        } catch (err) { self.$('mcModelDeleteErr').textContent = err.message; }
      });

      // 从账号同步
      this.$('mcSyncBtn').addEventListener('click', async function () {
        var btn = self.$('mcSyncBtn');
        if (btn.disabled) return;
        btn.disabled = true;
        self._setNote('mcModelOut', '', '正在从这家的账号拉取模型列表…');
        try {
          var r = await self._api(self._providerUrl() + '/models/sync', { method: 'POST' });
          if (r.ok) {
            var n = r.added.length;
            self._setNote('mcModelOut', 'ok', n
              ? '同步完成：新加了 ' + n + ' 个模型（' + r.added.slice(0, 3).join('、')
                + (n > 3 ? ' 等' : '') + '）。'
              : '同步完成：账号下的对话模型都已经在清单里了。');
          } else {
            self._setNote('mcModelOut', 'fail', r.message);
          }
        } catch (err) {
          self._setNote('mcModelOut', 'fail', '同步没成功：' + err.message);
        }
        btn.disabled = false;
        await self._afterChange();
      });

      // 自动（推荐）
      this.$('mcAutoBtn').addEventListener('click', async function () {
        var btn = self.$('mcAutoBtn');
        btn.disabled = true;
        try {
          await self._api('/config', {
            method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ model_auto: true })
          });
          self._toast('已回到自动挑选：软件会用清单里验证过能用的模型');
          await self._afterChange();
        } catch (err) { self._toast('没保存成功：' + err.message); }
        btn.disabled = false;
      });

      // 重新体检
      this.$('mcRecheck').addEventListener('click', async function () {
        var btn = self.$('mcRecheck');
        btn.disabled = true;
        try {
          await self._api('/health/recheck', { method: 'POST' });
          await self.load();
          self._pollHealth();
        } catch (err) { self._toast('体检没触发成功：' + err.message); }
        btn.disabled = false;
      });

      // 思考深度
      this.$('mcThinkingCard').addEventListener('click', async function (e) {
        var btn = e.target.closest('[data-level]');
        if (!btn) return;
        var level = btn.dataset.level;
        if ((((self.status || {}).thinking_level) || 'auto') === level) return;
        try {
          await self._api('/config', {
            method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ thinking_level: level })
          });
          await self.load();
          self._toast('已切换思考深度：' + THINKING_LABELS[level]);
        } catch (err) { self._toast('没保存成功：' + err.message); }
      });

      // ⋯ 菜单
      this.$('mcMoreBtn').addEventListener('click', function (e) {
        e.stopPropagation();
        self._setMenu(self.$('mcMenu').hidden);
      });
      this.shadowRoot.addEventListener('click', function (e) {
        if (!e.target.closest('.mc-more-wrap')) self._setMenu(false);
      });
      this.$('mcRenameBtn').addEventListener('click', function () {
        self._setMenu(false);
        var p = self._currentProvider();
        if (!p) return;
        self.$('mcRenameName').value = p.name;
        self.$('mcRenameErr').textContent = '';
        self.$('mcDlgRename').showModal();
      });
      this.$('mcRenameCancel').addEventListener('click', function () { self.$('mcDlgRename').close(); });
      this.$('mcDlgRenameForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        var p = self._currentProvider();
        if (!p) return;
        try {
          await self._api(self._providerUrl(), {
            method: 'PATCH', headers: JSON_HEADERS,
            body: JSON.stringify({ name: self.$('mcRenameName').value.trim() })
          });
          self.$('mcDlgRename').close();
          self._toast('名字已改');
          await self._afterChange();
        } catch (err) { self.$('mcRenameErr').textContent = err.message; }
      });

      // 删除供应商
      this.$('mcDeleteProviderBtn').addEventListener('click', function () {
        self._setMenu(false);
        var p = self._currentProvider();
        if (!p) return;
        self.deleteProviderId = p.id;
        var box = self.$('mcDlgDeleteProvider').querySelector('.mc-confirm-text');
        if (box) {
          box.innerHTML = '删除「<strong>' + esc(p.name) + '</strong>」后，它的 Key 和模型清单会一起删掉，'
            + '不能再用它。<strong>此操作无法撤回。</strong>';
        }
        self.$('mcDeleteProviderErr').textContent = '';
        self.$('mcDlgDeleteProvider').showModal();
      });
      this.$('mcDeleteProviderCancel').addEventListener('click', function () {
        self.$('mcDlgDeleteProvider').close();
      });
      this.$('mcDlgDeleteProviderForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        try {
          await self._api('/providers/' + encodeURIComponent(self.deleteProviderId), { method: 'DELETE' });
          self.$('mcDlgDeleteProvider').close();
          self.selectedProvider = null;
          self.detailShownFor = null;
          self.catalogWanted = false;
          await self._afterChange();
          self._toast('已删除');
        } catch (err) { self.$('mcDeleteProviderErr').textContent = err.message; }
      });
    }

    async _saveKey() {
      var input = this.$('mcKeyInput');
      var key = input.value.trim();
      var pid = this.selectedProvider;
      if (!key || this.keyBusy || !pid) return;
      this.keyBusy = true;
      this._setNote('mcKeyOut', '', '正在验证这家的 Key，最多十几秒…');
      var saved = false;
      try {
        var r = await this._api('/providers/' + encodeURIComponent(pid) + '/key', {
          method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ api_key: key })
        });
        saved = !!r.ok;
        if (pid === this.selectedProvider) {
          if (saved) {
            if (input.value.trim() === key) {
              input.value = '';
              this.revealedKey = '';
              this._setKeyVisible(false);
            }
            this._setNote('mcKeyOut', 'ok', 'Key 已保存，这家可以用了。');
            this._toast('Key 已保存');
          } else {
            this._setNote('mcKeyOut', 'fail', r.message);
          }
        }
      } catch (err) {
        this._setNote('mcKeyOut', 'fail', '没保存成功：' + err.message);
      }
      this.keyBusy = false;
      if (saved) await this._afterChange();
    }

    async _useModel(model) {
      var st = this.status || {};
      if (st.model_auto === false && st.model === model && st.model_provider === this.selectedProvider) return;
      var box = this.$('mcModelsBox');
      box.classList.add('busy');
      this._setNote('mcModelOut', '', '正在验证「' + model + '」能不能调通，最多十几秒…');
      try {
        var r = await this._api('/config', {
          method: 'POST', headers: JSON_HEADERS,
          body: JSON.stringify({ model_auto: false, model: model, model_provider: this.selectedProvider })
        });
        this._setNote('mcModelOut', 'ok', '');
        await this._afterChange();
        this._toast('已指定用「' + model + '」' + (r.model_notice ? '；' + r.model_notice : ''));
      } catch (err) {
        this._setNote('mcModelOut', 'fail', err.message);
      }
      box.classList.remove('busy');
    }

    async _testModel(model) {
      this._setNote('mcModelOut', '', '正在测试「' + model + '」，最多十几秒…');
      var typed = this.$('mcKeyInput').value.trim();
      try {
        var r = await this._api(this._providerUrl() + '/models/test', {
          method: 'POST', headers: JSON_HEADERS,
          body: JSON.stringify(typed ? { model: model, api_key: typed } : { model: model })
        });
        this._setNote('mcModelOut', r.ok ? 'ok' : 'fail', r.message);
        await this.load();
      } catch (err) {
        this._setNote('mcModelOut', 'fail', '测不成：' + err.message);
      }
    }

    async _toggleModel(model, on) {
      try {
        await this._api(this._providerUrl() + '/models/enabled', {
          method: 'PATCH', headers: JSON_HEADERS,
          body: JSON.stringify({ model: model, enabled: on })
        });
        this._toast(on ? '已打开「' + model + '」：自动挑选时会考虑它'
          : '已关掉「' + model + '」：自动挑选会跳过它（清单里留着）');
        await this._afterChange();
      } catch (err) {
        this._toast('没保存成功：' + err.message);
        this.render();
      }
    }
  }

  customElements.define('model-config-panel', ModelConfigPanel);
  window.ModelConfigPanel = ModelConfigPanel;
  window.ModelConfig = {
    Panel: ModelConfigPanel,
    create: function (options) {
      options = options || {};
      var el = document.createElement('model-config-panel');
      if (options.apiBase) el.setAttribute('api-base', options.apiBase);
      if (options.cssHref) el.setAttribute('css-href', options.cssHref);
      if (options.showThinking === false) el.setAttribute('show-thinking', 'false');
      if (options.heading) el.setAttribute('heading', options.heading);
      return el;
    }
  };
})();
