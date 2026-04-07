from django.contrib import admin
from .models import Trade, TradeImport, Strategy


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = [
        'symbol', 'trade_type', 'entry_date', 'exit_date',
        'profit_loss', 'status', 'user', 'strategy'
    ]
    list_filter = [
        'trade_type', 'status', 'market_type', 'strategy',
        'pre_trade_emotion', 'timeframe'
    ]
    search_fields = ['symbol', 'user__email', 'notes']
    date_hierarchy = 'entry_date'
    ordering = ['-entry_date']


@admin.register(TradeImport)
class TradeImportAdmin(admin.ModelAdmin):
    list_display = ['source', 'status', 'user', 'total_trades', 'created_at']
    list_filter = ['source', 'status']
    search_fields = ['user__email', 'mt5_server']


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'win_rate', 'profit_factor', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'user__email']