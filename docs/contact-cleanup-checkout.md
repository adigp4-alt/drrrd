# Contact-cleanup payment handoff

Related offer: [issue #32](https://github.com/adigp4-alt/drrrd/issues/32).

## Public status

The proposed service is **$49 USD** for one compatible CSV, up to **2,000 records
and 15 columns**, with agreed rules, exact-duplicate handling, a review queue,
an audit, and one revision within scope. Target delivery is 24 hours after the
usable file, rules, and payment are confirmed.

**Checkout is disabled by default. No live payment destination or completed
payment has been verified for this change.** The test URL is a syntax-only
fixture; tests never follow it or transact.

- **Inquiry:** a public comment in issue #32 about scope. It creates no order
  and collects no payment. Ask for row count, headers, desired output, and phone
  country context; never request contact data or receipts in public comments.
- **Payment handoff:** after scope is agreed, the enabled button opens the
  operator's hosted payment page. This repository does not collect card details.
- **Paid order:** requires successful payment confirmation from the provider
  and seller confirmation of the agreed scope. A click, redirect, return URL,
  query string, screenshot, or comment is not payment verification. The seller
  checks the provider's record and matches the order privately before delivery.

## Repository-controlled entry point

The Flask app serves `/contact-cleanup`, linked from its navigation. It always
offers **Ask about fit — inquiry only**. When unavailable it shows a genuinely
disabled **Payment unavailable** button. When enabled it shows **Continue to
payment — $49 USD** and sends the visitor to `/contact-cleanup/checkout`.

The checkout route rechecks configuration and returns either a `303` redirect
to the configured destination or a `503` unavailable page with the inquiry link.
It does not accept a destination from request parameters. Both routes use
`Cache-Control: no-store`; the service worker excludes the entire checkout path
from offline caching. No success page, webhook, payment database, or provider
SDK is added. No deployed Flask origin is assumed or invented here.

## Configuration

Set these in the Flask host's environment, then restart/redeploy the app:

| Variable | Default | Meaning |
| --- | --- | --- |
| `CONTACT_CLEANUP_PAYMENT_URL` | empty | A real, public, provider-hosted HTTPS payment link for this offer. Never an API key, dashboard URL, or inquiry link. |
| `CONTACT_CLEANUP_CHECKOUT_ENABLED` | `false` | Set to `true` only after the operator verifies that exact destination. A URL alone does not enable checkout. |

The URL check rejects missing/malformed values, HTTP, embedded credentials,
nonstandard ports, IP/local addresses, and common example/test domains. It is
**syntax validation, not proof of a working checkout**. It does not fetch the
destination or determine ownership, live/test mode, availability, or price.

Before enabling, verify that the actual hosted checkout belongs to the seller,
describes this service, charges the agreed **$49 USD once**, and provides a usable
receipt/payment record and private customer contact. Confirm the provider's
successful-payment record and the seller's fulfillment process using the
provider's supported verification process; do not call checkout verified based
only on an HTTP 200 or a test redirect. Any real charge requires the payer's
authorization. No credentials or payment account need to be committed here.

Changing the destination requires verifying it again. To disable checkout, set
`CONTACT_CLEANUP_CHECKOUT_ENABLED=false` or clear the URL and restart/redeploy.
Existing tabs will hit the server gate again when their payment link is clicked.

For a local disabled-page preview without market-data jobs:

```bash
python -m flask --app 'app:create_app(start_background=False)' run
```

Open `http://127.0.0.1:5000/contact-cleanup`. The app reads environment variables
at startup; it does not load a `.env` file automatically.

## One remaining external integration

The public portfolio at
[practical-data-tools.pulsargeek.chatgpt.site](https://practical-data-tools.pulsargeek.chatgpt.site)
is a separately maintained Sites project; its source and deployment are not in
this GitHub repository. A repository commit cannot change its CTA.

**Activate the handoff on that portfolio:** once this repo change is merged and
deployed, the portfolio maintainer must point its payment CTA to the actual
deployed `/contact-cleanup` page, with the seller's real $49 hosted-payment URL
verified, configured, and enabled on the Flask host. Keep its inquiry CTA
labeled **Ask about fit — inquiry only**, and keep payment unavailable until
that destination exists. If the portfolio cannot use the Flask deployment,
port the same disabled-by-default gate to its own source instead.

Public status remains **inquiries open; checkout unavailable** until that
external activation has been verified. Do not label the site checkout live
merely because this PR is merged or local tests pass.
