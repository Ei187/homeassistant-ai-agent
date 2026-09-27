"""Constants for AI Agent Pro Integration."""

DOMAIN = "ai_agent"
VERSION = "1.2.0"

# Storage
STORAGE_KEY = f"{DOMAIN}_settings"
STORAGE_VERSION = 1

# Providers
PROVIDER_OPENAI = "openai"
PROVIDER_GEMINI = "gemini"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_CUSTOM = "custom"

PROVIDERS = [
    PROVIDER_OPENAI,
    PROVIDER_GEMINI,
    PROVIDER_ANTHROPIC,
    PROVIDER_DEEPSEEK,
    PROVIDER_OPENROUTER,
    PROVIDER_CUSTOM,
]

PROVIDER_NAMES = {
    PROVIDER_OPENAI: "OpenAI (ChatGPT / GPT-4o / o1 / GPT-6)",
    PROVIDER_GEMINI: "Google Gemini (Flash / Pro)",
    PROVIDER_ANTHROPIC: "Anthropic Claude (Sonnet / Opus / Haiku)",
    PROVIDER_DEEPSEEK: "DeepSeek (V3 / R1 Reasoner)",
    PROVIDER_OPENROUTER: "OpenRouter (All Global Models)",
    PROVIDER_CUSTOM: "Custom Endpoint (Ollama / Local / Private API)",
}

DEFAULT_BASE_URLS = {
    PROVIDER_OPENAI: "https://api.openai.com/v1",
    PROVIDER_GEMINI: "https://generativelanguage.googleapis.com",
    PROVIDER_ANTHROPIC: "https://api.anthropic.com/v1",
    PROVIDER_DEEPSEEK: "https://api.deepseek.com/v1",
    PROVIDER_OPENROUTER: "https://openrouter.ai/api/v1",
    PROVIDER_CUSTOM: "http://localhost:11434/v1",
}

# Default Known Models (User can freely type/paste ANY model)
DEFAULT_MODELS = {
    PROVIDER_OPENAI: ["gpt-6-astra", "o1", "o3-mini", "gpt-4o", "gpt-4o-mini"],
    PROVIDER_GEMINI: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    PROVIDER_ANTHROPIC: ["claude-3-7-sonnet", "claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-opus"],
    PROVIDER_DEEPSEEK: ["deepseek-reasoner", "deepseek-chat"],
    PROVIDER_OPENROUTER: ["openai/gpt-6-astra", "anthropic/claude-3.7-sonnet", "deepseek/deepseek-r1"],
    PROVIDER_CUSTOM: ["llama3.3", "qwen2.5-coder", "mistral-large"],
}

# Thinking / Reasoning Levels
THINKING_OFF = "off"
THINKING_LOW = "low"
THINKING_MEDIUM = "medium"
THINKING_HIGH = "high"
THINKING_XHIGH = "xhigh"
THINKING_MAX = "max"

THINKING_LEVELS = [
    THINKING_OFF,
    THINKING_LOW,
    THINKING_MEDIUM,
    THINKING_HIGH,
    THINKING_XHIGH,
    THINKING_MAX,
]

THINKING_LEVEL_NAMES = {
    THINKING_OFF: "כבוי (Off / Instant - ללא חשיבה)",
    THINKING_LOW: "נמוכה (Low - תגובה מהירה)",
    THINKING_MEDIUM: "בינונית (Medium - אוטומציות רגילות)",
    THINKING_HIGH: "גבוהה (High - פתרון תקלות מורכבות)",
    THINKING_XHIGH: "גבוהה מאוד (XHigh - ניתוח מעמיק)",
    THINKING_MAX: "מקסימלית (Max - חשיבה מירבית ללא הגבלה)",
}

# Fallback sequence: Each step tries to drop to the next if unsupported
FALLBACK_ORDER = [
    THINKING_MAX,
    THINKING_XHIGH,
    THINKING_HIGH,
    THINKING_MEDIUM,
    THINKING_LOW,
    THINKING_OFF,
]

# Agent Roles / Profiles
AGENT_OMNI = "omni"
AGENT_DIAGNOSTIC = "diagnostic"
AGENT_AUTOMATIONS = "automations"
AGENT_BUTLER = "butler"

