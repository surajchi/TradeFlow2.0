from django.urls import path
from .views import (
    MT5AccountListCreateView, MT5AccountDetailView,
    MT5ConnectionTestView, MT5SyncTradesView,
    MT5FileImportView, MT5OpenPositionsView,
    MT5ImportHistoryView, MT5ConnectionLogsView,
    MT5SetupGuideView, MT5DashboardStatsView,
    MT5DisconnectView, MT5ManualImportGuideView,
)

urlpatterns = [
    # ── Accounts ─────────────────────────────────────────────────────────────
    path('accounts/',                              MT5AccountListCreateView.as_view(), name='mt5-accounts'),
    path('accounts/<uuid:pk>/',                    MT5AccountDetailView.as_view(),     name='mt5-account-detail'),
    path('accounts/<uuid:account_id>/disconnect/', MT5DisconnectView.as_view(),        name='mt5-disconnect'),
    path('accounts/<uuid:account_id>/positions/',  MT5OpenPositionsView.as_view(),     name='mt5-positions'),

    # ── Import ────────────────────────────────────────────────────────────────
    path('sync/',          MT5SyncTradesView.as_view(),  name='mt5-sync'),          # Windows direct
    path('import-file/',   MT5FileImportView.as_view(),  name='mt5-import-file'),   # Any OS ← use this on Linux

    # ── Connection ────────────────────────────────────────────────────────────
    path('test-connection/', MT5ConnectionTestView.as_view(), name='mt5-test-connection'),

    # ── History / logs ────────────────────────────────────────────────────────
    path('imports/', MT5ImportHistoryView.as_view(),  name='mt5-imports'),
    path('logs/',    MT5ConnectionLogsView.as_view(), name='mt5-logs'),

    # ── Info ──────────────────────────────────────────────────────────────────
    path('setup-guide/',         MT5SetupGuideView.as_view(),        name='mt5-setup-guide'),
    path('dashboard-stats/',     MT5DashboardStatsView.as_view(),    name='mt5-dashboard-stats'),
    path('manual-import-guide/', MT5ManualImportGuideView.as_view(), name='mt5-manual-import-guide'),
]