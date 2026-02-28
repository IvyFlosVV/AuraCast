"""
Generate a two-host podcast script from extracted book text using Google Gemini.
Returns a list of {speaker, text} dicts. No Flask imports.
"""
import json
import re
import time
import warnings

# Suppress deprecation warning for google.generativeai (still works; migrate to google.genai later)
with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=FutureWarning)
    import google.generativeai as genai

try:
    import config
    GEMINI_API_KEY = config.GEMINI_API_KEY
    GEMINI_MODEL = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
    GEMINI_TIMEOUT = getattr(config, "GEMINI_TIMEOUT", 120)
    GEMINI_MAX_INPUT_CHARS = getattr(config, "GEMINI_MAX_INPUT_CHARS", 30_000)
    RETRY_DELAY_SEC = getattr(config, "RETRY_DELAY_SEC", 30)
except ImportError:
    GEMINI_API_KEY = ""
    GEMINI_MODEL = "gemini-1.5-flash"
    GEMINI_TIMEOUT = 120
    GEMINI_MAX_INPUT_CHARS = 30_000
    RETRY_DELAY_SEC = 30


class ScriptGenerationError(Exception):
    """Raised when Gemini fails or returns invalid script JSON."""
    pass


# Fixed instruction template; book content is passed separately to avoid injection.
INSTRUCTION = """You are a scriptwriter. Write a short podcast script based on the book excerpt below.

Rules:
- Two hosts: "Host A" (female) and "Host B" (male).
- Tone: warm, engaging, conversational. Summarize the book's premise and key takeaways from the excerpt.
- Output ONLY a valid JSON array. No markdown, no code fence, no other text.
- Each element: {"speaker": "Host A" or "Host B", "text": "one line of dialogue"}.
- Use "Host A" and "Host B" exactly. Keep each "text" to 1-3 sentences.
- Aim for about 8-16 dialogue turns total.

Book excerpt:
"""

# Shorter episode script (5-8 turns) for one chunk; optional user focus prompt.
EPISODE_INSTRUCTION_TEMPLATE = """You are a scriptwriter. Write a short podcast segment based on the book excerpt below.

Rules:
- Two hosts: "Host A" (female) and "Host B" (male).
- Tone: warm, engaging, conversational. Summarize this excerpt's key points.
{focus_line}
- Output ONLY a valid JSON array. No markdown, no code fence, no other text.
- Each element: {{"speaker": "Host A" or "Host B", "text": "one line of dialogue"}}.
- Use "Host A" and "Host B" exactly. Keep each "text" to 1-3 sentences.
- Aim for 5-8 dialogue turns total.

Book excerpt:
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


# Retry settings for rate-limit and transient errors (RETRY_DELAY_SEC from config, default 30)
MAX_RETRIES = 2


def generate_podcast_script(extracted_text: str, *, model: str | None = None) -> list[dict]:
    """
    Call Gemini to generate a podcast script. Returns list of {speaker, text}.
    Uses extracted_text as content only; instructions are fixed.
    Retries up to MAX_RETRIES on rate-limit or transient errors.
    """
    if not GEMINI_API_KEY:
        raise ScriptGenerationError("GEMINI_API_KEY is not set.")
    model = model or GEMINI_MODEL
    genai.configure(api_key=GEMINI_API_KEY)
    # Cap input size to stay within free-tier token limits (fewer tokens = fewer rate limits)
    prompt = INSTRUCTION + extracted_text[:GEMINI_MAX_INPUT_CHARS]

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
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
            last_error = e
            err_msg = str(e).lower()
            is_rate_limit = "quota" in err_msg or "rate" in err_msg or "429" in err_msg
            if is_rate_limit and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)
                continue
            if "timeout" in err_msg or "deadline" in err_msg:
                raise ScriptGenerationError("Request timed out. Try a shorter book or try again.") from e
            if is_rate_limit:
                raise ScriptGenerationError(
                    "Free tier rate limit reached. Wait 1–2 minutes, then try again. Use one episode at a time; in .env set GEMINI_MAX_INPUT_CHARS=15000 to use fewer tokens."
                ) from e
            if "length" in err_msg or "context" in err_msg:
                raise ScriptGenerationError("Summary too long. Try a shorter book or reduce input.") from e
            raise ScriptGenerationError("Failed to generate script. Please try again.") from e

        if not response or not response.text:
            raise ScriptGenerationError("Model returned no text.")

        return _parse_script_json(response.text)

    raise ScriptGenerationError(
        "Free tier rate limit reached. Wait 1–2 minutes, then try again."
    ) from last_error


def generate_episode_script(chunk_text: str, user_prompt: str = "", *, model: str | None = None) -> list[dict]:
    """
    Generate a short (5-8 turn) two-host script for one chunk. Optional user_prompt focuses the hosts.
    Same retry/parse as generate_podcast_script.
    """
    if not GEMINI_API_KEY:
        raise ScriptGenerationError("GEMINI_API_KEY is not set.")
    focus_line = ""
    if user_prompt and user_prompt.strip():
        focus_line = "- The hosts should focus on: " + user_prompt.strip() + "\n"
    instruction = EPISODE_INSTRUCTION_TEMPLATE.format(focus_line=focus_line)
    prompt = instruction + chunk_text[:GEMINI_MAX_INPUT_CHARS]
    model = model or GEMINI_MODEL
    genai.configure(api_key=GEMINI_API_KEY)

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            generative_model = genai.GenerativeModel(model)
            response = generative_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                ),
                request_options={"timeout": GEMINI_TIMEOUT} if GEMINI_TIMEOUT else {},
            )
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            is_rate_limit = "quota" in err_msg or "rate" in err_msg or "429" in err_msg
            if is_rate_limit and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)
                continue
            if "timeout" in err_msg or "deadline" in err_msg:
                raise ScriptGenerationError("Request timed out. Try again.") from e
            if is_rate_limit:
                raise ScriptGenerationError(
                    "Free tier rate limit reached. Wait 1–2 minutes, then try one episode at a time. In .env you can set GEMINI_MAX_INPUT_CHARS=15000 to use fewer tokens."
                ) from e
            if "length" in err_msg or "context" in err_msg:
                raise ScriptGenerationError("Summary too long. Try again.") from e
            if "key" in err_msg or "api_key" in err_msg or "invalid" in err_msg and "api" in err_msg:
                raise ScriptGenerationError(
                    "Gemini API key missing or invalid. Check GEMINI_API_KEY in .env."
                ) from e
            if "blocked" in err_msg or "safety" in err_msg:
                raise ScriptGenerationError(
                    "Content was blocked. Try a different focus prompt or chapter."
                ) from e
            raise ScriptGenerationError(
                "Failed to generate script. Please try again. (Tip: wait a minute if you hit rate limits.)"
            ) from e

        if not response or not response.text:
            raise ScriptGenerationError("Model returned no text.")
        try:
            return _parse_script_json(response.text)
        except ScriptGenerationError:
            raise
        except Exception as e:
            raise ScriptGenerationError(
                "Model returned an invalid format. Please try again."
            ) from e

    raise ScriptGenerationError(
        "Free tier rate limit reached. Wait 1–2 minutes, then try one episode at a time."
    ) from last_error


INTERRUPT_INSTRUCTION_TEMPLATE = """The user asked the podcast hosts: "{question}"

