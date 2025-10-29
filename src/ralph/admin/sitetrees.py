# -*- coding: utf-8 -*-
from django.apps import apps
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.translation import activate
from sitetree.sitetreeapp import register_i18n_trees
from sitetree.utils import item, tree

from ralph.admin.sites import ralph_site

# To generate and display the menu, use the command:
# ralph sitetreeload
# ralph sitetree_resync_apps

activate(settings.LANGUAGE_CODE)


def ralph_item(*args, **kwargs):
    kwargs.setdefault("access_loggedin", True)
    # create access_by_perms entries by iterating through all children
    # and extracting app and model name from it
    # permission is created in '<app>.{add|change|view}_<model>' format
    access_by_perms = kwargs.get("access_by_perms", [])
    if isinstance(access_by_perms, (str, int)):
        access_by_perms = [access_by_perms]
    for child in kwargs.get("children", []):
        if hasattr(child, "_model") and hasattr(child, "_app"):
            model = child._model.lower()
            app = child._app.lower()
            access_by_perms.extend(
                [
                    "{}.add_{}".format(app, model),
                    "{}.change_{}".format(app, model),
                    "{}.view_{}".format(app, model),
                ]
            )
        elif hasattr(child, "permissions"):
            access_by_perms.extend(child.permissions)
    if access_by_perms:
        kwargs["access_by_perms"] = list(set(access_by_perms))
    return item(*args, **kwargs)


extra_views = ralph_site.get_extra_view_menu_items()


def get_menu_items_for_admin(name, perm):
    # TODO: detailed permissions for extra views
    return [ralph_item(access_by_perms=perm, **view) for view in extra_views[name]]


def section(section_name, app, model):
    app, model = map(str.lower, [app, model])
    model_class = apps.get_model(app, model)
    permission_model = getattr(model_class._meta, "proxy_for_model", None) or model_class
    perm_model_name = permission_model._meta.model_name
    perm_app_label = permission_model._meta.app_label
    # support for proxy model beacause this bug
    # https://code.djangoproject.com/ticket/11154
    change_perm = "{}.change_{}".format(perm_app_label, perm_model_name)
    item = ralph_item(
        title=section_name,
        url="admin:{}_{}_changelist".format(app, model),
        access_by_perms="{}.view_{}".format(perm_app_label, perm_model_name),
        perms_mode_all=False,
        children=[
            ralph_item(
                title=_("Add {}".format(model_class._meta.verbose_name.lower())),
                url="admin:{}_{}_add".format(app, model),
                access_by_perms="{}.add_{}".format(perm_app_label, perm_model_name),
            ),
            ralph_item(
                title="{{ original }}",
                url="admin:{}_{}_change original.id".format(app, model),
                access_by_perms=change_perm,
                children=get_menu_items_for_admin(
                    "{}_{}".format(app, model),
                    change_perm,
                ),
            ),
        ],
    )
    # save app and model info to create permissions entries later
    item._app = perm_app_label
    item._model = perm_model_name
    return item


