"""
LLM Router — Intelligent Multi-Provider Orchestration
======================================================

Routing strategy (in priority order):
  1. Check cache — return immediately if hit
  2. Select primary provider based on task type
  3. Check quota — skip provider if near limit
  4. Call primary provider with timeout
  5. On failure/timeout → try next provider in fallback chain
  6. Score response quality
  7. Detect hallucinations
  8. Record metrics
  9. Cache successful response

Task → Provider routing table:
  summarization  → Gemini 1.5 Pro  (best long-form)
  extraction     → Gemini 1.5 Flash (fast structured JSON)
  reasoning      → GPT-4o           (best logic chains)
  sentiment      → Gemini Flash     (fast)
  classification → Local            (zero cost)
  chat           → GPT-4o-mini      (conversational)
  fallback       → Local            (always available)

Fallback chains:
  Gemini fails  → OpenAI → Local
  OpenAI fails  → Gemini → Local
  All fail      → Local  (guaranteed)
"""

import logging
import os
import threading
import time
from typing import Optional

from backend.services.llm.providers import (
    GeminiProvider, OpenAIProvider, LocalProvider,
    LLMResponse, ProviderName, TaskType, estimate_tokens,
)
from backend.services.llm.cache import get_cached, set_cached, make_cache_key
from backend.services.llm.quality import score_response, detect_hallucinations, rerank_responses
from backend.services.llm.metrics import record_call

logger = logging.getLogger(__name__)

# ── Routing table: task → ordered provider preference ────────────────────────

ROUTING_TABLE: dict[TaskType, list[ProviderName]] = {
    TaskType.SUMMARIZATION:  [ProviderName.GEMINI, ProviderName.OPENAI, ProviderName.LOCAL],
    TaskType.EXTRACTION:     [ProviderName.GEMINI, ProviderName.OPENAI, ProviderName.LOCAL],
    TaskType.REASONING:      [ProviderName.OPENAI, ProviderName.GEMINI, ProviderName.LOCAL],
    TaskType.SENTIMENT:      [ProviderName.GEMINI, ProviderName.LOCAL,  ProviderName.OPENAI],
    TaskType.CLASSIFICATION: [ProviderName.LOCAL,  ProviderName.GEMINI, ProviderName.OPENAI],
    TaskType.CHAT:           [ProviderName.OPENAI, ProviderName.GEMINI, ProviderName.LOCAL],
    TaskType.EMBEDDING:      [ProviderName.GEMINI, ProviderName.LOCAL],
    TaskType.FALLBACK:       [ProviderName.LOCAL,  ProviderName.GEMINI, ProviderName.OPENAI],
}

# ── Timeout per task type (seconds) ──────────────────────────────────────────

TIMEOUTS: dict[TaskType, float] = {
    TaskType.SUMMARIZATION:  45.0,
    TaskType.EXTRACTION:     30.0,
    TaskType.REASONING:      60.0,
    TaskType.SENTIMENT:      15.0,
    TaskType.CLASSIFICATION: 10.0,
    TaskType.CHAT:           20.0,
    TaskType.EMBEDDING:      10.0,
    TaskType.FALLBACK:        5.0,
}

# ── Circuit breaker state ─────────────────────────────────────────────────────

class CircuitBreaker:
    """
    Per-provider circuit breaker.
    Opens after 3 consecutive failures, resets after 60s.
    """
    def __init__(self, threshold: int = 3, reset_secs: float = 60.0):
        self._failures:   dict[ProviderName, int]   = {}
        self._opened_at:  dict[ProviderName, float] = {}
        self._threshold   = threshold
        self._reset_secs  = reset_secs
        self._lock        = threading.Lock()

    def is_open(self, provider: ProviderName) -> bool:
        with self._lock:
            opened = self._opened_at.get(provider)
            if opened and time.time() - opened < self._reset_secs:
                return True
            if opened:
                # Auto-reset
                self._failures[provider]  = 0
                self._opened_at[provider] = None
            return False

    def record_failure(self, provider: ProviderName) -> None:
        with self._lock:
            self._failures[provider] = self._failures.get(provider, 0) + 1
            if self._failures[provider] >= self._threshold:
                self._opened_at[provider] = time.time()
                logger.warning(f"[Router] Circuit breaker OPEN for {provider.value}")

    def record_success(self, provider: ProviderName) -> None:
        with self._lock:
            self._failures[provider]  = 0
            self._opened_at[provider] = None

    def status(self) -> dict:
        return {
            p.value: {
                "failures": self._failures.get(p, 0),
                "open":     self.is_open(p),
            }
            for p in ProviderName
        }


