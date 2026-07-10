# Enterprise content scoring rubric

Score every dimension with an integer from 0 to 5. Use the supplied facts and the current draft only.

| Key | Dimension | Weight | 0–1 | 2–3 | 4–5 |
|---|---|---:|---|---|---|
| ER | Pain resonance | 1.5 | No recognizable buyer problem | Generic problem or weak scenario | Specific customer language, trigger, cost, or risk |
| SR | Search resonance | 1.5 | No plausible discovery query | Topic exists but intent is vague | Clear learn/compare/buy/avoid query and entities |
| HP | Hook strength | 1.5 | Opening gives no reason to continue | Understandable but familiar | Concrete tension, contrast, risk, or immediate value |
| QL | Quotable judgment | 1.0 | Only slogans or description | A conclusion exists but lacks precision | Memorable, bounded judgment supported by evidence |
| NA | Decision path | 1.0 | Disconnected claims | Partial problem-to-answer flow | Problem → criteria → proof → boundary → next step |
| AB | Valuable audience | 1.0 | Audience is everyone or irrelevant | Broad but partially identifiable | Specific buyer/decision-maker with commercial relevance |
| SAT | Differentiation sharpness | 1.0 | Interchangeable introduction | Some comparison or warning | Useful contrast, anti-pattern, tradeoff, or supplier criterion |

Formula:

```text
composite = weighted points / maximum weighted points × 10
```

Default pass threshold: `6.0`.

Use a blocked reason regardless of composite when the draft contains unsupported proof, prohibited promises, fabricated customer results, misleading comparisons, missing required disclosures, or a failed upstream protocol gate.

For a score below 3, recommend an observable repair: add one customer phrase, replace a slogan with evidence, name the decision criterion, state a boundary, or narrow the audience. Do not recommend “make it more engaging” without specifying how.
