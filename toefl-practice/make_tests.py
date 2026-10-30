"""Assemble reproducible practice forms from authentic, verified source items."""
import json
import copy
import random
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from practice_catalog import is_toefl_2026

BASE = Path(__file__).resolve().parent

def normalized_content(value):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', str(value or '')).casefold()))


def content_key(item):
    """Recognize duplicate imports even when their IDs or option order differ."""
    section, kind = item['section'], item['type']
    options = tuple(sorted(normalized_content(option['text']) for option in item.get('options', [])))
    if kind == 'repeat':
        content = (normalized_content(item.get('reference') or item.get('audio')),)
    elif kind == 'sentence':
        content = (normalized_content(item.get('context') or item['prompt']), normalized_content(item.get('answer')))
    else:
        stimulus = item.get('reference') if section == 'Listening' else item.get('passage')
        content = (normalized_content(stimulus), normalized_content(item.get('prompt')), options)
    return (section, kind, content)


def reservation_keys(item):
    """Reserve questions and shared passages/recordings for one prepared form."""
    keys = {('id', item['id']), ('content', content_key(item))}
    section, kind = item['section'], item['type']
    if (section == 'Reading' and kind == 'mcq') or section in {'Listening', 'Speaking'}:
        if item.get('groupId'):
            keys.add(('group', section, item['groupId']))
        stimulus = item.get('passage') if section == 'Reading' else item.get('reference') if section == 'Listening' else None
        if stimulus:
            keys.add(('stimulus', section, normalized_content(stimulus)))
        if item.get('audio'):
            keys.add(('audio', str(item['audio']).replace('http://', 'https://')))
    return keys


def available_items(catalog, exclude):
    seen, items = set(), []
    for item in catalog['exercises']:
        if not is_toefl_2026(item) or reservation_keys(item) & exclude:
            continue
        key = content_key(item)
        if key not in seen:
            seen.add(key)
            items.append(item)
    return items


def sample(items, count, rng):
    if len(items) < count:
        raise ValueError(f'Insufficient source items: need {count}, got {len(items)}')
    return rng.sample(items, count)

def groups(items):
    grouped = defaultdict(list)
    for item in items:
        grouped[item.get('groupId') or item['id']].append(item)
    return list(grouped.values())

def pick_grouped(items, count, rng, exclude=()):
    used = set(exclude)
    available = groups([x for x in items if x['id'] not in used])
    rng.shuffle(available)
    chosen = []
    # Prefer complete source groups that fit the remaining question count.
    while available and len(chosen) < count:
        remaining = count - len(chosen)
        index = next((i for i, group in enumerate(available) if len(group) <= remaining), 0)
        chosen.extend(available.pop(index)[:remaining])
    if len(chosen) != count:
        raise ValueError(f'Insufficient source items: need {count}, got {len(chosen)}')
    return chosen

def listening_type(item):
    url = str(item.get('audio','')).lower()
    if 'choose' in url: return 'short'
    if 'conversation' in url: return 'conversation'
    if 'announcement' in url: return 'announcement'
    if 'talk' in url: return 'talk'
    category=str(item.get('audioType','')).lower()
    return {'statement':'short','short':'short','conversation':'conversation','announcement':'announcement','academic_talk':'talk','talk':'talk','lecture':'talk'}.get(category,'other')

def reading_type(item):
    if item.get('readingTaskType') in {'daily','academic'}:
        return item['readingTaskType']
    return 'daily' if re.match(r'^Read (?:a|an)\b', str(item.get('passage','')).strip(), re.I) else 'academic'

def build_reading(items, rng):
    gap = [x for x in items if x['section']=='Reading' and x['type']=='complete_words' and len(x.get('answer',[]))==10]
    mcq = [x for x in items if x['section']=='Reading' and x['type']=='mcq' and x.get('answer')]
    chosen_gaps = sample(gap, 2, rng)
    academic = [x for x in mcq if reading_type(x)=='academic']
    daily = [x for x in mcq if x not in academic]
    chosen_academic = pick_grouped(academic, 20, rng)
    chosen_daily = pick_grouped(daily, 10, rng)
    return chosen_gaps + chosen_daily + chosen_academic

