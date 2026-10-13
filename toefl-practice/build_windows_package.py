"""Bundle all original exercises, cached prompt audio, and the Windows runtime.

Learner recordings/results, account information, machine paths and models are
excluded. Models are installed with the included one-time setup launcher.
"""
import argparse
import hashlib
import json
import subprocess
import urllib.parse
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent

def package_files(include_materials=True):
    catalog = json.loads((BASE/'data/catalog.json').read_text(encoding='utf-8'))
    files = {}
    for resource in catalog['resources'] if include_materials else []:
        path = (ROOT/resource['path']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError('Missing or invalid source material: '+resource['path'])
        files[resource['path'].replace('\\','/')] = path
    for path in BASE.iterdir():
        if path.is_file() and path.suffix.lower() in {'.py','.ps1','.cmd','.md','.txt'}:
            files['toefl-practice/'+path.name] = path
    for folder in ('static','.deps','.runtime','engines'):
        for path in (BASE/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc','.pyo'}:
                files['toefl-practice/'+path.relative_to(BASE).as_posix()] = path
    for name in ('catalog.json','ets_sources.json','prepared-tests.json','validation_report.json') if include_materials else []:
        path = BASE/'data'/name
        if path.is_file(): files['toefl-practice/data/'+name] = path
    for source in {x.get('audio') for x in catalog['exercises'] if x.get('audio')} if include_materials else []:
        if not source.startswith(('http://','https://')): continue
        suffix = Path(urllib.parse.urlparse(source).path).suffix or '.mp3'
        name = hashlib.sha256(source.encode()).hexdigest()+suffix
        path = BASE/'cache'/name
        if not path.is_file(): raise ValueError('Uncached prompt: '+source)
        files['toefl-practice/cache/'+name] = path
    return files, catalog

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'output/windows/TOEFL-Practice-Windows.zip'))
    parser.add_argument('--public',action='store_true',help='Exclude all source materials, exercise data, and cached prompts')
    options=parser.parse_args()
    output=Path(options.output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    files,catalog=package_files(include_materials=not options.public)
    if options.public:
        files.pop('toefl-practice/README.md', None)
    if 'toefl-practice/.runtime/python.exe' not in files:
        raise ValueError('Run prepare_windows_runtime.py before packaging')
    # Verify the decoder in the actual bundled runtime before producing a ZIP.
    subprocess.run([str(BASE/'.runtime/python.exe'), '-c', 'import faster_whisper.audio; from faster_whisper import WhisperModel; import av'], cwd=BASE, check=True)
    root='TOEFL Practice Room/'
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
        for index,(relative,path) in enumerate(sorted(files.items()),1):
            archive.write(path,root+relative)
            if index%500==0:print(f'Bundled {index}/{len(files)} files.',flush=True)
        manifest={'originalResources':0 if options.public else len(catalog['resources']),'exerciseEntries':0 if options.public else len(catalog['exercises']),'preparedTests':0 if options.public else 20,'platform':'Windows x64','gradingModels':'Install once with Setup grading models.cmd','excluded':['learner recordings','response history','machine-specific storage configuration','model weights','browser data'],'files':sorted(files)}
        if options.public:
            archive.writestr(root+'toefl-practice/README.md',(BASE/'PUBLIC-README.md').read_text(encoding='utf-8'))
            archive.writestr(root+'toefl-practice/data/catalog.json',json.dumps({'resources':[],'exercises':[],'tests':[],'importReport':{'notes':['Import your own authorized practice materials.']}}))
            archive.writestr(root+'PUBLIC PACKAGE.txt','This package contains app code and a Windows runtime only. It does not include copyrighted exercise files, question data, or user results. Add your own authorized materials using Import exercises.cmd.\n')
        archive.writestr(root+'PACKAGE-MANIFEST.json',json.dumps(manifest,indent=2))
        scope='Add your own authorized materials using Import exercises.cmd.\n' if options.public else 'Keep all folders together: they contain your original exercises and audio.\n'
        archive.writestr(root+'START HERE.txt','1. Extract this entire ZIP into a short path, such as C:\\TOEFL.\n2. Open toefl-practice\\Start TOEFL.cmd.\n3. For offline Writing/Speaking grading, run toefl-practice\\Setup grading models.cmd once with internet access.\n'+scope+'Personal results are saved separately on each computer.\n')
    with zipfile.ZipFile(output) as archive:
        names=set(archive.namelist())
        if not options.public:
            assert all(root+r['path'].replace('\\','/') in names for r in catalog['resources'])
        else:
            assert not any(root+r['path'].replace('\\','/') in names for r in catalog['resources'])
        assert not any('storage-config.json' in n or '/recordings/' in n or '/history/' in n for n in names)
    print(f'Portable package ready: {output}',flush=True)
    print(f'Archive bytes: {output.stat().st_size}',flush=True)

if __name__=='__main__':main()
