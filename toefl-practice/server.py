"""Loopback-only TOEFL practice server. No response or recording is sent online."""
from __future__ import annotations
import atexit
import concurrent.futures
import importlib
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import wave
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(BASE / ".deps"))
sys.path.insert(0, str(BASE))
for folder in ("data", "cache"):
    (BASE / folder).mkdir(exist_ok=True)
storage_config = BASE / 'data/storage-config.json'
configured_directory = json.loads(storage_config.read_text(encoding='utf-8')).get('privateDirectory') if storage_config.exists() else None
default_private = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share'))) / 'TOEFLPractice'
PRIVATE = Path(os.environ.get('TOEFL_DATA_DIR') or configured_directory or default_private)
for folder in ('history', 'recordings'):
    (PRIVATE / folder).mkdir(parents=True, exist_ok=True)
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)
PREPARE_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)
JOBS = {}
JOBS_LOCK = threading.Lock()
MODEL_LOCK = threading.Lock()
LLM_LOCK = threading.Lock()
WHISPER = None
SPEECH_MODEL_DIR = BASE / 'models/whisper-base.en'
SPEECH_PROCESS_LOCK = threading.RLock()
SPEECH_STATE_LOCK = threading.Lock()
SPEECH_RUNTIME = None
SPEECH_STATUS = None
SPEECH_CHECK_THREAD = None
SPEECH_CHECKED_AT = 0
SERVER_REVISION = hashlib.sha256(''.join(
    hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(BASE.glob('*.py'), key=lambda path: path.name)).encode()).hexdigest()
LLAMA = None
LLAMA_LOG = None
LLAMA_TOKEN = uuid.uuid4().hex + uuid.uuid4().hex
PORT = int(os.environ.get("TOEFL_PORT", "8765"))
LLAMA_PORT = PORT + 1
FEEDBACK_MODEL = BASE / 'models/qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
CATALOG = {"resources": [], "exercises": [], "tests": [], "importReport": {}}
EXERCISES = {}
RESOURCES = {}
ALLOWED_AUDIO = set()

def load_catalog():
    global CATALOG, EXERCISES, RESOURCES, ALLOWED_AUDIO
    path = BASE / "data" / "catalog.json"
    if path.exists():
        CATALOG = json.loads(path.read_text(encoding="utf-8"))
    from practice_catalog import classify, remove_generated_audio
    remove_generated_audio(CATALOG)
    for exercise in CATALOG['exercises']:classify(exercise)
    EXERCISES = {x["id"]: x for x in CATALOG["exercises"]}
    RESOURCES = {x["id"]: x for x in CATALOG["resources"]}
    ALLOWED_AUDIO = {x[key] for x in CATALOG['exercises'] for key in ('audio','exerciseImage') if isinstance(x.get(key), str)}
    overrides=BASE/'data/reference-overrides.json'
    if overrides.exists():
        for identifier,reference in json.loads(overrides.read_text(encoding='utf-8')).items():
            if identifier in EXERCISES:
                EXERCISES[identifier].update(reference if isinstance(reference,dict) else {'reference':reference})
                EXERCISES[identifier]['transcriptVerified']=True
    if EXERCISES:
        from make_tests import prepared_tests
        try:
            forms = prepared_tests(CATALOG)
        except ValueError as error:
            forms = []
            CATALOG.setdefault('importReport', {}).setdefault('warnings', []).append('More verified source exercises are needed to assemble full tests: ' + str(error))
        (BASE / 'data/prepared-tests.json').write_text(json.dumps(forms, indent=2), encoding='utf-8')
        CATALOG['tests'] = forms + CATALOG['tests']

def normalized(text):
    text = str(text).lower().replace("’", "'")
    for source, replacement in {"can't": "cannot", "won't": "will not", "don't": "do not", "doesn't": "does not", "didn't": "did not", "it's": "it is", "i'm": "i am", "we're": "we are", "they're": "they are", "you're": "you are", "isn't": "is not", "aren't": "are not", "wasn't": "was not", "weren't": "were not"}.items():
        text = re.sub(r"\b" + re.escape(source) + r"\b", replacement, text)
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)

