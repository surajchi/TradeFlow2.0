"""
trades/models.py
────────────────
Pip value reference (USD-denominated account, all standard MT5 lot sizes):

  Direct pairs   (quote = USD)  → EURUSD, GBPUSD, AUDUSD, NZDUSD, XAGUSD
    pip_value = lots × 100 000 × pip_size          (pip_size = 0.0001)
    Example: 0.01 lot, 100 pips = 0.01 × 100 000 × 0.0001 × 100 = $10.00 ✓

  Indirect pairs (base = USD)   → USDJPY, USDCAD, USDCHF
    pip_value = lots × 100 000 × pip_size / exit_rate
    Example: 0.01 lot, 100 pips USDJPY @ 150 = 0.01×100 000×0.01/150 = $6.67

  Cross pairs    (no USD)       → EURJPY, GBPJPY, EURGBP, AUDCAD …
    Requires live quote-vs-USD rate for exact value.
    We approximate:  pnl = lots × 100 000 × price_diff
    then convert quote→USD using a static fallback table (good enough for display).
    For production-accurate values see:
      - ExchangeRate-API  https://www.exchangerate-api.com/  (free tier available)
      - Fixer.io          https://fixer.io/
      - MT5 always sends the real net P&L — that value is ALWAYS preferred.

  CFD / exotic symbols (AUDCAD!, XAUUSD, BTCUSD …)
    MT5 provides the authoritative profit.  We never recalculate for MT5 trades.
"""

from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.conf import settings
import uuid


# ─── Approximate USD rates for cross-pair pip-value conversion ────────────────
# Used ONLY for manually entered trades where MT5 profit is unavailable.
# Update these periodically or replace with a live rate API call.

_APPROX_USD_RATE = {
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "AUD": Decimal("0.65"),
    "NZD": Decimal("0.60"),
    "CAD": Decimal("0.74"),
    "CHF": Decimal("1.12"),
    "JPY": Decimal("0.0067"),
    "SGD": Decimal("0.74"),
    "HKD": Decimal("0.13"),
    "NOK": Decimal("0.095"),
    "SEK": Decimal("0.096"),
    "DKK": Decimal("0.145"),
    "MXN": Decimal("0.058"),
    "ZAR": Decimal("0.054"),
    "TRY": Decimal("0.031"),
    "USD": Decimal("1.0"),
}

def _usd_rate(currency: str) -> Decimal:
    """Return approximate USD rate for a currency (1 unit = ? USD)."""
    return _APPROX_USD_RATE.get(currency.upper(), Decimal("1.0"))


# ─── Pip value engine ─────────────────────────────────────────────────────────

