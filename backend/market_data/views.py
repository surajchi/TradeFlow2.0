import time
import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MarketNews, EconomicEvent, MarketPrice, Instrument
from .serializers import (
    MarketNewsSerializer, EconomicEventSerializer,
    MarketPriceSerializer, InstrumentSerializer,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  LIVE endpoints  (no DB — data comes directly from upstream via in-memory cache)
# ═══════════════════════════════════════════════════════════════════════════════

class LivePricesView(APIView):
    """
    GET /api/market/live/prices/

    Returns live prices from Yahoo Finance + CoinGecko.
    Server-side cache: 30 s so multiple users don't hammer upstream.

    Query params:
      market_type=FOREX|INDICES|CRYPTO|COMMODITIES  (filter)
      symbols=EURUSD,GBPUSD                         (filter)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .services import LiveMarketService

        market_type = request.query_params.get("market_type", "").upper()
        symbols_raw = request.query_params.get("symbols", "")

        try:
            data = LiveMarketService.get_prices()

            all_prices: list[dict] = (
                data.get("forex",       []) +
                data.get("commodities", []) +
                data.get("indices",     []) +
                data.get("crypto",      [])
            )

            if market_type:
                all_prices = [p for p in all_prices if p.get("market_type") == market_type]
            if symbols_raw:
                sym_list   = [s.strip().upper() for s in symbols_raw.split(",")]
                all_prices = [p for p in all_prices if p.get("symbol") in sym_list]

            fetched_at = data.get("fetched_at", time.time())
            return Response({
                "prices":            all_prices,
                "fetched_at":        fetched_at,
                "cache_age_seconds": round(time.time() - fetched_at, 1),
                "next_refresh_in":   max(0, round(30 - (time.time() - fetched_at), 1)),
            })

        except Exception as exc:
            logger.error("LivePricesView error: %s", exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LiveNewsView(APIView):
    """
    GET /api/market/live/news/

    Returns market news from RSS feeds. Cache: 5 min.

    Query params:
      impact=HIGH|MEDIUM|LOW
      source=FXStreet|ForexLive|Reuters|Investing.com
      pair=EURUSD
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .services import LiveMarketService

        impact = request.query_params.get("impact", "").upper()
        source = request.query_params.get("source", "")
        pair   = request.query_params.get("pair",   "").upper()

        try:
            articles = LiveMarketService.get_news()

            if impact:
                articles = [a for a in articles if a.get("impact") == impact]
            if source:
                articles = [a for a in articles if a.get("source", "").lower() == source.lower()]
            if pair:
                articles = [a for a in articles if pair in (a.get("currency_pairs") or [])]

            age = LiveMarketService.get_news_age()
            return Response({
                "news":              articles[:60],
                "total":             len(articles),
                "cache_age_seconds": round(age, 1),
                "next_refresh_in":   max(0, round(300 - age, 1)),
            })

        except Exception as exc:
            logger.error("LiveNewsView error: %s", exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LiveCalendarView(APIView):
    """
    GET /api/market/live/calendar/

    Returns economic calendar scraped from ForexFactory. Cache: 1 h.

    Query params:
      days=7           (days ahead, max 14)
      impact=HIGH|MEDIUM
      currency=USD
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .services import LiveMarketService

        days     = min(int(request.query_params.get("days", 7)), 14)
        impact   = request.query_params.get("impact",   "").upper()
        currency = request.query_params.get("currency", "").upper()

        try:
            events = LiveMarketService.get_calendar(days_ahead=days)

            if impact:
                events = [e for e in events if e.get("impact") == impact]
            if currency:
                events = [e for e in events if e.get("currency") == currency]

            age = LiveMarketService.get_calendar_age(days_ahead=days)
            return Response({
                "events":            events,
                "total":             len(events),
                "cache_age_seconds": round(age, 1),
                "next_refresh_in":   max(0, round(3600 - age, 1)),
            })

        except Exception as exc:
            logger.error("LiveCalendarView error: %s", exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LiveOverviewView(APIView):
    """
    GET /api/market/live/overview/

    Single endpoint that returns prices + recent news + upcoming calendar.
    Ideal for the dashboard initial load.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .services import LiveMarketService

        try:
            prices_data = LiveMarketService.get_prices()
            news        = LiveMarketService.get_news()
            calendar    = LiveMarketService.get_calendar(days_ahead=3)

            major_pairs = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}
            forex       = [p for p in prices_data.get("forex", []) if p["symbol"] in major_pairs]

            fetched_at = prices_data.get("fetched_at", time.time())
            return Response({
                "forex":             forex,
                "indices":           prices_data.get("indices", []),
                "crypto":            prices_data.get("crypto", [])[:7],
                "commodities":       prices_data.get("commodities", []),
                "recent_news":       news[:15],
                "upcoming_events":   calendar,
                "fetched_at":        fetched_at,
                "cache_age_seconds": round(time.time() - fetched_at, 1),
            })

        except Exception as exc:
            logger.error("LiveOverviewView error: %s", exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InvalidateCacheView(APIView):
    """
    POST /api/market/live/invalidate/

    Forces cache bust so the next request refetches from upstream.
    Useful after a manual data trigger.
    Body: { "prices": true, "news": true, "calendar": true }
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        from .services import LiveMarketService

        def to_bool(val):
            if isinstance(val, bool):
                return val
            return str(val).lower() not in ("false", "0", "no")

        if to_bool(request.data.get("prices", True)):
            LiveMarketService.invalidate_prices()
        if to_bool(request.data.get("news", True)):
            LiveMarketService.invalidate_news()
        if to_bool(request.data.get("calendar", True)):
            LiveMarketService.invalidate_calendar()

        return Response({"status": "cache invalidated"})


# ═══════════════════════════════════════════════════════════════════════════════
#  DB-backed endpoints  (legacy — kept for compatibility)
# ═══════════════════════════════════════════════════════════════════════════════

class MarketNewsListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = MarketNewsSerializer

    def get_queryset(self):
        qs = MarketNews.objects.all()

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        impact = self.request.query_params.get("impact")
        if impact:
            qs = qs.filter(impact=impact.upper())

        pair = self.request.query_params.get("pair")
        if pair:
            qs = qs.filter(currency_pairs__contains=[pair])

        week_ago = timezone.now() - timedelta(days=7)
        qs = qs.filter(published_at__gte=week_ago)
        return qs[:50]


class EconomicCalendarView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = EconomicEventSerializer

    def get_queryset(self):
        qs = EconomicEvent.objects.all()

        date_from = self.request.query_params.get("date_from")
        date_to   = self.request.query_params.get("date_to")

        if date_from:
            qs = qs.filter(event_date__gte=date_from)
        if date_to:
            qs = qs.filter(event_date__lte=date_to)
        else:
            today = timezone.now().date()
            qs    = qs.filter(event_date__gte=today, event_date__lte=today + timedelta(days=7))

        impact = self.request.query_params.get("impact")
        if impact:
            qs = qs.filter(impact=impact.upper())

        currency = self.request.query_params.get("currency")
        if currency:
            qs = qs.filter(currency=currency.upper())

        return qs


class MarketPricesView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = MarketPriceSerializer

    def get_queryset(self):
        qs = MarketPrice.objects.all()

        market_type = self.request.query_params.get("market_type")
        if market_type:
            qs = qs.filter(market_type=market_type.upper())

        symbols = self.request.query_params.get("symbols")
        if symbols:
            qs = qs.filter(symbol__in=symbols.split(","))

        return qs


class InstrumentListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = InstrumentSerializer

    def get_queryset(self):
        from django.db import models as dj_models
        qs = Instrument.objects.filter(is_active=True)

        market_type = self.request.query_params.get("market_type")
        if market_type:
            qs = qs.filter(market_type=market_type.upper())

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                dj_models.Q(symbol__icontains=search) |
                dj_models.Q(name__icontains=search)
            )
        return qs


class InstrumentDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = InstrumentSerializer
    queryset           = Instrument.objects.filter(is_active=True)
    lookup_field       = "symbol"


class MarketOverviewView(APIView):
    """Legacy DB-backed overview — prefer /live/overview/ for fresh data."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        major_pairs = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]

        forex_prices    = MarketPrice.objects.filter(symbol__in=major_pairs, market_type="FOREX")
        indices         = MarketPrice.objects.filter(market_type="INDICES")[:5]
        crypto          = MarketPrice.objects.filter(market_type="CRYPTO")[:5]
        recent_news     = MarketNews.objects.all()[:5]
        today           = timezone.now().date()
        upcoming_events = EconomicEvent.objects.filter(
            event_date__gte=today,
            event_date__lte=today + timedelta(days=3),
        )[:10]

        return Response({
            "forex":           MarketPriceSerializer(forex_prices,     many=True).data,
            "indices":         MarketPriceSerializer(indices,           many=True).data,
            "crypto":          MarketPriceSerializer(crypto,            many=True).data,
            "recent_news":     MarketNewsSerializer(recent_news,        many=True).data,
            "upcoming_events": EconomicEventSerializer(upcoming_events, many=True).data,
        })


class FetchMarketDataView(APIView):
    """
    POST /api/market/fetch-data/
    Triggers a live fetch and saves to DB, then invalidates the live cache.
    Body: { "prices": true, "news": true, "calendar": true }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .services import MarketDataOrchestrator

        def to_bool(val):
            if isinstance(val, bool):
                return val
            return str(val).lower() not in ("false", "0", "no")

        try:
            result = MarketDataOrchestrator.run(
                fetch_prices   = to_bool(request.data.get("prices",   True)),
                fetch_news     = to_bool(request.data.get("news",     True)),
                fetch_calendar = to_bool(request.data.get("calendar", True)),
            )
            return Response({
                "status":  "success",
                "message": "Market data fetched and updated successfully.",
                "details": result,
            })

        except Exception as exc:
            logger.error("FetchMarketDataView error: %s", exc, exc_info=True)
            return Response({"status": "error", "message": str(exc)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)