def listening_mix(pool):
    available={kind:sum(listening_type(item)==kind for item in pool) for kind in ('short','conversation','announcement','talk')}
    base={'short':25,'conversation':8,'announcement':6,'talk':8}
    counts={kind:min(count,available[kind]) for kind,count in base.items()}
    if any(count==0 for count in counts.values()):raise ValueError('All four Listening task types are required')
    # The publisher banks do not have identical proportions. Keep 47 questions
    # and all four types, using unused source groups rather than repeating items.
    while sum(counts.values())<47:
        changed=False
        for kind,step in [('conversation',2),('announcement',2),('talk',4),('short',1)]:
            add=min(step,available[kind]-counts[kind],47-sum(counts.values()))
            if add>0:counts[kind]+=add;changed=True
        if not changed:raise ValueError('Insufficient unused Listening items for a complete form')
    return counts

def build_test(catalog, seed, identifier, title, exclude=frozenset()):
    rng = random.Random(seed)
    items = available_items(catalog, exclude)
    reading = build_reading(items,rng)
    listening = []
    pool = [x for x in items if x['section']=='Listening' and x.get('audio') and x.get('answer')]
    # A practice composition, not a claim about an invariant ETS blueprint.
    composition=listening_mix(pool)
    for kind, count in composition.items():
        listening.extend(pick_grouped([x for x in pool if listening_type(x)==kind],count,rng))
    writing = sample([x for x in items if x['type']=='sentence' and x.get('answer')],10,rng)
    writing += sample([x for x in items if x['type']=='email'],1,rng)+sample([x for x in items if x['type']=='discussion'],1,rng)
    repeat_groups = [g for g in groups([x for x in items if x['type']=='repeat' and x.get('audio') and x.get('reference')]) if len(g)==7]
    interview_groups = [g for g in groups([x for x in items if x['type']=='interview' and x.get('audio')]) if len(g)==4]
    if not repeat_groups or not interview_groups:
        raise ValueError('Insufficient complete Speaking prompt groups')
    speaking = rng.choice(repeat_groups) + rng.choice(interview_groups)
    sections = {section:[x['id'] for x in selected] for section,selected in [('Reading',reading),('Listening',listening),('Writing',writing),('Speaking',speaking)]}
    selected = reading + listening + writing + speaking
    if len({x['id'] for x in selected})!=len(selected): raise ValueError('Repeated exercise within a test')
    return {'id':identifier,'title':title,'sections':sections,'sectionOrder':['Reading','Listening','Writing','Speaking'],'adaptive':False,'prepared':True,'seed':seed,'listeningComposition':composition,'questionCounts':{'Reading':50,'Listening':47,'Writing':12,'Speaking':11},'missingItemCounts':{},'sourceIds':sorted({x['sourceId'] for x in selected}),'description':'A fixed practice form assembled from 2026 task types. Reading and Listening are not adaptive.','notes':['50 Reading points, 47 Listening questions, 12 Writing items, and 11 Speaking responses.','Task types and base timers follow the 2026 format; Listening proportions can vary with the unused publisher recordings available.']}

def reserved_for_tests(catalog, forms):
    items={item['id']:item for item in catalog['exercises']}
    return set().union(*(reservation_keys(items[identifier]) for form in forms
                         for identifiers in form.get('sections',{}).values()
                         for identifier in identifiers if identifier in items))


