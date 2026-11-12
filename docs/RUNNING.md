# Running the systems

Run commands from the repository root, with the virtual environment and your
configuration loaded. `prepare`, `check`, `status`, and `export` do not call a
model. `run` does. Generation defaults to Astra/xhigh through sbtunnel; judges
use their separately configured GPT and Opus profiles. Credentials remain
outside the repository and are never passed in command-line arguments.

## Four IdeaX conditions

```bash
python system/run.py single-full prepare --domains all --out runs/single-full-38
python system/run.py single-full run --execution runs/single-full-38 --gpt-budget 38 --external-gpt-reserved 0
python system/run.py single-full export --execution runs/single-full-38

python system/run.py single-api prepare --domains all --out runs/single-api-38
python system/run.py single-api run --execution runs/single-api-38 --gpt-budget 38 --external-gpt-reserved 0

python system/run.py light-multi-full prepare --domains all --out runs/multi-full-38
python system/run.py light-multi-full run --execution runs/multi-full-38 --gpt-budget 12 --external-gpt-reserved 0

python system/run.py light-multi-api prepare --domains all --out runs/multi-api-38
python system/run.py light-multi-api run --execution runs/multi-api-38 --gpt-budget 12 --external-gpt-reserved 0
```

These are separate example commands, not a recommendation to run all four at
once with zero external reservation. Declare other active usage explicitly.
The multi budget reserves six complete authors at a time: 12 means at most two
domain runs. Generation, discussion, revision, and selection have validation
barriers. Infrastructure failures retain attempts and do not count as success.
Inspect `state.json`, per-domain logs, `recovery_blocked.json`, and validation
receipts before resuming a blocked native session. Do not delete those files to
force progression.

The Full prompt preloads the complete frozen domain snapshot. The API prompt
provides the same library interface and asks the author to explore it. These
are the experiment prompts, including the six ideation rules, novelty check,
five-card schema and source requirements. The four `prompts/` directories also
contain the exact discuss/respond/select instructions.

## Research Blueprint

Blueprint is a separate writing stage after selection, retaining the original
card. It uses the saved search logs, sources, previous work and explicit design
record; it does not claim access to unrecorded private reasoning. New writing
bridges are labeled additions. The writer produces nine sections and checks
whether the core mechanism was preserved.

```bash
python system/run.py single-full blueprint prepare --execution runs/single-full-38 --out runs/blueprint-full-38
python system/run.py single-full blueprint run --out runs/blueprint-full-38 --workers 4
python system/run.py single-full blueprint status --out runs/blueprint-full-38
python system/run.py single-full blueprint export --out runs/blueprint-full-38
```

Use the same condition as the original generation. Full/API access constraints
continue to apply. An export contains `benchmark_input.json` and
`mechanisms.json`, allowing the Blueprint prose to be evaluated while the IS
transfer test receives the original mechanism. Baselines retain their native
report formats; this writer does not silently rewrite baseline outputs.

## IdeaScientist and CoI

```bash
python baselines/run.py prepare --method ideascientist --domains all --out runs/is-38
python baselines/run.py run --method ideascientist --out runs/is-38 --workers 4
python baselines/run.py export --method ideascientist --out runs/is-38

python baselines/run.py prepare --method coi --domains all --out runs/coi-38
python baselines/run.py run --method coi --out runs/coi-38 --workers 4
python baselines/run.py export --method coi --out runs/coi-38
```

Each domain contains five sequential independent native proposals. Different
domains may run in parallel. `IDEAX_BASELINE_GPT_CONCURRENCY` limits actual model
requests across baseline roles and readers. `COI_PYTHON` / `ISCI_PYTHON` can
select separate Python environments; their defaults are the current interpreter.

CoI uses arXiv/OpenAlex, PyMuPDF, lexical reranking, one 2–3-paper chain, and one
native review refinement. Set `OPENALEX_API_KEY`, or point `LITGRAPH_SECRETS_DIR`
to an existing directory containing `openalex.env`; the key is not distributed.
Its native retry/checkpoint, chain repair and terminal novelty rejection policy
are included. A verified terminal novelty rejection occupies a zero-score slot;
network errors, invalid chains and missing outputs do not. The export records
rejections in `zero_score_outcomes.json` separately from real generated cards.

