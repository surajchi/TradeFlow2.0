"""
analytics/services.py

AI-powered trading insight generation using the Google Gemini API.

Flow:
  1. Collect raw stats from the Trade queryset (pure Python / Django ORM)
  2. Serialize into a compact JSON payload
  3. Ask Gemini to analyse and return structured insights as JSON
  4. Persist each insight to TradingInsight and return the list

No extra paid services — only the Google Generative AI SDK that is already
available in the project environment.
"""

import json
import logging
import os
from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Gemini client (lazy-initialised so import never fails) ────────────────────

_gemini_configured = False

def _configure_gemini():
    global _gemini_configured
    if not _gemini_configured:
        try:
            import google.generativeai as genai  # pip install google-generativeai
            api_key = os.environ.get("GEMINI_API_KEY", "")
            genai.configure(api_key=api_key)
            _gemini_configured = True
        except ImportError:
            raise RuntimeError(
                "google-generativeai package is not installed. "
                "Run: pip install google-generativeai"
            )


# ── Trading statistics collector ──────────────────────────────────────────────

def _collect_trading_stats(trades_qs) -> dict:
    """
    Build a rich statistics dict from a closed-trade queryset.
    Everything here is plain ORM / Python — no AI involved yet.
    """
    trades = list(
        trades_qs.values(
            "id", "symbol", "trade_type", "profit_loss",
            "entry_date", "exit_date",
            "pre_trade_emotion", "post_trade_emotion",
            "setup_type", "timeframe", "risk_reward_ratio",
            "lot_size", "notes", "tags",
        )
    )

    if not trades:
        return {}

    total = len(trades)
    pnls  = [float(t["profit_loss"] or 0) for t in trades]

    wins  = [p for p in pnls if p > 0]
    losses= [p for p in pnls if p <= 0]

    # ── Equity curve + drawdown ───────────────────────────────────────────────
    cumulative = 0.0
    peak       = 0.0
    max_dd_pct = 0.0
    equity_series = []
    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak * 100 if peak > 0 else 0
        if dd > max_dd_pct:
            max_dd_pct = dd
        equity_series.append(round(cumulative, 2))

    # ── Consecutive wins / losses ─────────────────────────────────────────────
    max_consec_w = max_consec_l = cur_w = cur_l = 0
    for pnl in pnls:
        if pnl > 0:
            cur_w += 1; cur_l = 0
        else:
            cur_l += 1; cur_w = 0
        max_consec_w = max(max_consec_w, cur_w)
        max_consec_l = max(max_consec_l, cur_l)

    # ── By symbol ─────────────────────────────────────────────────────────────
    by_symbol: dict[str, list] = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"] or "UNKNOWN"].append(float(t["profit_loss"] or 0))

    symbol_stats = {
        sym: {
            "trades": len(ps),
            "net_pnl": round(sum(ps), 2),
            "win_rate": round(len([p for p in ps if p > 0]) / len(ps) * 100, 1),
            "avg_pnl":  round(sum(ps) / len(ps), 2),
        }
        for sym, ps in by_symbol.items()
    }

    # ── By emotion ────────────────────────────────────────────────────────────
    by_emotion: dict[str, list] = defaultdict(list)
    for t in trades:
        emo = t.get("pre_trade_emotion") or "Unknown"
        by_emotion[emo].append(float(t["profit_loss"] or 0))

    emotion_stats = {
        emo: {
            "trades":   len(ps),
            "net_pnl":  round(sum(ps), 2),
            "win_rate": round(len([p for p in ps if p > 0]) / len(ps) * 100, 1),
        }
        for emo, ps in by_emotion.items()
        if len(ps) >= 3
    }

    # ── By session / hour ─────────────────────────────────────────────────────
    by_hour: dict[int, list] = defaultdict(list)
    for t in trades:
        ed = t.get("entry_date")
        if ed:
            hour = ed.hour if hasattr(ed, "hour") else 0
            by_hour[hour].append(float(t["profit_loss"] or 0))

    hour_stats = {
        f"{h:02d}:00": {
            "trades":   len(ps),
            "avg_pnl":  round(sum(ps) / len(ps), 2),
            "win_rate": round(len([p for p in ps if p > 0]) / len(ps) * 100, 1),
        }
        for h, ps in by_hour.items()
        if len(ps) >= 3
    }

    # ── By setup type ─────────────────────────────────────────────────────────
    by_setup: dict[str, list] = defaultdict(list)
    for t in trades:
        setup = t.get("setup_type") or "Untagged"
        by_setup[setup].append(float(t["profit_loss"] or 0))

    setup_stats = {
        s: {
            "trades":   len(ps),
            "net_pnl":  round(sum(ps), 2),
            "win_rate": round(len([p for p in ps if p > 0]) / len(ps) * 100, 1),
            "avg_pnl":  round(sum(ps) / len(ps), 2),
        }
        for s, ps in by_setup.items()
        if len(ps) >= 3
    }

    # ── By day of week ────────────────────────────────────────────────────────
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_dow: dict[int, list] = defaultdict(list)
    for t in trades:
        ed = t.get("entry_date")
        if ed and hasattr(ed, "weekday"):
            by_dow[ed.weekday()].append(float(t["profit_loss"] or 0))

    dow_stats = {
        day_names[dow]: {
            "trades":   len(ps),
            "net_pnl":  round(sum(ps), 2),
            "win_rate": round(len([p for p in ps if p > 0]) / len(ps) * 100, 1),
        }
        for dow, ps in by_dow.items()
        if len(ps) >= 2
    }

    # ── Risk / reward ─────────────────────────────────────────────────────────
    # FIX: Safely parse risk/reward to avoid ValueError on empty strings ("")
    rr_values = []
    for t in trades:
        rr = t.get("risk_reward_ratio")
        if rr not in (None, ""):
            try:
                rr_values.append(float(rr))
            except (ValueError, TypeError):
                pass # Ignore unparseable values safely

    avg_rr = round(sum(rr_values) / len(rr_values), 2) if rr_values else None

    # ── Overtrading detector (>N trades on same day) ──────────────────────────
    by_date: dict[str, int] = defaultdict(int)
    for t in trades:
        ed = t.get("entry_date")
        if ed:
            key = str(ed.date()) if hasattr(ed, "date") else str(ed)[:10]
            by_date[key] += 1
    overtrade_days = {d: c for d, c in by_date.items() if c >= 5}

    # ── Profit factor ─────────────────────────────────────────────────────────
    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    pf = round(gross_profit / gross_loss, 2) if gross_loss else None

    return {
        "summary": {
            "total_trades":          total,
            "winning_trades":        len(wins),
            "losing_trades":         len(losses),
            "win_rate_pct":          round(len(wins) / total * 100, 1),
            "net_pnl":               round(sum(pnls), 2),
            "gross_profit":          round(gross_profit, 2),
            "gross_loss":            round(gross_loss, 2),
            "profit_factor":         pf,
            "avg_win":               round(sum(wins) / len(wins), 2)    if wins   else 0,
            "avg_loss":              round(sum(losses) / len(losses), 2) if losses else 0,
            "largest_win":           round(max(wins),   2) if wins   else 0,
            "largest_loss":          round(min(losses), 2) if losses else 0,
            "max_consecutive_wins":  max_consec_w,
            "max_consecutive_losses":max_consec_l,
            "max_drawdown_pct":      round(max_dd_pct, 2),
            "avg_risk_reward":       avg_rr,
        },
        "by_symbol":    symbol_stats,
        "by_emotion":   emotion_stats,
        "by_hour":      hour_stats,
        "by_setup":     setup_stats,
        "by_day_of_week": dow_stats,
        "overtrading_days": overtrade_days,   # date → trade count
    }


