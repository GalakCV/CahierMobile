"""
Configurações do Cahier — plataforma local de exercícios de francês.

Princípios:
- Execução local, um único usuário, sem telemetria e sem chamadas externas.
- Tudo que é pessoal fica em ``data/`` (banco SQLite e backups).
- Valores sensíveis ou específicos da máquina vêm do arquivo ``.env``
  (veja ``.env.example``). Nenhuma dependência extra é necessária para lê-lo.
"""
from pathlib import Path
import os
import secrets

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    """Lê um arquivo .env simples (CHAVE=valor) sem sobrescrever o ambiente."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "sim", "on"}


DATA_DIR = Path(os.environ.get("CAHIER_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _secret_key() -> str:
    """Usa CAHIER_SECRET_KEY do .env; caso não exista, gera e guarda uma chave local."""
    key = os.environ.get("CAHIER_SECRET_KEY", "").strip()
    if key:
        return key
    key_file = DATA_DIR / "secret_key.txt"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(50)
    key_file.write_text(key, encoding="utf-8")
    return key


SECRET_KEY = _secret_key()
DEBUG = env_bool("CAHIER_DEBUG", False)

# Por padrão a aplicação só responde a endereços locais.
# Para expor na rede é preciso alterar CAHIER_ALLOWED_HOSTS e CAHIER_HOST de forma explícita.
ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    "CAHIER_ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]").split(",") if h.strip()]
CAHIER_HOST = os.environ.get("CAHIER_HOST", "127.0.0.1")
CAHIER_PORT = int(os.environ.get("CAHIER_PORT", "8000"))

# Login automático do usuário local (sem senha) apenas para requisições de loopback.
# Desative se publicar a aplicação em um servidor.
LOCAL_SINGLE_USER = env_bool("CAHIER_LOCAL_SINGLE_USER", True)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "content",
    "learning",
    "portability",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "learning.middleware.LocalUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "learning.context_processors.study_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.environ.get("CAHIER_DB_PATH", DATA_DIR / "db.sqlite3")),
        "OPTIONS": {
            "timeout": 20,
            "init_command": "PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = []  # nenhuma senha é criada no modo local

LANGUAGE_CODE = "pt-br"
TIME_ZONE = os.environ.get("CAHIER_TIME_ZONE", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Endereço do app para celular (PWA publicado no GitHub Pages). Aparece em "Dados e backup".
CAHIER_MOBILE_URL = os.environ.get("CAHIER_MOBILE_URL", "https://galakcv.github.io/CahierMobile/")

# Limites de upload (importação JSON e restauração de backup).
MAX_IMPORT_BYTES = int(os.environ.get("CAHIER_MAX_IMPORT_MB", "5")) * 1024 * 1024
MAX_RESTORE_BYTES = int(os.environ.get("CAHIER_MAX_RESTORE_MB", "200")) * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Segurança de navegador (adequada para localhost; HTTPS fica para uma futura publicação).
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}

# Durante os testes automatizados, silencia os avisos esperados (404, 403, host inválido).
import sys  # noqa: E402
if len(sys.argv) > 1 and sys.argv[1] == "test":
    LOGGING["loggers"] = {"django.request": {"level": "CRITICAL"}, "django.security": {"level": "CRITICAL"}}
