# Legora

An AI workspace for legal document review. Upload contracts, run a grid of
questions across them, and click every answer through to its verified source
text.

See [CLAUDE.md](./CLAUDE.md) for architecture, conventions, and commands.

## Getting started

```bash
cp .env.example .env      # add OPENAI_API_KEY when you reach Phase 3
pnpm install
uv sync --directory apps/api
pnpm dev                  # or: make dev
```

- web — http://localhost:3000
- api — http://localhost:8000/docs
- MinIO console — http://localhost:9001 (legora / legora-secret)
