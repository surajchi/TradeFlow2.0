"""
MT5 Integration Service Layer
─────────────────────────────
Two import strategies:

  1. MT5Service        – Direct connection via MetaTrader5 Python library.
                         Windows only (requires MT5 terminal running).
                         Returns 503 on Linux — use strategy 2 instead.

  2. MT5ReportParser   – Parses the HTML/CSV report exported from MT5's
                         History tab.  Works on any OS (Linux, macOS, Windows).
                         This is the primary path for Linux/cloud servers.

How to export from MT5:
  Terminal (Ctrl+T) → History tab → right-click → Save as Detailed Report → HTML
"""

import csv
import io
import logging
import platform
import re
from datetime import datetime, timezone as dt_tz
from decimal import Decimal, InvalidOperation

from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Try importing the MT5 library (Windows-only) ─────────────────────────────

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    if platform.system() != "Windows":
        logger.info(
            "MetaTrader5 library unavailable on %s — file-based import will be used.",
            platform.system(),
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _safe_decimal(value, places: int = 5, fallback=Decimal("0")) -> Decimal:
    try:
        if value is None or str(value).strip() in ("", "-", "—"):
            return fallback
        cleaned = str(value).replace(" ", "").replace(",", "")
        return Decimal(str(round(float(cleaned), places)))
    except (TypeError, ValueError, InvalidOperation):
        return fallback


def _mt5_time_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=dt_tz.utc)


def _parse_mt5_datetime(value: str) -> datetime | None:
    """Parse MT5 report date strings like '2024.01.15 08:30:00'."""
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=dt_tz.utc)
        except (ValueError, AttributeError):
            continue
    return None


# ─── Errors ───────────────────────────────────────────────────────────────────

class MT5Error(Exception):
    def __init__(self, message: str, code: int = 0):
        self.code = code
        super().__init__(message)

class MT5NotAvailableError(MT5Error):
    pass

class MT5AuthError(MT5Error):
    pass


# ─── Direct MT5 connection (Windows only) ────────────────────────────────────

class MT5Service:
    """
    Wraps MetaTrader5 library calls.  Context-manager usage:

        with MT5Service(account) as svc:
            info   = svc.get_account_info()
            trades = svc.get_history(date_from, date_to)
    """

    DEAL_TYPE_BUY  = 0
    DEAL_TYPE_SELL = 1
    DEAL_ENTRY_IN  = 0
    DEAL_ENTRY_OUT = 1

    def __init__(self, account_obj):
        self._account   = account_obj
        self._connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def connect(self) -> None:
        if not MT5_AVAILABLE:
            raise MT5NotAvailableError(
                f"MetaTrader5 library is not available on {platform.system()}. "
                "Use file-based import (HTML/CSV) instead.",
                code=-1,
            )
        if not mt5.initialize():
            code, msg = mt5.last_error()
            raise MT5Error(f"mt5.initialize() failed: {msg}", code=code)

        ok = mt5.login(
            login=int(self._account.account_number),
            password=self._account.password,
            server=self._account.server,
        )
        if not ok:
            code, msg = mt5.last_error()
            mt5.shutdown()
            raise MT5AuthError(
                f"Login failed for {self._account.account_number} "
                f"on {self._account.server}: {msg}",
                code=code,
            )
        self._connected = True

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False

    def _require_connection(self):
        if not self._connected:
            raise MT5Error("Not connected. Use MT5Service as a context manager.")

    def get_account_info(self) -> dict:
        self._require_connection()
        info = mt5.account_info()
        if info is None:
            code, msg = mt5.last_error()
            raise MT5Error(f"account_info() failed: {msg}", code=code)
        return {
            "balance":          _safe_decimal(info.balance, 2),
            "equity":           _safe_decimal(info.equity, 2),
            "margin":           _safe_decimal(info.margin, 2),
            "free_margin":      _safe_decimal(info.margin_free, 2),
            "margin_level":     _safe_decimal(info.margin_level, 2),
            "currency":         info.currency,
            "leverage":         info.leverage,
            "server":           info.server,
            "name":             info.name,
            "company":          info.company,
            "is_trade_allowed": bool(info.trade_allowed),
        }

    def get_open_positions(self) -> list[dict]:
        self._require_connection()
        positions = mt5.positions_get() or []
        return [
            {
                "ticket":        p.ticket,
                "symbol":        p.symbol,
                "trade_type":    "BUY" if p.type == 0 else "SELL",
                "volume":        _safe_decimal(p.volume, 2),
                "entry_price":   _safe_decimal(p.price_open, 5),
                "current_price": _safe_decimal(p.price_current, 5),
                "sl":            _safe_decimal(p.sl, 5),
                "tp":            _safe_decimal(p.tp, 5),
                "profit":        _safe_decimal(p.profit, 2),
                "swap":          _safe_decimal(p.swap, 2),
                "open_time":     _mt5_time_to_dt(p.time),
                "comment":       p.comment,
                "magic":         p.magic,
            }
            for p in positions
        ]

    def get_history(self, date_from: datetime, date_to: datetime) -> list[dict]:
        self._require_connection()
        if date_from.tzinfo is None:
            date_from = date_from.replace(tzinfo=dt_tz.utc)
        if date_to.tzinfo is None:
            date_to = date_to.replace(tzinfo=dt_tz.utc)

        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            return []

        positions: dict[int, dict] = {}
        for deal in deals:
            pid = deal.position_id
            if deal.entry == self.DEAL_ENTRY_IN:
                positions[pid] = {
                    "ticket":      deal.ticket,
                    "position_id": pid,
                    "symbol":      deal.symbol,
                    "trade_type":  "BUY" if deal.type == self.DEAL_TYPE_BUY else "SELL",
                    "volume":      deal.volume,
                    "entry_price": deal.price,
                    "entry_time":  _mt5_time_to_dt(deal.time),
                    "commission":  deal.commission,
                    "swap":        0.0,
                    "profit":      0.0,
                    "exit_price":  None,
                    "exit_time":   None,
                    "comment":     deal.comment,
                    "magic":       deal.magic,
                }
            elif deal.entry == self.DEAL_ENTRY_OUT:
                if pid not in positions:
                    positions[pid] = {
                        "ticket":      deal.ticket,
                        "position_id": pid,
                        "symbol":      deal.symbol,
                        "trade_type":  "SELL" if deal.type == self.DEAL_TYPE_BUY else "BUY",
                        "volume":      deal.volume,
                        "entry_price": None,
                        "entry_time":  None,
                        "commission":  deal.commission,
                        "swap":        deal.swap,
                        "profit":      deal.profit,
                        "exit_price":  deal.price,
                        "exit_time":   _mt5_time_to_dt(deal.time),
                        "comment":     deal.comment,
                        "magic":       deal.magic,
                    }
                else:
                    positions[pid]["exit_price"]  = deal.price
                    positions[pid]["exit_time"]   = _mt5_time_to_dt(deal.time)
                    positions[pid]["profit"]     += deal.profit
                    positions[pid]["swap"]       += deal.swap
                    positions[pid]["commission"] += deal.commission

        return [
            t for t in positions.values()
            if t["entry_price"] is not None and t["exit_price"] is not None
        ]


