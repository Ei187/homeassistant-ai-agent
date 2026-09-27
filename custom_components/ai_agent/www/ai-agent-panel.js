/**
 * AI Agent Pro - Apple Edition Dashboard Panel & Card
 * Pure Vanilla Web Component with Apple-style Glassmorphism & Micro-Interactions
 */

class AIAgentPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.hass = null;
    this.settings = {
      agent_role: 'diagnostic',
      provider: 'openai',
      model: 'gpt-6-astra',
      thinking_level: 'high',
      require_approval: true,
      api_key: '',
      base_url: 'https://api.openai.com/v1',
    };
    this.chatHistory = [];
    this.pendingProposals = [];
    this.isLoading = false;
    this.activeFallbackNotice = null;
    this.isSettingsOpen = false;
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
        ...this.settings,
      });
      this.showToast('✅ ההגדרות נשמרו בהצלחה');
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
        this.render();
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
    this.render();

    try {
      const res = await this._hass.callWS({
        type: 'ai_agent/chat',
        message: text,
        history: this.chatHistory.slice(-6),
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
    } catch (e) {
      this.chatHistory.push({
        role: 'assistant',
        content: `⚠️ שגיאה בתקשורת עם הסוכן: ${e.message || e}`,
        isError: true,
      });
    } finally {
      this.isLoading = false;
      this.render();
      this.scrollToBottom();
    }
  }

  showToast(msg) {
    const toast = document.createElement('div');
    toast.className = 'apple-toast';
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
    this.render();
  }

  render() {
    const s = this.settings;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          min-height: 820px;
          background: #000000;
          color: #f5f5f7;
          font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          direction: rtl;
          box-sizing: border-box;
          padding: 24px;
          overflow-y: auto;
        }

        * { box-sizing: border-box; }

        /* Apple Glass Card Container */
        .app-container {
          max-width: 1080px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        /* Top Header */
        .apple-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 12px;
        }
        .header-title {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .apple-logo-badge {
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
          font-size: 24px;
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

        /* Header Toggle Button */
        .apple-btn-toggle {
          background: rgba(255, 255, 255, 0.08);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: #ffffff;
          padding: 9px 18px;
          border-radius: 980px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .apple-btn-toggle:hover {
          background: rgba(255, 255, 255, 0.16);
          transform: scale(1.02);
        }

        /* The 5 Individual Rectangles (Apple Setting Cards) */
        .cards-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 16px;
          transition: all 0.3s ease;
        }

        .apple-card {
          background: #1c1c1e;
          background: linear-gradient(180deg, rgba(28,28,30,0.85) 0%, rgba(20,20,22,0.95) 100%);
          backdrop-filter: blur(30px);
          -webkit-backdrop-filter: blur(30px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 20px;
          padding: 20px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
          position: relative;
          overflow: hidden;
          transition: transform 0.25s ease, border-color 0.25s ease;
        }
        .apple-card:hover {
          border-color: rgba(255, 255, 255, 0.18);
        }

        .card-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 14px;
        }
        .card-icon {
          width: 32px;
          height: 32px;
          border-radius: 10px;
          background: rgba(255, 255, 255, 0.06);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
        }
        .card-title {
          font-size: 15px;
          font-weight: 600;
          color: #f5f5f7;
          letter-spacing: -0.2px;
        }
        .card-subtitle {
          font-size: 12px;
          color: #86868b;
          margin-top: 2px;
        }

        /* Inputs & Selects Apple Style */
        .apple-select, .apple-input {
          width: 100%;
          background: rgba(0, 0, 0, 0.35);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 12px;
          padding: 12px 14px;
          color: #ffffff;
          font-size: 14px;
          outline: none;
          transition: all 0.2s ease;
          appearance: none;
          -webkit-appearance: none;
        }
        .apple-select:focus, .apple-input:focus {
          border-color: #0a84ff;
          box-shadow: 0 0 0 3px rgba(10, 132, 255, 0.25);
          background: rgba(0, 0, 0, 0.55);
        }

        /* Pill Group for Thinking Level */
        .thinking-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 10px;
        }
        .thinking-pill {
          flex: 1;
          min-width: 60px;
          text-align: center;
          padding: 10px 8px;
          border-radius: 12px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #a1a1a6;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .thinking-pill:hover {
          background: rgba(255, 255, 255, 0.1);
          color: #ffffff;
        }
        .thinking-pill.active {
          background: #0a84ff;
          color: #ffffff;
          border-color: #0a84ff;
          box-shadow: 0 4px 14px rgba(10, 132, 255, 0.4);
        }

        /* Fallback Alert Banner */
        .fallback-banner {
          background: rgba(255, 159, 10, 0.12);
          border: 1px solid rgba(255, 159, 10, 0.3);
          border-radius: 14px;
          padding: 12px 16px;
          color: #ff9f0a;
          font-size: 13px;
          display: flex;
          align-items: center;
          gap: 10px;
          margin-top: 12px;
          animation: slideDown 0.3s ease;
        }

        /* Switch Toggle (Human-in-the-Loop) */
        .switch-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 12px;
        }
        .switch {
          position: relative;
          display: inline-block;
          width: 50px;
          height: 30px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
          position: absolute;
          cursor: pointer;
          top: 0; left: 0; right: 0; bottom: 0;
          background-color: rgba(255,255,255,0.15);
          transition: .3s cubic-bezier(0.16, 1, 0.3, 1);
          border-radius: 34px;
        }
        .slider:before {
          position: absolute;
          content: "";
          height: 24px;
          width: 24px;
          left: 3px;
          bottom: 3px;
          background-color: white;
          transition: .3s cubic-bezier(0.16, 1, 0.3, 1);
          border-radius: 50%;
          box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        }
        input:checked + .slider { background-color: #30d158; }
        input:checked + .slider:before { transform: translateX(20px); }

        /* Chat Canvas Panel */
        .chat-container {
          background: #1c1c1e;
          background: linear-gradient(180deg, rgba(28,28,30,0.9) 0%, rgba(18,18,20,0.95) 100%);
          backdrop-filter: blur(30px);
          -webkit-backdrop-filter: blur(30px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 24px;
          display: flex;
          flex-direction: column;
          height: 600px;
          box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
          overflow: hidden;
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
          max-width: 80%;
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

        /* Apple Interactive Proposal Card in Chat */
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
        .apple-pill-btn {
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

        /* Chat Input Bar */
        .chat-input-bar {
          padding: 16px 20px;
          background: rgba(0, 0, 0, 0.4);
          border-top: 1px solid rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          gap: 12px;
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
        }
        .send-btn:hover {
          transform: scale(1.06);
        }

        /* Toast */
        .apple-toast {
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
        .apple-toast.visible {
          opacity: 1;
          transform: translateX(-50%) translateY(0);
        }

        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      </style>

      <div class="app-container">
        <!-- Apple Header -->
        <div class="apple-header">
          <div class="header-title">
            <div class="apple-logo-badge">🤖</div>
            <div class="title-text">
              <h1>סוכן AI חכם ל-Home Assistant</h1>
              <p>ניהול, אוטומציות ותיקון תקלות באבטחת Human-in-the-Loop</p>
            </div>
          </div>
          <button class="apple-btn-toggle" id="toggle-settings-btn">
            ${this.isSettingsOpen ? '✕ סגור הגדרות' : '⚙️ הגדרות מודלים וסוכנים'}
          </button>
        </div>

        <!-- 5 Separate Selection Cards (Shown when toggled or configured) -->
        <div class="cards-grid" style="display: ${this.isSettingsOpen ? 'grid' : 'none'};">
          
          <!-- מלבן 1: בחירת סוכן -->
          <div class="apple-card">
            <div class="card-header">
              <div class="card-icon">👤</div>
              <div>
                <div class="card-title">1. מלבן בחירת סוכן</div>
                <div class="card-subtitle">בחר את תפקיד הסוכן הפעיל</div>
              </div>
            </div>
            <select class="apple-select" id="agent-role-select">
              <option value="omni" ${s.agent_role === 'omni' ? 'selected' : ''}>👑 סוכן-על שעושה הכל ללא הגבלה (אוטומציות, תיקונים, לוגים ושליטה)</option>
              <option value="diagnostic" ${s.agent_role === 'diagnostic' ? 'selected' : ''}>🔧 סוכן דיאגנוסטיקה ותיקונים (לוגים ותקלות)</option>
              <option value="automations" ${s.agent_role === 'automations' ? 'selected' : ''}>⚡ סוכן מומחה אוטומציות (בנייה וקוד YAML)</option>
              <option value="butler" ${s.agent_role === 'butler' ? 'selected' : ''}>🏠 סוכן בית חכם כללי (שליטה ומענה שוטף)</option>
            </select>
          </div>

          <!-- מלבן 2: בחירת ספק -->
          <div class="apple-card">
            <div class="card-header">
              <div class="card-icon">🌐</div>
              <div>
                <div class="card-title">2. מלבן בחירת ספק (Provider)</div>
                <div class="card-subtitle">בחר את חברת ה-AI המפעילה</div>
              </div>
            </div>
            <select class="apple-select" id="provider-select">
              <option value="openai" ${s.provider === 'openai' ? 'selected' : ''}>OpenAI (ChatGPT / GPT-4o / o1 / GPT-6)</option>
              <option value="gemini" ${s.provider === 'gemini' ? 'selected' : ''}>Google Gemini (Flash / Pro)</option>
              <option value="anthropic" ${s.provider === 'anthropic' ? 'selected' : ''}>Anthropic Claude (Sonnet / Opus)</option>
              <option value="deepseek" ${s.provider === 'deepseek' ? 'selected' : ''}>DeepSeek (V3 / R1 Reasoner)</option>
              <option value="openrouter" ${s.provider === 'openrouter' ? 'selected' : ''}>OpenRouter (כל המודלים בעולם)</option>
              <option value="custom" ${s.provider === 'custom' ? 'selected' : ''}>שרת מקומי / Custom (Ollama / Local)</option>
            </select>
          </div>

          <!-- מלבן 3: בחירת מודל והדבקה חופשית של מודלים חדשים -->
          <div class="apple-card">
            <div class="card-header">
              <div class="card-icon">🧠</div>
              <div>
                <div class="card-title">3. מלבן בחירת מודל</div>
                <div class="card-subtitle">הקלד או הדבק כל שם מודל חדש שיצא</div>
              </div>
            </div>
            <input type="text" class="apple-input" id="model-input" value="${s.model}" placeholder="למשל: gpt-6-astra, o1, deepseek-r1..." />
            <div style="font-size: 11px; color: #86868b; margin-top: 6px;">
              💡 פתוח לחלוטין: הדבק כל מודל עתידי ללא צורך בעדכון תוכנה.
            </div>
          </div>

          <!-- מלבן 4: בורר רמות חשיבה אוניברסלי עם Fallback -->
          <div class="apple-card">
            <div class="card-header">
              <div class="card-icon">⚡</div>
              <div>
                <div class="card-title">4. מלבן רמת חשיבה (Reasoning)</div>
                <div class="card-subtitle">ירידה אוטומטית עם התראה כשלא נתמך</div>
              </div>
            </div>
            <div class="thinking-pills">
              ${['off', 'low', 'medium', 'high', 'xhigh', 'max'].map((lvl) => `
                <div class="thinking-pill ${s.thinking_level === lvl ? 'active' : ''}" data-level="${lvl}">
                  ${lvl === 'off' ? 'Off' : lvl.toUpperCase()}
                </div>
              `).join('')}
            </div>

            ${this.activeFallbackNotice ? `
              <div class="fallback-banner">
                <span>⚠️</span>
                <span>${this.activeFallbackNotice}</span>
              </div>
            ` : ''}
          </div>

          <!-- מלבן 5: אבטחה ואישורים (Human-in-the-Loop) -->
          <div class="apple-card">
            <div class="card-header">
              <div class="card-icon">🛡️</div>
              <div>
                <div class="card-title">5. מלבן בקרת אישורים</div>
                <div class="card-subtitle">שום פעולה לא מבוצעת בלי אישור ידני</div>
              </div>
            </div>
            <div class="switch-row">
              <span style="font-size: 13.5px; font-weight: 500;">בקש אישור לפני כל שינוי:</span>
              <label class="switch">
                <input type="checkbox" id="approval-checkbox" ${s.require_approval ? 'checked' : ''}>
                <span class="slider"></span>
              </label>
            </div>
            <div style="margin-top: 14px;">
              <input type="password" class="apple-input" id="api-key-input" placeholder="הזן API Key של הספק..." value="${s.api_key || ''}" />
            </div>
            <button class="apple-pill-btn btn-approve" id="save-settings-btn" style="margin-top: 12px; width: 100%;">
              💾 שמור את כל ההגדרות
            </button>
          </div>

        </div>

        <!-- Chat & Execution Interface -->
        <div class="chat-container">
          <div class="chat-scroll" id="chat-scroll">
            ${this.chatHistory.length === 0 ? `
              <div style="text-align: center; margin: auto; max-width: 440px;">
                <div style="font-size: 48px; margin-bottom: 12px;">✨</div>
                <div style="font-size: 18px; font-weight: 600; margin-bottom: 6px;">במה אוכל לעזור לך בבית?</div>
                <div style="font-size: 13px; color: #86868b; line-height: 1.5;">
                  בקש ממני ליצור אוטומציה חדשה, לסרוק תקלות ושגיאות בלוגים, או לפתור בעיה באחד המכשירים. אני אכין תוכנית מלאה ואבקש את אישורך לפני כל שינוי.
                </div>
              </div>
            ` : ''}

            ${this.chatHistory.map((msg) => `
              <div class="message-bubble ${msg.role === 'user' ? 'message-user' : 'message-assistant'}">
                ${msg.fallbackNotice ? `
                  <div class="fallback-banner" style="margin-bottom: 10px;">
                    ${msg.fallbackNotice}
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
                      <button class="apple-pill-btn btn-approve" data-approve="${p.id}">
                        ✅ אשר והטמע במערכת
                      </button>
                      <button class="apple-pill-btn btn-reject" data-reject="${p.id}">
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

          <!-- Chat Input Bar -->
          <div class="chat-input-bar">
            <input type="text" class="chat-input" id="chat-input" placeholder="כתוב הוראה לסוכן (למשל: 'תיצור אוטומציה לכיבוי הדוד', 'בדוק שגיאות בלוגים')..." />
            <button class="send-btn" id="send-btn">↑</button>
          </div>
        </div>

      </div>
    `;

    this.attachEventListeners();
  }

  attachEventListeners() {
    const root = this.shadowRoot;

    // Toggle Settings
    const toggleBtn = root.querySelector('#toggle-settings-btn');
    if (toggleBtn) {
      toggleBtn.onclick = () => {
        this.isSettingsOpen = !this.isSettingsOpen;
        this.render();
      };
    }

    // Thinking Pills Selection
    root.querySelectorAll('.thinking-pill').forEach((pill) => {
      pill.onclick = () => {
        this.settings.thinking_level = pill.getAttribute('data-level');
        this.render();
      };
    });

    // Save Settings
    const saveBtn = root.querySelector('#save-settings-btn');
    if (saveBtn) {
      saveBtn.onclick = () => {
        this.settings.agent_role = root.querySelector('#agent-role-select').value;
        this.settings.provider = root.querySelector('#provider-select').value;
        this.settings.model = root.querySelector('#model-input').value.trim();
        this.settings.require_approval = root.querySelector('#approval-checkbox').checked;
        const key = root.querySelector('#api-key-input').value.trim();
        if (key) this.settings.api_key = key;
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

customElements.define('ai-agent-panel', AIAgentPanel);
customElements.define('ai-agent-card', AIAgentPanel);

// Register in Lovelace card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ai-agent-card',
  name: 'AI Agent Pro (Apple Edition)',
  description: 'סוכן AI אוטונומי מעוצב בסגנון אפל עם מנגנון אישורים, תמיכה בכל הספקים ומודלים עתידיים.',
});
