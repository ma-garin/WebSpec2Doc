from __future__ import annotations

import threading
import webbrowser

from web import create_app
from web.config import PORT

app = create_app()


def _open_browser() -> None:
    import time

    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)
