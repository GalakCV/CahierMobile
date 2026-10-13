"""
Usuário local sem senha.

A aplicação é de um único estudante e roda em 127.0.0.1. Para que o painel
administrativo do Django funcione sem criar e armazenar uma senha, este
middleware autentica automaticamente um usuário local ("estudante", com senha
inutilizável) — mas somente quando a requisição vem do próprio computador
(loopback) e ``LOCAL_SINGLE_USER`` está ativo.

Se a aplicação for publicada em um servidor, defina CAHIER_LOCAL_SINGLE_USER=false
e crie um superusuário com ``python manage.py createsuperuser``.
"""
from __future__ import annotations

import ipaddress

from django.conf import settings
from django.contrib.auth import get_user_model, login

LOCAL_USERNAME = "estudante"


def is_loopback(request) -> bool:
    addr = request.META.get("REMOTE_ADDR", "")
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def get_local_user():
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=LOCAL_USERNAME,
        defaults={"is_staff": True, "is_superuser": True, "first_name": "Estudante"})
    if created or user.has_usable_password():
        user.set_unusable_password()
        user.is_staff = user.is_superuser = True
        user.save()
    return user


class LocalUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (getattr(settings, "LOCAL_SINGLE_USER", False) and not request.user.is_authenticated
                and is_loopback(request)):
            user = get_local_user()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
