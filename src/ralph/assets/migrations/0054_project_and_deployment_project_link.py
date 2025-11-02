from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import ralph.lib.mixins.models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_auto_20250408_1522"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("assets", "0053_baseobject_content_type_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=75, verbose_name="name")),
                ("created", models.DateTimeField(auto_now_add=True, verbose_name="date created")),
                ("modified", models.DateTimeField(auto_now=True, verbose_name="last modified")),
                ("code", models.CharField(help_text="Short unique identifier used by SC3 and reporting.", max_length=64, unique=True)),
                ("external_id", models.CharField(blank=True, help_text="Optional external identifier supplied by SC3.", max_length=128, null=True, unique=True)),
                ("status", models.PositiveIntegerField(choices=[(1, "planned"), (2, "active"), (3, "paused"), (4, "completed"), (5, "cancelled")], default=1)),
                ("location_name", models.CharField(blank=True, help_text="Primary project location or site label.", max_length=128)),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("description", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("default_team", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="projects", to="accounts.team")),
                ("manager", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="projects_managed", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Project",
                "verbose_name_plural": "Projects",
                "ordering": ("name", "code"),
            },
            bases=(ralph.lib.mixins.models.AdminAbsoluteUrlMixin, models.Model),
        ),
        migrations.AddField(
            model_name="deploymententry",
            name="project",
            field=models.ForeignKey(blank=True, help_text="Project or engagement this deployment supports.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="deployment_entries", to="assets.project"),
        ),
        migrations.AddIndex(
            model_name="deploymententry",
            index=models.Index(fields=["project", "started_at"], name="assets_depl_proj_start_idx"),
        ),
    ]