def source_tests(catalog):
    """Keep source order, assigning repeated source material to its first test."""
    items = {item['id']: item for item in catalog['exercises']}
    forms, reserved = [], set()
    for original in catalog.get('tests', []):
        if original.get('prepared'):
            continue
        form = copy.deepcopy(original)
        removed, seen = {}, set()
        for section, identifiers in form['sections'].items():
            kept = []
            for identifier in identifiers:
                item = items[identifier]
                key = content_key(item)
                if reservation_keys(item) & reserved or key in seen:
                    removed[section] = removed.get(section, 0) + item.get('questionCount', 1)
                    continue
                kept.append(identifier)
                seen.add(key)
            form['sections'][section] = kept
        form['questionCounts'] = {
            section: sum(items[identifier].get('questionCount', 1) for identifier in identifiers)
            for section, identifiers in form['sections'].items()}
        if removed:
            form['partial'] = True
            form['excludedDuplicateItemCounts'] = removed
        form['availableSections'] = [section for section, identifiers in form['sections'].items() if identifiers]
        form['disjoint'] = True
        if any(form['sections'].values()):
            forms.append(form)
            reserved.update(reserved_for_tests(catalog, [form]))
    return forms


def prepared_tests(catalog, previous=()):
    forms = []
    reserved = reserved_for_tests(catalog, source_tests(catalog))
    items = {item['id']: item for item in catalog['exercises']}
    # Existing forms keep their questions as the bank grows. Reserve them before
    # assigning new material, so adding resources never reshuffles earlier forms.
    for old in previous[:20]:
        identifiers=[identifier for section in ('Reading','Listening','Writing','Speaking') for identifier in old.get('sections',{}).get(section,[])]
        if not identifiers or len(set(identifiers))!=len(identifiers) or any(identifier not in items or not is_toefl_2026(items[identifier]) for identifier in identifiers):break
        selected=[items[identifier] for identifier in identifiers]
        if len({content_key(item) for item in selected}) != len(selected):
            break
        keys=set().union(*(reservation_keys(item) for item in selected))
        counts={section:sum(item.get('questionCount',1) for item in selected if item['section']==section) for section in ('Reading','Listening','Writing','Speaking')}
        if keys & reserved or counts!={'Reading':50,'Listening':47,'Writing':12,'Speaking':11}:break
        form=copy.deepcopy(old);form['disjoint']=True
        forms.append(form);reserved.update(keys)
    for number in range(len(forms)+1, 21):
        try:
            form = build_test(catalog, 2026101300+number, f'prepared-{number:02}', f'Prepared full test {number:02}', reserved)
        except ValueError:
            break  # Stop when a full form cannot be filled without reusing material.
        form['disjoint'] = True
        form['description'] += ' No exercises, Reading passages, or audio groups are shared with another test.'
        forms.append(form)
        for identifiers in form['sections'].values():
            for identifier in identifiers:
                reserved.update(reservation_keys(items[identifier]))
    return forms


def assemble_tests(catalog, previous=()):
    forms = prepared_tests(catalog, previous) + source_tests(catalog)
    items = {item['id']: item for item in catalog['exercises']}
    reserved = set()
    for form in forms:
        identifiers = [identifier for section in form['sections'].values() for identifier in section]
        keys = reserved_for_tests(catalog, [form])
        if keys & reserved or len({content_key(items[identifier]) for identifier in identifiers}) != len(identifiers):
            raise ValueError('Repeated exercise material in the test library')
        reserved.update(keys)
    return forms


def choose_full_test(catalog, seed):
    """Random selection opens an existing form; it never invents an overlapping test."""
    forms = [form for form in catalog['tests'] if form.get('prepared') and not form.get('partial')]
    if not forms:
        raise ValueError('No complete tests are available without repeating exercises')
    return copy.deepcopy(random.Random(seed).choice(forms))

if __name__=='__main__':
    catalog=json.loads((BASE/'data/catalog.json').read_text(encoding='utf-8'))
    saved=BASE/'data/prepared-tests.json'
    previous=json.loads(saved.read_text(encoding='utf-8')) if saved.exists() else []
    tests=[test for test in assemble_tests(catalog,previous) if test.get('prepared')]
    (BASE/'data/prepared-tests.json').write_text(json.dumps(tests,indent=2),encoding='utf-8')
    print(f'Prepared {len(tests)} complete forms with verified source IDs.')
