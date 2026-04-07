from django.contrib import admin
from .models import PerformanceReport, TradingInsight


@admin.register(PerformanceReport)
class PerformanceReportAdmin(admin.ModelAdmin):
    list_display = ['report_type', 'user', 'net_profit', 'win_rate', 'created_at']
    list_filter = ['report_type']
    search_fields = ['user__email']


@admin.register(TradingInsight)
class TradingInsightAdmin(admin.ModelAdmin):
    list_display = ['insight_type', 'title', 'user', 'impact_score', 'created_at']
    list_filter = ['insight_type', 'is_acknowledged']
    search_fields = ['title', 'user__email']
