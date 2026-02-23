"""
Generate a two-host podcast script from extracted book text using Google Gemini.
Returns a list of {speaker, text} dicts. No Flask imports.
"""
import json
import re

import google.generativeai as genai

try:
    import config
    GEMINI_API_KEY = config.GEMINI_API_KEY
    GEMINI_MODEL = getattr(config, "GEMINI_MODEL", "gemini-1.5-pro")
    GEMINI_TIMEOUT = getattr(config, "GEMINI_TIMEOUT", 120)
except ImportError:
    GEMINI_API_KEY = ""
    GEMINI_MODEL = "gemini-1.5-flash"
    GEMINI_TIMEOUT = 120


class ScriptGenerationError(Exception):
    """Raised when Gemini fails or returns invalid script JSON."""
    pass


# Fixed instruction template; book content is passed separately to avoid injection.
INSTRUCTION = """You are a scriptwriter. Write a short podcast script based on the book content below.

Rules:
- Two hosts: "Host A" (female) and "Host B" (male).
- Tone: warm, engaging, conversational. Discuss the book's synopsis and key takeaways.
- Output ONLY a valid JSON array. No markdown, no code fence, no other text.
- Each element: {"speaker": "Host A" or "Host B", "text": "one line of dialogue"}.
- Use "Host A" and "Host B" exactly. Keep each "text" to 1-3 sentences.
- Aim for about 8-16 dialogue turns total.

Book content:
"""


def _parse_script_json(raw: str) -> list[dict]:
    """Parse and validate script JSON from model output. Strips code fences if present."""
    raw = raw.strip()
    # Remove optional markdown code block
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ScriptGenerationError("Model did not return valid JSON.") from e
    if not isinstance(data, list):
        raise ScriptGenerationError("Script must be a JSON array.")
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "speaker" not in item or "text" not in item:
            raise ScriptGenerationError(f"Script item {i} must have 'speaker' and 'text'.")
        if item["speaker"] not in ("Host A", "Host B"):
            item["speaker"] = "Host A" if "female" in str(item.get("speaker", "")).lower() else "Host B"
        item["text"] = str(item["text"]).strip()
        if not item["text"]:
            raise ScriptGenerationError(f"Script item {i} has empty text.")
    return data


def generate_podcast_script(extracted_text: str, *, model: str | None = None) -> list[dict]:
    """
    Call Gemini to generate a podcast script. Returns list of {speaker, text}.
    Uses extracted_text as content only; instructions are fixed.
    """
    if not GEMINI_API_KEY:
        raise ScriptGenerationError("GEMINI_API_KEY is not set.")
    model = model or GEMINI_MODEL
    genai.configure(api_key=GEMINI_API_KEY)
    prompt = INSTRUCTION + extracted_text[:200_000]  # Extra safety cap per request

    try:
        generative_model = genai.GenerativeModel(model)
        response = generative_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=8192,
            ),
            request_options={"timeout": GEMINI_TIMEOUT} if GEMINI_TIMEOUT else {},
        )
    except Exception as e:
        err_msg = str(e).lower()
        if "timeout" in err_msg or "deadline" in err_msg:
            raise ScriptGenerationError("Request timed out. Try a shorter book or try again.") from e
        if "quota" in err_msg or "rate" in err_msg:
            raise ScriptGenerationError("API rate limit reached. Please try again later.") from e
        if "length" in err_msg or "context" in err_msg:
            raise ScriptGenerationError("Summary too long. Try a shorter book or reduce input.") from e
        raise ScriptGenerationError("Failed to generate script. Please try again.") from e

    if not response or not response.text:
        raise ScriptGenerationError("Model returned no text.")

    return _parse_script_json(response.text)
