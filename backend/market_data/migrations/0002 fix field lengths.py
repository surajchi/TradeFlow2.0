"""
Migration: increase MarketNews.external_id from 100 → 500 chars
           and source_url from URLField default to 500 chars

Run with:  python manage.py migrate market_data
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    # ← Change this to match your last migration file name
    # Check your market_data/migrations/ folder and set this correctly.
    # Example: if your last file is 0001_initial.py use ("market_data", "0001_initial")
    dependencies = [
        ("market_data", "0001_initial"),
    ]

    operations = [
        # external_id: 100 → 500  (RSS entry IDs are full URLs)
        migrations.AlterField(
            model_name="marketnews",
            name="external_id",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        # source_url: URLField default is 200 → raise to 500 to be safe
        migrations.AlterField(
            model_name="marketnews",
            name="source_url",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]