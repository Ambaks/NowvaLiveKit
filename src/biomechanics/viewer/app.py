"""Launch the squat visualiser in a native PyWebView window.

The Three.js renderer runs in the webview; all optimisation (what-if,
warping) runs in Python and is exposed via ``pywebview.api``.
"""

from __future__ import annotations

import tempfile
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ..skeleton.definition import SkeletonModel


def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve_html(html: str, port: int, ready: threading.Event) -> None:
    tmpdir = tempfile.mkdtemp()
    index = Path(tmpdir) / "index.html"
    index.write_text(html, encoding="utf-8")

    handler = partial(SimpleHTTPRequestHandler, directory=tmpdir)
    httpd = HTTPServer(("127.0.0.1", port), handler)
    ready.set()
    httpd.serve_forever()


def launch_viewer(
    html: str,
    skeleton: "SkeletonModel",
    q_trajectory_per_rep: list[np.ndarray],
    rep_boundaries: list | None = None,
    title: str = "Squat Replay – Kinodynamics",
    width: int = 1400,
    height: int = 900,
) -> None:
    """Open *html* (from ``build_html()``) in a native window with a
    Python-backed kinodynamics solver.

    Serves the HTML from a local HTTP server so that ES module imports
    (Three.js from CDN) work correctly — ``html=`` loads at
    ``about:blank`` which blocks them.
    """
    import webview

    from .api import KinodynamicsAPI

    api = KinodynamicsAPI(skeleton, q_trajectory_per_rep, rep_boundaries)

    port = _find_free_port()
    ready = threading.Event()
    server_thread = threading.Thread(
        target=_serve_html, args=(html, port, ready), daemon=True
    )
    server_thread.start()
    ready.wait()

    window = webview.create_window(
        title,
        url=f"http://127.0.0.1:{port}/index.html",
        js_api=api,
        width=width,
        height=height,
        min_size=(800, 600),
    )

    webview.start(debug=True)


def launch_diagnosis_viewer(
    diagnosis_artifact_path: str,
    skeleton: "SkeletonModel | None" = None,
    title: str = "Diagnosis Comparison",
    width: int = 1600,
    height: int = 900,
) -> None:
    """Open the diagnosis comparison viewer in a native PyWebView window.

    Parameters
    ----------
    diagnosis_artifact_path : path to ``diagnosis_output_<set_id>.json``
    skeleton : optional pre-built skeleton (if *None*, reconstructed from
        the artifact's ``metadata.height_m`` / ``metadata.weight_kg``)
    """
    import webview

    from .api import DiagnosisViewerAPI
    from .diagnosis_html import build_diagnosis_html

    api = DiagnosisViewerAPI(diagnosis_artifact_path, skeleton=skeleton)
    html = build_diagnosis_html()

    port = _find_free_port()
    ready = threading.Event()
    server_thread = threading.Thread(
        target=_serve_html, args=(html, port, ready), daemon=True
    )
    server_thread.start()
    ready.wait()

    window = webview.create_window(
        title,
        url=f"http://127.0.0.1:{port}/index.html",
        js_api=api,
        width=width,
        height=height,
        min_size=(800, 600),
    )

    webview.start(debug=True)
