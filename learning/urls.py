from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sessao/nova/", views.session_new, name="session_new"),
    path("sessao/<int:pk>/", views.session_play, name="session_play"),
    path("sessao/<int:pk>/questao/<int:pos>/", views.session_feedback, name="session_feedback"),
    path("sessao/<int:pk>/interromper/", views.session_pause, name="session_pause"),
    path("sessao/<int:pk>/encerrar/", views.session_finish, name="session_finish"),
    path("sessao/<int:pk>/resultado/", views.session_result, name="session_result"),
    path("sessao/<int:pk>/refazer-erradas/", views.session_retry, name="session_retry"),
    path("sessoes/", views.session_history, name="session_history"),
    path("iniciar/capitulo/<slug:code>/revisao/", views.start_chapter_review, name="start_chapter_review"),
    path("iniciar/capitulo/<slug:code>/avaliacao/", views.start_chapter_assessment, name="start_chapter_assessment"),
    path("iniciar/texto/<str:code>/", views.start_passage, name="start_passage"),
    path("iniciar/revisoes/", views.start_spaced_review, name="start_spaced_review"),
    path("revisoes/", views.review_queue, name="review_queue"),
    path("caderno-de-erros/", views.notebook, name="notebook"),
    path("producao-escrita/", views.written_list, name="written_list"),
    path("producao-escrita/<int:pk>/", views.written_assess, name="written_assess"),
    path("questao/<str:code>/marcar/", views.mark_for_review, name="mark_for_review"),
    path("questao/<str:code>/sinalizar/", views.flag_issue, name="flag_issue"),
    path("progresso/", views.progress, name="progress"),
    path("historico/", views.attempt_history, name="attempt_history"),
    path("preferencias/", views.settings_view, name="settings"),
]