# ── LLM Router ────────────────────────────────────────────────────────────────

class LLMRouter:
    def __init__(self):
        self._providers: dict[ProviderName, object] = {
            ProviderName.GEMINI: GeminiProvider(),
            ProviderName.OPENAI: OpenAIProvider(),
            ProviderName.LOCAL:  LocalProvider(),
        }
        self._breaker = CircuitBreaker()
        self._cache_ttl = int(os.getenv("LLM_CACHE_TTL", "3600"))
        self._enable_cache = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"

    # ── Public API ────────────────────────────────────────────────────────────

    def complete(
        self,
        prompt: str,
        task_type: TaskType,
        source_text: str = "",
        meeting_id: Optional[int] = None,
        user_id: Optional[int] = None,
        max_tokens: int = 2048,
        use_cache: bool = True,
    ) -> LLMResponse:
        """
        Route a prompt to the best available provider.
        Returns the first successful response, with quality scoring.
        """
        # ── Cache check ───────────────────────────────────────────────────
        cache_key = None
        if use_cache and self._enable_cache:
            primary_provider = ROUTING_TABLE.get(task_type, [ProviderName.GEMINI])[0]
            primary_model    = self._providers[primary_provider].default_model
            cache_key = make_cache_key(primary_provider.value, primary_model, task_type.value, prompt)
            cached = get_cached(cache_key)
            if cached:
                resp = LLMResponse(**cached)
                resp.cache_hit = True
                logger.info(f"[Router] Cache hit for {task_type.value}")
                return resp

        # ── Provider chain ────────────────────────────────────────────────
        chain = ROUTING_TABLE.get(task_type, [ProviderName.GEMINI, ProviderName.LOCAL])
        timeout = TIMEOUTS.get(task_type, 30.0)
        provider_chain_log = []
        response = None

        for provider_name in chain:
            provider = self._providers[provider_name]

            # Skip unavailable or circuit-broken providers
            if not provider.is_available():
                logger.debug(f"[Router] {provider_name.value} not available (no API key)")
                continue
            if self._breaker.is_open(provider_name):
                logger.info(f"[Router] {provider_name.value} circuit breaker open — skipping")
                continue

            provider_chain_log.append(provider_name.value)
            logger.info(f"[Router] Trying {provider_name.value} for {task_type.value}")

            # ── Call with timeout ─────────────────────────────────────────
            response = self._call_with_timeout(provider, prompt, task_type, max_tokens, timeout)

            if response.success:
                self._breaker.record_success(provider_name)

                # ── Quality scoring ───────────────────────────────────────
                response.quality_score = score_response(
                    response.text, task_type.value, source_text, prompt
                )

                # ── Hallucination detection ───────────────────────────────
                hall = detect_hallucinations(response.text, source_text or prompt)
                hall_risk = hall["hallucination_risk"]

                # ── Record metrics ────────────────────────────────────────
                record_call(
                    response,
                    meeting_id=meeting_id,
                    user_id=user_id,
                    hallucination_risk=hall_risk,
                    fallback_used=(provider_name != chain[0]),
                    provider_chain="→".join(provider_chain_log),
                )

                # ── Cache successful response ─────────────────────────────
                if cache_key and use_cache and self._enable_cache:
                    from dataclasses import asdict
                    try:
                        set_cached(cache_key, asdict(response), ttl=self._cache_ttl)
                    except Exception:
                        pass  # cache write failure is non-fatal

                logger.info(
                    f"[Router] ✅ {provider_name.value}/{response.model} "
                    f"latency={response.latency_ms}ms quality={response.quality_score} "
                    f"tokens={response.total_tokens} cost=${response.cost_usd}"
                )
                return response

            else:
                # Provider failed
                self._breaker.record_failure(provider_name)
                logger.warning(
                    f"[Router] {provider_name.value} failed: {response.error} — trying next"
                )
                record_call(
                    response,
                    meeting_id=meeting_id,
                    user_id=user_id,
                    fallback_used=True,
                    provider_chain="→".join(provider_chain_log),
                )

        # ── All providers failed — guaranteed local fallback ──────────────
        logger.error(f"[Router] All providers failed for {task_type.value} — using local")
        local = self._providers[ProviderName.LOCAL]
        response = local.complete(prompt, task_type, max_tokens)
        response.quality_score = 0.3
        record_call(response, meeting_id=meeting_id, user_id=user_id, fallback_used=True)
        return response

    def complete_with_rerank(
        self,
        prompt: str,
        task_type: TaskType,
        source_text: str = "",
        n_candidates: int = 2,
        meeting_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> LLMResponse:
        """
        Call multiple providers and return the highest-quality response.
        More expensive but higher accuracy for critical tasks.
        """
        chain = ROUTING_TABLE.get(task_type, [ProviderName.GEMINI])
        candidates = []

        for provider_name in chain[:n_candidates]:
            provider = self._providers[provider_name]
            if not provider.is_available() or self._breaker.is_open(provider_name):
                continue
            timeout = TIMEOUTS.get(task_type, 30.0)
            resp = self._call_with_timeout(provider, prompt, task_type, 2048, timeout)
            if resp.success:
                resp.quality_score = score_response(resp.text, task_type.value, source_text, prompt)
                candidates.append(resp)

        if not candidates:
            return self.complete(prompt, task_type, source_text, meeting_id, user_id)

        ranked = rerank_responses(candidates, task_type.value, source_text, prompt)
        best = ranked[0]
        record_call(best, meeting_id=meeting_id, user_id=user_id)
        return best

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "providers": {
                name.value: {
                    "available":       self._providers[name].is_available(),
                    "circuit_breaker": self._breaker.status()[name.value],
                }
                for name in ProviderName
            },
            "routing_table": {
                task.value: [p.value for p in providers]
                for task, providers in ROUTING_TABLE.items()
            },
            "cache_enabled": self._enable_cache,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _call_with_timeout(
        self,
        provider,
        prompt: str,
        task_type: TaskType,
        max_tokens: int,
        timeout: float,
    ) -> LLMResponse:
        """Call provider in a thread with timeout enforcement."""
        result_holder = [None]
        exc_holder    = [None]

        def _call():
            try:
                result_holder[0] = provider.complete(prompt, task_type, max_tokens)
            except Exception as e:
                exc_holder[0] = e

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            # Timeout — return error response
            logger.warning(f"[Router] {provider.name.value} timed out after {timeout}s")
            return LLMResponse(
                text="", provider=provider.name, model=provider.default_model,
                task_type=task_type, latency_ms=timeout * 1000,
                prompt_tokens=0, completion_tokens=0, total_tokens=0,
                cost_usd=0.0, error=f"Timeout after {timeout}s",
            )

        if exc_holder[0]:
            return LLMResponse(
                text="", provider=provider.name, model=provider.default_model,
                task_type=task_type, latency_ms=0,
                prompt_tokens=0, completion_tokens=0, total_tokens=0,
                cost_usd=0.0, error=str(exc_holder[0]),
            )

        return result_holder[0]


# ── Singleton ─────────────────────────────────────────────────────────────────

_router_instance: Optional[LLMRouter] = None
_router_lock = threading.Lock()


def get_router() -> LLMRouter:
    """Return the global LLMRouter singleton."""
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = LLMRouter()
                logger.info("[Router] LLMRouter initialised")
    return _router_instance