def media_path(source):
    if source.startswith(("http://", "https://")):
        if source not in ALLOWED_AUDIO:
            raise ValueError("Audio is not in the imported catalog")
        import hashlib
        suffix = Path(urllib.parse.urlparse(source).path).suffix or ".mp3"
        target = BASE / "cache" / (hashlib.sha256(source.encode()).hexdigest() + suffix)
        if not target.exists():
            request = urllib.request.Request(source.replace("http://", "https://", 1), headers={"User-Agent": "Local-TOEFL-Practice/1.0"})
            with urllib.request.urlopen(request, timeout=40) as response:
                data = response.read(30 * 1024 * 1024 + 1)
            if len(data) > 30 * 1024 * 1024:
                raise ValueError("Audio file is too large")
            temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(target)
        return target
    path = (ROOT / source).resolve()
    if not path.is_relative_to(ROOT) or not path.exists():
        raise ValueError("Invalid local resource")
    allowed = {str((ROOT / r['path']).resolve()) for r in RESOURCES.values() if r.get('path')}
    if str(path) not in allowed and source not in ALLOWED_AUDIO:
        raise ValueError("Resource is not in the catalog")
    return path

def read_audio(path):
    from faster_whisper.audio import decode_audio
    return decode_audio(str(path), sampling_rate=16000)

def run_speech_worker(operation, path=None, samples=None, clip=None):
    """Every review uses a verified runtime and a fresh isolated interpreter."""
    global SPEECH_RUNTIME
    with SPEECH_PROCESS_LOCK:
        return _run_speech_worker(operation, path, samples, clip)


