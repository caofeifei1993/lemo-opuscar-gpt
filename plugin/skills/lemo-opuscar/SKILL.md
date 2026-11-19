---
name: lemo-opuscar
description: Create code-rendered short films, explainers and animations with the Lemo-Opuscar style library in Codex. Use for 视频、短片、动画、宣传片 in a named library style, choosing a style for a topic, or creating and reusing a personal style. Not for simple trimming or converting existing videos.
---

# Lemo-Opuscar for Codex

Direct the user's story with the library's 99 visual styles and local rendering tools. This fork is at https://github.com/caoofeifie1993/lemo-opuscar-gpt; the original styles and demos are by [Lemomo (LemoLab)](https://github.com/lemomo-ai/lemo-opuscar). Keep the original licence and attribution. Codex supplies the coding agent; this skill needs no separate OpenAI API key or model endpoint.

## Locate the library

With a shell available, run `sh "<skill base directory>/scripts/setup.sh"`. It checks an explicit `LEMO_OPUSCAR_HOME`, a library in the current working directory, or the library containing this installed skill. Read the final `LIB=<path>` line as a path, not executable shell text; quote paths in commands. If a standalone skill copy reports that the library is missing, run the same script with `install` to download this fork into `~/lemo-opuscar-gpt`, then check again. Existing libraries are not automatically updated.

If the environment cannot execute shell commands or access local files, explain that it cannot render this project's MP4 pipeline there. Work from supplied guides to deliver a treatment or source files with local execution instructions; do not claim to have run the renderer. The normal target is Codex desktop with local execution.

## Route the request

- For finding styles or discussing an idea, read `$LIB/AGENTS.md` and `$LIB/styles/README.md`; do not install rendering dependencies just to answer a question.
- For producing a film, read `$LIB/AGENTS.md`, `$LIB/DIRECTOR.md`, `$LIB/TECHNIQUE.md` and the selected `styles/<slug>/STYLE.md`. Run `sh "<skill base directory>/scripts/setup.sh" deps` for the core tools; add `voice` or `music` only when needed. Track any background install through completion before rendering. Report missing system tools rather than silently installing them globally.
- For changing or saving a personal style, also read `$LIB/MY-STYLES.md`. Look in `~/lemo-my-styles/README.md` before the library when the user names a style.
- For generated illustrations and storyboard panels, follow `$LIB/docs/IMAGE-PROVIDERS.md`. Use the user's latest choice, then the film's saved settings. New films default to ChatGPT native, with GPT Image 2.6 Sunburst recorded as a preference. Proceed with native generation under automatic model selection. In the credits, label the actual model “unknown” in the film’s language. Save each plan with `core/image/image_route.py plan --save` and use its `status` output before dispatch. Import the returned image with `core/image/save_asset.py`. Use OpenArt only when selected, following the guide for live forms, prices and job recovery.
- For voice choice or character casting, read `$LIB/docs/VOICES.md` and list presets with `"$LIB/.venv/bin/python" "$LIB/core/tts/tts_zh.py" --list-presets`. Reuse the user's established voice preference; select a matching preset or generate a short audition with `--preview <id> --out-dir "<project>/voice-preview"`. Use `--cast` and per-line `role` for multiple speakers. Catalog lookup and `--dry-run` are local; Edge synthesis is online, without a separate API key. Do not describe rate/pitch presets as emotion controls or offline voice models.

Use the user's established language, duration, topic, assets and approvals. Ask only for missing decisions that matter, with an available host question tool or ordinary conversation. Do not require Claude commands or Claude-specific tools. Keep requested storyboard review gates; otherwise continue through production and verification.

## Production invariants

- Write a new `TREATMENT.md` from the user's topic before opening demo code. The guides describe the narrow exceptions for documentary material gathering and personal-style work. Demos teach techniques, not stories to re-skin.
- In the library checkout, put the film under `films/<name>/`. From another working directory, use `<name>/` there. Keep generated films outside `styles/` and `core/`.
- Run library commands from `$LIB` with absolute project paths, e.g. `node core/render/still.mjs "<project>" 1.5 3`. Pages use `/core/lib.js` and `/node_modules/three/…`; scripts and `build.sh` use a quoted `$LIB`, never `../..`.
- In a sparse library, fetch demo techniques with `sh "<skill base directory>/scripts/setup.sh" demo <slug>` at the point permitted by the guides. A full local checkout already has them.
- Styles marked ✦ need illustrated assets. Follow the selected provider while preserving the style's prompts, references, dimensions and filenames. Other styles can use generated storyboard concepts on request. Present concepts as such and render the actual shots for any requested film review.
- For recurring characters in native illustrations, use an existing master image or generate a model sheet first. Register it with `image_route.py character`, view the master, and include `--character ID` for each returning character in a shot. Compare the face, costume and proportions with the master when reviewing the results.
- For sequences of full-frame illustrated stills, follow the camera example in `$LIB/DIRECTOR.md` §8. Match the subject's screen position and direction across a cut and check the rendered frames on each side.
- Verify the actual frames, duration, audio and subtitles as directed by `$LIB/DIRECTOR.md` §11. Deliver the MP4 and reproducible sources using absolute clickable file paths; embed review images when supported. State any verification that could not run.

For installation, updates and a short renderer smoke test, see `$LIB/docs/CODEX.md`.
