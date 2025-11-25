# -*- coding: utf-8 -*-
from collections import Counter
from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal
from itertools import cycle

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Prefetch, Q, Sum
from django.template import Library
from django.urls import NoReverseMatch, reverse
from django.core.cache import cache
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from ralph.accounts.helpers import (
    get_acceptance_url,
    get_access_card_acceptance_url,
    get_access_cards_to_accept,
    get_assets_to_accept,
    get_assets_to_accept_loan,
    get_assets_to_accept_return,
    get_loan_acceptance_url,
    get_return_acceptance_url,
    get_simcard_acceptance_url,
    get_simcards_to_accept,
    get_team_asset_acceptance_url,
    get_team_assets_to_accept,
    get_test_asset_acceptance_url,
    get_test_assets_to_accept,
)
from ralph.assets.models import (
    Asset,
    BaseObject,
    Service,
    ServiceEnvironment,
    MaintenanceRecord,
    ComplianceRecord,
    DeploymentEntry,
    Project,
    ProjectStatus,
)
from ralph.heavy_equipment.models import HeavyEquipmentAsset, HeavyEquipmentType
from ralph.trailers.models import TrailerAsset
from ralph.power.models import PowerAsset
from ralph.assets.services.analytics import (
    aggregate_metrics,
    trailer_status_metrics,
    power_utilization_metrics,
)
from ralph.back_office.models import BackOfficeAsset
from ralph.data_center.models import DataCenter, DataCenterAsset, Rack, RackAccessory

register = Library()
COLORS = ["green", "blue", "purple", "orange", "red", "pink"]

TILE_STYLE_MAP = {
    "overview_datacenterasset": {"class": "tile-datacenter", "icon": "fa-server"},
    "overview_backofficeasset": {"class": "tile-backoffice", "icon": "fa-briefcase"},
    "overview_ralphuser": {"class": "tile-users", "icon": "fa-users"},
    "category_heavy-equipment": {"class": "tile-heavy", "icon": "fa-industry"},
    "category_trailers": {"class": "tile-trailers", "icon": "fa-truck"},
    "category_power-lighting": {"class": "tile-power", "icon": "fa-bolt"},
    "category_fleet-assets": {"class": "tile-fleet", "icon": "fa-bus"},
    "category_field-gear": {"class": "tile-field-gear", "icon": "fa-wrench"},
    "category_drones": {"class": "tile-drones", "icon": "fa-plane"},
    "category_sensors": {"class": "tile-sensors", "icon": "fa-wifi"},
    "projects_summary": {"class": "tile-projects", "icon": "fa-tasks"},
    "supplemental_trailer": {"class": "tile-trailer-occupancy", "icon": "fa-area-chart"},
    "supplemental_power": {"class": "tile-power-utilization", "icon": "fa-line-chart"},
}


def format_currency(value):
    if value is None:
        value = Decimal("0")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    quantized = value.quantize(Decimal("0.01"))
    return "${:,.2f}".format(quantized)


def summarize_project_budgets(project_ids):
    project_ids = list(project_ids)
    totals = {
        "capex_budget": Decimal("0"),
        "capex_actual": Decimal("0"),
        "opex_budget": Decimal("0"),
        "opex_actual": Decimal("0"),
        "capex_variance": Decimal("0"),
        "opex_variance": Decimal("0"),
        "asset_count": 0,
    }
    if not project_ids:
        return totals

    asset_qs = (
        Asset.objects.filter(
            deployment_entries__project_id__in=project_ids,
            deployment_entries__ended_at__isnull=True,
        )
        .distinct()
        .select_related()
    )
    asset_ids = list(asset_qs.values_list("pk", flat=True))
    totals["asset_count"] = len(asset_ids)

    for asset in asset_qs.iterator():
        if asset.annual_capex_budget:
            totals["capex_budget"] += asset.annual_capex_budget
        if asset.annual_opex_budget:
            totals["opex_budget"] += asset.annual_opex_budget
        if asset.price:
            price_amount = getattr(asset.price, "amount", asset.price)
            totals["capex_actual"] += Decimal(price_amount)

    if asset_ids:
        opex_actual = (
            MaintenanceRecord.objects.filter(
                base_object_id__in=asset_ids, cost__isnull=False
            ).aggregate(total=Sum("cost"))["total"]
            or Decimal("0")
        )
    else:
        opex_actual = Decimal("0")

    totals["opex_actual"] = opex_actual
    totals["capex_variance"] = totals["capex_budget"] - totals["capex_actual"]
    totals["opex_variance"] = totals["opex_budget"] - totals["opex_actual"]
    return totals


