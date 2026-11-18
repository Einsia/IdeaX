# Sources and attribution

This repository packages the IdeaX experiment implementations and their local
adaptations. The upstream baseline identities are retained; they are not
reimplemented as IdeaX prompts.

* **CoI-Agent**: [DAMO-NLP-SG/CoI-Agent](https://github.com/DAMO-NLP-SG/CoI-Agent).
  Apache-2.0; the complete license is in `baselines/coi/LICENSE`.
  Local adaptations include GPT Responses transport, arXiv/OpenAlex retrieval,
  lexical reranking, PDF reading, domain-relative tasks, retry/checkpoint handling,
  and a deterministic delivery adapter. The reported configuration uses one
  chain of 2–3 papers and one native review refinement per proposal.
* **IdeaScientist**: *Orchestrating Agents for Grounded Scientific Ideation*.
  CC-BY-NC-4.0; see `baselines/ideascientist/LICENSE`. Its upstream data is
  [Jerry999/SvalbardIdeaVault](https://huggingface.co/datasets/Jerry999/SvalbardIdeaVault).
  This inference snapshot retains the native gap finder, innovator, reviewer,
  report writer, retrieval, citation checking, and evaluation rubrics. Local
  adaptations add GPT transport, public paper reading, recovery and lossless
  normalization of nested report fields. Training dependencies and trained
  weights are not part of this inference release.
* **Founder Bench**: the project’s Founder/Recon benchmark implementation and
  exported task/target definitions. The shared v2 rubric is retained; the public
  wrapper additionally requires complete candidate × target judgments.

Files copied or adapted from experiment sources are listed by original hash in
`provenance/source_files.json`. Removed archival files are explicitly marked in
the release manifest. Changes made during packaging are described in
`docs/RELEASE.md`. Third-party code retains its own license; no blanket license
is asserted over all included projects or external paper texts.

# Offline AR baseline adapters — 2026-11-18

`system/baselines/` publishes the local integration and recovery code for the
current offline protocol. Upstream repositories are dependencies, not bundled
source trees. Each method's `source.json` records the exact commit and repository;
available license and notice files are preserved in `upstream-notices/`.

* AutoResearchClaw: `aiming-lab/AutoResearchClaw` (MIT).
* Dr. Claw: `OpenLAIR/dr-claw` (combined-work licensing; consult its LICENSE and NOTICE).
* ResearchAgent: `JinheonBaek/ResearchAgent` (no top-level license in the pinned checkout; no upstream source redistributed).
* CycleResearcher: `zhu-minjun/Researcher` (CycleResearcher research license).
* SciAgents: `lamm-mit/SciAgentsDiscovery` (Apache-2.0).
* DeepScientist: `ResearAI/DeepScientist` (Apache-2.0, with trademark notice).
* InsightAgents: `MichelleMa8/InsightAgents` (Apache-2.0, with NOTICE).
* AI-Scientist v3: `SakanaAI/AI-Scientist-v3` (see the preserved upstream license).

The adapters retain native method identities and stage boundaries. The shared
evaluator snapshot derives from this project's evaluation implementation. No
license is claimed over external papers, corpora, graph datasets or model weights.

# Demo rendering libraries

The static demo bundles markdown-it 14.1.0 and KaTeX 0.16.22 under the MIT license. Their license texts are included in `demo/site/vendor/markdown-it.LICENSE` and `demo/site/vendor/katex.LICENSE`. KaTeX font assets are included for local equation rendering. DM Sans and Libre Caslon Display are requested from Google Fonts with system-font fallbacks; they are not required for the demo to function.
