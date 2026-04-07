"""
Celery periodic tasks for automatic market data refresh.

Add to your settings.py CELERY_BEAT_SCHEDULE:

    from celery.schedules import crontab

    CELERY_BEAT_SCHEDULE = {
        'fetch-prices-every-5-min': {
            'task': 'market_data.tasks.fetch_prices',
            'schedule': crontab(minute='*/5'),
        },
        'fetch-news-every-15-min': {
            'task': 'market_data.tasks.fetch_news',
            'schedule': crontab(minute='*/15'),
        },
        'fetch-calendar-daily': {
            'task': 'market_data.tasks.fetch_calendar',
            'schedule': crontab(hour=0, minute=30),   # 00:30 UTC daily
        },
        'cleanup-old-news': {
            'task': 'market_data.tasks.cleanup_old_news',
            'schedule': crontab(hour=2, minute=0),    # 02:00 UTC daily
        },
    }
"""

import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_prices(self):
    """Fetch forex, indices and crypto prices. Run every 5 minutes."""
    try:
        from .services import MarketDataOrchestrator
        counts = MarketDataOrchestrator.update_prices()
        logger.info("Celery fetch_prices done: %s", counts)
        return counts
    except Exception as exc:
        logger.error("fetch_prices task failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def fetch_news(self):
    """Fetch market news from RSS feeds. Run every 15 minutes."""
    try:
        from .services import MarketDataOrchestrator
        saved = MarketDataOrchestrator.update_news()
        logger.info("Celery fetch_news done: %d new articles", saved)
        return {'saved': saved}
    except Exception as exc:
        logger.error("fetch_news task failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def fetch_calendar(self, days_ahead: int = 7):
    """Fetch economic calendar from ForexFactory. Run daily."""
    try:
        from .services import MarketDataOrchestrator
        saved = MarketDataOrchestrator.update_calendar(days_ahead=days_ahead)
        logger.info("Celery fetch_calendar done: %d events", saved)
        return {'saved': saved}
    except Exception as exc:
        logger.error("fetch_calendar task failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task
def cleanup_old_news(days_to_keep: int = 30):
    """Delete news older than N days to keep the DB clean."""
    from .models import MarketNews
    cutoff = timezone.now() - timedelta(days=days_to_keep)
    deleted, _ = MarketNews.objects.filter(published_at__lt=cutoff).delete()
    logger.info("Cleaned up %d old news articles", deleted)
    return {'deleted': deleted}


@shared_task(bind=True, max_retries=3)
def fetch_all(self):
    """Fetch everything at once. Useful for initial data load."""
    try:
        from .services import MarketDataOrchestrator
        result = MarketDataOrchestrator.run()
        logger.info("Celery fetch_all done: %s", result)
        return result
    except Exception as exc:
        logger.error("fetch_all task failed: %s", exc)
        raise self.retry(exc=exc)