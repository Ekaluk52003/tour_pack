# tours/ai_views.py
"""AI email parser views (Google Gemini).

Two-step flow: STEP 1 extracts basic info from a customer email, STEP 2 matches
available DB hotels/services. Supports a per-request guideline and persistent
"remember" instructions (AIParserInstruction). See GEMINI_AI_PARSER_IMPLEMENTATION.md.
"""

import json
import re
import hashlib
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse

from .models import (
    City, Hotel, Service, TourPackType, ServicePrice,
    AIParserInstruction, AIParseLog,
)

# How long an identical parse (same email + guideline + active instructions +
# model) is served from cache instead of re-calling Gemini.
AI_PARSE_CACHE_TIMEOUT = 60 * 60  # 1 hour


def _sanitize_text(text):
    """Normalize pasted email/guideline text: unify line endings, drop odd
    unicode spaces, trim each line, collapse runs of spaces/tabs and 3+ blank
    lines. Keeps paragraph breaks but removes the noise that bloats tokens and
    causes whitespace-only cache misses."""
    if not text:
        return ""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\xa0', ' ').replace('​', '')
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in text.split('\n')]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _build_ai_guidance(guideline, step):
    """Assemble the prompt block appended to an AI step, combining the per-request
    guideline (typed in the dialog, not persisted) with the active saved
    'remember' instructions scoped to this `step` ('extraction' or 'matching')."""
    parts = []
    guideline = (guideline or "").strip()
    if guideline:
        parts.append(f"User guideline for THIS request (highest priority):\n{guideline}")
    saved = AIParserInstruction.active_text(step)
    if saved:
        parts.append(
            "Standing instructions to ALWAYS follow (learned from past corrections):\n"
            f"{saved}"
        )
    if not parts:
        return ""
    return "\n\nADDITIONAL GUIDANCE:\n" + "\n\n".join(parts) + "\n"


def _extract_json(text):
    """Strip optional ```json fences and whitespace from a model response."""
    text = (text or "").strip()
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    return text.strip()


