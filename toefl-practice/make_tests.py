"""Assemble reproducible practice forms from authentic, verified source items."""
import json
import random
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent

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
    return 'other'

def build_test(catalog, seed, identifier, title):
    rng = random.Random(seed)
    items = catalog['exercises']
    gap = [x for x in items if x['section']=='Reading' and x['type']=='complete_words' and len(x.get('answer',[]))==10]
    mcq = [x for x in items if x['section']=='Reading' and x['type']=='mcq' and x.get('answer')]
    chosen_gaps = rng.sample(gap, 2)
    academic = [x for x in mcq if len(str(x.get('passage','')).split()) >= 110]
    daily = [x for x in mcq if x not in academic]
    chosen_academic = pick_grouped(academic, 20, rng)
    chosen_daily = pick_grouped(daily, 10, rng)
    reading = chosen_gaps + chosen_daily + chosen_academic
    listening = []
    pool = [x for x in items if x['section']=='Listening' and x.get('audio') and x.get('answer')]
    # A practice composition, not a claim about an invariant ETS blueprint.
    for kind, count in [('short',25),('conversation',8),('announcement',6),('talk',8)]:
        listening.extend(pick_grouped([x for x in pool if listening_type(x)==kind],count,rng))
    writing = rng.sample([x for x in items if x['type']=='sentence' and x.get('answer')],10)
    writing += [rng.choice([x for x in items if x['type']=='email']),rng.choice([x for x in items if x['type']=='discussion'])]
    repeat_groups = [g for g in groups([x for x in items if x['type']=='repeat' and x.get('audio') and x.get('reference')]) if len(g)==7]
    interview_groups = [g for g in groups([x for x in items if x['type']=='interview' and x.get('audio')]) if len(g)==4]
    speaking = rng.choice(repeat_groups) + rng.choice(interview_groups)
    sections = {section:[x['id'] for x in selected] for section,selected in [('Reading',reading),('Listening',listening),('Writing',writing),('Speaking',speaking)]}
    selected = reading + listening + writing + speaking
    if len({x['id'] for x in selected})!=len(selected): raise ValueError('Repeated exercise within a test')
    return {'id':identifier,'title':title,'sections':sections,'sectionOrder':['Reading','Listening','Writing','Speaking'],'adaptive':False,'prepared':True,'seed':seed,'questionCounts':{'Reading':50,'Listening':47,'Writing':12,'Speaking':11},'missingItemCounts':{},'sourceIds':sorted({x['sourceId'] for x in selected}),'description':'A fixed practice form assembled from your verified 2026 exercises. Some items recur across forms. Reading and Listening are not adaptive.','notes':['50 Reading points, 47 Listening questions, 12 Writing items, and 11 Speaking responses.','Task types and base timers follow the 2026 format; the particular mix is a practice composition.']}

def prepared_tests(catalog):
    return [build_test(catalog, 2026101300+i, f'prepared-{i:02}', f'Prepared full test {i:02}') for i in range(1,21)]

if __name__=='__main__':
    catalog=json.loads((BASE/'data/catalog.json').read_text(encoding='utf-8'))
    tests=prepared_tests(catalog)
    (BASE/'data/prepared-tests.json').write_text(json.dumps(tests,indent=2),encoding='utf-8')
    print(f'Prepared {len(tests)} complete forms with verified source IDs.')