# ─── File-based parser (cross-platform) ──────────────────────────────────────

class MT5ReportParser:
    """
    Parses the HTML or CSV trade history exported by MT5.

    MT5 HTML "Detailed Report" columns:
      Ticket | Open Time | Type | Size | Symbol | Price | S/L | T/P |
      Close Time | Price | Commission | Swap | Profit | Balance | Comment
    """

    TYPE_MAP = {
        "buy":        "BUY",
        "sell":       "SELL",
        "buy limit":  "BUY",
        "sell limit": "SELL",
        "buy stop":   "BUY",
        "sell stop":  "SELL",
    }

    @classmethod
    def parse(cls, content: str, file_format: str) -> list[dict]:
        if file_format == "csv":
            return cls.parse_csv(content)
        return cls.parse_html(content)

    @classmethod
    def parse_html(cls, content: str) -> list[dict]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise MT5Error("beautifulsoup4 required for HTML parsing: pip install beautifulsoup4")

        soup = BeautifulSoup(content, "html.parser")
        rows = []

        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if "symbol" not in " ".join(headers) or "profit" not in " ".join(headers):
                continue
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) < 13:
                    continue
                trade_type_raw = cells[2].strip().lower() if len(cells) > 2 else ""
                if trade_type_raw not in cls.TYPE_MAP:
                    continue
                row = cls._cells_to_dict(cells)
                if row:
                    rows.append(row)

        logger.info("MT5ReportParser HTML: %d trades parsed", len(rows))
        return rows

    @classmethod
    def parse_csv(cls, content: str) -> list[dict]:
        reader = csv.reader(io.StringIO(content.strip()))
        rows   = []
        header_skipped = False

        for cells in reader:
            if not header_skipped:
                header_skipped = True
                # If the first cell looks like a header, skip it
                if not cells[0].strip().isdigit():
                    continue
            if len(cells) < 13:
                continue
            trade_type_raw = cells[2].strip().lower() if len(cells) > 2 else ""
            if trade_type_raw not in cls.TYPE_MAP:
                continue
            row = cls._cells_to_dict(cells)
            if row:
                rows.append(row)

        logger.info("MT5ReportParser CSV: %d trades parsed", len(rows))
        return rows

    @classmethod
    def _cells_to_dict(cls, cells: list[str]) -> dict | None:
        """Convert a row of cell strings to a normalised trade dict."""
        try:
            ticket_raw = cells[0].strip()
            ticket     = int(ticket_raw) if ticket_raw.isdigit() else None

            return {
                "ticket":      ticket,
                "position_id": ticket,
                "symbol":      cells[4].strip().upper(),
                "trade_type":  cls.TYPE_MAP.get(cells[2].strip().lower(), "BUY"),
                "volume":      float(cells[3]) if cells[3].strip() else 0,
                "entry_price": float(cells[5]) if cells[5].strip() else None,
                "entry_time":  _parse_mt5_datetime(cells[1]),
                "exit_price":  float(cells[9]) if cells[9].strip() else None,
                "exit_time":   _parse_mt5_datetime(cells[8]),
                "commission":  float(cells[10]) if cells[10].strip() else 0,
                "swap":        float(cells[11]) if cells[11].strip() else 0,
                "profit":      float(cells[12]) if cells[12].strip() else 0,
                "comment":     cells[14].strip() if len(cells) > 14 else "",
                "magic":       0,
            }
        except (IndexError, ValueError):
            return None


# ─── Trade importer (shared by direct and file-based paths) ──────────────────

