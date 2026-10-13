"""Extract actual questions and worksheet tasks; never invent drills from prose."""
from pathlib import Path
import re,json,hashlib
import pdfplumber

def clean(text):
    text=text.replace('\u200b','').replace('\u00a0',' ')
    lines=[line for line in text.splitlines() if not re.fullmatch(r'\s*\d+\s*',line) and not re.search(r'TST Prep - TSB Handout|Speaking and Writing Topics for the TOEFL Test|TOEFL iBT.*Speaking Lesson Plans|For more info visit',line)]
    return '\n'.join(lines).strip()

def pages(root,path):
    cache=root/'toefl-practice/data/document-text-cache'
    cache.mkdir(parents=True,exist_ok=True)
    target=cache/(hashlib.sha256(path.encode()).hexdigest()[:16]+'.json')
    stamp=[(root/path).stat().st_size,(root/path).stat().st_mtime_ns]
    if target.exists():
        saved=json.loads(target.read_text(encoding='utf-8'))
        if saved['stamp']==stamp:return saved['pages']
    with pdfplumber.open(root/path) as pdf:
        texts=[clean(page.extract_text(x_tolerance=2) or '') for page in pdf.pages]
    target.write_text(json.dumps({'stamp':stamp,'pages':texts},ensure_ascii=False),encoding='utf-8')
    return texts

def numbered_pages(texts,start=1,end=None):
    # Keep page references even when a question continues on the next page.
    output=[];current=None
    for page,text in enumerate(texts,start=1):
        if page<start or (end is not None and page>end):continue
        for line in text.splitlines():
            found=re.match(r'^\s*(\d+)[.)]\s*(\S.*)',line)
            if found:
                if current:output.append(current)
                current={'number':int(found[1]),'page':page,'text':found[2]}
            elif current:
                if re.fullmatch(r'(?:Personal Preferences|Campus Life|Academic Topics|Education|Parenting|People|Community and Government|Science and Technology|Work|Money|Travel|Lifestyle|Entertainment|Volunteering|Health and Wellness|Environment|Technology|Social Issues|Relationships|Future Plans|Culture and Society|Ethics and Morality|Communication|Problem Solving)',line.strip()):continue
                current['text']+='\n'+line
    if current:output.append(current)
    return output

