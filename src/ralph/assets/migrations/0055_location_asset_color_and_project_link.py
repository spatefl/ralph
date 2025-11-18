from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import ralph.lib.mixins.models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0054_project_and_deployment_project_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="Location",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=75, verbose_name="name")),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="date created"
                    ),
                ),
                (
                    "modified",
                    models.DateTimeField(
                        auto_now=True, verbose_name="last modified"
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        help_text="Short unique identifier used by SC3 and reporting.",
                        max_length=64,
                        unique=True,
                    ),
                ),
                (
                    "external_id",
                    models.CharField(
                        blank=True,
                        help_text="Optional external identifier supplied by SC3.",
                        max_length=128,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    "color_hex",
                    models.CharField(
                        blank=True,
                        help_text="Use #RRGGBB hex colors for dashboard badges.",
                        max_length=7,
                        validators=[
                            django.core.validators.RegexValidator(
                                code="invalid_hex_color",
                                message="Use #RRGGBB hex colors for dashboard badges.",
                                regex="^#[0-9A-Fa-f]{6}$",
                            )
                        ],
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True, decimal_places=6, max_digits=9, null=True
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True, decimal_places=6, max_digits=9, null=True
                    ),
                ),
                ("notes", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Location",
                "verbose_name_plural": "Locations",
                "ordering": ("name", "code"),
            },
            bases=(
                ralph.lib.mixins.models.AdminAbsoluteUrlMixin,
                models.Model,
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="color_hex",
            field=models.CharField(
                blank=True,
                help_text="Optional dashboard color for telemetry / IoT assets synced from SC3.",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        code="invalid_hex_color",
                        message="Use #RRGGBB hex colors for dashboard badges.",
                        regex="^#[0-9A-Fa-f]{6}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="location",
            field=models.ForeignKey(
                blank=True,
                help_text="Linked location provided by SC3.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="projects",
                to="assets.location",
            ),
        ),
        migrations.AddField(
            model_name="deploymententry",
            name="location_ref",
            field=models.ForeignKey(
                blank=True,
                help_text="Linked location record for this deployment.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="deployments",
                to="assets.location",
            ),
        ),
    ]
