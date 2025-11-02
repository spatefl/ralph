from django.urls import reverse
from rest_framework import status

from ralph.api.tests._base import RalphAPITestCase
from ralph.assets.models import DeploymentEntry
from ralph.assets.services.projects import assign_asset_to_project
from ralph.assets.tests.factories import ProjectFactory
from ralph.back_office.tests.factories import BackOfficeAssetFactory


class ProjectAPITests(RalphAPITestCase):
    def test_assign_asset_defaults_to_manager(self):
        project = ProjectFactory(manager=self.user1)
        asset = BackOfficeAssetFactory()

        url = reverse("project-assign-assets", args=(project.pk,))
        payload = {"assignments": [{"asset": asset.pk}]}
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = DeploymentEntry.objects.get(project=project, base_object_id=asset.pk)
        self.assertEqual(entry.assigned_to_user, project.manager)
        self.assertEqual(entry.assigned_to_team, project.default_team)
        self.assertTrue(
            entry.assignments.filter(
                user=project.manager, ended_at__isnull=True
            ).exists()
        )

    def test_assign_asset_to_specific_user(self):
        project = ProjectFactory(manager=self.user1)
        asset = BackOfficeAssetFactory()

        url = reverse("project-assign-assets", args=(project.pk,))
        payload = {
            "assignments": [
                {
                    "asset": asset.pk,
                    "assignee": self.user2.pk,
                    "handover_notes": "Shift handover",
                }
            ]
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = DeploymentEntry.objects.get(project=project, base_object_id=asset.pk)
        self.assertEqual(entry.assigned_to_user, self.user2)
        assignment = entry.assignments.get(user=self.user2, ended_at__isnull=True)
        self.assertEqual(assignment.handover_notes, "Shift handover")

    def test_project_list_includes_active_asset_count(self):
        project = ProjectFactory(manager=self.user1)
        asset = BackOfficeAssetFactory()
        assign_asset_to_project(project=project, asset=asset)

        url = reverse("project-list")
        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)
        record = next(
            item for item in response.data["results"] if item["id"] == project.id
        )
        self.assertEqual(record["active_assets_count"], 1)
