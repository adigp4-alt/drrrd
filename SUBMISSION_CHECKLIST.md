# Final submission checklist

## Account and execution

- [ ] Register the team on the official lablab.ai event page.
- [ ] Use the dedicated competition Alpaca paper account with exactly $100,000 starting balance.
- [ ] Confirm options trading is enabled on that paper account.
- [ ] Generate paper API credentials; never paste them into GitHub or the browser.
- [ ] Set `ALPACA_PAPER_TRADE=true` and `ALPACA_AUTOTRADE_ENABLED=true` in the deployment environment.
- [ ] Select `AGENT_MODEL_PROVIDER=anthropic` or `openai` and set that provider's API key.
- [ ] Save the generated `AGENT_RUN_TOKEN`; enter it only when running the demo.
- [ ] Run one dry run, then one paper execution during US market hours.
- [ ] Verify the order appears in Alpaca and the Agent Desk audit record says `submitted`.

## Repository and deployment

- [ ] Merge the hackathon PR into a clean default branch (`main` recommended).
- [ ] Replace the old Iran Tracker README opening with the hackathon pitch and current setup.
- [ ] Confirm the public repo contains no `.env`, API keys, account IDs or generated audit logs.
- [ ] Confirm GitHub Actions installs dependencies and runs all unit tests.
- [ ] Deploy and verify `/agent`, `/foresight`, `/agent/api/runs` and the dry-run flow.
- [ ] Keep Render awake before judging or use a host without cold-start delay.

## Submission page

- [ ] Project name: **drrrd Agent Desk**.
- [ ] Tagline: **The autonomous options agent that knows when to say no.**
- [ ] Paste the one-page write-up from `HACKATHON_SUBMISSION.md`.
- [ ] Add the public GitHub repository URL.
- [ ] Add the live `/agent` URL.
- [ ] Upload a 90-second demo using `DEMO_SCRIPT.md`.
- [ ] Show Alpaca MCP usage, options logic, risk gates and a paper-account result on camera.
- [ ] Add screenshots: hero, approved/skipped proposal, risk-gate list, MCP trace, Alpaca order.
- [ ] State clearly that results are paper-only and not investment advice.
- [ ] Submit before the displayed September 4 deadline; do not rely on the final-hour countdown.

## Final QA

- [ ] Open every submitted link in a private/incognito window.
- [ ] Play the full uploaded video with sound.
- [ ] Check mobile layout and desktop layout.
- [ ] Confirm the demo still works with the chosen model provider.
- [ ] Save the final submission confirmation and URL.
