from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class JournalEntry(models.Model):
    ENTRY_TYPES = [
        ('TRADE_REVIEW', 'Trade Review'),
        ('DAILY_SUMMARY', 'Daily Summary'),
        ('WEEKLY_REVIEW', 'Weekly Review'),
        ('MONTHLY_REVIEW', 'Monthly Review'),
        ('LESSON_LEARNED', 'Lesson Learned'),
        ('STRATEGY_NOTES', 'Strategy Notes'),
        ('MARKET_OBSERVATION', 'Market Observation'),
        ('PSYCHOLOGY', 'Psychology'),
        ('GOALS', 'Goals'),
        ('GENERAL', 'General'),
    ]
    
    MOOD_CHOICES = [
        ('EXCELLENT', 'Excellent'),
        ('GOOD', 'Good'),
        ('NEUTRAL', 'Neutral'),
        ('BAD', 'Bad'),
        ('TERRIBLE', 'Terrible'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='journal_entries'
    )
    
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES, default='GENERAL')
    title = models.CharField(max_length=200)
    content = models.TextField()
    
    # Related trades
    related_trades = models.ManyToManyField(
        'trades.Trade',
        blank=True,
        related_name='journal_entries'
    )
    
    # Psychology tracking
    pre_trading_mood = models.CharField(
        max_length=10,
        choices=MOOD_CHOICES,
        blank=True,
        null=True
    )
    post_trading_mood = models.CharField(
        max_length=10,
        choices=MOOD_CHOICES,
        blank=True,
        null=True
    )
    
    # Tags
    tags = models.JSONField(default=list, blank=True)
    
    # Attachments
    attachments = models.JSONField(default=list, blank=True)
    
    # Date
    entry_date = models.DateTimeField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'journal_journalentry'
        ordering = ['-entry_date']
        verbose_name_plural = 'Journal Entries'
    
    def __str__(self):
        return f"{self.title} - {self.entry_date}"


class TradingGoal(models.Model):
    GOAL_TYPES = [
        ('PROFIT', 'Profit Target'),
        ('RISK', 'Risk Management'),
        ('DISCIPLINE', 'Discipline'),
        ('PSYCHOLOGY', 'Psychology'),
        ('STRATEGY', 'Strategy'),
        ('EDUCATION', 'Education'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('ABANDONED', 'Abandoned'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trading_goals'
    )
    
    goal_type = models.CharField(max_length=15, choices=GOAL_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    # Target metrics
    target_value = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True
    )
    current_value = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=0
    )
    
    # Timeline
    start_date = models.DateField()
    target_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    
    # Progress
    progress_percentage = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'journal_tradinggoal'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.status}"

    def update_progress(self):
        """
        Calculates the latest progress for the goal. If it's a 'PROFIT' goal,
        it automatically sums up the profit_loss of closed trades in the timeframe.
        """
        if self.status != 'ACTIVE':
            return
            
        from trades.models import Trade
        from django.db.models import Sum
        
        # 1. Automatically fetch actual profit if this is a PROFIT goal
        if self.goal_type == 'PROFIT':
            trades = Trade.objects.filter(
                user=self.user,
                status='CLOSED',
                entry_date__date__gte=self.start_date,
                entry_date__date__lte=self.target_date
            )
            total_profit = trades.aggregate(Sum('profit_loss'))['profit_loss__sum'] or 0
            self.current_value = total_profit

        # 2. Update percentage based on current_value (Manual goals or Profit goals)
        if self.target_value and self.target_value > 0:
            if float(self.current_value) < 0:
                self.progress_percentage = 0
            else:
                self.progress_percentage = min(
                    100, 
                    int((float(self.current_value) / float(self.target_value)) * 100)
                )
        else:
            self.progress_percentage = 0

        # 3. Check if completed
        if self.progress_percentage >= 100:
            self.status = 'COMPLETED'
            self.completed_date = timezone.now().date()
            
        # Save updates to DB
        self.save(update_fields=['current_value', 'progress_percentage', 'status', 'completed_date', 'updated_at'])


class TradingPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trading_plans'
    )
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    # Trading rules
    entry_criteria = models.TextField(blank=True, null=True)
    exit_criteria = models.TextField(blank=True, null=True)
    risk_management_rules = models.TextField(blank=True, null=True)
    position_sizing = models.TextField(blank=True, null=True)
    
    # Markets and timeframes
    markets_traded = models.JSONField(default=list, blank=True)
    timeframes = models.JSONField(default=list, blank=True)
    
    # Daily routine
    pre_trading_routine = models.TextField(blank=True, null=True)
    post_trading_routine = models.TextField(blank=True, null=True)
    
    # Risk parameters
    max_risk_per_trade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1.00
    )
    max_daily_loss = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=3.00
    )
    max_weekly_loss = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5.00
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'journal_tradingplan'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class ChecklistTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='checklist_templates'
    )
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    # Checklist items
    items = models.JSONField(default=list)
    
    # Usage
    is_pre_trade = models.BooleanField(default=True)
    is_post_trade = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'journal_checklisttemplate'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class TradeChecklist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.OneToOneField(
        'trades.Trade',
        on_delete=models.CASCADE,
        related_name='checklist'
    )
    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Completed items
    completed_items = models.JSONField(default=list)
    
    # Notes
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'journal_tradechecklist'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Checklist for {self.trade}"