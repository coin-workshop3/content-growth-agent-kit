---
name: score-enterprise-content
description: Blind-score enterprise content drafts with a seven-dimension, evidence-backed rubric and a deterministic publication gate. Use when an agent needs to evaluate a GEO answer, article, short-video script, post, or content brief; decide whether it passes a threshold; explain blocked claims; prioritize revisions; or produce a machine-readable score result without using post-publication performance.
---

# Score Enterprise Content

Score only the current draft and supplied enterprise facts. Keep semantic judgment in the Agent and arithmetic in the deterministic calculator.

## Workflow

1. Read the entire draft, enterprise facts, intended audience, channel, and goal.
2. Read `references/rubric.md` completely before assigning scores.
3. Use the repository `protocols/base-methodology.json` unless the user explicitly selects another protocol.
4. Score `ER`, `SR`, `HP`, `QL`, `NA`, `AB`, and `SAT` as integers from 0 to 5. Cite a concrete phrase or an explicit absence for every dimension.
5. Add `blocked_reasons` for unsupported claims, missing mandatory evidence, protocol violations, or unsafe promises.
6. Write an evaluation JSON matching `examples/demo-enterprise/score-evaluation.json`.
7. Run:

```bash
python3 skills/score-enterprise-content/scripts/calculate_score.py \
  --input <score-evaluation.json> \
  --out <score-result.json>
```

8. Return the composite score, pass/fail decision, blocked reasons, the lowest dimensions, and no more than three concrete revision actions.

## Integrity rules

- Do not use views, leads, comments, publication results, or knowledge of the author when blind-scoring a draft.
- Do not increase a score because the topic sounds strategically important.
- A composite at or above the threshold still fails when `blocked_reasons` is non-empty.
- Do not write vague reasons such as “good resonance.” Point to the draft or state what is absent.
- Re-score a revision as a new evaluation; do not overwrite an immutable prediction or historical score.
