from rest_framework import serializers
from .models import Trade, TradeImport, Strategy


class TradeSerializer(serializers.ModelSerializer):
    profit_loss_formatted = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    
    class Meta:
        model = Trade
        fields = [
            'id', 'symbol', 'trade_type', 'market_type', 'entry_price',
            'entry_date', 'exit_price', 'exit_date', 'position_size',
            'stop_loss', 'take_profit', 'profit_loss', 'profit_loss_pips',
            'profit_loss_percentage', 'risk_reward_ratio', 'risk_amount',
            'timeframe', 'strategy', 'setup_type', 'pre_trade_emotion',
            'post_trade_emotion', 'status', 'notes', 'lessons_learned',
            'tags', 'entry_screenshot', 'exit_screenshot', 'mt5_ticket',
            'commission', 'swap', 'created_at', 'updated_at',
            'profit_loss_formatted', 'duration'
        ]
        read_only_fields = [
            'id', 'profit_loss', 'profit_loss_pips', 'profit_loss_percentage',
            'risk_reward_ratio', 'created_at', 'updated_at'
        ]
    
    def get_profit_loss_formatted(self, obj):
        if obj.profit_loss is not None:
            return f"${float(obj.profit_loss):,.2f}"
        return None
    
    def get_duration(self, obj):
        if obj.exit_date and obj.entry_date:
            duration = obj.exit_date - obj.entry_date
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours >= 24:
                days = int(hours // 24)
                hours = int(hours % 24)
                return f"{days}d {hours}h {int(minutes)}m"
            return f"{int(hours)}h {int(minutes)}m"
        return None


class TradeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = [
            'symbol', 'trade_type', 'market_type', 'entry_price',
            'entry_date', 'exit_price', 'exit_date', 'position_size',
            'stop_loss', 'take_profit', 'timeframe', 'strategy',
            'setup_type', 'pre_trade_emotion', 'post_trade_emotion',
            'status', 'notes', 'lessons_learned', 'tags',
            'entry_screenshot', 'exit_screenshot', 'commission', 'swap'
        ]
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class TradeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = [
            'exit_price', 'exit_date', 'stop_loss', 'take_profit',
            'status', 'notes', 'lessons_learned', 'tags',
            'post_trade_emotion', 'exit_screenshot'
        ]


class TradeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for trade lists."""
    class Meta:
        model = Trade
        fields = [
            'id', 'symbol', 'trade_type', 'entry_price', 'exit_price',
            'entry_date', 'exit_date', 'profit_loss', 'profit_loss_percentage',
            'status', 'strategy', 'tags'
        ]


class TradeImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeImport
        fields = [
            'id', 'source', 'status', 'file', 'total_trades',
            'imported_trades', 'failed_trades', 'date_from', 'date_to',
            'error_message', 'created_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'status', 'total_trades', 'imported_trades',
            'failed_trades', 'error_message', 'created_at', 'completed_at'
        ]


class StrategySerializer(serializers.ModelSerializer):
    performance = serializers.SerializerMethodField()
    
    class Meta:
        model = Strategy
        fields = [
            'id', 'name', 'description', 'entry_rules', 'exit_rules',
            'risk_management', 'total_trades', 'winning_trades',
            'losing_trades', 'win_rate', 'avg_profit', 'avg_loss',
            'profit_factor', 'is_active', 'created_at', 'updated_at',
            'performance'
        ]
        read_only_fields = [
            'id', 'total_trades', 'winning_trades', 'losing_trades',
            'win_rate', 'avg_profit', 'avg_loss', 'profit_factor',
            'created_at', 'updated_at'
        ]
    
    def get_performance(self, obj):
        return {
            'win_rate': float(obj.win_rate) if obj.win_rate else 0,
            'profit_factor': float(obj.profit_factor) if obj.profit_factor else 0,
            'total_trades': obj.total_trades,
            'winning_trades': obj.winning_trades,
            'losing_trades': obj.losing_trades,
        }


class TradeStatisticsSerializer(serializers.Serializer):
    total_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    losing_trades = serializers.IntegerField()
    win_rate = serializers.FloatField()
    total_profit = serializers.FloatField()
    total_loss = serializers.FloatField()
    net_pnl = serializers.FloatField()
    avg_profit = serializers.FloatField()
    avg_loss = serializers.FloatField()
    profit_factor = serializers.FloatField()
    avg_trade = serializers.FloatField()
    largest_profit = serializers.FloatField()
    largest_loss = serializers.FloatField()
    max_consecutive_wins = serializers.IntegerField()
    max_consecutive_losses = serializers.IntegerField()
    avg_holding_time = serializers.CharField()
    total_commission = serializers.FloatField()
    total_swap = serializers.FloatField()


class TradeFilterSerializer(serializers.Serializer):
    symbol = serializers.CharField(required=False)
    trade_type = serializers.ChoiceField(choices=Trade.TRADE_TYPES, required=False)
    status = serializers.ChoiceField(choices=Trade.TRADE_STATUS, required=False)
    market_type = serializers.ChoiceField(choices=Trade.MARKET_TYPES, required=False)
    strategy = serializers.CharField(required=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)
    profit_min = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    profit_max = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
