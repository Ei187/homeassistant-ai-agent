/**
 * AI Agent Pro Dashboard Panel & Card
 * Pure Vanilla Web Component with Modern Glassmorphism, Quick "+" Settings Drawer,
 * Full Markdown Parsing with Code Highlighting, Copy Button & ChatGPT-Style Message Editing.
 */

class AIAgentPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.hass = null;
    this.settings = this.loadCachedSettings();
    this.resolvedModels = this.loadResolvedModels();
    this.chatHistory = this.loadChatHistory();
    this.pendingProposals = [];
    this.isLoading = false;
    this.activeFallbackNotice = null;
    this.isDrawerOpen = false;
    this.editingIndex = null;
    this._lastCodeBlocks = [];
  }

  loadResolvedModels() {
    try {
      const saved = localStorage.getItem('ai_agent_pro_resolved_models');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') return parsed;
      }
    } catch (_) {}
    const legacy = localStorage.getItem('ai_agent_pro_resolved_model');
    if (legacy && typeof legacy === 'string' && legacy !== 'free-engine') {
      return { [this.settings?.provider || 'gemini']: legacy };
    }
    return {};
  }

  saveResolvedModels() {
    try {
      localStorage.setItem('ai_agent_pro_resolved_models', JSON.stringify(this.resolvedModels || {}));
    } catch (_) {}
  }

  setResolvedModel(provider, model) {
    if (!provider || !model || model === 'free-engine') return;
    if (!this.resolvedModels) this.resolvedModels = {};
    this.resolvedModels[provider] = model;
    this.saveResolvedModels();
    this.updateHeaderStatusPill();
  }

  getResolvedModel(provider) {
    const prov = provider || this.settings?.provider;
    return (this.resolvedModels && this.resolvedModels[prov]) || '';
  }

  loadCachedSettings() {
    const defaults = {
      agent_role: 'omni',
      provider: 'openai',
      model: 'auto-latest',
      thinking_level: 'high',
      require_approval: true,
      api_key: '',
      api_keys: {},
      base_url: 'https://api.openai.com/v1',
    };
    try {
      const saved = localStorage.getItem('ai_agent_pro_settings');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed === 'object') {
          return { ...defaults, ...parsed };
        }
      }
    } catch (e) {}
    return defaults;
  }

  saveCachedSettings() {
    try {
      localStorage.setItem('ai_agent_pro_settings', JSON.stringify(this.settings));
    } catch (e) {}
  }

  loadChatHistory() {
    try {
      const saved = localStorage.getItem('ai_agent_pro_chat_history');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          parsed.forEach((m) => {
            delete m.fallbackNotice;
          });
          return parsed;
        }
      }
    } catch (e) {
      console.warn('Could not load chat history from localStorage', e);
    }
    return [];
  }

  saveChatHistory() {
    try {
      const toSave = this.chatHistory.slice(-40);
      localStorage.setItem('ai_agent_pro_chat_history', JSON.stringify(toSave));
    } catch (e) {
      console.warn('Could not save chat history to localStorage', e);
    }
  }

  startNewChat() {
    this.chatHistory = [];
    this.pendingProposals = [];
    this.activeFallbackNotice = null;
    this.editingIndex = null;
    try {
      localStorage.removeItem('ai_agent_pro_chat_history');
    } catch (e) {}
    this.showToast('✨ נפתחה שיחה חדשה!');
    this.render();
  }

  set hass(val) {
    this._hass = val;
    if (!this._initialized && val) {
      this._initialized = true;
      this.loadSettings();
      this.loadPendingActions();
    }
  }

  get hass() {
    return this._hass;
  }

  async loadSettings() {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({ type: 'ai_agent/get_settings' });
      if (res) {
        this.settings = { ...this.settings, ...res };
        if (!this.settings.api_keys) this.settings.api_keys = {};
        if (res.api_keys && typeof res.api_keys === 'object') {
          this.settings.api_keys = { ...this.settings.api_keys, ...res.api_keys };
        }
        if (this.settings.provider && this.settings.api_keys[this.settings.provider]) {
          this.settings.api_key = this.settings.api_keys[this.settings.provider];
        } else if (this.settings.api_key && this.settings.provider) {
          this.settings.api_keys[this.settings.provider] = this.settings.api_key;
        }
        if (res.resolved_model && res.resolved_model !== 'free-engine') {
          this.setResolvedModel(this.settings.provider, res.resolved_model);
        }
        this.saveCachedSettings();
        this.syncSettingsToUI();
      }
    } catch (e) {
      console.warn('Could not load AI Agent settings from WS', e);
    }
  }

  syncSettingsToUI() {
    this.updateHeaderStatusPill();
    const root = this.shadowRoot;
    if (!root) return;

    const roleSel = root.querySelector('#agent-role-select');
    const provSel = root.querySelector('#provider-select');
    const modelInp = root.querySelector('#model-input');
    const keyInp = root.querySelector('#api-key-input');

    if (roleSel && this.settings.agent_role) roleSel.value = this.settings.agent_role;
    if (provSel && this.settings.provider) provSel.value = this.settings.provider;
    if (modelInp && this.settings.model) modelInp.value = this.settings.model;

    if (this.settings.api_keys && this.settings.provider) {
      const pKey = this.settings.api_keys[this.settings.provider];
      if (pKey !== undefined) {
        this.settings.api_key = pKey;
      }
    }
    if (keyInp) keyInp.value = this.settings.api_key || '';

    const autoBadgeBtn = root.querySelector('#auto-model-badge-btn');
    if (autoBadgeBtn) {
      const curModel = (modelInp ? modelInp.value : this.settings.model) || '';
      const isAuto = (!curModel || curModel.trim() === 'auto-latest' || curModel.trim() === 'auto');
      autoBadgeBtn.style.background = isAuto ? 'linear-gradient(135deg, rgba(10, 132, 255, 0.4), rgba(191, 90, 242, 0.4))' : 'rgba(255, 255, 255, 0.08)';
      autoBadgeBtn.style.borderColor = isAuto ? '#0a84ff' : 'rgba(255, 255, 255, 0.16)';
      autoBadgeBtn.style.boxShadow = isAuto ? '0 4px 14px rgba(10, 132, 255, 0.35)' : 'none';
    }

    root.querySelectorAll('.thinking-pill').forEach((pill) => {
      const lvl = pill.getAttribute('data-level');
      pill.classList.toggle('active', lvl === this.settings.thinking_level);
    });
  }

  closeDrawer() {
    this.isDrawerOpen = false;
    const root = this.shadowRoot;
    if (!root) return;
    const drawer = root.querySelector('#drawer');
    const plusBtn = root.querySelector('#plus-btn');
    if (drawer) drawer.classList.remove('open');
    if (plusBtn) plusBtn.classList.remove('active');
  }

  openDrawer() {
    this.isDrawerOpen = true;
    const root = this.shadowRoot;
    if (!root) return;
    const drawer = root.querySelector('#drawer');
    const plusBtn = root.querySelector('#plus-btn');
    if (drawer) drawer.classList.add('open');
    if (plusBtn) plusBtn.classList.add('active');

    this.syncSettingsToUI();
  }

  toggleDrawer() {
    if (this.isDrawerOpen) {
      this.closeDrawer();
    } else {
      this.openDrawer();
    }
  }

  getProviderKeyHint(prov) {
    const p = prov || this.settings?.provider || 'openai';
    if (p === 'gemini') {
      return `🎁 <b>Google Gemini:</b> מודל Gemini 2.5 Flash חינמי לחלוטין (ללא אשראי) ב-Google AI Studio: <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener" style="color: #64d2ff; text-decoration: underline; font-weight: 600;">לחץ כאן להפקת מפתח חינם</a>`;
    }
    if (p === 'groq') {
      return `⚡ <b>GroqCloud:</b> חינם ב-100% ללא כרטיס אשראי (Llama 3.3 70B במהירות שיא): <a href="https://console.groq.com/keys" target="_blank" rel="noopener" style="color: #64d2ff; text-decoration: underline; font-weight: 600;">לחץ כאן להפקת מפתח Groq חינם</a>`;
    }
    if (p === 'openai') {
      return `ℹ️ <b>OpenAI:</b> דורש מפתח מ-<a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener" style="color: #64d2ff; text-decoration: underline; font-weight: 600;">platform.openai.com</a>. (באתר chatgpt.com השיחה חינם, אך ה-API דורש מפתח. למסלול חינמי ב-Home Assistant ללא עלות, בחר ב-<b>Google Gemini</b> או <b>GroqCloud</b> למעלה!).`;
    }
    if (p === 'anthropic') {
      return `ℹ️ <b>Anthropic Claude:</b> דורש מפתח מ-<a href="https://console.anthropic.com/" target="_blank" rel="noopener" style="color: #64d2ff; text-decoration: underline; font-weight: 600;">console.anthropic.com</a>.`;
    }
    if (p === 'deepseek') {
      return `ℹ️ <b>DeepSeek:</b> דורש מפתח מ-<a href="https://platform.deepseek.com/" target="_blank" rel="noopener" style="color: #64d2ff; text-decoration: underline; font-weight: 600;">platform.deepseek.com</a>.`;
    }
    if (p === 'openrouter') {
      return `🎁 <b>OpenRouter:</b> דורש מפתח מ-<a href="https://openrouter.ai/keys" target="_blank" rel="noopener" style="color: #64d2ff; text-decoration: underline; font-weight: 600;">openrouter.ai</a> (כולל מודלים חינמיים המסומנים :free).`;
    }
    return `ℹ️ שרת מקומי (Ollama/LM Studio): ללא צורך במפתח אם השרת מוגדר ללא אימות.`;
  }

  updateHeaderStatusPill() {
    const root = this.shadowRoot;
    if (!root) return;
    const pill = root.querySelector('#status-pill-btn');
    if (!pill) return;
    const s = this.settings;
    const hasKey = !!(s.api_key && s.api_key.trim());
    const provName = {
      openai: 'OpenAI (ChatGPT)',
      gemini: 'Google Gemini',
      groq: 'GroqCloud',
      anthropic: 'Anthropic Claude',
      deepseek: 'DeepSeek',
      openrouter: 'OpenRouter',
      custom: 'Custom',
    }[s.provider] || s.provider;

    let modelDisplay = s.model || 'auto-latest';
    if (modelDisplay === 'auto-latest' || modelDisplay === 'auto' || !modelDisplay) {
      const activeResolved = this.getResolvedModel(s.provider);
      if (activeResolved && activeResolved !== 'free-engine') {
        modelDisplay = `Auto (${activeResolved})`;
      } else {
        modelDisplay = 'Auto';
      }
    }

    const dotColor = hasKey ? '#0a84ff' : '#ff9f0a';
    const statusText = hasKey
      ? `${provName} • ${modelDisplay}`
      : `מצב מקומי (${provName} - חסר API Key)`;

    pill.innerHTML = `
      <div class="dot-indicator" style="background: ${dotColor}; box-shadow: 0 0 8px ${dotColor};"></div>
      <span>${statusText}</span>
      <span style="font-size: 11px; opacity: 0.7;">(חשיבה: ${(s.thinking_level || 'off').toUpperCase()})</span>
      <span style="margin-right: 4px;">⚙️</span>
    `;
  }

  async saveSettings() {
    if (!this._hass) return;
    if (!this.settings.api_keys) this.settings.api_keys = {};
    if (this.settings.provider) {
      this.settings.api_keys[this.settings.provider] = this.settings.api_key || '';
    }
    const payload = {
      type: 'ai_agent/save_settings',
      agent_role: this.settings.agent_role,
      provider: this.settings.provider,
      model: this.settings.model,
      thinking_level: this.settings.thinking_level,
      api_key: this.settings.api_key || '',
      api_keys: this.settings.api_keys || {},
      base_url: this.settings.base_url || '',
      require_approval: this.settings.require_approval !== false,
    };
    try {
      const res = await this._hass.callWS(payload);
      if (res && res.settings) {
        this.settings = { ...this.settings, ...res.settings };
        if (res.settings.api_keys && typeof res.settings.api_keys === 'object') {
          this.settings.api_keys = { ...this.settings.api_keys, ...res.settings.api_keys };
        }
        if (this.settings.provider && this.settings.api_keys[this.settings.provider]) {
          this.settings.api_key = this.settings.api_keys[this.settings.provider];
        }
        if (res.settings.resolved_model && res.settings.resolved_model !== 'free-engine') {
          this.setResolvedModel(this.settings.provider, res.settings.resolved_model);
        }
      }
      this.saveCachedSettings();
      this.closeDrawer();
      this.syncSettingsToUI();
      this.renderMessages();
      this.showToast('✅ ההגדרות עודכנו בהצלחה!');
    } catch (e) {
      this.showToast('⚠️ שגיאה בשמירה: ' + (e.message || e));
    }
  }

  async loadPendingActions() {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({ type: 'ai_agent/get_pending_actions' });
      if (res && res.actions) {
        this.pendingProposals = res.actions;
        this.render();
      }
    } catch (e) {
      console.warn('Could not load pending actions', e);
    }
  }

  async resolveAction(actionId, approved) {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({
        type: 'ai_agent/resolve_action',
        action_id: actionId,
        approved: approved,
      });
      if (res && res.success) {
        this.showToast(approved ? '✅ הפעולה אושרה ובוצעה בהצלחה!' : '❌ הפעולה נדחתה');
        this.pendingProposals = this.pendingProposals.filter((p) => p.id !== actionId);
        this.chatHistory.push({
          role: 'assistant',
          content: approved
            ? '✅ **הפעולה אושרה והוטמעה במערכת בהצלחה!** היא פעילה כעת ב-Home Assistant.'
            : '❌ **הפעולה בוטלה.** לא בוצעו שינויים במערכת.',
        });
        this.saveChatHistory();
        this.render();
        this.scrollToBottom();
      } else {
        this.showToast('⚠️ שגיאה: ' + (res.error || 'נכשלה הפעולה'));
      }
    } catch (e) {
      this.showToast('❌ שגיאה: ' + e.message);
    }
  }

  async sendMessage(text) {
    if (!text || !text.trim() || this.isLoading || !this._hass) return;

    this.isLoading = true;
    this.chatHistory.push({ role: 'user', content: text });

    // Create assistant message placeholder for instant live streaming
    const assistantMsg = {
      role: 'assistant',
      content: '',
      proposals: [],
      isStreaming: true,
      streamingStatus: 'מתחבר לסוכן...',
    };
    this.chatHistory.push(assistantMsg);
    this.saveChatHistory();
    this.render();
    this.scrollToBottom();

    let unsub = null;
    let completed = false;

    // Typewriter Smoothing State
    let targetText = '';
    let renderedText = '';
    let streamTimer = null;
    let isServerDone = false;
    let doneReply = '';
    let doneProposals = [];
    let doneFallbackNotice = null;

    const stopTypewriter = () => {
      if (streamTimer) {
        clearInterval(streamTimer);
        streamTimer = null;
      }
    };

    const finishMessage = (reply, proposals, fallbackNotice) => {
      if (completed) return;
      completed = true;
      stopTypewriter();
      this.isLoading = false;
      assistantMsg.isStreaming = false;
      assistantMsg.streamingStatus = '';
      if (reply) assistantMsg.content = reply;
      if (!assistantMsg.content.trim()) {
        assistantMsg.content = 'הפעולה עובדה בהצלחה.';
      }
      if (proposals && proposals.length > 0) {
        assistantMsg.proposals = proposals;
        this.pendingProposals.push(...proposals);
      }
      this.activeFallbackNotice = fallbackNotice || null;
      this.saveChatHistory();
      this.render();
      this.scrollToBottom();
      if (typeof unsub === 'function') {
        try { unsub(); } catch (_) {}
      }
    };

    const tickTypewriter = () => {
      const remaining = targetText.length - renderedText.length;
      if (remaining > 0) {
        // Natural human reading speed with dynamic acceleration for bursts
        let step = 1;
        if (remaining > 250) step = Math.ceil(remaining / 6);
        else if (remaining > 100) step = Math.ceil(remaining / 10);
        else if (remaining > 35) step = 3;
        else if (remaining > 12) step = 2;
        else step = 1;

        renderedText += targetText.slice(renderedText.length, renderedText.length + step);
        assistantMsg.content = renderedText;
        assistantMsg.streamingStatus = '';
        this._streamUpdateLastBubble(renderedText);
      } else if (isServerDone) {
        finishMessage(doneReply || targetText, doneProposals, doneFallbackNotice);
      }
    };

    const startTypewriter = () => {
      if (!streamTimer) {
        streamTimer = setInterval(tickTypewriter, 16);
      }
    };

    const cleanHistory = this.chatHistory
      .slice(0, -2)
      .slice(-8)
      .filter((m) => m && m.content && !String(m.content).startsWith('⚠️') && !String(m.content).includes('שגיאה בתקשורת'))
      .map((m) => {
        const item = { role: m.role, content: m.content };
        if (m.tool_calls) item.tool_calls = m.tool_calls;
        return item;
      });

    try {
      if (this._hass.connection && typeof this._hass.connection.subscribeMessage === 'function') {
        unsub = await this._hass.connection.subscribeMessage(
          (event) => {
            if (!event) return;
            if (event.type === 'chunk' && event.chunk) {
              targetText += event.chunk;
              assistantMsg.streamingStatus = '';
              startTypewriter();
            } else if (event.type === 'status' && event.status) {
              if (!targetText) {
                assistantMsg.streamingStatus = event.status;
                this._streamUpdateStatus(assistantMsg.streamingStatus);
              }
            } else if (event.type === 'done') {
              isServerDone = true;
              doneReply = event.reply || targetText;
              doneProposals = event.proposals || [];
              doneFallbackNotice = event.fallback_notice || null;
              if (event.actual_model && event.actual_model !== 'free-engine') {
                this.setResolvedModel(this.settings.provider, event.actual_model);
              }
              if (targetText.length === 0 && doneReply) {
                // If chunks were buffered by network, type entire reply via typewriter
                targetText = doneReply;
                startTypewriter();
              } else if (renderedText.length >= targetText.length) {
                finishMessage(doneReply, doneProposals, doneFallbackNotice);
              } else {
                startTypewriter();
              }
            } else if (event.type === 'error') {
              finishMessage(event.error, [], null);
            }
          },
          {
            type: 'ai_agent/chat',
            message: text,
            history: cleanHistory,
          }
        );
      } else {
        const res = await this._hass.callWS({
          type: 'ai_agent/chat',
          message: text,
          history: cleanHistory,
        });
        isServerDone = true;
        doneReply = res.reply || '';
        doneProposals = res.proposals || [];
        doneFallbackNotice = res.fallback_notice || null;
        if (res.actual_model && res.actual_model !== 'free-engine') {
          this.setResolvedModel(this.settings.provider, res.actual_model);
        }
        targetText = doneReply;
        startTypewriter();
      }
    } catch (e) {
      if (!completed) {
        assistantMsg.isStreaming = false;
        assistantMsg.isError = true;
        finishMessage(`⚠️ שגיאה בתקשורת עם הסוכן: ${e.message || e}`, [], null);
      }
    }
  }

  _streamUpdateLastBubble(content) {
    const root = this.shadowRoot;
    if (!root) return;
    const chatScroll = root.querySelector('#chat-scroll');
    const bubbles = root.querySelectorAll('.message-bubble.message-assistant');
    if (!bubbles || bubbles.length === 0) return;
    const lastBubble = bubbles[bubbles.length - 1];
    let mdBody = lastBubble.querySelector('.markdown-body');
    if (!mdBody) {
      lastBubble.innerHTML = `<div class="markdown-body"></div>`;
      mdBody = lastBubble.querySelector('.markdown-body');
    }
    mdBody.innerHTML = this.renderMarkdown(content) + '<span class="streaming-cursor">▌</span>';
    if (chatScroll) {
      const dist = chatScroll.scrollHeight - chatScroll.scrollTop - chatScroll.clientHeight;
      if (dist < 180) {
        chatScroll.scrollTop = chatScroll.scrollHeight;
      }
    }
  }

  _streamUpdateStatus(status) {
    const root = this.shadowRoot;
    if (!root) return;
    const bubbles = root.querySelectorAll('.message-bubble.message-assistant');
    if (!bubbles || bubbles.length === 0) return;
    const lastBubble = bubbles[bubbles.length - 1];
    const md = lastBubble.querySelector('.markdown-body');
    if (md && md.textContent.trim()) return;
    lastBubble.innerHTML = `<div style="display:flex;gap:8px;align-items:center;color:#86868b;font-size:13.5px;">
      <span class="streaming-status">${this.escapeHtml(status)}</span>
      <span style="font-size:15px;animation:spin 1s infinite linear;">⚙️</span>
    </div>`;
  }

  editAndResendMessage(index, newText) {
    if (!newText || !newText.trim() || this.isLoading || !this._hass) return;
    this.editingIndex = null;
    // Truncate history to before this message (ChatGPT-style branching)
    this.chatHistory = this.chatHistory.slice(0, index);
    this.saveChatHistory();
    this.sendMessage(newText.trim());
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  escapeForTextarea(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  renderMarkdown(text) {
    if (!text) return '';

    // If text has an unclosed code block during live streaming, temporarily close it for clean card rendering
    let textToParse = String(text);
    const tripleBackticks = (textToParse.match(/```/g) || []).length;
    if (tripleBackticks % 2 !== 0) {
      textToParse += '\n```';
    }

    // Step 1: Extract code blocks (```lang ... ```)
    const codeBlocks = [];
    let processed = textToParse.replace(/```([a-zA-Z0-9_-]*)\n?([\s\S]*?)```/g, (match, lang, code) => {
      const id = `%%CODEBLOCK_${codeBlocks.length}%%`;
      codeBlocks.push({ lang: lang || 'code', code: code.replace(/^\n+|\n+$/g, '') });
      return id;
    });

    // Step 2: Escape HTML
    processed = processed
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Step 3: Extract inline code (`code`)
    const inlineCodes = [];
    processed = processed.replace(/`([^`\n]+)`/g, (match, code) => {
      const id = `%%INLINECODE_${inlineCodes.length}%%`;
      inlineCodes.push(code);
      return id;
    });

    // Step 4: Ensure headings, bullets and numbered lists start on new lines even if squashed by LLM
    processed = processed.replace(/(?<!\n)(#{1,4}\s+)/g, '\n\n$1');
    processed = processed.replace(/(?<!\n)(\d+[\.\)]\s+)/g, '\n$1');
    processed = processed.replace(/(?<!\n)([ \t]*[-*•]\s+)/g, '\n$1');

    // Step 5: Handle Headings (#, ##, ###, ####)
    processed = processed.replace(/^[ \t]*####[ \t]+(.*?)$/gm, '<h4 class="md-heading md-h4">$1</h4>');
    processed = processed.replace(/^[ \t]*###[ \t]+(.*?)$/gm, '<h3 class="md-heading md-h3">$1</h3>');
    processed = processed.replace(/^[ \t]*##[ \t]+(.*?)$/gm, '<h2 class="md-heading md-h2">$1</h2>');
    processed = processed.replace(/^[ \t]*#[ \t]+(.*?)$/gm, '<h1 class="md-heading md-h1">$1</h1>');

    // Step 6: Horizontal Rules (---, ***, ___)
    processed = processed.replace(/^[ \t]*[-*_]{3,}[ \t]*$/gm, '<hr class="md-hr" />');

    // Step 7: Bold & Italic
    processed = processed.replace(/\*\*(.+?)\*\*/g, '<strong class="md-bold">$1</strong>');
    processed = processed.replace(/__(.+?)__/g, '<strong class="md-bold">$1</strong>');
    processed = processed.replace(/(^|[^\*])\*([^\*\n]+)\*([^\*]|$)/g, '$1<em>$2</em>$3');

    // Step 8: Blockquotes (> quote)
    processed = processed.replace(/^[ \t]*>[ \t]+(.*?)$/gm, '<blockquote class="md-quote">$1</blockquote>');

    // Step 9: Parse lists (ordered 1. and unordered - / * / •)
    const lines = processed.split('\n');
    const outLines = [];
    let inOl = false;
    let inUl = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const olMatch = line.match(/^[ \t]*(\d+)[\.\)][ \t]+(.*)$/);
      const ulMatch = line.match(/^[ \t]*[-*•][ \t]+(.*)$/);

      if (olMatch) {
        if (!inOl) {
          if (inUl) { outLines.push('</ul>'); inUl = false; }
          outLines.push('<ol class="md-ol">');
          inOl = true;
        }
        outLines.push(`  <li class="md-li"><span class="md-li-num">${olMatch[1]}</span><div class="md-li-text">${olMatch[2]}</div></li>`);
      } else if (ulMatch) {
        if (!inUl) {
          if (inOl) { outLines.push('</ol>'); inOl = false; }
          outLines.push('<ul class="md-ul">');
          inUl = true;
        }
        outLines.push(`  <li class="md-li"><span class="md-li-bullet">•</span><div class="md-li-text">${ulMatch[1]}</div></li>`);
      } else {
        if (inOl) { outLines.push('</ol>'); inOl = false; }
        if (inUl) { outLines.push('</ul>'); inUl = false; }
        outLines.push(line);
      }
    }
    if (inOl) outLines.push('</ol>');
    if (inUl) outLines.push('</ul>');
    processed = outLines.join('\n');

    // Step 10: Paragraphs and Line Breaks
    const paragraphs = processed.split(/\n{2,}/);
    const finalHtml = paragraphs.map((block) => {
      const t = block.trim();
      if (!t) return '';
      if (
        t.startsWith('<h1') ||
        t.startsWith('<h2') ||
        t.startsWith('<h3') ||
        t.startsWith('<h4') ||
        t.startsWith('<ol') ||
        t.startsWith('<ul') ||
        t.startsWith('<blockquote') ||
        t.startsWith('<hr') ||
        t.startsWith('%%CODEBLOCK_')
      ) {
        return t;
      }
      return `<p class="md-p">${t.replace(/\n/g, '<br/>')}</p>`;
    }).filter(Boolean).join('');

    // Step 11: Restore inline code
    let result = finalHtml;
    inlineCodes.forEach((code, i) => {
      result = result.replace(
        `%%INLINECODE_${i}%%`,
        `<code class="md-inline-code" dir="ltr">${code}</code>`
      );
    });

    // Step 12: Restore code blocks with copy button
    codeBlocks.forEach((block, i) => {
      const escaped = block.code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      const blockMarkup = `
        <div class="md-code-card" dir="ltr">
          <div class="md-code-header">
            <span class="md-code-lang">${block.lang}</span>
            <button class="md-copy-btn" data-copy-idx="${i}" title="העתק קוד">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
              <span>העתק</span>
            </button>
          </div>
          <pre class="md-pre"><code>${escaped}</code></pre>
        </div>
      `;
      result = result.replace(`%%CODEBLOCK_${i}%%`, blockMarkup);
    });

    this._lastCodeBlocks = codeBlocks;
    return result;
  }

  showToast(msg) {
    const toast = document.createElement('div');
    toast.className = 'pro-toast';
    toast.textContent = msg;
    this.shadowRoot.appendChild(toast);
    setTimeout(() => toast.classList.add('visible'), 10);
    setTimeout(() => {
      toast.classList.remove('visible');
      setTimeout(() => toast.remove(), 400);
    }, 3000);
  }

  scrollToBottom() {
    setTimeout(() => {
      const container = this.shadowRoot.querySelector('#chat-scroll');
      if (container) container.scrollTop = container.scrollHeight;
    }, 50);
  }

  // Build just the messages HTML (used by renderMessages)
  _buildMessagesHTML() {
    const s = this.settings;
    const isFreeMode = !s.api_key;
    let html = '';

    if (this.chatHistory.length === 0) {
      html += `<div style="text-align:center;margin:auto;max-width:440px;">
        <div style="font-size:48px;margin-bottom:12px;">✨</div>
        <div style="font-size:18px;font-weight:600;margin-bottom:6px;">שלום! אני סוכן ה-AI שלך בבית</div>
        <div style="font-size:13.5px;color:#86868b;line-height:1.55;">
          ${isFreeMode
            ? `אתה פועל כרגע ב<b>מצב חינמי</b> ללא צורך במפתח API!<br/>
               אפשר לבקש ממני לסרוק שגיאות, לבנות אוטומציות או לשלוט במכשירים.<br/>
               רוצה מודל ספציפי? לחץ על <b>+</b> למטה והזן מפתח API.`
            : `מחובר לספק <b>${{
                openai: 'OpenAI',
                gemini: 'Google Gemini',
                anthropic: 'Anthropic Claude',
                deepseek: 'DeepSeek',
                openrouter: 'OpenRouter',
                custom: 'Custom',
              }[s.provider] || s.provider}</b> עם מודל <b>${s.model}</b>.<br/>מה תרצה שנעשה בבית היום?`}
        </div>
      </div>`;
    }

    this.chatHistory.forEach((msg, index) => {
      if (msg.role === 'user') {
        if (this.editingIndex === index) {
          html += `<div class="message-user-wrapper">
            <div class="msg-edit-box">
              <div class="msg-edit-title">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
                <span>עריכת הודעה</span>
                <span style="margin-right:auto;font-size:11px;opacity:0.6;">Esc לביטול</span>
              </div>
              <textarea class="msg-edit-textarea" id="edit-textarea-${index}">${this.escapeForTextarea(msg.content)}</textarea>
              <div class="msg-edit-buttons">
                <button type="button" class="msg-edit-cancel" data-cancel-edit="${index}">ביטול</button>
                <button type="button" class="msg-edit-save" data-submit-edit="${index}">שמור ושלח שוב ↑</button>
              </div>
            </div>
          </div>`;
        } else {
          html += `<div class="message-user-wrapper">
            <div class="message-bubble message-user">
              <div class="user-msg-text">${this.escapeHtml(msg.content)}</div>
            </div>
            <div class="msg-hover-actions">
              <button type="button" class="msg-action-btn" data-edit-index="${index}" title="ערוך הודעה">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
                </svg>
              </button>
            </div>
          </div>`;
        }
      } else {
        const isLive = msg.isStreaming && this.isLoading;
        html += `<div class="message-bubble message-assistant">
          ${msg.content
            ? `<div class="markdown-body">${this.renderMarkdown(msg.content)}${isLive ? '<span class="streaming-cursor">▌</span>' : ''}</div>`
            : `<div style="display:flex;gap:8px;align-items:center;color:#86868b;font-size:13.5px;">
                <span class="streaming-status">${this.escapeHtml(msg.streamingStatus || 'מעבד נתונים...')}</span>
                <span style="font-size:15px;animation:spin 1s infinite linear;">⚙️</span>
              </div>`
          }
          ${msg.proposals && msg.proposals.length > 0 ? msg.proposals.map((p) => `
            <div class="proposal-card">
              <div class="proposal-header">
                <div class="proposal-title">⚡ ${p.title}</div>
                <span style="font-size:11px;color:#ff9f0a;font-weight:600;">ממתין לאישור</span>
              </div>
              <div class="yaml-block">${p.yaml_preview}</div>
              <div class="proposal-buttons">
                <button type="button" class="pro-pill-btn btn-approve" data-approve="${p.id}">✅ אשר והטמע</button>
                <button type="button" class="pro-pill-btn btn-reject" data-reject="${p.id}">❌ דחה</button>
              </div>
            </div>`).join('') : ''}
        </div>`;
      }
    });

    return html;
  }

  // Update ONLY the messages area — no full DOM replace, no scroll jump
  renderMessages() {
    const root = this.shadowRoot;
    const chatScroll = root && root.querySelector('#chat-scroll');
    if (!chatScroll) { this._rendered = false; this.render(); return; }

    const savedScroll = chatScroll.scrollTop;
    chatScroll.innerHTML = this._buildMessagesHTML();
    chatScroll.scrollTop = savedScroll; // Restore synchronously

    // Update scroll-to-bottom button visibility
    const stbBtn = root.querySelector('#scroll-to-bottom-btn');
    if (stbBtn) {
      const dist = chatScroll.scrollHeight - chatScroll.scrollTop - chatScroll.clientHeight;
      stbBtn.classList.toggle('visible', dist > 120);
    }

    // Reattach message-area listeners
    this._attachMsgListeners();
  }

  _attachMsgListeners() {
    const root = this.shadowRoot;
    if (!root) return;

    root.querySelectorAll('[data-edit-index]').forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault(); e.stopPropagation();
        this.editingIndex = parseInt(btn.getAttribute('data-edit-index'), 10);
        this.renderMessages();
        setTimeout(() => {
          const ta = root.querySelector(`#edit-textarea-${this.editingIndex}`);
          if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
        }, 40);
      };
    });

    root.querySelectorAll('[data-cancel-edit]').forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault(); e.stopPropagation();
        this.editingIndex = null;
        this.renderMessages();
      };
    });

    root.querySelectorAll('[data-submit-edit]').forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute('data-submit-edit'), 10);
        const ta = root.querySelector(`#edit-textarea-${idx}`);
        if (ta && ta.value.trim()) this.editAndResendMessage(idx, ta.value.trim());
      };
    });

    if (this.editingIndex !== null) {
      const ta = root.querySelector(`#edit-textarea-${this.editingIndex}`);
      if (ta) {
        ta.onkeydown = (e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (ta.value.trim()) this.editAndResendMessage(this.editingIndex, ta.value.trim());
          } else if (e.key === 'Escape') {
            e.preventDefault();
            this.editingIndex = null;
            this.renderMessages();
          }
        };
      }
    }

    root.querySelectorAll('[data-approve]').forEach((btn) => {
      btn.onclick = () => this.resolveAction(btn.getAttribute('data-approve'), true);
    });
    root.querySelectorAll('[data-reject]').forEach((btn) => {
      btn.onclick = () => this.resolveAction(btn.getAttribute('data-reject'), false);
    });

    root.querySelectorAll('.md-copy-btn').forEach((btn) => {
      btn.onclick = async () => {
        const idx = parseInt(btn.getAttribute('data-copy-idx'), 10);
        if (this._lastCodeBlocks && this._lastCodeBlocks[idx]) {
          try {
            await navigator.clipboard.writeText(this._lastCodeBlocks[idx].code);
            const sp = btn.querySelector('span');
            if (sp) {
              const o = sp.textContent; sp.textContent = 'הועתק! ✓';
              btn.style.borderColor = '#30d158'; btn.style.color = '#30d158';
              setTimeout(() => { sp.textContent = o; btn.style.borderColor = ''; btn.style.color = ''; }, 2000);
            }
          } catch (err) { console.warn('copy failed', err); }
        }
      };
    });
  }

  connectedCallback() {
    this.chatHistory = this.loadChatHistory();
    this.render();
    this.scrollToBottom();
  }

  render(preserveScroll = true) {
    const s = this.settings;
    const isFreeMode = !s.api_key;
    const provName = {
      openai: 'OpenAI',
      gemini: 'Google Gemini',
      groq: 'GroqCloud',
      anthropic: 'Anthropic Claude',
      deepseek: 'DeepSeek',
      openrouter: 'OpenRouter',
      custom: 'Custom',
    }[s.provider] || s.provider;

    let modelDisplay = s.model || 'auto-latest';
    if (modelDisplay === 'auto-latest' || modelDisplay === 'auto' || !modelDisplay) {
      const activeResolved = this.getResolvedModel(s.provider);
      if (activeResolved && activeResolved !== 'free-engine') {
        modelDisplay = `Auto (${activeResolved})`;
      } else {
        modelDisplay = 'Auto';
      }
    }

    // After first full render, only update the messages section to avoid scroll jump
    if (this._rendered && this.shadowRoot && this.shadowRoot.querySelector('#chat-scroll')) {
      this.renderMessages();
      return;
    }
    this._rendered = true;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          min-height: 700px;
          background: #000000;
          color: #f5f5f7;
          font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          direction: rtl;
          box-sizing: border-box;
          padding: 16px;
          overflow-y: auto;
        }

        * { box-sizing: border-box; }

        .app-container {
          max-width: 980px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 14px;
          position: relative;
          height: 100%;
        }

        /* Header */
        .pro-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 4px 6px;
          flex-wrap: wrap;
          gap: 10px;
        }
        .header-title {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .pro-logo-badge {
          width: 44px;
          height: 44px;
          border-radius: 14px;
          background: #000000;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          box-shadow: 0 4px 16px rgba(10, 132, 255, 0.35), 0 0 12px rgba(191, 90, 242, 0.4);
          border: 1.5px solid rgba(191, 90, 242, 0.5);
          flex-shrink: 0;
        }
        .title-text h1 {
          font-size: 20px;
          font-weight: 700;
          letter-spacing: -0.4px;
          margin: 0;
          color: #ffffff;
        }
        .title-text p {
          font-size: 12.5px;
          color: #86868b;
          margin: 2px 0 0 0;
        }

        /* Header Actions */
        .header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
        }

        /* New Chat Button */
        .new-chat-btn {
          background: rgba(10, 132, 255, 0.16);
          color: #2997ff;
          border: 1px solid rgba(10, 132, 255, 0.35);
          padding: 8px 16px;
          border-radius: 980px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
          display: flex;
          align-items: center;
          gap: 6px;
          outline: none;
        }
        .new-chat-btn:hover {
          background: #0a84ff;
          color: #ffffff;
          border-color: #0a84ff;
          transform: scale(1.03);
          box-shadow: 0 4px 16px rgba(10, 132, 255, 0.45);
        }
        .new-chat-btn:active {
          transform: scale(0.97);
        }

        /* Active Config Pill Badge */
        .status-pill-badge {
          background: rgba(255, 255, 255, 0.08);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: #f5f5f7;
          padding: 8px 16px;
          border-radius: 980px;
          font-size: 12.5px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .status-pill-badge:hover {
          background: rgba(255, 255, 255, 0.15);
          transform: scale(1.02);
        }
        .dot-indicator {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: ${isFreeMode ? '#30d158' : '#0a84ff'};
          box-shadow: 0 0 8px ${isFreeMode ? '#30d158' : '#0a84ff'};
        }

        /* Main Chat Container */
        .chat-container {
          background: #1c1c1e;
          background: linear-gradient(180deg, rgba(28,28,30,0.92) 0%, rgba(18,18,20,0.96) 100%);
          backdrop-filter: blur(30px);
          -webkit-backdrop-filter: blur(30px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 24px;
          display: flex;
          flex-direction: column;
          height: calc(100vh - 130px);
          min-height: 580px;
          box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55);
          overflow: hidden;
          position: relative;
        }

        .chat-scroll {
          flex: 1;
          padding: 24px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        /* Message Bubbles */
        .message-bubble {
          max-width: 88%;
          padding: 15px 19px;
          border-radius: 18px;
          font-size: 14.5px;
          line-height: 1.6;
          letter-spacing: -0.2px;
          position: relative;
        }
        .message-user {
          background: #0a84ff;
          color: #ffffff;
          border-bottom-left-radius: 4px;
          box-shadow: 0 4px 16px rgba(10, 132, 255, 0.3);
        }
        .message-assistant {
          align-self: flex-end;
          background: rgba(255, 255, 255, 0.08);
          color: #f5f5f7;
          border-bottom-right-radius: 4px;
          border: 1px solid rgba(255, 255, 255, 0.06);
          width: fit-content;
        }

        .streaming-cursor {
          display: inline-block;
          margin-right: 3px;
          color: #0a84ff;
          font-weight: 700;
          animation: blinkCursor 0.8s infinite;
        }
        @keyframes blinkCursor {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }

        /* User Message Wrapper with ChatGPT-style Edit */
        .message-user-wrapper {
          align-self: flex-start;
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          max-width: 85%;
          position: relative;
        }
        .user-msg-text {
          white-space: pre-wrap;
          word-break: break-word;
          line-height: 1.5;
        }
        .msg-hover-actions {
          display: flex;
          gap: 6px;
          margin-top: 5px;
          margin-right: 4px;
          opacity: 0.9;
          transition: all 0.2s;
          align-self: flex-start;
        }
        .message-user-wrapper:hover .msg-hover-actions {
          opacity: 1;
        }
        .msg-action-btn {
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.16);
          color: #d1d1d6;
          border-radius: 50%;
          width: 28px;
          height: 28px;
          padding: 0;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
          outline: none;
        }
        .msg-action-btn:hover {
          background: rgba(10, 132, 255, 0.25);
          color: #64d2ff;
          border-color: #0a84ff;
          transform: scale(1.12);
        }

        /* Inline Edit Box */
        .msg-edit-box {
          width: 100%;
          min-width: 320px;
          max-width: 650px;
          background: #1c1c1e;
          border: 1px solid #0a84ff;
          border-radius: 16px;
          padding: 12px 14px;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5), 0 0 0 3px rgba(10, 132, 255, 0.2);
          box-sizing: border-box;
        }
        .msg-edit-title {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          font-weight: 600;
          color: #2997ff;
          margin-bottom: 8px;
        }
        .msg-edit-textarea {
          width: 100%;
          background: rgba(0, 0, 0, 0.45);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          color: #ffffff;
          font-size: 14px;
          line-height: 1.5;
          font-family: inherit;
          resize: vertical;
          min-height: 65px;
          padding: 10px;
          outline: none;
          direction: rtl;
          box-sizing: border-box;
        }
        .msg-edit-textarea:focus {
          border-color: #0a84ff;
          box-shadow: 0 0 0 2px rgba(10, 132, 255, 0.25);
        }
        .msg-edit-buttons {
          display: flex;
          justify-content: flex-end;
          gap: 8px;
          margin-top: 10px;
        }
        .msg-edit-save {
          background: #0a84ff;
          color: #ffffff;
          border: none;
          border-radius: 980px;
          padding: 7px 15px;
          font-size: 12.5px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        .msg-edit-save:hover {
          background: #0071e3;
          transform: scale(1.02);
        }
        .msg-edit-cancel {
          background: rgba(255, 255, 255, 0.1);
          color: #f5f5f7;
          border: none;
          border-radius: 980px;
          padding: 7px 13px;
          font-size: 12.5px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
        }
        .msg-edit-cancel:hover {
          background: rgba(255, 255, 255, 0.18);
        }

        /* Rich Markdown Body */
        .markdown-body {
          font-size: 14.5px;
          line-height: 1.7;
          color: #f5f5f7;
          direction: rtl;
          text-align: right;
          word-break: break-word;
        }
        .markdown-body .md-p {
          margin: 0 0 12px 0;
          line-height: 1.7;
        }
        .markdown-body .md-p:last-child {
          margin-bottom: 0;
        }
        .markdown-body .md-heading {
          color: #ffffff;
          font-weight: 700;
          letter-spacing: -0.3px;
          margin: 18px 0 10px 0;
          display: block;
        }
        .markdown-body .md-h1 {
          font-size: 19px;
          border-bottom: 1px solid rgba(255,255,255,0.1);
          padding-bottom: 6px;
        }
        .markdown-body .md-h2 {
          font-size: 17px;
          color: #2997ff;
        }
        .markdown-body .md-h3 {
          font-size: 15.5px;
          color: #64d2ff;
          border-right: 3px solid #0a84ff;
          padding-right: 8px;
        }
        .markdown-body .md-h4 {
          font-size: 14.5px;
          color: #a1a1a6;
        }
        .markdown-body .md-bold {
          font-weight: 700;
          color: #ffffff;
        }
        .markdown-body .md-inline-code {
          background: rgba(255, 255, 255, 0.1);
          color: #ff9f0a;
          padding: 2px 7px;
          border-radius: 6px;
          font-family: "SF Mono", Menlo, Consolas, Monaco, monospace;
          font-size: 12.5px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          display: inline-block;
          direction: ltr;
          unicode-bidi: embed;
        }
        .markdown-body .md-ol, .markdown-body .md-ul {
          margin: 10px 0 14px 0;
          padding: 0;
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .markdown-body .md-li {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          line-height: 1.65;
        }
        .markdown-body .md-li-num {
          background: rgba(10, 132, 255, 0.18);
          color: #2997ff;
          font-weight: 700;
          font-size: 12px;
          padding: 2px 8px;
          border-radius: 6px;
          border: 1px solid rgba(10, 132, 255, 0.3);
          flex-shrink: 0;
          margin-top: 2px;
        }
        .markdown-body .md-li-bullet {
          color: #0a84ff;
          font-size: 16px;
          flex-shrink: 0;
          line-height: 1.2;
        }
        .markdown-body .md-li-text {
          flex: 1;
        }
        .markdown-body .md-quote {
          border-right: 3px solid #0a84ff;
          margin: 12px 0;
          padding: 6px 14px;
          background: rgba(10, 132, 255, 0.06);
          border-radius: 0 8px 8px 0;
          color: #a1a1a6;
          font-style: italic;
        }
        .markdown-body .md-hr {
          border: none;
          height: 1px;
          background: rgba(255, 255, 255, 0.1);
          margin: 16px 0;
        }

        /* Code Blocks */
        .md-code-card {
          background: #0e0e10;
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 12px;
          margin: 14px 0;
          overflow: hidden;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
        }
        .md-code-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(255, 255, 255, 0.04);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          padding: 6px 12px;
          font-size: 11.5px;
          color: #86868b;
          font-family: monospace;
        }
        .md-copy-btn {
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: #f5f5f7;
          padding: 4px 10px;
          border-radius: 6px;
          font-size: 11.5px;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 5px;
          transition: all 0.2s;
          outline: none;
        }
        .md-copy-btn:hover {
          background: #0a84ff;
          color: #fff;
          border-color: #0a84ff;
        }
        .md-pre {
          margin: 0;
          padding: 14px;
          font-family: "SF Mono", Menlo, Consolas, Monaco, monospace;
          font-size: 12.5px;
          color: #64d2ff;
          overflow-x: auto;
          line-height: 1.5;
          white-space: pre-wrap;
          word-break: break-word;
        }

        /* Proposals in Chat */
        .proposal-card {
          margin-top: 14px;
          background: #000000;
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: 16px;
          padding: 16px;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
        }
        .proposal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;
        }
        .proposal-title {
          font-weight: 700;
          font-size: 14px;
          color: #30d158;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .yaml-block {
          background: #111113;
          border-radius: 10px;
          padding: 12px;
          font-family: "SF Mono", Menlo, Consolas, Monaco, monospace;
          font-size: 12px;
          color: #64d2ff;
          direction: ltr;
          text-align: left;
          overflow-x: auto;
          white-space: pre-wrap;
          margin: 10px 0;
          border: 1px solid rgba(255,255,255,0.06);
        }
        .proposal-buttons {
          display: flex;
          gap: 10px;
          margin-top: 12px;
        }
        .pro-pill-btn {
          flex: 1;
          padding: 10px 16px;
          border-radius: 980px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          border: none;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          outline: none;
        }
        .btn-approve {
          background: #30d158;
          color: #000000;
        }
        .btn-approve:hover {
          background: #34c759;
          transform: scale(1.02);
          box-shadow: 0 4px 16px rgba(48, 209, 88, 0.4);
        }
        .btn-reject {
          background: rgba(255, 69, 58, 0.2);
          color: #ff453a;
          border: 1px solid rgba(255, 69, 58, 0.4);
        }
        .btn-reject:hover {
          background: #ff453a;
          color: #ffffff;
          transform: scale(1.02);
        }

        /* Fallback Banner */
        .fallback-banner {
          display: none !important;
        }

        /* Chat Input Bar */
        .chat-input-bar {
          background: rgba(28, 28, 30, 0.98);
          border-top: 1px solid rgba(255, 255, 255, 0.08);
          padding: 14px 18px;
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .chat-input {
          flex: 1;
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 980px;
          padding: 12px 20px;
          color: #ffffff;
          font-size: 14px;
          outline: none;
          transition: all 0.2s;
          direction: rtl;
        }
        .chat-input:focus {
          border-color: #0a84ff;
          background: rgba(255, 255, 255, 0.09);
          box-shadow: 0 0 0 3px rgba(10, 132, 255, 0.25);
        }
        .send-btn {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          background: #0a84ff;
          color: #ffffff;
          border: none;
          font-size: 18px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
          box-shadow: 0 4px 12px rgba(10, 132, 255, 0.4);
          flex-shrink: 0;
          outline: none;
        }
        .send-btn:hover {
          transform: scale(1.05);
          background: #0071e3;
        }
        .send-btn:active {
          transform: scale(0.95);
        }

        /* The Apple "+" Button */
        .pro-plus-btn {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.1);
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #f5f5f7;
          font-size: 20px;
          font-weight: 300;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          flex-shrink: 0;
          outline: none;
        }
        .pro-plus-btn:hover {
          background: rgba(255, 255, 255, 0.18);
          transform: scale(1.06);
        }
        .pro-plus-btn.active {
          transform: rotate(45deg);
          background: #ff453a;
          color: #ffffff;
          border-color: #ff453a;
        }

        /* Drawer Overlay */
        .drawer-overlay {
          position: absolute;
          bottom: 64px;
          left: 12px;
          right: 12px;
          background: rgba(26, 26, 28, 0.98);
          backdrop-filter: blur(40px);
          -webkit-backdrop-filter: blur(40px);
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: 18px;
          padding: 12px 14px;
          box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7);
          display: none;
          flex-direction: column;
          gap: 8px;
          z-index: 50;
          max-height: 85vh;
          overflow-y: auto;
          animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        .drawer-overlay.open {
          display: flex;
        }

        .drawer-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 6px;
        }
        .drawer-title {
          font-size: 13.5px;
          font-weight: 700;
          color: #ffffff;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .close-drawer-btn {
          background: transparent;
          border: none;
          color: #a1a1a6;
          border-radius: 50%;
          width: 24px;
          height: 24px;
          cursor: pointer;
          font-size: 13px;
        }
        .close-drawer-btn:hover { color: #ffffff; }

        /* Separate Selection Rectangle Cards inside Drawer */
        .cards-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 8px;
        }

        .pro-card {
          background: rgba(36, 36, 38, 0.75);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 14px;
          padding: 8px 12px;
          box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
          box-sizing: border-box;
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }
        .card-icon {
          width: 24px;
          height: 24px;
          border-radius: 7px;
          background: rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 13px;
        }
        .card-title {
          font-size: 12.5px;
          font-weight: 600;
          color: #f5f5f7;
        }
        .card-subtitle {
          font-size: 10.5px;
          color: #86868b;
          line-height: 1.2;
        }

        .pro-select, .pro-input {
          width: 100%;
          background: rgba(0, 0, 0, 0.45);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          padding: 6px 10px;
          color: #ffffff;
          font-size: 12px;
          height: 34px;
          outline: none;
          box-sizing: border-box;
        }
        .pro-select:focus, .pro-input:focus {
          border-color: #0a84ff;
          box-shadow: 0 0 0 2px rgba(10, 132, 255, 0.25);
        }

        /* Thinking Pills */
        .thinking-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          margin-top: 4px;
        }
        .thinking-pill {
          flex: 1;
          min-width: 44px;
          text-align: center;
          padding: 6px 2px;
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #a1a1a6;
          font-size: 10.5px;
          font-weight: 600;
          cursor: pointer;
        }
        .thinking-pill.active {
          background: #0a84ff;
          color: #ffffff;
          border-color: #0a84ff;
        }

        .help-question-btn {
          background: rgba(255, 255, 255, 0.1);
          border: 1px solid rgba(255, 255, 255, 0.2);
          color: #64d2ff;
          border-radius: 50%;
          width: 20px;
          height: 20px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
          margin-right: 6px;
          transition: all 0.2s ease;
          vertical-align: middle;
          line-height: 1;
        }
        .help-question-btn:hover {
          background: rgba(100, 210, 255, 0.25);
          border-color: #64d2ff;
          transform: scale(1.15);
        }

        /* Floating API Key Modal Styles */
        .modal-backdrop {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.75);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 16px;
          box-sizing: border-box;
          animation: fadeIn 0.2s ease-out forwards;
        }
        .api-key-floating-card {
          background: rgba(22, 22, 26, 0.98);
          border: 1.5px solid rgba(100, 210, 255, 0.35);
          border-radius: 18px;
          width: 440px;
          max-width: 95vw;
          max-height: 85vh;
          overflow-y: auto;
          box-shadow: 0 25px 60px rgba(0, 0, 0, 0.85);
          display: flex;
          flex-direction: column;
          box-sizing: border-box;
        }
        .modal-card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 14px 18px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        .modal-card-title {
          font-size: 14px;
          font-weight: 700;
          color: #64d2ff;
        }
        .modal-card-close {
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: #f5f5f7;
          border-radius: 50%;
          width: 28px;
          height: 28px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          font-size: 13px;
        }
        .modal-card-close:hover {
          background: rgba(255, 255, 255, 0.2);
          color: #ffffff;
        }
        .modal-card-body {
          padding: 16px 18px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          direction: rtl;
        }
        .help-section {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 12px 14px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .help-badge {
          font-size: 12.5px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 6px;
          display: inline-block;
          width: fit-content;
        }
        .help-desc {
          font-size: 11.5px;
          color: #a1a1a6;
          line-height: 1.45;
        }
        .help-action-btn {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: rgba(10, 132, 255, 0.15);
          border: 1px solid rgba(10, 132, 255, 0.35);
          color: #64d2ff;
          padding: 7px 12px;
          border-radius: 8px;
          font-size: 12px;
          font-weight: 600;
          text-decoration: none;
          transition: all 0.2s;
          margin-top: 4px;
        }
        .help-action-btn:hover {
          background: rgba(10, 132, 255, 0.3);
          color: #ffffff;
          transform: translateY(-1px);
        }
        .help-note {
          font-size: 11px;
          color: #86868b;
          border-top: 1px solid rgba(255, 255, 255, 0.06);
          padding-top: 8px;
          line-height: 1.4;
        }

        /* Toast */
        .pro-toast {
          position: fixed;
          bottom: 24px;
          left: 50%;
          transform: translateX(-50%) translateY(20px);
          background: rgba(30, 30, 32, 0.95);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #ffffff;
          padding: 12px 24px;
          border-radius: 980px;
          font-size: 14px;
          font-weight: 500;
          box-shadow: 0 10px 30px rgba(0,0,0,0.6);
          opacity: 0;
          pointer-events: none;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          z-index: 9999;
        }
        .pro-toast.visible {
          opacity: 1;
          transform: translateX(-50%) translateY(0);
        }

        /* Scroll-to-bottom floating button */
        .scroll-to-bottom-btn {
          position: absolute;
          bottom: 80px;
          right: 20px;
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: rgba(10, 132, 255, 0.85);
          border: 1px solid rgba(10, 132, 255, 0.5);
          color: #ffffff;
          font-size: 18px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 4px 16px rgba(10, 132, 255, 0.45);
          opacity: 0;
          pointer-events: none;
          transition: opacity 0.25s ease, transform 0.2s ease;
          z-index: 30;
          outline: none;
        }
        .scroll-to-bottom-btn.visible {
          opacity: 1;
          pointer-events: auto;
        }
        .scroll-to-bottom-btn:hover {
          transform: scale(1.1);
          background: #0a84ff;
        }

        @keyframes slideUp {
          from { opacity: 0; transform: translateY(30px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      </style>

      <div class="app-container">
        <!-- Header -->
        <div class="pro-header">
          <div class="header-title">
            <div class="pro-logo-badge">
              <img src="/ai_agent_panel/icon.png" style="width: 100%; height: 100%; object-fit: cover;" alt="AI Agent Pro" />
            </div>
            <div class="title-text">
              <h1>סוכן AI חכם ל-Home Assistant</h1>
              <p>שליטה מלאה, אוטומציות ותיקון תקלות</p>
            </div>
          </div>
          <div class="header-actions">
            <!-- New Chat Button -->
            <button class="new-chat-btn" id="new-chat-btn" title="התחל שיחה חדשה ונקה את היסטוריית השיחה הנוכחית">
              שיחה חדשה +
            </button>
            <!-- Clickable Status Pill that opens the + drawer -->
            <div class="status-pill-badge" id="status-pill-btn" title="לחץ לשינוי ספק, מודל וחשיבה">
              <div class="dot-indicator"></div>
              <span>${isFreeMode ? 'מצב חינמי פעיל' : `${provName} • ${modelDisplay}`}</span>
              <span style="font-size: 11px; opacity: 0.7;">(חשיבה: ${s.thinking_level.toUpperCase()})</span>
              <span style="margin-right: 4px;">⚙️</span>
            </div>
          </div>
        </div>

        <!-- Chat Container -->
        <div class="chat-container">
          <!-- Scrollable Chat — filled dynamically by renderMessages() -->
          <div class="chat-scroll" id="chat-scroll"></div>

          <!-- Slide-up Drawer: Opened by "+" or Status Pill -->
          <div class="drawer-overlay ${this.isDrawerOpen ? 'open' : ''}" id="drawer">
            <div class="drawer-header">
              <div class="drawer-title">
                <span>➕</span>
                <span>הגדרות ספק, מודל ורמת חשיבה</span>
              </div>
              <button class="close-drawer-btn" id="close-drawer-btn">✕</button>
            </div>

            <!-- The Separate Rectangles -->
            <div class="cards-grid">
              <!-- מלבן 1: תפקיד סוכן -->
              <div class="pro-card">
                <div class="card-header">
                  <div class="card-icon">👑</div>
                  <div>
                    <div class="card-title">1. תפקיד הסוכן</div>
                    <div class="card-subtitle">עושה הכל או מתמחה</div>
                  </div>
                </div>
                <select class="pro-select" id="agent-role-select">
                  <option value="omni" ${s.agent_role === 'omni' ? 'selected' : ''}>👑 סוכן-על שעושה הכל ללא הגבלה</option>
                  <option value="diagnostic" ${s.agent_role === 'diagnostic' ? 'selected' : ''}>🔧 סוכן דיאגנוסטיקה ותיקונים</option>
                  <option value="automations" ${s.agent_role === 'automations' ? 'selected' : ''}>⚡ סוכן מומחה אוטומציות</option>
                  <option value="butler" ${s.agent_role === 'butler' ? 'selected' : ''}>🏠 סוכן בית חכם כללי</option>
                </select>
              </div>

              <!-- מלבן 2: בחירת ספק -->
              <div class="pro-card">
                <div class="card-header">
                  <div class="card-icon">🌐</div>
                  <div>
                    <div class="card-title">2. בחירת ספק (Provider)</div>
                    <div class="card-subtitle">חברת ה-AI שמפעילה את המודל</div>
                  </div>
                </div>
                <select class="pro-select" id="provider-select">
                  <option value="openai" ${s.provider === 'openai' ? 'selected' : ''}>OpenAI</option>
                  <option value="gemini" ${s.provider === 'gemini' ? 'selected' : ''}>Google Gemini</option>
                  <option value="groq" ${s.provider === 'groq' ? 'selected' : ''}>GroqCloud</option>
                  <option value="anthropic" ${s.provider === 'anthropic' ? 'selected' : ''}>Anthropic Claude</option>
                  <option value="deepseek" ${s.provider === 'deepseek' ? 'selected' : ''}>DeepSeek</option>
                  <option value="openrouter" ${s.provider === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                  <option value="custom" ${s.provider === 'custom' ? 'selected' : ''}>שרת מקומי / Custom</option>
                </select>
              </div>

              <!-- מלבן 3: בחירת מודל והדבקה חופשית -->
              <div class="pro-card">
                <div class="card-header">
                  <div class="card-icon">🧠</div>
                  <div>
                    <div class="card-title">3. בחירת מודל</div>
                    <div class="card-subtitle">מודל עדכני אוטומטי או הקלדה חופשית</div>
                  </div>
                </div>
                <button type="button" id="auto-model-badge-btn" title="בחר מודל עדכני ביותר אוטומטית לפי הספק" style="
                  width: 100%;
                  margin-bottom: 8px;
                  background: ${(!s.model || s.model === 'auto-latest' || s.model === 'auto') ? 'linear-gradient(135deg, rgba(10, 132, 255, 0.4), rgba(191, 90, 242, 0.4))' : 'rgba(255, 255, 255, 0.08)'};
                  border: 1.5px solid ${(!s.model || s.model === 'auto-latest' || s.model === 'auto') ? '#0a84ff' : 'rgba(255, 255, 255, 0.16)'};
                  color: #ffffff;
                  border-radius: 10px;
                  padding: 8px 12px;
                  font-size: 12px;
                  font-weight: 600;
                  cursor: pointer;
                  display: flex;
                  align-items: center;
                  justify-content: space-between;
                  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
                  outline: none;
                  box-sizing: border-box;
                  box-shadow: ${(!s.model || s.model === 'auto-latest' || s.model === 'auto') ? '0 4px 14px rgba(10, 132, 255, 0.35)' : 'none'};
                ">
                  <span style="display: flex; align-items: center; gap: 6px;">
                    ✨ מודל עדכני ביותר (אוטומטי)
                  </span>
                  <span style="font-size: 11px; background: rgba(255, 255, 255, 0.18); padding: 2px 6px; border-radius: 6px; font-family: monospace;">auto-latest</span>
                </button>
                <input type="text" class="pro-input" id="model-input" value="${s.model || 'auto-latest'}" placeholder="למשל: auto-latest, gemini-2.5-flash, llama-3.1-8b-instant..." />
              </div>

              <!-- מלבן 4: רמת חשיבה ומהירות -->
              <div class="pro-card">
                <div class="card-header">
                  <div class="card-icon">⚡</div>
                  <div>
                    <div class="card-title">4. רמת חשיבה ומהירות (Performance & Reasoning)</div>
                  </div>
                </div>
                <div class="thinking-pills">
                  ${[
                    { lvl: 'off', label: '⚡ Off (Turbo)' },
                    { lvl: 'low', label: 'Low (מהיר)' },
                    { lvl: 'medium', label: 'Medium' },
                    { lvl: 'high', label: 'High' },
                    { lvl: 'xhigh', label: 'X-High' },
                    { lvl: 'max', label: '🐢 Max (כבד)' },
                  ].map((item) => `
                    <div class="thinking-pill ${s.thinking_level === item.lvl ? 'active' : ''}" data-level="${item.lvl}">
                      ${item.label}
                    </div>
                  `).join('')}
                </div>
              </div>

              <!-- מלבן 5: API Key -->
              <div class="pro-card">
                <div class="card-header" style="justify-content: space-between;">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="card-icon">🔑</div>
                    <div>
                      <div class="card-title" style="display: flex; align-items: center; gap: 8px;">
                        <span>5. מפתח API (API Key)</span>
                        <button type="button" id="api-key-help-btn" class="help-question-btn" title="הסבר והנפקת מפתחות API בחינם">?</button>
                      </div>
                      <div class="card-subtitle">נדרש לחיבור ענן (ללא מפתח: פקודות בית בלבד)</div>
                    </div>
                  </div>
                </div>
                <div style="display: flex; gap: 6px; align-items: center; width: 100%;">
                  <input type="password" class="pro-input" id="api-key-input" placeholder="הדבק מפתח API..." value="${s.api_key || ''}" style="flex: 1;" />
                  <button type="button" id="toggle-key-visibility-btn" title="הצג / הסתר מפתח API" style="
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 8px;
                    color: #f5f5f7;
                    padding: 6px 10px;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 15px;
                    line-height: 1;
                    height: 34px;
                    box-sizing: border-box;
                    transition: all 0.2s ease;
                  ">
                    👁️
                  </button>
                </div>
              </div>
            </div>

            <button class="pro-pill-btn btn-approve" id="save-drawer-btn" style="margin-top: 8px; padding: 10px;">
              💾 שמור את כל השינויים וסגור
            </button>
          </div>

          <!-- Floating API Key Modal / Popover -->
          <div class="modal-backdrop" id="api-key-modal-backdrop" style="display: none;">
            <div class="api-key-floating-card">
              <div class="modal-card-header">
                <div class="modal-card-title">🎁 מפתחות API חינמיים ללא עלות</div>
                <button type="button" class="modal-card-close" id="close-help-modal-btn" title="סגור">✕</button>
              </div>
              <div class="modal-card-body">
                <div class="help-section">
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="help-badge" style="background: rgba(10, 132, 255, 0.2); color: #64d2ff;">1</span>
                    <b style="font-size: 13px; color: #f5f5f7;">Google Gemini (הכי מומלץ – מודל חכם ועדכני)</b>
                  </div>
                  <div class="help-desc">לחיבור המודל החינמי העדכני של גוגל (כמו באתר Gemini):</div>
                  <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener" class="help-action-btn">
                    🎁 לחץ כאן להפקת מפתח Google Gemini בחינם (ללא אשראי)
                  </a>
                  <div class="help-note">
                    גוגל מעניקה מכסה חינמית מלאה וקבועה של 15 פניות בדקה ומיליון טוקנים – מעל ומעבר לכל צרכי הבית ללא שום עלות.
                  </div>
                </div>

                <div class="help-section">
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="help-badge" style="background: rgba(255, 159, 10, 0.2); color: #ff9f0a;">2</span>
                    <b style="font-size: 13px; color: #f5f5f7;">GroqCloud (מעבדי LPU במהירות שיא)</b>
                  </div>
                  <div class="help-desc">לחיבור מודלי Llama 3.3 70B בחינם וללא צורך במילוי טוקנים:</div>
                  <a href="https://console.groq.com/keys" target="_blank" rel="noopener" class="help-action-btn">
                    ⚡ לחץ כאן להפקת מפתח GroqCloud בחינם
                  </a>
                  <div class="help-note">
                    בחר בספק <b>GroqCloud</b> והדבק את המפתח שהונפק. מהירות תגובה קיצונית של מאות טוקנים בשנייה ללא חיוב.
                  </div>
                </div>

                <div class="help-section">
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="help-badge" style="background: rgba(48, 209, 88, 0.2); color: #30d158;">3</span>
                    <b style="font-size: 13px; color: #f5f5f7;">OpenRouter (גישה למודלים חינמיים שונים)</b>
                  </div>
                  <div class="help-desc">לחיבור מודלים חינמיים שונים (Llama, DeepSeek, Gemini):</div>
                  <a href="https://openrouter.ai/keys" target="_blank" rel="noopener" class="help-action-btn">
                    🌐 לחץ כאן להפקת מפתח OpenRouter בחינם
                  </a>
                  <div class="help-note">
                    מאפשר שימוש בכל המודלים המסומנים עם סיומת <code>:free</code> ללא חיוב.
                  </div>
                </div>

                <div style="font-size: 11px; color: #86868b; border-top: 1px solid rgba(255, 255, 255, 0.06); padding-top: 8px;">
                  ℹ️ <b>OpenAI (ChatGPT) / Claude:</b> ספקים אלו דורשים מפתח מחשבון מפתחים בתשלום עם יתרת טוקנים (באתר שלהם השיחה חינם, אך ה-API דורש תקציב).
                </div>
              </div>
            </div>
          </div>

          <!-- Chat Input Bar with the "+" Button -->
          <div class="chat-input-bar">
            <!-- The "+" Button -->
            <button type="button" class="pro-plus-btn ${this.isDrawerOpen ? 'active' : ''}" id="plus-btn" title="פתח הגדרות ספק, מודל וחשיבה">
              +
            </button>

            <!-- Text Input -->
            <input type="text" class="chat-input" id="chat-input" placeholder="כתוב הוראה לסוכן (למשל: 'בדוק שגיאות בלוגים', 'צור אוטומציה לכיבוי הדוד')..." />

            <!-- Send Button -->
            <button type="button" class="send-btn" id="send-btn">↑</button>
          </div>

          <!-- Scroll-to-bottom floating button -->
          <button type="button" class="scroll-to-bottom-btn" id="scroll-to-bottom-btn" title="גלול לתחתית השיחה">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="8 12 12 16 16 12"/>
              <line x1="12" y1="8" x2="12" y2="16"/>
            </svg>
          </button>
        </div>
      </div>
    `;

    this.attachEventListeners();
  }

  attachEventListeners() {
    const root = this.shadowRoot;

    // Toggle Drawer — manipulate DOM class directly, no full re-render
    const plusBtn = root.querySelector('#plus-btn');
    const statusPillBtn = root.querySelector('#status-pill-btn');
    const closeDrawerBtn = root.querySelector('#close-drawer-btn');

    if (plusBtn) plusBtn.onclick = (e) => { e.preventDefault(); e.stopPropagation(); this.toggleDrawer(); };
    if (statusPillBtn) statusPillBtn.onclick = (e) => { e.preventDefault(); e.stopPropagation(); this.toggleDrawer(); };
    if (closeDrawerBtn) closeDrawerBtn.onclick = (e) => { e.preventDefault(); e.stopPropagation(); this.closeDrawer(); };

    // Thinking Pills — toggle class directly, no re-render
    root.querySelectorAll('.thinking-pill').forEach((pill) => {
      pill.onclick = () => {
        this.settings.thinking_level = pill.getAttribute('data-level');
        root.querySelectorAll('.thinking-pill').forEach((p) => p.classList.remove('active'));
        pill.classList.add('active');
      };
    });

    // Auto Model Badge Button
    const autoBadgeBtn = root.querySelector('#auto-model-badge-btn');
    const modelInp = root.querySelector('#model-input');
    if (autoBadgeBtn && modelInp) {
      const updateBadgeVisual = () => {
        const val = modelInp.value.trim();
        const isAuto = (!val || val === 'auto-latest' || val === 'auto');
        autoBadgeBtn.style.background = isAuto ? 'linear-gradient(135deg, rgba(10, 132, 255, 0.4), rgba(191, 90, 242, 0.4))' : 'rgba(255, 255, 255, 0.08)';
        autoBadgeBtn.style.borderColor = isAuto ? '#0a84ff' : 'rgba(255, 255, 255, 0.16)';
        autoBadgeBtn.style.boxShadow = isAuto ? '0 4px 14px rgba(10, 132, 255, 0.35)' : 'none';
      };
      autoBadgeBtn.onclick = (e) => {
        e.preventDefault();
        modelInp.value = 'auto-latest';
        this.settings.model = 'auto-latest';
        updateBadgeVisual();
      };
      modelInp.addEventListener('input', updateBadgeVisual);
    }

    // Provider onchange helper: switch provider and remember API key per provider
    const provSel = root.querySelector('#provider-select');
    const keyInp = root.querySelector('#api-key-input');
    if (provSel) {
      provSel.onchange = () => {
        const oldProv = this.settings.provider;
        const newProv = provSel.value;

        if (!this.settings.api_keys) this.settings.api_keys = {};

        // 1. Remember whatever key was typed for the old provider
        if (keyInp && oldProv) {
          this.settings.api_keys[oldProv] = keyInp.value.trim();
        }

        // 2. Switch active provider
        this.settings.provider = newProv;

        // 3. Load saved key for the newly selected provider (or empty if none entered yet)
        const loadedKey = this.settings.api_keys[newProv] || '';
        this.settings.api_key = loadedKey;
        if (keyInp) {
          keyInp.value = loadedKey;
        }

        // 4. Default model to auto-latest for the new provider
        if (modelInp) {
          modelInp.value = 'auto-latest';
        }
        this.settings.model = 'auto-latest';
        if (autoBadgeBtn) {
          autoBadgeBtn.style.background = 'linear-gradient(135deg, rgba(10, 132, 255, 0.4), rgba(191, 90, 242, 0.4))';
          autoBadgeBtn.style.borderColor = '#0a84ff';
          autoBadgeBtn.style.boxShadow = '0 4px 14px rgba(10, 132, 255, 0.35)';
        }

        this.updateHeaderStatusPill();
      };
    }

    // Live update active provider's key when user types
    if (keyInp) {
      keyInp.addEventListener('input', () => {
        const val = keyInp.value.trim();
        this.settings.api_key = val;
        if (!this.settings.api_keys) this.settings.api_keys = {};
        if (this.settings.provider) {
          this.settings.api_keys[this.settings.provider] = val;
        }
      });
    }

    // Help Question Button for Free API Keys (Opens floating modal)
    const helpBtn = root.querySelector('#api-key-help-btn');
    const helpModal = root.querySelector('#api-key-modal-backdrop');
    const closeHelpModalBtn = root.querySelector('#close-help-modal-btn');

    if (helpBtn && helpModal) {
      helpBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        helpModal.style.display = 'flex';
      };
    }
    if (closeHelpModalBtn && helpModal) {
      closeHelpModalBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        helpModal.style.display = 'none';
      };
    }
    if (helpModal) {
      helpModal.onclick = (e) => {
        if (e.target === helpModal) {
          helpModal.style.display = 'none';
        }
      };
    }

    // Toggle API Key visibility
    const toggleKeyBtn = root.querySelector('#toggle-key-visibility-btn');
    if (toggleKeyBtn && keyInp) {
      toggleKeyBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (keyInp.type === 'password') {
          keyInp.type = 'text';
          toggleKeyBtn.textContent = '🙈';
          toggleKeyBtn.title = 'הסתר מפתח API';
        } else {
          keyInp.type = 'password';
          toggleKeyBtn.textContent = '👁️';
          toggleKeyBtn.title = 'הצג מפתח API';
        }
      };
    }

    // Save Settings from Drawer
    const saveBtn = root.querySelector('#save-drawer-btn');
    if (saveBtn) {
      saveBtn.onclick = (e) => {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        const roleSel = root.querySelector('#agent-role-select');
        const pSel = root.querySelector('#provider-select');
        const mInp = root.querySelector('#model-input');
        const kInp = root.querySelector('#api-key-input');
        const activePill = root.querySelector('.thinking-pill.active');

        if (roleSel) this.settings.agent_role = roleSel.value;
        if (pSel) this.settings.provider = pSel.value;
        if (mInp) this.settings.model = mInp.value.trim();

        if (!this.settings.api_keys) this.settings.api_keys = {};
        if (kInp) {
          const val = kInp.value.trim();
          this.settings.api_key = val;
          if (this.settings.provider) {
            this.settings.api_keys[this.settings.provider] = val;
          }
        }
        if (activePill) this.settings.thinking_level = activePill.getAttribute('data-level');

        this.updateHeaderStatusPill();
        this.saveSettings();
      };
    }

    // Send Chat
    const chatInput = root.querySelector('#chat-input');
    const sendBtn = root.querySelector('#send-btn');
    const handleSend = () => {
      if (chatInput && chatInput.value) {
        const val = chatInput.value;
        chatInput.value = '';
        this.sendMessage(val);
      }
    };
    if (sendBtn) sendBtn.onclick = handleSend;
    if (chatInput) chatInput.onkeydown = (e) => { if (e.key === 'Enter') handleSend(); };

    // New Chat
    const newChatBtn = root.querySelector('#new-chat-btn');
    if (newChatBtn) newChatBtn.onclick = () => this.startNewChat();

    // Scroll-to-bottom button
    const stbBtn = root.querySelector('#scroll-to-bottom-btn');
    const chatScrollEl = root.querySelector('#chat-scroll');
    if (chatScrollEl && stbBtn) {
      chatScrollEl.addEventListener('scroll', () => {
        const dist = chatScrollEl.scrollHeight - chatScrollEl.scrollTop - chatScrollEl.clientHeight;
        stbBtn.classList.toggle('visible', dist > 120);
      }, { passive: true });
      stbBtn.onclick = () => chatScrollEl.scrollTo({ top: chatScrollEl.scrollHeight, behavior: 'smooth' });
    }

    // Populate messages for the first time
    this.renderMessages();
  }
}

try {
  if (!customElements.get('ai-agent-panel')) {
    customElements.define('ai-agent-panel', AIAgentPanel);
  }
} catch (_) {}
try {
  if (!customElements.get('ai-agent-card')) {
    customElements.define('ai-agent-card', AIAgentPanel);
  }
} catch (_) {}

// Register in Lovelace card picker (only once)
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'ai-agent-card')) {
  window.customCards.push({
    type: 'ai-agent-card',
    name: 'AI Agent Pro',
    description: 'סוכן AI אוטונומי עם כפתור +, מנגנון אישורים, תמיכה בכל הספקים ומודלים עתידיים.',
  });
}

console.info('%c🚀 AI Agent Pro v1.7.4 (Evidence-Based Architecture: Rollback, Traces & History)', 'background: #0a84ff; color: #fff; font-weight: bold; padding: 4px 8px; border-radius: 4px;');