def get_cached_metrics(cache_key, builder, timeout=300):
    data = cache.get(cache_key)
    if data is None:
        data = builder()
        cache.set(cache_key, data, timeout)
    return data


def get_user_equipment_tile_data(user):
    return {
        "class": "tile-my-equipment",
        "label": _("My equipment"),
        "count": BackOfficeAsset.objects.filter(Q(user=user) | Q(owner=user)).count(),
        "url": reverse("current_user_info"),
        "icon": "fa-laptop",
    }


def get_user_equipment_to_accept_tile_data(user):
    assets_to_accept_count = get_assets_to_accept(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "tile-pickup",
        "label": _("Hardware pick up"),
        "count": assets_to_accept_count,
        "url": get_acceptance_url(user),
        "icon": "fa-hand-paper-o",
    }


def get_user_simcard_to_accept_tile_data(user):
    simcard_to_accept_count = get_simcards_to_accept(user).count()
    if not simcard_to_accept_count:
        return None
    return {
        "class": "tile-simcard",
        "label": _("SIM Card pick up"),
        "count": simcard_to_accept_count,
        "url": get_simcard_acceptance_url(user),
        "icon": "fa-credit-card",
    }


def get_user_access_card_to_accept_tile_data(user):
    access_card_to_accept_count = get_access_cards_to_accept(user).count()
    if not access_card_to_accept_count:
        return None
    return {
        "class": "tile-access-card",
        "label": _("Access Card pick up"),
        "count": access_card_to_accept_count,
        "url": get_access_card_acceptance_url(user),
        "icon": "fa-address-card-o",
    }


def get_user_equipment_to_accept_loan_tile_data(user):
    assets_to_accept_count = get_assets_to_accept_loan(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "tile-loan",
        "label": _("Hardware loan"),
        "count": assets_to_accept_count,
        "url": get_loan_acceptance_url(user),
        "icon": "fa-exchange",
    }


def get_user_equipment_to_accept_return_tile_data(user):
    assets_to_accept_count = get_assets_to_accept_return(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "tile-return",
        "label": _("Hardware return"),
        "count": assets_to_accept_count,
        "url": get_return_acceptance_url(user),
        "icon": "fa-undo",
    }


def get_user_team_equipment_to_accept_tile_data(user):
    assets_to_accept_count = get_team_assets_to_accept(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "tile-team",
        "label": _("Team hardware pick up"),
        "count": assets_to_accept_count,
        "url": get_team_asset_acceptance_url(user),
        "icon": "fa-users",
    }


def get_user_test_equipment_to_accept_tile_data(user):
    assets_to_accept_count = get_test_assets_to_accept(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "tile-test",
        "label": _("Test hardware pick up"),
        "count": assets_to_accept_count,
        "url": get_test_asset_acceptance_url(user),
        "icon": "fa-flask",
    }


def get_available_space_in_data_centers(data_centers):
    available = (
        Rack.objects.filter(
            server_room__data_center__in=data_centers, require_position=True
        )
        .values_list("server_room__data_center__name")
        .annotate(s=Sum("max_u_height"))
    )
    return Counter(dict(available))


def get_used_space_in_data_centers(data_centers):
    used_by_accessories = (
        RackAccessory.objects.filter(
            rack__server_room__data_center__in=data_centers,
        )
        .values_list("rack__server_room__data_center__name")
        .annotate(s=Count("rack"))
    )
    used_by_assets = (
        DataCenterAsset.objects.filter(
            rack__server_room__data_center__in=data_centers,
            model__has_parent=False,
            rack__require_position=True,
        )
        .values_list("rack__server_room__data_center__name")
        .annotate(s=Sum("model__height_of_device"))
    )
    return Counter(dict(used_by_assets)) + Counter(dict(used_by_accessories))


