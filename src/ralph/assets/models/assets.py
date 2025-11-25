# -*- coding: utf-8 -*-
import datetime
import json
import logging
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from mptt.models import MPTTModel, TreeForeignKey

from ralph.accounts.models import Team
from ralph.admin.autocomplete import AutocompleteTooltipMixin
from ralph.attachments.models import AttachmentItem
from ralph.assets.models.base import BaseObject
from ralph.assets.models.choices import ModelVisualizationLayout, ObjectModelType
from django.contrib.contenttypes.models import ContentType
from ralph.assets.notifications import AssetEventType, notify_asset_event
from ralph.lib.custom_fields.models import CustomFieldMeta, WithCustomFieldsMixin
from ralph.lib.dj_choices import Choices
from ralph.lib.mixins.fields import NullableCharField, NullableCharFieldWithAutoStrip
from ralph.lib.mixins.models import (
    AdminAbsoluteUrlMixin,
    NamedMixin,
    PriceMixin,
    TimeStampMixin,
)
from ralph.lib.permissions.models import PermByFieldMixin, PermissionsBase

logger = logging.getLogger(__name__)


class AssetHolder(
    AdminAbsoluteUrlMixin, NamedMixin.NonUnique, TimeStampMixin, models.Model
):
    pass


class BusinessSegment(AdminAbsoluteUrlMixin, NamedMixin, models.Model):
    pass


class ProfitCenter(AdminAbsoluteUrlMixin, NamedMixin, models.Model):
    description = models.TextField(blank=True)


class Environment(AdminAbsoluteUrlMixin, NamedMixin, TimeStampMixin, models.Model):
    pass


class Service(
    PermByFieldMixin, AdminAbsoluteUrlMixin, NamedMixin, TimeStampMixin, models.Model
):
    # Fixme: let's do service catalog replacement from that
    _allow_in_dashboard = True

    active = models.BooleanField(default=True)
    uid = NullableCharField(max_length=40, unique=True, blank=True, null=True)
    profit_center = models.ForeignKey(
        ProfitCenter, null=True, blank=True, on_delete=models.CASCADE
    )
    business_segment = models.ForeignKey(
        BusinessSegment, null=True, blank=True, on_delete=models.CASCADE
    )
    cost_center = models.CharField(max_length=100, blank=True)
    environments = models.ManyToManyField("Environment", through="ServiceEnvironment")
    business_owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="services_business_owner",
        blank=True,
    )
    technical_owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="services_technical_owner",
        blank=True,
    )
    support_team = models.ForeignKey(
        Team, null=True, blank=True, related_name="services", on_delete=models.CASCADE
    )

    def __str__(self):
        return "{}".format(self.name)

    @classmethod
    def get_autocomplete_queryset(cls):
        return cls._default_manager.filter(active=True)


class ServiceEnvironment(AdminAbsoluteUrlMixin, AutocompleteTooltipMixin, BaseObject):
    _allow_in_dashboard = True
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    environment = models.ForeignKey(Environment, on_delete=models.CASCADE)

    autocomplete_tooltip_fields = [
        "service__business_owners",
        "service__technical_owners",
        "service__support_team",
    ]

    def __str__(self):
        return "{} - {}".format(self.service.name, self.environment.name)

    class Meta:
        unique_together = ("service", "environment")
        ordering = ("service__name", "environment__name")

    @property
    def service_name(self):
        return self.service.name

    @property
    def service_uid(self):
        return self.service.uid

    @property
    def environment_name(self):
        return self.environment.name

    @classmethod
    def get_autocomplete_queryset(cls):
        return cls._default_manager.filter(service__active=True)


class ManufacturerKind(AdminAbsoluteUrlMixin, NamedMixin, models.Model):
    pass


class Manufacturer(AdminAbsoluteUrlMixin, NamedMixin, TimeStampMixin, models.Model):
    _allow_in_dashboard = True
    manufacturer_kind = models.ForeignKey(
        ManufacturerKind,
        verbose_name=_("manufacturer kind"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )


AssetModelMeta = type("AssetModelMeta", (CustomFieldMeta, PermissionsBase), {})


class AssetModel(
    PermByFieldMixin,
    NamedMixin.NonUnique,
    TimeStampMixin,
    AdminAbsoluteUrlMixin,
    WithCustomFieldsMixin,
    models.Model,
    metaclass=AssetModelMeta,
):
    # TODO: should type be determined based on category?
    _allow_in_dashboard = True

    type = models.PositiveIntegerField(
        verbose_name=_("type"),
        choices=ObjectModelType(),
    )
    manufacturer = models.ForeignKey(
        Manufacturer, on_delete=models.PROTECT, blank=True, null=True
    )
    category = TreeForeignKey(
        "Category", null=True, related_name="models", on_delete=models.CASCADE
    )
    power_consumption = models.PositiveIntegerField(
        verbose_name=_("Power consumption"),
        default=0,
    )
    height_of_device = models.FloatField(
        verbose_name=_("Height of device"),
        default=0,
        validators=[MinValueValidator(0)],
    )
    cores_count = models.PositiveIntegerField(
        verbose_name=_("Cores count"),
        default=0,
    )
    visualization_layout_front = models.PositiveIntegerField(
        verbose_name=_("visualization layout of front side"),
        choices=ModelVisualizationLayout(),
        default=ModelVisualizationLayout().na.id,
        blank=True,
    )
    visualization_layout_back = models.PositiveIntegerField(
        verbose_name=_("visualization layout of back side"),
        choices=ModelVisualizationLayout(),
        default=ModelVisualizationLayout().na.id,
        blank=True,
    )
    # Used in the visualization Data Center as is_blade
    has_parent = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("model")
        verbose_name_plural = _("models")

    def __str__(self):
        if self.category_id:
            return "[{}] {} {}".format(self.category, self.manufacturer, self.name)
        else:
            return "{} {}".format(self.manufacturer, self.name)

    def _get_layout_class(self, field):
        item = ModelVisualizationLayout.from_id(field)
        return getattr(item, "css_class", "")

    def get_front_layout_class(self):
        return self._get_layout_class(self.visualization_layout_front)

    def get_back_layout_class(self):
        return self._get_layout_class(self.visualization_layout_back)


class Category(
    AdminAbsoluteUrlMixin, MPTTModel, NamedMixin.NonUnique, TimeStampMixin, models.Model
):
    _allow_in_dashboard = True

    code = models.CharField(max_length=4, blank=True, default="")
    parent = TreeForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        db_index=True,
        on_delete=models.CASCADE,
    )
    imei_required = models.BooleanField(default=False)
    allow_deployment = models.BooleanField(default=False)
    show_buyout_date = models.BooleanField(default=False)
    is_field_gear = models.BooleanField(
        default=False,
        help_text=_("Mark categories that represent portable tools / field gear."),
    )
    default_depreciation_rate = models.DecimalField(
        blank=True,
        decimal_places=2,
        default=settings.DEFAULT_DEPRECIATION_RATE,
        help_text=_(
            "This value is in percentage."
            ' For example value: "100" means it depreciates during a year.'
            ' Value: "25" means it depreciates during 4 years, and so on... .'
        ),
        max_digits=5,
    )

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")

    class MPTTMeta:
        order_insertion_by = ["name"]

    def __str__(self):
        return self.name

    def get_default_depreciation_rate(self, category=None):
        if category is None:
            category = self

        if category.default_depreciation_rate:
            return category.default_depreciation_rate
        elif category.parent:
            return self.get_default_depreciation_rate(category.parent)
        return 0


