from django.urls import path

from . import views

app_name = "content"

urlpatterns = [
    path("capitulos/", views.chapter_list, name="chapter_list"),
    path("capitulos/<slug:code>/", views.chapter_detail, name="chapter_detail"),
    path("textos/<str:code>/", views.passage_detail, name="passage_detail"),
    path("mapa-curricular/", views.curriculum_map, name="curriculum_map"),
    path("creditos/", views.credits, name="credits"),
    path("fontes/<slug:key>/", views.source_detail, name="source_detail"),
    path("editorial/questao/<str:code>/", views.exercise_preview, name="exercise_preview"),
]
