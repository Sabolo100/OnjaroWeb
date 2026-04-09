"""Channel-specific prompt templates for content generation.

Each template receives:
  - event_type: the type of change (new_entity, data_update, etc.)
  - title: event title
  - summary: event summary
  - entity_type: company/building/person
  - entity_name: name of the changed entity
  - details: JSON details of the change
  - channel_tone: tone guidance from channel config
"""

# ── System prompt (shared) ──────────────────────────────────────────

SYSTEM_PROMPT = (
    "Te az FMintel platform kommunikációs asszisztense vagy. "
    "Az FMintel a magyar ingatlanpiac (facility management, property management, "
    "asset management) legátfogóbb piaci intelligencia platformja. "
    "A célközönség: magyar ingatlanpiaci szakemberek, döntéshozók, FM/PM/AM vezetők. "
    "Mindig magyarul kommunikálj, szakmai de közérthető stílusban. "
    "Csak a kért formátumban válaszolj, semmi mást ne adj hozzá."
)

# ── LinkedIn ────────────────────────────────────────────────────────

LINKEDIN_PROMPT = """Írj egy LinkedIn posztot az alábbi FMintel platformfrissítés alapján.

ESEMÉNY TÍPUSA: {event_type}
CÍM: {title}
ÖSSZEFOGLALÓ: {summary}
RÉSZLETEK: {details}

HANGNEM: {channel_tone}

FORMÁTUM (JSON):
{{
  "title": "Rövid, figyelemfelkeltő headline (max 100 karakter)",
  "body": "LinkedIn poszt szövege. 2-4 bekezdés. Szakmai de emberi hangvétel. Használj emojit mértékkel. Zárd CTA-val. Max 2500 karakter.",
  "cta": "CTA szöveg (pl. 'Nézd meg az FMintel platformon →')",
  "hashtags": ["FMintel", "ingatlanpiac", "facilitymanagement", "max5hashtag"]
}}

FONTOS:
- Ne legyen túl reklámszerű, inkább értéket közvetíts
- Első mondat legyen erős hook
- Csak JSON-t adj vissza"""

# ── Mailchimp / EDM ─────────────────────────────────────────────────

MAILCHIMP_PROMPT = """Írj egy hírlevél szöveget (EDM) az alábbi FMintel platformfrissítés alapján.

ESEMÉNY TÍPUSA: {event_type}
CÍM: {title}
ÖSSZEFOGLALÓ: {summary}
RÉSZLETEK: {details}

HANGNEM: {channel_tone}

FORMÁTUM (JSON):
{{
  "title": "Email tárgysor — max 80 karakter, kattintásra ösztönző",
  "body": "Hírlevél fő szövege. Üdvözlés + fő blokk (mit, miért, kinek hasznos) + CTA. Max 1500 karakter. HTML formázás NÉLKÜL, csak szöveg.",
  "cta": "CTA gomb szövege (pl. 'Megnézem az FMintel-en')"
}}

FONTOS:
- A tárgysor legyen rövid és releváns, ne clickbait
- A szöveg legyen közvetlen és értékközpontú
- Csak JSON-t adj vissza"""

# ── Email (direct) ──────────────────────────────────────────────────

EMAIL_PROMPT = """Írj egy rövid, személyes hangvételű email szöveget az alábbi FMintel frissítés alapján.

ESEMÉNY TÍPUSA: {event_type}
CÍM: {title}
ÖSSZEFOGLALÓ: {summary}
RÉSZLETEK: {details}

HANGNEM: {channel_tone}

FORMÁTUM (JSON):
{{
  "title": "Email tárgysor — max 60 karakter",
  "body": "Email szövege. Rövid üdvözlés + lényeg 2-3 mondatban + CTA. Max 800 karakter.",
  "cta": "Link szöveg (pl. 'Részletek az FMintel-en →')"
}}

FONTOS:
- Személyes, közvetlen hangvétel (nem hírlevél, hanem értesítés jelleg)
- Csak JSON-t adj vissza"""

# ── Facebook ────────────────────────────────────────────────────────

FACEBOOK_PROMPT = """Írj egy Facebook posztot az alábbi FMintel platformfrissítés alapján.

ESEMÉNY TÍPUSA: {event_type}
CÍM: {title}
ÖSSZEFOGLALÓ: {summary}
RÉSZLETEK: {details}

HANGNEM: {channel_tone}

FORMÁTUM (JSON):
{{
  "title": "",
  "body": "Facebook poszt szövege. Könnyed, befogadható stílus. 1-2 bekezdés. Max 800 karakter. Használj emojit.",
  "cta": "CTA szöveg",
  "hashtags": ["FMintel", "ingatlanpiac", "max3hashtag"]
}}

FONTOS:
- Rövid, vizuális, könnyen scrollozható
- Emberi hangvétel, ne legyen corporate
- Csak JSON-t adj vissza"""

# ── Weekly digest prompt ────────────────────────────────────────────

DIGEST_PROMPT = """Készíts heti összefoglalót az alábbi FMintel platform frissítésekből.

FRISSÍTÉSEK ({count} db):
{events_json}

CSATORNA: {channel_name}
HANGNEM: {channel_tone}

FORMÁTUM (JSON):
{{
  "title": "Összefoglaló cím / tárgysor",
  "body": "Összefoglaló szöveg. A legfontosabb 3-5 frissítés kiemelése. Zárd CTA-val.",
  "cta": "CTA szöveg",
  "hashtags": ["FMintel", "max3hashtag"]
}}

FONTOS:
- Priorizáld a fontosabb frissítéseket
- Ne listázd mindet, csak a legérdekesebbeket
- Csak JSON-t adj vissza"""

# ── Channel → prompt mapping ───────────────────────────────────────

CHANNEL_PROMPTS = {
    "linkedin": LINKEDIN_PROMPT,
    "mailchimp": MAILCHIMP_PROMPT,
    "email": EMAIL_PROMPT,
    "facebook": FACEBOOK_PROMPT,
}
