"""
Management command: fetch_market_data

Usage examples
--------------
# Fetch everything
python manage.py fetch_market_data

# Fetch only prices
python manage.py fetch_market_data --prices-only

# Fetch only news
python manage.py fetch_market_data --news-only

# Fetch only economic calendar (next 14 days)
python manage.py fetch_market_data --calendar-only --days 14

# Fetch prices + news, skip calendar
python manage.py fetch_market_data --skip-calendar
"""

import time
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Fetch live market data from free external APIs (Yahoo Finance, CoinGecko, RSS, ForexFactory)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--prices-only', action='store_true',
            help='Fetch only market prices (forex, indices, crypto)',
        )
        parser.add_argument(
            '--news-only', action='store_true',
            help='Fetch only market news from RSS feeds',
        )
        parser.add_argument(
            '--calendar-only', action='store_true',
            help='Fetch only the economic calendar from ForexFactory',
        )
        parser.add_argument(
            '--skip-prices', action='store_true',
            help='Skip fetching market prices',
        )
        parser.add_argument(
            '--skip-news', action='store_true',
            help='Skip fetching market news',
        )
        parser.add_argument(
            '--skip-calendar', action='store_true',
            help='Skip fetching economic calendar',
        )
        parser.add_argument(
            '--days', type=int, default=7,
            help='Number of days ahead to fetch calendar events (default: 7)',
        )

    def handle(self, *args, **options):
        from market_data.services import (
            MarketDataOrchestrator,
            ForexService, IndicesService, CryptoService,
            NewsService, EconomicCalendarService,
        )

        prices_only   = options['prices_only']
        news_only     = options['news_only']
        calendar_only = options['calendar_only']

        fetch_prices   = not options['skip_prices']
        fetch_news     = not options['skip_news']
        fetch_calendar = not options['skip_calendar']
        days = options['days']

        # Exclusive flags
        if prices_only:
            fetch_prices, fetch_news, fetch_calendar = True, False, False
        elif news_only:
            fetch_prices, fetch_news, fetch_calendar = False, True, False
        elif calendar_only:
            fetch_prices, fetch_news, fetch_calendar = False, False, True

        self.stdout.write(self.style.NOTICE(
            "\n📡 Starting market data fetch...\n"
            f"   Prices:   {'✓' if fetch_prices   else '✗'}\n"
            f"   News:     {'✓' if fetch_news     else '✗'}\n"
            f"   Calendar: {'✓' if fetch_calendar else '✗'} ({days} days ahead)\n"
        ))

        start = time.time()

        # ── Prices ──────────────────────────────────────────────────────────
        if fetch_prices:
            self.stdout.write("  → Fetching forex prices (Yahoo Finance)...")
            try:
                counts = MarketDataOrchestrator.update_prices()
                self.stdout.write(self.style.SUCCESS(
                    f"     ✓ Prices saved — "
                    f"Forex: {counts['forex']}, "
                    f"Indices: {counts['indices']}, "
                    f"Crypto: {counts['crypto']}"
                ))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"     ✗ Prices failed: {exc}"))

        # ── News ─────────────────────────────────────────────────────────────
        if fetch_news:
            self.stdout.write("  → Fetching news (RSS feeds)...")
            try:
                saved = MarketDataOrchestrator.update_news()
                self.stdout.write(self.style.SUCCESS(f"     ✓ {saved} new articles saved"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"     ✗ News failed: {exc}"))

        # ── Calendar ──────────────────────────────────────────────────────────
        if fetch_calendar:
            self.stdout.write(f"  → Fetching economic calendar (ForexFactory, next {days} days)...")
            try:
                from market_data.services import EconomicCalendarService
                from market_data.models import EconomicEvent

                events = EconomicCalendarService.fetch_calendar(days_ahead=days)
                saved = 0
                for ev in events:
                    try:
                        EconomicEvent.objects.update_or_create(
                            title=ev['title'],
                            event_date=ev['event_date'],
                            currency=ev['currency'],
                            defaults={k: v for k, v in ev.items()
                                      if k not in ('title', 'event_date', 'currency')},
                        )
                        saved += 1
                    except Exception:
                        pass
                self.stdout.write(self.style.SUCCESS(f"     ✓ {saved} calendar events saved"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"     ✗ Calendar failed: {exc}"))

        elapsed = round(time.time() - start, 2)
        self.stdout.write(self.style.SUCCESS(f"\n✅ Done in {elapsed}s\n"))