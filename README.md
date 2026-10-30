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

## Practice and feedback

Practise Reading, Listening, Writing and Speaking with 3,270 built-in exercises. Questions, passages, word banks and tables appear directly in the app. Use the Exercise Library to browse the available collections.

Required audio clips are stored in `toefl-practice/exercise-audio/`, with additional prompt audio under `assets/`. Keep these folders with the app so Listening and Speaking exercises can play their prompts.

Full tests use separate exercises: no questions, Reading passages or audio groups are shared between different tests. Original source tests reserve their material first, and repeated source questions appear only in the first test. The remaining bank supplies six prepared full tests. The random option chooses an existing prepared test.

Timers, answer review, microphone recording, saved history, transcript correction and local feedback are available. Practice estimates are not official TOEFL scores. The app does not reproduce proprietary adaptive routing or score pronunciation and intonation.

## Local files and privacy

Personal responses and recordings are stored in the local application-data directory and are excluded from Git. Installed models, engines and dependencies are also excluded. No source material is needed for startup, practice, review or grading.
