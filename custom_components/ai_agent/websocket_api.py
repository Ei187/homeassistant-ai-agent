"""WebSocket API endpoints for AI Agent Pro."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import (
    AGENT_SYSTEM_PROMPTS,
    CONF_AGENT_ROLE,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_REQUIRE_APPROVAL,
    CONF_THINKING_LEVEL,
    DOMAIN,
)
from .tools import PENDING_ACTIONS, TOOLS_SCHEMA, ToolEngine, async_resolve_action, get_entities_context

_LOGGER = logging.getLogger(__name__)


def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Register WebSocket handlers."""
    websocket_api.async_register_command(hass, ws_get_settings)
    websocket_api.async_register_command(hass, ws_save_settings)
    websocket_api.async_register_command(hass, ws_get_pending_actions)
    websocket_api.async_register_command(hass, ws_resolve_action)
    websocket_api.async_register_command(hass, ws_chat)


@websocket_api.websocket_command({vol.Required("type"): "ai_agent/get_settings"})
@callback
def ws_get_settings(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]) -> None:
    """Return active integration settings."""
    settings = hass.data.get(DOMAIN, {}).get("settings", {})
    # Mask API key for security
    safe_settings = dict(settings)
    if safe_settings.get(CONF_API_KEY):
        safe_settings[CONF_API_KEY] = "••••••••" + safe_settings[CONF_API_KEY][-4:]
    connection.send_result(msg["id"], safe_settings)


@websocket_api.websocket_command({
    vol.Required("type"): "ai_agent/save_settings",
    vol.Optional(CONF_AGENT_ROLE): str,
    vol.Optional(CONF_PROVIDER): str,
    vol.Optional(CONF_MODEL): str,
    vol.Optional(CONF_THINKING_LEVEL): str,
    vol.Optional(CONF_API_KEY): str,
    vol.Optional(CONF_BASE_URL): str,
    vol.Optional(CONF_REQUIRE_APPROVAL): bool,
})
@websocket_api.async_response
async def ws_save_settings(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]) -> None:
    """Save updated settings from the frontend."""
    storage = hass.data[DOMAIN]["storage"]
    current = hass.data[DOMAIN]["settings"]

    for key in (CONF_AGENT_ROLE, CONF_PROVIDER, CONF_MODEL, CONF_THINKING_LEVEL, CONF_BASE_URL, CONF_REQUIRE_APPROVAL):
        if key in msg:
            current[key] = msg[key]

    if CONF_API_KEY in msg and msg[CONF_API_KEY] and not msg[CONF_API_KEY].startswith("••••"):
        current[CONF_API_KEY] = msg[CONF_API_KEY]

    await storage.async_save(current)

    # Sync with config entry options so both entry options and storage stay in lockstep
    entry = hass.data.get(DOMAIN, {}).get("entry")
    if entry:
        hass.config_entries.async_update_entry(entry, options=dict(current))

    # Refresh active client
    await hass.data[DOMAIN]["refresh_client"]()

    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({vol.Required("type"): "ai_agent/get_pending_actions"})
@callback
def ws_get_pending_actions(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]) -> None:
    """Get all actions currently waiting for human approval."""
    actions = list(PENDING_ACTIONS.values())
    connection.send_result(msg["id"], {"actions": actions})


