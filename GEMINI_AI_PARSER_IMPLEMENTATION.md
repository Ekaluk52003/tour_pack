# AI Email Parser — Gemini Migration + Guideline + "Remember" Instructions

> Companion to `AI_IMPLEMENTATION_EXPLAINED.md` (which describes the original
> two-step parsing logic). This file documents the **changes made on 2026-06-08**:
> switching the LLM from OpenAI to Google Gemini, adding a per-request guideline,
> and adding a database-backed "remember" learning loop with visible AI reasoning.

---

## 1. What changed at a glance

| Area | Before | After |
|------|--------|-------|
| LLM provider | OpenAI (`gpt-4o`) via `openai` SDK | Google Gemini (`gemini-3.5-flash`) via `google-genai` SDK |
| JSON output | Manually strip ```` ```json ```` fences | `response_mime_type="application/json"` (fence-strip kept as fallback) |
| Steering a parse | Email text only | Email **+ optional per-request guideline** (not saved) |
| Improving over time | Edit prompt in code | **Save "remember" instructions to DB**, injected into every future parse |
| Transparency | Reasons hidden in backend | **Per-item `match_reason` shown in the results panel** |

The two-step flow itself is unchanged: **Step 1** extracts basic info, **Step 2**
matches DB hotels/services. See `AI_IMPLEMENTATION_EXPLAINED.md` for that logic.

---

## 2. Data flow (updated)

```
Customer Email  +  Guideline (typed, optional)
        │
        ▼
parse_email_with_ai()                    ← reads {email_content, guideline}
        │
        ├─ analyze_email_step_by_step(email, guideline)        [STEP 1 → Gemini]
        │        prompt += _build_ai_guidance(guideline)
        │
        └─ match_extracted_data_with_models(analysis, guideline)
                 └─ analyze_hotels_and_services_step2(analysis, cities, guideline) [STEP 2 → Gemini]
                          prompt += _build_ai_guidance(guideline)
        │
        ▼
JSON response: { success, analysis, matched_data }
   matched_data.reasoning = { hotels:[…], services:[…] }   ← each with match_reason
        │
        ▼
Frontend: shows extracted info + AI reasoning
        │
        ├─ "Apply to Form"  → builds the tour days
        └─ "Remember for next time" → POST /save-ai-instruction/ → AIParserInstruction row
                                          (active rows injected into ALL future parses)
```

`_build_ai_guidance(guideline)` returns a text block combining:
1. the **per-request guideline** (highest priority, not persisted), and
2. **all active `AIParserInstruction` rows** ("standing instructions").

It is appended to *both* the Step 1 and Step 2 prompts. The base prompts stay
hardcoded so the JSON contract can't be broken by an edit.

---

## 3. Files changed

### Backend
| File | Change |
|------|--------|
| `requirements.txt` | **Removed `openai`**; added `google-genai>=0.3.0` |
| `tour/settings.py` | **Removed `OPENAI_*`**; added `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-3.5-flash`) |
| `.env` | **Removed `OPENAI_API_KEY` / `OPENAI_MODEL`**; `GEMINI_API_KEY` kept |
| `tours/ai_views.py` | **NEW module — all AI views live here**: helpers `_build_ai_guidance`, `_gemini_generate_json`; views `parse_email_with_ai`, `save_ai_instruction`; steps `analyze_email_step_by_step`, `analyze_hotels_and_services_step2`, `match_extracted_data_with_models` |
| `tours/views.py` | AI code **moved out** to `ai_views.py`; no AI logic remains |
| `tours/models.py` | Added `AIParserInstruction` model + `active_text()` classmethod |
| `tours/admin.py` | Registered `AIParserInstructionAdmin` (inline `is_active` toggle) |
| `tours/urls.py` | `import ai_views`; AI routes point to `ai_views.*` |
| `tours/migrations/0034_aiparserinstruction.py` | Generated migration |

### Frontend
| File | Change |
|------|--------|
| `tours/templates/tour_quote/tour_package_quote.html` | Guideline textarea; AI reasoning list; "Remember for next time" box |
| `static/tour_quote/js/tour_package.js` | New Alpine state; send `guideline`; `saveRememberInstruction()`; reset in `clearEmailContent` |
| `static/dist/bundle.js` | Rebuilt by webpack (generated — don't edit by hand) |

---

## 4. Key code

### Gemini call helper — `tours/ai_views.py`
```python
def _gemini_generate_json(prompt, system_instruction):
    from django.conf import settings
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            response_mime_type="application/json",   # ← clean JSON, no markdown fences
        ),
    )
    ai_response = (response.text or "").strip()
    # fence-strip fallback (defensive)
    if ai_response.startswith('```json'): ai_response = ai_response[7:]
    elif ai_response.startswith('```'):   ai_response = ai_response[3:]
    if ai_response.endswith('```'):       ai_response = ai_response[:-3]
    return ai_response.strip()
