from rest_framework import serializers
from .models import PerformanceReport, TradingInsight


class PerformanceReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceReport
        fields = [
            'id', 'report_type', 'date_from', 'date_to',
            'total_trades', 'winning_trades', 'losing_trades',
            'win_rate', 'gross_profit', 'gross_loss', 'net_profit',
            'profit_factor', 'sharpe_ratio', 'max_drawdown',
            'max_drawdown_amount', 'avg_trade', 'avg_win', 'avg_loss',
            'largest_win', 'largest_loss', 'max_consecutive_wins',
            'max_consecutive_losses', 'ai_insights', 'recommendations',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class TradingInsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingInsight
        fields = [
            'id', 'insight_type', 'title', 'description',
            'metric_name', 'metric_value', 'impact_score',
            'is_acknowledged', 'is_actioned', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class EquityCurveSerializer(serializers.Serializer):
    date = serializers.DateTimeField()
    equity = serializers.FloatField()
    daily_pnl = serializers.FloatField()
    cumulative_pnl = serializers.FloatField()


class DrawdownSerializer(serializers.Serializer):
    date = serializers.DateTimeField()
    drawdown_percentage = serializers.FloatField()
    drawdown_amount = serializers.FloatField()
    peak_equity = serializers.FloatField()
    current_equity = serializers.FloatField()


class MonthlyPerformanceSerializer(serializers.Serializer):
    month = serializers.CharField()
    year = serializers.IntegerField()
    total_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    losing_trades = serializers.IntegerField()
    net_pnl = serializers.FloatField()
    win_rate = serializers.FloatField()


class TagPerformanceSerializer(serializers.Serializer):
    tag = serializers.CharField()
    total_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    net_pnl = serializers.FloatField()
    avg_pnl = serializers.FloatField()
    win_rate = serializers.FloatField()
