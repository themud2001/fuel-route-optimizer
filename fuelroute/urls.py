from django.urls import path

from routes.views import health, route_plan

urlpatterns = [
    path("health/", health),
    path("api/v1/route/", route_plan),
]