class AssetLastHostname(models.Model):
    prefix = models.CharField(max_length=30, db_index=True)
    counter = models.PositiveIntegerField(default=1)
    postfix = models.CharField(max_length=30, db_index=True)

    class Meta:
        unique_together = ("prefix", "postfix")

    def formatted_hostname(self, fill=5):
        return "{prefix}{counter:0{fill}}{postfix}".format(
            prefix=self.prefix,
            counter=int(self.counter),
            fill=fill,
            postfix=self.postfix,
        )

    @classmethod
    # TODO: select_for_update
    def increment_hostname(cls, prefix, postfix=""):
        obj, created = cls.objects.get_or_create(
            prefix=prefix,
            postfix=postfix,
        )
        if not created:
            # F() avoid race condition problem
            obj.counter = models.F("counter") + 1
            obj.save()
            return cls.objects.get(pk=obj.pk)
        else:
            return obj

    @classmethod
    def get_next_free_hostname(
        cls, prefix, postfix, fill=5, availability_checker=None, _counter=1
    ):
        try:
            last_hostname = cls.objects.get(prefix=prefix, postfix=postfix)
        except cls.DoesNotExist:
            last_hostname = cls(prefix=prefix, postfix=postfix, counter=0)

        last_hostname.counter += _counter
        hostname = last_hostname.formatted_hostname(fill=fill)

        if availability_checker is None or availability_checker(hostname):
            return hostname
        else:
            return cls.get_next_free_hostname(
                prefix, postfix, fill, availability_checker, _counter + 1
            )

    def __str__(self):
        return self.formatted_hostname()


class BudgetInfo(AdminAbsoluteUrlMixin, NamedMixin, TimeStampMixin, models.Model):
    class Meta:
        verbose_name = _("Budget info")
        verbose_name_plural = _("Budgets info")

    def __str__(self):
        return self.name


