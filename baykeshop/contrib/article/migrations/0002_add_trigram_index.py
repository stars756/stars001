from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm",
            reverse_sql="DROP EXTENSION IF EXISTS pg_trgm",
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS article_content_title_trgm_idx "
                "ON article_baykearticlecontent USING GIN (title gin_trgm_ops)"
            ),
            reverse_sql="DROP INDEX IF EXISTS article_content_title_trgm_idx",
        ),
    ]
