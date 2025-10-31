from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.heavy_equipment.models import (
    HeavyEquipmentAsset,
    HeavyEquipmentAssetStatus,
    HeavyEquipmentType,
)


class TrailerSubtype(models.TextChoices):
    COMMAND = "command", _("Mobile command trailer")
    OFFICE = "office", _("Office trailer")
    RESTROOM = "restroom", _("Restroom trailer")
    SHOWER = "shower", _("Shower trailer")
    LAUNDRY = "laundry", _("Laundry trailer")
    SLEEPING = "sleeping", _("Sleeping quarters")
    MEDICAL = "medical", _("Medical/mobile clinic")
    COMMUNICATIONS = "communications", _("Communications/Fiber trailer")
    WATER = "water", _("Water tank trailer")
    STORAGE = "storage", _("Storage / logistics trailer")
    SPECIALTY = "specialty", _("Specialty trailer")


class TrailerOccupancyStatus(models.TextChoices):
    AVAILABLE = "available", _("Available")
    OCCUPIED = "occupied", _("Occupied")
    OUT_OF_SERVICE = "out_of_service", _("Out of service")
    CLEANING = "cleaning", _("Servicing / cleaning")


class TrailerSubtypeManager(models.Manager):
    def __init__(self, subtype, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subtype = subtype

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.subtype:
            return queryset.filter(trailer_subtype=self.subtype)
        return queryset.none()


class TrailerAsset(HeavyEquipmentAsset):
    trailer_subtype = models.CharField(
        max_length=32,
        choices=TrailerSubtype.choices,
        default=TrailerSubtype.SPECIALTY,
    )
    occupancy_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Total personnel capacity for this trailer."),
    )
    fixtures = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Number of restroom/shower fixtures (if applicable)."),
    )
    occupancy_status = models.CharField(
        max_length=32,
        choices=TrailerOccupancyStatus.choices,
        default=TrailerOccupancyStatus.AVAILABLE,
    )
    occupancy_level_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Most recent occupancy reading (percentage) captured from telemetry or inspections."
        ),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    occupancy_last_reported_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp of the last occupancy telemetry reading."),
    )
    has_climate_control = models.BooleanField(default=False)
    has_onboard_generator = models.BooleanField(default=False)
    last_service_visit = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = _("Trailer")
        verbose_name_plural = _("Trailers")

    def save(self, *args, **kwargs):
        subtype_to_equipment = {
            TrailerSubtype.WATER: HeavyEquipmentType.TANK,
        }
        self.equipment_type = subtype_to_equipment.get(
            self.trailer_subtype, HeavyEquipmentType.TRAILER
        )
        super().save(*args, **kwargs)

    def set_occupancy_level(self, percent, *, captured_at=None):
        percent = Decimal(str(percent or 0))
        if percent < 0:
            percent = Decimal("0")
        if percent > 100:
            percent = Decimal("100")
        self.occupancy_level_percent = percent
        if captured_at is not None:
            self.occupancy_last_reported_at = captured_at
        if percent >= Decimal("1"):
            self.occupancy_status = TrailerOccupancyStatus.OCCUPIED
        else:
            self.occupancy_status = TrailerOccupancyStatus.AVAILABLE

    def mark_serviced(self):
        self.last_service_visit = timezone.now().date()
        self.status = HeavyEquipmentAssetStatus.active.id
        self.save(update_fields=["last_service_visit", "status", "modified"])


def _make_trailer_proxy(name, subtype, verbose_name, verbose_name_plural):
    attrs = {
        "subtype": subtype,
        "objects": TrailerSubtypeManager(subtype),
        "__module__": __name__,
        "Meta": type(
            "Meta",
            (TrailerAsset.Meta,),
            {
                "proxy": True,
                "verbose_name": verbose_name,
                "verbose_name_plural": verbose_name_plural,
            },
        ),
    }
    return type(name, (TrailerAsset,), attrs)


CommandTrailer = _make_trailer_proxy(
    "CommandTrailer",
    TrailerSubtype.COMMAND,
    _("Command trailer"),
    _("Command trailers"),
)
OfficeTrailer = _make_trailer_proxy(
    "OfficeTrailer",
    TrailerSubtype.OFFICE,
    _("Office trailer"),
    _("Office trailers"),
)
RestroomTrailer = _make_trailer_proxy(
    "RestroomTrailer",
    TrailerSubtype.RESTROOM,
    _("Restroom trailer"),
    _("Restroom trailers"),
)
ShowerTrailer = _make_trailer_proxy(
    "ShowerTrailer",
    TrailerSubtype.SHOWER,
    _("Shower trailer"),
    _("Shower trailers"),
)
LaundryTrailer = _make_trailer_proxy(
    "LaundryTrailer",
    TrailerSubtype.LAUNDRY,
    _("Laundry trailer"),
    _("Laundry trailers"),
)
SleepingTrailer = _make_trailer_proxy(
    "SleepingTrailer",
    TrailerSubtype.SLEEPING,
    _("Sleeping quarters trailer"),
    _("Sleeping quarters trailers"),
)
MedicalTrailer = _make_trailer_proxy(
    "MedicalTrailer",
    TrailerSubtype.MEDICAL,
    _("Medical trailer"),
    _("Medical trailers"),
)
CommunicationsTrailer = _make_trailer_proxy(
    "CommunicationsTrailer",
    TrailerSubtype.COMMUNICATIONS,
    _("Communications trailer"),
    _("Communications trailers"),
)
WaterTrailer = _make_trailer_proxy(
    "WaterTrailer",
    TrailerSubtype.WATER,
    _("Water tank trailer"),
    _("Water tank trailers"),
)
StorageTrailer = _make_trailer_proxy(
    "StorageTrailer",
    TrailerSubtype.STORAGE,
    _("Storage trailer"),
    _("Storage trailers"),
)
SpecialtyTrailer = _make_trailer_proxy(
    "SpecialtyTrailer",
    TrailerSubtype.SPECIALTY,
    _("Specialty trailer"),
    _("Specialty trailers"),
)
