"""Download the local CPU engines once; practice and evaluation then stay local."""
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
HEADERS = {"User-Agent": "Local-TOEFL-Practice/1.0"}

def fetch(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 100:
        print("Already available:", path.name, flush=True)
        return
    print("Downloading:", path.name, flush=True)
    request = urllib.request.Request(url, headers=HEADERS)
    temporary = path.with_suffix(path.suffix + ".partial")
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as out:
        shutil.copyfileobj(response, out, 1024 * 1024)
    temporary.replace(path)
    print("Saved:", path.name, flush=True)

def main():
    models = BASE / "models"
    models.mkdir(exist_ok=True)
    manifest = {}
    # Resolve immutable model revisions before downloading.
    for repo, folder, selected in [
        ("Systran/faster-whisper-base.en", "whisper-base.en", None),
        ("unsloth/Qwen3-4B-Instruct-2507-GGUF", "qwen", ["Qwen3-4B-Instruct-2507-Q4_K_M.gguf"]),
    ]:
        with urllib.request.urlopen(urllib.request.Request("https://huggingface.co/api/models/" + repo, headers=HEADERS), timeout=30) as r:
            metadata = json.load(r)
        revision = metadata["sha"]
        names = selected or [x["rfilename"] for x in metadata["siblings"] if x["rfilename"] in {"model.bin", "config.json", "tokenizer.json", "vocabulary.json", "vocabulary.txt", "preprocessor_config.json"}]
        for name in names:
            fetch(f"https://huggingface.co/{repo}/resolve/{revision}/{name}?download=true", models / folder / name)
        manifest[folder] = {"repository": repo, "revision": revision, "files": names}
    archive = models / "llama-b11583-bin-win-cpu-x64.zip"
    fetch("https://github.com/ggml-org/llama.cpp/releases/download/b11583/llama-b11583-bin-win-cpu-x64.zip", archive)
    target = BASE / "engines" / "llama"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            output = (target / info.filename).resolve()
            if not output.is_relative_to(target.resolve()):
                raise ValueError("Unsafe archive path")
        z.extractall(target)
    manifest["llama"] = {"release": "b11583", "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    (models / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Local speech and feedback engines are ready.", flush=True)

if __name__ == "__main__":
    main()
