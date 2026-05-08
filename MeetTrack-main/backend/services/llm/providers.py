"""
LLM Providers — Unified interface for Gemini, OpenAI, and local fallback.

Each provider implements:
  complete(prompt, task_type, max_tokens) → LLMResponse

ProviderName enum drives routing decisions.
TaskType enum maps tasks to preferred providers.
"""

import enum
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────────────

class ProviderName(str, enum.Enum):
    GEMINI   = "gemini"
    OPENAI   = "openai"
    LOCAL    = "local"


class TaskType(str, enum.Enum):
    SUMMARIZATION  = "summarization"   # → Gemini (best at long-form)
    EXTRACTION     = "extraction"      # → Gemini (structured JSON)
    REASONING      = "reasoning"       # → GPT-4o (best at logic chains)
    SENTIMENT      = "sentiment"       # → Gemini flash (fast)
    CLASSIFICATION = "classification"  # → local (lightweight)
    EMBEDDING      = "embedding"       # → Gemini text-embedding-004
    CHAT           = "chat"            # → GPT-4o-mini (conversational)
    FALLBACK       = "fallback"        # → local keyword extraction


# ── Response dataclass ────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    text:           str
    provider:       ProviderName
    model:          str
    task_type:      TaskType
    latency_ms:     float
    prompt_tokens:  int
    completion_tokens: int
    total_tokens:   int
    cost_usd:       float
    quality_score:  float = 0.0        # set by quality scorer
    cache_hit:      bool  = False
    error:          Optional[str] = None
    raw_response:   Optional[object] = field(default=None, repr=False)

    @property
    def success(self) -> bool:
        return bool(self.text) and self.error is None


# ── Token estimation ──────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Fast token estimate: ~4 chars per token (GPT-4 rule of thumb)."""
    return max(1, len(text) // 4)


# ── Cost table (USD per 1K tokens, input/output) ──────────────────────────────

COST_TABLE = {
    # model_name: (input_per_1k, output_per_1k)
    "gemini-1.5-flash":       (0.000075, 0.0003),
    "gemini-1.5-pro":         (0.00125,  0.005),
    "gemini-2.0-flash":       (0.000075, 0.0003),
    "gpt-4o":                 (0.005,    0.015),
    "gpt-4o-mini":            (0.00015,  0.0006),
    "gpt-3.5-turbo":          (0.0005,   0.0015),
    "local":                  (0.0,      0.0),
}

def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = COST_TABLE.get(model, (0.001, 0.002))
    return round((prompt_tokens / 1000) * inp + (completion_tokens / 1000) * out, 6)


# ── Base provider ─────────────────────────────────────────────────────────────

class BaseProvider:
    name: ProviderName
    default_model: str

    def complete(self, prompt: str, task_type: TaskType, max_tokens: int = 2048) -> LLMResponse:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError


# ── Gemini provider ───────────────────────────────────────────────────────────

class GeminiProvider(BaseProvider):
    name = ProviderName.GEMINI

    # Task → model mapping (flash for speed, pro for quality)
    TASK_MODELS = {
        TaskType.SUMMARIZATION:  "gemini-1.5-pro",
        TaskType.EXTRACTION:     "gemini-1.5-flash",
        TaskType.REASONING:      "gemini-1.5-pro",
        TaskType.SENTIMENT:      "gemini-1.5-flash",
        TaskType.CLASSIFICATION: "gemini-1.5-flash",
        TaskType.CHAT:           "gemini-1.5-flash",
        TaskType.FALLBACK:       "gemini-1.5-flash",
    }
    default_model = "gemini-1.5-flash"

    def __init__(self):
        self._api_key = os.getenv("GEMINI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete(self, prompt: str, task_type: TaskType, max_tokens: int = 2048) -> LLMResponse:
        model = self.TASK_MODELS.get(task_type, self.default_model)
        t0 = time.perf_counter()

        try:
            from google import genai
            from google.genai import types as gtypes

            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=gtypes.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.2,
                ),
            )
            text = response.text.strip() if response.text else ""
            latency = (time.perf_counter() - t0) * 1000

            p_tok = estimate_tokens(prompt)
            c_tok = estimate_tokens(text)

            # Use actual usage if available
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                p_tok = getattr(um, "prompt_token_count", p_tok) or p_tok
                c_tok = getattr(um, "candidates_token_count", c_tok) or c_tok

            return LLMResponse(
                text=text,
                provider=ProviderName.GEMINI,
                model=model,
                task_type=task_type,
                latency_ms=round(latency, 1),
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=p_tok + c_tok,
                cost_usd=compute_cost(model, p_tok, c_tok),
                raw_response=response,
            )

        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000
            logger.error(f"[Gemini] Error: {exc}")
            return LLMResponse(
                text="", provider=ProviderName.GEMINI, model=model,
                task_type=task_type, latency_ms=round(latency, 1),
                prompt_tokens=0, completion_tokens=0, total_tokens=0,
                cost_usd=0.0, error=str(exc),
            )


