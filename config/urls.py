from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from rest_framework import permissions
from drf_yasg import openapi
from drf_yasg.views import get_schema_view

from apps.files.views import FileResolveView

schema_view = get_schema_view(
    openapi.Info(
        title="File Manager API",
        default_version="v1",
        description="ArnaTech File Manager Service",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    path("", TemplateView.as_view(template_name="landing.html"), name="landing"),
    path("admin/", admin.site.urls),
    path("api/schema.json", schema_view.without_ui(cache_timeout=0), name="schema-json"),
    path("swagger", schema_view.with_ui("swagger", cache_timeout=0), name="swagger-ui"),
    path("redoc", schema_view.with_ui("redoc", cache_timeout=0), name="redoc"),
    path("api/", include("apps.files.urls")),
    path("<uuid:file_id>", FileResolveView.as_view(), name="file-resolve"),
]
