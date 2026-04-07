from django.db import models
from django.conf import settings
import uuid


class PerformanceReport(models.Model):
    REPORT_TYPES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('YEARLY', 'Yearly'),
        ('CUSTOM', 'Custom'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='performance_reports'
    )
    report_type = models.CharField(max_length=10, choices=REPORT_TYPES)
    date_from = models.DateTimeField()
    date_to = models.DateTimeField()
    
    # Performance metrics
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    win_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # P&L metrics
    gross_profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    gross_loss = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    net_profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    
    # Risk metrics
    profit_factor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sharpe_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_drawdown = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_drawdown_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    
    # Trade metrics
    avg_trade = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    avg_win = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    avg_loss = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    largest_win = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    largest_loss = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    
    # Consecutive trades
    max_consecutive_wins = models.IntegerField(default=0)
    max_consecutive_losses = models.IntegerField(default=0)
    
    # AI insights
    ai_insights = models.JSONField(default=dict, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'analytics_performance_report'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.report_type} Report - {self.user.email}"


class TradingInsight(models.Model):
    INSIGHT_TYPES = [
        ('PATTERN', 'Pattern'),
        ('MISTAKE', 'Mistake'),
        ('IMPROVEMENT', 'Improvement'),
        ('STRENGTH', 'Strength'),
        ('WEAKNESS', 'Weakness'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trading_insights'
    )
    insight_type = models.CharField(max_length=15, choices=INSIGHT_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    # Related metrics
    metric_name = models.CharField(max_length=100, blank=True, null=True)
    metric_value = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    
    # Impact
    impact_score = models.IntegerField(default=0)  # -100 to 100
    
    # Status
    is_acknowledged = models.BooleanField(default=False)
    is_actioned = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'analytics_trading_insight'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.insight_type}: {self.title}"
