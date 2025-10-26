from decimal import Decimal
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q, Count, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.accounts.models import Team
from ralph.lib.lifecycle import LifecycleStatusMixin
from ralph.lib.mixins.models import AdminAbsoluteUrlMixin, TimeStampMixin


class DroneQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=DroneStatus.OPERATIONAL)

    def due_for_maintenance(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        return self.filter(
            Q(next_maintenance_date__isnull=False, next_maintenance_date__lte=reference_date)
            | Q(
                next_maintenance_flight_hours__isnull=False,
                flight_hours__gte=F("next_maintenance_flight_hours"),
            )
        )


class DroneType(models.TextChoices):
    QUADCOPTER = "quadcopter", _("Quadcopter")
    FIXED_WING = "fixed_wing", _("Fixed-wing")
    VTOL = "vtol", _("VTOL")
    HEXACOPTER = "hexacopter", _("Hexacopter")
    OTHER = "other", _("Other")


class DroneStatus(models.TextChoices):
    OPERATIONAL = "operational", _("Operational")
    GROUNDED = "grounded", _("Grounded")
    AWAITING_CERTIFICATION = "awaiting_certification", _("Awaiting Certification")
    RETIRED = "retired", _("Retired")


class Drone(LifecycleStatusMixin, AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    identifier = models.CharField(
        max_length=64,
        unique=True,
        verbose_name=_("Identifier"),
    )
    model_name = models.CharField(
        max_length=128,
        verbose_name=_("Model"),
    )
    drone_type = models.CharField(
        max_length=32,
        choices=DroneType.choices,
        default=DroneType.QUADCOPTER,
        verbose_name=_("Type"),
    )
    serial_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Serial number"),
    )
    firmware_version = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Firmware version"),
    )
    last_firmware_update = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Last firmware update"),
    )
    status = models.CharField(
        max_length=32,
        choices=DroneStatus.choices,
        default=DroneStatus.AWAITING_CERTIFICATION,
        verbose_name=_("Status"),
    )
    payload_capacity_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Payload capacity (kg)"),
    )
    payload_description = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Payload details"),
    )
    flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        default=0,
        verbose_name=_("Flight hours"),
    )
    flight_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Flight count"),
    )
    battery_cycle_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Battery cycle count"),
    )
    last_service_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Last service date"),
    )
    maintenance_interval_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Maintenance interval (days)"),
    )
    maintenance_interval_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("Maintenance interval (flight hours)"),
    )
    next_maintenance_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next maintenance date"),
    )
    next_maintenance_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("Next maintenance flight hours"),
    )
    registration_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Registration number"),
    )
    pilot_license_required = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Required pilot license"),
    )
    assigned_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        related_name="drones",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned team"),
    )
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drones",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned user"),
    )
    assigned_location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Assigned location"),
    )
    current_mission = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Current mission"),
    )
    retired_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Retired at"),
    )
    acquisition_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Acquisition date"),
    )
    acquisition_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Acquisition cost"),
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

    STATUS_TRANSITIONS = {
        DroneStatus.OPERATIONAL: {DroneStatus.GROUNDED, DroneStatus.RETIRED},
        DroneStatus.GROUNDED: {
            DroneStatus.OPERATIONAL,
            DroneStatus.AWAITING_CERTIFICATION,
            DroneStatus.RETIRED,
        },
        DroneStatus.AWAITING_CERTIFICATION: {
            DroneStatus.OPERATIONAL,
            DroneStatus.RETIRED,
        },
        DroneStatus.RETIRED: set(),
    }

    objects = DroneQuerySet.as_manager()

    class Meta:
        verbose_name = _("Drone")
        verbose_name_plural = _("Drones")
        ordering = ("identifier",)

    def __str__(self):
        return "{} ({})".format(self.identifier, self.model_name)

    def pre_status_change(self, old_status, new_status, user, note="", metadata=None):
        metadata = metadata or {}
        updates = []
        if new_status == DroneStatus.RETIRED:
            if self.assigned_user_id:
                self.assigned_user = None
                updates.append("assigned_user")
            self.retired_at = metadata.get("retired_at", date.today())
            updates.append("retired_at")
        if metadata.get("next_maintenance_date"):
            self.next_maintenance_date = metadata["next_maintenance_date"]
            updates.append("next_maintenance_date")
        if metadata.get("next_maintenance_flight_hours") is not None:
            self.next_maintenance_flight_hours = metadata["next_maintenance_flight_hours"]
            updates.append("next_maintenance_flight_hours")
        if metadata.get("firmware_version"):
            self.firmware_version = metadata["firmware_version"]
            updates.append("firmware_version")
            if metadata.get("last_firmware_update"):
                self.last_firmware_update = metadata["last_firmware_update"]
                updates.append("last_firmware_update")
        return updates

    def create_status_log(self, user, old_status, new_status, note="", metadata=None):
        DroneStatusLog.objects.create(
            drone=self,
            previous_status=old_status,
            new_status=new_status,
            changed_by=user,
            note=note,
            metadata=metadata or {},
        )

    def assign_to(
        self,
        user=None,
        team=None,
        location="",
        mission="",
        assigned_by=None,
        note="",
    ):
        if self.status != DroneStatus.OPERATIONAL:
            raise ValidationError(
                _("Drone must be operational before assignment.")
            )
        with transaction.atomic():
            DroneAssignment.close_open_assignments(self, assigned_by)
            DroneAssignment.objects.create(
                drone=self,
                assignee=user,
                team=team,
                location=location or "",
                mission=mission or "",
                assigned_by=assigned_by,
                note=note,
            )
            update_fields = []
            if user is not None or self.assigned_user_id:
                self.assigned_user = user
                update_fields.append("assigned_user")
            if team is not None or self.assigned_team_id:
                self.assigned_team = team
                update_fields.append("assigned_team")
            if location is not None:
                self.assigned_location = location or ""
                update_fields.append("assigned_location")
            if mission is not None:
                self.current_mission = mission or ""
                update_fields.append("current_mission")
            if update_fields:
                update_fields.append("modified")
                self.save(update_fields=update_fields)

    def unassign(self, unassigned_by=None, note=""):
        if (
            not self.assigned_user
            and not self.assigned_team
            and not self.assigned_location
            and not self.current_mission
        ):
            return False
        with transaction.atomic():
            DroneAssignment.close_open_assignments(self, unassigned_by, note=note)
            self.assigned_user = None
            self.assigned_team = None
            self.assigned_location = ""
            self.current_mission = ""
            self.save(
                update_fields=[
                    "assigned_user",
                    "assigned_team",
                    "assigned_location",
                    "current_mission",
                    "modified",
                ]
            )
        return True

    def is_maintenance_overdue(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        if self.next_maintenance_date and self.next_maintenance_date <= reference_date:
            return True
        if (
            self.next_maintenance_flight_hours is not None
            and self.flight_hours >= self.next_maintenance_flight_hours
        ):
            return True
        return False

    @property
    def total_cost_of_ownership(self):
        cost = Decimal(self.acquisition_cost or 0)
        return cost + Decimal(self.total_maintenance_cost) + Decimal(
            self.total_operational_cost
        )

class DroneStatusLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    drone = models.ForeignKey(
        Drone,
        related_name="status_logs",
        on_delete=models.CASCADE,
    )
    previous_status = models.CharField(
        max_length=32,
        choices=DroneStatus.choices,
        verbose_name=_("Previous status"),
    )
    new_status = models.CharField(
        max_length=32,
        choices=DroneStatus.choices,
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
        verbose_name = _("Drone status log entry")
        verbose_name_plural = _("Drone status log entries")
        ordering = ("-created",)

    def __str__(self):
        return "{}: {} → {}".format(self.drone, self.previous_status, self.new_status)


class DroneMaintenanceLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    drone = models.ForeignKey(
        Drone,
        related_name="maintenance_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Maintenance date"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("Flight hours at service"),
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
    firmware_version = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Firmware version"),
    )
    battery_cycles = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Battery cycles"),
    )
    next_maintenance_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next maintenance date"),
    )
    next_maintenance_flight_hours = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name=_("Next maintenance flight hours"),
    )

    class Meta:
        verbose_name = _("Drone maintenance log")
        verbose_name_plural = _("Drone maintenance logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.drone, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        drone = self.drone
        updates = set()
        if self.next_maintenance_date:
            drone.next_maintenance_date = self.next_maintenance_date
            updates.add("next_maintenance_date")
        elif drone.maintenance_interval_days and self.date:
            drone.next_maintenance_date = self.date + timedelta(
                days=drone.maintenance_interval_days
            )
            updates.add("next_maintenance_date")

        if self.next_maintenance_flight_hours is not None:
            drone.next_maintenance_flight_hours = self.next_maintenance_flight_hours
            updates.add("next_maintenance_flight_hours")
        elif (
            drone.maintenance_interval_flight_hours is not None
            and self.flight_hours is not None
        ):
            drone.next_maintenance_flight_hours = (
                self.flight_hours + drone.maintenance_interval_flight_hours
            )
            updates.add("next_maintenance_flight_hours")

        if self.flight_hours is not None:
            drone.flight_hours = self.flight_hours
            updates.add("flight_hours")

        if self.battery_cycles is not None:
            drone.battery_cycle_count = self.battery_cycles
            updates.add("battery_cycle_count")

        if updates:
            updates.add("modified")
            drone.last_service_date = self.date
            updates.add("last_service_date")
            drone.save(update_fields=list(updates))

        aggregates = drone.maintenance_logs.aggregate(total_cost=Sum("cost"))
        total_cost = aggregates.get("total_cost") or Decimal("0.00")
        if drone.total_maintenance_cost != total_cost:
            drone.total_maintenance_cost = total_cost
            drone.save(update_fields=["total_maintenance_cost", "modified"])


class DroneAssignment(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    drone = models.ForeignKey(
        Drone,
        related_name="assignments",
        on_delete=models.CASCADE,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drone_assignments",
        on_delete=models.SET_NULL,
        verbose_name=_("Assignee"),
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        related_name="drone_assignments",
        on_delete=models.SET_NULL,
        verbose_name=_("Team"),
    )
    location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Location"),
    )
    mission = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Mission"),
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drone_assignments_created",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned by"),
    )
    unassigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="drone_assignments_closed",
        on_delete=models.SET_NULL,
        verbose_name=_("Unassigned by"),
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Drone assignment")
        verbose_name_plural = _("Drone assignments")
        ordering = ("-assigned_at",)

    def __str__(self):
        target = self.assignee or self.team or self.location or "-"
        return "{} → {}".format(self.drone, target)

    @classmethod
    def close_open_assignments(cls, drone, user=None, note=""):
        assignments = (
            cls.objects.select_for_update()
            .filter(drone=drone, unassigned_at__isnull=True)
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


class DroneFlightLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    drone = models.ForeignKey(
        Drone,
        related_name="flight_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Flight date"))
    duration_minutes = models.PositiveIntegerField(
        verbose_name=_("Duration (minutes)"),
    )
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Distance (km)"),
    )
    mission = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Mission"),
    )
    battery_cycles_used = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Battery cycles used"),
    )
    operational_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Operational cost"),
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
        verbose_name = _("Drone flight log")
        verbose_name_plural = _("Drone flight logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.drone, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        drone = self.drone
        updates = {"flight_hours", "flight_count", "modified"}
        if self.battery_cycles_used is not None:
            new_cycles = max(drone.battery_cycle_count or 0, self.battery_cycles_used)
            if drone.battery_cycle_count != new_cycles:
                drone.battery_cycle_count = new_cycles
                updates.add("battery_cycle_count")
        aggregates = drone.flight_logs.aggregate(
            total_minutes=Sum("duration_minutes"),
            flights=Count("id"),
        )
        total_minutes = aggregates.get("total_minutes") or 0
        flights = aggregates.get("flights") or 0
        drone.flight_hours = (
            (Decimal(total_minutes) / Decimal("60")) if total_minutes else Decimal("0")
        )
        drone.flight_count = flights
        drone.save(update_fields=list(updates))

        op_aggregates = drone.flight_logs.aggregate(total_cost=Sum("operational_cost"))
        total_cost = op_aggregates.get("total_cost") or Decimal("0.00")
        if drone.total_operational_cost != total_cost:
            drone.total_operational_cost = total_cost
            drone.save(update_fields=["total_operational_cost", "modified"])
