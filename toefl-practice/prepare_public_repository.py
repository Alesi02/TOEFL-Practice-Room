"""Prepare a source-only public repository, without any private exercise data."""
from pathlib import Path
import shutil
import re

BASE=Path(__file__).resolve().parent
TARGET=BASE.parent/'output/github/TOEFL-Practice-Room'

def main():
    app=TARGET/'toefl-practice'
    app.mkdir(parents=True,exist_ok=True)
    for path in BASE.iterdir():
        if path.is_file() and path.suffix in {'.py','.cmd','.ps1'}:
            shutil.copy2(path,app/path.name)
    shutil.copy2(BASE/'requirements.txt',app/'requirements.txt')
    shutil.copy2(BASE/'.gitignore',app/'.gitignore')
    for path in (BASE/'static').rglob('*'):
        if path.is_file():
            dest=app/'static'/path.relative_to(BASE/'static')
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest)
    readme=(BASE/'PUBLIC-README.md').read_text(encoding='utf-8')
    (TARGET/'README.md').write_text(readme,encoding='utf-8')
    (app/'README.md').write_text(readme,encoding='utf-8')
    (TARGET/'.gitignore').write_text('output/\ntmp/\nReading/\nListening/\nSpeaking/\nWriting/\n*.pdf\n*.flac\n*.mp3\n*.wav\n*.zip\n*.webm\n*.ogg\n*.m4a\n',encoding='utf-8')
    forbidden={'.pdf','.flac','.mp3','.wav','.webm','.ogg','.gguf','.bin','.zip'}
    for path in TARGET.rglob('*'):
        if path.is_file():
            if path.suffix in forbidden or path.name in {'catalog.json','ets_sources.json','storage-config.json','custom-clips.json'}:
                raise ValueError('Private or binary data found in public checkout: '+str(path))
            content=path.read_text(encoding='utf-8')
            if re.search(r'[A-Za-z]:[/\\]Users[/\\][^/\\\s\"\']+', content):
                raise ValueError('Machine-specific path found in public checkout')
    print('Public source checkout prepared:',TARGET)
    print('Files:',sum(p.is_file() for p in TARGET.rglob('*')))

if __name__=='__main__':main()
