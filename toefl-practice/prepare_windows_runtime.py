"""Prepare an isolated Windows x64 runtime for the portable distribution."""
import hashlib
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent

def main():
    target = BASE / '.runtime'
    target.mkdir(exist_ok=True)
    archive = BASE / 'data' / 'python-3.12.10-embed-amd64.zip'
    url = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
    if not archive.exists():
        with urllib.request.urlopen(url, timeout=60) as source, archive.open('wb') as out:
            while chunk := source.read(1024 * 1024):
                out.write(chunk)
    # Verify the published checksum for this official Windows binary.
    if hashlib.md5(archive.read_bytes()).hexdigest() != 'fe8ef205f2e9c3ba44d0cf9954e1abd3':
        raise ValueError('The downloaded runtime does not match the published checksum')
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if not (target / entry.filename).resolve().is_relative_to(target.resolve()):
                raise ValueError('Invalid archive path')
        source.extractall(target)
    (target / 'python312._pth').write_text('python312.zip\n.\n..\n../.deps\nimport site\n', encoding='utf-8')
    print('Portable Windows x64 Python runtime ready.')

if __name__ == '__main__':
    main()
