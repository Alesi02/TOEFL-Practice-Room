# TOEFL Practice Room

A local Windows practice app with 3,270 exercises across Reading, Listening, Writing, and Speaking. The bundled collection includes 116 original Reading cards and 20 original Writing prompts (10 emails and 10 academic discussions), alongside the existing source exercises.

## Run from source

1. Install Python 3.12 (64-bit).
2. Download or clone this repository, including its exercise files.
3. Open a terminal in `toefl-practice` and run `python -m pip install --target .deps -r requirements.txt`.
4. Double-click `Start TOEFL.cmd`, or run `python server.py`. Open http://127.0.0.1:8765.
5. For offline Writing feedback and Speaking transcription, run `Setup grading models.cmd` once with internet access. This downloads the models and CPU engine locally; they are deliberately excluded from Git.

## Included content

The repository includes the app, exercise banks, answer keys, original source documents and recordings used by the library, exercise images, and cached prompt clips. No import is required to use the bundled exercises. Model-generated voices are excluded. Original practice is labeled separately from publisher material. Source attribution remains in each exercise.

Prepared and randomized full tests, section practice, timers, answer review, microphone recording, and saved results use the same local app. Practice estimates are not official TOEFL scores. The app does not reproduce proprietary adaptive routing. Recognition errors can be corrected before reevaluation; pronunciation and intonation are not scored.

The exercise text remains usable when a reference image is unavailable; such a source record is marked unavailable rather than pointing to a nonexistent file.

## Clean distribution

Temporary builds, release archives, test copies, screenshots, development caches, installed Python/dependencies, grading models, machine-specific configuration, learner history, and response recordings are excluded. The remaining media files support the exercises and source library. Large downloads consist primarily of these original recordings, not installed models.

Personal results and response recordings are stored under the local application-data directory. They are not committed to this repository. The server listens on the local loopback address.

To add supported source material later, use `Import exercises.cmd`. Original exercise banks are merged at startup and during import.
