# Real Estate Data Pipeline & Normalization Engine

An automated backend pipeline for collecting, normalising, and synchronising real estate market data. This repository showcases production-ready integration patterns: cloud scheduling, external scraping APIs, deterministic data cleaning, and relational database storage.

## Key Architecture Features

- **Automated Workflows:** Scheduled jobs managed via GitHub Actions to orchestrate API synchronisation and run routine ETL twice daily.
- **External API Coordination:** Secure integration with Apify actors to scrape posts/comments defensively, with active polling and status verification.
- **Deterministic Price Validation (LLM guardrail):** A normalisation module (`reconstruct_sale_price.py`) that reconstructs prices directly from unstructured, multilingual text — parsing local per-unit rates (per-`are`, per-m²) and currencies — and cross-checks them against an upstream LLM's extraction. It corrects systematic 10×/100× decimal-shift errors, reverses currency-misparse patterns, and flags unreliable values. This is the deterministic layer that makes the AI-extracted data trustworthy.
- **Idempotent Database Operations:** Relational synchronisation with Supabase (PostgreSQL) using deterministic UUIDs (hash-derived) to guarantee upsert safety and zero record duplication.

## Technology Stack

- **Runtime:** Python 3.11
- **Database / Storage:** Supabase (PostgreSQL)
- **External Scraping Services:** Apify Client
- **CI/CD / Automation:** GitHub Actions
- **Core Libraries:** Python standard library for the engine (`re`, `math`, `hashlib`, `uuid`)

## File Structure

- `.github/workflows/pipeline.yml` — Scheduled automation that triggers the pipeline worker twice daily.
- `sync_comments.py` — Pipeline worker: orchestrates the scraping task and idempotent relational storage.
- `reconstruct_sale_price.py` — Deterministic price reconstruction & validation engine.
- `requirements.txt` — Runtime dependencies.

## Example — the price engine catching an LLM error

```python
from reconstruct_sale_price import reconstruct_price, tier_for, final_sale_price

raw = "Dijual tanah di Canggu, luas 5 are, harga 800 juta / are, SHM"
land_m2 = 500  # 5 are

recon, method = reconstruct_price(raw, land_size_m2=land_m2)
# -> (4_000_000_000, 'per_are')

llm_price = 250_000_000  # the LLM mistook the per-are rate for the total
tier = tier_for(llm_price, recon, method, land_m2=land_m2, listing_kind='land')
# -> 'use_recon'   (the reconstruction is trusted over the bad LLM value)

price = final_sale_price(llm_price, recon, tier)
# -> 4_000_000_000
```

## Disclaimer

This codebase contains generic, sanitised implementations extracted from a larger commercial pipeline. All target URLs, specific database schemas, and private API keys have been removed to protect intellectual property.
