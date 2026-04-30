from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0009_alter_baykeshopgoodsimages_image_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm",
            reverse_sql="DROP EXTENSION IF EXISTS pg_trgm",
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS shop_goods_name_trgm_idx "
                "ON shop_baykeshopgoods USING GIN (name gin_trgm_ops)"
            ),
            reverse_sql="DROP INDEX IF EXISTS shop_goods_name_trgm_idx",
        ),
    ]
