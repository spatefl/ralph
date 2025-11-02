from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _

from ralph.admin.mixins import RalphTemplateView, initialize_search_form
from ralph.admin.sites import ralph_site
from ralph.assets.models import DeploymentEntry, Project, ProjectStatus
from ralph.assets.services.projects import assign_asset_to_project
from ralph.projects.forms import ProjectAssignmentForm


class ProjectListView(LoginRequiredMixin, RalphTemplateView):
    template_name = "projects/list.html"

    def get_queryset(self):
        queryset = (
            Project.objects.select_related("manager", "default_team")
            .annotate(
                active_assets_total=Count(
                    "deployment_entries__base_object",
                    filter=Q(deployment_entries__ended_at__isnull=True),
                    distinct=True,
                )
            )
            .order_by("name", "code")
        )
        status_value = self.request.GET.get("status")
        if status_value:
            try:
                queryset = queryset.filter(status=int(status_value))
            except (TypeError, ValueError):
                pass
        query = self.request.GET.get("q")
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(code__icontains=query)
                | Q(location_name__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(ralph_site.each_context(self.request))
        context.update(
            {
                "projects": self.get_queryset(),
                "project_statuses": ProjectStatus(),
                "selected_status": self.request.GET.get("status") or "",
                "query": self.request.GET.get("q", ""),
                "opts": Project._meta,
                "title": _("Projects overview"),
            }
        )
        initialize_search_form(Project, context)
        return context


class ProjectDetailView(LoginRequiredMixin, RalphTemplateView):
    template_name = "projects/detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project.objects.select_related("manager", "default_team").annotate(
                active_assets_total=Count(
                    "deployment_entries__base_object",
                    filter=Q(deployment_entries__ended_at__isnull=True),
                    distinct=True,
                )
            ),
            pk=kwargs["pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def _deployments(self):
        return (
            self.project.deployment_entries.filter(ended_at__isnull=True)
            .select_related("base_object", "assigned_to_user", "assigned_to_team")
            .order_by("-started_at", "-pk")
        )

    def _can_assign(self):
        user = self.request.user
        return user.has_perm("assets.change_project") or user.has_perm(
            "assets.change_deploymententry"
        )

    def _assignment_forms(self, deployments, bound_form=None):
        forms = {}
        target_entry = None
        if bound_form and bound_form.is_bound:
            try:
                target_entry = int(bound_form.data.get("entry"))
            except (TypeError, ValueError):
                target_entry = None
        for entry in deployments:
            if bound_form and target_entry == entry.id:
                forms[entry.id] = bound_form
            else:
                forms[entry.id] = ProjectAssignmentForm(
                    initial={
                        "entry": entry.id,
                        "assignee": entry.assigned_to_user_id,
                    }
                )
        return forms

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        deployments = self._deployments()
        bound_form = kwargs.get("assignment_form")
        forms_map = self._assignment_forms(deployments, bound_form=bound_form)
        context.update(ralph_site.each_context(self.request))
        context.update(
            {
                "project": self.project,
                "deployments": deployments,
                "deployment_rows": [
                    (deployment, forms_map[deployment.id]) for deployment in deployments
                ],
                "project_statuses": ProjectStatus(),
                "can_assign": self._can_assign(),
                "opts": Project._meta,
                "original": self.project,
                "title": self.project.name,
            }
        )
        initialize_search_form(Project, context)
        return context

    def post(self, request, *args, **kwargs):
        if not self._can_assign():
            messages.error(
                request,
                _("You do not have permission to update project assignments."),
            )
            return redirect(request.path)
        form = ProjectAssignmentForm(request.POST)
        if form.is_valid():
            entry = get_object_or_404(
                DeploymentEntry,
                pk=form.cleaned_data["entry"],
                project=self.project,
                ended_at__isnull=True,
            )
            assign_asset_to_project(
                project=self.project,
                asset=entry.base_object,
                assignee=form.cleaned_data["assignee"],
                handover_notes=form.cleaned_data["handover_notes"],
            )
            messages.success(
                request,
                _(
                    "Assignment for %(asset)s updated."
                )
                % {"asset": entry.base_object},
            )
            return redirect(request.path)
        return self.render_to_response(
            self.get_context_data(assignment_form=form)
        )
