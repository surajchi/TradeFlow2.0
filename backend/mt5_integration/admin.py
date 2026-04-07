from django.contrib import admin
from .models import MT5Account, MT5TradeImport, MT5ConnectionLog, MT5SetupGuide


@admin.register(MT5Account)
class MT5AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'account_number', 'server', 'status', 'user', 'is_active']
    list_filter = ['status', 'is_active', 'is_demo']
    search_fields = ['name', 'account_number', 'user__email']


@admin.register(MT5TradeImport)
class MT5TradeImportAdmin(admin.ModelAdmin):
    list_display = ['account', 'status', 'imported_trades', 'created_at']
    list_filter = ['status']
    search_fields = ['account__name', 'user__email']


@admin.register(MT5ConnectionLog)
class MT5ConnectionLogAdmin(admin.ModelAdmin):
    list_display = ['account', 'log_type', 'created_at']
    list_filter = ['log_type']
    search_fields = ['account__name', 'message']


@admin.register(MT5SetupGuide)
class MT5SetupGuideAdmin(admin.ModelAdmin):
    list_display = ['title', 'order', 'is_active']
    list_editable = ['order', 'is_active']