def convert(catalog,root,out):
    resources=catalog['resources'];extra=[];coverage=[]
    def add(resource,number,page,section,kind,prompt,**fields):
        exercise={'id':'extra-'+resource['id']+'-'+section.lower()+'-'+str(number),'sourceId':resource['id'],'sourcePage':page,'section':section,'type':kind,'title':resource['title']+' · '+str(number),'prompt':prompt.strip(),'seconds':45 if section=='Speaking' else 600,'questionCount':1,'edition':'supplementary','origin':'printed exercise','simulationEligible':False,'groupId':None}
        exercise.update(fields);extra.append(exercise)
    for resource in resources:
        path=resource['path'];before=len(extra)
        if path.endswith('GfG- Speaking-Questions.pdf') or path.endswith('TSP Prep- Speaking Questions.pdf'):
            texts=pages(root,path)
            questions=numbered_pages(texts,2 if 'GfG' in path else 4)
            expected=180 if 'GfG' in path else None
            for q in questions:
                text=q['text'];tags=re.findall(r'\((S(?:/W)?|W)\)',text)
                if 'GfG' in path:
                    text=re.sub(r'(?m)^(?:Technology and Innovation|Travel and Culture|Environmental Issues|Education Systems|Current Events|Personal Growth)\s*$','',text).strip()
                text=re.sub(r'\((?:S(?:/W)?|W)\)','',text).strip()
                if not tags or any('S' in tag for tag in tags):
                    add(resource,q['number'],q['page'],'Speaking','interview',text,textPrompt=True)
                if any('W' in tag for tag in tags):add(resource,q['number'],q['page'],'Writing','essay',text)
            if expected and len(questions)!=expected:raise ValueError('Question extraction count differs from printed bank: '+path)
        elif path.endswith('LIBRO Phrasal_Verbs_masterclass_.pdf'):
            texts=pages(root,path)
            # Question regions end before their answer sections or dictionaries.
            regions=[(17,21,22,22),(24,30,31,33),(35,44,45,47),(49,51,52,54),(55,76,77,83),(89,92,93,96),(100,103,104,104),(109,111,112,113),(117,120,121,122),(123,123,124,124)]
            ordinal=0
            for first,last,key_first,key_last in regions:
                joined='\n'.join(texts[first-1:last])
                markers=list(re.finditer(r'(?im)^\s*(?:(?:Phrasal Verbs )?Exercise|Task)\s*\d+\s*[:.]?\s*$',joined))
                for i,marker in enumerate(markers):
                    block=joined[marker.start():markers[i+1].start() if i+1<len(markers) else len(joined)]
                    block=re.sub(r'(?im)^\s*(?:You can find the answers|Check your answers)[^\n]*','',block)
                    if not re.search(r'(?i)match|choose|underline|rewrite|complete|insert|write|decide|put .*gap',block):continue
                    ordinal+=1
                    section='Writing' if re.search(r'(?i)rewrite|word order|separable',block) else 'Reading'
                    guide='\n'.join(texts[key_first-1:key_last])
                    task_number=re.search(r'(?i)(?:Task|Exercise)\s*(\d+)',marker[0])
                    if task_number:
                        key_start=re.search(r'(?im)^.*(?:Task|Exercise)\s*'+task_number[1]+r'\s*[:.]?\s*$',guide)
                        if key_start:
                            guide=guide[key_start.end():]
                            guide=re.split(r'(?im)^.*(?:Task|Exercise)\s*\d+\s*[:.]?\s*$',guide,maxsplit=1)[0]
                    add(resource,ordinal,first,section,'worksheet',block,answerGuide=guide,sourcePageEnd=last,answerPage=key_first,seconds=600)
        elif path.endswith('LIBRO Perfect phrases-for-the-toefl-speaking-and-writing-sections.pdf'):
            texts=pages(root,path)
            # Sample prompts are genuine exercises. Preparation notes and sample responses are hidden.
            sample_starts=[i for i,t in enumerate(texts) if re.search(r'\d\s*\.\s*Sample\s+Prompt\s+with\s+(?:Response|Essay)',t)]
            for ordinal,i in enumerate(sample_starts,1):
                end=next((n for n in sample_starts if n>i),min(i+5,len(texts)))
                block='\n'.join(texts[i:end])
                block=re.sub(r'^.*?Sample\s+Prompt\s+with\s+(?:Response|Essay)','',block,count=1,flags=re.S).strip()
                block=re.split(r'Preparation Notes|Here is a sample (?:response|essay)|Sample Essay',block,flags=re.I)[0]
                if len(block)<40:continue
                section='Speaking' if i<60 else 'Writing'
                add(resource,'sample-'+str(ordinal),i+1,section,'oral_activity' if section=='Speaking' else 'essay',block,textPrompt=section=='Speaking',seconds=60 if section=='Speaking' else 1200)
            # Explicit grammar exercises, bounded before printed answers or the next topic.
            regions=[(109,110),(115,116),(116,118),(122,124),(124,125),(126,127),(127,128),(133,135),(140,141),(142,145),(147,148),(149,151),(153,154),(157,158),(159,161),(167,168),(174,175)]
            for ordinal,(first,last) in enumerate(regions,1):
                block='\n'.join(texts[first-1:last])
                marker=re.search(r'(?m)^.*(?:Exercise(?:\s*\d)?|(?:Grammar|Punctuation) (?:Pretest|Posttest))\s*$',block)
                if not marker:continue
                block=block[marker.start():]
                pieces=re.split(r'(?im)^(?:Here are some possible[^\n]*|Answers may vary[^\n]*|Corrections are in BOLD[^\n]*|[^\n]*(?:Exercise(?:\s*\d+)? Answers|Exercise(?:\s*\d+)? Answer Key|Answer Key|Answers/Explanations|Pretest Answers|Posttest Answers)[^\n]*)$',block,maxsplit=1)
                block=pieces[0].strip()
                # A header that says "corrections for Exercise" is an answer, not a task.
                if re.match(r'(?i).*corrections for Exercise',block):continue
                add(resource,'grammar-'+str(ordinal),first,'Writing','worksheet',block,answerGuide=pieces[1].strip() if len(pieces)>1 else '',sourcePageEnd=last,seconds=600)
        elif path.endswith('Chamorro- Speaking Template.pdf'):
            texts=pages(root,path)
            first=texts[0]
            match=re.search(r'Ejemplos de preguntas\s*:?',first)
            if match:
                block=first[match.end():]
                block=re.split(r'Template|Plantilla|Estructura',block,flags=re.I)[0]
                for n,q in enumerate(re.split(r'(?m)^[-•]\s*',block)[1:],1):
                    if len(q.split())>=8:add(resource,n,1,'Speaking','interview',q,textPrompt=True)
        elif path.endswith('iBT- Speaking-plan.pdf'):
            texts=pages(root,path)
            for q in numbered_pages(texts,6,6):add(resource,'lesson1-'+str(q['number']),6,'Speaking','interview',q['text'],textPrompt=True)
            repeat=texts[7].split('Repeat only once.',1)[1].split('Part 2.',1)[0]
            for n,line in enumerate(repeat.splitlines(),1):
                if line.strip():add(resource,'repeat-'+str(n),8,'Speaking','repeat','Listen and repeat exactly what you hear.',reference=line.strip(),ttsText=line.strip(),seconds=12,groupId=resource['id']+'-repeat',edition='2026')
            tip=texts[15].split('II. Student Conversation',1)[0]
            for q in numbered_pages([tip]):add(resource,'lesson4-'+str(q['number']),16,'Speaking','interview',q['text'].split('a) Answer the questions',1)[0],textPrompt=True)
            # Whole listening activities keep the table and original context together.
            for first,last,script_first,script_last in [(16,17,19,20),(24,25,27,28)]:
                block='\n'.join(texts[first-1:last])
                start=re.search(r'(?:II\. Student Conversation|Part 2: Listening)',block)
                block=block[start.start():] if start else block
                block=re.split(r'III\. Asking|Part 3:',block)[0]
                script='\n'.join(texts[script_first-1:script_last]).split('NARRATOR:',1)[-1]
                add(resource,'listen-'+str(first),first,'Listening','worksheet',block,ttsText=script,answerGuide=texts[20] if first==16 else script,groupId=resource['id']+'-listen-'+str(first),seconds=600)
            for page in (24,26):
                block=texts[page-1].split('Part 2:',1)[0] if page==24 else texts[page-1]
                add(resource,'activity-'+str(page),page,'Speaking','oral_activity',block,textPrompt=True,sourceImagePage=page,seconds=90)
        count=len(extra)-before
        if count:coverage.append({'path':path,'sourceId':resource['id'],'exerciseCards':count})
    manual=out/'extra-source.json'
    if manual.exists():
        for exercise in json.loads(manual.read_text(encoding='utf-8')):
            source=next((r for r in resources if r['path']==exercise.get('sourcePath')),None)
            if source:
                exercise['sourceId']=source['id'];extra.append(exercise)
    return extra,coverage