class Asset(AdminAbsoluteUrlMixin, PriceMixin, BaseObject):
    model = models.ForeignKey(
        AssetModel, related_name="assets", on_delete=models.PROTECT
    )
    # TODO: unify hostname for DCA, VirtualServer, Cluster and CloudHost
    # (use another model?)
    hostname = NullableCharFieldWithAutoStrip(
        blank=True,
        default=None,
        max_length=255,
        null=True,
        verbose_name=_("hostname"),  # TODO: unique
    )
    sn = NullableCharField(
        blank=True,
        max_length=200,
        null=True,
        verbose_name=_("SN"),
        unique=True,
        validators=[
            RegexValidator(
                r"\s",
                _("No spaces allowed"),
                inverse_match=True,
                code="no_spaces_allowed",
            )
        ],
    )
    barcode = NullableCharField(
        blank=True,
        default=None,
        max_length=200,
        null=True,
        unique=True,
        verbose_name=_("barcode"),
        validators=[
            RegexValidator(
                r"\s",
                _("No spaces allowed"),
                inverse_match=True,
                code="no_spaces_allowed",
            )
        ],
    )
    niw = NullableCharField(
        blank=True,
        default=None,
        max_length=200,
        null=True,
        verbose_name=_("inventory number"),
    )
    required_support = models.BooleanField(default=False)

    order_no = models.CharField(
        verbose_name=_("order number"),
        blank=True,
        max_length=50,
        null=True,
    )
    invoice_no = models.CharField(
        verbose_name=_("invoice number"),
        blank=True,
        db_index=True,
        max_length=128,
        null=True,
    )
    invoice_date = models.DateField(blank=True, null=True)
    # to discuss: foreign key?
    provider = models.CharField(
        blank=True,
        max_length=100,
        null=True,
    )
    annual_capex_budget = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Annual CAPEX budget allocated to the asset."),
    )
    annual_opex_budget = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Annual OPEX budget allocated to the asset."),
    )
    budget_period_start = models.DateField(
        null=True,
        blank=True,
        help_text=_("Start date of the current budget period."),
    )
    last_usage_value = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_("Last recorded usage meter value for telemetry delta calculations."),
    )
    last_usage_captured_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp of the last usage meter reading."),
    )
    depreciation_rate = models.DecimalField(
        blank=True,
        decimal_places=2,
        default=settings.DEFAULT_DEPRECIATION_RATE,
        help_text=_(
            "This value is in percentage."
            ' For example value: "100" means it depreciates during a year.'
            ' Value: "25" means it depreciates during 4 years, and so on... .'
        ),
        max_digits=5,
    )
    force_depreciation = models.BooleanField(
        help_text=("Check if you no longer want to bill for this asset"),
        default=False,
    )
    depreciation_end_date = models.DateField(blank=True, null=True)
    buyout_date = models.DateField(blank=True, null=True, db_index=True)
    task_url = models.URLField(
        blank=True,
        help_text=("External workflow system URL"),
        max_length=2048,
        null=True,
    )
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^#[0-9A-Fa-f]{6}$",
                message=_("Use #RRGGBB hex colors for dashboard badges."),
                code="invalid_hex_color",
            )
        ],
        help_text=_(
            "Optional dashboard color for telemetry / IoT assets synced from SC3."
        ),
    )
    budget_info = models.ForeignKey(
        BudgetInfo,
        blank=True,
        default=None,
        null=True,
        on_delete=models.PROTECT,
    )
    property_of = models.ForeignKey(
        AssetHolder,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    start_usage = models.DateField(
        blank=True,
        null=True,
        help_text=("Fill it if date of first usage is different then date of creation"),
    )

    def __str__(self):
        return self.hostname or ""

    def calculate_buyout_date(self):
        """
        Get buyout date.

        Calculate buyout date:
         invoice_date + buyout months offset by category

        Returns:
            Buyout date
        """
        if (
            not self.model
            or not self.model.category
            or not self.model.category.show_buyout_date
        ):
            return None

        category = self.model.category  # type: Category
        months = settings.ASSET_BUYOUT_CATEGORY_TO_MONTHS.get(str(category.pk), None)
        if self.invoice_date and months:
            return self.invoice_date + relativedelta(months=months)
        else:
            return None

    def get_depreciation_months(self):
        return int(
            (1 / (self.depreciation_rate / 100) * 12) if self.depreciation_rate else 0
        )

    def is_depreciated(self, date=None):
        date = date or datetime.date.today()
        if self.force_depreciation or not self.invoice_date:
            return True
        if self.depreciation_end_date:
            deprecation_date = self.deprecation_end_date
        else:
            deprecation_date = self.invoice_date + relativedelta(
                months=self.get_depreciation_months(),
            )
        return deprecation_date < date

    def get_depreciated_months(self):
        # DEPRECATED
        # BACKWARD_COMPATIBILITY
        return self.get_depreciation_months()

    def is_deprecated(self, date=None):
        # DEPRECATED
        # BACKWARD_COMPATIBILITY
        return self.is_depreciated()

    def _liquidated_at(self, date):
        liquidated_history = (
            self.get_history()
            .filter(
                new_value="liquidated",
                field_name="status",
            )
            .order_by("-date")[:1]
        )
        return liquidated_history and liquidated_history[0].date.date() <= date

    def clean(self):
        errors = {}
        if not self.sn and not self.barcode:
            error_message = [_("SN or BARCODE field is required")]
            errors.update({"sn": error_message, "barcode": error_message})
        if not self.property_of:
            error_message = [_("Property of field is required")]
            errors.update(
                {
                    "__all__": error_message,
                }
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # if you save barcode as empty string (instead of None) you could have
        # only one asset with empty barcode (because of `unique` constraint)
        # if you save barcode as None you could have many assets with empty
        # barcode (becasue `unique` constrainst is skipped)
        for unique_field in ["barcode", "sn"]:
            value = getattr(self, unique_field, None)
            if value == "":
                value = None
            setattr(self, unique_field, value)

        if not self.buyout_date:
            self.buyout_date = self.calculate_buyout_date()
        return super(Asset, self).save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Spend & budget helpers

    def capex_actual(self):
        value = Decimal(self.price or 0)
        acquisition = getattr(self, "acquisition_cost", None)
        if acquisition:
            value += acquisition
        return value

    def maintenance_cost_total(self, start=None, end=None, record_type=None):
        qs = self.maintenance_records.filter(cost__isnull=False)
        if start:
            qs = qs.filter(opened_at__date__gte=start)
        if end:
            qs = qs.filter(opened_at__date__lte=end)
        if record_type is not None:
            qs = qs.filter(record_type=record_type)
        return qs.aggregate(total=models.Sum("cost"))["total"] or Decimal("0")

    def opex_spend_to_date(self, start=None, end=None):
        return self.maintenance_cost_total(start=start, end=end)

    def fuel_spend_to_date(self, start=None, end=None):
        return self.maintenance_cost_total(
            start=start, end=end, record_type=MaintenanceRecordType.refuel.id
        )

    def budget_status(self, reference=None):
        reference = reference or timezone.now().date()
        period_start = self.budget_period_start or reference.replace(month=1, day=1)
        capex_budget = self.annual_capex_budget or Decimal("0")
        opex_budget = self.annual_opex_budget or Decimal("0")
        capex_actual = self.capex_actual()
        opex_actual = self.opex_spend_to_date(start=period_start, end=reference)
        return {
            "capex_budget": float(capex_budget),
            "capex_actual": float(capex_actual),
            "capex_variance": float(capex_budget - capex_actual),
            "opex_budget": float(opex_budget),
            "opex_actual": float(opex_actual),
            "opex_variance": float(opex_budget - opex_actual),
            "budget_period_start": period_start.isoformat(),
        }

    def budget_status_display(self):
        status = self.budget_status()
        capex = status["capex_actual"]
        capex_budget = status["capex_budget"]
        opex = status["opex_actual"]
        opex_budget = status["opex_budget"]
        return _("CAPEX {capex}/{capex_budget}, OPEX {opex}/{opex_budget}").format(
            capex=capex,
            capex_budget=capex_budget or "-",
            opex=opex,
            opex_budget=opex_budget or "-",
        )


class MaintenanceRecordType(Choices):
    _ = Choices.Choice

    maintenance = _("maintenance")
    repair = _("repair")
    refuel = _("refuel")
    calibration = _("calibration")
    inspection = _("inspection")
    approval = _("approval")
    other = _("other")


class MaintenanceRecordStatus(Choices):
    _ = Choices.Choice

    open = _("open")
    in_progress = _("in progress")
    completed = _("completed")


class MaintenanceRecordQuerySet(models.QuerySet):
    def open(self):
        return self.filter(
            status__in=[
                MaintenanceRecordStatus.open.id,
                MaintenanceRecordStatus.in_progress.id,
            ]
        )

    def overdue(self):
        today = timezone.now().date()
        return self.open().filter(
            expected_completion__isnull=False,
            expected_completion__lt=today,
        )

    def due_within(self, days):
        deadline = timezone.now().date() + timedelta(days=days)
        return self.open().filter(
            expected_completion__isnull=False,
            expected_completion__lte=deadline,
        )


class MaintenanceRecord(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="maintenance_records",
        on_delete=models.CASCADE,
    )
    work_order = models.ForeignKey(
        "WorkOrder",
        null=True,
        blank=True,
        related_name="maintenance_records",
        on_delete=models.SET_NULL,
    )
    record_type = models.PositiveIntegerField(
        choices=MaintenanceRecordType(),
        default=MaintenanceRecordType.maintenance.id,
    )
    status = models.PositiveIntegerField(
        choices=MaintenanceRecordStatus(),
        default=MaintenanceRecordStatus.open.id,
    )
    title = models.CharField(max_length=128, blank=True)
    description = models.TextField(blank=True)
    resolution = models.TextField(blank=True)
    opened_at = models.DateTimeField(default=timezone.now)
    expected_completion = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    out_of_service = models.BooleanField(default=False)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="reported_maintenance_records",
        on_delete=models.SET_NULL,
    )
    performed_by = models.CharField(max_length=128, blank=True)
    service_provider = models.CharField(max_length=128, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="closed_maintenance_records",
        on_delete=models.SET_NULL,
    )
    closure_notes = models.TextField(blank=True)
    closure_acknowledged = models.BooleanField(default=False)
    closure_acknowledged_at = models.DateTimeField(null=True, blank=True)
    extra_data = models.JSONField(default=dict, blank=True)

    objects = MaintenanceRecordQuerySet.as_manager()

    class Meta:
        ordering = ("-opened_at", "-pk")
        verbose_name = _("Maintenance record")
        verbose_name_plural = _("Maintenance records")
        indexes = [
            models.Index(fields=["base_object", "status", "opened_at"]),
            models.Index(fields=["base_object", "expected_completion"]),
        ]

    def __str__(self):
        return "{} ({})".format(
            self.get_record_type_display(), self.base_object or "-"
        )

    @classmethod
    def start_record(
        cls,
        base_object,
        record_type,
        *,
        title="",
        status=None,
        description="",
        expected_completion=None,
        out_of_service=False,
        reported_by=None,
        performed_by=None,
        extra_data=None,
        service_provider="",
        sla_due_at=None,
    ):
        status = status or MaintenanceRecordStatus.open.id
        return cls.objects.create(
            base_object=base_object,
            record_type=record_type,
            status=status,
            title=title[:128] if title else "",
            description=description or "",
            expected_completion=expected_completion,
            out_of_service=out_of_service,
            reported_by=reported_by,
            performed_by=performed_by or "",
            service_provider=service_provider or "",
            sla_due_at=sla_due_at,
            extra_data=extra_data or {},
        )

    @classmethod
    def close_latest(
        cls,
        base_object,
        record_type=None,
        *,
        resolution=None,
        extra_data=None,
        cost=None,
        closed_at=None,
        performed_by=None,
        closed_by=None,
        closure_notes=None,
        closure_acknowledged=False,
        closure_acknowledged_at=None,
    ):
        filters = {
            "base_object": base_object,
            "status__in": [
                MaintenanceRecordStatus.open.id,
                MaintenanceRecordStatus.in_progress.id,
            ],
        }
        if record_type is not None:
            filters["record_type"] = record_type

        record = (
            cls.objects.filter(**filters).order_by("-opened_at", "-pk").first()
        )
        if not record:
            return None
        record.status = MaintenanceRecordStatus.completed.id
        record.closed_at = closed_at or timezone.now()
        if resolution:
            record.resolution = resolution
        if cost is not None:
            record.cost = cost
        if performed_by is not None:
            record.performed_by = performed_by
        if closed_by is not None:
            record.closed_by = closed_by
        if closure_notes is not None:
            record.closure_notes = closure_notes
        if closure_acknowledged:
            record.closure_acknowledged = True
            record.closure_acknowledged_at = (
                closure_acknowledged_at or timezone.now()
            )
        if extra_data:
            combined = record.extra_data.copy()
            combined.update(extra_data)
            record.extra_data = combined
        record.save()
        return record

    @property
    def is_sla_overdue(self):
        if self.sla_due_at is None:
            return False
        if self.status == MaintenanceRecordStatus.completed.id:
            return False
        return self.sla_due_at < timezone.now()

    @classmethod
    def close_open_records(
        cls,
        base_object,
        record_type=None,
        resolution=None,
        performed_by=None,
    ):
        filters = {
            "base_object": base_object,
            "status__in": [
                MaintenanceRecordStatus.open.id,
                MaintenanceRecordStatus.in_progress.id,
            ],
        }
        if record_type is not None:
            filters["record_type"] = record_type
        now = timezone.now()
        for record in cls.objects.filter(**filters).order_by("-opened_at"):
            record.status = MaintenanceRecordStatus.completed.id
            record.closed_at = now
            if resolution and not record.resolution:
                record.resolution = resolution
            if performed_by is not None:
                record.performed_by = performed_by
            record.save()
        return True

    @classmethod
    def ensure_approval_record(
        cls,
        base_object,
        *,
        action,
        description="",
        requester=None,
        extra=None,
    ):
        filters = {
            "base_object": base_object,
            "record_type": MaintenanceRecordType.approval.id,
            "status__in": [
                MaintenanceRecordStatus.open.id,
                MaintenanceRecordStatus.in_progress.id,
            ],
            "extra_data__approval__action": action,
        }
        record = (
            cls.objects.filter(**filters)
            .order_by("-opened_at", "-pk")
            .first()
        )
        if record:
            return record, False

        extra_data = extra.copy() if extra else {}
        approval_meta = {
            "action": action,
            "requested_at": timezone.now().isoformat(),
        }
        if requester is not None:
            approval_meta["requested_by"] = requester.pk
        if description:
            approval_meta["description"] = description
        extra_data["approval"] = approval_meta
        record = cls.start_record(
            base_object=base_object,
            record_type=MaintenanceRecordType.approval.id,
            status=MaintenanceRecordStatus.open.id,
            title=_("Approval requested"),
            description=description or "",
            out_of_service=False,
            reported_by=requester,
            extra_data=extra_data,
        )
        return record, True

    def is_overdue(self):
        if self.status == MaintenanceRecordStatus.completed.id:
            return False
        if not self.expected_completion:
            return False
        return self.expected_completion < timezone.now().date()


class ComplianceRecordType(Choices):
    _ = Choices.Choice

    inspection = _("inspection")
    certification = _("certification")
    permit = _("permit")
    registration = _("registration")
    insurance = _("insurance")
    calibration = _("calibration")
    other = _("other")


class ComplianceRecordStatus(Choices):
    _ = Choices.Choice

    compliant = _("compliant")
    due_soon = _("due soon")
    overdue = _("overdue")
    failed = _("failed")


class ComplianceSeverity(Choices):
    _ = Choices.Choice

    low = _("low")
    medium = _("medium")
    high = _("high")
    critical = _("critical")


class ComplianceRecordQuerySet(models.QuerySet):
    def upcoming(self, within_days=30):
        today = timezone.now().date()
        deadline = today + timedelta(days=within_days)
        return self.filter(
            expires_on__gte=today,
            expires_on__lte=deadline,
        )

    @property
    def parts_cost_total(self):
        total = Decimal("0")
        for usage in self.part_usages.all():
            total += usage.extended_cost
        return total

    @property
    def parts_used(self):
        return self.part_usages.select_related("part", "stock")

    def as_dict_for_costs(self):
        data = {
            "id": self.pk,
            "title": self.title,
            "status": self.get_status_display(),
            "record_type": self.get_record_type_display(),
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "cost": self.cost,
            "parts_cost_total": self.parts_cost_total,
        }
        return data


class WorkOrderType(Choices):
    _ = Choices.Choice

    maintenance = _("maintenance")
    repair = _("repair")
    inspection = _("inspection")
    installation = _("installation")
    decommission = _("decommission")
    other = _("other")


class WorkOrderPriority(Choices):
    _ = Choices.Choice

    low = _("low")
    normal = _("normal")
    high = _("high")
    critical = _("critical")


class WorkOrderStatus(Choices):
    _ = Choices.Choice

    open = _("open")
    in_progress = _("in progress")
    waiting_approval = _("waiting approval")
    completed = _("completed")
    canceled = _("canceled")


class WorkOrder(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="work_orders",
        on_delete=models.CASCADE,
    )
    title = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    order_type = models.PositiveIntegerField(choices=WorkOrderType(), default=WorkOrderType.maintenance.id)
    priority = models.PositiveIntegerField(choices=WorkOrderPriority(), default=WorkOrderPriority.normal.id)
    status = models.PositiveIntegerField(choices=WorkOrderStatus(), default=WorkOrderStatus.open.id)
    vendor_name = models.CharField(max_length=128, blank=True)
    opened_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    sla_target_at = models.DateTimeField(null=True, blank=True)
    sla_breach_at = models.DateTimeField(null=True, blank=True)
    approval_required = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="approved_work_orders",
        on_delete=models.SET_NULL,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-opened_at", "-pk")
        verbose_name = _("Work order")
        verbose_name_plural = _("Work orders")

    def __str__(self):
        return f"{self.get_order_type_display()} – {self.title}"

    @property
    def is_open(self):
        return self.status in {WorkOrderStatus.open.id, WorkOrderStatus.in_progress.id, WorkOrderStatus.waiting_approval.id}

    @property
    def task_cost_total(self):
        return (
            self.tasks.aggregate(total=models.Sum("cost"))["total"]
            or Decimal("0")
        )

    @property
    def effective_total_cost(self):
        if self.total_cost is not None:
            return self.total_cost
        return self.task_cost_total


class WorkOrderTask(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    work_order = models.ForeignKey(
        WorkOrder,
        related_name="tasks",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=128)
    status = models.PositiveIntegerField(choices=WorkOrderStatus(), default=WorkOrderStatus.open.id)
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="work_order_tasks",
        on_delete=models.SET_NULL,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("work_order", "-created")
        verbose_name = _("Work order task")
        verbose_name_plural = _("Work order tasks")

    def __str__(self):
        return f"{self.name}"


class SparePartCategory(AdminAbsoluteUrlMixin, NamedMixin, TimeStampMixin, models.Model):
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Spare part category")
        verbose_name_plural = _("Spare part categories")

    def __str__(self):
        return self.name


class SparePart(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    category = models.ForeignKey(
        SparePartCategory,
        null=True,
        blank=True,
        related_name="parts",
        on_delete=models.SET_NULL,
    )
    name = models.CharField(max_length=128)
    sku = models.CharField(max_length=64, blank=True, db_index=True)
    vendor_name = models.CharField(max_length=128, blank=True)
    vendor_sku = models.CharField(max_length=64, blank=True, db_index=True)
    description = models.TextField(blank=True)
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    restock_threshold = models.PositiveIntegerField(
        default=0,
        help_text=_("Trigger restock alerts when stock reaches this quantity (global default)."),
    )
    restock_quantity = models.PositiveIntegerField(
        default=0,
        help_text=_("Suggested quantity to reorder when below threshold."),
    )
    is_active = models.BooleanField(default=True)
    external_reference = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("External procurement identifier or SKU."),
    )

    class Meta:
        ordering = ("name", "sku")
        verbose_name = _("Spare part")
        verbose_name_plural = _("Spare parts")

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.sku:
            return f"{self.name} ({self.sku})"
        return self.name

    def active_stocks(self):
        return self.stocks.filter(is_active=True)

    def total_quantity_on_hand(self):
        return sum(stock.quantity_on_hand for stock in self.active_stocks())


class SparePartStock(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    part = models.ForeignKey(
        SparePart,
        related_name="stocks",
        on_delete=models.CASCADE,
    )
    location = models.CharField(
        max_length=128,
        help_text=_("Storage location, e.g. warehouse or vehicle identifier."),
    )
    quantity_on_hand = models.PositiveIntegerField(default=0)
    quantity_reserved = models.PositiveIntegerField(default=0)
    reorder_point = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Override restock threshold for this location."),
    )
    reorder_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Override reorder quantity for this location."),
    )
    last_restocked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("part__name", "location")
        verbose_name = _("Spare part stock")
        verbose_name_plural = _("Spare part stocks")
        unique_together = ("part", "location")

    def __str__(self):
        return f"{self.part.display_name} @ {self.location}"

    @property
    def restock_threshold(self):
        if self.reorder_point is not None:
            return self.reorder_point
        return self.part.restock_threshold

    @property
    def restock_quantity(self):
        if self.reorder_quantity is not None and self.reorder_quantity > 0:
            return self.reorder_quantity
        return self.part.restock_quantity

    @property
    def needs_restock(self):
        threshold = self.restock_threshold
        return threshold and self.quantity_on_hand <= threshold

    def adjust_on_hand(self, delta):
        with transaction.atomic():
            new_value = self.quantity_on_hand + int(delta)
            if new_value < 0:
                raise ValidationError(
                    _("Insufficient stock for %(part)s at %(location)s"),
                    params={"part": self.part, "location": self.location},
                )
            self.quantity_on_hand = new_value
            self.save(update_fields=["quantity_on_hand", "modified"])
            if self.needs_restock:
                self.trigger_restock_alert()

    def consume(self, quantity):
        if quantity <= 0:
            return
        self.adjust_on_hand(-int(quantity))

    def restock(self, quantity):
        if quantity <= 0:
            return
        with transaction.atomic():
            self.quantity_on_hand += int(quantity)
            self.last_restocked_at = timezone.now()
            self.save(update_fields=["quantity_on_hand", "last_restocked_at", "modified"])

    def trigger_restock_alert(self):
        notify_asset_event(
            self.part,
            AssetEventType.INVENTORY_LOW,
            payload={
                "part_id": self.part_id,
                "stock_id": self.pk,
                "location": self.location,
                "quantity_on_hand": self.quantity_on_hand,
                "threshold": self.restock_threshold,
                "reorder_quantity": self.restock_quantity,
            },
            metadata={
                "category": "inventory",
                "event": "restock_threshold",
            },
        )


class MaintenancePartUsage(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    maintenance_record = models.ForeignKey(
        MaintenanceRecord,
        related_name="part_usages",
        on_delete=models.CASCADE,
    )
    part = models.ForeignKey(
        SparePart,
        related_name="maintenance_usages",
        on_delete=models.PROTECT,
    )
    stock = models.ForeignKey(
        SparePartStock,
        related_name="usages",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=_("Stock location the part was consumed from."),
    )
    quantity_used = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Override unit cost at time of use."),
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created",)
        verbose_name = _("Maintenance part usage")
        verbose_name_plural = _("Maintenance part usage")

    def __str__(self):
        return f"{self.part} x{self.quantity_used} for {self.maintenance_record}"

    @property
    def effective_unit_cost(self):
        if self.unit_cost is not None:
            return self.unit_cost
        if self.part.unit_cost is not None:
            return self.part.unit_cost
        return Decimal("0")

    @property
    def extended_cost(self):
        return self.effective_unit_cost * Decimal(self.quantity_used or 0)

    def clean(self):
        super().clean()
        if self.stock and self.stock.part_id != self.part_id:
            raise ValidationError(
                _("Selected stock location does not match spare part."),
            )

    def save(self, *args, **kwargs):
        if self.quantity_used <= 0:
            raise ValidationError(_("Used quantity must be greater than zero."))
        with transaction.atomic():
            if self.pk:
                previous = MaintenancePartUsage.objects.get(pk=self.pk)
                delta = self.quantity_used - previous.quantity_used
            else:
                delta = self.quantity_used
            super().save(*args, **kwargs)
            if self.stock:
                if delta > 0:
                    self.stock.consume(delta)
                elif delta < 0:
                    self.stock.restock(abs(delta))
                if self.stock.needs_restock:
                    notify_asset_event(
                        self.part,
                        AssetEventType.INVENTORY_REORDER,
                        payload={
                            "part_id": self.part_id,
                            "stock_id": self.stock_id,
                            "location": self.stock.location,
                            "quantity_on_hand": self.stock.quantity_on_hand,
                            "recommended_reorder": self.stock.restock_quantity,
                        },
                        metadata={"category": "inventory", "event": "reorder"},
                    )

    def delete(self, using=None, keep_parents=False):
        with transaction.atomic():
            if self.stock:
                self.stock.restock(self.quantity_used)
            return super().delete(using=using, keep_parents=keep_parents)


class SafetyChecklistTrigger(Choices):
    _ = Choices.Choice

    activation = _("Activation / pre-use")
    maintenance_release = _("Maintenance release")
    mission_launch = _("Mission launch")


class SafetyChecklistStatus(Choices):
    _ = Choices.Choice

    draft = _("Draft")
    passed = _("Passed")
    failed = _("Failed")


class SafetyChecklistItemType(Choices):
    _ = Choices.Choice

    boolean = _("Boolean (yes/no)")
    text = _("Text")
    decimal = _("Decimal")


class SafetyChecklistTemplate(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    name = models.CharField(max_length=128)
    trigger = models.PositiveIntegerField(choices=SafetyChecklistTrigger(), default=SafetyChecklistTrigger.activation.id)
    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text=_("Restrict template to a specific asset model."),
    )
    is_active = models.BooleanField(default=True)
    require_all_pass = models.BooleanField(
        default=True,
        help_text=_("Require every checklist item to pass in order to use the entry."),
    )
    validity_period_hours = models.PositiveIntegerField(
        default=24,
        help_text=_("Maximum age (hours) of a completed checklist for transition gating."),
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Safety checklist template")
        verbose_name_plural = _("Safety checklist templates")

    def __str__(self):
        return self.name

    def applies_to(self, asset):
        if not self.is_active:
            return False
        if self.content_type is None:
            return True
        return self.content_type.model_class() == asset.__class__

    @classmethod
    def applicable_for(cls, asset, trigger):
        return [
            template
            for template in cls.objects.filter(trigger=trigger, is_active=True)
            if template.applies_to(asset)
        ]


class SafetyChecklistItem(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    template = models.ForeignKey(
        SafetyChecklistTemplate,
        related_name="items",
        on_delete=models.CASCADE,
    )
    prompt = models.CharField(max_length=256)
    item_type = models.PositiveIntegerField(
        choices=SafetyChecklistItemType(),
        default=SafetyChecklistItemType.boolean.id,
    )
    is_required = models.BooleanField(default=True)
    require_attachment = models.BooleanField(default=False)

    class Meta:
        ordering = ("template", "pk")
        verbose_name = _("Safety checklist item")
        verbose_name_plural = _("Safety checklist items")

    def __str__(self):
        return self.prompt


class SafetyChecklistEntry(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="safety_checklists",
        on_delete=models.CASCADE,
    )
    template = models.ForeignKey(
        SafetyChecklistTemplate,
        related_name="entries",
        on_delete=models.CASCADE,
    )
    status = models.PositiveIntegerField(
        choices=SafetyChecklistStatus(),
        default=SafetyChecklistStatus.draft.id,
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="completed_safety_checklists",
        on_delete=models.SET_NULL,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    attachments = GenericRelation(AttachmentItem)

    class Meta:
        ordering = ("-completed_at", "-created")
        verbose_name = _("Safety checklist entry")
        verbose_name_plural = _("Safety checklist entries")

    def __str__(self):
        return f"{self.template.name} for {self.base_object}"

    @property
    def is_valid(self):
        if self.status != SafetyChecklistStatus.passed.id:
            return False
        if not self.completed_at:
            return False
        if self.template.validity_period_hours:
            validity = timezone.now() - timedelta(hours=self.template.validity_period_hours)
            return self.completed_at >= validity
        return True


class SafetyChecklistResponse(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    entry = models.ForeignKey(
        SafetyChecklistEntry,
        related_name="responses",
        on_delete=models.CASCADE,
    )
    item = models.ForeignKey(
        SafetyChecklistItem,
        related_name="responses",
        on_delete=models.CASCADE,
    )
    value_boolean = models.BooleanField(null=True, blank=True)
    value_text = models.TextField(blank=True)
    value_decimal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ("entry", "item")
        verbose_name = _("Safety checklist response")
        verbose_name_plural = _("Safety checklist responses")

    def __str__(self):
        return f"{self.item.prompt}"


class OperatorCertification(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="operator_certifications",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=128)
    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text=_("Restrict certification to a specific asset model."),
    )
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("user", "name")
        verbose_name = _("Operator certification")
        verbose_name_plural = _("Operator certifications")
        unique_together = ("user", "name", "content_type")

    def __str__(self):
        return f"{self.name} ({self.user})"

    def applies_to(self, asset):
        if not self.is_active:
            return False
        if self.content_type is None:
            return True
        return self.content_type.model_class() == asset.__class__

    @property
    def is_valid(self):
        if not self.is_active:
            return False
        if self.expires_on and self.expires_on < timezone.now().date():
            return False
        return True

    @classmethod
    def valid_for(cls, user, asset):
        today = timezone.now().date()
        qs = cls.objects.filter(user=user, is_active=True)
        qs = qs.filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today))
        return any(cert.applies_to(asset) for cert in qs)


class AssetIncidentSeverity(Choices):
    _ = Choices.Choice

    low = _("Low")
    medium = _("Medium")
    high = _("High")
    critical = _("Critical")


class AssetIncidentStatus(Choices):
    _ = Choices.Choice

    open = _("Open")
    in_progress = _("In progress")
    resolved = _("Resolved")


class AssetIncident(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="incidents",
        on_delete=models.CASCADE,
    )
    title = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    severity = models.PositiveIntegerField(
        choices=AssetIncidentSeverity(),
        default=AssetIncidentSeverity.medium.id,
    )
    status = models.PositiveIntegerField(
        choices=AssetIncidentStatus(),
        default=AssetIncidentStatus.open.id,
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="reported_asset_incidents",
        on_delete=models.SET_NULL,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="assigned_asset_incidents",
        on_delete=models.SET_NULL,
    )
    attachments = GenericRelation(AttachmentItem)

    class Meta:
        ordering = ("-opened_at", "-pk")
        verbose_name = _("Asset incident")
        verbose_name_plural = _("Asset incidents")

    def __str__(self):
        return self.title

    def mark_closed(self, user=None):
        self.status = AssetIncidentStatus.resolved.id
        self.closed_at = timezone.now()
        if user:
            self.assigned_to = user
        self.save(update_fields=["status", "closed_at", "assigned_to", "modified"])


class AssetIncidentTask(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    incident = models.ForeignKey(
        AssetIncident,
        related_name="tasks",
        on_delete=models.CASCADE,
    )
    description = models.CharField(max_length=256)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="completed_asset_incident_tasks",
        on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ("incident", "pk")
        verbose_name = _("Incident follow-up task")
        verbose_name_plural = _("Incident follow-up tasks")

    def __str__(self):
        return self.description

    def complete(self, user=None):
        self.completed_at = timezone.now()
        if user:
            self.completed_by = user
        self.save(update_fields=["completed_at", "completed_by", "modified"])

    def overdue(self):
        today = timezone.now().date()
        return self.filter(expires_on__lt=today)


class IntegrationEndpointType(Choices):
    _ = Choices.Choice

    webhook = _("Webhook")
    n8n = _("n8n Workflow")
    celery = _("Celery Task")
    erp = _("ERP/Finance")


class IntegrationEndpoint(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    name = models.CharField(max_length=128)
    endpoint_type = models.PositiveIntegerField(
        choices=IntegrationEndpointType(),
        default=IntegrationEndpointType.webhook.id,
    )
    target_url = models.CharField(
        max_length=256,
        blank=True,
        help_text=_("URL or dotted path depending on endpoint type."),
    )
    queue_name = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("When using Celery/RQ integrations, specify queue name."),
    )
    headers = models.JSONField(default=dict, blank=True)
    secret_token = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("Optional token included with outbound notifications."),
    )
    event_filter = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of AssetEventType values; empty list means all events."),
    )
    enabled = models.BooleanField(default=True)
    timeout_seconds = models.PositiveIntegerField(default=10)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Integration endpoint")
        verbose_name_plural = _("Integration endpoints")

    def __str__(self):
        return self.name

    def is_event_supported(self, event_type):
        if not self.event_filter:
            return True
        return str(event_type) in self.event_filter

    @property
    def parsed_url(self):
        if not self.target_url:
            return None
        return urlparse(self.target_url)


class IntegrationDeliveryStatus(Choices):
    _ = Choices.Choice

    success = _("Success")
    failure = _("Failure")


class IntegrationDeliveryLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    endpoint = models.ForeignKey(
        IntegrationEndpoint,
        related_name="deliveries",
        on_delete=models.CASCADE,
    )
    event_type = models.CharField(max_length=64)
    status = models.PositiveIntegerField(
        choices=IntegrationDeliveryStatus(),
        default=IntegrationDeliveryStatus.success.id,
    )
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created",)
        verbose_name = _("Integration delivery log")
        verbose_name_plural = _("Integration delivery logs")

    def __str__(self):
        return f"{self.endpoint} – {self.event_type}"


class SLAPolicy(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text=_("Restrict SLA to assets of this model; leave blank for global."),
    )
    target_response_hours = models.DecimalField(max_digits=6, decimal_places=2, default=4)
    target_resolution_hours = models.DecimalField(max_digits=6, decimal_places=2, default=24)
    require_manager_ack = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("SLA policy")
        verbose_name_plural = _("SLA policies")

    def __str__(self):
        return self.name

    def applies_to(self, asset):
        if not self.is_active:
            return False
        if self.content_type is None:
            return True
        return self.content_type.model_class() == asset.__class__

    @classmethod
    def for_asset(cls, asset):
        for policy in cls.objects.filter(is_active=True):
            if policy.applies_to(asset):
                return policy
        return None
class ComplianceRecord(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="compliance_records",
        on_delete=models.CASCADE,
    )
    record_type = models.PositiveIntegerField(
        choices=ComplianceRecordType(),
        default=ComplianceRecordType.inspection.id,
    )
    status = models.PositiveIntegerField(
        choices=ComplianceRecordStatus(),
        default=ComplianceRecordStatus.compliant.id,
    )
    title = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    performed_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    performed_by = models.CharField(max_length=128, blank=True)
    reference = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("External ticket, certificate or permit reference."),
    )
    document_url = models.URLField(
        blank=True,
        help_text=_("Link to compliance document or evidence."),
    )
    document = models.FileField(
        upload_to="compliance_documents/%Y/%m/",
        blank=True,
        null=True,
        help_text=_("Upload inspection certificates or permits."),
    )
    notes = models.TextField(blank=True)
    template = models.ForeignKey(
        "assets.ComplianceTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_records",
    )
    extra_data = models.JSONField(default=dict, blank=True)

    objects = ComplianceRecordQuerySet.as_manager()

    class Meta:
        ordering = ("expires_on", "title")
        verbose_name = _("Compliance record")
        verbose_name_plural = _("Compliance records")
        indexes = [
            models.Index(fields=["base_object", "expires_on"]),
            models.Index(fields=["base_object", "status"]),
        ]

    def __str__(self):
        return "{} – {}".format(self.get_record_type_display(), self.title)

    def clean(self):
        if self.expires_on and self.performed_on and self.expires_on < self.performed_on:
            raise ValidationError(_("Expiry date cannot be earlier than performed date."))

    @property
    def is_overdue(self):
        if not self.expires_on:
            return False
        return self.expires_on < timezone.now().date()

    @property
    def is_due_soon(self):
        if not self.expires_on:
            return False
        soon_threshold = timezone.now().date() + timedelta(days=30)
        return timezone.now().date() <= self.expires_on <= soon_threshold


class ComplianceTemplate(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    name = models.CharField(max_length=128)
    record_type = models.PositiveIntegerField(
        choices=ComplianceRecordType(),
        default=ComplianceRecordType.inspection.id,
    )
    title = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    severity = models.PositiveIntegerField(
        choices=ComplianceSeverity(),
        default=ComplianceSeverity.medium.id,
        help_text=_("Relative importance used for risk scoring."),
    )
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="owned_compliance_templates",
        on_delete=models.SET_NULL,
    )
    owner_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        related_name="owned_compliance_templates",
        on_delete=models.SET_NULL,
    )
    frequency_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Number of days between required checks."),
    )
    grace_period_days = models.PositiveIntegerField(
        default=0,
        help_text=_("Grace period before the compliance item is considered overdue."),
    )
    required_documents = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of evidence documents required for compliance."),
    )
    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text=_("Limit template to a specific asset type."),
    )
    is_active = models.BooleanField(default=True)
    auto_create = models.BooleanField(
        default=True,
        help_text=_("Automatically create compliance records for matching assets."),
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("Compliance template")
        verbose_name_plural = _("Compliance templates")

    def __str__(self):
        return self.name

    def applies_to(self, asset):
        if not self.is_active:
            return False
        if asset is None:
            return False
        if self.content_type is None:
            return True
        return self.content_type.model_class() == asset.__class__

    @classmethod
    def applicable_for(cls, asset):
        return [template for template in cls.objects.filter(is_active=True) if template.applies_to(asset)]


class ReportConfig(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    name = models.CharField(max_length=128)
    endpoint = models.CharField(
        max_length=64,
        help_text=_(
            "Endpoint key: inventory, utilization, maintenance-compliance, lifecycle, financial, resources, dashboard-ops, dashboard-compliance, dashboard-finance"
        ),
    )
    params = models.JSONField(default=dict, blank=True)
    export_format = models.CharField(max_length=8, default="csv")
    recipients = models.TextField(
        help_text=_("Comma or newline separated email recipients."),
    )
    is_active = models.BooleanField(default=True)
    schedule_interval_seconds = models.PositiveIntegerField(
        default=0, help_text=_("Run every N seconds (0 disables scheduling).")
    )
    initial_delay_seconds = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Saved report configuration")
        verbose_name_plural = _("Saved report configurations")

    def __str__(self):
        return self.name


class DisposalStatus(Choices):
    _ = Choices.Choice

    pending = _("pending")
    in_progress = _("in progress")
    completed = _("completed")


class DisposalTemplate(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    name = models.CharField(max_length=128)
    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text=_("Limit disposal template to a specific asset type."),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Disposal template")
        verbose_name_plural = _("Disposal templates")

    def __str__(self):
        return self.name

    def applies_to(self, asset):
        if not self.is_active:
            return False
        if self.content_type is None:
            return True
        return self.content_type.model_class() == asset.__class__

    @classmethod
    def for_asset(cls, asset):
        for template in cls.objects.filter(is_active=True):
            if template.applies_to(asset):
                return template
        return None


class DisposalTemplateTask(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    template = models.ForeignKey(
        DisposalTemplate,
        related_name="tasks",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=128)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ("template", "name")
        verbose_name = _("Disposal template task")
        verbose_name_plural = _("Disposal template tasks")

    def __str__(self):
        return f"{self.template}: {self.name}"


class DisposalRecord(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.OneToOneField(
        BaseObject,
        related_name="disposal_record",
        on_delete=models.CASCADE,
    )
    status = models.PositiveIntegerField(
        choices=DisposalStatus(),
        default=DisposalStatus.pending.id,
    )
    method = models.CharField(max_length=128, blank=True)
    notes = models.TextField(blank=True)
    document = models.FileField(
        upload_to="disposal_documents/%Y/%m/",
        blank=True,
        null=True,
        help_text=_("Upload sale receipts or certificates of destruction."),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="approved_disposals",
        on_delete=models.SET_NULL,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    template = models.ForeignKey(
        DisposalTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ("-created",)
        verbose_name = _("Disposal record")
        verbose_name_plural = _("Disposal records")

    def __str__(self):
        return f"Disposal for {self.base_object}"

    def mark_completed(self, user=None):
        self.status = DisposalStatus.completed.id
        if user is not None:
            self.approved_by = user
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at", "modified"])

    @classmethod
    def ensure_for_asset(cls, asset):
        base_object = getattr(asset, "baseobject_ptr", None) or asset
        template = DisposalTemplate.for_asset(asset)
        defaults = {"template": template}
        record, created = cls.objects.get_or_create(base_object=base_object, defaults=defaults)
        if created and template is not None:
            record.populate_tasks_from_template()
        return record

    def populate_tasks_from_template(self):
        if not self.template:
            return
        existing = {task.name for task in self.tasks.all()}
        for template_task in self.template.tasks.all():
            if template_task.name in existing:
                continue
            DisposalTask.objects.create(
                disposal_record=self,
                name=template_task.name,
                is_required=template_task.is_required,
            )


class DisposalTask(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    disposal_record = models.ForeignKey(
        DisposalRecord,
        related_name="tasks",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=128)
    is_required = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="completed_disposal_tasks",
        on_delete=models.SET_NULL,
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("disposal_record", "name")
        verbose_name = _("Disposal task")
        verbose_name_plural = _("Disposal tasks")

    def __str__(self):
        return f"{self.name} ({self.disposal_record})"

    def complete(self, user=None):
        self.is_completed = True
        self.completed_by = user
        self.completed_at = timezone.now()
        self.save(update_fields=["is_completed", "completed_by", "completed_at", "modified"])


class AssetUtilizationSnapshot(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="utilization_snapshots",
        on_delete=models.CASCADE,
    )
    date = models.DateField()
    active_seconds = models.PositiveIntegerField(default=0)
    idle_seconds = models.PositiveIntegerField(default=0)
    distance_km = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))

    class Meta:
        unique_together = ("base_object", "date")
        verbose_name = _("Asset utilization snapshot")
        verbose_name_plural = _("Asset utilization snapshots")
        indexes = [
            models.Index(fields=["base_object", "date"]),
        ]

    def __str__(self):
        return f"{self.base_object} @ {self.date}"

    @classmethod
    def record_activity(
        cls,
        base_object,
        *,
        active_seconds=0,
        idle_seconds=0,
        distance_km=Decimal("0"),
        date=None,
    ):
        date = date or timezone.now().date()
        snapshot, _ = cls.objects.get_or_create(base_object=base_object, date=date)
        snapshot.active_seconds += int(active_seconds)
        snapshot.idle_seconds += int(idle_seconds)
        snapshot.distance_km += Decimal(distance_km or 0)
        snapshot.save(update_fields=["active_seconds", "idle_seconds", "distance_km", "modified"])


class Location(AdminAbsoluteUrlMixin, NamedMixin.NonUnique, TimeStampMixin, models.Model):
    code = models.CharField(
        max_length=64,
        unique=True,
        help_text=_("Short unique identifier used by SC3 and reporting."),
    )
    external_id = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        null=True,
        help_text=_("Optional external identifier supplied by SC3."),
    )
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^#[0-9A-Fa-f]{6}$",
                message=_("Use #RRGGBB hex colors for dashboard badges."),
                code="invalid_hex_color",
            )
        ],
        help_text=_("Dashboard color propagated to telemetry-enabled assets at this location."),
    )
    description = models.TextField(blank=True)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name", "code")
        verbose_name = _("Location")
        verbose_name_plural = _("Locations")

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name


class ProjectStatus(Choices):
    _ = Choices.Choice

    planned = _("planned")
    active = _("active")
    paused = _("paused")
    completed = _("completed")
    cancelled = _("cancelled")


class Project(AdminAbsoluteUrlMixin, NamedMixin.NonUnique, TimeStampMixin, models.Model):
    code = models.CharField(
        max_length=64,
        unique=True,
        help_text=_("Short unique identifier used by SC3 and reporting."),
    )
    external_id = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        null=True,
        help_text=_("Optional external identifier supplied by SC3."),
    )
    status = models.PositiveIntegerField(
        choices=ProjectStatus(),
        default=ProjectStatus.planned.id,
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects_managed",
    )
    default_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
    )
    location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
        help_text=_("Linked location provided by SC3."),
    )
    location_name = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("Primary project location or site label."),
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name", "code")
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name

    @property
    def active_deployments(self):
        return self.deployment_entries.filter(ended_at__isnull=True)

    @property
    def active_assets_count(self):
        annotated = getattr(self, "active_assets_total", None)
        if annotated is not None:
            return annotated
        return (
            self.active_deployments.values("base_object_id").distinct().count()
        )

    def default_assignee(self):
        return self.manager


