"""
WSGI config for trading_journal project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trading_journal.settings')

application = get_wsgi_application()
