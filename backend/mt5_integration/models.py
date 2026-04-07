from django.db import models
from django.conf import settings
import uuid


class MT5Account(models.Model):
    CONNECTION_STATUS = [
        ('CONNECTED',    'Connected'),
        ('DISCONNECTED', 'Disconnected'),
        ('ERROR',        'Error'),
        ('PENDING',      'Pending'),
    ]

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mt5_accounts',
    )

    # Account details
    name           = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    server         = models.CharField(max_length=255)

    # Credentials (consider using django-encrypted-model-fields in production)
    password          = models.CharField(max_length=255)
    investor_password = models.CharField(max_length=255, blank=True, null=True)

    # Connection status
    status         = models.CharField(max_length=15, choices=CONNECTION_STATUS, default='DISCONNECTED')
    last_connected = models.DateTimeField(null=True, blank=True)
    last_error     = models.TextField(blank=True, null=True)

    # Cached account info (refreshed on every sync)
    balance      = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    equity       = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    margin       = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    free_margin  = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    margin_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Sync settings
    auto_sync     = models.BooleanField(default=True)
    sync_interval = models.IntegerField(default=5)   # minutes

    is_active  = models.BooleanField(default=True)
    is_demo    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table       = 'mt5_integration_mt5account'
        ordering       = ['-created_at']
        unique_together = ['user', 'account_number', 'server']

    def __str__(self):
        return f"{self.name} ({self.account_number})"


class MT5TradeImport(models.Model):
    IMPORT_STATUS = [
        ('PENDING',   'Pending'),
        ('RUNNING',   'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED',    'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]

    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mt5_imports',
    )
    account = models.ForeignKey(
        MT5Account,
        on_delete=models.CASCADE,
        related_name='imports',
    )

    status    = models.CharField(max_length=15, choices=IMPORT_STATUS, default='PENDING')
    date_from = models.DateTimeField(blank=True, null=True)
    date_to   = models.DateTimeField(blank=True, null=True)

    total_trades    = models.IntegerField(default=0)
    imported_trades = models.IntegerField(default=0)
    skipped_trades  = models.IntegerField(default=0)
    failed_trades   = models.IntegerField(default=0)

    error_message = models.TextField(blank=True, null=True)

    started_at   = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mt5_integration_mt5tradeimport'
        ordering = ['-created_at']

    def __str__(self):
        return f"Import {self.id} – {self.status}"


class MT5ConnectionLog(models.Model):
    LOG_TYPES = [
        ('CONNECT',    'Connect'),
        ('DISCONNECT', 'Disconnect'),
        ('SYNC',       'Sync'),
        ('ERROR',      'Error'),
        ('INFO',       'Info'),
    ]

    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        MT5Account,
        on_delete=models.CASCADE,
        related_name='connection_logs',
    )

    log_type   = models.CharField(max_length=15, choices=LOG_TYPES)
    message    = models.TextField()
    details    = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mt5_integration_mt5connectionlog'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.log_type} – {self.account.name}"


class MT5SetupGuide(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title      = models.CharField(max_length=200)
    content    = models.TextField()
    order      = models.IntegerField(default=0)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mt5_integration_mt5setupguide'
        ordering = ['order']

    def __str__(self):
        return self.title