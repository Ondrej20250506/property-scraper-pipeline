# Real Estate Data Pipeline & Normalization Engine

An automated backend pipeline for collecting, normalising, and synchronising real estate market data. This repository showcases production-ready integration patterns using cloud scheduling, external scraping APIs, deterministic data cleaning, and relational database storage.

## Key Architecture Features

- **Automated Workflows:** Scheduled jobs managed via GitHub Actions to orchestrate API synchronisation and run routine ETL processes twice daily.
- **External API Coordination:** Secure integration with Apify actors to scrape posts/comments defensively with active polling and status verification.
- **Deterministic Price Reconstruction:** Custom mathematical normalisation module (`reconstruct_sale_price.py`) that parses unstructured text, extracts per-unit land and building metrics, applies exchange rate conversions, and fixes systematic pricing anomalies (such as 10x/100x human data entry shifts).
- **Idempotent Database Operations:** Relational synchronization with Supabase (PostgreSQL) utilising deterministic UUIDs calculated via hashing to guarantee upsert safety and zero record duplication.

## Technology Stack

- **Runtime:** Python 3.11
- **Database / Storage:** Supabase (PostgreSQL client integration)
- **External Scraping Services:** Apify Client
- **CI/CD / Automation:** GitHub Actions
- **Core Libraries:** Standard library regex parser (`re`), `hashlib`, `uuid`

## File Structure Overview

- `.github/workflows/pipeline.yml` — Deployment configuration managing automated runtime tasks and pipeline triggers.
- `sync_comments.py` — Pipeline worker orchestrating comment scraping tasks and relational database storage.
- `reconstruct_sale_price.py` — Algorithmic price reconstruction engine executing structured text analysis and sanitising irregular pricing formats.

## Disclaimer

This codebase contains generic, sanitized implementations of a larger commercial pipeline. All target URLs, specific database schemas, and private API keys have been removed to protect Intellectual Property.
