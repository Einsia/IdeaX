# IdeaX Research Studio

A static interactive replay of six recorded model-efficiency explorations, with an explicit handoff to real local generation.

[Open the public demo](https://einsia-ideax-demo.static.hf.space/) · [Hugging Face Space](https://huggingface.co/spaces/Einsia/IdeaX-Demo)

## Open the demo locally

From the repository root, no Python dependencies or model credentials are needed for the replay:

```bash
python demo/serve.py
# Open http://127.0.0.1:8765
```

The five stages show a problem, the motivating literature insights, prior-work checks and candidate revisions, the resulting Idea Card, and a development plan. The site labels the replay as recorded material. It does not impersonate a live model session or show private chain-of-thought. The development plan is an editorial summary of the supplied proposal, not a newly generated Research Blueprint.

Each case begins with a plain-language setting, a four-term glossary, and an interactive teaching example. Every stage explains what IdeaX does and what it produces for the next step. Prior-work checks show the initial idea, the overlap discovered, and the revised claim. Formal mechanisms and formulas are expandable; full original documents remain accessible. `guides.json` holds these editorial explanations. The small numerical examples and A/B/C expert labels are explicitly illustrative, not recorded experiments or evidence of effectiveness; they are not injected into exported generation requests. Playback dwell time follows the amount of text, and interacting with an example pauses the guide.

Play walkthrough guides attention through individual evidence cards and design choices with animated highlights, a running progress bar, a short explanation, and automatic scrolling. Pause/resume retains the current position; 1×, 1.5×, and 2× speeds and a next-step control are available. Opening source documents, editing the research brief, or hiding the browser tab pauses playback. Reduced-motion preferences disable movement while preserving the explanations and focus indicators.

Visitors can inspect source links, switch among all six perspectives, download cards, edit a research question and critique, and export a request or a complete portable prompt. The form is kept in browser local storage; it is not submitted to a server. Including a recorded case as starting material is optional. The source API uses a temporary public tunnel; original process records and proposal downloads remain available independently.

“Read the complete case” and “Explore the full process” open the entire original Chinese documents inside the site, including equations, implementation details, all references, and request records. Markdown and math rendering use locally vendored markdown-it 14.1.0 and KaTeX 0.16.22 with their MIT license files in `site/vendor/`; no rendering service is needed. Short English stage summaries are navigation aids, not replacements for those complete cases.

## Start a real local run

Install and configure the system as described in the root README and [running guide](../docs/RUNNING.md). Download `ideax-request.json` from the site and place it in the repository root.

```bash
# Prepare only. No model calls.
python demo/run_local.py --request ideax-request.json --out runs/my-idea

# Inspect runs/my-idea/runs/DOMAIN/initial_prompt.md, then start generation.
python demo/run_local.py --request ideax-request.json --out runs/my-idea --run
```

Use a new output directory for each changed request. If other jobs use the same GPT account, declare their reservations with `--external-gpt-reserved N`.

This invokes the released Single API or Single Full runtime with one continuous research session and a budget of one GPT request. It appends explicit user material to a fresh run and records both original and effective prompt hashes. Full still injects its complete frozen domain snapshot; API does not. Five-card validation, source checks, attempts, and logs use the existing runtime. A repeated command only reuses the same frozen request. Blocked infrastructure failures must be inspected through the runtime's normal recovery process.

The original source prompts and their release hashes remain unchanged. Customized demo outputs are not a reproduction of the paper's benchmark; the request and manifest explicitly record that distinction. No generation or evaluation is automatically triggered by browsing the site.

After successful generation, the existing Blueprint writer can develop the selected ideas:

```bash
python system/run.py single-api blueprint prepare --execution runs/my-idea --out runs/my-blueprints
python system/run.py single-api blueprint run --out runs/my-blueprints --workers 1
```

Use `single-full` instead if that was the selected access mode. Blueprint `run` also calls the configured model. These commands use the generated cards and their actual retained evidence; the replay's source material is not silently substituted.

The portable copy-prompt option is another path: it can be used in a capable agent with HTTP access. Its Full adaptation requests all domain entries through the live API instead of injecting the repository snapshot, so it is not an independently evaluated equivalent of the frozen Full condition.

## Rebuild and deploy

```bash
python demo/build.py
```

The builder checks source references and recorded entry IDs, embeds the 38-domain catalog and portable prompt, and copies the original proposals/process records into `demo/site/sources/`. It does not call models or APIs. `stories.json` contains editorial summaries; the original records and their SHA-256 hashes remain attached to each case. The six proposals are unvalidated research proposals, with established mechanisms and overlap risks explicitly attributed.

Serve **only `demo/site/`**, not the repository root. All assets and sources use relative paths, so this directory can be deployed at `/` or at a project subpath such as `/IdeaX/` on GitHub Pages. Google Fonts is optional; system-font fallbacks work when it is unavailable. No model credentials belong in static assets.

The optional `Demo site` GitHub Actions workflow builds and publishes only this directory using GitHub Pages. First enable Pages with the GitHub Actions source in repository settings, then dispatch the workflow. It is deliberately manual so a normal source push does not assume that Pages is configured.
