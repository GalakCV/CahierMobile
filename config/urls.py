"""Rotas principais do Cahier."""
from django.contrib import admin
from django.urls import include, path, re_path
from django.contrib.staticfiles.views import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("learning.urls")),
    path("", include("content.urls")),
    path("", include("portability.urls")),
    # Arquivos estáticos servidos pelo próprio Django: a aplicação é local e de um usuário só.
    re_path(r"^static/(?P<path>.*)$", serve, {"insecure": True}),
]
