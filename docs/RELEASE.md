# Code organization revision — 2026-11-12

This is a source-code release assembled from the completed IdeaX experiments.
It does not overwrite or restart the original experiments.

* Four IdeaX configurations come from `current-six-v4-20261108`. Their Chinese
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