# ── OpenAI provider ───────────────────────────────────────────────────────────

class OpenAIProvider(BaseProvider):
    name = ProviderName.OPENAI

    TASK_MODELS = {
        TaskType.REASONING:      "gpt-4o",
        TaskType.CHAT:           "gpt-4o-mini",
        TaskType.SUMMARIZATION:  "gpt-4o-mini",
        TaskType.EXTRACTION:     "gpt-4o-mini",
        TaskType.SENTIMENT:      "gpt-4o-mini",
        TaskType.CLASSIFICATION: "gpt-4o-mini",
        TaskType.FALLBACK:       "gpt-3.5-turbo",
    }
    default_model = "gpt-4o-mini"

    def __init__(self):
        self._api_key = os.getenv("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete(self, prompt: str, task_type: TaskType, max_tokens: int = 2048) -> LLMResponse:
        model = self.TASK_MODELS.get(task_type, self.default_model)
        t0 = time.perf_counter()

        try:
            import openai
            client = openai.OpenAI(api_key=self._api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
            )
            text    = resp.choices[0].message.content.strip() if resp.choices else ""
            latency = (time.perf_counter() - t0) * 1000
            p_tok   = resp.usage.prompt_tokens     if resp.usage else estimate_tokens(prompt)
            c_tok   = resp.usage.completion_tokens if resp.usage else estimate_tokens(text)

            return LLMResponse(
                text=text,
                provider=ProviderName.OPENAI,
                model=model,
                task_type=task_type,
                latency_ms=round(latency, 1),
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=p_tok + c_tok,
                cost_usd=compute_cost(model, p_tok, c_tok),
                raw_response=resp,
            )

        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000
            logger.error(f"[OpenAI] Error: {exc}")
            return LLMResponse(
                text="", provider=ProviderName.OPENAI, model=model,
                task_type=task_type, latency_ms=round(latency, 1),
                prompt_tokens=0, completion_tokens=0, total_tokens=0,
                cost_usd=0.0, error=str(exc),
            )


# ── Local fallback provider ───────────────────────────────────────────────────

class LocalProvider(BaseProvider):
    """
    Zero-dependency keyword extraction fallback.
    No API key needed — always available.
    Used when all cloud providers fail or quota is exhausted.
    """
    name = ProviderName.LOCAL
    default_model = "local"

    def is_available(self) -> bool:
        return True

    def complete(self, prompt: str, task_type: TaskType, max_tokens: int = 2048) -> LLMResponse:
        t0 = time.perf_counter()
        text = self._local_extract(prompt, task_type)
        latency = (time.perf_counter() - t0) * 1000

        return LLMResponse(
            text=text,
            provider=ProviderName.LOCAL,
            model="local",
            task_type=task_type,
            latency_ms=round(latency, 1),
            prompt_tokens=estimate_tokens(prompt),
            completion_tokens=estimate_tokens(text),
            total_tokens=estimate_tokens(prompt) + estimate_tokens(text),
            cost_usd=0.0,
        )

    def _local_extract(self, prompt: str, task_type: TaskType) -> str:
        """Keyword-based extraction — no external dependencies."""
        # Extract the transcript portion from the prompt
        transcript_match = re.search(r"Transcript:\s*(.+)$", prompt, re.DOTALL | re.IGNORECASE)
        text = transcript_match.group(1).strip() if transcript_match else prompt

        if task_type == TaskType.SUMMARIZATION:
            sentences = re.split(r'[.!?]', text)
            key = [s.strip() for s in sentences if len(s.strip()) > 30][:3]
            return " ".join(key) or "Meeting transcript processed."

        if task_type in (TaskType.EXTRACTION, TaskType.FALLBACK):
            # Return minimal valid JSON
            action_words = ["will", "should", "must", "need to", "going to", "assigned to"]
            items = []
            for sent in re.split(r'[.!?\n]', text):
                if any(w in sent.lower() for w in action_words) and len(sent.strip()) > 15:
                    items.append({
                        "task": sent.strip()[:200],
                        "assignee": "Unassigned",
                        "deadline": None,
                        "confidence_score": 0.4,
                    })
            import json
            return json.dumps({"summary": "Extracted locally.", "decisions": [], "action_items": items[:5]})

        if task_type == TaskType.SENTIMENT:
            pos = sum(1 for w in ["good","great","agree","done","success"] if w in text.lower())
            neg = sum(1 for w in ["blocked","issue","problem","failed","delay"] if w in text.lower())
            label = "positive" if pos > neg else "negative" if neg > pos else "neutral"
            import json
            return json.dumps({"label": label, "positive": pos*20, "neutral": 40, "negative": neg*20})

        return "Local fallback: no structured output available."
