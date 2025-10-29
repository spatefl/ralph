# -*- coding: utf-8 -*-
from ralph.accounts.api_simple import ExtendedSimpleRalphUserSerializer
from ralph.api import RalphAPISerializer, RalphAPIViewSet, router
from ralph.assets.api.serializers import AssetSerializer
from ralph.assets.api.views import base_object_descendant_prefetch_related
from ralph.sensors.admin import SensorAssetAdmin
from ralph.sensors.models import SensorAsset


class SensorAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = SensorAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class SensorAssetSerializer(AssetSerializer):
    owner = ExtendedSimpleRalphUserSerializer()
    user = ExtendedSimpleRalphUserSerializer()

    class Meta(AssetSerializer.Meta):
        model = SensorAsset
        depth = 2


class SensorAssetViewSet(RalphAPIViewSet):
    select_related = SensorAssetAdmin.list_select_related + (
        "service_env__service",
        "service_env__environment",
    )
    prefetch_related = base_object_descendant_prefetch_related + [
        "tags",
        "content_type",
    ]
    queryset = SensorAsset.objects.all()
    serializer_class = SensorAssetSerializer


router.register(r"sensor-assets", SensorAssetViewSet)
urlpatterns = []

