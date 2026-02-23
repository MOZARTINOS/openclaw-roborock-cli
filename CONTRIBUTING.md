# Contributing

Thanks for contributing to `openclaw-roborock-cli`.

## Development setup

1. Fork and clone the repository.
2. Create a virtual environment.
3. Install dependencies:

```bash
pip install -e .[dev]
```

4. Run tests:

```bash
pytest
```

## Pull request checklist

- Keep changes focused and scoped.
- Add or update tests for behavior changes.
- Update docs (`README.md`, `docs/`) when behavior or commands change.
- Ensure CI is green.
- If changing OpenClaw integration behavior, update `docs/OPENCLAW_SKILL.md`.

## Commit guidelines

- Use clear, imperative commit messages.
- Mention user-facing changes first.

## Security

- Never commit `config.json`, tokens, or account credentials.
- If you discover a security issue, open a private report to the maintainer instead of a public issue.
