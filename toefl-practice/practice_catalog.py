"""One classification shared by practice views and full-test assembly."""
TASKS_2026={
    'Reading':{'complete_words','mcq'},
    'Listening':{'mcq'},
    'Writing':{'sentence','email','discussion'},
    'Speaking':{'repeat','interview'},
}

def merge_online_bank(catalog, bank):
    """Keep downloaded exercises when the owner's source materials are reimported."""
    for field in ('resources', 'exercises', 'tests'):
        combined={item['id']:item for item in catalog.get(field, [])}
        combined.update({item['id']:item for item in bank.get(field, [])})
        catalog[field]=list(combined.values())
    from collections import Counter
    counts=Counter(item.get('sourceId') for item in catalog['exercises'])
    for resource in catalog['resources']:
        resource['exerciseCount']=counts[resource['id']]
    report=catalog.setdefault('importReport', {})
    report.update(resourceCount=len(catalog['resources']), exerciseCount=len(catalog['exercises']),
                  bySection=dict(Counter(item['section'] for item in catalog['exercises'])),
                  byType=dict(Counter(item['type'] for item in catalog['exercises'])))
    return catalog

def load_practice_banks(catalog, directory):
    """Merge local additions consistently at startup, reimport and export."""
    import json
    for filename in ('online-exercises.json','original-reading.json','online-writing-and-listening.json','original-writing.json'):
        path=directory/filename
        if path.exists():merge_online_bank(catalog,json.loads(path.read_text(encoding='utf8')))
    return catalog

def is_generated_audio(item):
    return (item.get('audioAvailability') == 'synthesized'
            or 'synthesized' in str(item.get('audioMethod', '')).lower()
            or '/synthesized/' in str(item.get('audio', '')).replace('\\', '/').lower())

def remove_generated_audio(catalog):
    """Also clean older extracted banks when the app itself is updated."""
    catalog['exercises'] = [item for item in catalog['exercises'] if not is_generated_audio(item)]
    items = {item['id']: item for item in catalog['exercises']}
    for source in catalog.get('resources', []):
        source['exerciseCount'] = sum(item.get('sourceId') == source['id'] for item in items.values())
    catalog['tests'] = [test for test in catalog.get('tests', []) if not test.get('prepared')]
    for test in catalog['tests']:
        removed = {}
        for section, identifiers in test.get('sections', {}).items():
            removed[section] = sum(identifier not in items for identifier in identifiers)
            test['sections'][section] = [identifier for identifier in identifiers if identifier in items]
        if any(removed.values()):
            test['partial'] = True
            test['availableSections'] = [section for section, identifiers in test['sections'].items() if identifiers]
            missing = test.setdefault('missingItemCounts', {})
            for section, count in removed.items():
                missing[section] = max(missing.get(section, 0), count)
        test['questionCounts'] = {section: sum(items[identifier].get('questionCount', 1) for identifier in identifiers)
                                  for section, identifiers in test['sections'].items()}
        if 'synthesized script audio' in test.get('title', ''):
            test['title'] = test['title'].replace('synthesized script audio', 'Reading & Writing')
            test['partial'] = True
            test['availableSections'] = [section for section, identifiers in test['sections'].items() if identifiers]
            test['description'] = 'Original paper Reading and Writing exercises. Original Listening and Speaking recordings were not supplied.'
    report = catalog.get('importReport', {})
    if 'exerciseCount' in report:
        from collections import Counter
        report.update(exerciseCount=len(items), bySection=dict(Counter(item['section'] for item in items.values())),
                      byType=dict(Counter(item['type'] for item in items.values())))
    report['notes'] = [note for note in report.get('notes', []) if 'synthesi' not in note.lower()]
    return catalog

def is_toefl_2026(item):
    return (not is_generated_audio(item)
            and item.get('type') in TASKS_2026.get(item.get('section'),set())
            and item.get('edition')!='supplementary'
            and not item.get('textPrompt'))

def classify(item):
    item['practiceCategory']='toefl2026' if is_toefl_2026(item) else 'extra'
    return item