class MT5TradeImporter:
    """
    Persists parsed trade dicts to the Trade model.
    Used by both MT5SyncTradesView (Windows direct) and MT5FileImportView (any OS).
    """

    def __init__(self, user, account_obj, import_record):
        self.user          = user
        self.account       = account_obj
        self.import_record = import_record

    # ── Direct path (Windows MT5 library) ────────────────────────────────────

    def run_direct(self, date_from: datetime, date_to: datetime) -> dict:
        from .models import MT5ConnectionLog
        stats = {"total": 0, "imported": 0, "skipped": 0, "failed": 0}

        try:
            with MT5Service(self.account) as svc:
                self._update_account_from_info(svc.get_account_info())
                raw = svc.get_history(date_from, date_to)
                stats["total"] = len(raw)
                self._save_trades(raw, stats)

        except (MT5NotAvailableError, MT5AuthError, MT5Error) as exc:
            self._fail(str(exc))
            self.account.status     = "ERROR"
            self.account.last_error = str(exc)
            self.account.save(update_fields=["status", "last_error"])
            MT5ConnectionLog.objects.create(
                account=self.account, log_type="ERROR",
                message=str(exc), details={"code": getattr(exc, "code", 0)},
            )
            raise
        except Exception as exc:
            logger.error("MT5 direct sync: %s", exc, exc_info=True)
            self._fail(str(exc))
            raise
        finally:
            self._finalise(stats)

        MT5ConnectionLog.objects.create(
            account=self.account, log_type="SYNC",
            message=f"Direct sync done: {stats['imported']} imported.",
            details=stats,
        )
        return stats

    # ── File-based path (any OS) ──────────────────────────────────────────────

    def run_from_file(self, file_content: str, file_format: str = "html") -> dict:
        from .models import MT5ConnectionLog
        stats = {"total": 0, "imported": 0, "skipped": 0, "failed": 0}

        try:
            raw = MT5ReportParser.parse(file_content, file_format)
            stats["total"] = len(raw)
            if not raw:
                self._fail("No valid trades found in the uploaded file. "
                           "Make sure you export a Detailed Report from MT5.")
                return stats
            self._save_trades(raw, stats)

        except Exception as exc:
            logger.error("MT5 file import: %s", exc, exc_info=True)
            self._fail(str(exc))
            raise
        finally:
            self._finalise(stats)

        MT5ConnectionLog.objects.create(
            account=self.account, log_type="SYNC",
            message=f"File import done: {stats['imported']} imported.",
            details=stats,
        )
        return stats

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _save_trades(self, raw_trades: list[dict], stats: dict) -> None:
        from trades.models import Trade

        for t in raw_trades:
            try:
                if not t.get("symbol") or not t.get("entry_price") or not t.get("exit_price"):
                    stats["skipped"] += 1
                    continue

                ticket = t.get("ticket")
                if ticket and Trade.objects.filter(user=self.user, mt5_ticket=ticket).exists():
                    stats["skipped"] += 1
                    continue

                profit_loss = _safe_decimal(
                    (t.get("profit") or 0) + (t.get("swap") or 0) + (t.get("commission") or 0),
                    places=2,
                )
                Trade.objects.create(
                    user=self.user,
                    mt5_ticket=ticket,
                    mt5_position_id=t.get("position_id"),
                    symbol=t["symbol"],
                    trade_type=t["trade_type"],
                    entry_price=_safe_decimal(t["entry_price"], 5),
                    exit_price=_safe_decimal(t["exit_price"], 5),
                    position_size=_safe_decimal(t.get("volume"), 2),
                    profit_loss=profit_loss,
                    swap=_safe_decimal(t.get("swap"), 2),
                    commission=_safe_decimal(t.get("commission"), 2),
                    status="CLOSED",
                    entry_date=t.get("entry_time") or timezone.now(),
                    exit_date=t.get("exit_time")  or timezone.now(),
                    notes=t.get("comment", ""),
                )
                stats["imported"] += 1

            except Exception as exc:
                logger.warning("Failed to save trade ticket=%s: %s", t.get("ticket"), exc)
                stats["failed"] += 1

    def _update_account_from_info(self, info: dict) -> None:
        self.account.balance        = info["balance"]
        self.account.equity         = info["equity"]
        self.account.margin         = info["margin"]
        self.account.free_margin    = info["free_margin"]
        self.account.margin_level   = info["margin_level"]
        self.account.status         = "CONNECTED"
        self.account.last_connected = timezone.now()
        self.account.last_error     = None
        self.account.save(update_fields=[
            "balance", "equity", "margin", "free_margin",
            "margin_level", "status", "last_connected", "last_error",
        ])

    def _finalise(self, stats: dict) -> None:
        self.import_record.total_trades    = stats["total"]
        self.import_record.imported_trades = stats["imported"]
        self.import_record.skipped_trades  = stats["skipped"]
        self.import_record.failed_trades   = stats["failed"]
        self.import_record.completed_at    = timezone.now()
        if self.import_record.status == "RUNNING":
            self.import_record.status = "COMPLETED"
        self.import_record.save()

    def _fail(self, message: str) -> None:
        self.import_record.status        = "FAILED"
        self.import_record.error_message = message
        self.import_record.completed_at  = timezone.now()
        self.import_record.save(update_fields=["status", "error_message", "completed_at"])
        
        """
MT5 Integration Service Layer
─────────────────────────────
Two import strategies:

  1. MT5Service        – Direct connection via MetaTrader5 Python library.
                         Windows only (requires MT5 terminal running).
                         Returns 503 on Linux — use strategy 2 instead.

  2. MT5ReportParser   – Parses the HTML/CSV report exported from MT5's
                         History tab.  Works on any OS (Linux, macOS, Windows).
                         This is the primary path for Linux/cloud servers.

How to export from MT5:
  Terminal (Ctrl+T) → History tab → right-click → Save as Detailed Report → HTML
"""

import csv
import io
import logging
import platform
from datetime import datetime, timezone as dt_tz
from decimal import Decimal, InvalidOperation

from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Try importing the MT5 library (Windows-only) ─────────────────────────────

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    if platform.system() != "Windows":
        logger.info(
            "MetaTrader5 library unavailable on %s — file-based import will be used.",
            platform.system(),
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _safe_decimal(value, places: int = 5, fallback=Decimal("0")) -> Decimal:
    try:
        if value is None or str(value).strip() in ("", "-", "—"):
            return fallback
        cleaned = str(value).replace(" ", "").replace(",", "")
        return Decimal(str(round(float(cleaned), places)))
    except (TypeError, ValueError, InvalidOperation):
        return fallback


def _mt5_time_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=dt_tz.utc)


def _parse_mt5_datetime(value: str) -> datetime | None:
    """Parse MT5 report date strings like '2024.01.15 08:30:00'."""
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=dt_tz.utc)
        except (ValueError, AttributeError):
            continue
    return None


# ─── Errors ──────────────────────────────────────────────────────────────────

class MT5Error(Exception):
    def __init__(self, message: str, code: int = 0):
        self.code = code
        super().__init__(message)

class MT5NotAvailableError(MT5Error):
    pass

class MT5AuthError(MT5Error):
    pass


# ─── Direct MT5 connection (Windows only) ────────────────────────────────────

