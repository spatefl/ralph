# -*- coding: utf-8 -*-
from ralph.accounts.api_simple import ExtendedSimpleRalphUserSerializer
from ralph.api import RalphAPISerializer, RalphAPIViewSet, router
from ralph.assets.api.serializers import AssetSerializer
from ralph.assets.api.views import base_object_descendant_prefetch_related
from ralph.heavy_equipment.admin import HeavyEquipmentAssetAdmin
from ralph.heavy_equipment.models import HeavyEquipmentAsset


class HeavyEquipmentAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = HeavyEquipmentAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class HeavyEquipmentAssetSerializer(AssetSerializer):
    owner = ExtendedSimpleRalphUserSerializer()
    user = ExtendedSimpleRalphUserSerializer()

    class Meta(AssetSerializer.Meta):
        model = HeavyEquipmentAsset
        depth = 2


class HeavyEquipmentAssetViewSet(RalphAPIViewSet):
    select_related = HeavyEquipmentAssetAdmin.list_select_related + (
        "service_env__service",
        "service_env__environment",
    )
    prefetch_related = base_object_descendant_prefetch_related + [
        "tags",
        "content_type",
    ]
    queryset = HeavyEquipmentAsset.objects.all()
    serializer_class = HeavyEquipmentAssetSerializer


router.register(r"heavy-equipment-assets", HeavyEquipmentAssetViewSet)
urlpatterns = []

