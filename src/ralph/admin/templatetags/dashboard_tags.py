# -*- coding: utf-8 -*-
from collections import Counter
from collections.abc import Iterable
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
    BaseObject,
    Service,
    ServiceEnvironment,
    MaintenanceRecord,
    ComplianceRecord,
    DeploymentEntry,
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


def get_cached_metrics(cache_key, builder, timeout=300):
    data = cache.get(cache_key)
    if data is None:
        data = builder()
        cache.set(cache_key, data, timeout)
    return data


def get_user_equipment_tile_data(user):
    return {
        "class": "my-equipment",
        "label": _("My equipment"),
        "count": BackOfficeAsset.objects.filter(Q(user=user) | Q(owner=user)).count(),
        "url": reverse("current_user_info"),
    }


def get_user_equipment_to_accept_tile_data(user):
    assets_to_accept_count = get_assets_to_accept(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "equipment-to-accept",
        "label": _("Hardware pick up"),
        "count": assets_to_accept_count,
        "url": get_acceptance_url(user),
    }


def get_user_simcard_to_accept_tile_data(user):
    simcard_to_accept_count = get_simcards_to_accept(user).count()
    if not simcard_to_accept_count:
        return None
    return {
        "class": "equipment-to-accept",
        "label": _("SIM Card pick up"),
        "count": simcard_to_accept_count,
        "url": get_simcard_acceptance_url(user),
    }


def get_user_access_card_to_accept_tile_data(user):
    access_card_to_accept_count = get_access_cards_to_accept(user).count()
    if not access_card_to_accept_count:
        return None
    return {
        "class": "equipment-to-accept",
        "label": _("Access Card pick up"),
        "count": access_card_to_accept_count,
        "url": get_access_card_acceptance_url(user),
    }


def get_user_equipment_to_accept_loan_tile_data(user):
    assets_to_accept_count = get_assets_to_accept_loan(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "equipment-to-accept-loan",
        "label": _("Hardware loan"),
        "count": assets_to_accept_count,
        "url": get_loan_acceptance_url(user),
    }


def get_user_equipment_to_accept_return_tile_data(user):
    assets_to_accept_count = get_assets_to_accept_return(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "equipment-to-accept-return",
        "label": _("Hardware return"),
        "count": assets_to_accept_count,
        "url": get_return_acceptance_url(user),
    }


def get_user_team_equipment_to_accept_tile_data(user):
    assets_to_accept_count = get_team_assets_to_accept(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "equipment-to-accept",
        "label": _("Team hardware pick up"),
        "count": assets_to_accept_count,
        "url": get_team_asset_acceptance_url(user),
    }


def get_user_test_equipment_to_accept_tile_data(user):
    assets_to_accept_count = get_test_assets_to_accept(user).count()
    if not assets_to_accept_count:
        return None
    return {
        "class": "equipment-to-accept",
        "label": _("Test hardware pick up"),
        "count": assets_to_accept_count,
        "url": get_test_asset_acceptance_url(user),
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
        if not user.has_perm("{}.view_{}".format(app, meta.model_name)):
            continue
        overview_tiles.append(
            {
                "label": meta.verbose_name_plural,
                "count": model.objects.count(),
                "class": slugify(meta.model_name),
                "icon": "icon",
                "url": reverse(
                    "admin:{}_{}_changelist".format(meta.app_label, meta.model_name)
                ),
            }
        )

    def build_tile(label, count, url, css_class=None, meta=None):
        if css_class is None:
            css_class = slugify(label)
        return {
            "label": label,
            "count": count,
            "class": css_class,
            "icon": "icon",
            "url": url,
            "meta": meta or [],
        }

    category_tiles = []
    trailer_changelist_url = None
    power_changelist_url = None

    def build_lifecycle_meta(queryset):
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
            DeploymentEntry.objects.filter(base_object_id__in=base_ids, ended_at__isnull=True)
            .count()
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
                "class": "warning" if maintenance_open and not maintenance_overdue else "",
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

        # show only metrics with non-zero value or the first three if all zero
        significant_meta = [item for item in meta if item["value"]]
        if not significant_meta:
            significant_meta = meta[:3]
        return significant_meta[:3]

    asset_tiles = [
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
        try:
            changelist_url = reverse(
                "admin:{}_{}_changelist".format(
                    model._meta.app_label, model._meta.model_name
                )
            )
        except NoReverseMatch:
            continue
        queryset = model.objects.all()
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
        meta = build_lifecycle_meta(queryset)
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
                count=queryset.count(),
                url=changelist_url,
                css_class=css_class,
                meta=meta,
            )
        )

    if trailer_changelist_url and trailer_metrics.get("total"):
        supplemental_tiles.append(
            build_tile(
                label=_("Trailer Occupancy"),
                count="{:.0f}%".format(trailer_metrics["average_occupancy_percent"]),
                url=trailer_changelist_url,
                css_class="trailer-occupancy",
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
            )
        )

    if power_changelist_url and power_metrics.get("types"):
        for item in power_metrics["types"]:
            supplemental_tiles.append(
                build_tile(
                    label=_("{} Utilization").format(item["label"]),
                    count=item["deployed"],
                    url="{}?power_asset_type={}".format(power_changelist_url, item["value"]),
                    css_class=f"power-{slugify(item['value'])}",
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
