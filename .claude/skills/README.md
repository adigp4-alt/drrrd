# Project skills

Skills in this directory load automatically for anyone working on this repo with
Claude Code — the terminal CLI, the desktop app, or a web session. They are
committed deliberately: they encode how work gets done here, so the discipline
does not have to be re-explained every session.

A skill is a directory with a `SKILL.md` whose frontmatter carries a `name` and a
`description`. Only the description is loaded up front; the body is read when the
description matches the task at hand. Write new ones with the `writing-skills`
skill below.

## What's here

### Engineering discipline

| Skill | Use it when |
| --- | --- |
| `brainstorming` | Before any creative work — turns an idea into a design and a spec through dialogue, instead of guessing at requirements in code. |
| `writing-plans` | Turning an approved design into a written implementation plan another session can execute. |
| `executing-plans` | Executing a written plan with review checkpoints. |
| `test-driven-development` | Implementing any feature or bugfix. Write the test, watch it fail, then write the code. |
| `systematic-debugging` | Any bug, test failure, or unexpected behaviour. Root cause before fixes; symptom fixes are failure. |
| `verification-before-completion` | About to say something is done, fixed, or passing. Run the command, read the output, then claim. |
| `requesting-code-review` | Finishing a feature or preparing to merge — dispatches a reviewer with purpose-built context. |
| `receiving-code-review` | Feedback has arrived, especially if it seems wrong. Verify before implementing; no performative agreement. |
| `finishing-a-development-branch` | Implementation is complete and the work needs integrating. |
| `dispatching-parallel-agents` | Two or more genuinely independent investigations (different subsystems, different failures). |
| `writing-skills` | Adding to or editing this directory. |

### Testing this app

| Skill | Use it when |
| --- | --- |
| `webapp-testing` | Verifying the Flask dashboard in a real browser with Playwright — the foresight board, watchlist, alerts, PWA. Chromium is preinstalled in web sessions. |

### This codebase

| Skill | Use it when |
| --- | --- |
| `forecast-integrity` | Touching `app/forecast_*.py`, `app/market_data.py`, the `/foresight` routes, the backtest, or the accuracy ledger. The invariants that keep published probabilities honest, and the commands that prove they hold. |

`forecast-integrity` is the one written for this project. The rest are imported,
and they are worth more when paired with it: `test-driven-development` tells you
to write the failing test first, `forecast-integrity` tells you *which* property
that test has to pin down.

## Provenance and licensing

Imported skills are kept close to upstream so they can be refreshed. Both source
licenses permit redistribution and modification; the license texts are retained
here.

**[obra/superpowers](https://github.com/obra/superpowers)** — MIT, Copyright (c)
2025 Jesse Vincent. Full text in `LICENSE-superpowers-MIT.txt`.

Imported: `brainstorming`, `writing-plans`, `executing-plans`,
`test-driven-development`, `systematic-debugging`,
`verification-before-completion`, `requesting-code-review`,
`receiving-code-review`, `finishing-a-development-branch`,
`dispatching-parallel-agents`, `writing-skills`.

Changes made on import:

- `systematic-debugging` — removed `CREATION-LOG.md`, `test-academic.md` and
  `test-pressure-*.md`. Those are fixtures used to develop and pressure-test the
  skill upstream, not part of the skill.
- `brainstorming/SKILL.md` — the pointer to the visual companion guide now
  resolves from the repo root (`.claude/skills/brainstorming/visual-companion.md`).
- `writing-skills/SKILL.md` — the note on where skills live now describes this
  repo's layout, replacing two links to a skill that was not imported.

Not imported, deliberately: `using-superpowers` (a session-wide directive to
invoke a skill before every response, which conflicts with how this repo is
worked on), `subagent-driven-development` (heavyweight, and overlaps
`executing-plans` plus `dispatching-parallel-agents`), and `using-git-worktrees`
(the hosted sessions this repo is developed in already provide isolation).

**[anthropics/skills](https://github.com/anthropics/skills)** — Apache License
2.0. Full text in `webapp-testing/LICENSE.txt`.

Imported unmodified: `webapp-testing`.

Not imported: the document skills (`xlsx`, `docx`, `pptx`, `pdf`), the design
skills (`canvas-design`, `algorithmic-art`, `brand-guidelines`, `theme-factory`,
`web-artifacts-builder`), `skill-creator`, `mcp-builder`, `claude-api`,
`doc-coauthoring`, `internal-comms` and `slack-gif-creator`. These ship with
Claude Code already — committing a second copy here would shadow the maintained
one without adding anything.

## Refreshing an imported skill

```bash
git clone --depth 1 https://github.com/obra/superpowers /tmp/superpowers
diff -ru /tmp/superpowers/skills/systematic-debugging .claude/skills/systematic-debugging
```

Re-apply the changes listed above after pulling a new upstream copy.
