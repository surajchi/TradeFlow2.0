"""
Celery periodic tasks for automatic MT5 sync.

Add to settings.py CELERY_BEAT_SCHEDULE:

    from celery.schedules import crontab

    CELERY_BEAT_SCHEDULE = {
        'mt5-auto-sync': {
            'task': 'mt5_integration.tasks.auto_sync_all_accounts',
            'schedule': crontab(minute='*/5'),   # every 5 minutes
        },
    }
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def sync_account(self, account_id: str):
    """
    Fetch the latest closed trades for a single MT5Account.
    Date range: last 24 hours (overlapping on purpose to catch late settlements).
    """
    from .models import MT5Account, MT5TradeImport
    from .services import MT5TradeImporter, MT5Error

    try:
        account = MT5Account.objects.get(id=account_id, is_active=True)
    except MT5Account.DoesNotExist:
        logger.warning("sync_account: account %s not found", account_id)
        return

    date_to   = timezone.now()
    date_from = date_to - timedelta(hours=24)

    import_record = MT5TradeImport.objects.create(
        user=account.user,
        account=account,
        status='RUNNING',
        date_from=date_from,
        date_to=date_to,
        started_at=timezone.now(),
    )

    try:
        importer = MT5TradeImporter(account.user, account, import_record)
        stats    = importer.run(date_from, date_to)
        logger.info("sync_account %s: %s", account_id, stats)
        return stats
    except MT5Error as exc:
        logger.error("sync_account MT5 error for %s: %s", account_id, exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error("sync_account unexpected error for %s: %s", account_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task
def auto_sync_all_accounts():
    """
    Dispatch individual sync tasks for every account that has auto_sync=True.
    Called by Celery Beat every N minutes.
    """
    from .models import MT5Account

    accounts = MT5Account.objects.filter(is_active=True, auto_sync=True)
    count = 0
    for account in accounts:
        sync_account.delay(str(account.id))
        count += 1

    logger.info("auto_sync_all_accounts: dispatched %d sync tasks", count)
    return {'dispatched': count}


@shared_task(bind=True, max_retries=2)
def sync_account_range(self, account_id: str, date_from_iso: str, date_to_iso: str):
    """
    Sync a specific historical date range.
    Useful for backfilling or re-importing after fixes.

    date_from_iso / date_to_iso — ISO 8601 strings e.g. '2024-01-01T00:00:00+00:00'
    """
    from datetime import datetime
    from .models import MT5Account, MT5TradeImport
    from .services import MT5TradeImporter, MT5Error

    try:
        account = MT5Account.objects.get(id=account_id, is_active=True)
    except MT5Account.DoesNotExist:
        logger.warning("sync_account_range: account %s not found", account_id)
        return

    date_from = datetime.fromisoformat(date_from_iso)
    date_to   = datetime.fromisoformat(date_to_iso)

    import_record = MT5TradeImport.objects.create(
        user=account.user,
        account=account,
        status='RUNNING',
        date_from=date_from,
        date_to=date_to,
        started_at=timezone.now(),
    )

    try:
        importer = MT5TradeImporter(account.user, account, import_record)
        stats    = importer.run(date_from, date_to)
        logger.info("sync_account_range %s %s→%s: %s", account_id, date_from_iso, date_to_iso, stats)
        return stats
    except MT5Error as exc:
        logger.error("sync_account_range MT5 error: %s", exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error("sync_account_range unexpected error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)