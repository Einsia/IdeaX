# Benchmark protocols

| Benchmark | Evaluated object | Scale / aggregation | Public entry |
|---|---|---|---|
| Reviewer | One idea with a shared frozen literature evidence packet | N/I/S each 1–5; total `10N + 10I + 5S - 25`, 0–100 | `python benchmarks/run.py reviewer …` |
| Interesting | All cards from one system in one domain | Read every card first; then 0–100 per card, independent judge notes | `python benchmarks/run.py interesting …` |
| Founder | Offline, cutoff-constrained candidates versus later founder papers | 0–3 per candidate/target; best of ten per target, then average targets | `python benchmarks/run.py founder …` |
| IdeaScientist | Frozen proposal and current-literature evidence | Actionability, specificity, clarity, impact, soundness, relevance; separate novelty and structural transfer | `python benchmarks/run.py ideascientist …` |

The main-paper setting is **one independent evaluation per judge**, Astra/xhigh
and Opus 5.5/xhigh. No historical three-repeat score is silently pooled with it.
Prompts, input hashes, attempts and accepted outputs are saved separately.
Retries retain the same model and effort, including retryable Opus refusals.

Reviewer uses the original three-axis N/I/S rubric and the original independent
Astra query/selection process, after which both judges receive the same frozen
packet. It does not claim to have read the whole field or all full texts. Its
original `insufficient_information`/null branch is preserved for comparability;
null means unassessable, not zero. The later requirement to read **all claimed
domain insights/problems, relevant core-insight papers and cited previous
work** is preserved as the separately named experimental prompt
`reviewer/protocols/integrated_full_domain_experimental.md`. That tool-using
protocol is not the tools-disabled main-paper scorer exposed here. Scores from
these protocols must not be mixed.

Interesting's current protocol is `interesting-read-all-then-score-v2`. A
five-card domain panel is sufficient: all read stages precede all score stages.
The legacy ten-card warm-up instructions remain in upstream helper modules;
the public runner uses `interesting/read_all.py`, not that legacy schedule.
Panels are per system and per domain; cross-system mixed-panel experiments are
a different protocol. No forced score distribution is imposed.

IS Bench here is an **existing-output adaptation** of the IdeaScientist
rubrics. Six quality/relevance dimensions and current-literature novelty use
1–10 scales; transfer is 0/1 with a grounded quote and structural explanation.
Measured outcomes are excluded from its reference projection. There is no
fabricated historical-cutoff novelty or native paper Overall score. Idea cards
and Blueprints must be labeled and evaluated separately.

Founder answers are judge-only materials. The main set has 37 domains, 58
cutoff/domain tasks and 69 targets. Efficiency is supplementary (three targets)
and is not added to the main average. Complete Cartesian coverage is required:
a missing judgment cannot default to zero. A complete subset run is reported
separately from completeness of the full main benchmark.

All score reports distinguish returned, numeric and missing judgments. Explicit
terminal native novelty rejections are generation outcomes, not fabricated
judge reviews; the `end_to_end` summary includes their zero slots separately.
For preselected Top1, the only admissible choice is the selector's recorded
rank one before external review.
