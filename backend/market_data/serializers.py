from rest_framework import serializers
from .models import MarketNews, EconomicEvent, MarketPrice, Instrument


class MarketNewsSerializer(serializers.ModelSerializer):
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = MarketNews
        fields = [
            'id', 'title', 'content', 'summary', 'source',
            'source_url', 'category', 'currency_pairs',
            'impact', 'published_at', 'time_ago'
        ]
    
    def get_time_ago(self, obj):
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        diff = now - obj.published_at
        
        if diff < timedelta(minutes=1):
            return 'Just now'
        elif diff < timedelta(hours=1):
            minutes = int(diff.seconds / 60)
            return f'{minutes}m ago'
        elif diff < timedelta(days=1):
            hours = int(diff.seconds / 3600)
            return f'{hours}h ago'
        else:
            days = diff.days
            return f'{days}d ago'


class EconomicEventSerializer(serializers.ModelSerializer):
    time_until = serializers.SerializerMethodField()
    
    class Meta:
        model = EconomicEvent
        fields = [
            'id', 'title', 'country', 'currency', 'event_type',
            'impact', 'event_date', 'event_time', 'forecast',
            'previous', 'actual', 'time_until'
        ]
    
    def get_time_until(self, obj):
        from django.utils import timezone
        from datetime import datetime, timedelta
        
        if obj.event_time:
            event_datetime = datetime.combine(obj.event_date, obj.event_time)
        else:
            event_datetime = datetime.combine(obj.event_date, datetime.min.time())
        
        now = timezone.now()
        diff = event_datetime - now.replace(tzinfo=None)
        
        if diff.total_seconds() < 0:
            return 'Passed'
        
        days = diff.days
        hours = int(diff.seconds / 3600)
        minutes = int((diff.seconds % 3600) / 60)
        
        if days > 0:
            return f'{days}d {hours}h'
        elif hours > 0:
            return f'{hours}h {minutes}m'
        else:
            return f'{minutes}m'


class MarketPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketPrice
        fields = [
            'id', 'symbol', 'market_type', 'bid', 'ask',
            'spread', 'change', 'change_percentage',
            'high_24h', 'low_24h', 'timestamp'
        ]


class InstrumentSerializer(serializers.ModelSerializer):
    current_price = serializers.SerializerMethodField()
    
    class Meta:
        model = Instrument
        fields = [
            'id', 'symbol', 'name', 'market_type', 'description',
            'base_currency', 'quote_currency', 'pip_value',
            'contract_size', 'min_lot_size', 'max_lot_size',
            'session_open', 'session_close', 'is_active',
            'current_price'
        ]
    
    def get_current_price(self, obj):
        try:
            price = MarketPrice.objects.get(symbol=obj.symbol)
            return {
                'bid': float(price.bid),
                'ask': float(price.ask),
                'change_percentage': float(price.change_percentage)
            }
        except MarketPrice.DoesNotExist:
            return None
