# CLAUDE.md

This file provides guidance for AI assistants (Claude and others) working in this repository.

## Repository Overview

This is a new, empty repository (`adigp4-alt/drrrd`). No source code has been committed yet. This CLAUDE.md serves as the baseline development guide to be updated as the project grows.

## Git Workflow

### Branch Naming
- Feature branches: `claude/<description>-<session-id>` (for AI-assisted work)
- Follow conventional branch naming for human-authored work

### Commit Messages
Write clear, imperative commit messages:
```
Add user authentication module
Fix null pointer in payment processor
Refactor database connection pooling
```

### Push Protocol
```bash
git push -u origin <branch-name>
```

Branch names for AI sessions must start with `claude/` and end with the matching session ID.

### Rebasing / Merging
Prefer rebasing feature branches on top of the main branch before opening a pull request.

## Development Conventions

### Code Style
- Follow the language-idiomatic style for whatever stack is adopted (to be documented here once the stack is chosen)
- Use a linter and formatter appropriate to the language (e.g., `ruff`/`black` for Python, `eslint`/`prettier` for JS/TS)
- Keep functions small and single-purpose

### Testing
- Write tests for all non-trivial logic
- Run the full test suite before pushing
- Prefer unit tests; add integration tests for critical paths

### Security
- Never commit secrets, API keys, or credentials
- Validate all user input at system boundaries
- Follow OWASP top-10 guidelines

## AI Assistant Guidelines

### What to do
- Read files before editing them
- Make minimal, focused changes — only what is explicitly requested
- Prefer editing existing files over creating new ones
- Mark tasks complete immediately after finishing them
- Commit and push changes when a task is complete

### What to avoid
- Do not add unrequested features, refactors, or "improvements"
- Do not add comments or docstrings to code you didn't change
- Do not introduce backwards-compatibility shims for removed code
- Do not guess URLs or make network requests without clear justification
- Do not use destructive git commands (`reset --hard`, `push --force`) without explicit user approval

### Confirming risky actions
Always ask before:
- Deleting files or branches
- Force-pushing
- Modifying CI/CD pipelines
- Sending messages or interacting with external services

## Repository Structure

*(To be filled in as files are added)*

```
drrrd/
└── CLAUDE.md        # This file
```

## Getting Started

Once the project stack is decided, add:
- Install / setup instructions
- How to run the development server
- How to run tests
- Environment variable requirements (`.env.example`)
