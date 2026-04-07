"""
URL configuration for trading_journal project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/trades/', include('trades.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/journal/', include('journal.urls')),
    path('api/market/', include('market_data.urls')),
    path('api/mt5/', include('mt5_integration.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