class MT5Service:
    """
    Wraps MetaTrader5 library calls.  Context-manager usage:

        with MT5Service(account) as svc:
            info   = svc.get_account_info()
            trades = svc.get_history(date_from, date_to)
    """

    DEAL_TYPE_BUY  = 0
    DEAL_TYPE_SELL = 1
    DEAL_ENTRY_IN  = 0
    DEAL_ENTRY_OUT = 1

    def __init__(self, account_obj):
        self._account   = account_obj
        self._connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def connect(self) -> None:
        if not MT5_AVAILABLE:
            raise MT5NotAvailableError(
                f"MetaTrader5 library is not available on {platform.system()}. "
                "Use file-based import (HTML/CSV) instead.",
                code=-1,
            )

        if not mt5.initialize():
            code, msg = mt5.last_error()
            raise MT5Error(f"mt5.initialize() failed: {msg}", code=code)

        logger.debug(
            "Attempting MT5 login → account=%s | server=%s | password_set=%s",
            self._account.account_number,
            self._account.server,
            bool(self._account.password),
        )

        ok = mt5.login(
            login=int(self._account.account_number),
            password=self._account.password,
            server=self._account.server,
        )
        if not ok:
            code, msg = mt5.last_error()
            mt5.shutdown()
            raise MT5AuthError(
                f"mt5.login() failed for account={self._account.account_number} "
                f"on server={self._account.server}: {msg}",
                code=code,
            )

        self._connected = True

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False

    def _require_connection(self):
        if not self._connected:
            raise MT5Error("Not connected. Use MT5Service as a context manager.")

    def get_account_info(self) -> dict:
        self._require_connection()
        info = mt5.account_info()
        if info is None:
            code, msg = mt5.last_error()
            raise MT5Error(f"account_info() failed: {msg}", code=code)
        return {
            "balance":          _safe_decimal(info.balance, 2),
            "equity":           _safe_decimal(info.equity, 2),
            "margin":           _safe_decimal(info.margin, 2),
            "free_margin":      _safe_decimal(info.margin_free, 2),
            "margin_level":     _safe_decimal(info.margin_level, 2),
            "currency":         info.currency,
            "leverage":         info.leverage,
            "server":           info.server,
            "name":             info.name,
            "company":          info.company,
            "is_trade_allowed": bool(info.trade_allowed),
        }

    def get_open_positions(self) -> list[dict]:
        self._require_connection()
        positions = mt5.positions_get() or []
        return [
            {
                "ticket":        p.ticket,
                "symbol":        p.symbol,
                "trade_type":    "BUY" if p.type == 0 else "SELL",
                "volume":        _safe_decimal(p.volume, 2),
                "entry_price":   _safe_decimal(p.price_open, 5),
                "current_price": _safe_decimal(p.price_current, 5),
                "sl":            _safe_decimal(p.sl, 5),
                "tp":            _safe_decimal(p.tp, 5),
                "profit":        _safe_decimal(p.profit, 2),
                "swap":          _safe_decimal(p.swap, 2),
                "open_time":     _mt5_time_to_dt(p.time),
                "comment":       p.comment,
                "magic":         p.magic,
            }
            for p in positions
        ]

    def get_history(self, date_from: datetime, date_to: datetime) -> list[dict]:
        self._require_connection()
        if date_from.tzinfo is None:
            date_from = date_from.replace(tzinfo=dt_tz.utc)
        if date_to.tzinfo is None:
            date_to = date_to.replace(tzinfo=dt_tz.utc)

        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            return []

        positions: dict[int, dict] = {}
        for deal in deals:
            pid = deal.position_id
            if deal.entry == self.DEAL_ENTRY_IN:
                positions[pid] = {
                    "ticket":      deal.ticket,
                    "position_id": pid,
                    "symbol":      deal.symbol,
                    "trade_type":  "BUY" if deal.type == self.DEAL_TYPE_BUY else "SELL",
                    "volume":      deal.volume,
                    "entry_price": deal.price,
                    "entry_time":  _mt5_time_to_dt(deal.time),
                    "commission":  deal.commission,
                    "swap":        0.0,
                    "profit":      0.0,
                    "exit_price":  None,
                    "exit_time":   None,
                    "comment":     deal.comment,
                    "magic":       deal.magic,
                }
            elif deal.entry == self.DEAL_ENTRY_OUT:
                if pid not in positions:
                    positions[pid] = {
                        "ticket":      deal.ticket,
                        "position_id": pid,
                        "symbol":      deal.symbol,
                        "trade_type":  "SELL" if deal.type == self.DEAL_TYPE_BUY else "BUY",
                        "volume":      deal.volume,
                        "entry_price": None,
                        "entry_time":  None,
                        "commission":  deal.commission,
                        "swap":        deal.swap,
                        "profit":      deal.profit,
                        "exit_price":  deal.price,
                        "exit_time":   _mt5_time_to_dt(deal.time),
                        "comment":     deal.comment,
                        "magic":       deal.magic,
                    }
                else:
                    positions[pid]["exit_price"]  = deal.price
                    positions[pid]["exit_time"]   = _mt5_time_to_dt(deal.time)
                    positions[pid]["profit"]     += deal.profit
                    positions[pid]["swap"]       += deal.swap
                    positions[pid]["commission"] += deal.commission

        return [
            t for t in positions.values()
            if t["entry_price"] is not None and t["exit_price"] is not None
        ]


# ─── File-based parser (cross-platform) ──────────────────────────────────────

class MT5ReportParser:
    """
    Parses the HTML or CSV trade history exported by MT5.

    MT5 HTML "Detailed Report" columns (0-indexed):
      0: Ticket | 1: Open Time | 2: Type | 3: Size | 4: Symbol |
      5: Price  | 6: S/L      | 7: T/P  | 8: Close Time        |
      9: Price  | 10: Commission | 11: Swap | 12: Profit | 13: Balance | 14: Comment
    """

    TYPE_MAP = {
        "buy":        "BUY",
        "sell":       "SELL",
        "buy limit":  "BUY",
        "sell limit": "SELL",
        "buy stop":   "BUY",
        "sell stop":  "SELL",
    }

    @classmethod
    def parse(cls, content: str, file_format: str) -> list[dict]:
        if file_format == "csv":
            return cls.parse_csv(content)
        return cls.parse_html(content)

    @classmethod
    def parse_html(cls, content: str) -> list[dict]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise MT5Error(
                "beautifulsoup4 is required for HTML parsing. "
                "Run: pip install beautifulsoup4"
            )

        soup = BeautifulSoup(content, "html.parser")
        rows = []

        for table in soup.find_all("table"):
            headers_text = " ".join(
                th.get_text(strip=True).lower() for th in table.find_all("th")
            )
            # Only process the trades table (has both 'symbol' and 'profit' headers)
            if "symbol" not in headers_text or "profit" not in headers_text:
                continue

            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) < 13:
                    continue
                trade_type_raw = cells[2].strip().lower()
                if trade_type_raw not in cls.TYPE_MAP:
                    continue
                row = cls._cells_to_dict(cells)
                if row:
                    rows.append(row)

        logger.info("MT5ReportParser HTML: %d trades parsed", len(rows))
        return rows

    @classmethod
    def parse_csv(cls, content: str) -> list[dict]:
        reader = csv.reader(io.StringIO(content.strip()))
        rows   = []
        header_skipped = False

        for cells in reader:
            if not cells:
                continue
            if not header_skipped:
                header_skipped = True
                # Skip the header row (first cell won't be a digit)
                if not cells[0].strip().isdigit():
                    continue
            if len(cells) < 13:
                continue
            trade_type_raw = cells[2].strip().lower()
            if trade_type_raw not in cls.TYPE_MAP:
                continue
            row = cls._cells_to_dict(cells)
            if row:
                rows.append(row)

        logger.info("MT5ReportParser CSV: %d trades parsed", len(rows))
        return rows

    @classmethod
    def _cells_to_dict(cls, cells: list[str]) -> dict | None:
        """Convert a row of cell strings to a normalised trade dict."""
        try:
            ticket_raw = cells[0].strip()
            ticket     = int(ticket_raw) if ticket_raw.isdigit() else None

            entry_price_raw = cells[5].strip()
            exit_price_raw  = cells[9].strip()

            # Skip rows with no prices (e.g. balance/deposit rows)
            if not entry_price_raw or not exit_price_raw:
                return None

            return {
                "ticket":      ticket,
                "symbol":      cells[4].strip().upper(),
                "trade_type":  cls.TYPE_MAP.get(cells[2].strip().lower(), "BUY"),
                "volume":      float(cells[3]) if cells[3].strip() else 0.0,
                "entry_price": float(entry_price_raw),
                "entry_time":  _parse_mt5_datetime(cells[1]),
                "exit_price":  float(exit_price_raw),
                "exit_time":   _parse_mt5_datetime(cells[8]),
                "commission":  float(cells[10]) if cells[10].strip() else 0.0,
                "swap":        float(cells[11]) if cells[11].strip() else 0.0,
                "profit":      float(cells[12]) if cells[12].strip() else 0.0,
                "comment":     cells[14].strip() if len(cells) > 14 else "",
            }
        except (IndexError, ValueError) as exc:
            logger.debug("_cells_to_dict skipped row: %s | error: %s", cells, exc)
            return None