AGENT_ROLES = [
    AGENT_OMNI,
    AGENT_DIAGNOSTIC,
    AGENT_AUTOMATIONS,
    AGENT_BUTLER,
]

AGENT_ROLE_NAMES = {
    AGENT_OMNI: "👑 סוכן-על שעושה הכל (אוטומציות, תיקון תקלות, לוגים, שליטה מלאה וללא הגבלה)",
    AGENT_DIAGNOSTIC: "🔧 סוכן דיאגנוסטיקה ותיקונים (סורק לוגים, מתקן תקלות ומתריע)",
    AGENT_AUTOMATIONS: "⚡ סוכן מומחה אוטומציות (בונה, בודק ומטמיע תרחישים וקוד YAML)",
    AGENT_BUTLER: "🏠 סוכן מנהל בית כללי (שליטה במכשירים, מענה לשאלות וסטטוס)",
}

AGENT_SYSTEM_PROMPTS = {
    AGENT_OMNI: (
        "אתה סוכן-על אוטונומי ראשי (Master AI Assistant) עבור Home Assistant ללא שום הגבלה. "
        "יש לך סמכות ויכולת מלאה לעשות הכל: לבנות ולערוך אוטומציות מורכבות, לסרוק לוגים בזמן אמת, "
        "לאבחן ולתקן תקלות במכשירים ובאינטגרציות, לשלוט בכל הישויות בבית, להפעיל שירותים ולענות על שאלות. "
        "כשמשתמש מבקש ממך משהו, פעל באופן מיידי ומלא. עבור פעולות שמשנות הגדרות או יוצרות קוד, "
        "הצג תצוגה מקדימה ברורה ובקש אישור קליק מהמשתמש."
    ),
    AGENT_DIAGNOSTIC: (
        "אתה סוכן AI מומחה לדיאגנוסטיקה, יציבות ותיקון תקלות ב-Home Assistant. "
        "תפקידך לסרוק שגיאות בלוגים, לזהות התנתקויות של רכיבים ואינטגרציות, ולהציע פתרונות מדויקים. "
        "חוק עליון: לעולם אל תבצע פעולה משנה-מצב או תיקון בלי לתאר תחילה מה התקלה, מה הפתרון, "
        "ולבקש אישור מפורש מהמשתמש (Human-in-the-Loop)."
    ),
    AGENT_AUTOMATIONS: (
        "אתה סוכן AI מומחה לבנייה, ייעול ותחזוקת אוטומציות ב-Home Assistant. "
        "כשמשתמש מבקש תרחיש, תכנן את ה-Triggers, Conditions ו-Actions בצורה מושלמת. "
        "הצג תמיד תצוגה מקדימה נקייה של קוד ה-YAML, הסבר בעברית פשוטה מה האוטומציה תעשה, "
        "ובקש אישור לחיצה (Approve) לפני ההטמעה במערכת."
    ),
    AGENT_BUTLER: (
        "אתה סוכן הבית החכם האישי של המשתמש ב-Home Assistant. "
        "אתה שולט בתאורה, מיזוג, מתגים, מנעולים ומדיה. ענה בצורה אלגנטית, קצרה ונעימה. "
        "לפעולות רגישות (פתיחת מנעולים, שינוי קונפיגורציה), בקש אישור תחילה."
    ),
}

# Configuration Defaults
CONF_PROVIDER = "provider"
CONF_MODEL = "model"
CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_THINKING_LEVEL = "thinking_level"
CONF_AGENT_ROLE = "agent_role"
CONF_REQUIRE_APPROVAL = "require_approval"
CONF_NOTIFY_MOBILE = "notify_mobile"
CONF_MOBILE_NOTIFY_SERVICE = "mobile_notify_service"

DEFAULT_SETTINGS = {
    CONF_PROVIDER: PROVIDER_OPENAI,
    CONF_MODEL: "gpt-6-astra",
    CONF_API_KEY: "",
    CONF_BASE_URL: DEFAULT_BASE_URLS[PROVIDER_OPENAI],
    CONF_THINKING_LEVEL: THINKING_HIGH,
    CONF_AGENT_ROLE: AGENT_OMNI,
    CONF_REQUIRE_APPROVAL: True,
    CONF_NOTIFY_MOBILE: True,
    CONF_MOBILE_NOTIFY_SERVICE: "notify.notify",
}
