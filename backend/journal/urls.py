from django.urls import path
from .views import (
    JournalEntryListCreateView, JournalEntryDetailView,
    TradingGoalListCreateView, TradingGoalDetailView,
    TradingPlanListCreateView, TradingPlanDetailView,
    ChecklistTemplateListCreateView, ChecklistTemplateDetailView,
    TradeChecklistView, JournalSummaryView
)

urlpatterns = [
    path('entries/', JournalEntryListCreateView.as_view(), name='journal-entries'),
    path('entries/<uuid:pk>/', JournalEntryDetailView.as_view(), name='journal-entry-detail'),
    path('goals/', TradingGoalListCreateView.as_view(), name='trading-goals'),
    path('goals/<uuid:pk>/', TradingGoalDetailView.as_view(), name='trading-goal-detail'),
    path('plans/', TradingPlanListCreateView.as_view(), name='trading-plans'),
    path('plans/<uuid:pk>/', TradingPlanDetailView.as_view(), name='trading-plan-detail'),
    path('checklists/templates/', ChecklistTemplateListCreateView.as_view(), name='checklist-templates'),
    path('checklists/templates/<uuid:pk>/', ChecklistTemplateDetailView.as_view(), name='checklist-template-detail'),
    path('checklists/trade/<uuid:trade_id>/', TradeChecklistView.as_view(), name='trade-checklist'),
    path('summary/', JournalSummaryView.as_view(), name='journal-summary'),
]