def calculate_forex_pnl(
    symbol: str,
    trade_type: str,
    entry_price: Decimal,
    exit_price: Decimal,
    lots: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Calculate monetary P&L and pip count for a forex/CFD trade.

    Returns (profit_loss_usd, profit_loss_pips).

    Formula:
        units      = lots × 100 000
        price_diff = exit − entry  (negated for SELL)
        pip_size   = 0.01 for JPY pairs, else 0.0001
        pips       = price_diff / pip_size

    Pip value in USD:
        • Direct  (quote=USD): pip_value = units × pip_size
        • Indirect(base=USD) : pip_value = units × pip_size / exit_price
        • Cross              : pip_value = units × pip_size × usd_rate(quote)
    """
    # Normalise symbol — strip CFD suffix (! or _mt, etc.)
    raw = symbol.upper().replace("!", "").replace("_MT", "").strip()

    units = lots * Decimal("100000")

    price_diff = exit_price - entry_price
    if trade_type == "SELL":
        price_diff = -price_diff

    # Detect pip size
    pip_size = Decimal("0.01") if "JPY" in raw else Decimal("0.0001")

    # Detect special instruments
    if raw in ("XAUUSD", "GOLD"):
        pip_size = Decimal("0.01")   # Gold: 1 pip = $0.01; 1 lot = 100 oz
        units = lots * Decimal("100")
    elif raw in ("XAGUSD", "SILVER"):
        pip_size = Decimal("0.001")
        units = lots * Decimal("5000")
    elif raw.startswith("BTC") or raw.startswith("ETH"):
        # Crypto: treat price_diff × lots directly
        pnl = (price_diff * lots).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return pnl, Decimal("0")

    pips = (price_diff / pip_size).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    # Determine base / quote currencies (works for 6-char symbols like EURUSD)
    if len(raw) >= 6:
        base  = raw[:3]
        quote = raw[3:6]
    else:
        # Exotic / index — fall back to raw price × lots approximation
        pnl = (price_diff * units).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return pnl, pips

    if quote == "USD":
        # Direct: EURUSD, GBPUSD, AUDUSD, NZDUSD, XAGUSD …
        pip_value = units * pip_size          # already in USD
    elif base == "USD":
        # Indirect: USDJPY, USDCAD, USDCHF …
        pip_value = units * pip_size / exit_price
    else:
        # Cross: EURJPY, GBPJPY, AUDCAD, EURGBP …
        # Convert quote currency pip value → USD
        pip_value = units * pip_size * _usd_rate(quote)

    pnl = (pips * pip_value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return pnl, pips


# ─── Models ───────────────────────────────────────────────────────────────────

class Trade(models.Model):
    TRADE_TYPES = [
        ('BUY',  'Buy'),
        ('SELL', 'Sell'),
    ]

    TRADE_STATUS = [
        ('OPEN',      'Open'),
        ('CLOSED',    'Closed'),
        ('CANCELLED', 'Cancelled'),
    ]

    MARKET_TYPES = [
        ('FOREX',       'Forex'),
        ('CRYPTO',      'Cryptocurrency'),
        ('STOCKS',      'Stocks'),
        ('INDICES',     'Indices'),
        ('COMMODITIES', 'Commodities'),
        ('FUTURES',     'Futures'),
        ('OPTIONS',     'Options'),
    ]

    TIMEFRAMES = [
        ('M1',  '1 Minute'),
        ('M5',  '5 Minutes'),
        ('M15', '15 Minutes'),
        ('M30', '30 Minutes'),
        ('H1',  '1 Hour'),
        ('H4',  '4 Hours'),
        ('D1',  'Daily'),
        ('W1',  'Weekly'),
        ('MN',  'Monthly'),
    ]

    EMOTION_CHOICES = [
        ('CONFIDENT', 'Confident'),
        ('FEARFUL',   'Fearful'),
        ('GREEDY',    'Greedy'),
        ('NEUTRAL',   'Neutral'),
        ('IMPATIENT', 'Impatient'),
        ('REVENGE',   'Revenge Trading'),
        ('FOMO',      'FOMO'),
    ]

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trades',
    )

    # ── Core trade fields ────────────────────────────────────────────────────
    symbol      = models.CharField(max_length=20)
    trade_type  = models.CharField(max_length=4,  choices=TRADE_TYPES)
    market_type = models.CharField(max_length=15, choices=MARKET_TYPES, default='FOREX')

    entry_price   = models.DecimalField(max_digits=20, decimal_places=8)
    entry_date    = models.DateTimeField()
    position_size = models.DecimalField(max_digits=20, decimal_places=8)   # lots

    exit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    exit_date  = models.DateTimeField(null=True, blank=True)

    stop_loss   = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # ── P&L ─────────────────────────────────────────────────────────────────
    profit_loss = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text="Net monetary P&L in account currency (USD). "
                  "For MT5 trades this is sourced directly from MT5 "
                  "(profit + swap + commission). "
                  "For manual trades it is calculated by calculate_profit_loss().",
    )
    profit_loss_pips = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
    )
    profit_loss_percentage = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
    )

    # ── Risk management ──────────────────────────────────────────────────────
    risk_reward_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    risk_amount       = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    # ── Analysis ─────────────────────────────────────────────────────────────
    timeframe  = models.CharField(max_length=3,   choices=TIMEFRAMES, default='H1')
    strategy   = models.CharField(max_length=100, blank=True, null=True)
    setup_type = models.CharField(max_length=100, blank=True, null=True)

    # ── Psychology ───────────────────────────────────────────────────────────
    pre_trade_emotion  = models.CharField(max_length=20, choices=EMOTION_CHOICES, default='NEUTRAL')
    post_trade_emotion = models.CharField(max_length=20, choices=EMOTION_CHOICES, null=True, blank=True)

    # ── Status & journaling ──────────────────────────────────────────────────
    status          = models.CharField(max_length=10, choices=TRADE_STATUS, default='OPEN')
    notes           = models.TextField(blank=True, null=True)
    lessons_learned = models.TextField(blank=True, null=True)
    tags            = models.JSONField(default=list, blank=True)

    # ── Screenshots ──────────────────────────────────────────────────────────
    entry_screenshot = models.ImageField(upload_to='trade_screenshots/entries/', blank=True, null=True)
    exit_screenshot  = models.ImageField(upload_to='trade_screenshots/exits/',   blank=True, null=True)

    # ── MT5 integration ──────────────────────────────────────────────────────
    mt5_ticket       = models.CharField(max_length=50,  blank=True, null=True)
    mt5_magic_number = models.CharField(max_length=50,  blank=True, null=True)
    mt5_comment      = models.CharField(max_length=255, blank=True, null=True)

    # ── Fees ─────────────────────────────────────────────────────────────────
    commission = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    swap       = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'trades_trade'
        ordering = ['-entry_date']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'symbol']),
            models.Index(fields=['user', 'entry_date']),
            models.Index(fields=['user', 'strategy']),
        ]

    def __str__(self):
        return f"{self.symbol} {self.trade_type} – {self.entry_date:%Y-%m-%d}"

    # ── P&L calculation ──────────────────────────────────────────────────────

    def calculate_profit_loss(self) -> Decimal | None:
        """
        Calculate P&L for a manually entered trade.

        NOT called for MT5-imported trades — MT5 provides the authoritative
        net profit (including swap & commission) directly.

        Uses calculate_forex_pnl() for FOREX/CFD.
        For other market types uses simple price_diff × position_size.
        """
        if self.status != 'CLOSED' or self.exit_price is None:
            return None

        entry = Decimal(str(self.entry_price))
        exit_ = Decimal(str(self.exit_price))
        lots  = Decimal(str(self.position_size))

        if self.market_type == 'FOREX' or self.symbol.upper().endswith('!'):
            pnl, pips = calculate_forex_pnl(
                symbol=self.symbol,
                trade_type=self.trade_type,
                entry_price=entry,
                exit_price=exit_,
                lots=lots,
            )
            self.profit_loss      = pnl
            self.profit_loss_pips = pips
        else:
            # Stocks / indices / crypto — simple directional P&L
            price_diff = exit_ - entry
            if self.trade_type == 'SELL':
                price_diff = -price_diff
            self.profit_loss = (price_diff * lots).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        # Percentage of risk
        if self.risk_amount and self.risk_amount > 0:
            self.profit_loss_percentage = (
                self.profit_loss / self.risk_amount * 100
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        return self.profit_loss

    def calculate_risk_reward(self) -> Decimal | None:
        """Calculate R:R ratio from SL/TP levels."""
        if self.stop_loss and self.take_profit:
            risk   = abs(self.entry_price - self.stop_loss)
            reward = abs(self.take_profit  - self.entry_price)
            if risk > 0:
                self.risk_reward_ratio = (reward / risk).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        return self.risk_reward_ratio

    def save(self, *args, **kwargs):
        """
        Auto-calculate P&L only for MANUAL trades (no mt5_ticket).

        MT5-imported trades already carry the correct net profit
        (deal.profit + deal.swap + deal.commission) set by the importer.
        Recalculating would overwrite that with a price-based estimate
        and produce incorrect values for non-USD-quote pairs.
        """
        is_mt5_trade = bool(self.mt5_ticket)

        if self.status == 'CLOSED' and self.exit_price and not is_mt5_trade:
            # Manual trade — calculate P&L from prices
            if self.profit_loss is None:
                self.calculate_profit_loss()

        if self.stop_loss and self.take_profit:
            self.calculate_risk_reward()

        super().save(*args, **kwargs)


# ─── Trade import log ─────────────────────────────────────────────────────────

class TradeImport(models.Model):
    IMPORT_STATUS = [
        ('PENDING',    'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED',  'Completed'),
        ('FAILED',     'Failed'),
    ]

    IMPORT_SOURCES = [
        ('MT5',    'MetaTrader 5'),
        ('MT4',    'MetaTrader 4'),
        ('CSV',    'CSV File'),
        ('MANUAL', 'Manual Entry'),
    ]

    id     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trade_imports',
    )
    source = models.CharField(max_length=10, choices=IMPORT_SOURCES)
    status = models.CharField(max_length=15, choices=IMPORT_STATUS, default='PENDING')

    file      = models.FileField(upload_to='trade_imports/', blank=True, null=True)
    mt5_server = models.CharField(max_length=255, blank=True, null=True)
    mt5_login  = models.CharField(max_length=50,  blank=True, null=True)

    total_trades    = models.IntegerField(default=0)
    imported_trades = models.IntegerField(default=0)
    failed_trades   = models.IntegerField(default=0)

    date_from = models.DateTimeField(blank=True, null=True)
    date_to   = models.DateTimeField(blank=True, null=True)

    error_message = models.TextField(blank=True, null=True)

    created_at   = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'trades_tradeimport'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.source} Import – {self.status}"


# ─── Strategy ─────────────────────────────────────────────────────────────────

class Strategy(models.Model):
    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='strategies',
    )
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    entry_rules     = models.TextField(blank=True, null=True)
    exit_rules      = models.TextField(blank=True, null=True)
    risk_management = models.TextField(blank=True, null=True)

    total_trades   = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades  = models.IntegerField(default=0)
    win_rate       = models.DecimalField(max_digits=5,  decimal_places=2, default=0)
    avg_profit     = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    avg_loss       = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_factor  = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table       = 'trades_strategy'
        ordering       = ['-created_at']
        unique_together = ['user', 'name']

    def __str__(self):
        return self.name