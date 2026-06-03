# AGENTS.md

## Project
Short description. Stack: e.g. Python 3.12 + uv + FastAPI + Postgres / R + targets.

## Layout
- `src/` – application code (Python packages)
- `R/` – R scripts / package code (R packages)
- `shell/` – shell scripts
- `sql/` – migrations, queries, stored procs
- `notebooks/` – exploratory analysis (not production)
- `infra/` – Terraform / CloudFormation templates
- `.github/workflows/` – CI/CD pipelines
- `tests/` – pytest tests or testthat for R
- `scripts/` – dev utilities, one-off jobs, example run scripts

## Commands
- Install:  `uv sync`
- Dev:      `uv run python -m <module>`
- Test:     `uv run pytest`
- Lint:     `uv run ruff check . && uv run ruff format --check .`
- Deploy:   `terraform plan` / `aws cloudformation deploy ...`

## Conventions
- Python: type hints on public APIs; Google-style docstrings on functions; ruff for lint+format; pure functions where possible.
- R: tidyverse style; roxygen2 docs on exported functions.
- SQL: uppercase keywords; CTEs over nested subqueries; migrations are append-only.
- IaC: Terraform preferred for new infra; tag all resources with `team`, `env`, `project`.
- CI: GitHub Actions for all automation; pin action versions to SHA.
- Secrets: never hardcode; use AWS Secrets Manager / GCP Secret Manager / GitHub secrets.

## Do
- Run `uv run pytest && uv run ruff check .` before declaring done.
- Write a test for any bug fix.
- Use `uv add` for Python deps (not pip install).
- Keep notebooks for exploration only — promote to `src/` for production.
- Display timestamps/logs in America/Denver for local-facing output (app logs, Dozzle, dev runs); use UTC for shared/production data and convert at the display boundary.
- Update this file when introducing a new convention.

## Don't
- Don't modify `*.tfstate` or remote state manually.
- Don't commit `.env*`, credentials, or data files.
- Don't bump deps unless asked.
- Don't refactor IaC and application code in the same PR.
- Don't use `SELECT *` in production queries.