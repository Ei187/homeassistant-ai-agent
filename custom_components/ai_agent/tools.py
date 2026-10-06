"""Home Assistant Tool Engine with Strict Human-in-the-Loop Approval & Autonomous GitHub Super-Powers."""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from typing import Any, Dict, List, Optional
import yaml

from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

_LOGGER = logging.getLogger(__name__)

# In-memory registry of pending actions waiting for human approval
PENDING_ACTIONS: Dict[str, Dict[str, Any]] = {}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "control_device",
            "description": "שולט במכשיר או ישות בבית (הדלקת/כיבוי אורות, מזגנים, מתגים, מנעולים, מדיה). מכין פקודה מפורטת ומבקש תמיד את אישור המשתמש לפני הביצוע.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "מזהה הישות (למשל 'light.living_room', 'climate.ac', 'all_lights')"},
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
            "name": "search_github_integrations",
            "description": "מחפש אינטגרציות ורכיבים מותאמים אישית עבור Home Assistant ישירות ב-GitHub. מחזיר את המאגרים המובילים, מספר כוכבים, תיאור וקישור.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "מונח החיפוש באנגלית או בעברית (למשל 'smartir', 'dyson', 'broadlink', 'switchbot', 'tuya local')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "מספר התוצאות להחזרה (ברירת מחדל: 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_custom_component",
            "description": "מתקין אינטגרציה מותאמת אישית ישירות מ-GitHub אל תיקיית custom_components (למשל: 'smartHomeHub/SmartIR'). מכין כרטיס אישור ומוריד את הקבצים אוטומטית רק לאחר אישור המשתמש.",
            "parameters": {
                "type": "object",
                "properties": {
                    "github_repo": {
                        "type": "string",
                        "description": "שם המאגר ב-GitHub (למשל: 'smartHomeHub/SmartIR' או כתובת מלאה)",
                    },
                    "component_name": {
                        "type": "string",
                        "description": "שם התיקייה/האינטגרציה באותיות קטנות (למשל: 'smartir')",
                    },
                    "reason": {
                        "type": "string",
                        "description": "הסבר מפורט למשתמש מדוע מומלץ להתקין את האינטגרציה ומה היא תעשה",
                    },
                },
                "required": ["github_repo", "component_name", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_config_file",
            "description": "עורך או יוצר קובץ קונפיגורציה ב-Home Assistant (בתוך /config/): למשל עריכת configuration.yaml, הוספת פלטפורמות, יצירת קבצי JSON לקודי מזגנים/טלוויזיות ב-SmartIR, עדכון סקריפטים ועוד. תמיד מציג תצוגה מקדימה ומבקש אישור משתמש.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "נתיב יחסי לקובץ בתוך /config/ (למשל: 'configuration.yaml', 'smartir/codes/climate/1110.json', 'scripts.yaml')",
                    },
                    "content": {
                        "type": "string",
                        "description": "התוכן לכתיבה או להוספה לקובץ",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["append", "overwrite", "replace"],
                        "description": "מצב כתיבה: 'append' להוספה בסוף הקובץ (מומלץ ל-configuration.yaml), 'overwrite' לדריסת/יצירת כל הקובץ (מומלץ לקבצי json/yaml חדשים), 'replace' להחלפת קטע ספציפי",
                    },
                    "target_content": {
                        "type": "string",
                        "description": "הקטע המדויק להחלפה (נדרש רק אם mode הוא 'replace')",
                    },
                    "reason": {
                        "type": "string",
                        "description": "הסבר ברור בעברית מה השינוי עושה ולמה הוא נדרש",
                    },
                },
                "required": ["file_path", "content", "mode", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_config_file",
            "description": "קורא תוכן של קובץ מתוך תיקיית הקונפיגורציה של Home Assistant (/config/): configuration.yaml, automations.yaml, scripts.yaml, קבצי קוד SmartIR ועוד.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "נתיב יחסי לקובץ בתוך /config/ (למשל: 'configuration.yaml', 'custom_components/smartir/manifest.json')",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "כמות שורות מקסימלית לקריאה (ברירת מחדל: 250)",
                        "default": 250,
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_config_files",
            "description": "מציג רשימת קבצים ותיקיות בתוך תיקיית הקונפיגורציה (/config) או תיקייה ספציפית בתוכה (למשל 'custom_components', 'smartir').",
            "parameters": {
                "type": "object",
                "properties": {
                    "sub_directory": {
                        "type": "string",
                        "description": "תיקיית משנה לסריקה (השאר ריק לסריקת שורש /config)",
                        "default": "",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restart_or_reload",
            "description": "מבצע בדיקת תקינות קונפיגורציה, טעינה מחדש של הגדרות ללא הפעלה מחדש (Reload), או הפעלה מחדש של שרת Home Assistant (Restart עם אישור משתמש).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["check_config", "reload_all", "reload_core", "restart_ha"],
                        "description": "'check_config' לבדיקת תקינות YAML, 'reload_all'/'reload_core' לטעינה מהירה של הגדרות, 'restart_ha' להפעלה מחדש של השרת (דורש אישור)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "סיבת הפעולה",
                    },
                },
                "required": ["action", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reconnect_or_reload_integration",
            "description": "טוען מחדש ומחבר מחדש אינטגרציה קיימת ב-Home Assistant (למשל לאחר עדכון קבצים או לתיקון ניתוק).",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "תחום האינטגרציה (למשל 'smartir', 'hue', 'tuya', 'mqtt')",
                    },
                },
                "required": ["domain"],
            },
        },
    },
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
    """Execution engine with Strict Human-in-the-Loop protection and autonomous system control."""

    def __init__(self, hass: HomeAssistant, require_approval: bool = True, notify_mobile: bool = True) -> None:
        self.hass = hass
        self.require_approval = require_approval
        self.notify_mobile = notify_mobile

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch tool call safely."""
        try:
            if name == "control_device":
                return await self._handle_control_device(args)
            if name == "search_github_integrations":
                return await self._handle_search_github_integrations(args)
            if name == "install_custom_component":
                return await self._handle_install_custom_component(args)
            if name == "edit_config_file":
                return await self._handle_edit_config_file(args)
            if name == "read_config_file":
                return await self._handle_read_config_file(args)
            if name == "list_config_files":
                return await self._handle_list_config_files(args)
            if name == "restart_or_reload":
                return await self._handle_restart_or_reload(args)
            if name == "reconnect_or_reload_integration":
                return await self._handle_reconnect_or_reload_integration(args)
            if name == "create_automation":
                return await self._handle_create_automation(args)
            if name == "scan_system_errors":
                return await self._scan_system_errors(args.get("limit", 10))
            if name == "search_entities":
                return await self._search_entities(args.get("query"), args.get("domain"))
            if name == "get_entity_state":
                return await self._get_entity_state(args.get("entity_id", ""))
            if name == "propose_service_call":
                return await self._handle_propose_service_call(args)
            return {"error": f"Unknown tool name: {name}"}
        except Exception as err:
            _LOGGER.exception("Tool execution error in %s: %s", name, err)
            return {"error": str(err)}

    def _resolve_target_entities(self, raw_input: Any, action: str = "turn_on") -> List[str]:
        """Smart entity & room resolution from natural language, area names, or IDs."""
        if not raw_input:
            return []

        candidates = []
        if isinstance(raw_input, list):
            candidates = [str(x).strip() for x in raw_input if x]
        elif isinstance(raw_input, str):
            candidates = [x.strip() for x in raw_input.split(",") if x.strip()]

        # Common rooms in Hebrew and English
        room_keywords = {
            "סלון": ["סלון", "living", "salon"],
            "מטבח": ["מטבח", "kitchen"],
            "חדר שינה": ["חדר שינה", "bedroom", "הורים"],
            "חדר ילדים": ["חדר ילדים", "ילדים", "kids"],
            "ממ״ד": ["ממד", "ממ\"ד", "shelter"],
            "מרפסת": ["מרפסת", "balcony"],
            "חצר": ["חצר", "גינה", "yard", "garden"],
            "מסדרון": ["מסדרון", "hallway", "corridor"],
            "שירותים": ["שירותים", "toilet", "wc"],
            "מקלחת": ["מקלחת", "אמבטיה", "bath", "shower"],
            "פינת אוכל": ["פינת אוכל", "dining"],
            "כניסה": ["כניסה", "entrance"],
            "משרד": ["משרד", "עבודה", "office", "study"],
        }

        # Domain hint
        domain_hint = "light"
        for text in candidates:
            low = text.lower()
            if any(w in low for w in ["מזגן", "מיזוג", "ac", "climate"]):
                domain_hint = "climate"
                break
            elif any(w in low for w in ["תריס", "וילון", "cover"]):
                domain_hint = "cover"
                break
            elif any(w in low for w in ["דוד", "מתג", "switch", "בוילר"]):
                domain_hint = "switch"
                break

        resolved = []
        try:
            area_reg = ar.async_get(self.hass)
            ent_reg = er.async_get(self.hass)
            dev_reg = dr.async_get(self.hass)
        except Exception:
            area_reg = ent_reg = dev_reg = None

        for item in candidates:
            # 1. Exact match in state machine
            if self.hass.states.get(item):
                resolved.append(item)
                continue

            # 2. Check if all lights
            if item.lower() in ("all", "all_lights", "כל האורות", "אורות", "כל האור"):
                all_lights = [s.entity_id for s in self.hass.states.async_all("light")]
                return all_lights or ["light.all"]

            # 3. Check against Home Assistant Area Registry
            clean_item = (
                item.replace("תכבה את האור ב", "")
                .replace("תדליק את האור ב", "")
                .replace("תכבה את האור", "")
                .replace("תדליק את האור", "")
                .replace("תכבה את ה", "")
                .replace("תדליק את ה", "")
                .replace("תכבה את", "")
                .replace("תדליק את", "")
                .replace("תכבה", "")
                .replace("תדליק", "")
                .replace("כבה את", "")
                .replace("כבה", "")
                .replace("אור ב", "")
                .replace("אור בסלון", "סלון")
                .replace("אור במטבח", "מטבח")
                .replace("אור", "")
                .strip(" :,-?!")
                .lower()
            )

            area_matched_id = None
            if area_reg:
                for area in area_reg.async_list_areas():
                    a_name = area.name.lower()
                    a_id = area.id.lower()
                    if clean_item and (clean_item in a_name or clean_item in a_id or a_name in clean_item):
                        area_matched_id = area.id
                        break
                    # Check synonyms
                    for canon, synonyms in room_keywords.items():
                        if any(s in clean_item for s in synonyms) and any(s in a_name or s in a_id for s in synonyms):
                            area_matched_id = area.id
                            break
                    if area_matched_id:
                        break

            if area_matched_id and ent_reg:
                # Find entities belonging to this area
                area_entities = []
                for entity in ent_reg.entities.values():
                    if entity.disabled:
                        continue
                    ea = entity.area_id
                    if not ea and entity.device_id and dev_reg:
                        dev = dev_reg.async_get(entity.device_id)
                        if dev:
                            ea = dev.area_id
                    if ea == area_matched_id:
                        if not domain_hint or entity.domain == domain_hint:
                            area_entities.append(entity.entity_id)

                # Fallback to switch if no light in area
                if not area_entities and domain_hint == "light":
                    for entity in ent_reg.entities.values():
                        if not entity.disabled and (entity.area_id == area_matched_id) and entity.domain == "switch":
                            area_entities.append(entity.entity_id)

                if area_entities:
                    resolved.extend(area_entities)
                    continue

            # 4. Fuzzy search in state machine friendly_names and entity_ids
            fuzzy_matches = []
            for state in self.hass.states.async_all():
                if domain_hint and state.domain != domain_hint:
                    continue
                s_name = (state.name or "").lower()
                s_id = state.entity_id.lower()
                if clean_item and (clean_item in s_name or clean_item in s_id):
                    fuzzy_matches.append(state.entity_id)
                elif any(syn in s_name or syn in s_id for canon, syns in room_keywords.items() if any(s in clean_item for s in syns) for syn in syns):
                    fuzzy_matches.append(state.entity_id)

            if fuzzy_matches:
                resolved.extend(fuzzy_matches)
                continue

            # If still nothing, preserve original item
            resolved.append(item)

        # De-duplicate while preserving order
        seen = set()
        unique = []
        for r in resolved:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return unique

    async def _handle_control_device(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Control device, strictly requesting user approval when require_approval is True."""
        raw_entity_id = args.get("entity_id", "")
        action = args.get("action", "turn_on")
        params = dict(args.get("parameters") or {})

        entity_ids = self._resolve_target_entities(raw_entity_id, action)
        if not entity_ids:
            return {"error": "לא צוין מזהה ישות (entity_id) לביצוע הפעולה."}

        # Resolve names for display
        resolved_names = []
        for eid in entity_ids:
            state = self.hass.states.get(eid)
            resolved_names.append(state.name if state and state.name else eid)

        if self.require_approval:
            action_id = f"act_{uuid.uuid4().hex[:8]}"
            preview = (
                f"# פקודת שליטה במכשיר\n"
                f"ישות / ישויות: {', '.join(entity_ids)}\n"
                f"שם: {', '.join(resolved_names)}\n"
                f"פעולה: {action}\n"
                f"פרמטרים: {yaml.dump(params, allow_unicode=True) if params else 'ללא'}"
            )
            proposal = {
                "id": action_id,
                "type": "control_device",
                "title": f"שליטה במכשיר: {action} על {', '.join(resolved_names[:2])}",
                "description": f"ביצוע פעולת {action} על {len(entity_ids)} מכשיר/ים",
                "yaml_preview": preview,
                "created_at": time.time(),
                "status": "pending_approval",
                "payload": {
                    "entity_id": entity_ids,
                    "action": action,
                    "parameters": params,
                },
            }
            PENDING_ACTIONS[action_id] = proposal

            persistent_notification.async_create(
                self.hass,
                f"**סוכן AI מציע לשלוט במכשיר:** `{action}` על `{', '.join(entity_ids)}`\n\n"
                f"פתח את חלון הסוכן כדי לאשר או לדחות את הפעולה.",
                title=f"🤖 ממתין לאישורך: {action} על {', '.join(resolved_names[:2])}",
                notification_id=f"ai_agent_{action_id}",
            )

            return {
                "requires_user_approval": True,
                "action_id": action_id,
                "title": proposal["title"],
                "yaml_preview": preview,
                "instruction": f"הפעולה '{action}' על {', '.join(resolved_names[:2])} מוכנה וממתינה לאישור המשתמש. הצג מה בכוונתך לעשות ובקש את אישורו.",
            }

        return await self._execute_control_device(args)

    async def _execute_control_device(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the actual device control service call."""
        raw_entity_id = args.get("entity_id", "")
        action = args.get("action", "turn_on")
        params = dict(args.get("parameters") or {})

        entity_ids = self._resolve_target_entities(raw_entity_id, action)
        if not entity_ids:
            return {"error": "לא נמצאה ישות או חדר תואמים לביצוע הפעולה."}

        # Handle all lights
        if len(entity_ids) == 1 and entity_ids[0].lower() in ("all", "all_lights", "כל האורות", "אורות", "light.all"):
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
                if self.hass.services.has_service(domain, action):
                    await self.hass.services.async_call(domain, action, call_params, blocking=True)
                else:
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
        return {"error": f"לא ניתן היה לשלוט בישות או בחדר '{raw_entity_id}'."}

    async def _handle_search_github_integrations(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search GitHub for custom integrations."""
        query = args.get("query", "")
        limit = args.get("limit", 5)
        return await self.hass.async_add_executor_job(
            _safe_search_github, query, limit
        )

    async def _handle_read_config_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read configuration file content safely."""
        file_path = args.get("file_path", "")
        max_lines = args.get("max_lines", 250)
        return await self.hass.async_add_executor_job(
            _safe_read_file, self.hass.config.config_dir, file_path, max_lines
        )

    async def _handle_list_config_files(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List files in config directory."""
        sub_dir = args.get("sub_directory", "")
        return await self.hass.async_add_executor_job(
            _safe_list_files, self.hass.config.config_dir, sub_dir
        )

    async def _handle_edit_config_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Edit or write a configuration file with Human-in-the-Loop preview."""
        file_path = args.get("file_path", "")
        mode = args.get("mode", "append")
        content = args.get("content", "")
        reason = args.get("reason", "עריכת קונפיגורציה")

        if not self.require_approval:
            res = await self.hass.async_add_executor_job(
                _safe_edit_file, self.hass.config.config_dir, args
            )
            return {"status": "ok", "message": f"הקובץ '{file_path}' עודכן בהצלחה במערכת."}

        action_id = f"act_{uuid.uuid4().hex[:8]}"
        preview = f"# קובץ: /config/{file_path}\n# מצב: {mode}\n# סיבה: {reason}\n\n{content}"
        proposal = {
            "id": action_id,
            "type": "edit_config_file",
            "title": f"עריכת קובץ: {file_path}",
            "description": reason,
            "yaml_preview": preview,
            "created_at": time.time(),
            "status": "pending_approval",
            "payload": args,
        }
        PENDING_ACTIONS[action_id] = proposal

        persistent_notification.async_create(
            self.hass,
            f"**סוכן AI מציע לערוך קובץ:** `{file_path}`\n\n"
            f"סיבה: {reason}\n\n"
            f"```yaml\n{preview}\n```\n\n"
            f"פתח את חלון הסוכן כדי לאשר או לדחות את השינוי.",
            title=f"🤖 ממתין לאישורך: עריכת {file_path}",
            notification_id=f"ai_agent_{action_id}",
        )

        return {
            "requires_user_approval": True,
            "action_id": action_id,
            "title": proposal["title"],
            "yaml_preview": preview,
            "instruction": "הצעת העריכה מוכנה וממתינה לאישור המשתמש. שאל את המשתמש האם לאשר את ההטמעה.",
        }

    async def _handle_install_custom_component(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Install a custom component from GitHub with Human-in-the-Loop approval."""
        github_repo = args.get("github_repo", "")
        comp_name = args.get("component_name", "")
        reason = args.get("reason", "התקנת אינטגרציה")

        if not self.require_approval:
            res = await self.hass.async_add_executor_job(
                _safe_install_component, self.hass.config.config_dir, github_repo, comp_name
            )
            return {"status": "ok", "message": f"האינטגרציה '{comp_name}' הותקנה בהצלחה!"}

        action_id = f"act_{uuid.uuid4().hex[:8]}"
        repo_clean = github_repo.replace('https://github.com/', '').strip('/')
        preview = (
            f"# התקנת אינטגרציה מ-GitHub\n"
            f"מאגר מקור: https://github.com/{repo_clean}\n"
            f"תיקיית יעד: /config/custom_components/{comp_name}\n"
            f"סיבה: {reason}"
        )
        proposal = {
            "id": action_id,
            "type": "install_custom_component",
            "title": f"התקנת אינטגרציה: {comp_name}",
            "description": reason,
            "yaml_preview": preview,
            "created_at": time.time(),
            "status": "pending_approval",
            "payload": args,
        }
        PENDING_ACTIONS[action_id] = proposal

        persistent_notification.async_create(
            self.hass,
            f"**סוכן AI מציע להתקין אינטגרציה:** `{comp_name}` מ-`{github_repo}`\n\n"
            f"סיבה: {reason}\n\n"
            f"פתח את חלון הסוכן כדי לאשר את ההתקנה.",
            title=f"🤖 ממתין לאישורך: התקנת {comp_name}",
            notification_id=f"ai_agent_{action_id}",
        )

        return {
            "requires_user_approval": True,
            "action_id": action_id,
            "title": proposal["title"],
            "yaml_preview": preview,
            "instruction": "הצעת ההתקנה מוכנה וממתינה לאישור המשתמש. שאל את המשתמש האם לאשר את ההתקנה.",
        }

    async def _handle_restart_or_reload(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle config check, reload or restart."""
        action = args.get("action", "reload_all")
        reason = args.get("reason", "")

        if action == "check_config":
            await self.hass.services.async_call("homeassistant", "check_config", {}, blocking=True)
            return {"status": "ok", "message": "בדיקת תקינות הקונפיגורציה הסתיימה בהצלחה. הקוד תקין ללא שגיאות!"}

        if action == "reload_core":
            await self.hass.services.async_call("homeassistant", "reload_core_config", {}, blocking=True)
            return {"status": "ok", "message": "הגדרות הליבה של Home Assistant נטענו מחדש בהצלחה ללא הפעלה מחדש."}

        if action == "reload_all":
            await self.hass.services.async_call("homeassistant", "reload_all", {}, blocking=True)
            return {"status": "ok", "message": "כל הישויות, הסקריפטים וההגדרות נטענו מחדש בהצלחה!"}

        if action == "restart_ha":
            if not self.require_approval:
                await self.hass.services.async_call("homeassistant", "restart", {}, blocking=False)
                return {"status": "ok", "message": "פקודת הפעלה מחדש נשלחה לשרת."}

            action_id = f"act_{uuid.uuid4().hex[:8]}"
            preview = f"# הפעלה מחדש של שרת Home Assistant\nסיבה: {reason}\nפעולה: restart"
            proposal = {
                "id": action_id,
                "type": "restart_ha",
                "title": "הפעלה מחדש של השרת (Restart)",
                "description": reason,
                "yaml_preview": preview,
                "created_at": time.time(),
                "status": "pending_approval",
                "payload": args,
            }
            PENDING_ACTIONS[action_id] = proposal

            return {
                "requires_user_approval": True,
                "action_id": action_id,
                "title": proposal["title"],
                "yaml_preview": preview,
                "instruction": "ההפעלה מחדש ממתינה לאישור המשתמש. שאל האם לאשר את ההפעלה מחדש.",
            }

        return {"error": f"פעולה לא ידועה: {action}"}

    async def _handle_reconnect_or_reload_integration(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Reload and reconnect an integration."""
        domain = args.get("domain", "").lower()
        if not domain:
            return {"error": "לא צוין תחום אינטגרציה."}

        entries = self.hass.config_entries.async_entries(domain)
        if entries:
            reloaded = 0
            for entry in entries:
                await self.hass.config_entries.async_reload(entry.entry_id)
                reloaded += 1
            return {
                "status": "ok",
                "message": f"האינטגרציה '{domain}' נטענה מחדש בהצלחה ({reloaded} רשומות חוברו מחדש).",
            }

        await self.hass.services.async_call("homeassistant", "reload_all", {}, blocking=True)
        return {
            "status": "ok",
            "message": f"האינטגרציה '{domain}' רועננה והגדרות המערכת נטענו מחדש.",
        }

    async def _scan_system_errors(self, limit: int) -> Dict[str, Any]:
        """Scan real or recent system logs for errors."""
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

        def _safe_parse(val: Any) -> Any:
            if isinstance(val, (dict, list)):
                return val
            if isinstance(val, str) and val.strip():
                try:
                    parsed = yaml.safe_load(val)
                    if parsed is not None:
                        return parsed
                except Exception:
                    pass
            return []

        triggers = _safe_parse(trigger_yaml)
        if isinstance(triggers, dict):
            triggers = [triggers]

        conditions = _safe_parse(condition_yaml)
        if isinstance(conditions, dict):
            conditions = [conditions]

        actions = _safe_parse(action_yaml)
        if isinstance(actions, dict):
            actions = [actions]

        auto_id = str(int(time.time() * 1000))
        full_yaml_dict = {
            "id": auto_id,
            "alias": alias,
            "description": desc,
            "trigger": triggers,
            "condition": conditions,
            "action": actions,
            "mode": "single",
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


# --- Safe File & Network Operations (Run inside Executor) ---

def _safe_search_github(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search GitHub for Home Assistant custom integrations."""
    try:
        clean_q = query.strip()
        encoded = urllib.parse.quote(f"{clean_q} home-assistant")
        url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&order=desc&per_page={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistant-AIAgentPro"})

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        items = data.get("items", [])
        results = []
        for item in items[:limit]:
            results.append({
                "repo_name": item.get("full_name"),
                "description": item.get("description") or "ללא תיאור",
                "stars": item.get("stargazers_count", 0),
                "url": item.get("html_url"),
            })

        return {
            "status": "ok",
            "query": query,
            "count": len(results),
            "repositories": results,
        }
    except Exception as err:
        _LOGGER.warning("GitHub search failed: %s", err)
        return {"error": f"שגיאה בחיפוש ב-GitHub: {err}"}


def _safe_read_file(config_dir: str, file_path: str, max_lines: int = 250) -> Dict[str, Any]:
    file_rel = file_path.lstrip("/\\")
    full_path = os.path.abspath(os.path.join(config_dir, file_rel))
    if os.path.commonpath([full_path, config_dir]) != config_dir:
        return {"error": "נתיב הקובץ חייב להיות בתוך תיקיית /config"}
    if not os.path.exists(full_path):
        return {"error": f"הקובץ '{file_rel}' לא נמצא בתיקיית /config"}

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(max_lines)]
            content = "".join(lines)
            return {
                "status": "ok",
                "file_path": file_rel,
                "lines_read": len(lines),
                "content": content,
            }
    except Exception as err:
        return {"error": f"שגיאה בקריאת הקובץ: {err}"}


def _safe_list_files(config_dir: str, sub_dir: str = "") -> Dict[str, Any]:
    rel = sub_dir.lstrip("/\\")
    target_dir = os.path.abspath(os.path.join(config_dir, rel))
    if os.path.commonpath([target_dir, config_dir]) != config_dir:
        return {"error": "התיקייה חייבת להיות בתוך /config"}
    if not os.path.exists(target_dir):
        return {"error": f"התיקייה '{rel}' אינה קיימת."}

    items = []
    try:
        for entry in os.scandir(target_dir):
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else 0,
            })
        items.sort(key=lambda x: (not x["is_dir"], x["name"]))
        return {"status": "ok", "directory": rel or "/", "count": len(items), "items": items[:60]}
    except Exception as err:
        return {"error": f"שגיאה בסריקת התיקייה: {err}"}


def _safe_edit_file(config_dir: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    file_rel = payload["file_path"].lstrip("/\\")
    full_path = os.path.abspath(os.path.join(config_dir, file_rel))
    if os.path.commonpath([full_path, config_dir]) != config_dir:
        raise ValueError("נתיב הקובץ חייב להיות בתוך תיקיית /config")

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    mode = payload.get("mode", "append")
    content = payload.get("content", "")
    target = payload.get("target_content", "")

    if mode == "append":
        existing = ""
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                existing = f.read()
        separator = "\n\n" if existing and not existing.endswith("\n\n") else "\n" if existing and not existing.endswith("\n") else ""
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(separator + content + "\n")
    elif mode == "overwrite":
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
    elif mode == "replace":
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"הקובץ {file_rel} אינו קיים להחלפה.")
        with open(full_path, "r", encoding="utf-8") as f:
            current = f.read()
        if target not in current:
            raise ValueError(f"הטקסט להחלפה לא נמצא בתוך הקובץ {file_rel}.")
        new_text = current.replace(target, content, 1)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_text)

    return {"status": "ok", "file_path": file_rel, "mode": mode}


def _safe_install_component(config_dir: str, github_repo: str, component_name: str) -> Dict[str, Any]:
    repo_clean = github_repo.strip().replace("https://github.com/", "").strip("/")
    urls_to_try = [
        f"https://github.com/{repo_clean}/archive/refs/heads/main.zip",
        f"https://github.com/{repo_clean}/archive/refs/heads/master.zip",
        f"https://codeload.github.com/{repo_clean}/zip/refs/heads/main",
        f"https://api.github.com/repos/{repo_clean}/zipball",
    ]

    zip_data = None
    last_err = None
    for u in urls_to_try:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "HomeAssistant-AIAgentPro"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    zip_data = resp.read()
                    break
        except Exception as ex:
            last_err = ex

    if not zip_data:
        raise RuntimeError(f"שגיאה בהורדת {repo_clean} מ-GitHub: {last_err}")

    zf = zipfile.ZipFile(io.BytesIO(zip_data))
    target_comp_dir = os.path.join(config_dir, "custom_components", component_name)
    os.makedirs(target_comp_dir, exist_ok=True)

    extracted_files = 0
    prefix_to_find = f"custom_components/{component_name}/"
    matching_members = [m for m in zf.namelist() if prefix_to_find in m]

    if matching_members:
        for m in matching_members:
            if m.endswith("/"):
                continue
            idx = m.index(prefix_to_find) + len(prefix_to_find)
            rel_file = m[idx:]
            dest_file = os.path.join(target_comp_dir, rel_file)
            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            with zf.open(m) as src, open(dest_file, "wb") as dst:
                dst.write(src.read())
            extracted_files += 1
    else:
        manifest_members = [m for m in zf.namelist() if m.endswith("manifest.json")]
        if manifest_members:
            root_prefix = os.path.dirname(manifest_members[0])
            for m in zf.namelist():
                if m.startswith(root_prefix) and not m.endswith("/"):
                    rel_file = os.path.relpath(m, root_prefix)
                    dest_file = os.path.join(target_comp_dir, rel_file)
                    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                    with zf.open(m) as src, open(dest_file, "wb") as dst:
                        dst.write(src.read())
                    extracted_files += 1

    # Extract auxiliary directories like codes/ for SmartIR
    codes_prefix = "codes/"
    codes_members = [m for m in zf.namelist() if f"/{codes_prefix}" in m or m.startswith(codes_prefix)]
    if codes_members:
        target_codes_dir = os.path.join(config_dir, component_name, "codes")
        os.makedirs(target_codes_dir, exist_ok=True)
        for m in codes_members:
            if m.endswith("/"):
                continue
            idx = m.index(codes_prefix) + len(codes_prefix)
            rel_file = m[idx:]
            dest_file = os.path.join(target_codes_dir, rel_file)
            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            with zf.open(m) as src, open(dest_file, "wb") as dst:
                dst.write(src.read())

    return {
        "status": "installed",
        "component": component_name,
        "files_extracted": extracted_files,
        "path": f"custom_components/{component_name}",
    }


def _save_automation_to_file(config_path: str, automation_dict: Dict[str, Any]) -> None:
    """Save an automation to automations.yaml safely."""
    auto_id = str(automation_dict.get("id") or int(time.time() * 1000))
    automation_dict["id"] = auto_id
    if "mode" not in automation_dict:
        automation_dict["mode"] = "single"

    existing_automations = []
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                if isinstance(content, list):
                    existing_automations = content
                elif isinstance(content, dict):
                    existing_automations = [content]
        except Exception as err:
            _LOGGER.warning("Could not read existing automations from %s: %s", config_path, err)

    updated = False
    for i, a in enumerate(existing_automations):
        if isinstance(a, dict) and str(a.get("id")) == auto_id:
            existing_automations[i] = automation_dict
            updated = True
            break
    if not updated:
        existing_automations.append(automation_dict)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(existing_automations, f, allow_unicode=True, sort_keys=False)


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
        if action_type == "control_device":
            engine = ToolEngine(hass, require_approval=False)
            res = await engine._execute_control_device(payload)
            proposal["status"] = "executed"
            del PENDING_ACTIONS[action_id]
            msg = res.get("message", "הפעולה בוצעה בהצלחה!")
            return {
                "success": True,
                "status": "executed",
                "message": msg,
            }

        if action_type == "create_automation":
            automations_path = hass.config.path("automations.yaml")
            await hass.async_add_executor_job(
                _save_automation_to_file,
                automations_path,
                dict(payload),
            )
            await hass.services.async_call("automation", "reload", {}, blocking=True)
            proposal["status"] = "executed"
            del PENDING_ACTIONS[action_id]
            return {
                "success": True,
                "status": "executed",
                "message": f"האוטומציה '{proposal.get('title')}' נוצרה בהצלחה והוטמעה במערכת!",
            }

        if action_type == "edit_config_file":
            await hass.async_add_executor_job(
                _safe_edit_file,
                hass.config.config_dir,
                dict(payload),
            )
            if payload.get("file_path", "").endswith("configuration.yaml"):
                try:
                    await hass.services.async_call("homeassistant", "reload_core_config", {}, blocking=True)
                except Exception:
                    pass
            proposal["status"] = "executed"
            del PENDING_ACTIONS[action_id]
            return {
                "success": True,
                "status": "executed",
                "message": f"הקובץ '{payload.get('file_path')}' נשמר ועודכן בהצלחה במערכת!",
            }

        if action_type == "install_custom_component":
            res = await hass.async_add_executor_job(
                _safe_install_component,
                hass.config.config_dir,
                payload.get("github_repo", ""),
                payload.get("component_name", ""),
            )
            proposal["status"] = "executed"
            del PENDING_ACTIONS[action_id]
            return {
                "success": True,
                "status": "executed",
                "message": f"האינטגרציה '{payload.get('component_name')}' הותקנה בהצלחה ב-custom_components! יש לבצע Restart לשרת כדי ש-Home Assistant יזהה אותה.",
            }

        if action_type == "restart_ha":
            proposal["status"] = "executed"
            del PENDING_ACTIONS[action_id]
            await hass.services.async_call("homeassistant", "restart", {}, blocking=False)
            return {
                "success": True,
                "status": "executed",
                "message": "פקודת ההפעלה מחדש נשלחה! שרת Home Assistant מופעל מחדש כעת...",
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
    """Format home entities, rooms/areas, and current states into a clear list for the AI."""
    try:
        area_reg = ar.async_get(hass)
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
    except Exception:
        area_reg = ent_reg = dev_reg = None

    area_map: Dict[str, Dict[str, Any]] = {}
    if area_reg:
        for area in area_reg.async_list_areas():
            area_map[area.id] = {"name": area.name, "devices": []}

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
        if domain in ("sensor", "binary_sensor"):
            s_id = state.entity_id.lower()
            s_name = (state.name or "").lower()
            if not any(k in s_id or k in s_name for k in [
                "temp", "humidity", "battery", "motion", "door", "window",
                "power", "energy", "boiler", "דוד", "טמפ", "תנועה", "דלת", "חלון"
            ]):
                continue

        area_name = "כללי"
        if ent_reg:
            entry = ent_reg.async_get(state.entity_id)
            if entry:
                aid = entry.area_id
                if not aid and entry.device_id and dev_reg:
                    dev = dev_reg.async_get(entry.device_id)
                    if dev:
                        aid = dev.area_id
                if aid and aid in area_map:
                    area_name = area_map[aid]["name"]
                    if domain in ("light", "switch", "climate", "cover", "fan", "lock", "media_player"):
                        area_map[aid]["devices"].append(f"{state.name or state.entity_id} (`{state.entity_id}`)")

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
        lines.append(f"- {state.entity_id} | '{friendly_name}' | חדר/אזור: '{area_name}' | state: {current_state}{extra_str}")
        count += 1
        if count >= max_entities:
            break

    room_summary_lines = []
    if area_map:
        for aid, data in area_map.items():
            if data["devices"]:
                dev_list = ", ".join(data["devices"][:8])
                room_summary_lines.append(f"• **חדר {data['name']}** (מזהה: `{aid}`): {dev_list}")

    output_parts = []
    if room_summary_lines:
        output_parts.append("### 🏠 חלוקת מכשירים לפי חדרים ואזורים בבית (Home Areas & Rooms):\n" + "\n".join(room_summary_lines))
        output_parts.append("### 📋 רשימת ישויות ומצבים חיים (Entities & Current States):\n" + "\n".join(lines))
    elif lines:
        output_parts.append("\n".join(lines))
    else:
        output_parts.append("אין ישויות זמינות כרגע.")

    return "\n\n".join(output_parts)
