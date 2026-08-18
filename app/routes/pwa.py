"""Progressive-web-app plumbing: service worker, manifest, icons.

A service worker's scope is bounded by the path it is *served from*, not by the
manifest's ``scope`` field — a worker delivered from ``/static/sw.js`` can only
control ``/static/``. Serving it from the root gives it scope over the whole
app, which is what makes offline launch and navigation caching work.
"""

from flask import Blueprint, current_app, send_from_directory

bp = Blueprint("pwa", __name__)


def _static(filename, mimetype=None, max_age=0):
    response = send_from_directory(
        current_app.static_folder, filename, mimetype=mimetype
    )
    # The worker and manifest must not be cached by the browser, or a deploy
    # can leave a stale worker in charge indefinitely.
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    return response


@bp.route("/sw.js")
def service_worker():
    response = _static("sw.js", mimetype="application/javascript")
    # Belt and braces: allows a root scope even if the file moves under /static.
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@bp.route("/manifest.webmanifest")
def manifest():
    return _static("manifest.webmanifest", mimetype="application/manifest+json")


@bp.route("/favicon.ico")
def favicon():
    return _static("icons/favicon-32.png", mimetype="image/png", max_age=86400)


@bp.route("/apple-touch-icon.png")
@bp.route("/apple-touch-icon-precomposed.png")
def apple_touch_icon():
    """iOS requests these by convention when adding to the home screen."""
    return _static("icons/icon-180.png", mimetype="image/png", max_age=86400)
