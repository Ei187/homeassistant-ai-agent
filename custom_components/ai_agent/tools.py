"""Home Assistant Tool Engine with Human-in-the-Loop Approval & Dry-Run Security."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional
import yaml

from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification

_LOGGER = logging.getLogger(__name__)

# In-memory registry of pending actions waiting for human approval
PENDING_ACTIONS: Dict[str, Dict[str, Any]] = {}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "create_automation",
            "description": "יוצר אוטומציה חדשה ב-Home Assistant. דורש תמיד אישור משתמש לפני כתיבה למערכת.",
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {"type": "string", "description": "שם האוטומציה בעברית או באנגלית"},
                    "description": {"type": "string", "description": "הסבר מה האוטומציה עושה"},
                    "trigger_yaml": {"type": "string", "description": "הגדרת ה-trigger ב-YAML"},
                    "condition_yaml": {"type": "string", "description": "הגדרת ה-condition ב-YAML (אופציונלי)"},
                    "action_yaml": {"type": "string", "description": "הגדרת ה-action ב-YAML"},
                },
                "required": ["alias", "description", "trigger_yaml", "action_yaml"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_system_errors",
            "description": "סורק את לוג השגיאות של המערכת (System Logs) לאיתור תקלות באינטגרציות, מכשירים או רשת.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "כמות שורות שגיאה מקסימלית לסריקה", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": "מחפש רשימת ישויות (Entities) ומכשירים קיימים בבית לפי שם או תחום (domain).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "טקסט לחיפוש (למשל 'סלון', 'אור', 'מזגן')"},
                    "domain": {"type": "string", "description": "תחום לסינון (למשל 'light', 'climate', 'switch')"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_state",
            "description": "שולף את המצב הנוכחי והמאפיינים (Attributes) של ישות מסוימת.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "מזהה הישות (למשל 'light.living_room')"},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_device",
            "description": "שולט במכשיר או ישות בבית (הדלקת/כיבוי אורות, מזגנים, מתגים, מנעולים, מדיה). מתבצע מידית.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "מזהה הישות (למשל 'light.moms_room', 'climate.ac')"},
                    "action": {"type": "string", "description": "הפעולה: turn_on, turn_off, toggle, set_temperature וכו'"},
                    "parameters": {"type": "object", "description": "פרמטרים נוספים אופציונליים"},
                },
                "required": ["entity_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_service_call",
            "description": "מציע להפעיל פעולה או שירות במערכת (למשל הפעלה מחדש של אינטגרציה, כיבוי מתג רגיש).",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "תחום השירות (למשל 'homeassistant', 'light')"},
                    "service": {"type": "string", "description": "שם השירות (למשל 'reload_config_entry', 'turn_on')"},
                    "service_data": {"type": "object", "description": "פרמטרים לפעולה"},
                    "reason": {"type": "string", "description": "הסבר למשתמש מדוע מומלץ לבצע את הפעולה"},
                },
                "required": ["domain", "service", "reason"],
            },
        },
    },
]


class ToolEngine:
    """Execution engine with Human-in-the-Loop protection."""

    def __init__(self, hass: HomeAssistant, require_approval: bool = True, notify_mobile: bool = True) -> None:
        self.hass = hass
        self.require_approval = require_approval
        self.notify_mobile = notify_mobile

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch tool call safely."""
        try:
            if name == "control_device":
                return await self._handle_control_device(args)
            if name == "scan_system_errors":
                return await self._scan_system_errors(args.get("limit", 10))
            if name == "search_entities":
                return await self._search_entities(args.get("query"), args.get("domain"))
            if name == "get_entity_state":
                return await self._get_entity_state(args.get("entity_id", ""))
            if name == "create_automation":
                return await self._handle_create_automation(args)
            if name == "propose_service_call":
                return await self._handle_propose_service_call(args)
            return {"error": f"Unknown tool name: {name}"}
        except Exception as err:
            _LOGGER.exception("Tool execution error in %s: %s", name, err)
            return {"error": str(err)}

    async def _handle_control_device(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Directly control an entity in Home Assistant with smart matching and multi-entity support."""
        raw_entity_id = args.get("entity_id", "")
        action = args.get("action", "turn_on")
        params = dict(args.get("parameters") or {})

        # Handle list or comma-separated entity IDs
        entity_ids = []
        if isinstance(raw_entity_id, list):
            entity_ids = raw_entity_id
        elif isinstance(raw_entity_id, str):
            entity_ids = [e.strip() for e in raw_entity_id.split(",") if e.strip()]

        if not entity_ids:
            return {"error": "לא צוין מזהה ישות (entity_id) לביצוע הפעולה."}

        # Handle special target: "all" or "all_lights"
        if len(entity_ids) == 1 and entity_ids[0].lower() in ("all", "all_lights", "כל האורות", "אורות"):
            target_lights = [
                s.entity_id for s in self.hass.states.async_all("light")
                if (s.state == "on" if action == "turn_off" else s.state == "off")
            ]
            if not target_lights:
                target_lights = [s.entity_id for s in self.hass.states.async_all("light")]
            if target_lights:
                await self.hass.services.async_call("light", action, {"entity_id": target_lights}, blocking=True)
                return {
                    "status": "success",
                    "message": f"הפעולה '{action}' בוצעה על כל האורות בבית ({len(target_lights)} נורות).",
                    "entities": target_lights,
                }

        results = []
        for eid in entity_ids:
            state = self.hass.states.get(eid)
            # Fuzzy match if not found directly
            if not state:
                clean_target = eid.replace("light.", "").replace("switch.", "").replace("climate.", "").replace("_", " ").lower()
                for s in self.hass.states.async_all():
                    s_name = (s.name or "").lower()
                    s_id = s.entity_id.lower()
                    if clean_target in s_name or clean_target in s_id:
                        eid = s.entity_id
                        state = s
                        break

            domain = eid.split(".")[0] if "." in eid else "homeassistant"
            call_params = dict(params)
            call_params["entity_id"] = eid

            try:
                # Try domain-specific service first
                if self.hass.services.has_service(domain, action):
                    await self.hass.services.async_call(domain, action, call_params, blocking=True)
                else:
                    # Fallback to homeassistant service (turn_on / turn_off / toggle)
                    await self.hass.services.async_call("homeassistant", action, call_params, blocking=True)

                friendly = state.name if state else eid
                results.append(f"{friendly} ({eid})")
            except Exception as err:
                _LOGGER.warning("Could not execute %s on %s: %s", action, eid, err)

        if results:
            return {
                "status": "success",
                "message": f"הפעולה '{action}' בוצעה בהצלחה על: {', '.join(results)}.",
                "controlled": results,
            }
        return {"error": f"לא ניתן היה לשלוט בישות '{raw_entity_id}'."}

    async def _scan_system_errors(self, limit: int) -> Dict[str, Any]:
        """Scan real or recent system logs for errors."""
        # Query Home Assistant system log entries if available
        errors = []
        if "system_log" in self.hass.data:
            entries = self.hass.data["system_log"]
            if hasattr(entries, "records"):
                for record in list(entries.records.values())[-limit:]:
                    if record.level in ("ERROR", "WARNING"):
                        errors.append({
                            "timestamp": record.timestamp,
                            "level": record.level,
                            "source": record.source,
                            "message": record.message[0] if record.message else "No message",
                        })

        if not errors:
            return {"status": "ok", "message": "לא נמצאו שגיאות קריטיות פעילות בלוגים של Home Assistant."}

        return {"status": "found_errors", "count": len(errors), "errors": errors}

    async def _search_entities(self, query: Optional[str], domain: Optional[str]) -> Dict[str, Any]:
        """Search entities by domain or friendly name."""
        results = []
        q = (query or "").lower()
        for state in self.hass.states.async_all():
            entity_id = state.entity_id
            name = state.name or ""
            if domain and not entity_id.startswith(f"{domain}."):
                continue
            if q and q not in entity_id.lower() and q not in name.lower():
                continue
            results.append({
                "entity_id": entity_id,
                "name": name,
                "state": state.state,
            })
            if len(results) >= 25:
                break
        return {"count": len(results), "entities": results}

    async def _get_entity_state(self, entity_id: str) -> Dict[str, Any]:
        """Get state of a single entity."""
        state = self.hass.states.get(entity_id)
        if not state:
            return {"error": f"ישות '{entity_id}' לא נמצאה במערכת."}
        return {
            "entity_id": entity_id,
            "state": state.state,
            "attributes": dict(state.attributes),
            "last_changed": state.last_changed.isoformat(),
        }

    async def _handle_create_automation(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate automation proposal with YAML preview and wait for approval."""
        alias = args.get("alias", "אוטומציה חדשה")
        desc = args.get("description", "")
        trigger_yaml = args.get("trigger_yaml", "")
        condition_yaml = args.get("condition_yaml", "")
        action_yaml = args.get("action_yaml", "")

        # Assemble clean YAML for preview
        full_yaml_dict = {
            "alias": alias,
            "description": desc,
            "trigger": yaml.safe_load(trigger_yaml) if trigger_yaml else [],
            "condition": yaml.safe_load(condition_yaml) if condition_yaml else [],
            "action": yaml.safe_load(action_yaml) if action_yaml else [],
        }
        full_yaml_str = yaml.dump(full_yaml_dict, allow_unicode=True, sort_keys=False)

        action_id = f"act_{uuid.uuid4().hex[:8]}"
        proposal = {
            "id": action_id,
            "type": "create_automation",
            "title": f"יצירת אוטומציה: {alias}",
            "description": desc,
            "yaml_preview": full_yaml_str,
            "created_at": time.time(),
            "status": "pending_approval",
            "payload": full_yaml_dict,
        }
        PENDING_ACTIONS[action_id] = proposal

        # Create persistent notification in HA
        persistent_notification.async_create(
            self.hass,
            f"**סוכן AI מציע ליצור אוטומציה:** `{alias}`\n\n"
            f"{desc}\n\n"
            f"```yaml\n{full_yaml_str}\n```\n\n"
            f"פתח את חלון הסוכן כדי לאשר או לדחות את הפעולה.",
            title=f"🤖 ממתין לאישורך: {alias}",
            notification_id=f"ai_agent_{action_id}",
        )

        return {
            "requires_user_approval": True,
            "action_id": action_id,
            "title": proposal["title"],
            "yaml_preview": full_yaml_str,
            "instruction": "ההצעה מוכנה וממתינה לאישור המשתמש. שאל את המשתמש האם לאשר את ההטמעה.",
        }

    async def _handle_propose_service_call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Propose service call and wait for approval."""
        action_id = f"act_{uuid.uuid4().hex[:8]}"
        domain = args.get("domain")
        service = args.get("service")
        data = args.get("service_data") or {}
        reason = args.get("reason", "")

        preview = yaml.dump({"service": f"{domain}.{service}", "data": data}, allow_unicode=True)

        proposal = {
            "id": action_id,
            "type": "call_service",
            "title": f"ביצוע פעולה: {domain}.{service}",
            "description": reason,
            "yaml_preview": preview,
            "created_at": time.time(),
            "status": "pending_approval",
            "payload": {"domain": domain, "service": service, "data": data},
        }
        PENDING_ACTIONS[action_id] = proposal

        persistent_notification.async_create(
            self.hass,
            f"**סוכן AI מציע לבצע פעולה:** `{domain}.{service}`\n\n"
            f"סיבה: {reason}\n\n"
            f"פתח את חלון הסוכן כדי לאשר או לדחות.",
            title=f"🤖 ממתין לאישורך: {domain}.{service}",
            notification_id=f"ai_agent_{action_id}",
        )

        return {
            "requires_user_approval": True,
            "action_id": action_id,
            "title": proposal["title"],
            "yaml_preview": preview,
            "instruction": "הפעולה ממתינה לאישור המשתמש. הצג את הסיבה ושאל אם לאשר.",
        }


async def async_resolve_action(hass: HomeAssistant, action_id: str, approved: bool) -> Dict[str, Any]:
    """Execute or reject a pending proposal after user confirmation."""
    proposal = PENDING_ACTIONS.get(action_id)
    if not proposal:
        return {"success": False, "error": "פעולה לא נמצאה או שכבר פג תוקפה."}

    # Dismiss notification
    persistent_notification.async_dismiss(hass, f"ai_agent_{action_id}")

    if not approved:
        proposal["status"] = "rejected"
        del PENDING_ACTIONS[action_id]
        return {"success": True, "status": "rejected", "message": "הפעולה נדחתה בהצלחה. המערכת לא שונתה."}

    action_type = proposal.get("type")
    payload = proposal.get("payload", {})

    try:
        if action_type == "create_automation":
            # Call automation creation service
            await hass.services.async_call(
                "automation",
                "create",
                payload,
                blocking=True,
            )
            # Reload automations
            await hass.services.async_call("automation", "reload", {}, blocking=True)
            proposal["status"] = "executed"
            del PENDING_ACTIONS[action_id]
            return {
                "success": True,
                "status": "executed",
                "message": f"האוטומציה '{proposal.get('title')}' נוצרה בהצלחה והוטמעה במערכת!",
            }

        if action_type == "call_service":
            domain = payload.get("domain")
            service = payload.get("service")
            data = payload.get("data") or {}
            await hass.services.async_call(domain, service, data, blocking=True)
            proposal["status"] = "executed"
            del PENDING_ACTIONS[action_id]
            return {
                "success": True,
                "status": "executed",
                "message": f"הפעולה '{domain}.{service}' בוצעה בהצלחה במערכת!",
            }

        return {"success": False, "error": f"סוג פעולה לא מוכר: {action_type}"}
    except Exception as err:
        _LOGGER.exception("Failed to execute approved action %s: %s", action_id, err)
        return {"success": False, "error": f"שגיאה בהפעלת השינוי: {err}"}


def get_entities_context(hass: HomeAssistant, max_entities: int = 150) -> str:
    """Format home entities and current states into a clear list for the AI."""
    lines = []
    relevant_domains = {
        "light", "switch", "climate", "cover", "fan", "lock",
        "media_player", "vacuum", "scene", "script", "automation", "sensor", "binary_sensor"
    }
    count = 0
    for state in hass.states.async_all():
        domain = state.domain
        if domain not in relevant_domains:
            continue
        # Skip internal or noisy sensors unless helpful
        if domain in ("sensor", "binary_sensor"):
            s_id = state.entity_id.lower()
            s_name = (state.name or "").lower()
            if not any(k in s_id or k in s_name for k in [
                "temp", "humidity", "battery", "motion", "door", "window",
                "power", "energy", "boiler", "דוד", "טמפ", "תנועה", "דלת", "חלון"
            ]):
                continue

        friendly_name = state.attributes.get("friendly_name", state.entity_id)
        current_state = state.state

        extra = []
        if "current_temperature" in state.attributes:
            extra.append(f"temp: {state.attributes['current_temperature']}°C")
        if "temperature" in state.attributes:
            extra.append(f"target: {state.attributes['temperature']}°C")
        if "brightness" in state.attributes and state.attributes["brightness"]:
            pct = round((state.attributes["brightness"] / 255) * 100)
            extra.append(f"brightness: {pct}%")

        extra_str = f" ({', '.join(extra)})" if extra else ""
        lines.append(f"- {state.entity_id} | '{friendly_name}' | state: {current_state}{extra_str}")
        count += 1
        if count >= max_entities:
            break

    if not lines:
        return "אין ישויות זמינות כרגע."
    return "\n".join(lines)

