# Code organization revision — 2026-11-12

## Offline AR baseline source snapshot — 2026-11-18

The eight current offline baseline adapters are now indexed under
[`system/baselines/`](../system/baselines/README.md). The snapshot includes native
integration code, the local literature service, the isolated model bridge,
same-input recovery code and the current scoring implementation. Its own
`source_manifest.json` records original and published hashes; source files are
copied byte for byte. CycleResearcher v5 retains upstream parsing and tutorial
selection, and Dr. Claw retains the uncapped offline workflow.

This is a deployed-source snapshot, not an additional portable installation
target for `system/run.py`. Machine paths and binding checks remain explicit.
Upstream checkouts, corpora, domain materials, environments and fresh acceptance
receipts must be prepared separately. Live queues, credentials, historical
requests, results and checkpoint data are excluded. Packaging does not grant
runtime approval, restart an experiment or establish benchmark completion.

Run `python system/baselines/check.py` for an offline source integrity check.
The existing portable four-system entry points and their frozen prompts are
unchanged.

## Original portable release

This is a source-code release assembled from the completed InsightPro experiments.
It does not overwrite or restart the original experiments.

* Four InsightPro configurations come from `current-six-v4-20261108`. Their Chinese
  generation prompts retain their original bytes and hashes. Multi uses six
  authors, one discussion/revision round and independent selection. The heavy
  v10 workflow is not substituted for multi.
* The two Full configurations share an 8.3 MB snapshot containing 7,641
  domain-specific insights/problems. Each verifies its original per-domain
  hashes. This is not the complete LitGraph paper database. API configurations
  do not mount these snapshots.
* The native runtime's host-specific directory lookup and dependency loading
  were replaced with repository-relative paths and explicit environment
  configuration. The Blueprint endpoint example is now `{api_base}` and is
  filled at runtime. Original cards and source evidence remain immutable.
* Baselines include the deployed CoI chain-recovery source and delivery-v10
  recovery/validation code, plus the native IdeaScientist inference tree. Native
  OpenAlex credential loading supports an explicit environment value. Unused
  model-training code, private credentials, caches and historical outputs are
  excluded. Third-party license files remain alongside each source tree.
* Reviewer acquisition, scoring rubrics, parsers and weights are preserved.
  A portable native CLI transport replaces the host-specific chained transport
  wrappers. Interesting uses the existing read-all schedule and validators.
  IS Bench retains the original prompt generators and reference projection.
* Founder includes task definitions, exported judge truth, prompt protocol and
  v2 matching rubric. The portable scorer checks the complete candidate/target
  Cartesian product. Machine-bound historical campaign launchers and cutoff
  databases are not bundled; cutoff data must be prepared separately.
* All public preparation commands are separate from model-calling commands.
  The release was checked with offline fixtures, original regression tests,
  import checks and source/prompt checksums. No new paid generation or judgment
  was launched to package this release; the new entry points have not produced
  a fresh replication of the paper's scores.

`provenance/source_files.json` records source hashes. A source path that is not
present in the release is marked `omitted`; helpers reduced to reusable
functions are marked `adapted`. `provenance/release_files.json` records the
published artifact hashes. The release excludes Web, Mixed and no-tools
generation conditions from its supported system list.

## Project rename — 2026-11-27

The project was renamed from IdeaX to InsightPro (GitHub repository
`Einsia/IdeaX` → `Einsia/InsightPro`). Every occurrence of the old name in the
release was replaced, including the frozen prompts (`system/*/prompts/blueprint.md`,
the founder prompts now named `benchmarks/founder/prompts/insightpro_*`), the
reviewer prompt, the judge code, environment variables (`IDEAX_*` →
`INSIGHTPRO_*`), tool and schema identifiers and the `system/*/insightpro/`
directories. Only the name changed; no instruction, rubric, selection rule or
parameter changed. Affected entries in `provenance/source_files.json` are marked
`adapted`, and renamed baseline snapshot files are marked `renamed` in
`system/baselines/source_manifest.json` (their `source_sha256` still records the
original file).

Evaluation outputs prepared before the rename pin the old implementation and
prompt hashes; verify them with the pre-rename commit `a98d491`.
`provenance/benchmark_reporting_20261119.json` is a dated record and keeps the
pre-rename hashes. Names of things outside the release are unchanged: the
Hugging Face Space, server paths, archived run directories, archived system ids
in earlier mapping files and the source archive name.

## Standalone Single API prompt — 2026-11-12

`docs/single_api_copyable_zh.md` derives from the original Chinese Single API
prompt and preserves its research requirements. It replaces workspace-specific
client commands with direct HTTP instructions, supplies the current public
LitGraph endpoint, and makes the domain and output location portable. Its source
and output hashes are recorded in `provenance/single_api_copyable_zh.json`.
The original experiment prompts and their release hashes are unchanged. The
public endpoint requires no LitGraph credential but is a temporary tunnel URL.