class DeploymentStatus(Choices):
    _ = Choices.Choice

    deployed = _("deployed / in use")
    transit = _("in transit")
    maintenance = _("maintenance")
    storage = _("storage / standby")
    retired = _("retired")


class AssetStatusSnapshot(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="status_snapshots",
        on_delete=models.CASCADE,
    )
    date = models.DateField()
    status_label = models.CharField(max_length=64, blank=True)
    deployment_status_label = models.CharField(max_length=64, blank=True)
    open_maintenance = models.PositiveIntegerField(default=0)
    overdue_compliance = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("base_object", "date")
        verbose_name = _("Asset status snapshot")
        verbose_name_plural = _("Asset status snapshots")
        indexes = [
            models.Index(fields=["base_object", "date"]),
        ]


class AssetCostSnapshot(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="cost_snapshots",
        on_delete=models.CASCADE,
    )
    month = models.DateField(help_text=_("Snapshot month (first day of month)."))
    capex = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    opex = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    maintenance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    parts = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    fuel = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    active_hours = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    idle_hours = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    class Meta:
        unique_together = ("base_object", "month")
        verbose_name = _("Asset cost snapshot")
        verbose_name_plural = _("Asset cost snapshots")
        indexes = [
            models.Index(fields=["base_object", "month"]),
        ]