IdeaScientist needs a Svalbard vault API. To build one locally:

```bash
pip install zstandard huggingface_hub
hf download Jerry999/SvalbardIdeaVault --repo-type dataset --local-dir .state/svalbard
export PYTHONPATH="$PWD/baselines/ideascientist/source:$PWD/baselines/runtime"
python baselines/ideascientist/source/scripts/import_hf_vault.py --dataset .state/svalbard --db .state/idea_vault.db --split all
python -m ideascientist.serving.technique_index --db .state/idea_vault.db --out .state/technique_index.db
python -m ideascientist.serving.vault_api --db .state/idea_vault.db --index .state/technique_index.db --host 127.0.0.1 --port 8901
```

Run the server in a separate terminal. The native evaluation configuration uses
`2027-01-01` as its year-level corpus ceiling for the current-literature 2026
experiment; this is distinct from Founder's historical cutoff protocol. The
vault is not replaced with LitGraph. Public-source reading and structured
fallback retain per-source read-depth records. Dataset versions and upstream
model availability affect exact reproduction.

## Benchmark commands

All regular generation exports are arrays with `system`, `task_id`, `idea_id`,
`domain`, `domain_ids`, `task_context`, `idea_text`, and optional source texts
and `selector_top1`. Reviewer needs real LitGraph domain IDs. IS transfer needs
explicit method text; Markdown baseline/Blueprint exports provide a companion
`mechanisms.json` rather than inferring a mechanism from a score.

```bash
python benchmarks/run.py reviewer prepare --input runs/single-full-38/benchmark_input.json --out runs/reviewer-full
python benchmarks/run.py reviewer run --out runs/reviewer-full --astra-concurrency 8 --opus-concurrency 8
python benchmarks/run.py reviewer report --out runs/reviewer-full

python benchmarks/run.py interesting prepare --input runs/single-full-38/benchmark_input.json --out runs/interesting-full
python benchmarks/run.py interesting run --out runs/interesting-full --workers 8

python benchmarks/run.py ideascientist prepare --input runs/reviewer-full --out runs/isbench-full
python benchmarks/run.py ideascientist run --out runs/isbench-full --workers 8
```

For native baseline reports or Blueprints, add `--mechanisms
runs/<export>/mechanisms.json` to IS Bench preparation. Run the regular Reviewer
acquisition first, so both judges and the IS novelty check use the same frozen
paper evidence. `--judges astra` / `--judges opus` select one judge for the
Interesting, IS and Founder runners; both are required for a complete dual
report. Concurrency is explicit and must fit the account's remaining capacity.

`results.json` preserves separate judge results. `means` are all generated
cards; `selector_top1_means` use only the pre-review selection and are null if
that selection is missing or incomplete. `end_to_end` also includes verified
native novelty-rejection zero slots. It does not turn missing judgments into
zeros. There is no post-review Top1 maximization.

## Founder submissions

Founder is a separate **offline historical reconstruction experiment**. Current
38-domain live-library outputs are not valid Founder submissions. Use only a
cutoff-specific corpus and a generator whose documented training cutoff
precedes the task cutoff. Keep `benchmarks/founder/data/targets.jsonl` out of
every generation workspace; it is judge-only ground truth.

A submission is a JSON array of records with `system`, `task_id` from
`data/tasks.jsonl`, ten ranked `cards`, and `generation_protocol`:

```json
{
  "web_access": false,
  "literature_before": "2025-09-01",
  "generator_training_before": "2025-08-01"
}
```

Dates above illustrate the schema; record the actual model and corpus policy
of each run. This metadata is an assertion to audit against generation logs,
not proof that no leakage occurred. The cutoff libraries are external data;
their experiment inventory is in `benchmarks/founder/data/libraries.json`.

```bash
python benchmarks/run.py founder prepare --input submissions.json --out runs/founder
python benchmarks/run.py founder run --out runs/founder --workers 8
python benchmarks/run.py founder report --out runs/founder
```

The public scoring entry validates every card × target pair before aggregation.
It reports each judge's direction hits, mechanism hits and mean per-target best
level. Main coverage is 58 tasks / 69 targets; the three supplementary
Efficiency targets remain in the data but are excluded from the main score.