# ─── Trade importer (shared by direct and file-based paths) ──────────────────

class MT5TradeImporter:
    """
    Persists parsed trade dicts to the Trade model.
    Used by both MT5SyncTradesView (Windows direct) and MT5FileImportView (any OS).
    """

    def __init__(self, user, account_obj, import_record):
        self.user          = user
        self.account       = account_obj
        self.import_record = import_record

    # ── Direct path (Windows MT5 library) ────────────────────────────────────

    def run_direct(self, date_from: datetime, date_to: datetime) -> dict:
        from .models import MT5ConnectionLog
        stats = {"total": 0, "imported": 0, "skipped": 0, "failed": 0}

        try:
            with MT5Service(self.account) as svc:
                self._update_account_from_info(svc.get_account_info())
                raw = svc.get_history(date_from, date_to)
                stats["total"] = len(raw)
                self._save_trades(raw, stats)

        except (MT5NotAvailableError, MT5AuthError, MT5Error) as exc:
            self._fail(str(exc))
            self.account.status     = "ERROR"
            self.account.last_error = str(exc)
            self.account.save(update_fields=["status", "last_error"])
            MT5ConnectionLog.objects.create(
                account=self.account,
                log_type="ERROR",
                message=str(exc),
                details={"code": getattr(exc, "code", 0)},
            )
            raise
        except Exception as exc:
            logger.error("MT5 direct sync error: %s", exc, exc_info=True)
            self._fail(str(exc))
            raise
        finally:
            self._finalise(stats)

        MT5ConnectionLog.objects.create(
            account=self.account,
            log_type="SYNC",
            message=f"Direct sync complete: {stats['imported']} imported, {stats['skipped']} skipped.",
            details=stats,
        )
        return stats

    # ── File-based path (any OS) ──────────────────────────────────────────────

    def run_from_file(self, file_content: str, file_format: str = "html") -> dict:
        from .models import MT5ConnectionLog
        stats = {"total": 0, "imported": 0, "skipped": 0, "failed": 0}

        try:
            raw = MT5ReportParser.parse(file_content, file_format)
            stats["total"] = len(raw)

            if not raw:
                self._fail(
                    "No valid trades found in the uploaded file. "
                    "Make sure you export a Detailed Report from MT5 "
                    "(History tab → right-click → Save as Detailed Report)."
                )
                return stats

            self._save_trades(raw, stats)

        except Exception as exc:
            logger.error("MT5 file import error: %s", exc, exc_info=True)
            self._fail(str(exc))
            raise
        finally:
            self._finalise(stats)

        MT5ConnectionLog.objects.create(
            account=self.account,
            log_type="SYNC",
            message=f"File import complete: {stats['imported']} imported, {stats['skipped']} skipped.",
            details=stats,
        )
        return stats

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _save_trades(self, raw_trades: list[dict], stats: dict) -> None:
        from trades.models import Trade

        for t in raw_trades:
            try:
                # Skip incomplete trades
                if not t.get("symbol") or not t.get("entry_price") or not t.get("exit_price"):
                    logger.debug("Skipping trade (missing required fields): %s", t)
                    stats["skipped"] += 1
                    continue

                ticket = t.get("ticket")

                # Skip duplicates by MT5 ticket number
                if ticket and Trade.objects.filter(user=self.user, mt5_ticket=ticket).exists():
                    logger.debug("Skipping duplicate ticket=%s", ticket)
                    stats["skipped"] += 1
                    continue

                # Net profit = raw profit + swap + commission
                profit_loss = _safe_decimal(
                    (t.get("profit") or 0)
                    + (t.get("swap") or 0)
                    + (t.get("commission") or 0),
                    places=2,
                )

                # Build only the fields that exist on the Trade model.
                # NOTE: mt5_position_id is intentionally excluded — it does not
                # exist on the Trade model. Add a migration if you need it.
                Trade.objects.create(
                    user=self.user,
                    mt5_ticket=ticket,
                    symbol=t["symbol"],
                    trade_type=t["trade_type"],
                    entry_price=_safe_decimal(t["entry_price"], 5),
                    exit_price=_safe_decimal(t["exit_price"], 5),
                    position_size=_safe_decimal(t.get("volume"), 2),
                    profit_loss=profit_loss,
                    swap=_safe_decimal(t.get("swap"), 2),
                    commission=_safe_decimal(t.get("commission"), 2),
                    status="CLOSED",
                    entry_date=t.get("entry_time") or timezone.now(),
                    exit_date=t.get("exit_time") or timezone.now(),
                    notes=t.get("comment", ""),
                )
                stats["imported"] += 1
                logger.debug("Imported ticket=%s symbol=%s", ticket, t["symbol"])

            except Exception as exc:
                logger.warning(
                    "Failed to save trade ticket=%s symbol=%s: %s",
                    t.get("ticket"), t.get("symbol"), exc,
                )
                stats["failed"] += 1

    def _update_account_from_info(self, info: dict) -> None:
        self.account.balance        = info["balance"]
        self.account.equity         = info["equity"]
        self.account.margin         = info["margin"]
        self.account.free_margin    = info["free_margin"]
        self.account.margin_level   = info["margin_level"]
        self.account.status         = "CONNECTED"
        self.account.last_connected = timezone.now()
        self.account.last_error     = None
        self.account.save(update_fields=[
            "balance", "equity", "margin", "free_margin",
            "margin_level", "status", "last_connected", "last_error",
        ])

    def _finalise(self, stats: dict) -> None:
        self.import_record.total_trades    = stats["total"]
        self.import_record.imported_trades = stats["imported"]
        self.import_record.skipped_trades  = stats["skipped"]
        self.import_record.failed_trades   = stats["failed"]
        self.import_record.completed_at    = timezone.now()
        if self.import_record.status == "RUNNING":
            self.import_record.status = "COMPLETED"
        self.import_record.save()

    def _fail(self, message: str) -> None:
        self.import_record.status        = "FAILED"
        self.import_record.error_message = message
        self.import_record.completed_at  = timezone.now()
        self.import_record.save(update_fields=["status", "error_message", "completed_at"])







        """
MT5 Integration Service Layer
─────────────────────────────
Two import strategies:

  1. MT5Service        – Direct connection via MetaTrader5 Python library.
                         Windows only (requires MT5 terminal running).
                         Returns 503 on Linux — use strategy 2 instead.

  2. MT5ReportParser   – Parses the HTML/CSV report exported from MT5's
                         History tab.  Works on any OS (Linux, macOS, Windows).
                         This is the primary path for Linux/cloud servers.

How to export from MT5:
  Terminal (Ctrl+T) → History tab → right-click → Save as Detailed Report → HTML

P&L note:
  MT5 provides deal.profit, deal.swap, deal.commission for every closed deal.
  We sum these three values and store them directly as profit_loss.
  We do NOT recalculate from price diff — that would be wrong for non-USD-quote
  pairs and broker-specific CFD contracts.  The Trade.save() method is aware of
  this and skips its own recalculation when mt5_ticket is set.
"""

