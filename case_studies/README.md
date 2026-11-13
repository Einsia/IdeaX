# IdeaX case studies

[Model efficiency: six research perspectives](model_efficiency/README.md) contains six single-agent research proposals and their documented literature exploration. The original material is in Chinese, with paper titles and identifiers preserved.

Each example includes two complementary documents:

- **PROPOSAL.md** develops the research question, mechanism and equations, implementation plan, closest prior work, proposed validation, and failure conditions. These are detailed proposals; no separate standardized JSON idea cards are included.
- **PROCESS.md** documents LitGraph queries, problem and insight entries, paper reading depth, candidate revisions, novelty risks, and request times and HTTP status. The supplied package does not include raw API response files or executable code.

| Perspective | Proposal | Exploration record |
|---|---|---|
| A+B mechanisms: spectral constraints for W4A4 | [Proposal](model_efficiency/01_AB_mechanisms/PROPOSAL.md) | [Process](model_efficiency/01_AB_mechanisms/PROCESS.md) |
| Cross-domain transfer: adaptation through compression | [Proposal](model_efficiency/02_Cross_domain_transfer/PROPOSAL.md) | [Process](model_efficiency/02_Cross_domain_transfer/PROCESS.md) |
| Rethinking assumptions: compressed backpropagation with replay | [Proposal](model_efficiency/03_Rethinking_assumptions/PROPOSAL.md) | [Process](model_efficiency/03_Rethinking_assumptions/PROCESS.md) |
| Diagnosis and reattribution: FP4 weight and scale effects | [Proposal](model_efficiency/04_Diagnosis_reattribution/PROPOSAL.md) | [Process](model_efficiency/04_Diagnosis_reattribution/PROCESS.md) |
| Extending boundaries: certified speculative verification | [Proposal](model_efficiency/05_Extending_boundaries/PROPOSAL.md) | [Process](model_efficiency/05_Extending_boundaries/PROCESS.md) |
| Free exploration: rollback-aware MoE expert caching | [Proposal](model_efficiency/06_Free_exploration/PROPOSAL.md) | [Process](model_efficiency/06_Free_exploration/PROCESS.md) |

The examples support inspection of how literature informs a proposal. They report no new model-training or hardware-performance results. The first case explicitly reconstructs the existing SSO mechanism and proposes a W4A4 extension; it is not evidence of independently rediscovering SSO. The remaining proposals also distinguish prior contributions from unresolved novelty risks.

The source archive's 13 Markdown files are preserved unchanged. [SOURCE.json](model_efficiency/SOURCE.json) lists their SHA-256 hashes. Historical API URLs are retained as recorded and may expire; paper identifiers and original-source URLs remain in the documents.
