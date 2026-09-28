/**
 * AI Agent Pro Dashboard Panel & Card
 * Pure Vanilla Web Component with Modern Glassmorphism, Quick "+" Settings Drawer & Free Mode
 */

class AIAgentPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.hass = null;
    this.settings = {
      agent_role: 'omni',
      provider: 'openai',
      model: 'gpt-6-astra',
      thinking_level: 'high',
      require_approval: true,
      api_key: '',
      base_url: 'https://api.openai.com/v1',
    };
    this.chatHistory = this.loadChatHistory();
    this.pendingProposals = [];
    this.isLoading = false;
    this.activeFallbackNotice = null;
    this.isDrawerOpen = false;
  }

  loadChatHistory() {
    try {
      const saved = localStorage.getItem('ai_agent_pro_chat_history');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) return parsed;
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
        this.render();
      }
    } catch (e) {
      console.warn('Could not load AI Agent settings from WS', e);
    }
  }

  async saveSettings() {
    if (!this._hass) return;
    try {
      await this._hass.callWS({
        type: 'ai_agent/save_settings',
        agent_role: this.settings.agent_role,
        provider: this.settings.provider,
        model: this.settings.model,
        thinking_level: this.settings.thinking_level,
        api_key: this.settings.api_key || '',
        base_url: this.settings.base_url || '',
        require_approval: this.settings.require_approval !== false,
      });
      this.showToast('✅ ההגדרות עודכנו בהצלחה!');
      this.isDrawerOpen = false;
      this.render();
    } catch (e) {
      this.showToast('❌ שגיאה בשמירת הגדרות: ' + e.message);
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
            ? '✅ **האוטומציה אושרה והוטמעה במערכת בהצלחה!** היא פעילה כעת ב-Home Assistant.'
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
    if (!text.trim() || this.isLoading || !this._hass) return;

    this.isLoading = true;
    this.chatHistory.push({ role: 'user', content: text });
    this.saveChatHistory();
    this.render();
    this.scrollToBottom();

    try {
      const res = await this._hass.callWS({
        type: 'ai_agent/chat',
        message: text,
        history: this.chatHistory.slice(-8),
      });

      this.activeFallbackNotice = res.fallback_notice || null;

      if (res.proposals && res.proposals.length > 0) {
        this.pendingProposals.push(...res.proposals);
      }

      this.chatHistory.push({
        role: 'assistant',
        content: res.reply || 'הפעולה עובדה בהצלחה.',
        fallbackNotice: res.fallback_notice,
        proposals: res.proposals || [],
      });
      this.saveChatHistory();
    } catch (e) {
      this.chatHistory.push({
        role: 'assistant',
        content: `⚠️ שגיאה בתקשורת עם הסוכן: ${e.message || e}`,
        isError: true,
      });
      this.saveChatHistory();
    } finally {
      this.isLoading = false;
      this.render();
      this.scrollToBottom();
    }
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

  connectedCallback() {
    this.chatHistory = this.loadChatHistory();
    this.render();
    this.scrollToBottom();
  }

  render() {
    const s = this.settings;
    const isFreeMode = !s.api_key;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          min-height: 820px;
          background: #000000;
          color: #f5f5f7;
          font-family: -pro-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          direction: rtl;
          box-sizing: border-box;
          padding: 20px;
          overflow-y: auto;
        }

        * { box-sizing: border-box; }

        .app-container {
          max-width: 960px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 16px;
          position: relative;
        }

        /* Header */
        .pro-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 6px 10px;
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
          background: linear-gradient(135deg, #2c2c2e, #1c1c1e);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 22px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.5), inset 0 1px 1px rgba(255,255,255,0.1);
          border: 1px solid rgba(255,255,255,0.08);
        }
        .title-text h1 {
          font-size: 22px;
          font-weight: 700;
          letter-spacing: -0.5px;
          margin: 0;
          color: #ffffff;
        }
        .title-text p {
          font-size: 13px;
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
          height: 640px;
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
          gap: 18px;
        }

        /* Message Bubbles */
        .message-bubble {
          max-width: 82%;
          padding: 14px 18px;
          border-radius: 18px;
          font-size: 14.5px;
          line-height: 1.55;
          letter-spacing: -0.2px;
          position: relative;
        }
        .message-user {
          align-self: flex-start;
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
        }
        .btn-approve {
          background: #30d158;
          color: #000000;
          box-shadow: 0 4px 16px rgba(48, 209, 88, 0.35);
        }
        .btn-approve:hover {
          background: #34c759;
          transform: scale(1.02);
        }
        .btn-reject {
          background: rgba(255, 69, 58, 0.15);
          color: #ff453a;
          border: 1px solid rgba(255, 69, 58, 0.3);
        }
        .btn-reject:hover {
          background: rgba(255, 69, 58, 0.25);
          transform: scale(1.02);
        }

        /* Fallback Alert Banner */
        .fallback-banner {
          background: rgba(255, 159, 10, 0.12);
          border: 1px solid rgba(255, 159, 10, 0.3);
          border-radius: 12px;
          padding: 10px 14px;
          color: #ff9f0a;
          font-size: 12.5px;
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }

        /* Chat Input Bar with "+" Button */
        .chat-input-bar {
          padding: 14px 18px;
          background: rgba(0, 0, 0, 0.5);
          border-top: 1px solid rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          gap: 12px;
          position: relative;
        }

        /* The Plus (+) Button */
        .pro-plus-btn {
          width: 44px;
          height: 44px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(15px);
          -webkit-backdrop-filter: blur(15px);
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #ffffff;
          font-size: 24px;
          font-weight: 300;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
          flex-shrink: 0;
        }
        .pro-plus-btn:hover {
          background: rgba(255, 255, 255, 0.2);
          transform: scale(1.06);
        }
        .pro-plus-btn.active {
          transform: rotate(45deg);
          background: #ff453a;
          border-color: #ff453a;
        }

        .chat-input {
          flex: 1;
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 980px;
          padding: 14px 20px;
          color: #ffffff;
          font-size: 14.5px;
          outline: none;
          transition: all 0.2s ease;
        }
        .chat-input:focus {
          border-color: #0a84ff;
          background: rgba(255, 255, 255, 0.12);
        }
        .send-btn {
          width: 44px;
          height: 44px;
          border-radius: 50%;
          background: #0a84ff;
          border: none;
          color: #ffffff;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 18px;
          transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 4px 12px rgba(10, 132, 255, 0.4);
          flex-shrink: 0;
        }
        .send-btn:hover { transform: scale(1.06); }

        /* The Slide-up Settings Drawer (Opened by "+") */
        .drawer-overlay {
          position: absolute;
          bottom: 74px;
          left: 0;
          right: 0;
          max-height: 520px;
          background: rgba(24, 24, 26, 0.95);
          backdrop-filter: blur(35px);
          -webkit-backdrop-filter: blur(35px);
          border-top: 1px solid rgba(255, 255, 255, 0.15);
          box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.7);
          border-top-left-radius: 24px;
          border-top-right-radius: 24px;
          padding: 24px;
          overflow-y: auto;
          display: ${this.isDrawerOpen ? 'flex' : 'none'};
          flex-direction: column;
          gap: 16px;
          z-index: 100;
          animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .drawer-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 6px;
        }
        .drawer-title {
          font-size: 17px;
          font-weight: 700;
          color: #ffffff;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .close-drawer-btn {
          background: rgba(255, 255, 255, 0.1);
          border: none;
          color: #a1a1a6;
          border-radius: 50%;
          width: 28px;
          height: 28px;
          cursor: pointer;
          font-size: 14px;
        }
        .close-drawer-btn:hover { color: #ffffff; }

        /* Separate Selection Rectangle Cards inside Drawer */
        .cards-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 14px;
        }

        .pro-card {
          background: rgba(36, 36, 38, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 18px;
          padding: 16px;
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 12px;
        }
        .card-icon {
          width: 30px;
          height: 30px;
          border-radius: 9px;
          background: rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 15px;
        }
        .card-title {
          font-size: 14px;
          font-weight: 600;
          color: #f5f5f7;
        }
        .card-subtitle {
          font-size: 11.5px;
          color: #86868b;
        }

        .pro-select, .pro-input {
          width: 100%;
          background: rgba(0, 0, 0, 0.45);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 12px;
          padding: 11px 13px;
          color: #ffffff;
          font-size: 13.5px;
          outline: none;
        }
        .pro-select:focus, .pro-input:focus {
          border-color: #0a84ff;
          box-shadow: 0 0 0 3px rgba(10, 132, 255, 0.25);
        }

        /* Thinking Pills */
        .thinking-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 8px;
        }
        .thinking-pill {
          flex: 1;
          min-width: 50px;
          text-align: center;
          padding: 8px 6px;
          border-radius: 10px;
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #a1a1a6;
          font-size: 11.5px;
          font-weight: 600;
          cursor: pointer;
        }
        .thinking-pill.active {
          background: #0a84ff;
          color: #ffffff;
          border-color: #0a84ff;
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

        @keyframes slideUp {
          from { opacity: 0; transform: translateY(30px); }
          to { opacity: 1; transform: translateY(0); }
        }
      </style>

      <div class="app-container">
        <!-- Header -->
        <div class="pro-header">
          <div class="header-title">
            <div class="pro-logo-badge">🤖</div>
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
              <span>${isFreeMode ? 'מצב חינמי פעיל' : `${s.provider} • ${s.model}`}</span>
              <span style="font-size: 11px; opacity: 0.7;">(חשיבה: ${s.thinking_level.toUpperCase()})</span>
              <span style="margin-right: 4px;">⚙️</span>
            </div>
          </div>
        </div>

        <!-- Chat Container -->
        <div class="chat-container">
          <!-- Scrollable Chat -->
          <div class="chat-scroll" id="chat-scroll">
            ${this.chatHistory.length === 0 ? `
              <div style="text-align: center; margin: auto; max-width: 440px;">
                <div style="font-size: 48px; margin-bottom: 12px;">✨</div>
                <div style="font-size: 18px; font-weight: 600; margin-bottom: 6px;">שלום! אני סוכן ה-AI שלך בבית</div>
                <div style="font-size: 13.5px; color: #86868b; line-height: 1.55;">
                  ${isFreeMode ? `
                    אתה פועל כרגע ב<b>מצב חינמי</b> ללא צורך במפתח API!<br/>
                    אפשר לבקש ממני לסרוק שגיאות, לבנות אוטומציות או לשלוט במכשירים.<br/>
                    רוצה מודל ספציפי כמו <b>gpt-6-astra</b>? לחץ על כפתור ה-<b>+</b> למטה והזן מפתח API.
                  ` : `
                    מחובר לספק <b>${s.provider}</b> עם מודל <b>${s.model}</b> ברמת חשיבה <b>${s.thinking_level.toUpperCase()}</b>.<br/>
                    מה תרצה שנעשה בבית היום?
                  `}
                </div>
              </div>
            ` : ''}

            ${this.chatHistory.map((msg) => `
              <div class="message-bubble ${msg.role === 'user' ? 'message-user' : 'message-assistant'}">
                ${msg.fallbackNotice ? `
                  <div class="fallback-banner">
                    <span>⚠️</span>
                    <span>${msg.fallbackNotice}</span>
                  </div>
                ` : ''}
                <div>${msg.content}</div>

                ${msg.proposals && msg.proposals.length > 0 ? msg.proposals.map((p) => `
                  <div class="proposal-card">
                    <div class="proposal-header">
                      <div class="proposal-title">⚡ ${p.title}</div>
                      <span style="font-size: 11px; color: #ff9f0a; font-weight: 600;">ממתין לאישור</span>
                    </div>
                    <div class="yaml-block">${p.yaml_preview}</div>
                    <div class="proposal-buttons">
                      <button class="pro-pill-btn btn-approve" data-approve="${p.id}">
                        ✅ אשר והטמע במערכת
                      </button>
                      <button class="pro-pill-btn btn-reject" data-reject="${p.id}">
                        ❌ דחה ובטל
                      </button>
                    </div>
                  </div>
                `).join('') : ''}
              </div>
            `).join('')}

            ${this.isLoading ? `
              <div class="message-bubble message-assistant" style="display: flex; gap: 8px; align-items: center;">
                <span>חשיבה ועיבוד נתונים...</span>
                <span style="font-size: 16px; animation: spin 1s infinite linear;">⚙️</span>
              </div>
            ` : ''}
          </div>

          <!-- Slide-up Drawer: Opened by "+" or Status Pill -->
          <div class="drawer-overlay" id="drawer">
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
                  <option value="openai" ${s.provider === 'openai' ? 'selected' : ''}>OpenAI (ChatGPT / GPT-4o / o1 / GPT-6)</option>
                  <option value="gemini" ${s.provider === 'gemini' ? 'selected' : ''}>Google Gemini (Flash / Pro)</option>
                  <option value="anthropic" ${s.provider === 'anthropic' ? 'selected' : ''}>Anthropic Claude (Sonnet / Opus)</option>
                  <option value="deepseek" ${s.provider === 'deepseek' ? 'selected' : ''}>DeepSeek (V3 / R1 Reasoner)</option>
                  <option value="openrouter" ${s.provider === 'openrouter' ? 'selected' : ''}>OpenRouter (מגוון מודלים גלובליים)</option>
                  <option value="custom" ${s.provider === 'custom' ? 'selected' : ''}>שרת מקומי / Custom (Ollama)</option>
                </select>
              </div>

              <!-- מלבן 3: בחירת מודל והדבקה חופשית -->
              <div class="pro-card">
                <div class="card-header">
                  <div class="card-icon">🧠</div>
                  <div>
                    <div class="card-title">3. בחירת מודל (פתוח)</div>
                    <div class="card-subtitle">הקלד או הדבק כל שם מודל</div>
                  </div>
                </div>
                <input type="text" class="pro-input" id="model-input" value="${s.model}" placeholder="למשל: gpt-6-astra, o1, deepseek-r1..." />
                <div style="font-size: 11px; color: #86868b; margin-top: 4px;">
                  💡 חופשי לחלוטין: הדבק כל מודל עתידי בלי לחכות לעדכון
                </div>
              </div>

              <!-- מלבן 4: רמת חשיבה עם Fallback -->
              <div class="pro-card">
                <div class="card-header">
                  <div class="card-icon">⚡</div>
                  <div>
                    <div class="card-title">4. רמת חשיבה (Reasoning)</div>
                    <div class="card-subtitle">ירידה אוטומטית עם חיווי כשלא נתמך</div>
                  </div>
                </div>
                <div class="thinking-pills">
                  ${['off', 'low', 'medium', 'high', 'xhigh', 'max'].map((lvl) => `
                    <div class="thinking-pill ${s.thinking_level === lvl ? 'active' : ''}" data-level="${lvl}">
                      ${lvl === 'off' ? 'Off' : lvl.toUpperCase()}
                    </div>
                  `).join('')}
                </div>
              </div>

              <!-- מלבן 5: API Key (אופציונלי למצב חינמי) -->
              <div class="pro-card">
                <div class="card-header">
                  <div class="card-icon">🔑</div>
                  <div>
                    <div class="card-title">5. מפתח API (API Key)</div>
                    <div class="card-subtitle">השאר ריק למצב חינמי בסיסי</div>
                  </div>
                </div>
                <input type="password" class="pro-input" id="api-key-input" placeholder="הדבק מפתח API (אופציונלי)..." value="${s.api_key || ''}" />
                <div style="font-size: 11px; color: #86868b; margin-top: 4px;">
                  ללא מפתח המערכת תפעל במצב חינמי עד המגבלה.
                </div>
              </div>
            </div>

            <button class="pro-pill-btn btn-approve" id="save-drawer-btn" style="margin-top: 8px; padding: 12px;">
              💾 שמור את כל השינויים וסגור
            </button>
          </div>

          <!-- Chat Input Bar with the "+" Button -->
          <div class="chat-input-bar">
            <!-- The "+" Button -->
            <button class="pro-plus-btn ${this.isDrawerOpen ? 'active' : ''}" id="plus-btn" title="פתח הגדרות ספק, מודל וחשיבה">
              +
            </button>

            <!-- Text Input -->
            <input type="text" class="chat-input" id="chat-input" placeholder="כתוב הוראה לסוכן (למשל: 'בדוק שגיאות בלוגים', 'צור אוטומציה לכיבוי הדוד')..." />

            <!-- Send Button -->
            <button class="send-btn" id="send-btn">↑</button>
          </div>
        </div>
      </div>
    `;

    this.attachEventListeners();
  }

  attachEventListeners() {
    const root = this.shadowRoot;

    // Toggle Drawer via "+" Button or Status Pill
    const plusBtn = root.querySelector('#plus-btn');
    const statusPillBtn = root.querySelector('#status-pill-btn');
    const closeDrawerBtn = root.querySelector('#close-drawer-btn');

    const toggleDrawer = () => {
      this.isDrawerOpen = !this.isDrawerOpen;
      this.render();
    };

    if (plusBtn) plusBtn.onclick = toggleDrawer;
    if (statusPillBtn) statusPillBtn.onclick = toggleDrawer;
    if (closeDrawerBtn) closeDrawerBtn.onclick = toggleDrawer;

    // Thinking Pills
    root.querySelectorAll('.thinking-pill').forEach((pill) => {
      pill.onclick = () => {
        this.settings.thinking_level = pill.getAttribute('data-level');
        this.render();
      };
    });

    // Save Settings from Drawer
    const saveBtn = root.querySelector('#save-drawer-btn');
    if (saveBtn) {
      saveBtn.onclick = () => {
        this.settings.agent_role = root.querySelector('#agent-role-select').value;
        this.settings.provider = root.querySelector('#provider-select').value;
        this.settings.model = root.querySelector('#model-input').value.trim();
        const key = root.querySelector('#api-key-input').value.trim();
        this.settings.api_key = key;
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
    if (chatInput) {
      chatInput.onkeydown = (e) => {
        if (e.key === 'Enter') handleSend();
      };
    }

    // Start New Chat Button
    const newChatBtn = root.querySelector('#new-chat-btn');
    if (newChatBtn) {
      newChatBtn.onclick = () => this.startNewChat();
    }

    // Approve / Reject buttons inside chat
    root.querySelectorAll('[data-approve]').forEach((btn) => {
      btn.onclick = () => {
        const id = btn.getAttribute('data-approve');
        this.resolveAction(id, true);
      };
    });

    root.querySelectorAll('[data-reject]').forEach((btn) => {
      btn.onclick = () => {
        const id = btn.getAttribute('data-reject');
        this.resolveAction(id, false);
      };
    });
  }
}

if (!customElements.get('ai-agent-panel')) {
  customElements.define('ai-agent-panel', AIAgentPanel);
}
if (!customElements.get('ai-agent-card')) {
  customElements.define('ai-agent-card', AIAgentPanel);
}

// Register in Lovelace card picker (only once)
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'ai-agent-card')) {
  window.customCards.push({
    type: 'ai-agent-card',
    name: 'AI Agent Pro',
    description: 'סוכן AI אוטונומי עם כפתור +, מנגנון אישורים, תמיכה בכל הספקים ומודלים עתידיים.',
  });
}