def _loads_json(text):
    """Parse JSON, tolerating trailing content after the first value (which can
    happen in chat mode). Falls back to decoding just the first JSON object."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        obj, _ = json.JSONDecoder().raw_decode(text.lstrip())
        return obj


def _get_gemini_client():
    from google import genai
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _new_chat(client):
    """Create a single chat session shared across both steps, so Step 2 retains
    the context of Step 1's extraction (multi-turn refinement instead of two
    independent calls). Returns None on failure so callers fall back to
    single-shot generate_content."""
    from google.genai import types
    try:
        return client.chats.create(
            model=settings.GEMINI_MODEL,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                system_instruction=(
                    "You are a Thailand tour specialist. First extract facts from a "
                    "customer email, then match hotels/services from the provided "
                    "options. Always respond with valid JSON only."
                ),
            ),
        )
    except Exception as e:
        print(f"Gemini chat init failed, falling back to single-shot: {e}")
        return None


def _chat_json(chat, prompt):
    """Send a turn in a shared chat and return cleaned JSON text."""
    response = chat.send_message(prompt)
    return _extract_json(response.text or "")


def _gemini_generate_json(prompt, system_instruction):
    """Single-shot Gemini call returning cleaned JSON text.
    Raises on API error so callers can fall back to their error structure."""
    from google.genai import types

    client = _get_gemini_client()
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    return _extract_json(response.text or "")


def _step_json(prompt, system_instruction, chat=None):
    """Run one AI step either as a turn in the shared `chat` or, if no chat is
    available, as an independent single-shot call."""
    if chat is not None:
        return _chat_json(chat, prompt)
    return _gemini_generate_json(prompt, system_instruction)


def _applied_instructions():
    """Active instructions that will influence a parse (union of both steps),
    de-duplicated by id. Returns (list_of_dicts, sorted_ids)."""
    merged = {}
    for step in (AIParserInstruction.SCOPE_EXTRACTION, AIParserInstruction.SCOPE_MATCHING):
        for obj in AIParserInstruction.active_for(step):
            merged[obj.id] = obj
    items = [
        {'id': o.id, 'scope': o.scope, 'instruction': o.instruction}
        for o in merged.values()
    ]
    return items, sorted(merged.keys())


def _result_summary(matched_data):
    """Compact, log-friendly summary of what the parse produced."""
    reasoning = matched_data.get('reasoning', {}) or {}
    return {
        'cities': [c.get('name') for c in matched_data.get('cities', [])],
        'tour_pack_type': (matched_data.get('tour_pack_type') or {}).get('name'),
        'hotels': [
            {'city': h.get('city'), 'hotel': h.get('hotel_name')}
            for h in reasoning.get('hotels', [])
        ],
        'services': [
            {'city': s.get('city'), 'service': s.get('service_name')}
            for s in reasoning.get('services', [])
        ],
        'package_name': matched_data.get('package_name_suggestion'),
    }


def _log_parse(request, email_content, guideline, payload, applied_ids, from_cache=False):
    """Persist a reviewable record of the parse (best-effort; never fatal)."""
    try:
        analysis = payload.get('analysis') or {}
        AIParseLog.objects.create(
            email_content=email_content,
            guideline=guideline or "",
            model_used=settings.GEMINI_MODEL,
            analysis=analysis,
            result_summary=_result_summary(payload.get('matched_data') or {}),
            applied_instruction_ids=applied_ids,
            success=payload.get('success', True),
            error=analysis.get('error', '') or '',
            from_cache=from_cache,
            created_by=request.user if request.user.is_authenticated else None,
        )
    except Exception as e:
        print(f"AIParseLog save failed: {e}")


@login_required
def parse_email_with_ai(request):
    """
    Parse customer email using AI to extract tour information.
    Only accessible by superusers or users in 'assistance' group.
    """
    # Check if user is superuser
    can_use_ai = request.user.is_superuser
    if not can_use_ai:
        return JsonResponse({'error': 'Permission denied. Only authorized users can use AI email parsing.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        email_content = _sanitize_text(data.get('email_content', ''))
        guideline = _sanitize_text(data.get('guideline', ''))

        if not email_content:
            return JsonResponse({'error': 'Email content is required'}, status=400)

        # Limit email content to prevent token bloat (2000 chars ≈ 500 tokens)
        MAX_EMAIL_LENGTH = 2000
        if len(email_content) > MAX_EMAIL_LENGTH:
            return JsonResponse({
                'error': f'Email content too long. Maximum {MAX_EMAIL_LENGTH} characters allowed (current: {len(email_content)})'
            }, status=400)

        # Limit the per-request guideline as well
        MAX_GUIDELINE_LENGTH = 1000
        if len(guideline) > MAX_GUIDELINE_LENGTH:
            return JsonResponse({
                'error': f'Guideline too long. Maximum {MAX_GUIDELINE_LENGTH} characters allowed (current: {len(guideline)})'
            }, status=400)

        # Which standing instructions will influence this parse (for response,
        # logging, and the cache key).
        applied_list, applied_ids = _applied_instructions()

        # Serve identical repeated parses from cache instead of re-calling Gemini.
        raw_key = f"{settings.GEMINI_MODEL}|{email_content}|{guideline}|{','.join(map(str, applied_ids))}"
        cache_key = "ai_parse:" + hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
        cached = cache.get(cache_key)
        if cached:
            payload = dict(cached)
            payload['from_cache'] = True
            _log_parse(request, email_content, guideline, payload, applied_ids, from_cache=True)
            return JsonResponse(payload)

        # Optional shared chat session so Step 2 keeps Step 1's context. Disabled
        # by default (AI_USE_CHAT_SESSION) because chat turns proved less reliable
        # at returning clean per-step JSON; two single-shot calls are the default.
        # NOTE: keep `client` referenced for the whole request — if it is GC'd the
        # underlying connection closes and chat.send_message fails.
        client = chat = None
        if getattr(settings, 'AI_USE_CHAT_SESSION', False):
            client = _get_gemini_client()
            chat = _new_chat(client)

        # Step 1: extract basic info
        analysis_result = analyze_email_step_by_step(email_content, guideline, chat=chat)

        # Step 2 + DB matching
        matched_data = match_extracted_data_with_models(analysis_result, guideline, chat=chat)

        payload = {
            'success': True,
            'analysis': analysis_result,
            'matched_data': matched_data,
            'applied_instructions': applied_list,
            'from_cache': False,
        }

        cache.set(cache_key, payload, AI_PARSE_CACHE_TIMEOUT)
        _log_parse(request, email_content, guideline, payload, applied_ids, from_cache=False)

        return JsonResponse(payload)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error processing email: {str(e)}'}, status=500)


@login_required
def save_ai_instruction(request):
    """Save a persistent 'remember' instruction for the AI email parser.
    The user reviews the AI's reasoning, then teaches it what to do better
    next time. Superuser only, POST with JSON {"instruction": "...", "scope": "..."}.
    Scope is one of both|extraction|matching (default both). Identical active
    instructions with the same scope are de-duplicated."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        instruction = _sanitize_text(data.get('instruction', ''))

        if not instruction:
            return JsonResponse({'error': 'Instruction text is required'}, status=400)

        MAX_INSTRUCTION_LENGTH = 1000
        if len(instruction) > MAX_INSTRUCTION_LENGTH:
            return JsonResponse({
                'error': f'Instruction too long. Maximum {MAX_INSTRUCTION_LENGTH} characters allowed (current: {len(instruction)})'
            }, status=400)

        scope = (data.get('scope') or AIParserInstruction.SCOPE_BOTH).strip()
        valid_scopes = {c[0] for c in AIParserInstruction.SCOPE_CHOICES}
        if scope not in valid_scopes:
            scope = AIParserInstruction.SCOPE_BOTH

        # De-duplicate: don't create a second active row with identical text+scope.
        existing = AIParserInstruction.objects.filter(
            is_active=True, scope=scope, instruction__iexact=instruction
        ).first()
        if existing:
            return JsonResponse({'success': True, 'id': existing.id, 'duplicate': True})

        obj = AIParserInstruction.objects.create(
            instruction=instruction,
            scope=scope,
            created_by=request.user
        )
        return JsonResponse({'success': True, 'id': obj.id})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error saving instruction: {str(e)}'}, status=500)


def _instruction_dict(obj):
    return {
        'id': obj.id,
        'instruction': obj.instruction,
        'scope': obj.scope,
        'is_active': obj.is_active,
        'created_at': obj.created_at.strftime('%Y-%m-%d %H:%M'),
        'created_by': obj.created_by.username if obj.created_by else None,
    }


