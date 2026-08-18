"""Tests for the installable-app (PWA) plumbing.

Installability is easy to break silently — a wrong MIME type or a service
worker served from the wrong path leaves the app looking fine in a desktop
browser while quietly refusing to install on a phone. These assert the
conditions browsers actually check.

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from app import create_app  # noqa: E402


class PwaRouteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Without start_background=False, building the app kicks off a live
        # 36-ticker download and a scheduler that outlives the test run.
        cls.client = create_app(start_background=False).test_client()

    def test_manifest_is_served_with_the_manifest_mime_type(self):
        r = self.client.get("/manifest.webmanifest")
        self.assertEqual(r.status_code, 200)
        self.assertIn("manifest+json", r.headers["Content-Type"])

    def test_manifest_meets_installability_requirements(self):
        m = json.loads(self.client.get("/manifest.webmanifest").data)
        self.assertTrue(m.get("name") and m.get("short_name"))
        self.assertEqual(m.get("display"), "standalone")
        self.assertTrue(m.get("start_url", "").startswith("/"))
        sizes = {i["sizes"] for i in m["icons"]}
        # Chrome requires both a 192px and a 512px icon to offer installation.
        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)
        self.assertTrue(any(i.get("purpose") == "maskable" for i in m["icons"]),
                        "a maskable icon is needed for a non-letterboxed Android icon")

    def test_every_manifest_icon_actually_resolves(self):
        m = json.loads(self.client.get("/manifest.webmanifest").data)
        for icon in m["icons"]:
            r = self.client.get(icon["src"])
            self.assertEqual(r.status_code, 200, f"missing icon: {icon['src']}")
            self.assertEqual(r.headers["Content-Type"], "image/png")

    def test_shortcut_targets_resolve(self):
        """A manifest shortcut pointing at a dead route is a broken app icon.

        The market fetch is stubbed out: this asserts the URLs route, and
        letting it reach the real providers would make the suite depend on
        outbound network access to Yahoo.
        """
        from app import forecast_engine

        m = json.loads(self.client.get("/manifest.webmanifest").data)
        with mock.patch.object(forecast_engine, "fetch_bars_with_reasons",
                               return_value=({}, ["stubbed in tests"])):
            for shortcut in m.get("shortcuts", []):
                r = self.client.get(shortcut["url"])
                self.assertEqual(r.status_code, 200,
                                 f"dead shortcut: {shortcut['url']}")

    def test_service_worker_is_served_from_the_root(self):
        """Scope is bounded by the serving path — /static/sw.js could not
        control navigations, so offline launch would silently not work."""
        r = self.client.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r.headers["Content-Type"])
        self.assertEqual(r.headers.get("Service-Worker-Allowed"), "/")

    def test_service_worker_is_not_long_cached(self):
        """A long-lived cached worker can outlive several deploys."""
        r = self.client.get("/sw.js")
        self.assertIn("max-age=0", r.headers.get("Cache-Control", ""))

    def test_service_worker_never_caches_diagnostics(self):
        """A cached 'healthy' verdict during an outage would mislead."""
        body = self.client.get("/sw.js").data.decode()
        self.assertIn("/foresight/api/diagnostics", body)
        self.assertIn("request.method !== \"GET\"", body)

    def test_apple_touch_icon_and_favicon(self):
        for path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png",
                     "/favicon.ico"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertEqual(r.headers["Content-Type"], "image/png")

    def test_page_links_the_manifest_and_ios_meta(self):
        html = self.client.get("/foresight").data.decode()
        self.assertIn('rel="manifest"', html)
        self.assertIn('href="/manifest.webmanifest"', html)
        self.assertIn('apple-mobile-web-app-capable', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn('name="theme-color"', html)

    def test_page_registers_the_worker_at_root_scope(self):
        html = self.client.get("/foresight").data.decode()
        self.assertIn('navigator.serviceWorker.register("/sw.js"', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
