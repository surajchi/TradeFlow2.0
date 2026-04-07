from django.urls import path
from .views import (
    TradeListCreateView, TradeDetailView, TradeBulkDeleteView,
    TradeStatisticsView, TradeAnalyticsView, TradeImportView,
    StrategyListCreateView, StrategyDetailView, DashboardSummaryView
)

urlpatterns = [
    path('', TradeListCreateView.as_view(), name='trade-list-create'),
    path('<uuid:pk>/', TradeDetailView.as_view(), name='trade-detail'),
    path('bulk-delete/', TradeBulkDeleteView.as_view(), name='trade-bulk-delete'),
    path('statistics/', TradeStatisticsView.as_view(), name='trade-statistics'),
    path('analytics/', TradeAnalyticsView.as_view(), name='trade-analytics'),
    path('import/', TradeImportView.as_view(), name='trade-import'),
    path('strategies/', StrategyListCreateView.as_view(), name='strategy-list'),
    path('strategies/<uuid:pk>/', StrategyDetailView.as_view(), name='strategy-detail'),
    path('dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
]