# ── AI insight generator ──────────────────────────────────────────────────────

_SYSTEM_PROMPT = """
You are an expert quantitative trading coach and psychologist.
You will receive a JSON object containing detailed statistics about a trader's recent performance.
Your job is to analyse the data and generate actionable trading insights.

Return ONLY a valid JSON array. No markdown, no preamble, no explanation outside the JSON.

Each element in the array must be an object with exactly these keys:
{
  "insight_type": one of "PATTERN" | "STRENGTH" | "WEAKNESS" | "MISTAKE" | "IMPROVEMENT",
  "title": a concise title (max 80 chars),
  "description": a clear, actionable description (2-4 sentences, reference specific numbers from the data),
  "metric_name": the primary metric this insight is about (e.g. "win_rate", "avg_pnl", "drawdown"),
  "metric_value": the numeric value of that metric (float or null),
  "impact_score": integer from -100 (very bad) to +100 (very good)
}

Rules:
- Generate between 5 and 10 insights.
- Always cite specific numbers from the data in the description.
- Prioritise HIGH-IMPACT issues first (large drawdowns, emotional trading, overtrading).
- For every WEAKNESS, suggest a concrete corrective action.
- For every STRENGTH, explain how the trader can leverage it more.
- Do NOT invent data that is not in the input.
- If a breakdown (e.g. by_emotion) has fewer than 3 trades, skip it.
""".strip()


