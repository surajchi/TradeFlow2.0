from django.contrib import admin
from .models import MarketNews, EconomicEvent, MarketPrice, Instrument


@admin.register(MarketNews)
class MarketNewsAdmin(admin.ModelAdmin):
    list_display = ['title', 'source', 'impact', 'published_at']
    list_filter = ['impact', 'category', 'source']
    search_fields = ['title', 'content']


@admin.register(EconomicEvent)
class EconomicEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'country', 'event_date', 'impact']
    list_filter = ['impact', 'event_type', 'country']
    search_fields = ['title']
    date_hierarchy = 'event_date'


@admin.register(MarketPrice)
class MarketPriceAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'bid', 'ask', 'change_percentage', 'timestamp']
    list_filter = ['market_type']
    search_fields = ['symbol']


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'name', 'market_type', 'is_active']
    list_filter = ['market_type', 'is_active']
    search_fields = ['symbol', 'name']