import csv
import io
import logging
import platform
from datetime import datetime, timezone as dt_tz
from decimal import Decimal, InvalidOperation

from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Try importing the MT5 library (Windows-only) ─────────────────────────────

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    if platform.system() != "Windows":
        logger.info(
            "MetaTrader5 library unavailable on %s — file-based import will be used.",
            platform.system(),
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _safe_decimal(value, places: int = 5, fallback=Decimal("0")) -> Decimal:
    try:
        if value is None or str(value).strip() in ("", "-", "—"):
            return fallback
        cleaned = str(value).replace(" ", "").replace(",", "")
        return Decimal(str(round(float(cleaned), places)))
    except (TypeError, ValueError, InvalidOperation):
        return fallback


def _mt5_time_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=dt_tz.utc)


def _parse_mt5_datetime(value: str) -> datetime | None:
    """Parse MT5 report date strings like '2024.01.15 08:30:00'."""
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=dt_tz.utc)
        except (ValueError, AttributeError):
            continue
    return None


# ─── Errors ──────────────────────────────────────────────────────────────────

class MT5Error(Exception):
    def __init__(self, message: str, code: int = 0):
        self.code = code
        super().__init__(message)

class MT5NotAvailableError(MT5Error):
    pass

class MT5AuthError(MT5Error):
    pass


# ─── Direct MT5 connection (Windows only) ────────────────────────────────────

class MT5Service:
    """
    Wraps MetaTrader5 library calls.  Context-manager usage:

        with MT5Service(account) as svc:
            info   = svc.get_account_info()
            trades = svc.get_history(date_from, date_to)
    """

    DEAL_TYPE_BUY  = 0
    DEAL_TYPE_SELL = 1
    DEAL_ENTRY_IN    = 0   # position opened
    DEAL_ENTRY_OUT   = 1   # position closed
    DEAL_ENTRY_INOUT = 2   # instant execution — opens AND closes in one deal
                           # common on CFD brokers (symbols ending with !)

    def __init__(self, account_obj):
        self._account   = account_obj
        self._connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def connect(self) -> None:
        if not MT5_AVAILABLE:
            raise MT5NotAvailableError(
                f"MetaTrader5 library is not available on {platform.system()}. "
                "Use file-based import (HTML/CSV) instead.",
                code=-1,
            )

        if not mt5.initialize():
            code, msg = mt5.last_error()
            raise MT5Error(f"mt5.initialize() failed: {msg}", code=code)

        logger.debug(
            "Attempting MT5 login → account=%s | server=%s | password_set=%s",
            self._account.account_number,
            self._account.server,
            bool(self._account.password),
        )

        ok = mt5.login(
            login=int(self._account.account_number),
            password=self._account.password,
            server=self._account.server,
        )
        if not ok:
            code, msg = mt5.last_error()
            mt5.shutdown()
            raise MT5AuthError(
                f"mt5.login() failed for account={self._account.account_number} "
                f"on server={self._account.server}: {msg}",
                code=code,
            )

        self._connected = True

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False

    def _require_connection(self):
        if not self._connected:
            raise MT5Error("Not connected. Use MT5Service as a context manager.")

    def get_account_info(self) -> dict:
        self._require_connection()
        info = mt5.account_info()
        if info is None:
            code, msg = mt5.last_error()
            raise MT5Error(f"account_info() failed: {msg}", code=code)
        return {
            "balance":          _safe_decimal(info.balance, 2),
            "equity":           _safe_decimal(info.equity, 2),
            "margin":           _safe_decimal(info.margin, 2),
            "free_margin":      _safe_decimal(info.margin_free, 2),
            "margin_level":     _safe_decimal(info.margin_level, 2),
            "currency":         info.currency,
            "leverage":         info.leverage,
            "server":           info.server,
            "name":             info.name,
            "company":          info.company,
            "is_trade_allowed": bool(info.trade_allowed),
        }

    def get_open_positions(self) -> list[dict]:
        self._require_connection()
        positions = mt5.positions_get() or []
        return [
            {
                "ticket":        p.ticket,
                "symbol":        p.symbol,
                "trade_type":    "BUY" if p.type == 0 else "SELL",
                "volume":        _safe_decimal(p.volume, 2),
                "entry_price":   _safe_decimal(p.price_open, 5),
                "current_price": _safe_decimal(p.price_current, 5),
                "sl":            _safe_decimal(p.sl, 5),
                "tp":            _safe_decimal(p.tp, 5),
                "profit":        _safe_decimal(p.profit, 2),
                "swap":          _safe_decimal(p.swap, 2),
                "open_time":     _mt5_time_to_dt(p.time),
                "comment":       p.comment,
                "magic":         p.magic,
            }
            for p in positions
        ]

    def get_history(self, date_from: datetime, date_to: datetime) -> list[dict]:
        """
        Fetch closed trade history and group deals into complete round-trip trades.

        Handles all three MT5 deal entry types:
          DEAL_ENTRY_IN    (0) – opening deal
          DEAL_ENTRY_OUT   (1) – closing deal  ← profit lives here
          DEAL_ENTRY_INOUT (2) – instant exec (open+close in one deal)
                                  Used by many CFD brokers; profit is on the deal itself.

        IMPORTANT: profit, swap, and commission are accumulated from the OUT
        deal(s) only.  The IN deal has profit=0 in MT5.
        """
        self._require_connection()
        if date_from.tzinfo is None:
            date_from = date_from.replace(tzinfo=dt_tz.utc)
        if date_to.tzinfo is None:
            date_to = date_to.replace(tzinfo=dt_tz.utc)

        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            logger.warning("history_deals_get returned None — possible MT5 API error.")
            return []

        logger.debug("MT5 history: %d raw deals fetched", len(deals))

        positions: dict[int, dict] = {}

        for deal in deals:
            pid = deal.position_id

            if deal.entry == self.DEAL_ENTRY_INOUT:
                # ── Instant execution: single deal is both open and close ───
                # profit, swap, commission are all on this deal.
                positions[pid] = {
                    "ticket":      deal.ticket,
                    "symbol":      deal.symbol,
                    "trade_type":  "BUY" if deal.type == self.DEAL_TYPE_BUY else "SELL",
                    "volume":      deal.volume,
                    "entry_price": deal.price,
                    "entry_time":  _mt5_time_to_dt(deal.time),
                    "exit_price":  deal.price,
                    "exit_time":   _mt5_time_to_dt(deal.time),
                    "commission":  deal.commission,
                    "swap":        deal.swap,
                    "profit":      deal.profit,   # ← real P&L
                    "comment":     deal.comment,
                    "magic":       deal.magic,
                }

            elif deal.entry == self.DEAL_ENTRY_IN:
                # ── Opening deal — profit is always 0 here in MT5 ───────────
                positions[pid] = {
                    "ticket":      deal.ticket,
                    "symbol":      deal.symbol,
                    "trade_type":  "BUY" if deal.type == self.DEAL_TYPE_BUY else "SELL",
                    "volume":      deal.volume,
                    "entry_price": deal.price,
                    "entry_time":  _mt5_time_to_dt(deal.time),
                    "exit_price":  None,
                    "exit_time":   None,
                    "commission":  deal.commission,
                    "swap":        0.0,
                    "profit":      0.0,
                    "comment":     deal.comment,
                    "magic":       deal.magic,
                }

            elif deal.entry == self.DEAL_ENTRY_OUT:
                # ── Closing deal — profit, swap, commission are HERE ─────────
                if pid not in positions:
                    # OUT arrived before IN (partial history window)
                    positions[pid] = {
                        "ticket":      deal.ticket,
                        "symbol":      deal.symbol,
                        "trade_type":  "SELL" if deal.type == self.DEAL_TYPE_BUY else "BUY",
                        "volume":      deal.volume,
                        "entry_price": None,
                        "entry_time":  None,
                        "exit_price":  deal.price,
                        "exit_time":   _mt5_time_to_dt(deal.time),
                        "commission":  deal.commission,
                        "swap":        deal.swap,
                        "profit":      deal.profit,
                        "comment":     deal.comment,
                        "magic":       deal.magic,
                    }
                else:
                    # Merge closing data into the existing position
                    positions[pid]["exit_price"]   = deal.price
                    positions[pid]["exit_time"]    = _mt5_time_to_dt(deal.time)
                    positions[pid]["profit"]      += deal.profit      # ← accumulate
                    positions[pid]["swap"]        += deal.swap
                    positions[pid]["commission"]  += deal.commission

        # Only return fully-formed trades (have both entry and exit prices)
        result = [
            t for t in positions.values()
            if t["entry_price"] is not None and t["exit_price"] is not None
        ]
        logger.debug("MT5 history: %d complete trades after grouping", len(result))
        return result