```

### Guidance builder — `tours/ai_views.py`
```python
def _build_ai_guidance(guideline=""):
    parts = []
    guideline = (guideline or "").strip()
    if guideline:
        parts.append(f"User guideline for THIS request (highest priority):\n{guideline}")
    saved = AIParserInstruction.active_text()
    if saved:
        parts.append("Standing instructions to ALWAYS follow (learned from past corrections):\n" + saved)
    if not parts:
        return ""
    return "\n\nADDITIONAL GUIDANCE:\n" + "\n\n".join(parts) + "\n"
```

### Persistent learnings model — `tours/models.py`
```python
class AIParserInstruction(models.Model):
    instruction = models.TextField(help_text="A learning/correction for the AI to remember on future parses.")
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    created_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def active_text(cls):
        items = cls.objects.filter(is_active=True).values_list('instruction', flat=True)
        return "\n".join(f"- {t}" for t in items)
```

### Save endpoint — `tours/ai_views.py`
`POST /save-ai-instruction/` (superuser only), body `{"instruction": "..."}`,
caps length at 1000 chars, creates an `AIParserInstruction` row with `created_by`.

### Frontend wiring — `static/tour_quote/js/tour_package.js`
- New Alpine state: `aiGuideline`, `rememberInstruction`, `isSavingInstruction`,
  `instructionSaved`, `instructionError`.
- `parseEmailWithAI()` sends `{ email_content, guideline }`.
- `saveRememberInstruction()` POSTs to `/save-ai-instruction/` with the CSRF header.
- Results panel iterates `aiMatchedData.reasoning.hotels` / `.services` to show
  each choice with its `match_reason`.

---

## 5. How to use it

1. Open a tour-quote create page as a **superuser** → **Open AI Parser**.
2. Paste the customer email; optionally type a **Guideline** (applies to this
   parse only, e.g. "luxury client — prefer 5-star hotels").
3. **Parse with AI** → review extracted info and the **🧠 AI Reasoning** list.
4. **Apply to Form** to build the itinerary.
5. If the AI chose poorly, type a correction in **💾 Remember for next time** and
   **Save**. It becomes a standing instruction applied to every future parse.
6. Manage standing instructions in Django admin → **AI Parser Instructions**
   (toggle `is_active` off to retire one without deleting it).

---

## 6. Configuration

`.env`:
```
GEMINI_API_KEY=...            # already set
GEMINI_MODEL=gemini-3.5-flash # optional override, e.g. gemini-2.5-flash / gemini-2.5-pro
AI_USE_CHAT_SESSION=false     # optional; true = experimental shared chat (see §9.6)
```

`settings.py`:
```python
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
```

---

## 7. Runtime / deployment notes (this project runs in Docker)

The DB host is the compose service `db`, so backend commands must run **inside the
web container**:
```bash
docker compose exec web python manage.py migrate
docker compose exec web pip install google-genai      # ephemeral; see below
docker compose exec webpack npm run build             # or rely on `npm run watch`
```
- `makemigrations` can run on the host (no DB needed); `migrate` cannot.
- The in-container `pip install` is **ephemeral** — to persist the new dependency,
  rebuild the image: `docker compose build web` (picks up `requirements.txt`).
- The template loads `static/dist/bundle.js`; editing `tour_package.js` has no
  effect until webpack rebuilds the bundle.

---

## 8. Behaviour & safety notes

- **Cost/limits unchanged in shape:** email capped at 2000 chars, guideline at
  1000, saved instruction at 1000. `temperature=0.2` for consistent extraction.
- **Failure handling:** if a Gemini call fails (bad model, network, quota), the
  step returns its minimal fallback dict with an `error` field — the endpoint does
  not 500. If `gemini-3.5-flash` is unavailable on the key, set
  `GEMINI_MODEL=gemini-2.5-flash`.
- **JSON contract protected:** base prompts are hardcoded; user/DB text is only
  *appended* under an "ADDITIONAL GUIDANCE" heading, so a bad instruction can
  mis-steer choices but cannot break JSON parsing.
- **Guideline is never stored.** Only explicit "remember" saves persist.

---

## 9. Round-2 improvements (implemented)

These were the "ideas to improve" — now built. Migration: `0035_aiparserinstruction_scope_aiparselog`.

### 9.1 Show which standing instructions were applied
`parse_email_with_ai` returns `applied_instructions` (union of active extraction +
matching instructions, de-duped by id) alongside the result. The dialog renders
them in a "📌 Standing instructions applied" panel so the user sees the active
"memory" that influenced the parse. Backend helper: `_applied_instructions()`.

### 9.2 Categorize instructions by step (scope)
`AIParserInstruction.scope` ∈ `both | extraction | matching`. `_build_ai_guidance`
now takes a `step` and injects only instructions for that step via
`AIParserInstruction.active_text(step)` (which uses `active_for(step)`). The
"Remember" box has a scope `<select>`; admin shows/edits `scope` inline.

### 9.3 Reviewable parse log
`AIParseLog` records each parse: email, guideline, model, analysis, a compact
`result_summary` (cities / hotels / services chosen), `applied_instruction_ids`,
`success`, `error`, and `from_cache`. Written best-effort by `_log_parse()` (never
fatal). Read-only in admin (add disabled, all fields readonly). Use it to mine
real cases for better standing instructions.

### 9.4 De-duplicate & cap standing instructions
- `active_for(step)` skips duplicate text (case-insensitive) and caps at
  `AIParserInstruction.MAX_ACTIVE` (25), newest first — bounds prompt/token growth.
- `save_ai_instruction` refuses to create a second active row with identical
  text + scope (returns the existing id with `duplicate: true`).

### 9.5 Cache repeated parses
Identical parses (same email + guideline + active-instruction ids + model) are
served from Django cache for `AI_PARSE_CACHE_TIMEOUT` (1h) instead of re-calling
Gemini. Cache hits set `from_cache: true` (shown as a "⚡ from cache" badge) and
are still logged. Key = SHA-256 of those inputs.

### 9.6 Chat session (experimental, default OFF)
A shared `client.chats` session for both steps was implemented (`_new_chat`,
`_chat_json`, `chat=` params on the step functions) so Step 2 could keep Step 1's
context. **Disabled by default** via `AI_USE_CHAT_SESSION` (env) because chat turns
returned less reliable per-step JSON (trailing "Extra data"); two single-shot calls
are the default path. JSON parsing is now tolerant of trailing data via
`_loads_json` (uses `JSONDecoder.raw_decode`) regardless of mode.
> ⚠️ If you enable the chat session, keep a reference to the `genai.Client` for the
> whole request — if it is garbage-collected the connection closes and
> `chat.send_message` fails with "client has been closed".

### 9.7 Input sanitization
Pasted email + guideline (and saved instructions) are normalized by
`_sanitize_text()` before validation, AI calls, and the cache key: CRLF→LF,
NBSP/zero-width stripped, per-line trim, runs of spaces/tabs collapsed, and 3+
blank lines reduced to one. This removes paste noise that bloated tokens and
caused whitespace-only cache misses (so "same email, different blank lines" now
hits the same cache entry).

### 9.8 Manage instructions from the frontend (superuser)
Beyond Django admin, the parser dialog now has a collapsible **"⚙️ Manage AI
Parser Instructions"** panel: list all instructions, edit text, change scope,
toggle `is_active`, and delete — each change hits a dedicated endpoint and applies
to future parses immediately. Endpoints (all `@login_required` + superuser):
`GET /ai-instructions/` (list), `POST /ai-instructions/update/`,
`POST /ai-instructions/delete/` (plus the existing `POST /save-ai-instruction/`
to create). JS: `loadAiInstructions` / `updateAiInstruction` / `deleteAiInstruction`;
the panel loads when the dialog opens. Combined with §9.1 (applied-instructions
panel), the user can now both *see which* instructions ran and *manage* them
without leaving the form.

## 10. Still open / next time
- **Scope instructions to pax type / city** (not just step).
- **Unit-test** `_build_ai_guidance`, `_applied_instructions`, `active_for`
  dedupe/cap, and `_loads_json` (no live API needed).
- **Prune old `AIParseLog` rows** on a schedule (django-crontab is already used).
- Revisit the chat session if a future Gemini model returns clean per-turn JSON.
