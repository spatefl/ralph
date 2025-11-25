from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0055_location_asset_color_and_project_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="baseobject",
            name="org_location",
            field=models.ForeignKey(
                blank=True,
                help_text="Permanent organizational location (SC3).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="home_assets",
                to="assets.location",
            ),
        ),
    ]
