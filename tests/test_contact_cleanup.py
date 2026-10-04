"""Checkout routing tests; never contact a provider or attempt a payment."""

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402

# Syntax-only fixture, not a working payment destination. Redirects are never
# followed. Deliberately not shipped as a configuration default or example.
PAYMENT_FIXTURE = "https://checkout.fixture-provider.com/contact-cleanup?item=49&currency=USD"


class ContactCleanupTests(unittest.TestCase):
    def setUp(self):
        with mock.patch.dict(os.environ, {
            "CONTACT_CLEANUP_PAYMENT_URL": "",
            "CONTACT_CLEANUP_CHECKOUT_ENABLED": "false",
        }), mock.patch("app.init_db"):
            self.app = create_app(start_background=False)
        self.app.testing = True
        self.client = self.app.test_client()

    def configure(self, url=PAYMENT_FIXTURE, enabled=True):
        self.app.config.update(
            CONTACT_CLEANUP_PAYMENT_URL=url,
            CONTACT_CLEANUP_CHECKOUT_ENABLED=enabled,
        )

    def assert_unavailable(self):
        page = self.client.get("/contact-cleanup")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("View current offer and PayPal instructions — $49 USD", html)
        self.assertIn('href="https://practical-data-tools.pulsargeek.chatgpt.site/#payment"', html)
        self.assertNotIn("Payment unavailable", html)
        self.assertNotIn('href="/contact-cleanup/checkout"', html)
        self.assertIn('href="mailto:adigp4%2Bcsvcleanup@gmail.com?subject=Contact%20CSV%20cleanup%20inquiry"', html)
        self.assertNotIn("github.com/adigp4-alt/drrrd/issues", html)
        response = self.client.get("/contact-cleanup/checkout")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("Location", response.headers)
        for result in (page, response):
            self.assertEqual(result.headers["Cache-Control"], "no-store")

    def test_missing_configuration_leaves_inquiries_open_and_payment_disabled(self):
        self.assert_unavailable()

    def test_url_alone_never_enables_checkout(self):
        self.configure(enabled=False)
        self.assert_unavailable()

    def test_unsafe_missing_and_placeholder_destinations_fail_closed(self):
        for url in (
            "", "  ", None, 49, "/pay", "//checkout.fixture-provider.com/pay",
            "http://checkout.fixture-provider.com/pay", "javascript:alert(1)",
            "https://localhost/pay", "https://127.0.0.1/pay", "https://[::1]/pay",
            "https://127.1/pay", "https://127.0.1/pay",
            "https://internal/pay", "https://pay.local/pay", "https://pay.test/pay",
            "https://example.com/pay", "https://pay.example.org/pay",
            "https://pay.invalid/pay", "https://pay..com/pay",
            "https://user:password@checkout.fixture-provider.com/pay",
            "https://checkout.fixture-provider.com:bad/pay",
            "https://checkout.fixture-provider.com:8443/pay",
            "https://checkout.fixture-provider.com/\nwrong",
            "https://checkout.fixture-provider.com\\@evil.com/pay", "https://[broken",
        ):
            with self.subTest(url=url):
                self.configure(url=url)
                self.assert_unavailable()

    def test_configured_handoff_uses_only_server_destination(self):
        self.configure()
        page = self.client.get("/contact-cleanup").get_data(as_text=True)
        self.assertIn('href="/contact-cleanup/checkout"', page)
        self.assertIn("Continue to payment — $49 USD", page)
        self.assertNotIn(PAYMENT_FIXTURE, page)
        response = self.client.get(
            "/contact-cleanup/checkout?url=https://evil.com&next=https://evil.com"
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], PAYMENT_FIXTURE)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_disabling_after_page_load_blocks_direct_checkout(self):
        self.configure()
        self.assertIn('href="/contact-cleanup/checkout"',
                      self.client.get("/contact-cleanup").get_data(as_text=True))
        self.configure(enabled=False)
        self.assert_unavailable()

    def test_query_parameters_cannot_enable_checkout_or_confirm_payment(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.configure(enabled=enabled)
                html = self.client.get(
                    "/contact-cleanup?paid=true&success=true&session_id=fake"
                    "&CONTACT_CLEANUP_CHECKOUT_ENABLED=true"
                ).get_data(as_text=True)
                self.assertIn("An email is an inquiry.", html)
                self.assertIn("does not confirm payment", html)
                self.assertIn("payment provider's confirmation", html)
                self.assertIn("Wait for scope confirmation before paying", html)
                if not enabled:
                    self.assertIn("View current offer and PayPal instructions — $49 USD", html)

    def test_no_local_payment_submission_or_success_endpoint(self):
        self.configure()
        self.assertEqual(self.client.post("/contact-cleanup/checkout").status_code, 405)
        self.assertEqual(self.client.get("/contact-cleanup/success").status_code, 404)

    def test_factory_loads_environment_and_requires_explicit_true(self):
        for switch in ("", "false", "0", "1", "yes", "true", " TRUE "):
            with self.subTest(switch=switch), mock.patch.dict(os.environ, {
                "CONTACT_CLEANUP_PAYMENT_URL": PAYMENT_FIXTURE,
                "CONTACT_CLEANUP_CHECKOUT_ENABLED": switch,
            }), mock.patch("app.init_db"):
                client = create_app(start_background=False).test_client()
                response = client.get("/contact-cleanup/checkout")
                expected = 303 if switch.strip().lower() == "true" else 503
                self.assertEqual(response.status_code, expected)


if __name__ == "__main__":
    unittest.main()
