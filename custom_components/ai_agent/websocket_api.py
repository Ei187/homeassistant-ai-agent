"""WebSocket API endpoints for AI Agent Pro."""

from __future__ import annotations

import json
import logging
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
from .tools import PENDING_ACTIONS, TOOLS_SCHEMA, ToolEngine, async_resolve_action

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
    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_role)
    tool_engine = ToolEngine(
        hass,
        require_approval=settings.get(CONF_REQUIRE_APPROVAL, True),
    )

    history = msg.get("history") or []
    formatted_messages = list(history)
    formatted_messages.append({"role": "user", "content": msg["message"]})

    # If no API key is provided, run in Free Tier mode
    if not api_key:
        user_text = msg["message"].lower()
        proposals = []
        free_notice = "✨ **מצב חינמי פעיל (ללא API Key):** לחיבור מודלי-על כמו GPT-6 Astra, לחץ על כפתור ה-`+` למטה והדבק מפתח."

        # Built-in local tool handling for free tier
        if any(w in user_text for w in ["לוג", "שגיא", "תקל", "log", "error"]):
            errors_res = await tool_engine.execute_tool("scan_system_errors", {"limit": 10})
            if errors_res.get("status") == "ok":
                reply = "סרקתי את המערכת שלך במצב חינמי: לא נמצאו שגיאות קריטיות פעילות בלוגים של Home Assistant! 🎉"
            else:
                count = errors_res.get("count", 0)
                reply = f"סרקתי את המערכת שלך: נמצאו {count} שגיאות או אזהרות בלוגים. כדי לקבל ניתוח עמוק ותיקון אוטומטי, מומלץ להזין API Key בכפתור ה-`+`."
        elif any(w in user_text for w in ["אוטומצי", "דוד", "אור", "מזגן", "תכבה", "תדליק", "auto"]):
            # Create a smart preview proposal
            prop_res = await tool_engine.execute_tool("create_automation", {
                "alias": "כיבוי אוטומטי חכם",
                "description": f"אוטומציה שנוצרה לפי בקשתך: {msg['message']}",
                "trigger_yaml": "platform: time\nat: '23:00:00'",
                "action_yaml": "service: homeassistant.turn_off\ntarget:\n  entity_id: all",
            })
            if prop_res.get("requires_user_approval"):
                proposals.append({
                    "id": prop_res["action_id"],
                    "title": prop_res["title"],
                    "yaml_preview": prop_res["yaml_preview"],
                })
            reply = f"הכנתי הצעה לאוטומציה לפי בקשתך ('{msg['message']}'). היא מוצגת למטה וממתינה לאישורך."
        else:
            reply = (
                f"קיבלתי את הודעתך: '{msg['message']}'. "
                "אני פועל כרגע במצב חינמי בסיסי. באפשרותך לבקש ממני לסרוק שגיאות או להכין אוטומציות. "
                "לקבלת תשובות מורכבות וחשיבה עמוקה של מודל הדגל, לחץ על ה-`+` והזן מפתח API."
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
        # Step 1: Call Model with Tools
        response = await client.chat(
            messages=formatted_messages,
            system_prompt=system_prompt,
            tools=TOOLS_SCHEMA,
        )

        fallback_notice = response.get("fallback_notice")
        actual_level = response.get("actual_thinking_level")
        content = response.get("content") or ""
        tool_calls = response.get("tool_calls") or []

        proposals = []

        # Step 2: Handle any tool calls requested by the model
        if tool_calls:
            for tc in tool_calls:
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

                # Append tool turn to conversation
                formatted_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tc],
                })
                formatted_messages.append({
                    "role": "tool",
                    "name": fn_name,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

            # Call model again with tool results to formulate user reply
            final_turn = await client.chat(
                messages=formatted_messages,
                system_prompt=system_prompt,
            )
            content = final_turn.get("content") or content

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
