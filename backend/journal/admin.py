from django.contrib import admin
from .models import (
    JournalEntry, TradingGoal, TradingPlan,
    ChecklistTemplate, TradeChecklist
)


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ['title', 'entry_type', 'user', 'entry_date']
    list_filter = ['entry_type', 'pre_trading_mood']
    search_fields = ['title', 'content', 'user__email']


@admin.register(TradingGoal)
class TradingGoalAdmin(admin.ModelAdmin):
    list_display = ['title', 'goal_type', 'status', 'progress_percentage', 'user']
    list_filter = ['goal_type', 'status']
    search_fields = ['title', 'user__email']


@admin.register(TradingPlan)
class TradingPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_active']
    search_fields = ['name', 'user__email']


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_pre_trade', 'is_post_trade', 'user']
    search_fields = ['name', 'user__email']


@admin.register(TradeChecklist)
class TradeChecklistAdmin(admin.ModelAdmin):
    list_display = ['trade', 'template']