class ComplianceSnapshot(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="compliance_snapshots",
        on_delete=models.CASCADE,
    )
    date = models.DateField()
    status_label = models.CharField(max_length=32, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    risk_score = models.IntegerField(default=0)

    class Meta:
        unique_together = ("base_object", "date")
        verbose_name = _("Compliance snapshot")
        verbose_name_plural = _("Compliance snapshots")
        indexes = [
            models.Index(fields=["base_object", "date"]),
        ]


class DeploymentEntry(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="deployment_entries",
        on_delete=models.CASCADE,
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deployment_entries",
        help_text=_("Project or engagement this deployment supports."),
    )
    shift_label = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Roster or shift label (e.g. Day, Night, Alpha)."),
    )
    shift_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Scheduled start of the duty shift."),
    )
    shift_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Scheduled end of the duty shift."),
    )
    status = models.PositiveIntegerField(
        choices=DeploymentStatus(),
        default=DeploymentStatus.deployed.id,
    )
    assigned_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deployment_assignments",
    )
    assigned_to_team = models.ForeignKey(
        "accounts.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="asset_deployments",
    )
    location = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("Human readable deployment location (site, depot, project)."),
    )
    location_ref = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deployments",
        help_text=_("Linked location record for this deployment."),
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    current_speed_kmh = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Latest reported speed while this deployment is active."),
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    handover_notes = models.TextField(
        blank=True,
        help_text=_("Notes captured during the last handoff."),
    )
    last_telemetry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp of the last telemetry update tied to this deployment."),
    )

    class Meta:
        ordering = ("-started_at", "-pk")
        verbose_name = _("Deployment entry")
        verbose_name_plural = _("Deployment entries")
        indexes = [
            models.Index(fields=["base_object", "started_at"]),
            models.Index(fields=["project", "started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        parts = [self.get_status_display()]
        if self.project:
            parts.append(self.project.code or self.project.name)
        if self.shift_label:
            parts.append(self.shift_label)
        if self.location:
            parts.append(self.location)
        return " – ".join(parts)

    @property
    def is_active(self):
        return self.ended_at is None

    @property
    def active_assignments(self):
        return self.assignments.filter(ended_at__isnull=True)

    @property
    def roster_summary(self):
        active_assignments = list(self.active_assignments.select_related("user"))
        if not active_assignments:
            return _("Unassigned")
        names = [
            assignment.user.get_full_name() or assignment.user.username
            for assignment in active_assignments
        ]
        names = [name for name in names if name]
        return ", ".join(names)

    def record_telemetry_snapshot(self, *, captured_at=None, latitude=None, longitude=None, speed=None, reading=None):
        updates = []
        if captured_at and captured_at != self.last_telemetry_at:
            self.last_telemetry_at = captured_at
            updates.append("last_telemetry_at")
        if latitude is not None and latitude != self.latitude:
            self.latitude = latitude
            updates.append("latitude")
        if longitude is not None and longitude != self.longitude:
            self.longitude = longitude
            updates.append("longitude")
        if speed is not None and speed != self.current_speed_kmh:
            self.current_speed_kmh = speed
            updates.append("current_speed_kmh")
        if updates:
            updates.append("modified")
            self.save(update_fields=updates)
        if reading is not None:
            self.assignments.filter(ended_at__isnull=True).update(
                last_reported_at=captured_at,
                last_reported_metric=reading.metric,
            )


class DeploymentAssignment(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    deployment_entry = models.ForeignKey(
        DeploymentEntry,
        related_name="assignments",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="asset_deployment_assignments",
    )
    role = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Role of the person on this deployment (e.g. Operator, Driver)."),
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    handover_notes = models.TextField(blank=True)
    last_reported_at = models.DateTimeField(null=True, blank=True)
    last_reported_metric = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("-started_at", "-pk")
        verbose_name = _("Deployment assignment")
        verbose_name_plural = _("Deployment assignments")

    def __str__(self):
        display = self.user.get_full_name() or self.user.username
        return f"{display} – {self.deployment_entry}"

    @property
    def is_active(self):
        return self.ended_at is None

    def close(self, *, ended_at=None, handover_notes=None):
        if not ended_at:
            ended_at = timezone.now()
        self.ended_at = ended_at
        if handover_notes:
            self.handover_notes = handover_notes
        self.save(update_fields=["ended_at", "handover_notes", "modified"])

    def clean(self):
        super().clean()
        if self.user and self.deployment_entry_id:
            asset = self.deployment_entry.base_object
            if not OperatorCertification.valid_for(self.user, asset):
                raise ValidationError(
                    _("%(user)s does not hold an active certification for this asset."),
                    params={"user": self.user},
                )


class TelemetryReading(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="telemetry_readings",
        on_delete=models.CASCADE,
    )
    deployment_entry = models.ForeignKey(
        DeploymentEntry,
        null=True,
        blank=True,
        related_name="telemetry_events",
        on_delete=models.SET_NULL,
        help_text=_("Deployment assignment active when this reading was captured."),
    )
    source = models.CharField(
        max_length=64,
        help_text=_("Origin of the reading (device, system, integration)."),
    )
    metric = models.CharField(
        max_length=64,
        help_text=_("Name of the metric, e.g. fuel_level, temperature, altitude."),
    )
    unit = models.CharField(max_length=32, blank=True)
    value_numeric = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
    )
    value_text = models.CharField(max_length=256, blank=True)
    captured_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp when the measurement was captured on the device."),
    )
    ingested_at = models.DateTimeField(auto_now_add=True)
    raw_payload = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ("-captured_at", "-ingested_at")
        verbose_name = _("Telemetry reading")
        verbose_name_plural = _("Telemetry readings")
        indexes = [
            models.Index(fields=["base_object", "metric", "captured_at"]),
            models.Index(fields=["metric"]),
        ]

    def __str__(self):
        return "{} – {}".format(self.metric, self.value_numeric or self.value_text or "-")

    def clean(self):
        if self.value_numeric is None and not self.value_text:
            raise ValidationError(
                _("Provide either a numeric value or a textual value for telemetry readings.")
            )


class _FilterByContentTypeManager(models.Manager):
    def __init__(self, model_label: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._model_label = model_label

    def get_queryset(self):
        qs = super().get_queryset()
        try:
            app_label, model_name = self._model_label.split(".")
            ct = ContentType.objects.get(app_label=app_label, model=model_name.lower())
            return qs.filter(base_object__content_type=ct)
        except Exception:
            return qs.none()


# Heavy Equipment filtered proxies
class HeavyEquipmentDeploymentEntry(DeploymentEntry):
    objects = _FilterByContentTypeManager("heavy_equipment.heavyequipmentasset")

    class Meta:
        proxy = True
        verbose_name = _("Assignment (heavy equipment)")
        verbose_name_plural = _("Assignments (heavy equipment)")


class HeavyEquipmentTelemetryReading(TelemetryReading):
    objects = _FilterByContentTypeManager("heavy_equipment.heavyequipmentasset")

    class Meta:
        proxy = True
        verbose_name = _("Usage log (heavy equipment)")
        verbose_name_plural = _("Usage logs (heavy equipment)")


class HeavyEquipmentMaintenanceRecord(MaintenanceRecord):
    objects = _FilterByContentTypeManager("heavy_equipment.heavyequipmentasset")

    class Meta:
        proxy = True
        verbose_name = _("Maintenance log (heavy equipment)")
        verbose_name_plural = _("Maintenance logs (heavy equipment)")


class HeavyEquipmentAssetIncident(AssetIncident):
    objects = _FilterByContentTypeManager("heavy_equipment.heavyequipmentasset")

    class Meta:
        proxy = True
        verbose_name = _("Status log (heavy equipment)")
        verbose_name_plural = _("Status logs (heavy equipment)")


# Trailer filtered proxies
class TrailerDeploymentEntry(DeploymentEntry):
    objects = _FilterByContentTypeManager("trailers.trailerasset")

    class Meta:
        proxy = True
        verbose_name = _("Assignment (trailers)")
        verbose_name_plural = _("Assignments (trailers)")


class TrailerTelemetryReading(TelemetryReading):
    objects = _FilterByContentTypeManager("trailers.trailerasset")

    class Meta:
        proxy = True
        verbose_name = _("Usage log (trailers)")
        verbose_name_plural = _("Usage logs (trailers)")


class TrailerMaintenanceRecord(MaintenanceRecord):
    objects = _FilterByContentTypeManager("trailers.trailerasset")

    class Meta:
        proxy = True
        verbose_name = _("Maintenance log (trailers)")
        verbose_name_plural = _("Maintenance logs (trailers)")


class TrailerAssetIncident(AssetIncident):
    objects = _FilterByContentTypeManager("trailers.trailerasset")

    class Meta:
        proxy = True
        verbose_name = _("Status log (trailers)")
        verbose_name_plural = _("Status logs (trailers)")


# Power & Lighting filtered proxies
class PowerDeploymentEntry(DeploymentEntry):
    objects = _FilterByContentTypeManager("power.powerasset")

    class Meta:
        proxy = True
        verbose_name = _("Assignment (power & lighting)")
        verbose_name_plural = _("Assignments (power & lighting)")


class PowerTelemetryReading(TelemetryReading):
    objects = _FilterByContentTypeManager("power.powerasset")

    class Meta:
        proxy = True
        verbose_name = _("Usage log (power & lighting)")
        verbose_name_plural = _("Usage logs (power & lighting)")


class PowerMaintenanceRecord(MaintenanceRecord):
    objects = _FilterByContentTypeManager("power.powerasset")

    class Meta:
        proxy = True
        verbose_name = _("Maintenance log (power & lighting)")
        verbose_name_plural = _("Maintenance logs (power & lighting)")


class PowerAssetIncident(AssetIncident):
    objects = _FilterByContentTypeManager("power.powerasset")

    class Meta:
        proxy = True
        verbose_name = _("Status log (power & lighting)")
        verbose_name_plural = _("Status logs (power & lighting)")