# ─── File-based parser (cross-platform) ──────────────────────────────────────

class MT5ReportParser:
    """
    Parses the HTML or CSV Detailed Report exported from MT5.

    MT5 "Detailed Report" column layout (0-indexed):
      0  Ticket
      1  Open Time
      2  Type        (buy / sell / buy limit / …)
      3  Size        (lots)
      4  Symbol
      5  Price       (entry)
      6  S/L
      7  T/P
      8  Close Time
      9  Price       (exit)
      10 Commission
      11 Swap
      12 Profit      ← NET profit from broker (already correct)
      13 Balance
      14 Comment
    """

    TYPE_MAP = {
        "buy":        "BUY",
        "sell":       "SELL",
        "buy limit":  "BUY",
        "sell limit": "SELL",
        "buy stop":   "BUY",
        "sell stop":  "SELL",
    }

    @classmethod
    def parse(cls, content: str, file_format: str) -> list[dict]:
        if file_format == "csv":
            return cls.parse_csv(content)
        return cls.parse_html(content)

    @classmethod
    def parse_html(cls, content: str) -> list[dict]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise MT5Error(
                "beautifulsoup4 is required for HTML parsing. "
                "Run: pip install beautifulsoup4"
            )

        soup = BeautifulSoup(content, "html.parser")
        rows = []

        for table in soup.find_all("table"):
            headers_text = " ".join(
                th.get_text(strip=True).lower() for th in table.find_all("th")
            )
            if "symbol" not in headers_text or "profit" not in headers_text:
                continue

            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) < 13:
                    continue
                trade_type_raw = cells[2].strip().lower()
                if trade_type_raw not in cls.TYPE_MAP:
                    continue
                row = cls._cells_to_dict(cells)
                if row:
                    rows.append(row)

        logger.info("MT5ReportParser HTML: %d trades parsed", len(rows))
        return rows

    @classmethod
    def parse_csv(cls, content: str) -> list[dict]:
        reader         = csv.reader(io.StringIO(content.strip()))
        rows           = []
        header_skipped = False

        for cells in reader:
            if not cells:
                continue
            if not header_skipped:
                header_skipped = True
                if not cells[0].strip().isdigit():
                    continue
            if len(cells) < 13:
                continue
            trade_type_raw = cells[2].strip().lower()
            if trade_type_raw not in cls.TYPE_MAP:
                continue
            row = cls._cells_to_dict(cells)
            if row:
                rows.append(row)

        logger.info("MT5ReportParser CSV: %d trades parsed", len(rows))
        return rows

    @classmethod
    def _cells_to_dict(cls, cells: list[str]) -> dict | None:
        """
        Convert a row of cell strings to a normalised trade dict.

        Profit at cells[12] is the broker's net figure — we store it directly.
        Commission (cells[10]) and swap (cells[11]) are stored separately for
        display; they are already included in cells[12] by MT5.
        """
        try:
            ticket_raw      = cells[0].strip()
            ticket          = int(ticket_raw) if ticket_raw.isdigit() else None
            entry_price_raw = cells[5].strip()
            exit_price_raw  = cells[9].strip()

            if not entry_price_raw or not exit_price_raw:
                return None   # balance / deposit rows have no price

            commission = float(cells[10]) if cells[10].strip() else 0.0
            swap       = float(cells[11]) if cells[11].strip() else 0.0
            # cells[12] = broker's net profit (already includes swap+commission
            # in some MT5 versions). We store it as-is; _save_trades uses it
            # directly rather than re-summing components.
            profit_raw = cells[12].strip()
            profit     = float(profit_raw) if profit_raw else 0.0

            return {
                "ticket":      ticket,
                "symbol":      cells[4].strip().upper(),
                "trade_type":  cls.TYPE_MAP.get(cells[2].strip().lower(), "BUY"),
                "volume":      float(cells[3]) if cells[3].strip() else 0.0,
                "entry_price": float(entry_price_raw),
                "entry_time":  _parse_mt5_datetime(cells[1]),
                "exit_price":  float(exit_price_raw),
                "exit_time":   _parse_mt5_datetime(cells[8]),
                "commission":  commission,
                "swap":        swap,
                # For file import, cells[12] is the broker's complete net profit.
                # We expose it as "profit" and will NOT add swap/commission again.
                "profit":      profit,
                "profit_is_net": True,   # flag: don't re-add swap/commission
                "comment":     cells[14].strip() if len(cells) > 14 else "",
            }
        except (IndexError, ValueError) as exc:
            logger.debug("_cells_to_dict skipped row: %s | error: %s", cells, exc)
            return None