@register.inclusion_tag("admin/templatetags/dc_capacity.html", takes_context=True)
def dc_capacity(context, data_centers=None, size="big"):
    user = context.request.user
    if not user.has_perm("data_center.view_datacenter"):
        return {}
    color = cycle(COLORS)
    if not data_centers:
        data_centers = DataCenter.objects.all()
    if not isinstance(data_centers, Iterable):
        data_centers = [data_centers]
    data_centers_mapper = dict(data_centers.values_list("name", "id"))
    available_space = get_available_space_in_data_centers(data_centers)
    used_space = get_used_space_in_data_centers(data_centers)
    difference = dict(available_space - used_space)
    results = []
    for name, value in sorted(difference.items()):
        capacity = 100 - (100 * value / available_space[name])
        tooltip = "<strong>Free U:</strong> {} ({} in total)".format(
            available_space[name] - int(used_space[name]), available_space[name]
        )
        results.append(
            {
                "url": "{}#/dc/{}".format(
                    reverse("dc_view"), data_centers_mapper[name]
                ),
                "tooltip": tooltip,
                "size": size,
                "color": next(color),
                "dc": name,
                "capacity": int(capacity),
            }
        )
    return {"capacities": results}


@register.inclusion_tag("admin/templatetags/ralph_summary.html", takes_context=True)
def ralph_summary(context):
    user = context.request.user
    models = [
        "data_center.DataCenterAsset",
        "back_office.BackOfficeAsset",
        "accounts.RalphUser",
    ]
    results = []
    overview_tiles = []
    supplemental_tiles = []
    today = timezone.now().date()

    def build_tile(label, count, url, css_class=None, meta=None, icon=None, style_key=None):
        style = TILE_STYLE_MAP.get(style_key or css_class or "", {})
        style_class = style.get("class")
        if css_class and style_class and style_class not in css_class:
            css_class = f"{style_class} {css_class}"
        else:
            css_class = css_class or style_class or slugify(label)
        icon = style.get("icon", icon or "fa-bar-chart")
        return {
            "label": label,
            "count": count,
            "class": css_class,
            "icon": icon,
            "url": url,
            "meta": meta or [],
        }

    def build_lifecycle_meta(queryset, total_assets=None):
        base_ids = list(queryset.values_list("id", flat=True))
        if not base_ids:
            return []
        maintenance_overdue = (
            MaintenanceRecord.objects.overdue()
            .filter(base_object_id__in=base_ids)
            .count()
        )
        maintenance_open = (
            MaintenanceRecord.objects.open()
            .filter(base_object_id__in=base_ids)
            .count()
        )
        today = timezone.now().date()
        compliance_overdue = (
            ComplianceRecord.objects.filter(base_object_id__in=base_ids)
            .filter(expires_on__lt=today)
            .count()
        )
        compliance_due_soon = (
            ComplianceRecord.objects.upcoming(30)
            .filter(base_object_id__in=base_ids)
            .count()
        )
        active_deployments = (
            DeploymentEntry.objects.filter(
                base_object_id__in=base_ids, ended_at__isnull=True
            ).count()
        )

        meta = [
            {
                "label": _("Maint. overdue"),
                "value": maintenance_overdue,
                "class": "alert" if maintenance_overdue else "",
            },
            {
                "label": _("Maint. open"),
                "value": maintenance_open,
                "class": "warning"
                if maintenance_open and not maintenance_overdue
                else "",
            },
            {
                "label": _("Compliance 30d"),
                "value": compliance_due_soon,
                "class": "warning" if compliance_due_soon else "",
            },
            {
                "label": _("Compliance overdue"),
                "value": compliance_overdue,
                "class": "alert" if compliance_overdue else "",
            },
            {
                "label": _("Deployed"),
                "value": active_deployments,
                "class": "info" if active_deployments else "",
            },
        ]

        if total_assets is not None:
            available = max(total_assets - active_deployments, 0)
            meta.append(
                {
                    "label": _("Available"),
                    "value": available,
                }
            )

        analytics = aggregate_metrics(queryset[:100])
        if analytics.get("asset_count"):
            mttr = round(analytics.get("mttr_hours", 0.0), 1)
            mtbf = round(analytics.get("mtbf_hours", 0.0), 1)
            meta.append(
                {
                    "label": _("Avg MTTR (h)"),
                    "value": mttr,
                    "class": "info" if mttr else "",
                }
            )
            meta.append(
                {
                    "label": _("Avg MTBF (h)"),
                    "value": mtbf,
                    "class": "info" if mtbf else "",
                }
            )

        significant_meta = [item for item in meta if item["value"]]
        if not significant_meta:
            significant_meta = meta[:3]
        return significant_meta[:3]
    trailer_metrics = get_cached_metrics(
        "dashboard:trailer_metrics", trailer_status_metrics, timeout=180
    )
    power_metrics = get_cached_metrics(
        "dashboard:power_metrics", power_utilization_metrics, timeout=180
    )
    for model_name in models:
        app, model = model_name.split(".")
        model = apps.get_model(app, model)
        meta = model._meta
        perm_name = "{}.view_{}".format(app, meta.model_name)
        if not user.has_perm(perm_name):
            continue
        total_count = model.objects.count()
        changelist_url = reverse(
            "admin:{}_{}_changelist".format(meta.app_label, meta.model_name)
        )
        queryset = model.objects.all()
        overview_meta = []
        if model_name == "data_center.DataCenterAsset":
            overview_meta = build_lifecycle_meta(queryset, total_assets=total_count)
        elif model_name == "back_office.BackOfficeAsset":
            overview_meta = build_lifecycle_meta(queryset, total_assets=total_count)
        elif model_name == "accounts.RalphUser":
            active_users = model.objects.filter(is_active=True).count()
            staff_users = model.objects.filter(is_staff=True).count()
            inactive_users = max(total_count - active_users, 0)
            overview_meta = [
                {
                    "label": _("Active"),
                    "value": active_users,
                    "class": "info" if active_users else "",
                },
                {
                    "label": _("Inactive"),
                    "value": inactive_users,
                    "class": "warning" if inactive_users else "",
                },
                {
                    "label": _("Staff"),
                    "value": staff_users,
                    "class": "info" if staff_users else "",
                },
            ]
        overview_tiles.append(
            build_tile(
                label=meta.verbose_name_plural,
                count=total_count,
                url=changelist_url,
                meta=(overview_meta or [])[:3],
                style_key=f"overview_{meta.model_name}",
            )
        )

    category_tiles = []
    trailer_changelist_url = None
    power_changelist_url = None

    asset_tiles = [
        ("back_office", "FieldGearAsset", _("Field Gear"), "field-gear"),
        ("heavy_equipment", "HeavyEquipmentAsset", _("Heavy Equipment"), "heavy-equipment"),
        ("trailers", "TrailerAsset", _("Trailers"), "trailers"),
        ("power", "PowerAsset", _("Power & Lighting"), "power-lighting"),
        ("fleet", "FleetAsset", _("Fleet Assets"), "fleet-assets"),
        ("drones", "DroneAsset", _("Drones"), "drones"),
        ("sensors", "SensorAsset", _("Sensors"), "sensors"),
    ]

    for app_label, model_name, label, css_class in asset_tiles:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        perm = f"{app_label}.view_{model._meta.model_name}"
        if not user.has_perm(perm):
            continue
        base_changelist = "admin:{}_{}_changelist".format(
            model._meta.app_label, model._meta.model_name
        )
        try:
            changelist_url = reverse(base_changelist)
        except NoReverseMatch:
            continue
        queryset = model.objects.all()
        if app_label == "back_office" and model_name == "FieldGearAsset":
            # proxy manager already scopes to field gear
            pass
        if model is HeavyEquipmentAsset:
            queryset = queryset.filter(equipment_type__in=HeavyEquipmentAsset.MACHINERY_TYPES)
        elif model is TrailerAsset:
            queryset = queryset.filter(equipment_type=HeavyEquipmentType.TRAILER)
            trailer_changelist_url = changelist_url
        elif model is PowerAsset:
            queryset = queryset.filter(
                equipment_type__in={
                    HeavyEquipmentType.GENERATOR,
                    HeavyEquipmentType.LIGHT_TOWER,
                    HeavyEquipmentType.PUMP,
                }
            )
            power_changelist_url = changelist_url
        total_assets = queryset.count()
        meta = build_lifecycle_meta(queryset, total_assets=total_assets)
        if model is TrailerAsset and trailer_metrics.get("total"):
            meta.extend(
                [
                    {
                        "label": _("Available"),
                        "value": trailer_metrics["available"],
                        "class": "info" if trailer_metrics["available"] else "",
                    },
                    {
                        "label": _("Occupied"),
                        "value": trailer_metrics["occupied"],
                        "class": "warning" if trailer_metrics["occupied"] else "",
                    },
                ]
            )
        if model is PowerAsset and power_metrics.get("total"):
            meta.extend(
                [
                    {
                        "label": _("Avg runtime (h)"),
                        "value": "{:.0f}".format(power_metrics["average_runtime_hours"]),
                        "class": "info" if power_metrics["average_runtime_hours"] else "",
                    },
                    {
                        "label": _("Avg fuel (%)"),
                        "value": "{:.0f}%".format(power_metrics["average_fuel_percent"]),
                        "class": "warning" if power_metrics["average_fuel_percent"] and power_metrics["average_fuel_percent"] < 40 else "",
                    },
                ]
            )
        meta = meta[:5]
        category_tiles.append(
            build_tile(
                label=label,
                count=total_assets,
                url=changelist_url,
                meta=meta,
                style_key=f"category_{css_class}",
            )
        )

    if user.has_perm("assets.view_project"):
        project_qs = Project.objects.all()
        project_total = project_qs.count()
        if project_total:
            active_projects = project_qs.filter(
                status=ProjectStatus.active.id
            ).count()
            planned_projects = project_qs.filter(
                status=ProjectStatus.planned.id
            ).count()
            managerless_projects = project_qs.filter(manager__isnull=True).count()
            ending_soon = project_qs.filter(
                end_date__isnull=False,
                end_date__gte=today,
                end_date__lte=today + timedelta(days=30),
                status__in=[ProjectStatus.active.id, ProjectStatus.paused.id],
            ).count()
            deployed_assets = (
                DeploymentEntry.objects.filter(
                    project__isnull=False, ended_at__isnull=True
                )
                .values("base_object_id")
                .distinct()
                .count()
            )
            budget_totals = summarize_project_budgets(project_qs.values_list("pk", flat=True))
            capex_remaining = budget_totals["capex_variance"]
            supplemental_tiles.append(
                build_tile(
                    label=_("Projects"),
                    count=project_total,
                    url=reverse("projects:list"),
                    meta=[
                        {
                            "label": _("Capex used"),
                            "value": format_currency(budget_totals["capex_actual"]),
                            "class": "info",
                        },
                        {
                            "label": _("Capex remaining"),
                            "value": format_currency(capex_remaining),
                            "class": "alert" if capex_remaining < 0 else "info",
                        },
                        {
                            "label": _("Active"),
                            "value": active_projects,
                            "class": "info" if active_projects else "",
                        },
                        {
                            "label": _("Opex used"),
                            "value": format_currency(budget_totals["opex_actual"]),
                            "class": "info",
                        },
                    ][:3],
                    style_key="projects_summary",
                )
            )

    if trailer_changelist_url and trailer_metrics.get("total"):
        supplemental_tiles.append(
            build_tile(
                label=_("Trailer Occupancy"),
                count="{:.0f}%".format(trailer_metrics["average_occupancy_percent"]),
                url=trailer_changelist_url,
                meta=[
                    {
                        "label": _("Occupied"),
                        "value": trailer_metrics["occupied"],
                        "class": "warning" if trailer_metrics["occupied"] else "",
                    },
                    {
                        "label": _("Available"),
                        "value": trailer_metrics["available"],
                        "class": "info" if trailer_metrics["available"] else "",
                    },
                    {
                        "label": _("Servicing"),
                        "value": trailer_metrics["servicing"],
                        "class": "alert" if trailer_metrics["servicing"] else "",
                    },
                ],
                style_key="supplemental_trailer",
            )
        )

    if power_changelist_url and power_metrics.get("types"):
        for item in power_metrics["types"]:
            supplemental_tiles.append(
                build_tile(
                    label=_("{} Utilization").format(item["label"]),
                    count=item["deployed"],
                    url="{}?power_asset_type={}".format(power_changelist_url, item["value"]),
                    css_class=f"tile-power-{slugify(item['value'])}",
                    meta=[
                        {
                            "label": _("In fleet"),
                            "value": item["count"],
                        },
                        {
                            "label": _("Avg runtime (h)"),
                            "value": "{:.0f}".format(item["average_runtime_hours"]),
                            "class": "info" if item["average_runtime_hours"] else "",
                        },
                        {
                            "label": _("Avg fuel (%)"),
                            "value": "{:.0f}%".format(item["average_fuel_percent"]),
                            "class": "warning" if item["average_fuel_percent"] and item["average_fuel_percent"] < 35 else "",
                        },
                    ],
                    style_key="supplemental_power",
                )
            )

    results.extend(category_tiles)
    results.extend(supplemental_tiles)
    results.extend(overview_tiles)

    results.append(get_user_equipment_tile_data(user=user))
    accept_tile_data = get_user_equipment_to_accept_tile_data(user=user)
    if accept_tile_data:
        results.append(accept_tile_data)
    accept_for_simcard_tile_data = get_user_simcard_to_accept_tile_data(user=user)  # noqa
    if accept_for_simcard_tile_data:
        results.append(accept_for_simcard_tile_data)
    accept_for_access_card_tile_data = get_user_access_card_to_accept_tile_data(
        user=user
    )  # noqa
    if accept_for_access_card_tile_data:
        results.append(accept_for_access_card_tile_data)
    accept_for_loan_tile_data = get_user_equipment_to_accept_loan_tile_data(user=user)  # noqa
    if accept_for_loan_tile_data:
        results.append(accept_for_loan_tile_data)
    accept_for_return_tile_data = get_user_equipment_to_accept_return_tile_data(
        user=user
    )  # noqa
    if accept_for_return_tile_data:
        results.append(accept_for_return_tile_data)
    accept_for_team_asset_tile_data = get_user_team_equipment_to_accept_tile_data(
        user=user
    )  # noqa
    if accept_for_team_asset_tile_data:
        results.append(accept_for_team_asset_tile_data)
    accept_for_test_asset_tile_data = get_user_test_equipment_to_accept_tile_data(
        user=user
    )  # noqa
    if accept_for_test_asset_tile_data:
        results.append(accept_for_test_asset_tile_data)

    return {"results": results}