def _run_speech_worker(operation, path=None, samples=None, clip=None):
    global SPEECH_RUNTIME
    from speech_runtime import prepare_runtime
    if SPEECH_RUNTIME is None:
        SPEECH_RUNTIME = prepare_runtime(BASE, PRIVATE)
    with tempfile.TemporaryDirectory(prefix='speech-worker-', dir=PRIVATE) as folder:
        directory = Path(folder).resolve()
        if not directory.is_relative_to(PRIVATE.resolve()):
            raise ValueError('Invalid speech temporary directory')
        request = {'operation': operation, 'modelDirectory': str(SPEECH_MODEL_DIR)}
        if clip is not None:
            request['clip'] = clip
        if path is not None:
            request['path'] = str(Path(path).resolve())
        if samples is not None:
            import numpy as np
            np.save(directory/'samples.npy', samples, allow_pickle=False)
            request['samples'] = str(directory/'samples.npy')
        input_path, output_path = directory/'request.json', directory/'response.json'
        input_path.write_text(json.dumps(request), encoding='utf8')
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith('PYTHON') and key != 'TOEFL_SPEECH_WORKER'}
        environment.update(TOEFL_DATA_DIR=str(PRIVATE), HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
        for attempt in range(2):
            output_path.unlink(missing_ok=True)
            runtime = SPEECH_RUNTIME
            flags = ['-I', '-S', '-B'] if runtime['portable'] else ['-I', '-B']
            completed = subprocess.run([str(runtime['python']), *flags, str(runtime['directory']/'server.py'),
                                        '--speech-worker', str(input_path), str(output_path)],
                                      cwd=runtime['directory'], env=environment, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE, timeout=240,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
            result = json.loads(output_path.read_text(encoding='utf8')) if output_path.is_file() else {
                'workerError': 'The speech process stopped unexpectedly.', 'workerErrorType': 'ProcessError'}
            if not result.get('workerError'):
                return result
            recoverable = result.get('workerErrorType') in {'ModuleNotFoundError', 'ImportError', 'ProcessError'}
            diagnostic = {'operation': operation, 'attempt': attempt + 1, 'error': result['workerError'],
                          'type': result.get('workerErrorType'), 'exitCode': completed.returncode,
                          'traceback': result.get('workerTraceback'),
                          'stderr': completed.stderr.decode('utf8', errors='replace')[-2000:]}
            with (PRIVATE/'speech-engine.log').open('a', encoding='utf8') as log:
                log.write(json.dumps(diagnostic, ensure_ascii=False)+'\n')
            if not recoverable or attempt:
                raise RuntimeError(result['workerError'])
            # Missing/changed runtime files are restored from the verified local
            # archive. No reinstall, network request, or recording modification.
            SPEECH_RUNTIME = prepare_runtime(BASE, PRIVATE)

def speech_status_local():
    """Executed in the isolated speech interpreter, never in the web process."""
    try:
        importlib.invalidate_caches()
        importlib.import_module('faster_whisper.audio')
        importlib.import_module('faster_whisper').WhisperModel
        model = SPEECH_MODEL_DIR
        missing = [name for name in ('model.bin', 'config.json', 'tokenizer.json') if not (model / name).is_file()]
        if missing:
            raise RuntimeError('Local speech model is incomplete. Run Setup grading models.cmd.')
        return {'speechAvailable': True, 'speechError': None, 'speechRuntimeVersion': 2}
    except Exception as error:
        # Import errors must reach the parent so it can repair and retry.
        if isinstance(error, ImportError):
            raise
        return {'speechAvailable': False, 'speechError': str(error), 'speechRuntimeVersion': 2}


def speech_status(wait=False):
    """Health remains responsive while startup verification runs in the background."""
    global SPEECH_STATUS, SPEECH_CHECK_THREAD, SPEECH_CHECKED_AT
    def check():
        global SPEECH_STATUS, SPEECH_CHECKED_AT
        try:
            status = run_speech_worker('status')
        except Exception as error:
            status = {'speechAvailable': False, 'speechError': str(error), 'speechRuntimeVersion': 2}
        with SPEECH_STATE_LOCK:
            SPEECH_STATUS = status
            SPEECH_CHECKED_AT = time.monotonic()
    with SPEECH_STATE_LOCK:
        active = SPEECH_CHECK_THREAD and SPEECH_CHECK_THREAD.is_alive()
        interval = 60 if SPEECH_STATUS and SPEECH_STATUS.get('speechAvailable') else 10
        if not active and (SPEECH_STATUS is None or time.monotonic()-SPEECH_CHECKED_AT > interval):
            SPEECH_CHECK_THREAD = threading.Thread(target=check, daemon=True)
            SPEECH_CHECK_THREAD.start()
        thread = SPEECH_CHECK_THREAD
    if wait and thread:
        thread.join(timeout=240)
    with SPEECH_STATE_LOCK:
        return dict(SPEECH_STATUS or {'speechAvailable': False, 'speechError': None,
                                     'speechPreparing': True, 'speechRuntimeVersion': 2})

def audio_metrics(samples):
    import numpy as np
    duration = len(samples) / 16000
    if not len(samples):
        return {"duration": 0, "silent": True, "longPauses": 0}
    peak = float(np.max(np.abs(samples)))
    usable = samples[:len(samples) // 320 * 320]
    frames = usable.reshape(-1, 320) if len(usable) else np.zeros((1, 320))
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    # Energy measurements are descriptive; they are not pronunciation scores.
    threshold = max(0.008, float(np.max(rms)) * 0.065)
    active = np.flatnonzero(rms > threshold)
    pauses = []
    if len(active):
        start = None
        for i in range(int(active[0]), int(active[-1]) + 1):
            if rms[i] <= threshold and start is None:
                start = i
            elif rms[i] > threshold and start is not None:
                length = (i - start) * 0.02
                if length >= 0.7:
                    pauses.append(round(length, 2))
                start = None
    return {"duration": round(duration, 2), "silent": peak < 0.009 or not len(active), "longPauses": len(pauses), "pauseLengths": pauses, "clipped": float(np.mean(np.abs(samples) > 0.99)) > 0.01}

def transcribe(path=None, samples=None):
    return run_speech_worker('transcribe', path=path, samples=samples)

def transcribe_local(path=None, samples=None):
    global WHISPER
    import numpy as np
    with MODEL_LOCK:
        if samples is None:
            samples = read_audio(path)
        metrics = audio_metrics(samples)
        if metrics["silent"]:
            return {"text": "", "metrics": metrics, "segments": [], "note": "No clear speech was detected. Check your microphone."}
        if WHISPER is None:
            from faster_whisper import WhisperModel
            model = SPEECH_MODEL_DIR
            if not (model / "model.bin").exists():
                raise RuntimeError("Local speech model is missing. Run setup_models.py.")
            WHISPER = WhisperModel(str(model), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
        parts, info = WHISPER.transcribe(np.asarray(samples, dtype=np.float32), language="en", beam_size=5, word_timestamps=True, vad_filter=True, condition_on_previous_text=False)
        segments = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(), "confidence": round(s.avg_logprob, 3)} for s in parts if s.no_speech_prob < 0.7]
        text = " ".join(s["text"] for s in segments).strip()
        metrics["wordsPerMinute"] = round(len(normalized(text)) / max(metrics["duration"], 1) * 60)
        return {"text": text, "metrics": metrics, "segments": segments, "note": "Machine transcription can miss words. Listen to the recording and correct the transcript if needed."}

def ensure_llama():
    global LLAMA, LLAMA_LOG
    if LLAMA and LLAMA.poll() is None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
    if LLAMA is None or LLAMA.poll() is not None:
        engines = list((BASE / "engines" / "llama").rglob("llama-server.exe"))
        model = FEEDBACK_MODEL
        if not engines or not model.exists():
            raise RuntimeError("The local feedback model is not installed. Run setup_models.py.")
        LLAMA_LOG = (BASE / "data" / "feedback-engine.log").open("a", encoding="utf-8")
        engine_env = {**os.environ, "LLAMA_API_KEY": LLAMA_TOKEN}
        LLAMA = subprocess.Popen([str(engines[0]), "-m", str(model), "--host", "127.0.0.1", "--port", str(LLAMA_PORT), "-c", "6144", "-t", "6", "--parallel", "1", "--no-ui", "--cors-origins", f"http://127.0.0.1:{PORT}"], stdout=LLAMA_LOG, stderr=LLAMA_LOG, env=engine_env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(90):
        if LLAMA.poll() is not None:
            raise RuntimeError("Local feedback engine could not start. See data/feedback-engine.log.")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Local feedback engine is still loading. Retry shortly.")

def request_assessment(payload):
    """One transport for structured local-model assessments."""
    with LLM_LOCK:
        ensure_llama()
        request = urllib.request.Request(f"http://127.0.0.1:{LLAMA_PORT}/v1/chat/completions",
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + LLAMA_TOKEN})
        with urllib.request.urlopen(request, timeout=240) as response:
            return json.load(response)


def language_feedback(exercise, response, metrics=None):
    from feedback_engine import evaluate
    from feedback_rubric import apply_rubric
    if not normalized(response):
        return apply_rubric({"score": 0, "method": "local rubric review", "strengths": [],
                            "improvements": ["No response was submitted."], "corrections": [], "rubric": {},
                            "limitations": ["Practice feedback; not an official TOEFL score."]}, response, exercise, metrics)
    if exercise['type'] in ('email', 'discussion') and normalized(response) in [
            normalized(str(exercise.get(key, ''))) for key in ('prompt', 'passage') if exercise.get(key)]:
        return apply_rubric({'score': 0, 'method': 'local rubric review', 'rubric': {}, 'strengths': [],
                            'corrections': [], 'improvements': ['Write your own response instead of copying the stimulus.'],
                            'scoreExplanation': 'The submitted response is entirely copied from the task stimulus.'}, response, exercise)
    return evaluate(exercise, response, metrics, request_assessment)

def repetition_rubric_grade(exercise, transcript, metrics=None):
    """Keep word-edit feedback and estimate the content band separately."""
    from feedback_rubric import apply_rubric, verbatim_words
    from feedback_engine import VERSION
    reference=exercise.get('reference','')
    grade=repetition_grade(reference,transcript)
    if not normalized(transcript):
        score,reason=0,'No recognizable response was submitted.'
    elif verbatim_words(reference)==verbatim_words(transcript):
        score,reason=5,'The recognized words exactly match the reference. Auditory intelligibility is not assessed.'
    elif normalized(reference)==normalized(transcript):
        score,reason=4,'The wording differs while preserving the reference meaning.'
    else:
        try:
            reviewed=language_feedback({**exercise,'type':'repeat'},transcript,metrics)
        except Exception as error:
            grade['rubricScoreError']='The numerical repetition estimate is unavailable: '+str(error)
            grade['improvements'].append('Word comparison is saved. Retry after the local feedback engine is ready.')
            return apply_rubric(grade,transcript,exercise,metrics)
        score,reason=reviewed['score'],reviewed.get('scoreExplanation','')
    grade.update(score=score,scoreExplanation=reason,feedbackVersion=VERSION)
    return apply_rubric(grade,transcript,exercise,metrics)

def objective_grade(exercise, response):
    expected = exercise.get("answer")
    kind = exercise["type"]
    if expected is None:
        return {"score": None, "method": "ungraded", "improvements": ["The source answer could not be verified; review this item in the original resource."]}
    if kind == "complete_words":
        answers = response if isinstance(response, list) else re.split(r"[,\n]", str(response))
        expected = expected if isinstance(expected, list) else [expected]
        matched = [normalized(answers[i] if i < len(answers) else "") == normalized(x) for i, x in enumerate(expected)]
        points, total = sum(matched), len(expected)
    elif kind == "mcq":
        points, total = int(str(response).strip().lower() == str(expected).strip().lower()), 1
        matched = [bool(points)]
    else:
        variants = expected if isinstance(expected, list) else [expected]
        points, total = int(any(normalized(response) == normalized(x) for x in variants)), 1
        matched = [bool(points)]
    return {"points": points, "total": total, "correct": points == total, "matched": matched, "answer": expected, "explanation": exercise.get("explanation", ""), "method": "source answer key", "improvements": [] if points == total else ["Compare your answer with the source key and explain the difference before retrying."]}

def repetition_grade(reference, transcript):
    expected, actual = normalized(reference), normalized(transcript)
    # Compute edit operations directly; no external scoring conversion is used.
    table = [[0] * (len(actual) + 1) for _ in range(len(expected) + 1)]
    for i in range(len(expected) + 1): table[i][0] = i
    for j in range(len(actual) + 1): table[0][j] = j
    for i in range(1, len(expected) + 1):
        for j in range(1, len(actual) + 1):
            table[i][j] = min(table[i - 1][j] + 1, table[i][j - 1] + 1, table[i - 1][j - 1] + (expected[i - 1] != actual[j - 1]))
    errors = table[-1][-1]
    accuracy = max(0, 1 - errors / max(1, len(expected))) if actual else 0
    changes = [{"type": tag, "expected": " ".join(expected[i:j]), "heard": " ".join(actual[k:l])} for tag, i, j, k, l in SequenceMatcher(None, expected, actual, autojunk=False).get_opcodes() if tag != "equal"]
    return {"accuracy": round(accuracy * 100, 1), "wordEdits": errors, "expectedWords": len(expected), "changes": changes, "reference": reference, "method": "transcript word comparison", "strengths": ["All words matched the reference transcript."] if not errors and actual else [], "improvements": ["Practise the missing or changed words, especially articles, prepositions, and endings."] if errors else [], "limitations": ["This measures transcript word accuracy, not pronunciation or an official TOEFL score. Check recognition errors before accepting the result."]}

def recording_path(identifier):
    if not re.fullmatch(r"[a-f0-9]{32}\.(webm|ogg|wav|mp4|m4a)", str(identifier)):
        raise ValueError("Invalid recording")
    path = PRIVATE / "recordings" / identifier
    if not path.exists():
        raise ValueError("Recording not found")
    return path

def evaluate_attempt(payload, job, previous=None):
    rows = []
    items = payload.get("items", [])
    if len(items) > 250:
        raise ValueError("Too many items")
    for index, entry in enumerate(items):
        job["message"] = f"Reviewing response {index + 1} of {len(items)}"
        job["completed"] = index
        exercise = EXERCISES.get(entry.get("id"))
        if exercise is None:
            continue
        # A retry keeps completed feedback and only repeats failed evaluations.
        saved_row = next((row for row in previous['rows'] if row['id'] == exercise['id']), None) if previous else None
        if saved_row and not saved_row['grade'].get('error') and not saved_row['grade'].get('rubricScoreError'):
            rows.append(saved_row)
            continue
        response = entry.get("response", "")
        audio = None
        try:
            if exercise["type"] in {"repeat", "interview", "oral_activity"}:
                if not entry.get('recording') and normalized(response):
                    raise ValueError('Speaking requires an audio recording. Typed submissions are not accepted.')
                if entry.get("recording"):
                    audio = transcribe(recording_path(entry["recording"]))
                    response = entry.get("correctedTranscript") if entry.get("correctedTranscript") is not None else audio["text"]
                response = str(response)
                if exercise["type"] == "repeat":
                    grade = repetition_rubric_grade(exercise, response, audio['metrics'] if audio else None) if exercise.get("reference") else {"method": "recording saved", "improvements": ["No verified reference transcript is available for comparison."]}
                else:
                    grade = language_feedback(exercise, response, audio["metrics"] if audio else None)
                if not entry.get("recording"):
                    grade.setdefault('limitations', []).append('No audio response was submitted.')
            elif exercise["type"] in {"email", "discussion", "essay", "worksheet"}:
                grade = language_feedback(exercise, str(response))
            else:
                grade = objective_grade(exercise, response)
        except Exception as error:
            grade = {"score": None, "method": "review incomplete", "error": str(error), "improvements": ["Your response is saved. Retry evaluation after resolving the engine or audio issue."]}
        rows.append({"id": exercise["id"], "section": exercise["section"], "type": exercise["type"], "title": exercise.get("title", ""), "prompt": exercise.get("prompt", ""), "sourceId": exercise.get("sourceId"), "sourcePage": exercise.get("sourcePage"), "response": response, "recording": entry.get("recording"), "audio": audio, "grade": grade, "sampleAnswer": exercise.get("sampleAnswer"), "elapsed": entry.get("elapsed")})
    from review_store import summaries, save_result
    summary, priorities = summaries(rows)
    result = {"id": uuid.uuid4().hex, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "mode": str(payload.get("mode", "practice")), "title": str(payload.get("title", "Practice session"))[:200], "summary": summary, "priorities": priorities[:6], "rows": rows, "disclaimer": "Objective answers use source keys. Open responses use an uncalibrated local model. Repetition uses machine-transcribed word comparison. No score is an official TOEFL band; no proprietary adaptive scoring or pronunciation scoring is reproduced."}
    if previous:
        result['id'], result['created'] = previous['id'], previous['created']
    save_result(PRIVATE, result)
    job["completed"] = len(items)
    return result

def retry_result(identifier, job):
    if not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('Invalid session')
    target = PRIVATE / 'history' / (identifier + '.json')
    previous = json.loads(target.read_text(encoding='utf-8'))
    # Retain the original feedback for recovery; recordings remain untouched.
    backup = PRIVATE / 'retry-backups' / (identifier + '.json')
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
    payload = {'title': previous['title'], 'mode': previous['mode'], 'items': [
        {key: row.get(key) for key in ('id', 'response', 'recording', 'elapsed')}
        for row in previous['rows']
    ]}
    return evaluate_attempt(payload, job, previous=previous)

def submit_job(function, executor=None):
    identifier = uuid.uuid4().hex
    job = {"id": identifier, "status": "working", "message": "Starting local review", "completed": 0}
    with JOBS_LOCK:
        JOBS[identifier] = job
    def work():
        try:
            job["result"] = function(job)
            job["status"] = "done"
            job["message"] = "Complete"
        except Exception as error:
            job["status"] = "error"
            job["error"] = str(error)
    (executor or POOL).submit(work)
    return identifier

def create_clip(payload, job):
    resource = RESOURCES.get(payload.get("resourceId"))
    if not resource or resource.get("kind") not in {"audio", "flac"} and not resource["path"].lower().endswith((".flac", ".mp3", ".wav")):
        raise ValueError("Select an imported audio recording")
    start, end = float(payload.get("start", 0)), float(payload.get("end", 10))
    if start < 0 or end <= start or end - start > 60:
        raise ValueError("Select a clip between 0.2 and 60 seconds")
    job["message"] = "Transcribing the selected prompt locally"
    identifier = "clip-" + uuid.uuid4().hex
    relative = "toefl-practice/cache/" + identifier + ".wav"
    target = ROOT / relative
    recognized = run_speech_worker('clip', path=media_path(resource['path']),
                                   clip={'start': start, 'end': end, 'target': str(target)})
    kind = "interview" if payload.get("type") == "interview" else "repeat"
    exercise = {"id": identifier, "section": "Speaking", "type": kind, "title": resource["title"] + " - selected clip", "sourceId": resource["id"], "prompt": recognized["text"] if kind == "interview" else "Listen carefully and repeat exactly what you hear.", "reference": recognized["text"] if kind == "repeat" else "", "audio": relative, "seconds": 45 if kind == "interview" else min(12, max(8, round((end - start) * 1.3))), "edition": "2026", "referenceMethod": "machine-transcribed source clip"}
    EXERCISES[identifier] = exercise
    CATALOG["exercises"].append(exercise)
    ALLOWED_AUDIO.add(relative)
    (BASE / "data" / "custom-clips.json").write_text(json.dumps([x for x in CATALOG["exercises"] if x["id"].startswith("clip-")], indent=2), encoding="utf-8")
    return public_exercise(exercise)

def prepare_media(payload, job):
    sources = list(dict.fromkeys(EXERCISES[x].get("audio") for x in payload.get("ids", []) if x in EXERCISES and EXERCISES[x].get("audio")))
    failed = []
    for index, source in enumerate(sources):
        job["message"] = f"Preparing audio {index + 1} of {len(sources)}"
        job["completed"] = index
        try:
            media_path(source)
        except Exception as error:
            failed.append({"source": source, "error": str(error)})
    return {"prepared": len(sources) - len(failed), "failed": failed}

def public_exercise(item):
    return {key: value for key, value in item.items() if key not in {"answer", "explanation", "reference", "sampleAnswer", "answerGuide", "ttsText"}}

def set_result_removed(identifier, removed):
    if not re.fullmatch(r'[a-f0-9]{32}', str(identifier)):
        raise ValueError('Invalid result')
    history = PRIVATE / 'history' / (identifier + '.json')
    archived = PRIVATE / 'removed-results' / (identifier + '.json')
    source, destination = (history, archived) if removed else (archived, history)
    private_root = PRIVATE.resolve()
    if not source.resolve().is_relative_to(private_root) or not destination.resolve().is_relative_to(private_root):
        raise ValueError('Invalid result location')
    if not source.is_file():
        raise ValueError('Result not found')
    if destination.exists():
        raise ValueError('Result already exists at the destination')
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.replace(destination)
    return {'ok': True, 'id': identifier, 'removed': removed}

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, format, *args):
        if args and "/api/jobs/" not in str(args[0]):
            print(format % args, flush=True)
    def origin_ok(self):
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        return host in {f"127.0.0.1:{PORT}", f"localhost:{PORT}"} and (not origin or origin in {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"})
    def json(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)
    def file(self, path, content_type=None):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        requested = self.headers.get("Range", "")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
            if not match:
                return self.json({"error": "Invalid range"}, 416)
            if match[1]:
                start = int(match[1]); end = min(int(match[2]) if match[2] else size - 1, size - 1)
            else:
                start = max(0, size - int(match[2] or size))
            if start >= size or end < start:
                return self.json({"error": "Range outside file"}, 416)
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(remaining, 65536))
                if not data: break
                self.wfile.write(data); remaining -= len(data)
    def do_GET(self):
        if not self.origin_ok():
            return self.json({"error": "Use the local app address"}, 403)
        parts = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parts.query)
        try:
            if parts.path == "/api/health":
                return self.json({"ok": True, **speech_status(), "serverRevision": SERVER_REVISION,
                                  "activeJobs": sum(job.get('status') == 'working' for job in list(JOBS.values())),
                                  "feedbackAvailable": FEEDBACK_MODEL.exists(), "localOnly": True,
                                  "exerciseCount": len(EXERCISES), "resourceCount": len(RESOURCES)})
            if parts.path == "/api/catalog":
                return self.json({**CATALOG, "exercises": [public_exercise(x) for x in CATALOG["exercises"]]})
            if parts.path.startswith("/api/jobs/"):
                job = JOBS.get(parts.path.rsplit("/", 1)[-1])
                return self.json(job or {"error": "Job not found"}, 200 if job else 404)
            if parts.path == "/api/media":
                return self.file(media_path(query.get("source", [""])[0]))
            if parts.path == '/api/source-page':
                resource=RESOURCES.get(query.get('sourceId',[''])[0])
                page=int(query.get('page',['1'])[0])
                if not resource or resource.get('kind')!='pdf' or not 1<=page<=500:
                    raise ValueError('Invalid source page')
                image=BASE/'cache'/f"page-{resource['id']}-{page}.png"
                if not image.exists():
                    import pypdfium2
                    with pypdfium2.PdfDocument(str(media_path(resource['path']))) as document:
                        if page>len(document):raise ValueError('Source page not found')
                        document[page-1].render(scale=1.4).to_pil().save(image)
                return self.file(image,'image/png')
            if parts.path.startswith("/api/recordings/"):
                return self.file(recording_path(parts.path.rsplit("/", 1)[-1]))
            if parts.path == "/api/history":
                values = []
                for f in sorted((PRIVATE / "history").glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:100]:
                    try:
                        item = json.loads(f.read_text(encoding="utf-8"))
                        values.append({k: item[k] for k in ("id", "created", "title", "mode", "summary")})
                    except (ValueError, KeyError): pass
                return self.json(values)
            if parts.path.startswith("/api/history/"):
                identifier = parts.path.rsplit("/", 1)[-1]
                if not re.fullmatch(r"[a-f0-9]{32}", identifier): raise ValueError("Invalid session")
                target = PRIVATE / "history" / (identifier + ".json")
                if not target.exists(): return self.json({"error": "Session not found"}, 404)
                return self.json(json.loads(target.read_text(encoding="utf-8")))
            requested = "index.html" if parts.path == "/" else urllib.parse.unquote(parts.path.lstrip("/"))
            target = (BASE / "static" / requested).resolve()
            if not target.is_relative_to((BASE / "static").resolve()) or not target.is_file():
                return self.json({"error": "Not found"}, 404)
            return self.file(target)
        except BrokenPipeError:
            pass
        except Exception as error:
            return self.json({"error": str(error)}, 400)
    def do_POST(self):
        if not self.origin_ok():
            return self.json({"error": "Cross-origin requests are not allowed"}, 403)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if size > 20 * 1024 * 1024:
                return self.json({"error": "Request too large"}, 413)
            if self.path.startswith("/api/recordings?"):
                extension = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("ext", ["webm"])[0]
                if extension not in {"webm", "ogg", "wav", "mp4", "m4a"}: raise ValueError("Unsupported recording format")
                if not size: raise ValueError("Recording is empty")
                identifier = uuid.uuid4().hex + "." + extension
                (PRIVATE / "recordings" / identifier).write_bytes(self.rfile.read(size))
                return self.json({"id": identifier})
            payload = json.loads(self.rfile.read(size) or b"{}")
            if self.path=='/api/reference':
                exercise=EXERCISES.get(payload.get('id'))
                text=payload.get('text')
                if not exercise or exercise.get('origin')!='recording' and not str(exercise.get('id','')).startswith('clip-'):
                    raise ValueError('Only machine-transcribed custom prompts can be corrected')
                if not isinstance(text,str) or not text.strip() or len(text)>2500:raise ValueError('Enter a prompt transcript up to 2500 characters')
                field='reference' if exercise['type']=='repeat' else 'prompt'
                with MODEL_LOCK:
                    overrides=BASE/'data/reference-overrides.json'
                    values=json.loads(overrides.read_text(encoding='utf-8')) if overrides.exists() else {}
                    values[exercise['id']]={field:text.strip()}
                    temporary=overrides.with_suffix('.tmp')
                    temporary.write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(overrides)
                    exercise[field]=text.strip();exercise['transcriptVerified']=True
                return self.json({'ok':True})
            retry_action = re.fullmatch(r'/api/history/([a-f0-9]{32})/retry', self.path)
            if retry_action:
                return self.json({'jobId': submit_job(lambda job: retry_result(retry_action[1], job))}, 202)
            result_action = re.fullmatch(r'/api/history/([a-f0-9]{32})/(remove|restore)', self.path)
            if result_action:
                return self.json(set_result_removed(result_action[1], result_action[2] == 'remove'))
            if self.path == "/api/evaluate":
                if not isinstance(payload.get("items"), list): raise ValueError("Responses are missing")
                return self.json({"jobId": submit_job(lambda job: evaluate_attempt(payload, job))}, 202)
            if self.path == "/api/create-clip":
                return self.json({"jobId": submit_job(lambda job: create_clip(payload, job))}, 202)
            if self.path == "/api/prepare":
                return self.json({"jobId": submit_job(lambda job: prepare_media(payload, job), executor=PREPARE_POOL)}, 202)
            if self.path == "/api/transcribe":
                path = recording_path(payload.get("recording"))
                return self.json({"jobId": submit_job(lambda job: transcribe(path))}, 202)
            if self.path == "/api/random-test":
                from make_tests import build_test
                test = build_test(CATALOG, uuid.uuid4().int, 'random-' + uuid.uuid4().hex, 'Randomized full test')
                test['prepared'] = False
                return self.json(test)
            if self.path == '/api/shutdown':
                self.json({'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self.json({"error": "Not found"}, 404)
        except Exception as error:
            return self.json({"error": str(error)}, 400)

def shutdown_engines():
    if LLAMA and LLAMA.poll() is None:
        LLAMA.terminate()
    if LLAMA_LOG:
        LLAMA_LOG.close()

def main():
    load_catalog()
    from review_store import upgrade_history
    upgrade_history(PRIVATE, EXERCISES)
    custom = BASE / "data" / "custom-clips.json"
    if custom.exists():
        for item in json.loads(custom.read_text(encoding="utf-8")):
            EXERCISES[item["id"]] = item
            CATALOG["exercises"].append(item)
            ALLOWED_AUDIO.add(item["audio"])
    atexit.register(shutdown_engines)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    speech_status()
    print(f"TOEFL practice ready at http://127.0.0.1:{PORT}", flush=True)
    print("Responses and recordings stay on this computer.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close(); shutdown_engines()

def speech_worker_main(input_path, output_path):
    global SPEECH_MODEL_DIR
    try:
        request = json.loads(input_path.read_text(encoding='utf8'))
        SPEECH_MODEL_DIR = Path(request['modelDirectory']).resolve()
        if request['operation'] == 'status':
            result = speech_status_local()
        elif request['operation'] == 'transcribe':
            import numpy as np
            samples = np.load(request['samples'], allow_pickle=False) if request.get('samples') else None
            result = transcribe_local(path=request.get('path'), samples=samples)
        elif request['operation'] == 'clip':
            import numpy as np
            samples = read_audio(request['path'])
            clip = request['clip']
            start, end = float(clip['start']), float(clip['end'])
            if start < 0 or end <= start or end-start > 60 or end > len(samples)/16000 + 0.1:
                raise ValueError('The selected clip is outside the recording or exceeds 60 seconds')
            chunk = samples[int(start*16000):int(end*16000)]
            result = transcribe_local(samples=chunk)
            if not result['text']:
                raise ValueError('No prompt speech was detected in this clip')
            with wave.open(str(clip['target']), 'wb') as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
                output.writeframes((np.clip(chunk, -1, 1)*32767).astype('<i2').tobytes())
        else:
            raise ValueError('Unknown speech operation')
    except Exception as error:
        import traceback
        result = {'workerError': str(error), 'workerErrorType': type(error).__name__,
                  'workerTraceback': traceback.format_exc()}
    output_path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf8')

if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == '--speech-worker':
        speech_worker_main(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        main()