Based on the following podcast script (what the hosts just said), have Host A and Host B each give a brief 1-2 sentence answer. Stay in character and address the question.

Output ONLY a valid JSON array of exactly 2 elements: [{{"speaker": "Host A", "text": "..."}}, {{"speaker": "Host B", "text": "..."}}]. No markdown, no code fence.

Podcast script (what the hosts said):
{script_text}
"""


def generate_interrupt_reply(
    question: str,
    episode_script: list[dict],
    chunk_text: str | None = None,
    *,
    model: str | None = None,
) -> list[dict]:
    """
    Generate a 2-line reply (Host A, Host B) answering the user's question based on the episode script.
    Optionally include chunk_text for deeper context.
    """
    if not GEMINI_API_KEY:
        raise ScriptGenerationError("GEMINI_API_KEY is not set.")
    script_text = "\n".join(
        (item.get("speaker", "") + ": " + (item.get("text") or "")) for item in episode_script
    )
    if chunk_text:
        script_text += "\n\n[Additional context from the book:\n" + chunk_text[:8000] + "]"
    # Escape braces so .format() does not interpret them
    q_esc = question.replace("{", "{{").replace("}", "}}")
    s_esc = script_text.replace("{", "{{").replace("}", "}}")
    prompt = INTERRUPT_INSTRUCTION_TEMPLATE.format(question=q_esc, script_text=s_esc)
    model = model or GEMINI_MODEL
    genai.configure(api_key=GEMINI_API_KEY)

    try:
        generative_model = genai.GenerativeModel(model)
        response = generative_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.6,
                max_output_tokens=512,
            ),
            request_options={"timeout": GEMINI_TIMEOUT} if GEMINI_TIMEOUT else {},
        )
    except Exception as e:
        err_msg = str(e).lower()
        if "quota" in err_msg or "rate" in err_msg or "429" in err_msg:
            raise ScriptGenerationError("Free tier rate limit. Wait 1–2 minutes and try again.") from e
        raise ScriptGenerationError("Failed to generate reply. Please try again.") from e

    if not response or not response.text:
        raise ScriptGenerationError("Model returned no text.")
    data = _parse_script_json(response.text)
    if len(data) < 2:
        raise ScriptGenerationError("Reply must have at least Host A and Host B.")
    return data[:2]
