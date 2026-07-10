---
name: generate-geo-tasks
description: Generate evidence-aware GEO and search-discovery tasks from local enterprise facts. Use when an agent needs to turn a company profile, customer questions, products, competitors, scenarios, or proof assets into AI-answer prompts, search-intent topics, content briefs, monitoring fields, or a local geo-tasks.json file without inventing claims.
---

# Generate GEO Tasks

Turn verified enterprise facts into reviewable content opportunities. Keep factual gaps visible instead of filling them with plausible claims.

## Workflow

1. Read the enterprise profile. Accept JSON when available; otherwise structure the user's facts before generation.
2. Read `references/geo-method.md` when selecting task types or reviewing quality.
3. Check that at least one core offer exists. Record missing proof, customer language, competitors, or scenarios as gaps.
4. Run:

```bash
python3 skills/generate-geo-tasks/scripts/generate_geo_tasks.py \
  --input <enterprise-profile.json> \
  --out <geo-tasks.json>
```

5. Review every P0 task. Reject tasks whose query does not resemble a real customer question or whose proposed answer needs unavailable evidence.
6. Report the generated task count, P0 tasks, evidence gaps, and recommended first content experiment.

## Guardrails

- Never invent certifications, customers, prices, inventory, delivery dates, rankings, citations, or performance results.
- Distinguish a proposed monitoring prompt from an observed AI answer. This skill does not claim that a brand is already visible in an AI system.
- Do not automate platform login or repeated querying unless the user separately authorizes and configures it.
- Treat generated tasks as candidates. Require human review before publication.

## Input contract

Use the shape shown in `examples/demo-enterprise/enterprise-profile.json`. The generator also accepts common camelCase aliases from the earlier workbench.

Required: `core_offers` or `coreOffer`.

Useful: `company_name`, `customer_questions`, `trigger_scenarios`, `competitors`, `proof_points`, `target_platforms`, `boundaries`, and `conversion_action`.
