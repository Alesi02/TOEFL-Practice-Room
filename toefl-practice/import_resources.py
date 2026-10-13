"""Import the owner's TOEFL materials locally; never guess an answer or audio mapping.

Run with Python and pypdf/pdfplumber installed. The catalog contains answer keys,
so the application must remove answer/reference/sampleAnswer from test responses.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import unicodedata
from pypdf import PdfReader
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / 'data'
REPORT = []
EXERCISES = []
TESTS = []
RESOURCES = []
CACHE = {}

def norm(text):
    return unicodedata.normalize('NFKC', text or '').replace('\u00a0', ' ')

def flatten(text):
    return re.sub(r'\s+', ' ', norm(text)).strip()

def slug(path):
    return hashlib.sha256(path.as_posix().encode('utf8')).hexdigest()[:14]

def clean(text):
    lines = norm(text).splitlines()
    while lines and (not lines[-1].strip() or re.fullmatch(r'\d+', lines[-1].strip())):
        lines.pop()
    lines = [l for l in lines if not re.match(r'^(100 Practice Questions for the TOEFL|Free (Speaking|Writing) Practice 2026|For the TOEFL| ?Practice Test #\d| ?TST Prep)', l.strip())]
    return '\n'.join(lines).strip()

def read_pdf(relative):
    if relative in CACHE:
        return CACHE[relative]
    file = ROOT / relative
    reader = PdfReader(file)
    with pdfplumber.open(file) as pdf:
        pages = [clean(p.extract_text(x_tolerance=2) or '') for p in pdf.pages]
    links = []
    for page in reader.pages:
        urls = []
        for ref in page.get('/Annots', []):
            ann = ref.get_object()
            uri = ann.get('/A', {}).get('/URI')
            if uri and '.mp3' in str(uri):
                urls.append((float(ann['/Rect'][1]), str(uri)))
        links.append([u for _, u in sorted(urls, reverse=True)])
    CACHE[relative] = (pages, links)
    return pages, links

def resource(relative):
    return next(r for r in RESOURCES if r['path'] == relative)

def add(src, page, section, kind, number, **fields):
    r = resource(src)
    ex = dict(id=f"{r['id']}-{section.lower()}-{kind}-{number}", section=section,
              type=kind, title=f'{section} · {kind.replace("_", " ").title()} {number}',
              sourceId=r['id'], sourcePage=page, prompt='', passage='', options=[],
              answer=None, explanation='', audio=None, seconds=45, groupId=None,
              testId=None, order=len(EXERCISES), reference='', sampleAnswer='',questionCount=1)
    ex.update(fields)
    EXERCISES.append(ex)
    return ex

def answer_keys(text):
    matches = list(re.finditer(r'(?m)^\s*(\d+)\.\s*([A-D])(?:\s*[,.:]?)(?:\s|$)', text))
    return {int(m[1]): (m[2], flatten(text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)])) for i, m in enumerate(matches)}

def questions(text):
    starts = list(re.finditer(r'(?m)^\s*(\d+)\.\s*', text))
    result = []
    for i, m in enumerate(starts):
        chunk = text[m.end():starts[i+1].start() if i+1 < len(starts) else len(text)].strip()
        opt = list(re.finditer(r'(?m)^\s*([a-d])\.\s+', chunk))
        if len(opt) == 4:
            result.append((int(m[1]), flatten(chunk[:opt[0].start()]), [dict(key=x[1].upper(), text=flatten(chunk[x.end():opt[k+1].start() if k+1 < len(opt) else len(chunk)])) for k,x in enumerate(opt)]))
        elif '(A)' in chunk and '(D)' in chunk:
            result.append((int(m[1]), flatten(chunk), [dict(key=k, text=f'Location ({k})') for k in 'ABCD']))
    return result

def import_reading(src, task_range, key_range, test=None):
    pages, _ = read_pdf(src)
    keys = answer_keys('\n'.join(pages[a-1] for a in key_range))
    gapkeys = {}
    kt = '\n'.join(pages[a-1] for a in key_range)
    gm = list(re.finditer(r'(?m)^\s*(\d+)\s*-\s*(\d+)\s*$', kt))
    for i,m in enumerate(gm):
        chunk = kt[m.end():gm[i+1].start() if i+1 < len(gm) else len(kt)]
        # One source has sur{face), a typographic closing-brace error; the prompt confirms its five suffix letters.
        vals = re.findall(r'\{([A-Za-z]+)[})]', chunk)
        if len(vals) >= int(m[2])-int(m[1])+1:
            gapkeys[int(m[1])] = vals[:int(m[2])-int(m[1])+1]
    gapstarts = iter(sorted(gapkeys))
    gapstart, passage, gid = 1, '', None
    for pno in task_range:
        text = pages[pno-1]
        gapchunks = re.split(r'Fill in the missing letters in the paragraph\.', text)[1:]
        if gapchunks:
            for chunk in gapchunks:
                gapstart = next(gapstarts, gapstart)
                chunk = re.sub(r'(?m)^\s*#\d+\s*$', '', chunk).strip()
                slots = list(re.finditer(r'\b([A-Za-z]+)\s*_(?:\s*_)*', chunk))
                vals = gapkeys.get(gapstart)
                if not vals or len(vals) != len(slots):
                    REPORT.append(f'{src} p{pno}: complete-words block {gapstart} not imported: suffix count mismatch.')
                    gapstart += len(slots)
                    continue
                spans=[]
                for i,m in enumerate(slots):
                    missing=m[0].count('_')
                    if missing != len(vals[i]):
                        REPORT.append(f'{src} p{pno}: source underscore count differs from key for gap {gapstart+i}; key preserved.')
                    spans.append(dict(index=i+1,prefix=m[1],length=missing))
                index=[0]
                def slot(m):
                    index[0]+=1
                    return m[1]+f'[{index[0]}: '+('_'*m[0].count('_'))+']'
                prompt = flatten(re.sub(r'\b([A-Za-z]+)\s*_(?:\s*_)*', slot, chunk))
                add(src,pno,'Reading','complete_words',gapstart,prompt='Fill in the missing letters. Enter only each missing suffix.',passage=prompt,answer=vals,slots=spans,seconds=180,groupId=f'{resource(src)["id"]}-gap-{gapstart}',testId=test,questionCount=len(vals))
                gapstart+=len(vals)
            passage=''
            continue
        qs = questions(text)
        if not qs: continue
        first = re.search(r'(?m)^\s*\d+\.\s*', text)
        lead=text[:first.start()].strip()
        lead=re.sub(r'(?m)^Module \d+\s*$', '', lead).strip()
        if lead:
            passage=flatten(lead);gid=f'{resource(src)["id"]}-reading-p{pno}'
        for n,prompt,options in qs:
            if n not in keys:
                REPORT.append(f'{src} p{pno}: Reading question {n} skipped, missing key.');continue
            answer,exp=keys[n]
            add(src,pno,'Reading','mcq',n,prompt=prompt,passage=passage,options=options,answer=answer,explanation=exp,seconds=60,groupId=gid,testId=test)

def import_listening(src, task_range, key_range, test=None):
    pages, links=read_pdf(src)
    keytext='\n'.join(pages[a-1] for a in key_range)
    keys=answer_keys(keytext)
    # Short heard statements are separated from explanatory paragraphs in the PDF.
    # Preserve that layout boundary to extract only the actual stimulus for replay.
    reader=PdfReader(ROOT/src)
    layoutkey='\n\n'.join(clean(reader.pages[a-1].extract_text(extraction_mode='layout')) for a in key_range)
    shortrefs={}
    rawmatches=list(re.finditer(r'(?m)^\s*(\d+)\.\s*([A-D])(?:\s*[,.:]?)(?:\s|$)',layoutkey))
    for i,m in enumerate(rawmatches):
        chunk=layoutkey[m.end():rawmatches[i+1].start() if i+1<len(rawmatches) else len(layoutkey)]
        chunk=re.split(r'(?m)^\s*(?:Set \d+|Module \d+|Listen to a Conversation|Listen to an Announcement|Listen and Choose|(?:Conversation|Announcement|Listen to an Academic Talk)\s*#\d+)',chunk)[0]
        paragraphs=[flatten(x) for x in re.split(r'\n\s*\n',chunk) if x.strip()]
        if len(paragraphs)>1:
            candidate=paragraphs[-1]
            if len(candidate.split())<55 and not re.search(r'correct|incorrect|option|transcript',candidate,re.I):shortrefs[int(m[1])]=candidate
    transcripts={}
    tm=list(re.finditer(r'(?m)^(?:Listen to an )?(Conversation|Announcement|(?:Academic Talk|Lecture))\s*#(\d+)\s*Transcript\s*$',keytext))
    for i,m in enumerate(tm):
        chunk=keytext[m.end():tm[i+1].start() if i+1<len(tm) else len(keytext)]
        stop=re.search(r'(?m)^(?:\d+\.\s*[A-D]|(?:Conversation|Announcement|Listen to an Academic Talk|Lecture)\s*#\d+|Module \d+|Listen and Choose)',chunk)
        if stop:chunk=chunk[:stop.start()]
        # The advanced source repeats Conversation #3 in Module 2. Keep the
        # occurrence order instead of overwriting its earlier transcript.
        transcripts.setdefault(m[1],[]).append(flatten(chunk))
    last_audio=None;gid=None;transcript='';category='';counter=Counter()
    for pno in task_range:
        text=pages[pno-1];audio=links[pno-1]
        qs=questions(text)
        if audio and not qs:
            last_audio=audio[0];gid=f'{resource(src)["id"]}-listening-p{pno}'
            category='Conversation' if 'conversation' in text.lower() else ('Announcement' if 'announcement' in text.lower() else 'Academic Talk')
            counter[category]+=1
            choices=transcripts.get(category,[])
            transcript=choices[counter[category]-1] if counter[category]<=len(choices) else ''
        for idx,(n,prompt,options) in enumerate(qs):
            if n not in keys:
                REPORT.append(f'{src} p{pno}: Listening question {n} skipped, missing key.');continue
            selected = audio[idx] if idx<len(audio) else last_audio
            if not selected:
                REPORT.append(f'{src} p{pno}: Listening question {n} retained for reference, excluded from timed tests: no direct audio link in PDF.')
            answer,exp=keys[n]
            short=not prompt or bool(selected and 'statement-' in selected)
            ref=transcript
            if short:
                # Prompt transcript is printed after the short-response explanation.
                ref=shortrefs.get(n,'')
            add(src,pno,'Listening','mcq',n,prompt=prompt or 'Choose the best response to what you hear.',options=options,answer=answer,explanation=exp,audio=selected,reference=ref,seconds=20 if short else 45,groupId=f'{resource(src)["id"]}-listen-{n}' if short else gid,testId=test,audioType='statement' if short else category.lower().replace(' ','_'),audioAvailability='linked' if selected else 'missing')

def numbered(text):
    matches=list(re.finditer(r'(?m)^\s*(\d+)\.\s+',text))
    return [(int(m[1]),text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip()) for i,m in enumerate(matches)]

def import_writing(src,sentence_pages,email_pages,discussion_pages,key_pages,test=None):
    pages,_=read_pdf(src)
    keys='\n'.join(pages[a-1] for a in key_pages)
    before=keys.split('Write an Email')[0]
    answers={n:flatten(chunk) for n,chunk in numbered(before)}
    for pno in sentence_pages:
        for n,chunk in numbered(pages[pno-1]):
            if '_' not in chunk or '/' not in chunk:continue
            if n not in answers:
                REPORT.append(f'{src} p{pno}: sentence {n} skipped, missing key.');continue
            lines=[l.strip() for l in chunk.splitlines() if l.strip()]
            ti=next(i for i,l in enumerate(lines) if '_' in l)
            ci=next(i for i,l in enumerate(lines) if '/' in l)
            context=flatten(' '.join(lines[:ti]));template=flatten(' '.join(lines[ti:ci]));chunks=[flatten(x) for x in ' '.join(lines[ci:]).split('/')]
            add(src,pno,'Writing','sentence',n,prompt=f'{context}\n\n{template}\n\nWords and phrases: '+ ' / '.join(chunks),context=context,template=template,chunks=chunks,answer=answers[n],seconds=36,groupId=f'{resource(src)["id"]}-sentences',testId=test)
    for kind,pnums in [('email',email_pages),('discussion',discussion_pages)]:
        for idx,pno in enumerate(pnums):
            text=pages[pno-1]
            n=re.search(r'#(\d+)',text)
            number=int(n[1]) if n else idx+1
            # Read columns separately: horizontal extraction interleaves the prompt
            # with the response editor and would silently truncate real sentences.
            with pdfplumber.open(ROOT/src) as pdf:
                page=pdf.pages[pno-1]
                placeholder=next((w['top'] for w in page.extract_words() if w['text']=='Space'),730)
                if kind=='email':
                    left=page.crop((40,175,254,730)).extract_text(x_tolerance=2) or ''
                    right=page.crop((254,175,600,max(176,placeholder-2))).extract_text(x_tolerance=2) or ''
                    text=norm(left)+'\n\n'+norm(right).replace('Your Response:','').strip()
                else:
                    left=page.crop((40,175,274,730)).extract_text(x_tolerance=2) or ''
                    right=page.crop((327,175,600,max(176,placeholder-2))).extract_text(x_tolerance=2,layout=True) or ''
                    names=[w['text'] for w in page.extract_words() if 275<=w['x0']<327 and 175<w['top']<placeholder-2]
                    paragraphs=[' '.join(l.strip() for l in block.splitlines() if l.strip()) for block in re.split(r'\n\s*\n',norm(right)) if block.strip()]
                    text=norm(left)+'\n\nStudent comments'+(' ('+', '.join(names)+')' if names else '')+':\n'+'\n\n'.join(paragraphs)
            sample=''
            if kind=='email':
                part=keys.split('Write an Email',1)[-1].split('Write for an Academic Discussion',1)[0]
            else:part=keys.split('Write for an Academic Discussion',1)[-1]
            samples=dict(numbered(part))
            if number in samples:sample=flatten(samples[number])
            elif len(pnums)==1:sample=flatten(re.sub(r'^\s*-?\s*Sample (?:Response|Answers)\s*','',part))
            add(src,pno,'Writing',kind,number,prompt=text,seconds=420 if kind=='email' else 600,testId=test,sampleAnswer=sample)

def import_speaking(src,repeat_pages,interview_pages,key_pages,test=None):
    pages,links=read_pdf(src)
    keys='\n'.join(pages[a-1] for a in key_pages)
    repeats={};interviews={}
    rm=list(re.finditer(r'(?m)^Listen and Repeat(?:\s*#(\d+))?\s*$',keys))
    for i,m in enumerate(rm):
        chunk=keys[m.end():rm[i+1].start() if i+1<len(rm) else len(keys)].split('Take an Interview')[0]
        repeats[int(m[1] or 1)]=dict((n,flatten(s)) for n,s in numbered(chunk))
    im=list(re.finditer(r'(?m)^Take an Interview(?:\s*#(\d+))?\s*$',keys))
    for i,m in enumerate(im):
        chunk=keys[m.end():im[i+1].start() if i+1<len(im) else len(keys)]
        interviews[int(m[1] or 1)]={n:tuple(flatten(x) for x in s.split('Sample Answer',1)) for n,s in numbered(chunk)}
    for kind,pnums,dictionary in [('repeat',repeat_pages,repeats),('interview',interview_pages,interviews)]:
        for idx,pno in enumerate(pnums):
            setnum=idx+1
            use=[u for u in links[pno-1] if ('statement-' in u if kind=='repeat' else 'interview-question-' in u)]
            expected=7 if kind=='repeat' else 4
            if len(use)!=expected or len(dictionary.get(setnum,{}))!=expected:
                REPORT.append(f'{src} p{pno}: {kind} set {setnum} skipped: {len(use)} audio links / {len(dictionary.get(setnum,{}))} key entries.');continue
            scenario=pages[pno-1]
            scenario=re.sub(r'(?s)\n1\.\s.*','',scenario)
            for n,url in enumerate(use,1):
                key=dictionary[setnum][n]
                prompt='Listen carefully and repeat exactly what you hear, only once.' if kind=='repeat' else key[0]
                sample='' if kind=='repeat' else (key[1] if len(key)>1 else '')
                add(src,pno,'Speaking',kind,f'{setnum}-{n}',prompt=prompt,scenario=flatten(scenario),audio=url,reference=key if kind=='repeat' else '',sampleAnswer=sample,seconds=12 if kind=='repeat' else 45,testId=test,groupId=f'{resource(src)["id"]}-{kind}-{setnum}',preparationSeconds=0)

def clean_ets(text):
    text=norm(text)
    text=re.sub(r'(?m)^.*TOEFL iBT.*Practice Test.*$', '',text)
    text=re.sub(r'(?m)^\s*(?:[|.)’¢~]?[\s|.)’¢~]*|[0-9]+|wil|U)\s*$','',text)
    text=text.replace('| think','I think').replace('| believe','I believe').replace('| hope','I hope').replace('| don\'t',"I don't")
    text=text.replace('Abank','A bank').replace('Anew','A new').replace('Tellthe','Tell the').replace('Itis','It is').replace('Toillustrate','To illustrate').replace('onan','on an').replace('amirror','a mirror')
    text=text.replace('Sheena lyengar','Sheena Iyengar').replace('as robiotics','as probiotics')
    # OCR consistently sees the hooked ETS question mark as a final digit 2.
    text=re.sub(r'(?<=[A-Za-z0-9])2(?=\s*(?:\n|$))','?',text)
    text=text.replace('April20?','April 20?').replace('May 27?','May 27?')
    return text.strip()

def ets_questions(text):
    starts=list(re.finditer(r'(?m)^\s*(\d+)\.\s*',text))
    found=[]
    for i,m in enumerate(starts):
        chunk=text[m.end():starts[i+1].start() if i+1<len(starts) else len(text)]
        opts=list(re.finditer(r'\(([A-D])\)\s*',chunk))
        if len(opts)==4:
            found.append((int(m[1]),flatten(chunk[:opts[0].start()]),[dict(key=o[1],text=flatten(chunk[o.end():opts[j+1].start() if j+1<len(opts) else len(chunk)])) for j,o in enumerate(opts)]))
    return found

def import_ets():
    cache=OUT/'ets_sources.json'
    if not cache.exists():
        REPORT.append('Official ETS PDFs retained as references: OCR cache ets_sources.json is not available.')
        return
    datasets=json.loads(cache.read_text(encoding='utf8'))
    for num,d in datasets.items():
        src=f'toefl-ibt-full-length-practice-test-{num}.pdf';tid=f'ets-paper-{num}'
        if not (ROOT/src).exists():continue
        def text(pno):return clean_ets(d['pages'][str(pno)]['text'])
        for module,pnums in d['readingModules'].items():
            vals=d['readingKeys'][module][:10];paragraph=d['gaps'][module]
            index=[0];slots=[]
            def gap(m):
                index[0]+=1;slots.append(dict(index=index[0],prefix=m[1],length=len(m[2])))
                return m[1]+f'[{index[0]}: '+('_'*len(m[2]))+']'
            passage=re.sub(r'([A-Za-z]+)\{([A-Za-z]+)\}',gap,paragraph)
            add(src,pnums[0],'Reading','complete_words',f'm{module}-1',prompt='Fill in the missing letters. Enter only each missing suffix.',passage=passage,answer=vals,slots=slots,seconds=180,groupId=f'{tid}-reading-m{module}-gap',testId=tid,module=int(module),questionCount=10,sourceVerified=True)
            passage='';gid=None;seen=set()
            for pno in pnums:
                page=text(pno)
                # ETS pages sometimes place the next passage after the preceding
                # passage's final question, including the academic title alone.
                split=r'(?m)(?=^Read (?:a|an) [^\n]+|^The Impact of Sports on Social Integration|^The Human Microbiome)'
                for segment in re.split(split,page):
                    qs=ets_questions(segment)
                    if not qs:continue
                    first=re.search(r'(?m)^\s*\d+\.\s*',segment)
                    lead=segment[:first.start()].strip()
                    if lead:
                        if 'Fill' in lead and not lead.startswith('Read'):continue
                        lead=re.sub(r'(?m)^\s*(?:\[.*|dy Like.*)$','',lead)
                        passage=flatten(lead);gid=f'{tid}-reading-m{module}-p{pno}'
                    for n,prompt,opts in qs:
                        if n<=10 or n>20:continue
                        add(src,pno,'Reading','mcq',f'm{module}-{n}',prompt=prompt,passage=passage,options=opts,answer=d['readingKeys'][module][n-1],explanation=f'Official ETS printed answer key: Reading Module {module}, question {n}.',seconds=60,groupId=gid,testId=tid,module=int(module),ocrConfidence=d['pages'][str(pno)]['confidence'],answerKeyVerified=True)
                        seen.add(n)
            if seen!=set(range(11,21)):REPORT.append(f'{src}: Reading module {module} unparsed questions {sorted(set(range(11,21))-seen)}.')
        for n in range(1,11):
            chunks=[flatten(x) for x in d['chunks'][n-1].split('/')]
            context=d['contexts'][n-1];template=d['templates'][n-1]
            add(src,29 if n<=5 else 30,'Writing','sentence',n,prompt=f'{context}\n\n{template}\n\nWords and phrases: '+ ' / '.join(chunks),context=context,template=template,chunks=chunks,answer=d['sentenceAnswers'][n-1],seconds=36,testId=tid,groupId=f'{tid}-sentences',sourceVerified=True)
        for kind,pno in [('email',31),('discussion',32)]:
            prompt=text(pno).replace('Your Response:','')
            prompt=re.sub(r'(?m)^\s*\)\s*','',prompt)
            add(src,pno,'Writing',kind,1,prompt=prompt,seconds=420 if kind=='email' else 600,testId=tid,ocrConfidence=d['pages'][str(pno)]['confidence'])
        # No audio is supplied in these paper PDFs. Preserve the original printed
        # scripts as hidden references, never create a recording or imply replay.
        for module,pnums in d['listeningModules'].items():
            script='';gid=None;seen=set()
            for pno in pnums:
                page=text(pno)
                for segment in re.split(r'(?m)(?=^Listen to (?:a|an) )',page):
                    qs=ets_questions(segment)
                    if not qs:continue
                    first=re.search(r'(?m)^\s*\d+\.\s*',segment)
                    lead=segment[:first.start()].strip()
                    if lead and lead.startswith('Listen'):
                        script=flatten(lead);gid=f'{tid}-listening-m{module}-p{pno}'
                    for n,prompt,opts in qs:
                        short=bool(re.match(r'(?:Woman|Man):',prompt))
                        ref=prompt if short else script
                        keyn=d.get('listeningKeyNumberMap',{}).get(module,{}).get(str(n),n)
                        add(src,pno,'Listening','mcq',f'm{module}-{n}',prompt='Choose the best response to what you hear.' if short else prompt,options=opts,answer=d['listeningKeys'][module][keyn-1],explanation=f'Official ETS printed answer key: Listening Module {module}, answer-row {keyn}.',reference=ref,audio=None,audioAvailability='missing',audioType='statement' if short else 'conversation_or_talk',seconds=20 if short else 45,testId=tid,module=int(module),groupId=f'{tid}-listening-m{module}-{n}' if short else gid,ocrConfidence=d['pages'][str(pno)]['confidence'],answerKeyVerified=True,sourceKeyQuestionNumber=keyn)
                        seen.add(n)
            expected=set(range(1,len(d['listeningKeys'][module])+1))
            if num=='2' and module=='2':
                expected=set(range(1,12))|set(range(13,18))
                REPORT.append(f'{src}: Listening Module 2 skips printed question 12; its final five questions 13–17 correspond to answer rows 12–16 by their original order. Source answer-row numbers are retained explicitly.')
            if seen!=expected:REPORT.append(f'{src}: Listening module {module} unparsed questions {sorted(expected-seen)}.')
        repeats=re.split(r'(?m)^Trainer:\s*',text(35))[1:]
        for n,ref in enumerate(repeats,1):
            add(src,35,'Speaking','repeat',n,prompt='Listen carefully and repeat exactly what you hear, only once.',reference=flatten(ref),audio=None,audioAvailability='missing',seconds=12,testId=tid,groupId=f'{tid}-repeat',preparationSeconds=0)
        interviews=re.split(r'(?m)^Interviewer:\s*',text(36))[1:]
        for n,prompt in enumerate(interviews,1):
            prompt=flatten(prompt).replace('citiese','cities?').replace('enjoyable Give','enjoyable? Give')
            add(src,36,'Speaking','interview',n,prompt=prompt,audio=None,audioAvailability='missing',seconds=45,testId=tid,groupId=f'{tid}-interview',preparationSeconds=0)
        sections={s:[e['id'] for e in EXERCISES if e['testId']==tid and e['section']==s and e.get('audioAvailability')!='missing'] for s in ['Reading','Listening','Speaking','Writing']}
        missing={s:sum(e['testId']==tid and e['section']==s and e.get('audioAvailability')=='missing' for e in EXERCISES) for s in sections}
        questioncounts={s:sum(e['questionCount'] for e in EXERCISES if e['id'] in ids) for s,ids in sections.items()}
        TESTS.append(dict(id=tid,title=f'ETS 2026 Paper Test {num} · Reading & Writing',sections=sections,questionCounts=questioncounts,sectionOrder=['Reading','Listening','Speaking','Writing'],sourceId=resource(src)['id'],adaptive=False,partial=True,availableSections=['Reading','Writing'],missingItemCounts=missing,description='Official paper-adapted practice. Reading and Writing are available as timed exercises. Printed Listening and Speaking scripts have no supplied recordings and remain reference-only. Fixed printed module sequence; no adaptive routing.'))
        REPORT.append(f'{src}: {missing["Listening"]} printed Listening and {missing["Speaking"]} Speaking items retained as references; original audio not supplied.')

def main():
    for path in sorted(ROOT.rglob('*')):
        relative=path.relative_to(ROOT)
        if not path.is_file() or relative.parts[0] in {'tmp','toefl-practice','output','.git','.codex','.agents'}:continue
        ext=path.suffix.lower()
        if ext not in {'.pdf','.flac','.mp3','.wav','.txt','.png','.jpg','.jpeg','.md'}:continue
        section=relative.parts[0] if relative.parts[0] in {'Reading','Listening','Writing','Speaking'} else 'General'
        edition='2026' if '2026' in path.name else ('current-ETS' if path.name.startswith('toefl-ibt-full') else 'reference')
        RESOURCES.append(dict(id=slug(relative),title=path.stem,path=relative.as_posix(),kind='audio' if ext in {'.flac','.mp3','.wav'} else ('pdf' if ext=='.pdf' else 'text' if ext in {'.txt','.md'} else 'image'),section=section,edition=edition,size=path.stat().st_size,exerciseCount=0))
    if (ROOT / 'Reading/Reading-100-questions-2026 --TSP Prep.pdf').exists():import_reading('Reading/Reading-100-questions-2026 --TSP Prep.pdf',range(6,36),range(37,49))
    if (ROOT / 'Listening/Listening-100-questions-2026 --TSP Prep.pdf').exists():import_listening('Listening/Listening-100-questions-2026 --TSP Prep.pdf',range(5,85),range(86,116))
    if (ROOT / 'Writing/Writing-100-questions-2026 --TSP Prep.pdf').exists():import_writing('Writing/Writing-100-questions-2026 --TSP Prep.pdf',range(3,14),range(14,19),range(19,24),range(25,31))
    if (ROOT / 'Speaking/Speaking-questions-2026 --TSP Prep.pdf').exists():import_speaking('Speaking/Speaking-questions-2026 --TSP Prep.pdf',range(4,9),range(9,14),range(15,27))
    config=[(1,range(4,14),range(16,21),range(24,45),range(47,57),[61],[62],range(65,67),range(70,74),[74],[75],range(78,80)),(2,range(4,12),range(15,19),range(22,50),range(53,64),[68],[69],range(72,74),range(77,81),[81],[82],range(85,87))]
    for num,rp,rk,lp,lk,sp,ip,sk,wp,ep,dp,wk in config:
        src=f'TSP Prep-Toefl-complete-test-{num}-2026.pdf';tid=f'tst-test-{num}'
        if not (ROOT/src).exists():continue
        import_reading(src,rp,rk,tid);import_listening(src,lp,lk,tid);import_speaking(src,sp,ip,sk,tid);import_writing(src,wp,ep,dp,wk,tid)
        sections={s:[e['id'] for e in EXERCISES if e['testId']==tid and e['section']==s and e.get('audioAvailability')!='missing'] for s in ['Reading','Listening','Speaking','Writing']}
        missing={s:sum(e['testId']==tid and e['section']==s and e.get('audioAvailability')=='missing' for e in EXERCISES) for s in sections}
        questioncounts={s:sum(e.get('questionCount',1) for e in EXERCISES if e['id'] in ids) for s,ids in sections.items()}
        TESTS.append(dict(id=tid,title=f'TST Prep 2026 · Complete Test {num}',sections=sections,questionCounts=questioncounts,sectionOrder=['Reading','Listening','Speaking','Writing'],sourceId=resource(src)['id'],adaptive=False,missingItemCounts=missing,description='Original printed modules in their supplied order, with missing audio items excluded. The PDF supplies one fixed Module 2 route; computer-adaptive routing is not reproduced.'))
    import_ets()
    # Validate that all objectively graded answers belong to their visible options,
    # and tag the printed module boundaries without creating alternative routes.
    for e in EXERCISES:
        if e['type']=='mcq':
            assert e['answer'] in [o['key'] for o in e['options']],e['id']
            assert len(e['options'])==4 and all(o['text'] for o in e['options']),e['id']
        if e['type']=='sentence':assert e['answer'] and e['chunks'] and e['template'],e['id']
        if e['type']=='complete_words':assert len(e['answer'])==len(e['slots']),e['id']
        if e['section'] in {'Reading','Listening'} and 'module' not in e:
            src=next(r['path'] for r in RESOURCES if r['id']==e['sourceId'])
            pages,_=read_pdf(src)
            e['module']=next((int(m[1]) for p in reversed(pages[:e['sourcePage']]) if (m:=re.search(r'(?m)^\s*Module (\d+)\s*$',p))),None)
    counts=Counter(e['sourceId'] for e in EXERCISES)
    for r in RESOURCES:r['exerciseCount']=counts[r['id']]
    report=dict(resourceCount=len(RESOURCES),exerciseCount=len(EXERCISES),bySection=dict(Counter(e['section'] for e in EXERCISES)),byType=dict(Counter(e['type'] for e in EXERCISES)),audioFiles=sum(r['kind']=='audio' for r in RESOURCES),warnings=REPORT,notes=['All original materials remain linked as local references. Legacy exercises are not converted to the 2026 simulation.','Official ETS paper PDFs were OCR-extracted; objective answer tables, gap paragraphs, and sentence templates were visually verified. Reading and Writing are playable; their unsupplied audio remains reference-only.','The 294 local FLAC files are full practice recordings with no verified sentence/question transcript mapping; indexed as audio drills, not standalone scored questions.','MP3 audio URLs are copied from original PDF link annotations; network access is needed unless cached by the application.','Practice scoring is not an official ETS score. Printed advanced sentence-placement questions retain the publisher’s A–D representation.','Repeat drills use a 12-second response cap; this is a conservative practice cap and is not per-item official timing.'])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'catalog.json').write_text(json.dumps(dict(resources=RESOURCES,exercises=EXERCISES,tests=TESTS,importReport=report),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
