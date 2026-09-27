# 🤖 AI Agent Pro for Home Assistant

סוכן AI אוטונומי ומאובטח ל-Home Assistant בעיצוב יוקרתי בסגנון **Apple**, התומך בכל ספקי ה-AI בעולם, מודלים עתידיים ומנגנון אישורים קפדני (Human-in-the-Loop).

---

## ✨ תכונות עיקריות

1. **עיצוב יוקרתי בסגנון Apple:**
   * מבוסס זכוכית מעורפלת (Frosted Glass), גווני Dark Mode עמוקים, טיפוגרפיית SF Pro ואנימציות מיקרו חלקות.
   * **5 מלבני בחירה עצמאיים ונקיים:**
     - **מלבן 1: בחירת סוכן** (דיאגנוסטיקה ותיקונים / אוטומציות / מנהל בית).
     - **מלבן 2: בחירת ספק** (OpenAI, Gemini, Anthropic Claude, DeepSeek, OpenRouter, Custom).
     - **מלבן 3: בחירת מודל פתוחה** (הדבקה חופשית של מודלים חדשים כמו `gpt-6-astra`).
     - **מלבן 4: בורר רמות חשיבה אוניברסלי** (`Off` עד `Max`) עם מנגנון ירידה חכם והתראה למשתמש.
     - **מלבן 5: בקרת אישורים ואבטחה** (שום שינוי בקוד לא מבוצע בלי קליק על `[אשר]`).

2. **מנגנון ירידה חכם ברמות חשיבה (Reasoning Fallback with Notice):**
   * בחרת רמה שהמודל אינו תומך בה? המערכת יורדת אוטומטית בסולם:
     $$\text{Max} \longrightarrow \text{XHigh} \longrightarrow \text{High} \longrightarrow \text{Medium} \longrightarrow \text{Low} \longrightarrow \text{Off}$$
   * המערכת מקפיצה התראה שקופה:  
     `ℹ️ התאמת רמת חשיבה: המודל אינו תומך ב-Max, הותאם אוטומטית ל-High`.

3. **שליטה ואישור בדפדפן ובטלפון:**
   * **בצ'אט בדפדפן:** כרטיס עם תצוגת קוד ה-YAML וכפתורי `[ ✅ אשר והטמע במערכת ]` ו-`[ ❌ דחה ובטל ]`.
   * **בהתראות המערכת:** התראת Persistent Notification עם כפתורי אישור.
   * **בנייד:** התראות פוש עם כפתורי Actionable.

---

## 🚀 הוראות התקנה ב-Home Assistant

### שלב 1: העתקת התיקייה ל-Home Assistant
העתק את תיקיית `custom_components/ai_agent` ישירות לתוך תיקיית הקונפיגורציה של ה-Home Assistant שלך:
```text
/config/custom_components/ai_agent/
```

### שלב 2: הפעלה מחדש (Restart)
היכנס להגדרות Home Assistant ובצע הפעלה מחדש לשרת (Developer Tools -> Restart).

### שלב 3: הוספת האינטגרציה
1. עבור אל **Settings (הגדרות) -> Devices & Services (מכשירים ושירותים)**.
2. לחץ על **+ Add Integration**.
3. חפש **AI Agent Pro**.
4. בחר את הספק, הזן את מפתח ה-API ואת רמת החשיבה הרצויה.

### שלב 4: הוספת הכרטיס למסך הבית (Lovelace Dashboard)
הוסף כרטיס ידני (Manual Card) עם ההגדרה הבאה:
```yaml
type: custom:ai-agent-card
```
או כפאנל מלא במסך נפרד.