def generate_ai_insights(trades_qs) -> list[dict]:
    """
    Build stats from the queryset, call Gemini, return a list of raw insight dicts.
    Raises RuntimeError if the API call fails or returns unparseable JSON.
    """
    stats = _collect_trading_stats(trades_qs)
    if not stats:
        return []

    payload = json.dumps(stats, default=str)

    _configure_gemini()
    import google.generativeai as genai

    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash", 
            system_instruction=_SYSTEM_PROMPT,
        )
        
        # Enforce JSON output for maximum reliability
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            max_output_tokens=2048,
        )

        user_prompt = (
            "Here is my trading performance data for the last 30 days. "
            "Please generate insights:\n\n"
            f"{payload}"
        )

        response = model.generate_content(
            user_prompt,
            generation_config=generation_config
        )
        
        raw_text = response.text.strip()
        
    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc)
        raise RuntimeError(f"AI insight generation failed: {exc}") from exc

    # Strip accidental markdown fences (just in case, though JSON mode usually prevents this)
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        insights = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Gemini returned non-JSON: %s", raw_text[:500])
        raise RuntimeError(f"Could not parse AI response as JSON: {exc}") from exc

    if not isinstance(insights, list):
        raise RuntimeError("Expected a JSON array from AI, got something else.")

    return insights


# ── Persist insights to DB ────────────────────────────────────────────────────

def save_insights(user, raw_insights: list[dict]) -> list:
    """
    Persist a list of raw insight dicts (as returned by generate_ai_insights)
    to the TradingInsight model and return the saved ORM objects.
    """
    from .models import TradingInsight

    # Valid choices from the model
    valid_types = {c[0] for c in TradingInsight.INSIGHT_TYPES}

    saved = []
    for item in raw_insights:
        insight_type = str(item.get("insight_type", "PATTERN")).upper()
        if insight_type not in valid_types:
            insight_type = "PATTERN"

        title       = str(item.get("title", ""))[:200]
        description = str(item.get("description", ""))
        metric_name = str(item.get("metric_name", "") or "")[:100] or None
        impact      = int(item.get("impact_score", 0))
        impact      = max(-100, min(100, impact))

        raw_val = item.get("metric_value")
        try:
            metric_value = float(raw_val) if raw_val is not None else None
        except (TypeError, ValueError):
            metric_value = None

        try:
            obj = TradingInsight.objects.create(
                user=user,
                insight_type=insight_type,
                title=title,
                description=description,
                metric_name=metric_name,
                metric_value=metric_value,
                impact_score=impact,
            )
            saved.append(obj)
        except Exception as exc:
            logger.warning("Failed to save insight '%s': %s", title, exc)

    return saved