@login_required
def list_ai_instructions(request):
    """List all standing instructions for the frontend manager (superuser)."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied.'}, status=403)
    items = [_instruction_dict(o) for o in AIParserInstruction.objects.all()]
    return JsonResponse({'success': True, 'instructions': items})


@login_required
def update_ai_instruction(request):
    """Edit an instruction's text / scope / active flag (superuser, POST).
    Body: {"id": N, "instruction"?: "...", "scope"?: "...", "is_active"?: bool}."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        obj = AIParserInstruction.objects.filter(id=data.get('id')).first()
        if not obj:
            return JsonResponse({'error': 'Instruction not found'}, status=404)

        if 'instruction' in data:
            text = _sanitize_text(data.get('instruction', ''))
            if not text:
                return JsonResponse({'error': 'Instruction text is required'}, status=400)
            if len(text) > 1000:
                return JsonResponse({'error': 'Instruction too long (max 1000 characters)'}, status=400)
            obj.instruction = text

        if 'scope' in data:
            scope = (data.get('scope') or '').strip()
            valid_scopes = {c[0] for c in AIParserInstruction.SCOPE_CHOICES}
            if scope not in valid_scopes:
                return JsonResponse({'error': 'Invalid scope'}, status=400)
            obj.scope = scope

        if 'is_active' in data:
            obj.is_active = bool(data.get('is_active'))

        obj.save()
        return JsonResponse({'success': True, 'instruction': _instruction_dict(obj)})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error updating instruction: {str(e)}'}, status=500)


