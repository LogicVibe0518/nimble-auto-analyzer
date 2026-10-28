# ADR 0001: Keep the app local, with a shared Python pipeline

Status: accepted for 1.0

## Context

The first version used Streamlit. Scraping, report schemas and PDF generation were already Python modules, but the interface needed more control over layout, progress and source inspection. The project is a small research tool used on one machine.

## Decision

Use React and Vite for the interface, FastAPI for HTTP endpoints, and a shared Python function for the analysis pipeline. Store jobs, reports and PDF bytes in SQLite. Use OpenRouter for model selection across providers.

| Module | Owns |
| --- | --- |
| `apps/web` | URL input, model selection, progress, findings and report history |
| `apps/api` | Request validation, queue admission, status polling and downloads |
| `core/schemas.py` | Typed inputs, scraped pages and reports |
| `core/settings.py`, `core/model_catalog.py` | Explicit configuration and public model options |
| `core/storage.py` | SQLite persistence and interrupted-job recovery |
| `utils/safe_scraper.py` | Bounded HTTP acquisition, robots checks and text extraction |
| `utils/model_provider.py` | Provider dispatch; the default adapter is OpenRouter |
| `utils/llm_client.py` | Versioned prompt, output validation and one repair attempt |
| `utils/report_verification.py` | Deterministic source and quotation checks |
| `utils/pdf_builder.py` | Report layout and PDF rendering |
| `utils/pipeline.py` | Coordination of the analysis stages |
| `benchmarks` | Frozen source capture and offline/live evaluation |

## Request lifecycle

`POST /api/analyses` validates three distinct URLs and the selected model before admitting a job. A process-local semaphore limits admission to four jobs; two worker threads execute them. The client polls `GET /api/analyses/{id}` until completion or failure.

The pipeline retrieves the pages concurrently. An unusable client page stops the analysis before inference. Missing competitor pages become explicit limitations. Model output is parsed, checked and rendered; the completed report and PDF are stored together. Restarting the backend preserves completed reports and marks interrupted jobs as failed.

`GET /api/config` exposes model options and readiness, never the key. Configuration comes from `.env.nimble`; legacy environment variables are not fallback credential sources.

## Tradeoffs

- Two local processes make UI development straightforward without adding a separate production deployment stack.
- SQLite handles local history without a database server. The queue is not distributed: run one backend process, not several Uvicorn workers.
- A thread pool is sufficient for this workload. Redis and a separate task service would add setup without a current requirement.
- Plain HTTP extraction is bounded and testable, but cannot read JavaScript-only content. There is no browser-rendering fallback.
- Model adapters separate provider-specific requests from prompt and report logic. OpenRouter routing can still change, so evaluation records the returned route metadata when available.

The original Streamlit UI and scraper remain as earlier implementations. The supported React/FastAPI path uses `utils/safe_scraper.py` and the shared pipeline.
