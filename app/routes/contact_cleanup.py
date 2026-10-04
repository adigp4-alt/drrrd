"""Provider-neutral handoff only; no payment collection or order confirmation."""

import ipaddress
import re
from urllib.parse import urlsplit

from flask import Blueprint, current_app, redirect, render_template

bp = Blueprint("contact_cleanup", __name__, url_prefix="/contact-cleanup")

INQUIRY_URL = "mailto:adigp4%2Bcsvcleanup@gmail.com?subject=Contact%20CSV%20cleanup%20inquiry"
PORTFOLIO_URL = "https://practical-data-tools.pulsargeek.chatgpt.site"


def payment_destination():
    """Fail closed on missing/unsafe configuration, not proof a provider works.

    Only the operator can verify ownership, live mode, price and fulfillment.
    The separate enable switch records that deliberate activation decision.
    No user-supplied redirect target is accepted and no URL is fetched here.
    """
    if current_app.config.get("CONTACT_CLEANUP_CHECKOUT_ENABLED") is not True:
        return None
    value = current_app.config.get("CONTACT_CLEANUP_PAYMENT_URL", "")
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return None
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        if (url.scheme != "https" or url.username is not None
                or url.password is not None or url.port not in (None, 443)):
            return None
    except ValueError:
        return None

    # Public DNS names only. Reject common copy/paste placeholders and local
    # destinations; syntax validation still cannot establish a real checkout.
    labels = host.split(".")
    if len(host) > 253 or len(labels) < 2 or not re.search(r"[a-z]", labels[-1]) or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    ):
        return None
    if labels[-1] in {"localhost", "local", "test", "invalid", "example"}:
        return None
    if any(host == name or host.endswith("." + name)
           for name in ("example.com", "example.net", "example.org")):
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None
    return value


@bp.after_request
def prevent_stale_checkout(response):
    # A disabled destination must not survive in a browser/proxy cache.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def service_page(destination=None):
    return render_template(
        "contact_cleanup.html",
        checkout_available=bool(destination),
        inquiry_url=INQUIRY_URL,
        portfolio_url=PORTFOLIO_URL,
        current_offer_url=PORTFOLIO_URL + "/#payment",
    )


@bp.get("")
def offer():
    return service_page(payment_destination())


@bp.get("/checkout")
def checkout():
    # Recheck even if the visitor has an old tab with an enabled button.
    destination = payment_destination()
    if not destination:
        return service_page(), 503
    return redirect(destination, code=303)
