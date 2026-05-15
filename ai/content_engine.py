"""
AI content engine — wraps Anthropic (primary) with OpenAI fallback.
Tracks token costs so every generation maps to a P&L line.
"""
import json
import time
from typing import Any, Optional

from core.config import get_settings
from ai.prompt_library import Prompt

settings = get_settings()

# Cost per 1M tokens (USD) — update as pricing changes
COST_TABLE = {
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":   {"input": 0.25,  "output": 1.25},
    "gpt-4o":             {"input": 5.00,  "output": 15.00},
    "gpt-4o-mini":        {"input": 0.15,  "output": 0.60},
}


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    table = COST_TABLE.get(model, {"input": 5.0, "output": 15.0})
    return (input_tokens / 1_000_000) * table["input"] + \
           (output_tokens / 1_000_000) * table["output"]


class GenerationResult:
    def __init__(self, text: str, model: str,
                 input_tokens: int, output_tokens: int):
        self.text = text
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.cost_usd = _calc_cost(model, input_tokens, output_tokens)

    def as_json(self) -> Optional[Any]:
        """Attempt to parse text as JSON, return None on failure."""
        try:
            return json.loads(self.text)
        except json.JSONDecodeError:
            # Strip markdown code fences if present
            stripped = self.text.strip()
            if stripped.startswith("```"):
                stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0]
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return None


class ContentEngine:
    """
    Generates content via Claude (primary) or GPT (fallback).
    Each instance can be injected with a db session for auto-logging.
    """

    def __init__(self, db_session=None):
        self._db = db_session
        self._anthropic = None
        self._openai = None

    def _get_anthropic(self):
        if self._anthropic is None:
            import anthropic
            self._anthropic = anthropic.Anthropic(
                api_key=settings.anthropic_api_key
            )
        return self._anthropic

    def _get_openai(self):
        if self._openai is None:
            from openai import OpenAI
            self._openai = OpenAI(api_key=settings.openai_api_key)
        return self._openai

    def generate(
        self,
        prompt: Prompt,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> GenerationResult:
        """
        Generate text. Tries Claude first, falls back to GPT on any error.
        """
        model = model or settings.ai_model
        max_tokens = max_tokens or settings.ai_max_tokens

        # ── Try Claude ────────────────────────────────────────────────
        if "claude" in model and settings.anthropic_api_key:
            try:
                return self._call_claude(prompt, model, max_tokens, temperature)
            except Exception as exc:
                print(f"[ContentEngine] Claude failed ({exc}), falling back to GPT")

        # ── Try OpenAI fallback ───────────────────────────────────────
        if settings.openai_api_key:
            fallback = settings.ai_fallback_model
            return self._call_openai(prompt, fallback, max_tokens, temperature)

        raise RuntimeError(
            "No AI provider available. Set ANTHROPIC_API_KEY or OPENAI_API_KEY."
        )

    def _call_claude(self, prompt: Prompt, model: str,
                     max_tokens: int, temperature: float) -> GenerationResult:
        client = self._get_anthropic()
        t0 = time.perf_counter()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=prompt.system,
            messages=[{"role": "user", "content": prompt.user}],
            temperature=temperature,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        text = response.content[0].text
        result = GenerationResult(
            text=text,
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        print(
            f"[ContentEngine] Claude {model} | "
            f"{result.total_tokens} tok | ${result.cost_usd:.4f} | {elapsed_ms}ms"
        )
        return result

    def _call_openai(self, prompt: Prompt, model: str,
                     max_tokens: int, temperature: float) -> GenerationResult:
        client = self._get_openai()
        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": prompt.system},
                {"role": "user",   "content": prompt.user},
            ],
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        text = response.choices[0].message.content
        result = GenerationResult(
            text=text,
            model=model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
        print(
            f"[ContentEngine] OpenAI {model} | "
            f"{result.total_tokens} tok | ${result.cost_usd:.4f} | {elapsed_ms}ms"
        )
        return result

    # ── Convenience wrappers ──────────────────────────────────────────────────

    def cheap_generate(self, prompt: Prompt) -> GenerationResult:
        """Use the cheapest model — for bulk scheduled tasks."""
        cheap = "claude-haiku-4-5" if settings.anthropic_api_key else "gpt-4o-mini"
        return self.generate(prompt, model=cheap)
