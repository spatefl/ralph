from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.heavy_equipment.models import (
    HeavyEquipmentAsset,
    HeavyEquipmentAssetStatus,
    HeavyEquipmentType,
)


class PowerAssetType(models.TextChoices):
    GENERATOR = "generator", _("Generator")
    LIGHT_TOWER = "light_tower", _("Light tower")
    BATTERY = "battery", _("Battery or solar pack")
    PUMP = "pump", _("Pump / auxiliary power")


class PowerAssetTypeManager(models.Manager):
    def __init__(self, asset_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.asset_type = asset_type

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.asset_type:
            return queryset.filter(power_asset_type=self.asset_type)
        return queryset.none()


class PowerAsset(HeavyEquipmentAsset):
    power_asset_type = models.CharField(
        max_length=32,
        choices=PowerAssetType.choices,
        default=PowerAssetType.GENERATOR,
    )
    max_output_kw = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("rated output (kW)"),
    )
    supports_three_phase = models.BooleanField(default=False)
    fuel_burn_rate_lph = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Estimated fuel burn rate (L/h) at nominal load."),
    )
    last_runtime_hours = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Runtime hours recorded at last service."),
    )

    class Meta:
        verbose_name = _("Power & lighting asset")
        verbose_name_plural = _("Power & lighting assets")

    def save(self, *args, **kwargs):
        equipment_type = HeavyEquipmentType.GENERATOR
        if self.power_asset_type == PowerAssetType.LIGHT_TOWER:
            equipment_type = HeavyEquipmentType.LIGHT_TOWER
        elif self.power_asset_type == PowerAssetType.PUMP:
            equipment_type = HeavyEquipmentType.PUMP
        self.equipment_type = equipment_type
        super().save(*args, **kwargs)

    def record_runtime(self, hours_increment):
        hours_increment = Decimal(hours_increment or 0)
        if hours_increment <= 0:
            return
        self.hours_used = (self.hours_used or Decimal("0")) + hours_increment
        self.last_runtime_hours = self.hours_used
        self.last_status_change = timezone.now().date()
        self.save(update_fields=["hours_used", "last_runtime_hours", "last_status_change", "modified"])


def _make_power_proxy(name, asset_type, verbose_name, verbose_name_plural):
    attrs = {
        "objects": PowerAssetTypeManager(asset_type),
        "__module__": __name__,
        "Meta": type(
            "Meta",
            (PowerAsset.Meta,),
            {
                "proxy": True,
                "verbose_name": verbose_name,
                "verbose_name_plural": verbose_name_plural,
            },
        ),
    }
    return type(name, (PowerAsset,), attrs)


GeneratorAsset = _make_power_proxy(
    "GeneratorAsset",
    PowerAssetType.GENERATOR,
    _("Generator"),
    _("Generators"),
)
LightTowerAsset = _make_power_proxy(
    "LightTowerAsset",
    PowerAssetType.LIGHT_TOWER,
    _("Light tower"),
    _("Light towers"),
)
BatteryAsset = _make_power_proxy(
    "BatteryAsset",
    PowerAssetType.BATTERY,
    _("Battery or solar pack"),
    _("Battery and solar packs"),
)
PumpAsset = _make_power_proxy(
    "PumpAsset",
    PowerAssetType.PUMP,
    _("Pump / auxiliary power"),
    _("Pumps / auxiliary power"),
)
