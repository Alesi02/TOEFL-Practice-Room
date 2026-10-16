"""An offline, verified speech runtime kept beside private application data.

The portable app seeds this once from its already installed Python/dependencies.
It never downloads or installs packages during grading.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile

RUNTIME_VERSION = 2


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # A short sibling name avoids exceeding Windows' path limit for deep
    # dependency paths; appending a UUID to their filename can exceed it.
    temporary = path.with_name('.' + uuid.uuid4().hex[:12] + '.tmp')
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def portable_files(base):
    for folder in ('.runtime', '.deps'):
        for path in sorted((base/folder).rglob('*')):
            if (path.is_file() and '__pycache__' not in path.parts
                    and path.suffix not in {'.pyc', '.pyo', '._pth', '.partial'}):
                yield path


def make_backup(base, archive):
    required = ('.runtime/python.exe', '.deps/faster_whisper/audio.py',
                '.deps/faster_whisper/transcribe.py', '.deps/av/__init__.py')
    if not all((base/name).is_file() for name in required):
        raise RuntimeError('The portable speech dependencies are incomplete. Run the app setup once before offline grading.')
    # Never turn a partially installed package into the recovery source. A
    # failed first setup can then install its dependencies and try again.
    probe = subprocess.run([str(base/'.runtime/python.exe'), '-I', '-S', '-B', '-c',
                            'import sys; sys.path.insert(0,sys.argv[1]); import faster_whisper.audio; from faster_whisper import WhisperModel; import av',
                            str(base/'.deps')], cwd=base, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
    if probe.returncode:
        raise RuntimeError('Speech dependencies did not pass the initial check. Complete the app setup before offline grading.')
    temporary = archive.with_name(archive.name + '.' + uuid.uuid4().hex + '.tmp')
    manifest = {'version': RUNTIME_VERSION, 'files': {}}
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as output:
            for path in portable_files(base):
                name = path.relative_to(base).as_posix()
                data = path.read_bytes()
                manifest['files'][name] = hashlib.sha256(data).hexdigest()
                output.writestr(name, data)
            output.writestr('runtime-manifest.json', json.dumps(manifest))
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)


def restore_backup(archive, directory):
    """Verify every installed file; repair missing/changed files from the local ZIP."""
    repaired = 0
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read('runtime-manifest.json'))
        if manifest.get('version') != RUNTIME_VERSION:
            raise ValueError('Unsupported speech runtime backup')
        for name, expected in manifest['files'].items():
            target = (directory/name).resolve()
            if not target.is_relative_to(directory.resolve()):
                raise ValueError('Invalid speech runtime file')
            if target.is_file() and digest(target) == expected:
                continue
            data = source.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('The offline speech runtime backup is damaged')
            atomic_write(target, data)
            repaired += 1
    return repaired


def prepare_runtime(base, private):
    base, private = Path(base).resolve(), Path(private).resolve()
    directory = private/'speech-engine-v2'
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.resolve().is_relative_to(private):
        raise ValueError('Invalid private speech runtime directory')
    archive = private/'speech-engine-v2.zip'
    # Source-only installations retain their explicit Python installation. The
    # Windows portable edition always uses its independent, recoverable copy.
    if not archive.is_file() and not (base/'.runtime/python.exe').is_file():
        return {'python': Path(sys.executable), 'directory': base, 'portable': False, 'repaired': 0}
    if not archive.is_file():
        make_backup(base, archive)
    try:
        repaired = restore_backup(archive, directory)
    except (zipfile.BadZipFile, KeyError, ValueError, EOFError):
        # The installed source is checked before replacing an unusable backup.
        make_backup(base, archive)
        repaired = restore_backup(archive, directory)
    # Ignore registry paths, PYTHONPATH, user site packages and executable .pth
    # files. Only this runtime's standard library, app, and dependencies load.
    version = f'python{sys.version_info.major}{sys.version_info.minor}'
    pth = directory/'.runtime'/f'{version}._pth'
    expected = f'{version}.zip\n.\n..\n../.deps\n'.encode('ascii')
    if not pth.is_file() or pth.read_bytes() != expected:
        atomic_write(pth, expected)
    # Keep the worker code current independently of the dependency snapshot.
    worker = directory/'server.py'
    data = (base/'server.py').read_bytes()
    if not worker.is_file() or worker.read_bytes() != data:
        atomic_write(worker, data)
    return {'python': directory/'.runtime/python.exe', 'directory': directory,
            'portable': True, 'repaired': repaired}


def main():
    base = Path(__file__).resolve().parent
    config_path = base/'data/storage-config.json'
    config = json.loads(config_path.read_text(encoding='utf8')) if config_path.is_file() else {}
    default = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'TOEFLPractice'
    private = Path(os.environ.get('TOEFL_DATA_DIR') or config.get('privateDirectory') or default)
    private.mkdir(parents=True, exist_ok=True)
    runtime = prepare_runtime(base, private)
    flags = ['-I', '-S', '-B'] if runtime['portable'] else ['-I', '-B']
    result = subprocess.run([str(runtime['python']), *flags, '-c',
                             'import faster_whisper.audio; from faster_whisper import WhisperModel; import av'],
                            cwd=runtime['directory'], timeout=60,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
    if result.returncode:
        raise RuntimeError('The local speech runtime could not pass its startup check')
    print('The verified local speech runtime is ready. No download is needed.', flush=True)


if __name__ == '__main__':
    main()