@websocket_api.websocket_command({
    vol.Required("type"): "ai_agent/resolve_action",
    vol.Required("action_id"): str,
    vol.Required("approved"): bool,
})
@websocket_api.async_response
async def ws_resolve_action(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]) -> None:
    """Approve or reject a pending action."""
    action_id = msg["action_id"]
    approved = msg["approved"]
    result = await async_resolve_action(hass, action_id, approved)
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "ai_agent/chat",
    vol.Required("message"): str,
    vol.Optional("history"): list,
})
@websocket_api.async_response
async def ws_chat(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: Dict[str, Any]) -> None:
    """Process a user chat message through the multi-agent engine."""
    client = hass.data[DOMAIN].get("client")
    settings = hass.data[DOMAIN].get("settings", {})
    api_key = settings.get(CONF_API_KEY, "")

    agent_role = settings.get(CONF_AGENT_ROLE, "omni")
    base_prompt = AGENT_SYSTEM_PROMPTS.get(agent_role, AGENT_SYSTEM_PROMPTS["omni"])
    tool_engine = ToolEngine(
        hass,
        require_approval=settings.get(CONF_REQUIRE_APPROVAL, True),
    )

    history = msg.get("history") or []
    formatted_messages = list(history)
    formatted_messages.append({"role": "user", "content": msg["message"]})

    # If no API key is provided, run in Smart Free Tier mode
    if not api_key:
        user_raw = msg["message"]
        user_text = user_raw.lower()
        proposals = []
        free_notice = "✨ **מצב מקומי חינמי:** פועל ללא צורך במפתח API. לחיבור מודלי שפה עמוקים (GPT-6, Claude 3.7, Gemini 2.5), לחץ על ה-`+` והדבק מפתח."

        # 1. Error scan
        if any(w in user_text for w in ["לוג", "שגיא", "תקל", "log", "error"]):
            errors_res = await tool_engine.execute_tool("scan_system_errors", {"limit": 10})
            if errors_res.get("status") == "ok":
                reply = "סרקתי את המערכת: לא נמצאו שגיאות קריטיות פעילות בלוגים של Home Assistant! 🎉"
            else:
                count = errors_res.get("count", 0)
                reply = f"סרקתי את המערכת: נמצאו {count} שגיאות או אזהרות בלוגים. באפשרותך לבקש פרטים נוספים או להזין מפתח AI בכפתור ה-`+` לניתוח מעמיק."

        # 2. What's on query
        elif any(w in user_text for w in ["מה דולק", "איזה אורות דולקים", "מה פועל", "מה עובד"]):
            active = [s.name or s.entity_id for s in hass.states.async_all() if s.domain in ("light", "switch") and s.state == "on"]
            if active:
                reply = f"המכשירים שדולקים כרגע בבית ({len(active)}): {', '.join(active[:15])}."
            else:
                reply = "כל האורות והמתגים בבית כבויים כרגע. 🌙"

        # 3. Automation proposal
        elif any(w in user_text for w in ["צור אוטומצי", "תבנה אוטומצי", "אוטומציה"]):
            prop_res = await tool_engine.execute_tool("create_automation", {
                "alias": "אוטומציה חכמה",
                "description": f"בקשה מהצ'אט: {user_raw}",
                "trigger_yaml": "platform: time\nat: '23:00:00'",
                "action_yaml": "service: homeassistant.turn_off\ntarget:\n  entity_id: all",
            })
            if prop_res.get("requires_user_approval"):
                proposals.append({
                    "id": prop_res["action_id"],
                    "title": prop_res["title"],
                    "yaml_preview": prop_res["yaml_preview"],
                })
            reply = f"הכנתי הצעה לאוטומציה לפי בקשתך ('{user_raw}'). היא מוצגת למטה וממתינה לאישורך."

        # 4. Direct device control
        elif any(w in user_text for w in ["תדליק", "תכבה", "תפעיל", "תסגור", "turn on", "turn off", "שנה"]):
            is_off = any(w in user_text for w in ["תכבה", "תסגור", "כבה", "turn off"])
            action = "turn_off" if is_off else "turn_on"
            ctrl_res = await tool_engine.execute_tool("control_device", {
                "entity_id": "all_lights" if "כל האור" in user_text else user_raw,
                "action": action,
            })
            reply = ctrl_res.get("message", "בוצע.")

        else:
            reply = (
                f"קיבלתי את הודעתך: '{user_raw}'. "
                "אני פועל במצב מקומי חינמי ויכול לשלוט במכשירים (למשל 'תדליק אור בסלון', 'מה דולק בבית'), "
                "לסרוק שגיאות ולבנות אוטומציות. לחיבור מודלי-על מתקדמים, לחץ על ה-`+` למטה והזן מפתח API."
            )

        connection.send_result(
            msg["id"],
            {
                "reply": reply,
                "fallback_notice": free_notice,
                "actual_thinking_level": "free",
                "proposals": proposals,
            },
        )
        return

    try:
        # Prepare system prompt with live home entity context
        entities_text = get_entities_context(hass)
        full_system_prompt = (
            f"{base_prompt}\n\n"
            f"### רשימת המכשירים והישויות בבית (Home Entities & Current States):\n"
            f"{entities_text}\n\n"
            "הנחיות חשובות לפעולה:\n"
            "1. כשמשתמש מבקש לשלוט במכשיר (הדלקה, כיבוי, שינוי טמפרטורה), קרא מיד לכלי control_device עם ה-entity_id המדויק מהרשימה.\n"
            "2. כשמשתמש שואל מה פתוח/דולק או על נתון של מכשיר, ענה ישירות לפי המצב הנוכחי ברשימה או קרא לכלי המתאים.\n"
            "3. ענה תמיד בעברית טבעית, תמציתית וישירה."
        )

        # Step 1: Call Model with Tools
        response = await client.chat(
            messages=formatted_messages,
            system_prompt=full_system_prompt,
            tools=TOOLS_SCHEMA,
        )

        fallback_notice = response.get("fallback_notice")
        actual_level = response.get("actual_thinking_level")
        content = response.get("content") or ""
        tool_calls = response.get("tool_calls") or []

        proposals = []

        # Step 2: Handle tool calls strictly per OpenAI Chat Completion specification
        if tool_calls:
            formatted_messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                call_id = tc.get("id") or str(uuid.uuid4())
                fn = tc.get("function", {})
                fn_name = fn.get("name")
                raw_args = fn.get("arguments") or "{}"
                fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                tool_result = await tool_engine.execute_tool(fn_name, fn_args)

                if tool_result.get("requires_user_approval"):
                    proposals.append({
                        "id": tool_result["action_id"],
                        "title": tool_result["title"],
                        "yaml_preview": tool_result["yaml_preview"],
                    })

                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn_name,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

            # Call model again with tool results to formulate user reply
            final_turn = await client.chat(
                messages=formatted_messages,
                system_prompt=full_system_prompt,
            )
            content = final_turn.get("content") or content or "הפעולה בוצעה בהצלחה."

        connection.send_result(
            msg["id"],
            {
                "reply": content,
                "fallback_notice": fallback_notice,
                "actual_thinking_level": actual_level,
                "proposals": proposals,
            },
        )
    except Exception as err:
        _LOGGER.exception("Error during AI chat handling: %s", err)
        connection.send_error(msg["id"], "chat_error", str(err))
