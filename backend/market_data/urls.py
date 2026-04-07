from django.urls import path
from .views import (
    # ── Live (no-DB) endpoints ────────────────────────────────────────────────
    LivePricesView,
    LiveNewsView,
    LiveCalendarView,
    LiveOverviewView,
    InvalidateCacheView,

    # ── DB-backed endpoints (legacy / background tasks) ───────────────────────
    MarketNewsListView,
    EconomicCalendarView,
    MarketPricesView,
    InstrumentListView,
    InstrumentDetailView,
    MarketOverviewView,
    FetchMarketDataView,
)

urlpatterns = [
    # ─── Live data (frontend uses these) ─────────────────────────────────────

    # GET  /api/market/live/overview/
    #   One-shot call: forex + indices + crypto + news + calendar.
    #   Cache: prices 30 s, news 5 min, calendar 1 h.
    path("live/overview/",   LiveOverviewView.as_view(),   name="live-market-overview"),

    # GET  /api/market/live/prices/
    #   ?market_type=FOREX|INDICES|CRYPTO|COMMODITIES
    #   ?symbols=EURUSD,GBPUSD
    path("live/prices/",     LivePricesView.as_view(),     name="live-market-prices"),

    # GET  /api/market/live/news/
    #   ?impact=HIGH|MEDIUM|LOW  ?source=FXStreet  ?pair=EURUSD
    path("live/news/",       LiveNewsView.as_view(),       name="live-market-news"),

    # GET  /api/market/live/calendar/
    #   ?days=7  ?impact=HIGH|MEDIUM  ?currency=USD
    path("live/calendar/",   LiveCalendarView.as_view(),   name="live-market-calendar"),

    # POST /api/market/live/invalidate/   (admin only)
    #   Body: { "prices": true, "news": true, "calendar": true }
    path("live/invalidate/", InvalidateCacheView.as_view(), name="live-cache-invalidate"),

    # ─── DB-backed endpoints (legacy / Celery / admin) ────────────────────────

    # GET  /api/market/news/
    path("news/",                   MarketNewsListView.as_view(),  name="market-news"),
    # GET  /api/market/calendar/
    path("calendar/",               EconomicCalendarView.as_view(), name="economic-calendar"),
    # GET  /api/market/prices/
    path("prices/",                 MarketPricesView.as_view(),    name="market-prices"),
    # GET  /api/market/instruments/
    path("instruments/",            InstrumentListView.as_view(),  name="instruments"),
    # GET  /api/market/instruments/<symbol>/
    path("instruments/<str:symbol>/", InstrumentDetailView.as_view(), name="instrument-detail"),
    # GET  /api/market/overview/
    path("overview/",               MarketOverviewView.as_view(),  name="market-overview"),
    # POST /api/market/fetch-data/
    path("fetch-data/",             FetchMarketDataView.as_view(), name="fetch-market-data"),
]