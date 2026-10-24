from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("accounts.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]
