# TOEFL Practice Room

A Windows x64 practice app with timed sections, full-test assembly, audio recording, offline speech transcription, local Writing/interview feedback, and saved result review.

## Public code, private exercises

This repository contains app code only. Preparation PDFs, audio tracks, extracted question banks, answer keys, learner recordings, and results are not published. Each user supplies their own authorized study materials or a private exercise bundle.

The repository owner controls write access to the official repository. Public visitors can download or fork the code and propose changes, but cannot directly modify this repository unless the owner grants them permission.

## Run on Windows

1. Download the public Windows package from Releases and extract it into a short folder path such as `C:\TOEFL`.
2. Double-click `toefl-practice\Start TOEFL.cmd`. The browser app opens at `http://127.0.0.1:8765`.
3. Add your own supported preparation files beside the `toefl-practice` folder, then run `toefl-practice\Import exercises.cmd`.
4. Run `toefl-practice\Setup grading models.cmd` once with internet access to install the local models. Recording transcription and language feedback then run on your computer.

The portable package includes Python and its runtime dependencies; Codex and a separate Python installation are not required. Source-only downloads require Python 3.12 and the dependencies in `requirements.txt`.

## Bring your own materials

The importer supports the saved 2026 TST question-bank/test layouts and preserves other PDFs/audio as study references. Put `Reading`, `Listening`, `Writing`, and `Speaking` folders beside `toefl-practice`. The supported bank filenames are listed in `import_resources.py`. Other exercise sets can use a private `data/catalog.json` with the same schema. Scanned ETS exercises require verified OCR data; the public repository does not include extracted copyrighted text.

Twenty deterministic prepared forms and a randomized-test option are generated when the imported pool contains enough verified questions for all four sections. Fixed forms use current task types and approximate section timers. They do not reproduce ETS's adaptive routing or official score conversion.

Writing and interview task ratings are uncalibrated practice estimates. Repetition feedback uses offline transcription and word comparison. Pronunciation and intonation do not receive validated scores. Users can correct transcripts, re-evaluate, remove results, and undo removal.

## Keep personal results private

Results and recordings are stored per computer under the local application-data folder unless explicitly configured elsewhere. They are excluded from Git and release packages. To move personal history, copy that private folder separately; never add it to a public repository.

## Development

App files are in `toefl-practice/`. Run `python toefl-practice/server.py` from a source checkout after installing the Python dependencies. Import authorized source materials locally; do not commit the generated catalogs or original media. The portable release builder supports `--public` to exclude source materials.

## References

- [ETS current test format](https://www.ets.org/toefl/test-takers/ibt/about/content.html)
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)

Independent practice software. Not affiliated with ETS or preparation publishers. Third-party runtimes and models retain their own licenses. No license is granted for any privately imported study material.
