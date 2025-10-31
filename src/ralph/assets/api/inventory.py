# -*- coding: utf-8 -*-
from django.db.models import F, Q
from rest_framework.decorators import action
from rest_framework.response import Response

from ralph.api import RalphAPIViewSet, router
from ralph.assets.api.serializers import (
    MaintenancePartUsageSerializer,
    SparePartSerializer,
    SparePartStockSerializer,
)
from ralph.assets.models import MaintenancePartUsage, SparePart, SparePartStock


class SparePartViewSet(RalphAPIViewSet):
    queryset = SparePart.objects.prefetch_related("stocks").order_by("name")
    serializer_class = SparePartSerializer
    search_fields = ("name", "sku", "vendor_name", "vendor_sku", "external_reference")
    filterset_fields = ("category", "is_active")

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request, *args, **kwargs):
        stocks = SparePartStock.objects.filter(is_active=True, part__is_active=True)
        stocks = stocks.filter(
            Q(reorder_point__isnull=False, quantity_on_hand__lte=F("reorder_point"))
            | Q(
                reorder_point__isnull=True,
                quantity_on_hand__lte=F("part__restock_threshold"),
            )
        ).select_related("part")
        serializer = SparePartStockSerializer(stocks, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request, *args, **kwargs):
        """Lightweight procurement feed for downstream systems."""
        parts = self.filter_queryset(self.get_queryset())
        data = [
            {
                "id": part.pk,
                "name": part.name,
                "sku": part.sku,
                "vendor": part.vendor_name,
                "vendor_sku": part.vendor_sku,
                "unit_cost": float(part.unit_cost) if part.unit_cost is not None else None,
                "restock_threshold": part.restock_threshold,
                "restock_quantity": part.restock_quantity,
                "external_reference": part.external_reference,
                "total_quantity": part.total_quantity_on_hand(),
            }
            for part in parts
        ]
        return Response(data)


class SparePartStockViewSet(RalphAPIViewSet):
    queryset = SparePartStock.objects.select_related("part").order_by("part__name", "location")
    serializer_class = SparePartStockSerializer
    filterset_fields = ("part", "location", "is_active")
    search_fields = ("part__name", "part__sku", "location")


class MaintenancePartUsageViewSet(RalphAPIViewSet):
    queryset = MaintenancePartUsage.objects.select_related("maintenance_record", "part", "stock")
    serializer_class = MaintenancePartUsageSerializer
    filterset_fields = ("part", "stock", "maintenance_record__base_object")
    search_fields = (
        "maintenance_record__base_object__hostname",
        "maintenance_record__base_object__barcode",
        "part__name",
        "part__sku",
    )


router.register(r"inventory/parts", SparePartViewSet)
router.register(r"inventory/stocks", SparePartStockViewSet)
router.register(r"inventory/usage", MaintenancePartUsageViewSet)


urlpatterns = []
