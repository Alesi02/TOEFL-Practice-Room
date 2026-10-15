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

The importer supports the existing TST question banks and complete tests, older Speaking banks, the supported grammar/phrasal-verb workbooks, and the ETS Speaking lesson plan. Put `Reading`, `Listening`, `Writing`, and `Speaking` folders beside `toefl-practice`, preserving the supported filenames. Test PDFs stored at the project root must also be copied. This is a parser for those known layouts, not a universal importer for any PDF or file format. Other exercise sets can use a private `data/catalog.json` with the same schema. Scanned/image exercises need verified extraction data; the public repository does not include copyrighted extracted text.

With the local speech model installed, Import exercises automatically splits saved Speaking recordings into individual prompt clips. Instructions, sample answers, and closing messages are excluded. Quiet recordings receive a second recognition pass. References are machine-transcribed and can be corrected from the feedback page after checking the original audio. Audio exercises require supplied recordings. Printed scripts without original audio are excluded; the importer does not generate voices. Templates, vocabulary lists, prose explanations, rubrics, schedules, and learner notes do not become exercises.

The Material filter has two groups: **TOEFL 2026 PRACTICE** and **Extra**. Older essay tasks, workbooks and activities outside the current task formats belong to Extra. Prepared and randomized full tests select TOEFL 2026 exercises only. Worksheets preserve their question instructions and provide an editor for numbered answers; source answer guides stay hidden during the attempt. Non-exercise explanations, vocabulary lists and templates are not converted into drills.

Speaking accepts recordings only. After starting a task, its prompt plays automatically and recording begins immediately when playback ends, without preparation time. Build a Sentence uses drag-and-drop tiles rather than clicking words or typing the answer; a keyboard alternative is provided for accessibility.

Twenty deterministic prepared forms and a randomized-test option are generated when the imported pool contains enough verified questions for all four sections. Fixed forms use current task types and approximate section timers. They do not reproduce ETS's adaptive routing or official score conversion.

Writing and Speaking practice ratings use the official ETS TOEFL iBT **0–5 task descriptors**, separately for Email, Academic Discussion, Listen and Repeat, and Interview. Writing is judged holistically for communicative success, development, language and (for email) appropriate social conventions. Ordinary timed-writing slips are allowed; there are no fixed typo, word-count, filler-count or pause-count cutoffs.

Listen and Repeat retains word-edit feedback and adds a numerical **content estimate**. Changed meaning is distinguished from minor wording changes; word accuracy is not converted directly into a score. Numerical review of non-verbatim repetition uses the local feedback model. If that model is unavailable, word comparison remains available. Speaking estimates cover recognized content/language; auditory intelligibility, pronunciation, rhythm and intonation are unassessed. Diagnostic subscores are app feedback, not separate official ETS scores. No task estimate is an official or calibrated 1–6 section band. Each new review includes its rubric source, band explanation and complete task scale. Extra essays and worksheets retain their own source instructions and practice grading. Recognition errors can be corrected before re-evaluation.

TOEFL Primary scoring guides apply to a different test. This app uses the linked TOEFL iBT Speaking guide instead. Users can re-evaluate saved responses to use the current grading criteria; existing feedback is retained until re-evaluation.

An exercises-only private edition can retain the functioning question bank and compressed prompt clips while excluding original PDFs, long recordings, conversion scripts and intermediate extraction files. Its first setup installs speech dependencies and downloads grading models once. Personal history remains separate.

## Keep personal results private

Results and recordings are stored per computer under the local application-data folder unless explicitly configured elsewhere. They are excluded from Git and release packages. To move personal history, copy that private folder separately; never add it to a public repository.

## Development

App files are in `toefl-practice/`. Run `python toefl-practice/server.py` from a source checkout after installing the Python dependencies. Import authorized source materials locally; do not commit the generated catalogs or original media. The portable release builder supports `--public` to exclude source materials.

## References

- [ETS TOEFL iBT Writing rubric](https://www.ets.org/content/dam/ets-org/pdfs/toefl/writing-rubrics.pdf)
- [ETS TOEFL iBT Speaking rubric](https://www.ets.org/content/dam/ets-org/pdfs/toefl/speaking-rubrics.pdf)
- [ETS current test format](https://www.ets.org/toefl/test-takers/ibt/about/content.html)
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)

Independent practice software. Not affiliated with ETS or preparation publishers. Third-party runtimes and models retain their own licenses. No license is granted for any privately imported study material.

Reading uses one input box per missing letter and preserves source paragraph, title and email-header breaks. Updates also filter generated-voice exercises from older imported banks.
