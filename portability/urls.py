from django.urls import path

from . import views

app_name = "dados"

urlpatterns = [
    path("dados/", views.data_home, name="home"),
    path("dados/exportar/<slug:kind>/", views.export_view, name="export"),
    path("dados/importar/", views.import_view, name="import"),
    path("dados/backup/criar/", views.backup_create, name="backup_create"),
    path("dados/backup/restaurar/", views.backup_restore, name="backup_restore"),
    path("dados/backup/<str:name>/baixar/", views.backup_download, name="backup_download"),
    path("editorial/", views.editorial, name="editorial"),
]
