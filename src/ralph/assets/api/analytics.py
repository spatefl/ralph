# -*- coding: utf-8 -*-
from datetime import datetime

from django.apps import apps
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from ralph.api import RalphAPIViewSet, router
from ralph.assets.models import Asset
from ralph.assets.services.analytics import aggregate_metrics, compute_asset_metrics


class AssetMetricsSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField()
    mttr_hours = serializers.FloatField()
    mtbf_hours = serializers.FloatField()
    time_in_state_hours = serializers.DictField(child=serializers.FloatField())
    transition_counts = serializers.DictField(child=serializers.IntegerField())
    open_incidents = serializers.IntegerField()


class AggregateMetricsSerializer(serializers.Serializer):
    asset_count = serializers.IntegerField()
    mttr_hours = serializers.FloatField()
    mtbf_hours = serializers.FloatField()
    time_in_state_hours = serializers.DictField(child=serializers.FloatField())
    transition_counts = serializers.DictField(child=serializers.IntegerField())


class AssetMetricsViewSet(RalphAPIViewSet):
    queryset = Asset.objects.all()
    serializer_class = AssetMetricsSerializer

    def retrieve(self, request, *args, **kwargs):
        asset = self.get_object()
        metrics = compute_asset_metrics(asset)
        serializer = self.get_serializer(metrics)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="aggregate")
    def aggregate(self, request, *args, **kwargs):
        model_label = request.query_params.get("model")
        if model_label:
            try:
                model = apps.get_model(model_label)
            except (LookupError, ValueError) as exc:
                return Response({"detail": f"Invalid model label: {model_label}"}, status=400)
        else:
            model = Asset

        queryset = model.objects.all()
        group_field = request.query_params.get("group_field")
        start_param = request.query_params.get("start")
        end_param = request.query_params.get("end")

        def parse_dt(value):
            if not value:
                return None
            dt = datetime.fromisoformat(value)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt

        start = parse_dt(start_param)
        end = parse_dt(end_param)

        if group_field and hasattr(model, group_field):
            response = {}
            distinct_values = queryset.values_list(group_field, flat=True).distinct()
            for value in distinct_values:
                if value is None:
                    continue
                assets = queryset.filter(**{group_field: value})
                metrics = aggregate_metrics(assets, start=start, end=end)
                response[str(value)] = AggregateMetricsSerializer(metrics).data
            return Response(response)

        metrics = aggregate_metrics(queryset, start=start, end=end)
        serializer = AggregateMetricsSerializer(metrics)
        return Response(serializer.data)


router.register(r"analytics/assets", AssetMetricsViewSet, basename="asset-metrics")


urlpatterns = []
