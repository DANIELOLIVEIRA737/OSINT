"""Cross-platform launcher used by Iniciar Atlas.bat."""

import json
import os
import socket
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def main():
    if sys.version_info < (3, 12):
        raise RuntimeError(
            "O Atlas necessita de Python 3.12 ou superior: https://www.python.org/downloads/"
        )
    os.chdir(Path(__file__).resolve().parent)
    os.environ.setdefault(
        "ATLAS_DATA_DIR", str(Path(__file__).resolve().parent / "data")
    )
    port = int(os.environ.get("PORT", "8000"))
    state_path = Path(os.environ["ATLAS_DATA_DIR"]) / "server.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        saved_port = state.get("port")
        if type(saved_port) is int and 0 < saved_port < 65536:
            port = saved_port
    except (OSError, ValueError):
        pass
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            health = json.load(response)
        if health.get("app") == "atlas" and health.get("version") == 3:
            webbrowser.open(f"http://127.0.0.1:{port}")
            print(
                "O Atlas já está aberto. Feche esta janela; o servidor existente continua ativo."
            )
            return
    except (OSError, ValueError, urllib.error.URLError):
        pass
    # If another application owns the default port, choose an available local port.
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            port = 0
    import app

    def ready(actual_port):
        import threading

        threading.Timer(
            0.6, lambda: webbrowser.open(f"http://127.0.0.1:{actual_port}")
        ).start()
        print(
            "Mantenha esta janela aberta. Projetos guardados em: "
            + os.environ["ATLAS_DATA_DIR"]
        )

    app.serve("127.0.0.1", port, ready)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAtlas terminado. Os projetos continuam guardados.")
    except Exception as exc:
        print("Não foi possível iniciar o Atlas: " + str(exc))
        sys.exit(1)
