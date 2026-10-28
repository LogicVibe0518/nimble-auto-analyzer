# Evaluating Nimble

The runner is implemented. A live comparison across reviewed cases has not been published.

The question is narrow: given the same three extracted pages, which model returns useful findings with supported source quotations, and what does each report cost in time and tokens? This does not measure search rankings or an SEO campaign's outcome.

## Start with the offline check

```sh
.venv/bin/python -m benchmarks.evaluate --mode offline
```

This audits one synthetic report fixture without making a model call. A passing result means the fixture satisfies the schema and evidence checks. It is not a model accuracy score.

## Freeze the inputs

Capture a real case once so each model receives the same source text:

```sh
.venv/bin/python -m benchmarks.capture \
  --id ballarat-hotels \
  --client https://craigsroyal.com.au/ \
  --competitor-one https://theprovincialballarat.com.au/ \
  --competitor-two https://hotelballarat.com.au/
```

The file is saved under `.nimble/datasets/ballarat-hotels.json`, with a capture timestamp and content hash. Capture does not call an AI provider. Check that each page contains usable content before comparing models. Keep third-party source snapshots local unless you have permission to redistribute them.

The generated `ground_truth` starts with `reviewed: false` and no expected keywords. Only mark it reviewed after checking the sources and annotating real opportunities. Literal keyword matching is narrower than a human assessment of meaning or business relevance.

## Run a bounded comparison

Configure a dedicated OpenRouter key first. Choose exact model IDs from `.nimble/available-models.json`; current availability and prices depend on the account and route.

```sh
.venv/bin/python -m benchmarks.evaluate --mode live \
  --dataset .nimble/datasets/ballarat-hotels.json \
  --model EXACT_FIRST_MODEL_ID \
  --model EXACT_SECOND_MODEL_ID \
  --repeats 2 \
  --max-calls 8
```

Replace both model IDs before running. This example allows four report attempts and up to eight paid generation calls, including one repair per report. The runner reserves repair capacity before starting an attempt, stops on authentication or quota failures, and alternates model order across repeats. It uses the same generation and repair code as the app.

Catalog prices are reference data. Provider-reported cost is recorded when present; missing cost stays unknown. A call limit is not a dollar limit, so also set a spending limit on the key.

## Read the results

| Measure | Interpretation |
| --- | --- |
| First-pass validity | Whether the first response satisfied the report schema |
| Repairs | Extra calls required to obtain a valid report |
| Quote grounding | Whether submitted excerpts appear in the retrieved sources |
| Annotation precision/recall | Literal matches against expected keywords, only for reviewed cases |
| Latency | Time for an individual report attempt, including any repair |
| Usage and cost | Recorded token counts and available provider-reported charges |
| Failures | Failed attempts stay in the comparison rather than disappearing from it |

The latest summary appears in the app's Benchmarks view. Detailed results and checkpoints are stored under `.nimble/benchmarks/`, including raw and verified outputs, response IDs and route metadata when available. Checkpoints preserve completed work; they do not automatically resume a run.

For a human review, hide model names and prices, then compare each report with its sources. Rate factual support, specificity and usefulness separately. Record unsupported assumptions, missed opportunities and ambiguous source attribution. A real quote can still support a poor recommendation.

## Before publishing a comparison

Start with a small smoke comparison to check the workflow. The proposed fuller pilot is ten frozen hotel triplets, two models and two repeats: 40 report attempts and at most 80 generation calls. Keep five cases for development and five held out before tuning prompts. This pilot has not been run.

Publish the case count, split, model IDs, prompt version, settings, dates, failures, repairs and per-run measurements. Disclose who reviewed the reports and what the annotations cover. Do not turn one passing fixture or one successful hotel report into an accuracy, reliability or model-superiority claim.

A product smoke test is separate: submit live URLs, inspect partial-source behaviour, open the saved report after a restart, and check the PDF. It validates the integrated workflow; it does not replace model evaluation.
