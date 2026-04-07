"""
Free market data services — LIVE mode (in-memory cache, no DB writes for live data).

Cache TTLs:
  Prices   → 30 s   (yfinance is ~2 s per call; server-side cache prevents hammering)
  News     → 5 min
  Calendar → 1 h    (ForexFactory events change slowly)

Sources:
  Yahoo Finance         → Forex + Commodities + Indices (no key)
  CoinGecko             → Crypto                        (no key)
  RSS Feeds             → News                          (FXStreet, ForexLive, Reuters, Investing.com)
  nfs.faireconomy.media → Economic calendar (ForexFactory JSON feed, no key, no scraping)
"""

import logging
import math
import re
import threading
import time
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

import feedparser
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from django.utils import timezone

logger = logging.getLogger(__name__)

# ─── Symbol maps ──────────────────────────────────────────────────────────────

FOREX_SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X",
    "EURGBP": "EURGBP=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "USOIL":  "CL=F",
}

CRYPTO_IDS = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
    "BNBUSD": "binancecoin",
    "XRPUSD": "ripple",
    "ADAUSD": "cardano",
    "SOLUSD": "solana",
    "DOTUSD": "polkadot",
}

INDICES_SYMBOLS = {
    "SPX500":  "^GSPC",
    "NASDAQ":  "^IXIC",
    "DOW30":   "^DJI",
    "FTSE100": "^FTSE",
    "DAX":     "^GDAXI",
    "NIKKEI":  "^N225",
}

NEWS_RSS_FEEDS = [
    {"url": "https://www.fxstreet.com/rss/news",              "source": "FXStreet"},
    {"url": "https://www.forexlive.com/feed/news",            "source": "ForexLive"},
    {"url": "https://feeds.reuters.com/reuters/businessNews", "source": "Reuters"},
    {"url": "https://www.investing.com/rss/news_25.rss",      "source": "Investing.com"},
]

