from django.db import models
import uuid


class MarketNews(models.Model):
    IMPACT_LEVELS = [
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)
    content = models.TextField()
    summary = models.TextField(blank=True, null=True)
    
    # Source
    source = models.CharField(max_length=100)
    source_url = models.URLField(blank=True, null=True)
    external_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Categorization
    category = models.CharField(max_length=50, blank=True, null=True)
    currency_pairs = models.JSONField(default=list, blank=True)
    impact = models.CharField(max_length=10, choices=IMPACT_LEVELS, default='MEDIUM')
    
    # Timestamps
    published_at = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'market_data_marketnews'
        ordering = ['-published_at']
        verbose_name_plural = 'Market News'
    
    def __str__(self):
        return self.title


class EconomicEvent(models.Model):
    IMPACT_LEVELS = [
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    ]
    
    EVENT_TYPES = [
        ('GDP', 'GDP'),
        ('EMPLOYMENT', 'Employment'),
        ('INFLATION', 'Inflation'),
        ('INTEREST_RATE', 'Interest Rate'),
        ('RETAIL_SALES', 'Retail Sales'),
        ('MANUFACTURING', 'Manufacturing'),
        ('TRADE_BALANCE', 'Trade Balance'),
        ('CONSUMER_CONFIDENCE', 'Consumer Confidence'),
        ('OTHER', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Event details
    title = models.CharField(max_length=200)
    country = models.CharField(max_length=50)
    currency = models.CharField(max_length=3)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='OTHER')
    impact = models.CharField(max_length=10, choices=IMPACT_LEVELS, default='MEDIUM')
    
    # Time
    event_date = models.DateField()
    event_time = models.TimeField(blank=True, null=True)
    
    # Forecast and actual values
    forecast = models.CharField(max_length=50, blank=True, null=True)
    previous = models.CharField(max_length=50, blank=True, null=True)
    actual = models.CharField(max_length=50, blank=True, null=True)
    
    # Source
    source = models.CharField(max_length=100, default='ForexFactory')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'market_data_economicevent'
        ordering = ['event_date', 'event_time']
    
    def __str__(self):
        return f"{self.title} - {self.event_date}"


class MarketPrice(models.Model):
    MARKET_TYPES = [
        ('FOREX', 'Forex'),
        ('CRYPTO', 'Cryptocurrency'),
        ('STOCKS', 'Stocks'),
        ('INDICES', 'Indices'),
        ('COMMODITIES', 'Commodities'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField(max_length=20)
    market_type = models.CharField(max_length=15, choices=MARKET_TYPES)
    
    # Price data
    bid = models.DecimalField(max_digits=20, decimal_places=8)
    ask = models.DecimalField(max_digits=20, decimal_places=8)
    spread = models.DecimalField(max_digits=20, decimal_places=8)
    
    # Change
    change = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    change_percentage = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    
    # High/Low
    high_24h = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    low_24h = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'market_data_marketprice'
        ordering = ['-timestamp']
        unique_together = ['symbol', 'market_type']
    
    def __str__(self):
        return f"{self.symbol} - {self.bid}"


class Instrument(models.Model):
    MARKET_TYPES = [
        ('FOREX', 'Forex'),
        ('CRYPTO', 'Cryptocurrency'),
        ('STOCKS', 'Stocks'),
        ('INDICES', 'Indices'),
        ('COMMODITIES', 'Commodities'),
        ('FUTURES', 'Futures'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    market_type = models.CharField(max_length=15, choices=MARKET_TYPES)
    
    # Details
    description = models.TextField(blank=True, null=True)
    base_currency = models.CharField(max_length=3, blank=True, null=True)
    quote_currency = models.CharField(max_length=3, blank=True, null=True)
    
    # Trading specs
    pip_value = models.DecimalField(max_digits=20, decimal_places=8, default=0.0001)
    contract_size = models.DecimalField(max_digits=20, decimal_places=8, default=100000)
    min_lot_size = models.DecimalField(max_digits=10, decimal_places=2, default=0.01)
    max_lot_size = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    
    # Session times (UTC)
    session_open = models.TimeField(blank=True, null=True)
    session_close = models.TimeField(blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'market_data_instrument'
        ordering = ['symbol']
    
    def __str__(self):
        return self.symbol