sitetrees = [
    tree(
        "ralph_admin",
        items=[
            ralph_item(
                title=_("Heavy Equipment"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("All Heavy Equipment"), "heavy_equipment", "HeavyEquipmentAsset"),
                    section(_("Debris Removal"), "heavy_equipment", "HeavyEquipmentDebrisRemoval"),
                    section(_("Power Generation & Lighting"), "heavy_equipment", "HeavyEquipmentPowerGeneration"),
                    section(_("Water & Fluid Management"), "heavy_equipment", "HeavyEquipmentWaterManagement"),
                    section(_("Material Handling"), "heavy_equipment", "HeavyEquipmentMaterialHandling"),
                ],
            ),
            ralph_item(
                title=_("Fleet"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("All Fleet Assets"), "fleet", "FleetAsset"),
                    section(_("Light Vehicles"), "fleet", "FleetLightVehicle"),
                    section(_("Trucks & Haulers"), "fleet", "FleetTruckHauler"),
                    section(_("Utility Vehicles"), "fleet", "FleetUtilityVehicle"),
                    section(_("Emergency Response"), "fleet", "FleetEmergencyVehicle"),
                    section(_("Passenger Transport"), "fleet", "FleetPassengerVehicle"),
                    section(_("Vehicles"), "fleet", "Vehicle"),
                    section(_("Vehicle Assignments"), "fleet", "VehicleAssignment"),
                    section(_("Vehicle Usage Logs"), "fleet", "VehicleUsageLog"),
                    section(_("Vehicle Maintenance Logs"), "fleet", "VehicleMaintenanceLog"),
                    section(_("Vehicle Status Logs"), "fleet", "VehicleStatusLog"),
                ],
            ),
            ralph_item(
                title=_("Drones"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("All Drone Assets"), "drones", "DroneAsset"),
                    section(_("Survey & Mapping"), "drones", "SurveyDroneAsset"),
                    section(_("Surveillance & Security"), "drones", "SurveillanceDroneAsset"),
                    section(_("Delivery"), "drones", "DeliveryDroneAsset"),
                    section(_("Inspection & Maintenance"), "drones", "InspectionDroneAsset"),
                    section(_("Training & Testing"), "drones", "TrainingDroneAsset"),
                    section(_("Drones"), "drones", "Drone"),
                    section(_("Drone Assignments"), "drones", "DroneAssignment"),
                    section(_("Drone Flight Logs"), "drones", "DroneFlightLog"),
                    section(_("Drone Maintenance Logs"), "drones", "DroneMaintenanceLog"),
                    section(_("Drone Status Logs"), "drones", "DroneStatusLog"),
                ],
            ),
            ralph_item(
                title=_("Sensors"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("All Sensor Assets"), "sensors", "SensorAsset"),
                    section(_("Environmental Sensors"), "sensors", "EnvironmentalSensorAsset"),
                    section(_("Security Sensors"), "sensors", "SecuritySensorAsset"),
                    section(_("Infrastructure Sensors"), "sensors", "InfrastructureSensorAsset"),
                    section(_("Logistics & Tracking Sensors"), "sensors", "LogisticsSensorAsset"),
                    section(_("Wearable Support Sensors"), "sensors", "WearableSensorAsset"),
                    section(_("Sensors"), "sensors", "Sensor"),
                    section(_("Sensor Assignments"), "sensors", "SensorAssignment"),
                    section(_("Sensor Uptime Logs"), "sensors", "SensorUptimeLog"),
                    section(_("Sensor Maintenance Logs"), "sensors", "SensorMaintenanceLog"),
                    section(_("Sensor Status Logs"), "sensors", "SensorStatusLog"),
                ],
            ),
            ralph_item(
                title=_("Data Center"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("All hosts"), "data_center", "DCHost"),
                    ralph_item(
                        title=_("DC Visualization"),
                        url="dc_view",
                        access_by_perms="accounts.can_view_extra_serverroomview",
                    ),
                    section(_("Hardware"), "data_center", "DataCenterAsset"),
                    section(_("Virtual Servers"), "virtual", "VirtualServer"),
                    section(_("Clusters"), "data_center", "cluster"),
                    section(_("Data Centers"), "data_center", "DataCenter"),
                    section(_("Racks"), "data_center", "Rack"),
                    section(_("Rack accessories"), "data_center", "RackAccessory"),
                    section(_("accessories"), "data_center", "Accessory"),
                    section(_("Databases"), "data_center", "Database"),
                    section(_("Disk Shares"), "data_center", "DiskShare"),
                    section(_("Server Rooms"), "data_center", "ServerRoom"),
                    section(_("Preboots"), "deployment", "Preboot"),
                    section(
                        _("Preboot configuration"), "deployment", "PrebootConfiguration"
                    ),
                    section(_("Preboot files"), "deployment", "PrebootFile"),
                ],
            ),
            ralph_item(
                title=_("Back Office"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("Access Cards"), "access_cards", "AccessCard"),
                    section(_("Hardware"), "back_office", "backofficeasset"),
                    section(_("SIM Cards"), "sim_cards", "SIMCard"),
                    section(_("Accessory"), "accessories", "Accessory"),
                ],
            ),
            ralph_item(
                title=_("Supports"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("Supports"), "supports", "Support"),
                    section(_("Types"), "supports", "SupportType"),
                    section(_("Assets supports"), "supports", "BaseObjectsSupport"),
                ],
            ),
            ralph_item(
                title=_("Reports"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    ralph_item(
                        title=_("Category model"),
                        url="category_model_report",
                        access_by_perms=("accounts.can_view_extra_categorymodelreport"),
                    ),
                    ralph_item(
                        title=_("Category model status"),
                        url="category_model__status_report",
                        access_by_perms=(
                            "accounts.can_view_extra_categorymodelstatusreport"
                        ),
                    ),
                    ralph_item(
                        title=_("Manufacturer category model"),
                        url="manufactured_category_model_report",
                        access_by_perms=(
                            "accounts.can_view_extra_manufacturercategorymodelreport"
                        ),
                    ),
                    ralph_item(
                        title=_("Status model"),
                        url="status_model_report",
                        access_by_perms=("accounts.can_view_extra_statusmodelreport"),
                    ),
                    ralph_item(
                        title=_("Asset - relations"),
                        url="asset-relations",
                        access_by_perms=(
                            "accounts.can_view_extra_assetrelationsreport"
                        ),
                    ),
                    ralph_item(
                        title=_("Licence - relations"),
                        url="licence-relations",
                        access_by_perms=(
                            "accounts.can_view_extra_licencerelationsreport"
                        ),
                    ),
                    ralph_item(
                        title=_("Assets - supports"),
                        url="assets-supports",
                        access_by_perms=("accounts.can_view_extra_assetsupportsreport"),
                    ),
                    ralph_item(
                        title=_("Failures"),
                        url="failures-report",
                        access_by_perms=("accounts.can_view_extra_failurereport"),
                    ),
                ],
            ),
            ralph_item(
                title=_("Operations"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("Changes"), "operations", "Change"),
                    section(_("Problems"), "operations", "Problem"),
                    section(_("Incidents"), "operations", "Incident"),
                    section(_("Failures"), "operations", "Failure"),
                    section(_("All"), "operations", "Operation"),
                    section(_("Types"), "operations", "OperationType"),
                    section(_("Statuses"), "operations", "OperationStatus"),
                ],
            ),
            ralph_item(
                title=_("Dashboards"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("Dashboards"), "dashboards", "Dashboard"),
                    section(_("Graphs"), "dashboards", "Graph"),
                ],
            ),
            ralph_item(
                title=_("Settings"),
                url="#",
                url_as_pattern=False,
                perms_mode_all=False,
                children=[
                    section(_("Asset model"), "assets", "AssetModel"),
                    section(_("Asset category"), "assets", "Category"),
                    section(_("Manufacturer"), "assets", "Manufacturer"),
                    section(_("Manufacturer Kind"), "assets", "Manufacturerkind"),
                    section(_("Business segment"), "assets", "BusinessSegment"),
                    section(_("Profit center"), "assets", "ProfitCenter"),
                    section(_("Service"), "assets", "Service"),
                    section(_("Environment"), "assets", "Environment"),
                    section(_("Budget info"), "assets", "BudgetInfo"),
                    section(_("Service Environment"), "assets", "ServiceEnvironment"),
                    section(
                        _("Configuration modules"), "assets", "ConfigurationModule"
                    ),
                    section(_("Configuration classes"), "assets", "ConfigurationClass"),
                    section(_("Asset holder"), "assets", "AssetHolder"),
                    section(_("Users list"), "accounts", "RalphUser"),
                    section(_("Groups list"), "auth", "Group"),
                    section(_("Regions"), "accounts", "Region"),
                    section(
                        _("Visibility scopes"),
                        "visibility_scope",
                        "ServiceBasedVisibilityScope",
                    ),
                    section(_("Access Zones"), "access_cards", "AccessZone"),
                    section(_("Transitions"), "transitions", "TransitionModel"),
                    section(_("Report template"), "reports", "Report"),
                    section(_("Custom fields"), "custom_fields", "CustomField"),
                    section(_("Warehouses"), "back_office", "warehouse"),
                    section(
                        _("Office Infrastructures"),
                        "back_office",
                        "officeinfrastructure",
                    ),
                ],
            ),
        ],
    )
]

register_i18n_trees(["ralph_admin"])
