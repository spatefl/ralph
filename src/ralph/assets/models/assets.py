# -*- coding: utf-8 -*-
import datetime
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from mptt.models import MPTTModel, TreeForeignKey

from ralph.accounts.models import Team
from ralph.admin.autocomplete import AutocompleteTooltipMixin
from ralph.assets.models.base import BaseObject
from ralph.assets.models.choices import ModelVisualizationLayout, ObjectModelType
from ralph.lib.dj_choices import Choices
from ralph.lib.custom_fields.models import CustomFieldMeta, WithCustomFieldsMixin
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


class ComplianceRecordQuerySet(models.QuerySet):
    def upcoming(self, within_days=30):
        today = timezone.now().date()
        deadline = today + timedelta(days=within_days)
        return self.filter(
            expires_on__gte=today,
            expires_on__lte=deadline,
        )

    def overdue(self):
        today = timezone.now().date()
        return self.filter(expires_on__lt=today)


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
    frequency_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Number of days between required checks."),
    )
    grace_period_days = models.PositiveIntegerField(
        default=0,
        help_text=_("Grace period before the compliance item is considered overdue."),
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


class DeploymentStatus(Choices):
    _ = Choices.Choice

    deployed = _("deployed / in use")
    transit = _("in transit")
    maintenance = _("maintenance")
    storage = _("storage / standby")
    retired = _("retired")


class DeploymentEntry(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="deployment_entries",
        on_delete=models.CASCADE,
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
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-started_at", "-pk")
        verbose_name = _("Deployment entry")
        verbose_name_plural = _("Deployment entries")
        indexes = [
            models.Index(fields=["base_object", "started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return "{} – {}".format(self.get_status_display(), self.location or _("Unknown"))

    @property
    def is_active(self):
        return self.ended_at is None


class TelemetryReading(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    base_object = models.ForeignKey(
        BaseObject,
        related_name="telemetry_readings",
        on_delete=models.CASCADE,
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
