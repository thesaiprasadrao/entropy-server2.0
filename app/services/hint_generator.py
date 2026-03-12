"""
AI hint generation service.

Generates vague, safe hints for CTF levels. The AI is never given the
flag value — only the level name, description, and difficulty.
"""

from groq import Groq

from app.config import get_settings
from app.services.llm_client import _get_next_key

MAX_HINT_TOKENS = 150
HINT_MODEL = "llama-3.3-70b-versatile"

HINT_SYSTEM_PROMPT = """You are a hint generator for a cybersecurity CTF puzzle.

Rules (strictly follow):
- NEVER reveal the flag, secret key, or exact solution.
- Keep hints short: 1–2 sentences only.
- Give a vague directional nudge that points the player in the right direction.
- Do not mention the word "flag" or specific technical exploits.
- Be cryptic but still helpful."""


def generate_hint(level_name: str, level_description: str, difficulty: str = "hard") -> str:
    """
    Generate a safe, non-spoiling AI hint for a CTF level.
    The flag/secret is never passed to this function.
    """
    api_key = _get_next_key()
    client = Groq(api_key=api_key)

    user_message = (
        f"Level: {level_name}\n"
        f"Difficulty: {difficulty}\n"
        f"Description: {level_description}\n\n"
        "Give me a 1–2 sentence hint that nudges me in the right direction "
        "without revealing the answer."
    )

    completion = client.chat.completions.create(
        model=HINT_MODEL,
        messages=[
            {"role": "system", "content": HINT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=MAX_HINT_TOKENS,
        temperature=0.5,
    )
    return completion.choices[0].message.content or "Think about what the AI is trying to protect."
