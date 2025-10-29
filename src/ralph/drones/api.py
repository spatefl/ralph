# -*- coding: utf-8 -*-
from ralph.accounts.api_simple import ExtendedSimpleRalphUserSerializer
from ralph.api import RalphAPISerializer, RalphAPIViewSet, router
from ralph.assets.api.serializers import AssetSerializer
from ralph.assets.api.views import base_object_descendant_prefetch_related
from ralph.drones.admin import DroneAssetAdmin
from ralph.drones.models import DroneAsset


class DroneAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = DroneAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class DroneAssetSerializer(AssetSerializer):
    owner = ExtendedSimpleRalphUserSerializer()
    user = ExtendedSimpleRalphUserSerializer()

    class Meta(AssetSerializer.Meta):
        model = DroneAsset
        depth = 2


class DroneAssetViewSet(RalphAPIViewSet):
    select_related = DroneAssetAdmin.list_select_related + (
        "service_env__service",
        "service_env__environment",
    )
    prefetch_related = base_object_descendant_prefetch_related + [
        "tags",
        "content_type",
    ]
    queryset = DroneAsset.objects.all()
    serializer_class = DroneAssetSerializer


router.register(r"drone-assets", DroneAssetViewSet)
urlpatterns = []