@register.inclusion_tag("admin/templatetags/projects_widget.html", takes_context=True)
def projects_widget(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    if not user or not user.has_perm("assets.view_project"):
        return {}

    today = timezone.now().date()
    upcoming = today + timedelta(days=30)
    projects = Project.objects.all()
    total = projects.count()
    active = projects.filter(status=ProjectStatus.active.id).count()
    planned = projects.filter(status=ProjectStatus.planned.id).count()
    managerless = projects.filter(manager__isnull=True).count()
    ending_soon = projects.filter(
        end_date__isnull=False,
        end_date__gte=today,
        end_date__lte=upcoming,
        status__in=[ProjectStatus.active.id, ProjectStatus.paused.id],
    ).count()
    deployed_assets = (
        DeploymentEntry.objects.filter(project__isnull=False, ended_at__isnull=True)
        .values("base_object_id")
        .distinct()
        .count()
    )
    budget_totals = summarize_project_budgets(projects.values_list("pk", flat=True))
    capex_remaining_total = budget_totals["capex_variance"]

    top_projects_qs = (
        projects.annotate(
            active_assets=Count(
                "deployment_entries",
                filter=Q(deployment_entries__ended_at__isnull=True),
                distinct=True,
            )
        )
        .order_by("-active_assets", "-modified")[:5]
    )

    status_class_map = {
        ProjectStatus.planned.id: "warning",
        ProjectStatus.active.id: "info",
        ProjectStatus.paused.id: "warning",
        ProjectStatus.completed.id: "info",
        ProjectStatus.cancelled.id: "alert",
    }

    project_rows = []
    for project in top_projects_qs:
        manager_display = None
        if project.manager:
            manager_display = (
                project.manager.get_full_name() or project.manager.username
            )
        project_budget = summarize_project_budgets([project.pk])
        capex_remaining = project_budget["capex_variance"]
        project_rows.append(
            {
                "name": project.name,
                "code": project.code,
                "url": reverse("projects:detail", args=[project.pk]),
                "status": project.get_status_display(),
                "status_class": status_class_map.get(project.status, ""),
                "manager": manager_display,
                "active_assets": project.active_assets,
                "location": project.location_name,
                "end_date": project.end_date,
                "capex_used": format_currency(project_budget["capex_actual"]),
                "capex_budget": format_currency(project_budget["capex_budget"]),
                "capex_remaining": format_currency(capex_remaining),
                "capex_remaining_class": "alert" if capex_remaining < 0 else "info",
                "opex_used": format_currency(project_budget["opex_actual"]),
            }
        )

    stats = [
        {
            "label": _("Active"),
            "value": active,
            "class": "info" if active else "",
        },
        {
            "label": _("Planned"),
            "value": planned,
            "class": "info" if planned else "",
        },
        {
            "label": _("Ending 30d"),
            "value": ending_soon,
            "class": "warning" if ending_soon else "",
        },
        {
            "label": _("No manager"),
            "value": managerless,
            "class": "alert" if managerless else "",
        },
        {
            "label": _("Assets deployed"),
            "value": deployed_assets,
            "class": "info" if deployed_assets else "",
        },
        {
            "label": _("Capex used"),
            "value": format_currency(budget_totals["capex_actual"]),
            "class": "info",
        },
        {
            "label": _("Capex remaining"),
            "value": format_currency(capex_remaining_total),
            "class": "alert" if capex_remaining_total < 0 else "info",
        },
        {
            "label": _("Opex used"),
            "value": format_currency(budget_totals["opex_actual"]),
            "class": "info",
        },
    ]

    return {
        "total_projects": total,
        "projects_url": reverse("projects:list"),
        "stats": stats,
        "project_rows": project_rows,
    }


@register.inclusion_tag("admin/templatetags/my_services.html")
def my_services(user):
    return {
        "services": Service.objects.prefetch_related(
            Prefetch(
                "serviceenvironment_set",
                queryset=ServiceEnvironment.objects.prefetch_related(
                    Prefetch(
                        "baseobject_set",
                        queryset=BaseObject.objects.exclude(
                            content_type__model="vip"  # TODO remove after vip deletion
                        ).order_by("content_type_id"),
                    )
                ),
            ),
            "serviceenvironment_set__environment",
        ).filter(technical_owners=user, active=True),
        "user": user,
    }


@register.inclusion_tag("admin/templatetags/objects_summary.html")
def get_objects_summary(service_env, content_type_id, objects):
    from django.urls import reverse

    content_type = ContentType.objects.get_for_id(content_type_id)
    opts = content_type.model_class()._meta
    url = reverse("admin:{}_{}_changelist".format(opts.app_label, opts.model_name))
    return {
        "url": "{}?service_env={}".format(url, service_env.id),
        "name": opts.verbose_name,
        "count": len(objects),
    }
