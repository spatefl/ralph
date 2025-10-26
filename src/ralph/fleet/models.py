from decimal import Decimal
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.lib.lifecycle import LifecycleStatusMixin
from ralph.lib.mixins.models import AdminAbsoluteUrlMixin, TimeStampMixin


class VehicleQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(status=VehicleStatus.DECOMMISSIONED)

    def due_for_service(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        return self.filter(
            Q(next_service_date__isnull=False, next_service_date__lte=reference_date)
            | Q(
                next_service_odometer__isnull=False,
                odometer_km__gte=F("next_service_odometer"),
            )
        )


class FuelType(models.TextChoices):
    GASOLINE = "gasoline", _("Gasoline")
    DIESEL = "diesel", _("Diesel")
    HYBRID = "hybrid", _("Hybrid")
    ELECTRIC = "electric", _("Electric")
    OTHER = "other", _("Other")


class VehicleStatus(models.TextChoices):
    ORDERED = "ordered", _("Ordered / Purchased")
    IN_SERVICE = "in_service", _("In Service")
    UNDER_MAINTENANCE = "under_maintenance", _("Under Maintenance")
    DECOMMISSIONED = "decommissioned", _("Decommissioned")


class Vehicle(LifecycleStatusMixin, AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vin = models.CharField(
        max_length=17,
        unique=True,
        verbose_name=_("VIN"),
    )
    license_plate = models.CharField(
        max_length=32,
        unique=True,
        verbose_name=_("License plate"),
    )
    make = models.CharField(
        max_length=64,
        verbose_name=_("Make"),
    )
    model_name = models.CharField(
        max_length=64,
        verbose_name=_("Model"),
    )
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(1900), MaxValueValidator(2100)],
        verbose_name=_("Year"),
    )
    fuel_type = models.CharField(
        max_length=16,
        choices=FuelType.choices,
        default=FuelType.GASOLINE,
        verbose_name=_("Fuel type"),
    )
    seating_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Seating capacity"),
    )
    cargo_capacity_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Cargo capacity (kg)"),
    )
    telematics_id = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Telematics ID"),
    )
    odometer_km = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Odometer (km)"),
    )
    average_fuel_consumption = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Fuel consumption (L/100km)"),
    )
    status = models.CharField(
        max_length=32,
        choices=VehicleStatus.choices,
        default=VehicleStatus.ORDERED,
        verbose_name=_("Status"),
    )
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="fleet_vehicles",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned user"),
    )
    assigned_location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Assigned location"),
    )
    acquisition_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Acquisition date"),
    )
    purchase_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Purchase cost"),
    )
    depreciation_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Depreciation rate (%)"),
    )
    total_maintenance_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total maintenance cost"),
    )
    total_operational_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total operational cost"),
    )
    warranty_expiration = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Warranty expiration"),
    )
    service_contract_expiration = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Service contract expiration"),
    )
    cost_center = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Cost center"),
    )
    maintenance_interval_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Service interval (days)"),
    )
    maintenance_interval_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Service interval (km)"),
    )
    next_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next service date"),
    )
    next_service_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Next service odometer (km)"),
    )
    decommissioned_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Decommissioned at"),
    )

    STATUS_TRANSITIONS = {
        VehicleStatus.ORDERED: {VehicleStatus.IN_SERVICE, VehicleStatus.DECOMMISSIONED},
        VehicleStatus.IN_SERVICE: {
            VehicleStatus.UNDER_MAINTENANCE,
            VehicleStatus.DECOMMISSIONED,
        },
        VehicleStatus.UNDER_MAINTENANCE: {
            VehicleStatus.IN_SERVICE,
            VehicleStatus.DECOMMISSIONED,
        },
        VehicleStatus.DECOMMISSIONED: set(),
    }

    objects = VehicleQuerySet.as_manager()

    class Meta:
        verbose_name = _("Vehicle")
        verbose_name_plural = _("Vehicles")
        ordering = ("make", "model_name", "license_plate")

    def __str__(self):
        return "{} {} ({})".format(self.make, self.model_name, self.license_plate)

    def pre_status_change(self, old_status, new_status, user, note="", metadata=None):
        metadata = metadata or {}
        updates = []
        if new_status == VehicleStatus.DECOMMISSIONED:
            if self.assigned_user_id:
                self.assigned_user = None
                updates.append("assigned_user")
            self.decommissioned_at = metadata.get("decommissioned_at", date.today())
            updates.append("decommissioned_at")
        if metadata.get("next_service_date"):
            self.next_service_date = metadata["next_service_date"]
            updates.append("next_service_date")
        if metadata.get("next_service_odometer") is not None:
            self.next_service_odometer = metadata["next_service_odometer"]
            updates.append("next_service_odometer")
        return updates

    def create_status_log(self, user, old_status, new_status, note="", metadata=None):
        VehicleStatusLog.objects.create(
            vehicle=self,
            previous_status=old_status,
            new_status=new_status,
            changed_by=user,
            note=note,
            metadata=metadata or {},
        )

    def assign_to(self, assignee=None, location="", assigned_by=None, note=""):
        if self.status == VehicleStatus.DECOMMISSIONED:
            raise ValidationError(_("Cannot assign a decommissioned vehicle."))
        with transaction.atomic():
            VehicleAssignment.close_open_assignments(self, assigned_by)
            VehicleAssignment.objects.create(
                vehicle=self,
                assignee=assignee,
                location=location or "",
                assigned_by=assigned_by,
                note=note,
            )
            updated_fields = []
            if assignee is not None or self.assigned_user_id:
                self.assigned_user = assignee
                updated_fields.append("assigned_user")
            if location is not None:
                self.assigned_location = location or ""
                updated_fields.append("assigned_location")
            if updated_fields:
                updated_fields.append("modified")
                self.save(update_fields=updated_fields)

    def unassign(self, unassigned_by=None, note=""):
        if not self.assigned_user and not self.assigned_location:
            return False
        with transaction.atomic():
            VehicleAssignment.close_open_assignments(self, unassigned_by, note=note)
            self.assigned_user = None
            self.assigned_location = ""
            self.save(update_fields=["assigned_user", "assigned_location", "modified"])
        return True

    def is_service_overdue(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        due_date = self.next_service_date
        due_odometer = self.next_service_odometer
        if due_date and due_date <= reference_date:
            return True
        if due_odometer is not None and self.odometer_km >= due_odometer:
            return True
        return False

    @property
    def total_cost_of_ownership(self):
        cost = Decimal(self.purchase_cost or 0)
        return cost + Decimal(self.total_maintenance_cost) + Decimal(
            self.total_operational_cost
        )


class VehicleStatusLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        related_name="status_logs",
        on_delete=models.CASCADE,
    )
    previous_status = models.CharField(
        max_length=32,
        choices=VehicleStatus.choices,
        verbose_name=_("Previous status"),
    )
    new_status = models.CharField(
        max_length=32,
        choices=VehicleStatus.choices,
        verbose_name=_("New status"),
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Changed by"),
    )
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Vehicle status log entry")
        verbose_name_plural = _("Vehicle status log entries")
        ordering = ("-created",)

    def __str__(self):
        return "{}: {} → {}".format(self.vehicle, self.previous_status, self.new_status)


class VehicleMaintenanceLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        related_name="maintenance_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Maintenance date"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    mileage_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Odometer at service (km)"),
    )
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Cost"),
    )
    reference = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Reference / ticket"),
    )
    performed_by = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Performed by"),
    )
    next_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next service date"),
    )
    next_service_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Next service odometer (km)"),
    )

    class Meta:
        verbose_name = _("Vehicle maintenance log")
        verbose_name_plural = _("Vehicle maintenance logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.vehicle, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        vehicle = self.vehicle
        updates = set()
        if self.next_service_date:
            vehicle.next_service_date = self.next_service_date
            updates.add("next_service_date")
        elif vehicle.maintenance_interval_days and self.date:
            vehicle.next_service_date = self.date + timedelta(
                days=vehicle.maintenance_interval_days
            )
            updates.add("next_service_date")

        if self.next_service_odometer is not None:
            vehicle.next_service_odometer = self.next_service_odometer
            updates.add("next_service_odometer")
        elif (
            vehicle.maintenance_interval_km
            and self.mileage_km is not None
        ):
            vehicle.next_service_odometer = (
                self.mileage_km + vehicle.maintenance_interval_km
            )
            updates.add("next_service_odometer")

        if self.mileage_km is not None and self.mileage_km >= vehicle.odometer_km:
            vehicle.odometer_km = self.mileage_km
            updates.add("odometer_km")

        if updates:
            updates.add("modified")
            vehicle.save(update_fields=list(updates))

        aggregates = vehicle.maintenance_logs.aggregate(total_cost=Sum("cost"))
        total = aggregates.get("total_cost") or Decimal("0.00")
        if vehicle.total_maintenance_cost != total:
            vehicle.total_maintenance_cost = total
            vehicle.save(update_fields=["total_maintenance_cost", "modified"])


class VehicleAssignment(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        related_name="assignments",
        on_delete=models.CASCADE,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="vehicle_assignments",
        on_delete=models.SET_NULL,
        verbose_name=_("Assignee"),
    )
    location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Location"),
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="vehicle_assignments_created",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned by"),
    )
    unassigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="vehicle_assignments_closed",
        on_delete=models.SET_NULL,
        verbose_name=_("Unassigned by"),
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Vehicle assignment")
        verbose_name_plural = _("Vehicle assignments")
        ordering = ("-assigned_at",)

    @classmethod
    def close_open_assignments(cls, vehicle, user=None, note=""):
        assignments = (
            cls.objects.select_for_update()
            .filter(vehicle=vehicle, unassigned_at__isnull=True)
        )
        now = timezone.now()
        for assignment in assignments:
            assignment.unassigned_at = now
            assignment.unassigned_by = user
            if note:
                assignment.note = (
                    assignment.note + "\n" if assignment.note else ""
                ) + note
            assignment.save(
                update_fields=["unassigned_at", "unassigned_by", "note", "modified"]
            )

    def __str__(self):
        return "{} → {}".format(self.vehicle, self.assignee or self.location or "-")


class VehicleUsageLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        related_name="usage_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Usage date"))
    odometer_km = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Odometer reading (km)"),
    )
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Distance (km)"),
    )
    fuel_volume_l = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Fuel used (L)"),
    )
    fuel_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Fuel cost"),
    )
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Recorded by"),
    )

    class Meta:
        verbose_name = _("Vehicle usage log")
        verbose_name_plural = _("Vehicle usage logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.vehicle, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        vehicle = self.vehicle
        updates = set()
        if self.odometer_km is not None and self.odometer_km >= vehicle.odometer_km:
            vehicle.odometer_km = self.odometer_km
            updates.add("odometer_km")
        if self.distance_km and self.fuel_volume_l and self.distance_km > 0:
            fuel_per_100 = (self.fuel_volume_l / self.distance_km) * Decimal("100")
            vehicle.average_fuel_consumption = fuel_per_100
            updates.add("average_fuel_consumption")
        if updates:
            updates.add("modified")
            vehicle.save(update_fields=list(updates))

        aggregates = vehicle.usage_logs.aggregate(
            total_distance=Sum("distance_km"), total_fuel=Sum("fuel_volume_l")
        )
        total_distance = aggregates.get("total_distance")
        total_fuel = aggregates.get("total_fuel")
        if total_distance and total_fuel and total_distance > 0:
            avg = (total_fuel / total_distance) * Decimal("100")
            if vehicle.average_fuel_consumption != avg:
                vehicle.average_fuel_consumption = avg
                vehicle.save(update_fields=["average_fuel_consumption", "modified"])

        op_aggregates = vehicle.usage_logs.aggregate(total_cost=Sum("fuel_cost"))
        total_cost = op_aggregates.get("total_cost") or Decimal("0.00")
        if vehicle.total_operational_cost != total_cost:
            vehicle.total_operational_cost = total_cost
            vehicle.save(update_fields=["total_operational_cost", "modified"])
