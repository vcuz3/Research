from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import httpx

from .models import Candidate
from .redact import redact_sensitive


TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    "market_microstructure": ("microstructure", "order book", "limit order", "bid ask", "liquidity", "market impact", "execution", "market making", "market maker"),
    "momentum_trend": ("momentum", "trend following", "time-series momentum", "breakout"),
    "mean_reversion": ("mean reversion", "reversal", "pairs trading", "statistical arbitrage", "cointegration"),
    "strategy": ("sharpe", "Sharpe", "trading", "intraday", "annualized return", "trending", "Alpha", "alpha"),
    "volatility_derivatives": ("volatility", "option", "derivative", "variance risk", "implied volatility"),
    "portfolio_risk": ("portfolio", "asset allocation", "risk parity", "drawdown", "position sizing"),
    "machine_learning": ("machine learning", "neural network", "deep learning", "reinforcement learning", "transformer"),
    "asset_pricing_factors": ("asset pricing", "factor", "cross-sectional", "value premium", "carry trade"),
    "macro_events": ("monetary policy", "macroeconomic", "central bank", "inflation", "interest rate", "event study"),
    "digital_assets": ("bitcoin", "crypto", "digital asset", "blockchain", "defi"),
    "research_methods": ("backtest", "data snooping", "overfitting", "transaction cost", "survivorship", "look-ahead"),
    "event_driven": ("event driven", "earnings announcement", "merger arbitrage", "post-earnings", "market reaction"),
    "alternative_data": ("alternative data", "news sentiment", "textual analysis", "satellite data", "web traffic"),
}

GENERIC_TRADING_TERMS = (
    "trading", "trader", "financial market", "stock return", "futures", "forex", "foreign exchange",
    "equity", "bond", "commodity", "arbitrage", "alpha", "portfolio", "asset pricing", "market return",
)

NEGATIVE_TERMS = (
    "medical", "clinical", "protein", "battery", "traffic routing", "electricity grid",
    "image classification", "speech recognition", "wireless network",
)


def deterministic_classify(candidate: Candidate) -> tuple[int, list[str]]:
    text = f"{candidate.title} {candidate.abstract}".lower()
    topics = [topic for topic, terms in TOPIC_TERMS.items() if any(term in text for term in terms)]
    score = len(topics) * 2 + sum(1 for term in GENERIC_TRADING_TERMS if term in text)
    score -= sum(2 for term in NEGATIVE_TERMS if term in text)
    return score, topics


@dataclass
class AIResult:
    status: str
    accepted: bool | None = None
    relevance_score: float | None = None
    topics: list[str] = field(default_factory=list)
    reason: str = ""
    warning: str | None = None


class ZeroCostOmniRoute:
    """Fail-closed client for one operator-configured free-only OmniRoute route."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.enabled = bool(config.get("enabled"))
        self.base_url = os.getenv(config["base_url_env"], "http://127.0.0.1:20128/v1").rstrip("/")
        self.api_key = os.getenv(config["api_key_env"], "")
        self.model = os.getenv(config["model_env"], "")
        self.calls = 0
        self.estimated_input_tokens = 0
        self.stopped_reason: str | None = None
        required_fragment = config.get("required_model_name_fragment", "free").lower()
        if self.enabled and (not self.model or required_fragment not in self.model.lower()):
            self.stopped_reason = (
                f"AI disabled: {config['model_env']} must name an explicitly free-only route "
                f"containing {required_fragment!r}"
            )

    def classify(self, candidate: Candidate, extracted_text: str) -> AIResult:
        if not self.enabled:
            return AIResult("disabled")
        if self.stopped_reason:
            return AIResult("stopped", warning=self.stopped_reason)
        text = extracted_text[: self.config["max_chars_per_document"]]
        estimated = max(1, len(text) // 4)
        if self.calls >= self.config["max_calls_per_run"]:
            self.stopped_reason = "AI call cap reached; no further documents were sent"
            return AIResult("quota_stopped", warning=self.stopped_reason)
        if self.estimated_input_tokens + estimated > self.config["max_input_tokens_per_run"]:
            self.stopped_reason = "AI input-token cap reached; no further documents were sent"
            return AIResult("quota_stopped", warning=self.stopped_reason)

        prompt = {
            "task": "Assess whether this is useful for trading research or systematic backtesting.",
            "rules": [
                "Accept only if the work offers a plausible tradable signal, execution method, portfolio/risk method, market mechanism, forecast, dataset, or backtesting lesson.",
                "Reject generic corporate finance, banking performance, institutional policy, regulation, investor surveys, and broad literature reviews unless they provide a concrete systematic-trading use.",
                "Reject unrelated routing/optimization, non-financial uses of trading language, and marketing without research substance.",
                "Return JSON only with accepted, relevance_score 0..1, topics, and reason.",
            ],
            "title": candidate.title,
            "abstract": candidate.abstract,
            "document_text": text,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a strict trading-research librarian. Output valid JSON only."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "temperature": 0,
            "max_tokens": self.config["max_output_tokens"],
            "response_format": {"type": "json_object"},
            # OmniRoute can proxy providers that otherwise choose a streaming
            # response. The pipeline expects one OpenAI-compatible JSON object.
            "stream": False,
        }
        self.calls += 1
        self.estimated_input_tokens += estimated
        try:
            response = httpx.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=90)
            if response.status_code in {402, 429}:
                self.stopped_reason = f"OmniRoute returned {response.status_code}; AI stopped to prevent paid fallback or quota overrun"
                return AIResult("quota_stopped", warning=self.stopped_reason)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            parsed = json.loads(match.group(0) if match else content)
            return AIResult(
                status="classified",
                accepted=bool(parsed["accepted"]),
                relevance_score=max(0.0, min(1.0, float(parsed["relevance_score"]))),
                topics=[str(x) for x in parsed.get("topics", [])],
                reason=str(parsed.get("reason", "")),
            )
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
            message = redact_sensitive(exc)
            if isinstance(exc, httpx.TransportError):
                self.stopped_reason = f"OmniRoute is unreachable; AI stopped for this run: {message}"
                return AIResult("stopped", warning=self.stopped_reason)
            if any(term in message.lower() for term in ("quota", "credit", "billing", "payment", "token limit")):
                self.stopped_reason = f"OmniRoute quota/payment warning; AI stopped: {message}"
                return AIResult("quota_stopped", warning=self.stopped_reason)
            return AIResult("error", warning=f"OmniRoute classification failed: {message}")
