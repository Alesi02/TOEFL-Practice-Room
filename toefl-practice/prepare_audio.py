"""Cache original linked prompt files for offline practice without moving source files."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import server

if __name__ == '__main__':
    server.load_catalog()
    sources = sorted(x for x in server.ALLOWED_AUDIO if x.startswith(('https://', 'http://')))
    failures = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(server.media_path, source): source for source in sources}
        for index, result in enumerate(as_completed(pending), 1):
            try:
                result.result()
            except Exception as error:
                failures.append({'source': pending[result], 'error': str(error)})
            if index % 25 == 0 or index == len(sources):
                print(f'Prepared {index}/{len(sources)} prompts; {len(failures)} unavailable.', flush=True)
    import json
    (server.BASE/'data'/'audio-cache-report.json').write_text(json.dumps({'total':len(sources),'failures':failures},indent=2),encoding='utf-8')
