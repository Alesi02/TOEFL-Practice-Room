# TOEFL Practice Room

A local practice app with 3,270 built-in exercises across Reading, Listening, Writing and Speaking.

## First-time setup (once per computer)

1. Install Python 3.12 (64-bit).
2. Download the latest source ZIP from this repository (Code → Download ZIP), or clone it. The ZIP contains only the current exercise app; a Git clone also includes older repository history and its previously removed files.
3. Open a terminal in `toefl-practice` and run `python -m pip install --target .deps -r requirements.txt`.
4. Run `Setup grading models.cmd` once with internet access to install the local Writing-feedback model, speech-transcription model and CPU engine.
5. Open `Start TOEFL.cmd`, or run `python server.py`, then visit http://127.0.0.1:8765.

## Every later session

Double-click `Start TOEFL.cmd`. Python, dependencies and models do not need to be reinstalled. The prepared exercises and installed grading models run locally.

## Self-contained exercises

All exercise text, passages, questions, word banks, tables, formatting, answers and grading guides are stored in `toefl-practice/data/catalog.json`. Every existing exercise ID is retained, so saved responses continue to refer to the same exercises. The collection includes 116 original Reading cards and 20 original Writing prompts.

Exercises render as selectable native text and tables. Underlined and italicized choices are preserved. Previously illustrated speaking prompts use descriptions of the depicted activities and transcribed club information. Reading notices and emails use their full text. There are no exercise images, source PDFs, document renderers, OCR tools or import scripts to install or run.

The repository contains only the app, its built-in catalog and the audio files directly used by its exercises. Despite its name, `cache/` holds required exercise clips, not disposable temporary files; additional prompt audio is bundled under `assets/`. Full-length source recordings and Audio Studio are excluded. The Exercise Library lists the bundled exercise collections and retains source attribution. External rubric/source links are optional references and are never loaded to run or grade an exercise.

Prepared and randomized full tests, timers, answer review, microphone recording, saved history, transcript correction and local feedback remain available. Practice estimates are not official TOEFL scores. The app does not reproduce proprietary adaptive routing or score pronunciation and intonation.

## Local files and privacy

Personal responses and recordings are stored in the local application-data directory and are excluded from Git. Installed models, engines and dependencies are also excluded. No source material is needed for startup, practice, review or grading. Image and PDF extraction utilities and their dependencies have been removed.