@login_required
def delete_ai_instruction(request):
    """Delete a standing instruction (superuser, POST {"id": N})."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        deleted, _ = AIParserInstruction.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'success': True, 'deleted': deleted})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error deleting instruction: {str(e)}'}, status=500)


@login_required
def suggest_instruction_from_feedback(request):
    """Owner feedback loop: turn a concrete per-item correction (the owner says a
    specific AI hotel/service pick was wrong and what it should have been) into a
    GENERAL standing rule, using Gemini to rephrase. Returns a DRAFT only — the
    owner reviews it and persists it via `save_ai_instruction`. Superuser, POST.

    Body: {item_type: "hotel"|"service", city, original_name, original_reason,
           correction, context: {destinations, raw_hotel_mentions,
           raw_activity_mentions, number_of_people}}."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)

        correction = _sanitize_text(data.get('correction', ''))
        if not correction:
            return JsonResponse({'error': 'Correction text is required'}, status=400)

        MAX_CORRECTION_LENGTH = 1000
        if len(correction) > MAX_CORRECTION_LENGTH:
            return JsonResponse({
                'error': f'Correction too long. Maximum {MAX_CORRECTION_LENGTH} characters allowed (current: {len(correction)})'
            }, status=400)

        # Context about the AI's choice the owner is correcting.
        item_type = (data.get('item_type') or '').strip().lower()
        if item_type not in ('hotel', 'service'):
            item_type = 'item'
        city = _sanitize_text(str(data.get('city', '')))[:100]
        original_name = _sanitize_text(str(data.get('original_name', '')))[:200]
        original_reason = _sanitize_text(str(data.get('original_reason', '')))[:500]

        context = data.get('context') or {}
        destinations = ', '.join(str(d) for d in (context.get('destinations') or []))[:300]
        raw_hotel = _sanitize_text(str(context.get('raw_hotel_mentions', '')))[:500]
        raw_activity = _sanitize_text(str(context.get('raw_activity_mentions', '')))[:500]
        num_people = context.get('number_of_people')

        # Hotel/service corrections are Step 2 (matching) by default.
        default_scope = AIParserInstruction.SCOPE_MATCHING

        prompt = f"""You help a Thailand tour-quote AI learn from a tour expert's correction.

The AI picked a {item_type} for a customer quote and the expert says it was wrong.

Context of the quote:
- Cities in the trip: {destinations or 'not specified'}
- Number of travelers: {num_people if num_people is not None else 'not specified'}
- Hotels the customer mentioned: {raw_hotel or 'none'}
- Activities/interests the customer mentioned: {raw_activity or 'none'}

The AI's choice being corrected:
- City: {city or 'not specified'}
- {item_type.capitalize()} chosen: {original_name or 'not specified'}
- AI's stated reason: {original_reason or 'not specified'}

The expert's correction:
"{correction}"

Convert this one-off correction into a SINGLE, GENERAL standing rule the AI should
follow on ALL future quotes (not just this customer). Requirements:
- Generalize: state the principle, not this specific booking. Do NOT mention the
  individual customer. You MAY reference a city or trip pattern if the rule is
  genuinely city-specific (e.g. "In Phuket, ...").
- Keep it to one or two concise sentences (max ~200 characters).
- Make it actionable and unambiguous for the AI's hotel/service matching.

Also choose the scope this rule applies to:
- "matching" = choosing hotels/services from available options (most corrections)
- "extraction" = reading facts from the email (people count, cities, dates, days)
- "both" = applies to both steps

Respond with JSON only:
{{"instruction": "<the general rule>", "scope": "matching|extraction|both"}}
"""

        ai_response = _gemini_generate_json(
            prompt,
            system_instruction=(
                "You convert a tour expert's one-off correction into a concise, "
                "general standing rule for an AI tour-quote assistant. Always "
                "respond with valid JSON."
            ),
        )
        result = _loads_json(ai_response)

        instruction = _sanitize_text(str(result.get('instruction', '')))[:1000]
        if not instruction:
            return JsonResponse({
                'success': False,
                'error': 'Could not draft a rule from this correction. Please rephrase it.'
            })

        scope = (result.get('scope') or default_scope).strip()
        valid_scopes = {c[0] for c in AIParserInstruction.SCOPE_CHOICES}
        if scope not in valid_scopes:
            scope = default_scope

        return JsonResponse({
            'success': True,
            'suggested_instruction': instruction,
            'scope': scope,
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        # Mirror the step functions' non-fatal pattern so the dialog never 500s.
        print(f"suggest_instruction_from_feedback error: {e}")
        return JsonResponse({'success': False, 'error': f'Error drafting rule: {str(e)}'})


def analyze_email_step_by_step(email_content, guideline="", chat=None):
    """
    STEP 1: Extract basic information from email (cities, people, duration).
    """
    from django.conf import settings
    from datetime import datetime
    import json

    # Get available cities from database for context
    available_cities = list(City.objects.values_list('name', flat=True))


    # Get current date for context
    from datetime import datetime as dt
    current_date = dt.now()
    current_date_str = current_date.strftime('%B %d, %Y')  # e.g., "October 04, 2025"
    current_month = current_date.month
    current_year = current_date.year

    # STEP 1 PROMPT: Extract basic info only
    prompt = f"""
You are a Thailand tour specialist analyzing customer emails to extract tour information.
**CURRENT DATE: {current_date_str}** (Month: {current_month}, Year: {current_year})
Available Thailand cities in our system: {', '.join(available_cities)}

Customer Email:
{email_content}

Extract ONLY the following BASIC information as JSON:
{{
    "customer_name": "customer name if mentioned (e.g., from signature, 'My name is...', 'I am...')",
    "number_of_people": "number of travelers - extract NUMBER (1 for solo/'I', 2 for couple/'we', 4 for family, etc.)",
    "destinations": ["cities mentioned"],
    "days_per_city": {{
        "Bangkok": 2,
        "Chiang Mai": 5,
        "Phuket": 7
    }},
    "travel_months": ["months mentioned like December, January, February"],
    "travel_start_date": "specific start date if mentioned (format: YYYY-MM-DD). See YEAR LOGIC rule below for choosing the year",
    "travel_timing": "time of month if mentioned: 'early', 'mid', 'end', 'late', 'beginning' (e.g., 'end of November' → 'end')",
    "duration_days": "total trip duration in days (e.g., 7 for 1 week, 14 for 2 weeks, 2 for 2 days)",
    "raw_hotel_mentions": "any hotel names or brands mentioned in the email (exact text)",
    "raw_activity_mentions": "any activities or interests mentioned (exact text)"
}}

IMPORTANT RULES:
1. **NUMBER OF PEOPLE**:
   - "I" or "alone" = 1 person
   - "we" or "couple" or "my wife and I" = 2 people
   - "family" = 4 people (default)
   - ALWAYS extract a number, never leave as None
2. For destinations: ONLY use cities from the available cities list
3. If a city is not in the list, find the closest match
4. **YEAR LOGIC**:
   - Current date is {current_date_str}
   - If travel month is AFTER current month ({current_month}) → use {current_year}
   - If travel month is BEFORE or EQUAL to current month → use {current_year + 1}
   - Example: Today is Oct (month 10). "Dec" (month 12) → {current_year}, "Sep" (month 9) → {current_year + 1}
5. For raw_hotel_mentions and raw_activity_mentions: Extract the EXACT text from the email, don't interpret or modify
6. **DAYS PER CITY & DURATION**:
   - If customer specifies days per city (e.g., "7 days in Phuket and 2 nights in Bangkok"), extract those exact numbers
   - Pay attention to phrases like "stay for X days", "spend X nights", "X days in [city]"
   - Convert weeks to days (1 week = 7 days, 2 weeks = 14 days)
7. **CITY ORDER**:
   - If customer specifies order (e.g., "start in Bangkok, then Chiang Mai, end in Phuket"), follow their order.
   - Apply the "city routing" standing instruction in ADDITIONAL GUIDANCE below if one is provided;
"""

    # Append per-request guideline + saved "remember" instructions (extraction scope)
    prompt += _build_ai_guidance(guideline, AIParserInstruction.SCOPE_EXTRACTION)

    try:
        # Call Gemini (shared chat turn, or single-shot fallback)
        ai_response = _step_json(
            prompt,
            system_instruction="You are a Thailand tour specialist. Extract only factual information from emails. Always respond with valid JSON.",
            chat=chat,
        )

        analysis = _loads_json(ai_response)

        # Log the STEP 1 extraction for debugging
        print("=" * 50)
        print("STEP 1 - BASIC EXTRACTION:")
        print(f"Customer name: {analysis.get('customer_name')}")
        print(f"Number of people: {analysis.get('number_of_people')}")
        print(f"Destinations: {analysis.get('destinations')}")
        print(f"Duration: {analysis.get('duration_days')}")
        print(f"Days per city: {analysis.get('days_per_city')}")
        print(f"Raw hotel mentions: {analysis.get('raw_hotel_mentions')}")
        print(f"Raw activity mentions: {analysis.get('raw_activity_mentions')}")
        print("=" * 50)

        # Ensure required fields exist
        if 'customer_name' not in analysis:
            analysis['customer_name'] = ''
        if 'number_of_people' not in analysis:
            analysis['number_of_people'] = None
        if 'destinations' not in analysis:
            analysis['destinations'] = []
        if 'days_per_city' not in analysis:
            analysis['days_per_city'] = {}
        if 'travel_months' not in analysis:
            analysis['travel_months'] = []
        if 'travel_start_date' not in analysis:
            analysis['travel_start_date'] = None
        if 'travel_timing' not in analysis:
            analysis['travel_timing'] = ''
        if 'duration_days' not in analysis:
            analysis['duration_days'] = None
        if 'raw_hotel_mentions' not in analysis:
            analysis['raw_hotel_mentions'] = ''
        if 'raw_activity_mentions' not in analysis:
            analysis['raw_activity_mentions'] = ''

        return analysis

    except Exception as e:
        print(f"Gemini API error in Step 1: {str(e)}")
        # Return minimal structure on error
        return {
            'customer_name': '',
            'number_of_people': None,
            'destinations': [],
            'days_per_city': {},
            'travel_months': [],
            'travel_start_date': None,
            'travel_timing': '',
            'duration_days': None,
            'raw_hotel_mentions': '',
            'raw_activity_mentions': '',
            'error': str(e)
        }

def analyze_hotels_and_services_step2(basic_analysis, cities, guideline="", chat=None):
    """
    STEP 2: With selected cities, get available hotels and services from DB,
    then ask AI to match with customer requirements.
    """
    from django.conf import settings
    import json

    # Get tour pack type for pricing
    num_people = basic_analysis.get('number_of_people')
    tour_pack_type = None
    if num_people:
        pax_name = f"{num_people}pax"
        tour_pack_type = TourPackType.objects.filter(name__iexact=pax_name).first()

        print(f"Looking for tour pack type: {pax_name}, Found: {tour_pack_type.name if tour_pack_type else 'NOT FOUND'}")

    # Collect available hotels and services for each city
    city_options = []
    for city_data in cities:
        city_id = city_data['id']
        city_name = city_data['name']

        # Get hotels for this city
        hotels = Hotel.objects.filter(city_id=city_id)
        hotel_list = [{'id': h.id, 'name': h.name} for h in hotels]

        # Get services for this city. Exclude transfer-type services: transfers
        # (arrival/departure/inter-city) are added deterministically in Python
        # below, never by the AI, so sending them here only bloats the prompt
        # (~42% of all services) and risks the AI picking a transfer as a daily
        # activity. Also no need to send price — the AI doesn't use it for
        # matching, and the real price is re-fetched per selection later.
        services = (
            Service.objects
            .filter(cities__id=city_id)
            .exclude(service_type__name__icontains='transfer')
            .select_related('service_type')
        )
        print(f"Services for {city_name} (before price filter): {services.count()}")

        if tour_pack_type:
            services = services.filter(prices__tour_pack_type=tour_pack_type).distinct()
            print(f"Services for {city_name} (after {tour_pack_type.name} price filter): {services.count()}")

        service_list = [
            {'id': s.id, 'name': s.name, 'type': s.service_type.name}
            for s in services
        ]

        city_options.append({
            'city': city_name,
            'hotels': hotel_list,
            'services': service_list
        })

    # Debug: Log what we're sending to AI
    print("=" * 50)
    print("STEP 2 - CONTEXT FOR AI:")
    print(f"Customer hotel mentions: {basic_analysis.get('raw_hotel_mentions', 'Not specified')}")
    print(f"Customer activity mentions: {basic_analysis.get('raw_activity_mentions', 'Not specified')}")
    for city_opt in city_options:
        print(f"\nCity: {city_opt['city']}")
        print(f"  Hotels available: {len(city_opt['hotels'])}")
        print(f"  Services available: {len(city_opt['services'])}")
        if city_opt['services']:
            print(f"  Sample services: {[s['name'] for s in city_opt['services'][:3]]}")
    print("=" * 50)

    # STEP 2 PROMPT: Match with available options
    prompt = f"""
You are a Thailand tour specialist. Based on customer requirements, select the best matching hotels and services from available options.

Customer mentioned:
- Hotels: {basic_analysis.get('raw_hotel_mentions', 'Not specified')}
- Activities/Interests: {basic_analysis.get('raw_activity_mentions', 'Not specified')}

Available options by city:
{json.dumps(city_options, separators=(',', ':'))}

Return JSON with matched selections:
{{
    "matched_hotels": [
        {{"city": "Bangkok", "hotel_id": 123, "hotel_name": "...", "match_reason": "customer mentioned Ibis"}},
        {{"city": "Chiang Mai", "hotel_id": 456, "hotel_name": "...", "match_reason": "similar to customer preference"}},
        {{"city": "Phuket", "hotel_id": 789, "hotel_name": "...", "match_reason": "beach resort matching preference"}}
    ],
    "matched_services": [
        {{"city": "Bangkok", "service_id": 111, "service_name": "...", "match_reason": "matches shopping interest"}},
        {{"city": "Bangkok", "service_id": 222, "service_name": "...", "match_reason": "matches cultural tours"}},
        {{"city": "Chiang Mai", "service_id": 333, "service_name": "...", "match_reason": "matches cultural tours"}},
        {{"city": "Chiang Mai", "service_id": 444, "service_name": "...", "match_reason": "matches activities"}},
        {{"city": "Phuket", "service_id": 555, "service_name": "...", "match_reason": "matches beach time"}},
        {{"city": "Phuket", "service_id": 666, "service_name": "...", "match_reason": "water activities"}}
    ]
}}

CRITICAL RULES:
1. **MUST select hotels for EVERY city** in the destinations list
2. **MUST select AT LEAST 2-3 services per city** to cover multiple days
3. Match hotel names even with spelling variations (e.g., "Ibis reviver side" → "Ibis Riverside")
4. Match services based on activity keywords (e.g., "shopping" → shopping tour services, "cultural" → temple/palace tours, "beach" → island/water activities)
5. Only select from the provided available options
6. Provide match_reason to explain why you selected each item
7. Prioritize variety - select different types of services for each city
"""

    # Append per-request guideline + saved "remember" instructions (matching scope)
    prompt += _build_ai_guidance(guideline, AIParserInstruction.SCOPE_MATCHING)

    try:
        ai_response = _step_json(
            prompt,
            system_instruction="You are a hotel and service matching expert. Always respond with valid JSON.",
            chat=chat,
        )

        matches = _loads_json(ai_response)

        print("=" * 50)
        print("STEP 2 - HOTEL & SERVICE MATCHING:")
        print(f"Matched hotels: {matches.get('matched_hotels')}")
        print(f"Matched services: {matches.get('matched_services')}")
        print("=" * 50)

        return matches

    except Exception as e:
        print(f"Gemini API error in Step 2: {str(e)}")
        return {
            'matched_hotels': [],
            'matched_services': [],
            'error': str(e)
        }

def match_extracted_data_with_models(analysis_result, guideline="", chat=None):
    """
    Match extracted data with Django models following the manual import pattern.
    Returns structured data ready for tour package creation.
    """
    from datetime import datetime, timedelta

    matched_data = {
        'tour_pack_type': None,  # Single tour pack type based on number of people
        'cities': [],
        'tour_days': [],  # Structured tour days ready for form
        'package_name_suggestion': '',
        'customer_name_suggestion': '',
        'reasoning': {'hotels': [], 'services': []},  # AI's logic for each choice (for UI review)
    }

    # 1. Match Tour Pack Type based on number of people
    num_people = analysis_result.get('number_of_people')
    if num_people:
        # Convert to pax format (e.g., 2 -> "2pax")
        pax_name = f"{num_people}pax"
        pack_type = TourPackType.objects.filter(name__iexact=pax_name).first()
        if pack_type:
            matched_data['tour_pack_type'] = {
                'id': pack_type.id,
                'name': pack_type.name
            }

    # 2. Match cities (already ordered by AI: Central -> North -> South)
    for destination in analysis_result.get('destinations', []):
        city = City.objects.filter(name__iexact=destination).first()
        if city:
            matched_data['cities'].append({
                'id': city.id,
                'name': city.name
            })

    # 2.5 STEP 2: Get AI to match hotels and services from available options
    step2_matches = analyze_hotels_and_services_step2(analysis_result, matched_data['cities'], guideline, chat=chat)

    # Surface the AI's per-item reasoning to the frontend so the user can review
    # the logic and decide what to teach the parser to "remember" next time.
    matched_data['reasoning'] = {
        'hotels': step2_matches.get('matched_hotels', []),
        'services': step2_matches.get('matched_services', []),
    }

    # 3. Create tour days - distribute intelligently across cities based on duration
    # Start date: Use specific date > travel month > tomorrow
    start_date = datetime.now().date() + timedelta(days=1)

    # Priority 1: Use specific start date if provided
    travel_start_date = analysis_result.get('travel_start_date')
    if travel_start_date:
        try:
            from datetime import datetime as dt
            parsed_date = dt.strptime(travel_start_date, '%Y-%m-%d').date()

            # If the date is in the past, move it to next year
            today = datetime.now().date()
            if parsed_date < today:
                # Move to next year
                parsed_date = parsed_date.replace(year=today.year + 1)
                print(f"Date was in past, moved to next year: {parsed_date}")

            start_date = parsed_date
            print(f"Using specific start date: {start_date}")
        except Exception as e:
            print(f"Error parsing start date '{travel_start_date}': {e}")

    # Priority 2: Use travel month if no specific date
    if not travel_start_date:
        travel_months = analysis_result.get('travel_months') or []
        raw_activity = (analysis_result.get('raw_activity_mentions') or '').lower()
        raw_hotel = (analysis_result.get('raw_hotel_mentions') or '').lower()

        if travel_months and travel_months[0]:
            try:
                import calendar

                month_name = str(travel_months[0])
                current_year = datetime.now().year

                # Parse month name to month number
                month_num = None
                for i in range(1, 13):
                    if calendar.month_name[i].lower() == month_name.lower():
                        month_num = i
                        break

                if month_num:
                    # If month is in the past, use next year
                    if month_num < datetime.now().month:
                        current_year += 1

                    # Determine day based on travel_timing
                    day = 1  # Default to first day
                    travel_timing = (analysis_result.get('travel_timing') or '').lower()

                    if travel_timing in ['end', 'late']:
                        # End of month: use 20th
                        day = 20
                        print(f"Detected '{travel_timing}' of {month_name} → Using day {day}")
                    elif travel_timing in ['early', 'beginning', 'start']:
                        # Early month: use 1st
                        day = 1
                        print(f"Detected '{travel_timing}' {month_name} → Using day {day}")
                    elif travel_timing in ['mid', 'middle']:
                        # Mid month: use 15th
                        day = 15
                        print(f"Detected '{travel_timing}' {month_name} → Using day {day}")

                    start_date = datetime(current_year, month_num, day).date()
                    print(f"Using travel month {month_name} → Start date: {start_date}")
            except Exception as e:
                print(f"Error parsing travel month: {e}, using tomorrow as start date")

    duration_days = analysis_result.get('duration_days')
    days_per_city_ai = analysis_result.get('days_per_city', {})
    tour_pack_type_id = matched_data['tour_pack_type']['id'] if matched_data['tour_pack_type'] else None

    # Get matched hotels and services from Step 2
    matched_hotels_by_city = {}
    for hotel_match in step2_matches.get('matched_hotels', []):
        city_name = hotel_match.get('city')
        matched_hotels_by_city[city_name] = hotel_match

    matched_services_by_city = {}
    for service_match in step2_matches.get('matched_services', []):
        city_name = service_match.get('city')
        if city_name not in matched_services_by_city:
            matched_services_by_city[city_name] = []
        matched_services_by_city[city_name].append(service_match)

    # Convert duration to integer if it's a string
    if isinstance(duration_days, str):
        try:
            duration_days = int(duration_days)
        except:
            duration_days = None

    # Calculate how many days per city
    num_cities = len(matched_data['cities'])
    if num_cities == 0:
        return matched_data

    # Use AI-recommended days per city if available
    city_day_distribution = []
    if days_per_city_ai:
        print(f"Using AI-recommended days per city: {days_per_city_ai}")
        for city_data in matched_data['cities']:
            city_name = city_data['name']
            num_days = days_per_city_ai.get(city_name, 1)  # Default to 1 if not specified
            # Coerce to a positive int: the AI sometimes returns null or a string
            # (e.g. {"Phuket": null} / "2"), which would later break range()/sum().
            try:
                num_days = int(num_days)
            except (TypeError, ValueError):
                num_days = 1
            if num_days < 1:
                num_days = 1
            city_day_distribution.append((city_data, num_days))
    elif duration_days and duration_days > 0:
        # Fallback: Distribute days evenly across cities
        days_per_city = max(1, duration_days // num_cities)
        remaining_days = duration_days % num_cities

        for idx, city_data in enumerate(matched_data['cities']):
            # Give extra days to later cities (beach destinations get more time)
            extra_day = 1 if idx >= (num_cities - remaining_days) else 0
            num_days_in_city = days_per_city + extra_day
            city_day_distribution.append((city_data, num_days_in_city))
    else:
        # Default: 1 day per city
        city_day_distribution = [(city_data, 1) for city_data in matched_data['cities']]

    # Recalculate total duration from AI recommendations
    if days_per_city_ai:
        duration_days = sum(days for _, days in city_day_distribution)

    # Now create tour days based on distribution
    current_day = 0
    for city_data, num_days_in_city in city_day_distribution:
        city_id = city_data['id']
        city_name = city_data['name']

        # Create multiple days for this city
        for day_in_city in range(num_days_in_city):
            # Calculate date for this day
            day_date = start_date + timedelta(days=current_day)
            is_first_day_in_city = (day_in_city == 0)
            is_last_day_in_city = (day_in_city == num_days_in_city - 1)
            is_first_day_overall = (current_day == 0)
            is_last_day_overall = (current_day == (duration_days - 1) if duration_days else False)

            # 3.1 Find hotel for this city using Step 2 AI matches
            hotel = None
            if city_name in matched_hotels_by_city:
                hotel_match = matched_hotels_by_city[city_name]
                hotel_id = hotel_match.get('hotel_id')
                if hotel_id:
                    hotel = Hotel.objects.filter(id=hotel_id).first()
                    print(f"Using AI-matched hotel: {hotel.name if hotel else 'Not found'} (Reason: {hotel_match.get('match_reason')})")

            # Fallback: get first hotel from database for this city
            if not hotel:
                hotel = Hotel.objects.filter(city_id=city_id).first()
                print(f"Using fallback hotel: {hotel.name if hotel else 'No hotel available'}")

            # 3.2 Find services for this city using Step 2 AI matches
            suggested_services = []

            # Add AI-matched services (activities) - ONE service per day to avoid duplicates
            if city_name in matched_services_by_city:
                available_services = matched_services_by_city[city_name]

                # Use round-robin to distribute services across days in this city
                if available_services and day_in_city < len(available_services):
                    service_match = available_services[day_in_city]
                    service_id = service_match.get('service_id')
                    if service_id:
                        service = Service.objects.filter(id=service_id).first()
                        if service:
                            # Get the price for this tour pack type
                            price = None
                            if tour_pack_type_id:
                                price_obj = ServicePrice.objects.filter(
                                    service=service,
                                    tour_pack_type_id=tour_pack_type_id
                                ).first()
                                if price_obj:
                                    price = str(price_obj.price)

                            suggested_services.append({
                                'id': service.id,
                                'name': service.name,
                                'service_type': service.service_type.name,
                                'price': price,
                                'activity_match': service_match.get('match_reason', '')
                            })
                            print(f"Day {current_day + 1} - Using AI-matched service: {service.name} (Reason: {service_match.get('match_reason')})")
                elif available_services:
                    # If we have more days than services, cycle through services
                    service_match = available_services[day_in_city % len(available_services)]
                    service_id = service_match.get('service_id')
                    if service_id:
                        service = Service.objects.filter(id=service_id).first()
                        if service:
                            price = None
                            if tour_pack_type_id:
                                price_obj = ServicePrice.objects.filter(
                                    service=service,
                                    tour_pack_type_id=tour_pack_type_id
                                ).first()
                                if price_obj:
                                    price = str(price_obj.price)

                            suggested_services.append({
                                'id': service.id,
                                'name': service.name,
                                'service_type': service.service_type.name,
                                'price': price,
                                'activity_match': service_match.get('match_reason', '')
                            })
                            print(f"Day {current_day + 1} - Using AI-matched service (cycled): {service.name}")

            # 3.3 Add inter-city transfer when changing cities
            if is_first_day_in_city and not is_first_day_overall:
                # This is the first day in a new city (not the first day of trip)
                # Need transfer from previous city to this city
                prev_city_idx = matched_data['cities'].index(city_data) - 1
                if prev_city_idx >= 0:
                    prev_city_name = matched_data['cities'][prev_city_idx]['name']

                    # Search for train/bus transfer FROM previous city TO current city
                    # Look in PREVIOUS city's services for transfers going TO current city
                    prev_city_id = matched_data['cities'][prev_city_idx]['id']

                    # Strategy 1: Exact route match (e.g., "Bangkok to Chiang Mai")
                    transfer = Service.objects.filter(
                        service_type__name__icontains='transfer',
                        cities__id=prev_city_id
                    ).filter(
                        name__icontains=prev_city_name
                    ).filter(
                        name__icontains=city_name
                    ).exclude(
                        name__icontains='Bangkok'  # Exclude if going TO Bangkok (wrong direction)
                    ).first() if city_name != 'Bangkok' else Service.objects.filter(
                        service_type__name__icontains='transfer',
                        cities__id=prev_city_id,
                        name__icontains=prev_city_name
                    ).filter(
                        name__icontains=city_name
                    ).first()

                    # Strategy 2: Transfer mentioning destination city (flight/train/bus)
                    if not transfer:
                        transfer = Service.objects.filter(
                            service_type__name__icontains='transfer',
                            cities__id=prev_city_id
                        ).filter(
                            name__icontains=city_name  # Must mention destination
                        ).filter(
                            Q(name__icontains='flight') | Q(name__icontains='train') | Q(name__icontains='bus')
                        ).first()

                    # Strategy 3: Generic transfer with destination keyword
                    if not transfer:
                        # For long distances (e.g., Chiang Mai to Phuket), prefer flight
                        if (prev_city_name == 'Chiang Mai' and city_name == 'Phuket') or \
                           (prev_city_name == 'Phuket' and city_name == 'Chiang Mai'):
                            transfer = Service.objects.filter(
                                service_type__name__icontains='transfer',
                                cities__id=prev_city_id,
                                name__icontains='flight'
                            ).first()

                        # For shorter distances, train/bus is fine
                        if not transfer:
                            transfer = Service.objects.filter(
                                service_type__name__icontains='transfer',
                                cities__id=prev_city_id
                            ).filter(
                                Q(name__icontains='train') | Q(name__icontains='bus')
                            ).first()

                    if transfer and tour_pack_type_id:
                        price_obj = ServicePrice.objects.filter(
                            service=transfer,
                            tour_pack_type_id=tour_pack_type_id
                        ).first()
                        if price_obj:
                            suggested_services.insert(0, {
                                'id': transfer.id,
                                'name': transfer.name,
                                'service_type': transfer.service_type.name,
                                'price': str(price_obj.price),
                                'activity_match': f'transfer_{prev_city_name}_to_{city_name}'
                            })
                            print(f"Day {current_day + 1} - Added inter-city transfer: {transfer.name}")

            # 3.4 Add arrival transfer for first day of trip
            if is_first_day_overall:
                # Search for transfer services with 'airport' AND city name
                transfer = Service.objects.filter(
                    service_type__name__icontains='transfer',
                    cities__id=city_id
                ).filter(
                    name__icontains='airport'
                ).filter(
                    name__icontains=city_name
                ).first()

                if transfer and tour_pack_type_id:
                    price_obj = ServicePrice.objects.filter(
                        service=transfer,
                        tour_pack_type_id=tour_pack_type_id
                    ).first()
                    if price_obj:
                        suggested_services.insert(0, {
                            'id': transfer.id,
                            'name': transfer.name,
                            'service_type': transfer.service_type.name,
                            'price': str(price_obj.price),
                            'activity_match': 'arrival_transfer'
                        })

            # 3.5 Add departure transfer for last day of trip
            if is_last_day_overall:
                # Search for transfer services with 'airport' AND city name
                transfer = Service.objects.filter(
                    service_type__name__icontains='transfer',
                    cities__id=city_id
                ).filter(
                    name__icontains='airport'
                ).filter(
                    name__icontains=city_name
                ).first()

                if transfer and tour_pack_type_id:
                    price_obj = ServicePrice.objects.filter(
                        service=transfer,
                        tour_pack_type_id=tour_pack_type_id
                    ).first()
                    if price_obj:
                        suggested_services.append({
                            'id': transfer.id,
                            'name': transfer.name,
                            'service_type': transfer.service_type.name,
                            'price': str(price_obj.price),
                            'activity_match': 'departure_transfer'
                        })

            # Build tour day object
            tour_day = {
                'date': day_date.isoformat(),
                'city_id': city_id,
                'city_name': city_name,
                'hotel_id': hotel.id if hotel else None,
                'hotel_name': hotel.name if hotel else 'No hotel available',
                'services': suggested_services
            }

            matched_data['tour_days'].append(tour_day)
            current_day += 1

    # 4. Generate package name suggestion
    if matched_data['cities']:
        city_names = ' - '.join([c['name'] for c in matched_data['cities']])
        pax_info = matched_data['tour_pack_type']['name'] if matched_data['tour_pack_type'] else ''
        matched_data['package_name_suggestion'] = f"{city_names} Tour ({pax_info})"

    # 5. Customer name suggestion
    customer_name = analysis_result.get('customer_name', '')
    if customer_name:
        matched_data['customer_name_suggestion'] = customer_name

    return matched_data