CURRENCY_KEYWORDS = {
    "USD": ["dollar", "fed", "federal reserve", "usd", "us economy"],
    "EUR": ["euro", "ecb", "european central bank", "eur", "eurozone"],
    "GBP": ["pound", "boe", "bank of england", "gbp", "sterling"],
    "JPY": ["yen", "boj", "bank of japan", "jpy", "japan"],
    "AUD": ["aussie", "rba", "reserve bank of australia", "aud"],
    "CAD": ["loonie", "boc", "bank of canada", "cad"],
    "CHF": ["franc", "snb", "swiss national bank", "chf"],
    "NZD": ["kiwi", "rbnz", "reserve bank of new zealand", "nzd"],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ─── In-memory live cache ─────────────────────────────────────────────────────

_live_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def _cache_get(key: str):
    """Return cached value or None if missing / expired."""
    with _cache_lock:
        entry = _live_cache.get(key)
        if not entry:
            return None
        if time.time() - entry["ts"] > entry["ttl"]:
            return None
        return entry["data"]


def _cache_set(key: str, data, ttl: int):
    with _cache_lock:
        _live_cache[key] = {"data": data, "ts": time.time(), "ttl": ttl}


def _cache_age(key: str) -> float:
    """Seconds since last cache fill, or infinity if not cached."""
    with _cache_lock:
        entry = _live_cache.get(key)
        if not entry:
            return float("inf")
        return time.time() - entry["ts"]


# ─── Serialization helper ─────────────────────────────────────────────────────

def _to_serializable(obj):
    """Recursively convert Decimal / date / time → JSON-safe primitives."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if hasattr(obj, "strftime"):            # time objects
        return obj.strftime("%H:%M:%S")
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(i) for i in obj]
    return obj


# ─── Helper ───────────────────────────────────────────────────────────────────

def safe_decimal(value, fallback=None, places=5):
    try:
        if value is None:
            return fallback
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return fallback
        return Decimal(str(round(f, places)))
    except (TypeError, ValueError, InvalidOperation):
        return fallback


# ─── Forex + Commodities via Yahoo Finance ────────────────────────────────────

class ForexService:

    @staticmethod
    def fetch_prices() -> list[dict]:
        results = []
        tickers_list = list(FOREX_SYMBOLS.values())

        try:
            data = yf.download(
                tickers_list,
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
            )
        except Exception as exc:
            logger.error("yfinance forex download failed: %s", exc)
            return results

        for symbol, yf_ticker in FOREX_SYMBOLS.items():
            try:
                df = data[yf_ticker] if len(tickers_list) > 1 else data
                df = df.dropna(subset=["Close"])
                if df.empty:
                    continue

                latest  = df.iloc[-1]
                prev    = df.iloc[-2] if len(df) >= 2 else latest
                close   = float(latest["Close"])
                prev_cl = float(prev["Close"])

                if math.isnan(close):
                    continue

                change     = close - prev_cl if not math.isnan(prev_cl) else 0.0
                change_pct = (change / prev_cl * 100) if prev_cl else 0.0

                pip    = 0.01 if "JPY" in symbol else 0.0001
                spread = 2 * pip
                bid    = round(close - spread / 2, 5)
                ask    = round(close + spread / 2, 5)

                mtype = "COMMODITIES" if symbol in ("XAUUSD", "XAGUSD", "USOIL") else "FOREX"

                results.append({
                    "symbol":            symbol,
                    "market_type":       mtype,
                    "bid":               float(round(bid, 5)),
                    "ask":               float(round(ask, 5)),
                    "spread":            float(round(ask - bid, 5)),
                    "change":            float(round(change, 5)),
                    "change_percentage": float(round(change_pct, 4)),
                    "high_24h":          float(round(float(latest.get("High", close)), 5)) if latest.get("High") else None,
                    "low_24h":           float(round(float(latest.get("Low",  close)), 5)) if latest.get("Low")  else None,
                })

            except Exception as exc:
                logger.warning("Error processing forex %s: %s", symbol, exc)

        return results


# ─── Indices via Yahoo Finance ────────────────────────────────────────────────

class IndicesService:

    @staticmethod
    def fetch_prices() -> list[dict]:
        results = []
        tickers_list = list(INDICES_SYMBOLS.values())

        try:
            data = yf.download(
                tickers_list,
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
            )
        except Exception as exc:
            logger.error("yfinance indices download failed: %s", exc)
            return results

        for symbol, yf_ticker in INDICES_SYMBOLS.items():
            try:
                df = data[yf_ticker] if len(tickers_list) > 1 else data
                df = df.dropna(subset=["Close"])
                if df.empty:
                    continue

                latest  = df.iloc[-1]
                prev    = df.iloc[-2] if len(df) >= 2 else latest
                close   = float(latest["Close"])
                prev_cl = float(prev["Close"])

                if math.isnan(close):
                    continue

                change     = close - prev_cl if not math.isnan(prev_cl) else 0.0
                change_pct = (change / prev_cl * 100) if prev_cl else 0.0

                bid = round(close - 0.25, 2)
                ask = round(close + 0.25, 2)

                results.append({
                    "symbol":            symbol,
                    "market_type":       "INDICES",
                    "bid":               float(bid),
                    "ask":               float(ask),
                    "spread":            0.50,
                    "change":            float(round(change, 2)),
                    "change_percentage": float(round(change_pct, 4)),
                    "high_24h":          float(round(float(latest.get("High", close)), 2)) if latest.get("High") else None,
                    "low_24h":           float(round(float(latest.get("Low",  close)), 2)) if latest.get("Low")  else None,
                })

            except Exception as exc:
                logger.warning("Error processing index %s: %s", symbol, exc)

        return results


# ─── Crypto via CoinGecko ─────────────────────────────────────────────────────

class CryptoService:
    BASE_URL = "https://api.coingecko.com/api/v3"

    @classmethod
    def fetch_prices(cls) -> list[dict]:
        ids    = ",".join(CRYPTO_IDS.values())
        url    = f"{cls.BASE_URL}/simple/price"
        params = {
            "ids":                 ids,
            "vs_currencies":       "usd",
            "include_24hr_change": "true",
            "include_24hr_vol":    "false",
            "include_last_updated_at": "true",
        }

        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("CoinGecko request failed: %s", exc)
            return []

        results      = []
        id_to_symbol = {v: k for k, v in CRYPTO_IDS.items()}

        for coin_id, coin_data in data.items():
            symbol = id_to_symbol.get(coin_id)
            if not symbol:
                continue

            price      = float(coin_data.get("usd", 0) or 0)
            change_pct = float(coin_data.get("usd_24h_change", 0) or 0)

            if math.isnan(price) or price <= 0:
                continue

            change = price * change_pct / 100
            bid    = round(price * 0.9995, 2)
            ask    = round(price * 1.0005, 2)

            results.append({
                "symbol":            symbol,
                "market_type":       "CRYPTO",
                "bid":               float(bid),
                "ask":               float(ask),
                "spread":            float(round(ask - bid, 2)),
                "change":            float(round(change, 2)),
                "change_percentage": float(round(change_pct, 4)),
                "high_24h":          None,
                "low_24h":           None,
            })

        return results


# ─── News helpers ─────────────────────────────────────────────────────────────

def _detect_currency_pairs(text: str) -> list[str]:
    text_lower = text.lower()
    detected   = [c for c, kws in CURRENCY_KEYWORDS.items()
                  if any(kw in text_lower for kw in kws)]
    pairs = []
    for i, c1 in enumerate(detected):
        for c2 in detected[i + 1:]:
            pairs.append(f"{c1}{c2}")

    explicit = re.findall(
        r'\b(EUR|GBP|USD|JPY|AUD|CAD|CHF|NZD)[/\-]?(EUR|GBP|USD|JPY|AUD|CAD|CHF|NZD)\b',
        text.upper(),
    )
    for p in explicit:
        pair = "".join(p)
        if pair not in pairs and p[0] != p[1]:
            pairs.append(pair)

    return list(set(pairs))[:5]


def _detect_impact(title: str, summary: str) -> str:
    text    = (title + " " + summary).lower()
    high_kw = [
        "fed", "federal reserve", "rate decision", "interest rate",
        "nonfarm", "non-farm", "gdp", "inflation", "cpi", "ecb",
        "boe", "boj", "emergency", "crisis", "crash", "recession",
    ]
    med_kw  = [
        "employment", "trade balance", "retail sales", "pmi",
        "manufacturing", "consumer confidence", "earnings",
    ]
    if any(kw in text for kw in high_kw):
        return "HIGH"
    if any(kw in text for kw in med_kw):
        return "MEDIUM"
    return "LOW"


# ─── News Service ─────────────────────────────────────────────────────────────

class NewsService:
    """Fetches market news from RSS feeds. Two modes:
       fetch_news()      → DB-backed (deduplicates, saves to MarketNews model)
       fetch_news_live() → pure in-memory, no DB interaction
    """

    @classmethod
    def fetch_news_live(cls, max_per_feed: int = 15) -> list[dict]:
        """Fetch news without any DB interaction. Used by LiveMarketService."""
        articles = []

        for feed_cfg in NEWS_RSS_FEEDS:
            try:
                feed   = feedparser.parse(feed_cfg["url"])
                source = feed_cfg["source"]

                for entry in feed.entries[:max_per_feed]:
                    title   = entry.get("title", "").strip()[:500]
                    summary = entry.get("summary", "").strip()
                    blocks  = entry.get("content", [])
                    content = blocks[0].get("value", summary) if blocks else summary
                    link    = entry.get("link", "")

                    if content:
                        soup    = BeautifulSoup(content, "html.parser")
                        content = soup.get_text(separator=" ", strip=True)[:3000]

                    published_at = timezone.now()
                    if entry.get("published_parsed"):
                        try:
                            published_at = datetime(
                                *entry.published_parsed[:6],
                                tzinfo=timezone.utc,
                            )
                        except Exception:
                            pass

                    articles.append({
                        "id":             (entry.get("id") or link or title)[:200],
                        "title":          title,
                        "content":        content or summary,
                        "summary":        summary[:1500] if summary else "",
                        "source":         source,
                        "source_url":     link,
                        "currency_pairs": _detect_currency_pairs(title + " " + summary),
                        "impact":         _detect_impact(title, summary),
                        "category":       "Market News",
                        "published_at":   published_at.isoformat(),
                    })

            except Exception as exc:
                logger.warning("RSS feed error (%s): %s", feed_cfg["source"], exc)

        # Sort newest first
        articles.sort(key=lambda x: x["published_at"], reverse=True)
        logger.info("NewsService live: %d articles fetched", len(articles))
        return articles

    @classmethod
    def fetch_news(cls, max_per_feed: int = 15) -> list[dict]:
        """DB-backed fetch (used by management command / Celery tasks)."""
        from .models import MarketNews

        all_news = []
        seen_ids = set(MarketNews.objects.values_list("external_id", flat=True))

        for feed_cfg in NEWS_RSS_FEEDS:
            try:
                feed   = feedparser.parse(feed_cfg["url"])
                source = feed_cfg["source"][:95]

                for entry in feed.entries[:max_per_feed]:
                    external_id = (entry.get("id") or entry.get("link", ""))[:100]
                    if not external_id or external_id in seen_ids:
                        continue

                    title   = entry.get("title", "").strip()[:500]
                    summary = entry.get("summary", "").strip()
                    blocks  = entry.get("content", [])
                    content = blocks[0].get("value", summary) if blocks else summary
                    link    = entry.get("link", "")[:500]

                    if content:
                        soup    = BeautifulSoup(content, "html.parser")
                        content = soup.get_text(separator=" ", strip=True)[:2000]

                    published_at = timezone.now()
                    if entry.get("published_parsed"):
                        try:
                            published_at = datetime(
                                *entry.published_parsed[:6],
                                tzinfo=timezone.utc,
                            )
                        except Exception:
                            pass

                    all_news.append({
                        "external_id":    external_id,
                        "title":          title,
                        "content":        content or summary,
                        "summary":        summary[:1000] if summary else None,
                        "source":         source,
                        "source_url":     link,
                        "currency_pairs": _detect_currency_pairs(title + " " + summary),
                        "impact":         _detect_impact(title, summary),
                        "category":       "Market News",
                        "published_at":   published_at,
                    })
                    seen_ids.add(external_id)

            except Exception as exc:
                logger.warning("RSS feed error (%s): %s", feed_cfg["source"], exc)

        return all_news


# ─── Economic Calendar via ForexFactory JSON feed ─────────────────────────────
#
#  FIX: The old approach scraped ForexFactory HTML pages, which triggers
#  Cloudflare bot protection and returns HTTP 403.
#
#  Solution: Use the unofficial ForexFactory JSON feed served by
#  nfs.faireconomy.media — the same data, no scraping, no bot blocks.
#
#  Endpoints:
#    https://nfs.faireconomy.media/ff_calendar_thisweek.json
#    https://nfs.faireconomy.media/ff_calendar_nextweek.json
#
#  Sample record:
#    {
#      "title":    "Nonfarm Payrolls",
#      "country":  "USD",
#      "date":     "2026-04-05T00:00:00-04:00",
#      "impact":   "High",           # High | Medium | Low | Holiday
#      "forecast": "190K",
#      "previous": "275K",
#      "actual":   null
#    }
# ─────────────────────────────────────────────────────────────────────────────

class EconomicCalendarService:

    # JSON feed endpoints — no scraping, no Cloudflare
    THISWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    NEXTWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

    IMPACT_MAP = {
        "high":    "HIGH",
        "medium":  "MEDIUM",
        "low":     "LOW",
        "holiday": "LOW",
    }

    CURRENCY_COUNTRY_MAP = {
        "USD": "United States", "EUR": "European Union",
        "GBP": "United Kingdom", "JPY": "Japan",
        "AUD": "Australia",      "CAD": "Canada",
        "CHF": "Switzerland",    "NZD": "New Zealand",
        "CNY": "China",          "INR": "India",
    }

    EVENT_TYPE_MAP = {
        "gdp": "GDP", "gross domestic": "GDP",
        "unemployment": "EMPLOYMENT", "employment": "EMPLOYMENT",
        "nonfarm": "EMPLOYMENT", "non-farm": "EMPLOYMENT",
        "payroll": "EMPLOYMENT", "jobs": "EMPLOYMENT",
        "cpi": "INFLATION", "inflation": "INFLATION", "pce": "INFLATION",
        "rate decision": "INTEREST_RATE", "interest rate": "INTEREST_RATE", "fomc": "INTEREST_RATE",
        "retail": "RETAIL_SALES",
        "pmi": "MANUFACTURING", "manufacturing": "MANUFACTURING", "industrial": "MANUFACTURING",
        "trade balance": "TRADE_BALANCE", "current account": "TRADE_BALANCE",
        "consumer confidence": "CONSUMER_CONFIDENCE", "sentiment": "CONSUMER_CONFIDENCE",
    }

    @classmethod
    def _detect_event_type(cls, title: str) -> str:
        t = title.lower()
        for keyword, etype in cls.EVENT_TYPE_MAP.items():
            if keyword in t:
                return etype
        return "OTHER"

    @classmethod
    def _fetch_json_feed(cls, url: str) -> list[dict]:
        """Fetch one of the JSON calendar feeds and return raw list."""
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Calendar JSON feed fetch failed (%s): %s", url, exc)
            return []

    @classmethod
    def _parse_record(cls, record: dict) -> dict | None:
        """
        Convert a raw JSON record into our internal event dict.
        Returns None if the record should be skipped (e.g. holiday, bad data).
        """
        title    = (record.get("title") or "").strip()[:200]
        currency = (record.get("country") or "").strip().upper()[:3]
        impact   = cls.IMPACT_MAP.get((record.get("impact") or "").lower(), "LOW")

        if not title or not currency or len(currency) != 3:
            return None

        # The 'date' field is an ISO-8601 string like "2026-04-07T08:30:00-04:00"
        raw_date = record.get("date") or ""
        event_date = date.today()
        event_time = None
        try:
            dt = datetime.fromisoformat(raw_date)
            event_date = dt.date()
            # Store time in UTC
            if dt.tzinfo is not None:
                import datetime as _dt
                dt_utc = dt.astimezone(_dt.timezone.utc)
                event_time = dt_utc.strftime("%H:%M:%S")
            else:
                event_time = dt.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            pass

        def clean(v) -> str | None:
            if v is None:
                return None
            s = str(v).strip()
            return s if s not in ("", "\xa0", "—", "-", "null") else None

        return {
            "title":      title,
            "currency":   currency,
            "country":    cls.CURRENCY_COUNTRY_MAP.get(currency, currency),
            "event_type": cls._detect_event_type(title),
            "impact":     impact,
            "event_date": event_date.isoformat(),
            "event_time": event_time,
            "forecast":   clean(record.get("forecast")),
            "previous":   clean(record.get("previous")),
            "actual":     clean(record.get("actual")),
            "source":     "ForexFactory",
        }

    @classmethod
    def fetch_calendar(cls, days_ahead: int = 7) -> list[dict]:
        """
        Fetch economic calendar events for today + days_ahead days.

        Uses two JSON feeds (this week / next week) so we never need to
        scrape HTML or worry about Cloudflare blocking.
        """
        today      = date.today()
        cutoff     = today + timedelta(days=days_ahead)
        all_events: list[dict] = []

        # Always fetch this week; add next week if the window extends past Sunday
        feeds = [cls.THISWEEK_URL]
        days_until_sunday = 6 - today.weekday()          # Mon=0 … Sun=6
        if days_ahead > days_until_sunday:
            feeds.append(cls.NEXTWEEK_URL)

        for url in feeds:
            raw_records = cls._fetch_json_feed(url)
            for record in raw_records:
                ev = cls._parse_record(record)
                if ev is None:
                    continue

                # Filter to the requested date window
                try:
                    ev_date = date.fromisoformat(ev["event_date"])
                except ValueError:
                    continue

                if ev_date < today or ev_date > cutoff:
                    continue

                all_events.append(ev)

        # Deduplicate by (title, currency, event_date) in case feeds overlap
        seen: set[tuple] = set()
        unique_events: list[dict] = []
        for ev in all_events:
            key = (ev["title"], ev["currency"], ev["event_date"])
            if key not in seen:
                seen.add(key)
                unique_events.append(ev)

        # Sort chronologically
        unique_events.sort(key=lambda e: (e["event_date"], e["event_time"] or ""))

        logger.info(
            "EconomicCalendarService: %d events fetched (%d days ahead)",
            len(unique_events), days_ahead,
        )
        return unique_events


# ─── LIVE Market Service (primary interface for API views) ────────────────────

class LiveMarketService:
    """
    Returns market data from in-memory cache.
    On cache miss (or expiry) fetches fresh data from upstream sources.
    No database reads or writes.
    """

    PRICES_TTL   = 30      # seconds
    NEWS_TTL     = 300     # 5 minutes
    CALENDAR_TTL = 3600    # 1 hour

    # ── Prices ────────────────────────────────────────────────────────────────

    @classmethod
    def get_prices(cls) -> dict:
        cached = _cache_get("live_prices")
        if cached is not None:
            return cached

        forex      = ForexService.fetch_prices()
        indices    = IndicesService.fetch_prices()
        crypto     = CryptoService.fetch_prices()

        result = {
            "forex":      [p for p in forex   if p["market_type"] == "FOREX"],
            "commodities":[p for p in forex   if p["market_type"] == "COMMODITIES"],
            "indices":    indices,
            "crypto":     crypto,
            "fetched_at": time.time(),
        }
        _cache_set("live_prices", result, cls.PRICES_TTL)
        logger.info(
            "LiveMarketService prices refreshed — forex:%d indices:%d crypto:%d",
            len(result["forex"]), len(result["indices"]), len(result["crypto"]),
        )
        return result

    @classmethod
    def get_prices_age(cls) -> float:
        return _cache_age("live_prices")

    # ── News ──────────────────────────────────────────────────────────────────

    @classmethod
    def get_news(cls) -> list[dict]:
        cached = _cache_get("live_news")
        if cached is not None:
            return cached

        articles = NewsService.fetch_news_live()
        _cache_set("live_news", articles, cls.NEWS_TTL)
        return articles

    @classmethod
    def get_news_age(cls) -> float:
        return _cache_age("live_news")

    # ── Calendar ──────────────────────────────────────────────────────────────

    @classmethod
    def get_calendar(cls, days_ahead: int = 7) -> list[dict]:
        cache_key = f"live_calendar_{days_ahead}"
        cached    = _cache_get(cache_key)
        if cached is not None:
            return cached

        events = EconomicCalendarService.fetch_calendar(days_ahead=days_ahead)
        _cache_set(cache_key, events, cls.CALENDAR_TTL)
        return events

    @classmethod
    def get_calendar_age(cls, days_ahead: int = 7) -> float:
        return _cache_age(f"live_calendar_{days_ahead}")

    # ── Invalidation helpers (e.g. called by Celery tasks) ───────────────────

    @classmethod
    def invalidate_prices(cls):
        with _cache_lock:
            _live_cache.pop("live_prices", None)

    @classmethod
    def invalidate_news(cls):
        with _cache_lock:
            _live_cache.pop("live_news", None)

    @classmethod
    def invalidate_calendar(cls, days_ahead: int = 7):
        with _cache_lock:
            _live_cache.pop(f"live_calendar_{days_ahead}", None)


# ─── Orchestrator (used by management command + Celery) ───────────────────────

class MarketDataOrchestrator:
    """DB-backed orchestrator. Keeps the management command / Celery tasks working."""

    @staticmethod
    def update_prices() -> dict:
        from .models import MarketPrice

        counts  = {"forex": 0, "indices": 0, "crypto": 0}
        forex   = ForexService.fetch_prices()
        indices = IndicesService.fetch_prices()
        crypto  = CryptoService.fetch_prices()

        for price in forex:
            mtype  = price.pop("market_type")
            symbol = price.pop("symbol")
            # Convert float back to Decimal for the model
            for k in ("bid","ask","spread","change","change_percentage","high_24h","low_24h"):
                if price.get(k) is not None:
                    price[k] = Decimal(str(price[k]))
            MarketPrice.objects.update_or_create(symbol=symbol, market_type=mtype, defaults=price)
            counts["forex"] += 1

        for price in indices:
            mtype  = price.pop("market_type")
            symbol = price.pop("symbol")
            for k in ("bid","ask","spread","change","change_percentage","high_24h","low_24h"):
                if price.get(k) is not None:
                    price[k] = Decimal(str(price[k]))
            MarketPrice.objects.update_or_create(symbol=symbol, market_type=mtype, defaults=price)
            counts["indices"] += 1

        for price in crypto:
            mtype  = price.pop("market_type")
            symbol = price.pop("symbol")
            for k in ("bid","ask","spread","change","change_percentage"):
                if price.get(k) is not None:
                    price[k] = Decimal(str(price[k]))
            MarketPrice.objects.update_or_create(symbol=symbol, market_type=mtype, defaults=price)
            counts["crypto"] += 1

        # Also invalidate the live cache so fresh data is served next request
        LiveMarketService.invalidate_prices()
        return counts

    @staticmethod
    def update_news() -> int:
        from .models import MarketNews

        articles = NewsService.fetch_news()
        saved    = 0
        for article in articles:
            try:
                MarketNews.objects.get_or_create(
                    external_id=article["external_id"],
                    defaults={k: v for k, v in article.items() if k != "external_id"},
                )
                saved += 1
            except Exception as exc:
                logger.warning("Failed to save article: %s", exc)

        LiveMarketService.invalidate_news()
        return saved

    @staticmethod
    def update_calendar(days_ahead: int = 7) -> int:
        from .models import EconomicEvent

        events = EconomicCalendarService.fetch_calendar(days_ahead=days_ahead)
        saved  = 0
        for ev in events:
            try:
                EconomicEvent.objects.update_or_create(
                    title=ev["title"],
                    event_date=ev["event_date"],
                    currency=ev["currency"],
                    defaults={k: v for k, v in ev.items()
                              if k not in ("title", "event_date", "currency")},
                )
                saved += 1
            except Exception as exc:
                logger.warning("Failed to save event: %s", exc)

        LiveMarketService.invalidate_calendar(days_ahead)
        return saved

    @classmethod
    def run(cls, fetch_prices=True, fetch_news=True, fetch_calendar=True) -> dict:
        result = {}
        if fetch_prices:   result["prices"]   = cls.update_prices()
        if fetch_news:     result["news"]      = cls.update_news()
        if fetch_calendar: result["calendar"]  = cls.update_calendar()
        return result