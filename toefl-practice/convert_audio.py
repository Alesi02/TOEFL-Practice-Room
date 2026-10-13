"""Convert every saved Speaking recording into isolated, source-linked prompts."""
from pathlib import Path
import sys,json,re,time,wave
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'.deps'))
from faster_whisper import WhisperModel,BatchedInferencePipeline
from faster_whisper.audio import decode_audio
import numpy as np

def word_groups(words,gap):
    groups=[]
    for word in words:
        if not groups or word['start']-groups[-1][-1]['end']>gap:
            groups.append([])
        groups[-1].append(word)
    return groups

def energy_spans(samples):
    frames=samples[:len(samples)//320*320].reshape(-1,320)
    rms=np.sqrt(np.mean(frames*frames,axis=1))
    active=np.flatnonzero(rms>max(.001,float(np.max(rms))*.04))
    groups=np.split(active,np.where(np.diff(active)>35)[0]+1)
    spans=[]
    for group in groups:
        if not len(group):continue
        start=max(0,float(group[0])*.02-.2);end=min(len(samples)/16000,float(group[-1])*.02+.3)
        if end-start<.9:continue
        for left in np.arange(start,end,27):
            spans.append({'start':float(left),'end':min(float(left)+27,end)})
    return spans

def prompts(record,kind):
    words=[w for s in record['segments'] for w in s.get('words',[])]
    begin=next((i for i,w in enumerate(words) if 'begin' in w['word'].lower()),None)
    # The source files begin with spoken test instructions; never make these questions.
    if begin is not None and words[begin]['end']<50:
        words=words[begin+1:]
    else:
        words=[w for w in words if w['start']>=23]
    result=[]
    for group in word_groups(words,5 if kind=='repeat' else 20):
        text=''.join(w['word'] for w in group).strip()
        if re.search(r'advanced practice video|you may pause or skip|longer sentences.*next video',text,re.I):
            continue
        if re.search(r'sample answers?|model answers?|this concludes|you (?:have |\x27ve )?completed',text,re.I):
            break
        if re.search(r'(?:this concludes|end of (?:the |your )?(?:test|practice|task)|thanks for (?:watching|practicing)|subscribe|great job completing)',text,re.I):
            continue
        if len(text.split())<3 or group[-1]['end']-group[0]['start']>55:
            continue
        result.append({'text':text,'start':max(0,group[0]['start']-.45),'end':min(record['duration'],group[-1]['end']+.25)})
    return result

def main():
    catalog=json.loads((BASE/'data/catalog.json').read_text(encoding='utf-8'))
    tracks=[r for r in catalog['resources'] if r['kind']=='audio' and r['section']=='Speaking']
    cache=BASE/'data/audio-import-cache';cache.mkdir(exist_ok=True)
    output=BASE/'cache/imported-prompts';output.mkdir(exist_ok=True)
    pipeline=None;exercises=[];coverage=[];started=time.time()
    for index,resource in enumerate(tracks,1):
        path=cache/(resource['id']+'.json')
        samples=decode_audio(str(BASE.parent/resource['path']))
        if path.exists():
            record=json.loads(path.read_text(encoding='utf-8'))
        else:
            if pipeline is None:
                pipeline=BatchedInferencePipeline(WhisperModel(str(BASE/'models/whisper-base.en'),device='cpu',compute_type='int8',cpu_threads=6,local_files_only=True))
            segments,_=pipeline.transcribe(samples,language='en',beam_size=1,batch_size=8,word_timestamps=True,vad_filter=True,vad_parameters={'min_silence_duration_ms':500})
            record={'sourceId':resource['id'],'duration':len(samples)/16000,'segments':[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in (s.words or [])]} for s in segments]}
            path.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
        kind='repeat' if re.search(r'Task\s*1|Listen.*Repeat',resource['title'],re.I) else 'interview'
        selected=prompts(record,kind)
        expected_group=7 if kind=='repeat' else 4
        if not selected or len(selected)%expected_group!=0:
            if pipeline is None:
                pipeline=BatchedInferencePipeline(WhisperModel(str(BASE/'models/whisper-base.en'),device='cpu',compute_type='int8',cpu_threads=6,local_files_only=True))
            segments,_=pipeline.transcribe(samples,language='en',beam_size=3,batch_size=8,word_timestamps=True,vad_filter=False,clip_timestamps=energy_spans(samples))
            repaired={'sourceId':resource['id'],'duration':len(samples)/16000,'segments':[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in (s.words or [])]} for s in segments]}
            alternatives=prompts(repaired,kind)
            if len(alternatives)>len(selected) or (alternatives and len(alternatives)%expected_group==0 and len(selected)%expected_group!=0):
                record=repaired;selected=alternatives
                path.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
        for n,clip in enumerate(selected,1):
            identifier='audio-'+resource['id']+'-'+str(n)
            target=output/(identifier+'.wav')
            with wave.open(str(target),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
                chunk=samples[int(clip['start']*16000):int(clip['end']*16000)]
                audio.writeframes((np.clip(chunk,-1,1)*32767).astype('<i2').tobytes())
            exercises.append({'id':identifier,'section':'Speaking','type':kind,'title':resource['title']+' · prompt '+str(n),'sourceId':resource['id'],'sourceStart':round(clip['start'],2),'sourceEnd':round(clip['end'],2),'audio':target.relative_to(BASE.parent).as_posix(),'prompt':'Listen carefully and repeat exactly what you hear.' if kind=='repeat' else clip['text'],'reference':clip['text'] if kind=='repeat' else '', 'seconds':12 if kind=='repeat' else 45,'preparationSeconds':0,'groupId':'audio-'+resource['id']+'-'+str((n-1)//expected_group),'edition':'2026','origin':'recording','referenceMethod':'machine-transcribed source recording','transcriptVerified':False,'simulationEligible':len(selected)%expected_group==0,'questionCount':1})
        coverage.append({'sourceId':resource['id'],'path':resource['path'],'prompts':len(selected),'expectedGroup':expected_group,'needsReview':not selected or len(selected)%expected_group!=0})
        (BASE/'data/audio-exercises.json').write_text(json.dumps({'exercises':exercises,'coverage':coverage},ensure_ascii=False),encoding='utf-8')
        print(f'Audio {index}/{len(tracks)}: {len(selected)} prompts; {len(exercises)} total; {round(time.time()-started)} seconds elapsed.',flush=True)
    print('All saved recordings processed.',flush=True)

if __name__=='__main__':main()