# ─── Trade importer (shared by direct and file-based paths) ──────────────────

class MT5TradeImporter:
    """
    Persists parsed trade dicts to the Trade model.
    Used by both MT5SyncTradesView (Windows direct) and MT5FileImportView (any OS).
    """

    def __init__(self, user, account_obj, import_record):
        self.user          = user
        self.account       = account_obj
        self.import_record = import_record

    # ── Direct path (Windows MT5 library) ────────────────────────────────────

    def run_direct(self, date_from: datetime, date_to: datetime) -> dict:
        from .models import MT5ConnectionLog
        stats = {"total": 0, "imported": 0, "skipped": 0, "failed": 0}

        try:
            with MT5Service(self.account) as svc:
                self._update_account_from_info(svc.get_account_info())
                raw = svc.get_history(date_from, date_to)
                stats["total"] = len(raw)
                self._save_trades(raw, stats, profit_is_net=False)

        except (MT5NotAvailableError, MT5AuthError, MT5Error) as exc:
            self._fail(str(exc))
            self.account.status     = "ERROR"
            self.account.last_error = str(exc)
            self.account.save(update_fields=["status", "last_error"])
            MT5ConnectionLog.objects.create(
                account=self.account,
                log_type="ERROR",
                message=str(exc),
                details={"code": getattr(exc, "code", 0)},
            )
            raise
        except Exception as exc:
            logger.error("MT5 direct sync error: %s", exc, exc_info=True)
            self._fail(str(exc))
            raise
        finally:
            self._finalise(stats)

        MT5ConnectionLog.objects.create(
            account=self.account,
            log_type="SYNC",
            message=f"Direct sync complete: {stats['imported']} imported, {stats['skipped']} skipped.",
            details=stats,
        )
        return stats

    # ── File-based path (any OS) ──────────────────────────────────────────────

    def run_from_file(self, file_content: str, file_format: str = "html") -> dict:
        from .models import MT5ConnectionLog
        stats = {"total": 0, "imported": 0, "skipped": 0, "failed": 0}

        try:
            raw = MT5ReportParser.parse(file_content, file_format)
            stats["total"] = len(raw)

            if not raw:
                self._fail(
                    "No valid trades found in the uploaded file. "
                    "Make sure you export a Detailed Report from MT5 "
                    "(History tab → right-click → Save as Detailed Report)."
                )
                return stats

            # File export: cells[12] is already the net broker profit
            self._save_trades(raw, stats, profit_is_net=True)

        except Exception as exc:
            logger.error("MT5 file import error: %s", exc, exc_info=True)
            self._fail(str(exc))
            raise
        finally:
            self._finalise(stats)

        MT5ConnectionLog.objects.create(
            account=self.account,
            log_type="SYNC",
            message=f"File import complete: {stats['imported']} imported, {stats['skipped']} skipped.",
            details=stats,
        )
        return stats

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _save_trades(self, raw_trades: list[dict], stats: dict, profit_is_net: bool = False) -> None:
        """
        Persist trade dicts to the Trade model.

        profit_is_net=True  → t["profit"] already includes swap+commission (file import).
        profit_is_net=False → profit, swap, commission are separate (direct MT5 sync);
                              we sum them here for the net profit_loss field.

        In both cases, profit_loss stored = the authoritative net figure from MT5.
        Trade.save() will NOT recalculate this because mt5_ticket is set.
        """
        from trades.models import Trade

        for t in raw_trades:
            try:
                if not t.get("symbol") or not t.get("entry_price") or not t.get("exit_price"):
                    logger.debug("Skipping trade (missing required fields): %s", t)
                    stats["skipped"] += 1
                    continue

                ticket = t.get("ticket")
                if ticket and Trade.objects.filter(user=self.user, mt5_ticket=ticket).exists():
                    logger.debug("Skipping duplicate ticket=%s", ticket)
                    stats["skipped"] += 1
                    continue

                raw_profit     = t.get("profit")     or 0
                raw_swap       = t.get("swap")        or 0
                raw_commission = t.get("commission")  or 0

                if profit_is_net or t.get("profit_is_net"):
                    # File export: cells[12] already = net profit (broker figure)
                    profit_loss = _safe_decimal(raw_profit, places=2)
                else:
                    # Direct MT5 API: sum the three components
                    profit_loss = _safe_decimal(
                        raw_profit + raw_swap + raw_commission, places=2
                    )

                Trade.objects.create(
                    user=self.user,
                    mt5_ticket=ticket,
                    symbol=t["symbol"],
                    trade_type=t["trade_type"],
                    entry_price=_safe_decimal(t["entry_price"], 5),
                    exit_price=_safe_decimal(t["exit_price"], 5),
                    position_size=_safe_decimal(t.get("volume"), 2),
                    profit_loss=profit_loss,        # ← real MT5 net profit
                    swap=_safe_decimal(raw_swap, 2),
                    commission=_safe_decimal(raw_commission, 2),
                    status="CLOSED",
                    entry_date=t.get("entry_time") or timezone.now(),
                    exit_date=t.get("exit_time")   or timezone.now(),
                    notes=t.get("comment", ""),
                )
                stats["imported"] += 1
                logger.debug(
                    "Imported ticket=%s symbol=%s profit_loss=%s",
                    ticket, t["symbol"], profit_loss,
                )

            except Exception as exc:
                logger.warning(
                    "Failed to save trade ticket=%s symbol=%s: %s",
                    t.get("ticket"), t.get("symbol"), exc,
                )
                stats["failed"] += 1

    def _update_account_from_info(self, info: dict) -> None:
        self.account.balance        = info["balance"]
        self.account.equity         = info["equity"]
        self.account.margin         = info["margin"]
        self.account.free_margin    = info["free_margin"]
        self.account.margin_level   = info["margin_level"]
        self.account.status         = "CONNECTED"
        self.account.last_connected = timezone.now()
        self.account.last_error     = None
        self.account.save(update_fields=[
            "balance", "equity", "margin", "free_margin",
            "margin_level", "status", "last_connected", "last_error",
        ])

    def _finalise(self, stats: dict) -> None:
        self.import_record.total_trades    = stats["total"]
        self.import_record.imported_trades = stats["imported"]
        self.import_record.skipped_trades  = stats["skipped"]
        self.import_record.failed_trades   = stats["failed"]
        self.import_record.completed_at    = timezone.now()
        if self.import_record.status == "RUNNING":
            self.import_record.status = "COMPLETED"
        self.import_record.save()

    def _fail(self, message: str) -> None:
        self.import_record.status        = "FAILED"
        self.import_record.error_message = message
        self.import_record.completed_at  = timezone.now()
        self.import_record.save(update_fields=["status", "error_message", "completed_at"])