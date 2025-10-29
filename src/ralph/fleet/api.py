# -*- coding: utf-8 -*-
from ralph.accounts.api_simple import ExtendedSimpleRalphUserSerializer
from ralph.api import RalphAPISerializer, RalphAPIViewSet, router
from ralph.assets.api.serializers import AssetSerializer
from ralph.assets.api.views import base_object_descendant_prefetch_related
from ralph.fleet.admin import FleetAssetAdmin
from ralph.fleet.models import FleetAsset


class FleetAssetSimpleSerializer(AssetSerializer):
    class Meta(AssetSerializer.Meta):
        model = FleetAsset
        exclude = AssetSerializer.Meta.exclude
        depth = 0


class FleetAssetSerializer(AssetSerializer):
    owner = ExtendedSimpleRalphUserSerializer()
    user = ExtendedSimpleRalphUserSerializer()

    class Meta(AssetSerializer.Meta):
        model = FleetAsset
        depth = 2


class FleetAssetViewSet(RalphAPIViewSet):
    select_related = FleetAssetAdmin.list_select_related + (
        "service_env__service",
        "service_env__environment",
    )
    prefetch_related = base_object_descendant_prefetch_related + [
        "tags",
        "content_type",
    ]
    queryset = FleetAsset.objects.all()
    serializer_class = FleetAssetSerializer


router.register(r"fleet-assets", FleetAssetViewSet)
urlpatterns = []

