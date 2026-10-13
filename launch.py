"""
Inicia o Cahier e abre o navegador em http://localhost:8000.

Uso:
    python launch.py               # inicia e abre o navegador
    python launch.py --no-browser  # só inicia o servidor
    python launch.py --port 8001   # outra porta

O servidor escuta somente em 127.0.0.1 (CAHIER_HOST no .env muda isso de forma explícita).
Para encerrar, feche a janela do terminal ou pressione Ctrl+C.
"""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def open_when_ready(url: str, host: str, port: int) -> None:
    for _ in range(120):
        if port_open(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.25)
    print(f"O servidor demorou para responder. Abra manualmente: {url}")


def main() -> None:
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    parser = argparse.ArgumentParser(description="Inicia o Cahier.")
    parser.add_argument("--no-browser", action="store_true", help="não abrir o navegador")
    parser.add_argument("--port", type=int, default=settings.CAHIER_PORT)
    args = parser.parse_args()

    host = settings.CAHIER_HOST
    port = args.port
    url = f"http://localhost:{port}/"
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "127.0.0.1", "localhost") else host

    if port_open(probe_host, port):
        print(f"Já existe algo rodando na porta {port}. Abrindo {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return

    call_command("migrate", interactive=False, verbosity=0)
    print("=" * 60)
    print(f"  Cahier rodando em {url}")
    print("  Para encerrar: feche esta janela ou pressione Ctrl+C.")
    print("=" * 60)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url, probe_host, port), daemon=True).start()
    call_command("runserver", f"{host}:{port}", use_reloader=False, use_threading=True)


if __name__ == "__main__":
    main()
