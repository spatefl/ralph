from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0056_baseobject_org_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="is_field_gear",
            field=models.BooleanField(
                default=False,
                help_text="Mark categories that represent portable tools / field gear.",
            ),
        ),
    ]
