# Generated manually — RenameField for clarity

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('member', '0009_add_user_notification'),
    ]

    operations = [
        migrations.RenameField(
            model_name='baykeshopuser',
            old_name='email_verify_at',
            new_name='verification_token_created_at',
        ),
    ]
