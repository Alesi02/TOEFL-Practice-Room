'use strict';
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const typeName = {mcq:'Choose an answer',complete_words:'Complete the Words',sentence:'Build a Sentence',email:'Write an Email',discussion:'Academic Discussion',repeat:'Listen and Repeat',interview:'Take an Interview'};
Object.assign(typeName,{essay:'Essay practice',worksheet:'Workbook exercise',oral_activity:'Speaking activity'});
let practicePool='toefl2026';
const descriptions = {Reading:'Complete words, read everyday texts, and work through academic passages.',Listening:'Follow short responses, conversations, announcements, and academic talks.',Writing:'Build sentences, write a purposeful email, and contribute to a discussion.',Speaking:'Repeat sentences accurately and answer interview questions with confidence.'};
const baseTimes = {Reading:30,Listening:29,Writing:23,Speaking:8};
const icons = {Reading:'Aa',Listening:'♫',Writing:'✎',Speaking:'◉'};
let catalog, exercises, resources, health, currentView='practice', selectedSection='Speaking', session=null, interval=null, stream=null, recorder=null, playback=null, advancing=false;
let studioResource='', studioDuration=0, selectedChunks=[];
const content = $('#content');
const DRAFT_KEY = 'toefl-practice-draft-v1';
const REMOVED_RESULT_KEY = 'toefl-last-removed-result';

async function api(path, data) {
  const r = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const value = await r.json();
  if (!r.ok) throw new Error(value.error || 'Request failed');
  return value;
}
function toast(message) { $('#toast').textContent=message; $('#toast').style.display='block'; clearTimeout(toast.timeout); toast.timeout=setTimeout(()=>$('#toast').style.display='none',6500); }
function mediaUrl(source) { return '/api/media?source='+encodeURIComponent(source); }
function formatTime(seconds) { seconds=Math.max(0,Math.ceil(seconds)); return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`; }
function sourceLink(e) { const r=resources[e.sourceId]; return r?.path ? `<a href="${mediaUrl(r.path)}${e.sourcePage?'#page='+e.sourcePage:''}" target="_blank" rel="noreferrer">Original resource${e.sourcePage?' · page '+e.sourcePage:''} ↗</a>` : r ? `Source: ${esc(r.title)}` : ''; }
function loading(message) { content.innerHTML=`<div class="loading"><div class="spinner"></div><h2>${esc(message)}</h2><p class="small" id="job-message">Working on this computer.</p></div>`; }
async function waitJob(id) {
  for (;;) {
    const job=await api('/api/jobs/'+id);
    if ($('#job-message')) $('#job-message').textContent=job.message || 'Working locally';
    if (job.status==='done') return job.result;
    if (job.status==='error') throw new Error(job.error);
    await new Promise(r=>setTimeout(r,1000));
  }
}
function usable(e) { return !['Listening','Speaking'].includes(e.section) || Boolean(e.audio)||Boolean(e.textPrompt); }
function inPracticePool(e){return e.practiceCategory===practicePool;}
function setNav(view) { $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.view===view)); }
async function navigate(view) {
  if (session) { toast('Finish or save this session before switching views.'); return; }
  currentView=view; setNav(view);
  if(view==='practice') renderPractice();
  if(view==='tests') renderTests();
  if(view==='studio') renderStudio();
  if(view==='resources') renderResources();
  if(view==='history') await renderHistory();
}
function hero(eyebrow,title,subtitle,aside='') { return `<div class="hero"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="lead">${subtitle}</p></div>${aside}</div>`; }
function resumeBanner() {
  try { const d=JSON.parse(localStorage.getItem(DRAFT_KEY)); if(d) return `<div class="resume"><span>You have a saved session: ${esc(d.title)}.</span><div><button class="button" id="resume-session">Resume</button> <button class="text-button" id="discard-draft">Discard</button></div></div>`; } catch{}
  return '';
}
function bindResume() {
  $('#resume-session')?.addEventListener('click',resumeSession);
  $('#discard-draft')?.addEventListener('click',()=>{localStorage.removeItem(DRAFT_KEY);renderPractice();});
}
function renderPractice() {
  const total=catalog.exercises.filter(usable).length;
  content.innerHTML=hero('A LITTLE PRACTICE, EVERY DAY','Make room for progress.','Choose a section, practise under a timer, and turn your mistakes into your next practice session.',`<div class="hero-note"><strong>${total}</strong><span>exercises from your resources</span></div>`)+resumeBanner()+
    `<div class="grid">${['Reading','Listening','Writing','Speaking'].map(section=>`<article class="section-card ${selectedSection===section?'selected':''}" data-section="${section}"><div class="section-top"><span class="section-symbol">${icons[section]}</span><span class="section-meta">${baseTimes[section]} min · full section</span></div><h2>${section}</h2><p>${descriptions[section]}</p><div class="section-bottom"><span>${catalog.exercises.filter(e=>e.section===section&&usable(e)&&inPracticePool(e)).length} exercises available</span><button data-choose="${section}">Choose section →</button></div></article>`).join('')}</div>`+
    `<div class="panel" style="margin-top:22px"><h3>Your practice session</h3><div class="practice-options"><div class="field"><label for="task-type">TASK</label><select id="task-type"><option value="all">Mixed ${selectedSection.toLowerCase()} practice</option>${[...new Set(catalog.exercises.filter(e=>e.section===selectedSection&&usable(e)).map(e=>e.type))].map(t=>`<option value="${t}">${typeName[t]}</option>`).join('')}</select></div><div class="field"><label for="set-size">SET SIZE</label><select id="set-size"><option value="short">Short set</option><option value="section">Full section practice</option><option value="single">One exercise</option></select></div><div class="field"><label for="practice-mode">MODE</label><select id="practice-mode"><option value="timed">Timed · one attempt</option><option value="coach">Coaching · replay & pause</option></select></div><button class="button primary large" id="start-practice">Start practice →</button></div><p class="mode-note">Timed mode hides answers until the end. Full-section timers follow the 2026 base times; short-set timers are practice budgets. Source PDFs cannot reproduce the test's adaptive routing.</p></div>`+
    `<div class="practice-tip"><span>↗</span><div><h3>Give Speaking a little space every day.</h3><p>Try seven repetition sentences and four interview questions. Review your first attempt before recording an improved version.</p></div></div>`;
  $('#task-type').closest('.field').insertAdjacentHTML('beforebegin','<div class="field"><label for="exercise-pool">MATERIAL</label><select id="exercise-pool"><option value="toefl2026">TOEFL 2026 PRACTICE</option><option value="extra">Extra</option></select></div>');
  $('#exercise-pool').value=practicePool;
  $('#exercise-pool').onchange=()=>{practicePool=$('#exercise-pool').value;renderPractice();};
  $('#task-type').innerHTML='<option value="all">Mixed '+selectedSection.toLowerCase()+' practice</option>'+[...new Set(catalog.exercises.filter(e=>e.section===selectedSection&&usable(e)&&inPracticePool(e)).map(e=>e.type))].map(t=>`<option value="${t}">${typeName[t]}</option>`).join('');
  content.insertAdjacentHTML('beforeend','<p class="small">Extra includes essays, workbooks, older task formats, and other activities. Synthesized prompts and machine-transcribed references are labeled. Random and prepared tests use TOEFL 2026 tasks only.</p>');
  $$('[data-choose]').forEach(b=>b.onclick=()=>{selectedSection=b.dataset.choose;renderPractice();});
  $('#start-practice').onclick=()=>startPractice().catch(showStartError);
  bindResume();
  if(!total)content.insertAdjacentHTML('afterbegin','<div class="warning">Add your own authorized practice materials to this app folder, then run Import exercises.cmd. The public download includes app code only.</div>');
}
function shuffle(values) { return [...values].sort(()=>Math.random()-.5); }
function freshGroup(list, count) {
  const groups=[...new Set(list.map(x=>x.groupId||x.id))];
  if(!groups.length)return [];
  const chosen=groups[Math.floor(Math.random()*groups.length)];
  return list.filter(x=>(x.groupId||x.id)===chosen).slice(0,count);
}
function practiceSelection(section,type,size) {
  let list=catalog.exercises.filter(e=>e.section===section&&usable(e)&&inPracticePool(e)&&(!e.id.startsWith('clip-'))&&(type==='all'||e.type===type));
  // Prefer banks over rehearsal materials, keeping full tests fresh.
  const banks=list.filter(e=>!e.testId); if(banks.length)list=banks;
  if(section==='Speaking') {
    if(type==='oral_activity')return shuffle(list).slice(0,size==='single'?1:3);
    if(type==='repeat')return freshGroup(list, size==='single'?1:7);
    if(type==='interview')return freshGroup(list, size==='single'?1:4);
    const chosen=[...freshGroup(list.filter(e=>e.type==='repeat'),7),...freshGroup(list.filter(e=>e.type==='interview'),4)];
    return chosen.length?chosen:shuffle(list).slice(0,size==='single'?1:3);
  }
  if(section==='Writing') {
    if(type==='all')return [...shuffle(list.filter(e=>e.type==='sentence')).slice(0,size==='short'?5:10),...shuffle(list.filter(e=>e.type==='email')).slice(0,1),...shuffle(list.filter(e=>e.type==='discussion')).slice(0,1),...shuffle(list.filter(e=>['essay','worksheet'].includes(e.type))).slice(0,1)];
    return shuffle(list).slice(0,size==='single'||['email','discussion'].includes(type)?1:10);
  }
  if(section==='Listening') {
    const groups=shuffle([...new Set(list.map(x=>x.groupId||x.id))]);
    const picked=[]; const target=size==='single'?1:size==='section'?47:10;
    for(const g of groups) {picked.push(...list.filter(x=>(x.groupId||x.id)===g));if(picked.length>=target)break;}
    return picked;
  }
  const picked=[];const limit=size==='single'?1:size==='section'?50:10;
  const groups=shuffle([...new Set(list.map(e=>e.groupId||e.id))]);
  for(const g of groups) {picked.push(...list.filter(e=>(e.groupId||e.id)===g));if(picked.reduce((s,e)=>s+(e.questionCount||1),0)>=limit)break;}
  return picked;
}
function makeBlocks(items, full=false) {
  const blocks=[];
  for(const section of ['Reading','Listening','Writing','Speaking']) {
    const list=items.filter(e=>e.section===section);if(!list.length)continue;
    if(section==='Writing') {
      for(const type of ['sentence','email','discussion','essay','worksheet']) {
        const subset=list.filter(e=>e.type===type);if(!subset.length)continue;
        if(type==='sentence')blocks.push({section,type,label:'Build a Sentence',ids:subset.map(e=>e.id),seconds:full?360:Math.min(360,subset.length*36)});
        else for(const e of subset)blocks.push({section,type,label:typeName[type],ids:[e.id],seconds:e.seconds||({email:420,discussion:600}[type])});
      }
    } else {
      const seconds=full?baseTimes[section]*60:section==='Speaking'?480:list.reduce((n,e)=>n+(e.seconds||60),0);
      blocks.push({section,label:section,ids:list.map(e=>e.id),seconds});
    }
  }
  return blocks;
}
async function startPractice() {
  const size=$('#set-size').value, type=$('#task-type').value;
  const items=practiceSelection(selectedSection,type,size);
  if(!items.length)throw new Error('No verified exercises are available for this selection.');
  await launchSession(makeBlocks(items,size==='section'),`${selectedSection} · ${type==='all'?'Mixed practice':typeName[type]}`,$('#practice-mode').value,'record');
}
function renderTests() {
  if(!catalog.tests.length){content.innerHTML=hero('YOUR TEST LIBRARY','Add your practice materials.','Prepared and randomized tests become available once you import enough verified exercises for all four sections.')+'<div class="panel"><p>Run Import exercises.cmd after adding supported PDFs and audio, or copy your own private exercise bundle into the app folder.</p><button class="button" id="view-materials">View resources →</button></div>';$('#view-materials').onclick=()=>navigate('resources');return;}
  content.innerHTML=hero('REHEARSE THE WHOLE EXPERIENCE','Build your test-day rhythm.','Work through Reading, Listening, Writing, and Speaking in order. Your answers stay hidden until the review.')+
    `<div class="panel test-card"><div class="test-layout"><div><div class="eyebrow">A FRESH COMBINATION</div><h2>Randomized full test</h2><p class="lead" style="font-size:12px">A new mix from your verified exercises: 50 Reading points, 47 Listening questions, 12 Writing items, and 11 Speaking responses.</p></div><button class="button accent" id="random-test" ${catalog.tests.some(t=>t.prepared)?'':'disabled'}>Create random test →</button></div></div><div class="panel" style="margin-bottom:22px"><p class="mode-note">Source-based rehearsals use fixed questions and 2026 base timers. Reading and Listening are not adaptive. Exercises can recur across tests. Speaking uses original prompt audio with automatic response windows.</p></div><h2>${catalog.tests.filter(t=>t.prepared).length} prepared full tests</h2><p class="small">Each form keeps the same question selection when you return to it.</p><div class="prepared-grid">${catalog.tests.filter(t=>t.prepared).map(t=>`<article class="panel prepared-card"><div class="eyebrow">FORM ${esc(t.id.split('-').at(-1))}</div><h3>${esc(t.title)}</h3><p class="small">Reading · Listening<br>Writing · Speaking</p><button class="button" data-test="${esc(t.id)}">Start test →</button></article>`).join('')}</div><h2 style="margin-top:32px">Original source tests</h2>`+
    catalog.tests.filter(t=>!t.prepared).map(t=>{
      const counts=Object.entries(t.sections).map(([s,ids])=>`${s}: ${ids.reduce((n,id)=>n+(exercises[id]?.questionCount||1),0)}`);
      const missing=Object.entries(t.missingItemCounts||{}).filter(([s,n])=>n>0);
      return `<article class="panel test-card"><div class="test-layout"><div><span class="tag">${t.partial?'READING & WRITING':'2026 FORMAT'}</span><h2>${esc(t.title)}</h2><div class="test-parts">${counts.map(c=>`<span>${c}</span>`).join('')}</div><p class="small">${esc(t.description||'Original exercises and answer keys. Fixed section timers.')}</p>${missing.length?`<p class="small">Original audio unavailable: ${missing.map(([s,n])=>`${esc(s)} ${n}`).join(', ')}. Those items are kept as references.</p>`:''}</div><button class="button primary" data-test="${esc(t.id)}">${t.partial?'Begin paper practice':'Begin full test'} →</button></div></article>`;
    }).join('')+
    `<p class="mode-note">Writing has separate 6-, 7-, and 10-minute task timers. Repetition uses a 12-second practice cap; interview answers have 45 seconds. There is no pause button in timed mode. Prepared tests combine existing questions.</p>`;
  $$('[data-test]').forEach(b=>b.onclick=()=>{
    const test=catalog.tests.find(t=>t.id===b.dataset.test);
    startFullTest(test).catch(showStartError);
  });
  $('#random-test').onclick=async()=>{try{const test=await api('/api/random-test',{});await startFullTest(test);}catch(e){showStartError(e);}};
}
async function startFullTest(test){
  const responseMode='record';
  const items=['Reading','Listening','Writing','Speaking'].flatMap(s=>test.sections[s]||[]).map(id=>exercises[id]).filter(e=>e&&usable(e));
  await launchSession(makeBlocks(items,true),test.title,'timed',responseMode);
}
async function getMicrophone() {
  if(!navigator.mediaDevices?.getUserMedia)throw new Error('Microphone recording needs a browser with microphone support at this local address.');
  if(!window.MediaRecorder)throw new Error('This browser cannot record audio. Use Chrome or Edge with microphone support.');
  if(stream&&stream.getAudioTracks().some(t=>t.readyState==='live'))return;
  stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
}
function releaseMicrophone(){if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}}
async function launchSession(blocks,title,mode,responseMode) {
  responseMode='record';
  if(blocks.some(b=>b.section==='Speaking')&&responseMode==='record') {
    try{await getMicrophone();}catch(e){throw new Error('Microphone access was not granted. Allow microphone access to practise Speaking.');}
  }
  loading('Preparing your practice session');
  const ids=blocks.flatMap(b=>b.ids);
  const prepared=await api('/api/prepare',{ids});
  const ready=await waitJob(prepared.jobId);
  if(ready.failed.length){releaseMicrophone();throw new Error(`${ready.failed.length} audio files could not be prepared. Check your connection and retry. Cached exercises work offline.`);}
  session={title,mode,responseMode,blocks,block:0,index:0,answers:{},played:[],phase:'instructions',blockDeadline:null,itemDeadline:null,paused:false,started:Date.now(),itemStarted:null};
  saveDraft();setNav('');renderInstructions();
}
function showStartError(e) { releaseMicrophone();session=null;toast(e.message);navigate(currentView); }
function saveDraft() { if(session){try{localStorage.setItem(DRAFT_KEY,JSON.stringify(session));}catch{toast('The browser could not save your draft. Keep the session open.');}} }
async function resumeSession() {
  try {
    const d=JSON.parse(localStorage.getItem(DRAFT_KEY));if(!d)return;
    if(d.blocks.some(b=>b.section==='Speaking'))await getMicrophone();
    d.responseMode='record';session=d;session.paused=false;session.phase=session.phase==='instructions'?'instructions':'question';setNav('');
    if(session.block>=session.blocks.length){await finishSession();return;}
    if(session.phase==='instructions')renderInstructions();else{renderQuestion();startClock();}
  }catch(e){toast(e.message);}
}
function currentBlock(){return session.blocks[session.block];}
function currentExercise(){return exercises[currentBlock().ids[session.index]];}
function currentAnswer(){const e=currentExercise();return session.answers[e.id]||(session.answers[e.id]={id:e.id,response:''});}
function renderInstructions() {
  stopPlayback();clearInterval(interval);
  const b=currentBlock();
  content.innerHTML=`<div class="eyebrow">${esc(session.title)}</div><div class="panel"><span class="tag">${esc(b.section)}</span><h1 style="margin-top:18px">${esc(b.label)}</h1><p class="lead">${descriptions[b.section]}</p><div class="summary-strip"><div><strong>${formatTime(b.seconds)}</strong><small>TIME BUDGET</small></div><div><strong>${b.ids.length}</strong><small>EXERCISE CARDS</small></div></div><p class="small">${session.mode==='timed'?'The timer continues if you switch tabs. Answers and feedback appear at the end.':'You can pause and replay in coaching mode.'} ${b.section==='Speaking'?'Each response window begins after the prompt audio ends.':''}</p><div class="session-actions"><button class="button" id="save-exit">Save & leave</button><button class="button primary" id="begin-block">Begin ${esc(b.label)} →</button></div></div>`;
  $('#begin-block').onclick=()=>{session.blockDeadline=Date.now()+b.seconds*1000;session.phase='question';session.index=0;session.itemDeadline=null;renderQuestion();startClock();};
  $('#save-exit').onclick=saveAndLeave;
}
function renderQuestion() {
  const e=currentExercise(), b=currentBlock(), a=currentAnswer();selectedChunks=[];
  session.itemStarted=session.itemStarted||Date.now();
  const done=session.blocks.slice(0,session.block).reduce((n,b)=>n+b.ids.length,0)+session.index;
  const all=session.blocks.reduce((n,b)=>n+b.ids.length,0);
  const number=session.index+1;
  content.innerHTML=`<div class="session-top"><div><div class="eyebrow">${esc(b.section)} / ${esc(b.label)}</div><h2>${esc(typeName[e.type]||b.label)}</h2></div><div class="timer" id="timer"><small id="timer-label">${b.section==='Speaking'?'SECTION':'TIME REMAINING'}</small><strong id="timer-value">${formatTime((session.blockDeadline-Date.now())/1000)}</strong></div></div><div class="progress"><div style="width:${done/all*100}%"></div></div><div class="question-header"><span>Exercise ${number} of ${b.ids.length}</span><span>${session.mode==='timed'?'TIMED PRACTICE':'COACHING MODE'}</span></div><div class="panel question-panel" id="question-body"></div><div class="session-actions"><div>${session.mode==='coach'?'<button class="button" id="pause-session">Pause</button>':''}${['Reading','Writing'].includes(b.section)&&session.index>0?'<button class="button" id="previous-question">← Previous</button>':''}<button class="button" id="end-session">Finish & review</button></div><button class="button primary" id="next-question">${session.index===b.ids.length-1?'Complete task':'Next question'} →</button></div>`;
  const body=$('#question-body');
  if(e.type==='complete_words') {
    const slots=e.slots||[]; const values=Array.isArray(a.response)?a.response:[];
    const passage=esc(e.passage||'').replace(/\[(\d+):\s*_+\]/g,(whole,n)=>`<span class="gap-slot"><input class="gap-input" data-gap="${Number(n)-1}" aria-label="Missing letters for word ${n}" maxlength="${slots[Number(n)-1]?.length||30}" value="${esc(values[Number(n)-1]||'')}" autocomplete="off" spellcheck="false"><small>${n}</small></span>`);
    body.innerHTML=`<p class="small">${esc(e.prompt)}</p><div class="passage" style="max-height:none">${passage}</div>`;
    $$('[data-gap]').forEach(input=>input.oninput=()=>{const ans=currentAnswer();if(!Array.isArray(ans.response))ans.response=[];ans.response[Number(input.dataset.gap)]=input.value;saveDraft();});
  } else if(e.type==='mcq') {
    const question=`<div id="question-options"><p class="question-prompt">${esc(e.prompt)}</p>${(e.options||[]).map(o=>`<label class="option"><input type="radio" name="answer" value="${esc(o.key)}" ${a.response===o.key?'checked':''}><span><strong>${esc(o.key)}.</strong> ${esc(o.text)}</span></label>`).join('')}</div>`;
    if(b.section==='Listening'&&!session.played.includes(e.groupId||e.audio||e.id)) {
      body.innerHTML=audioStage('Listen carefully.','The questions will appear after the audio finishes.');
      bindPlay(e,()=>{session.played.push(e.groupId||e.audio||e.id);saveDraft();showListeningQuestion(question);});
      $('#next-question').disabled=true;
    }else if(b.section==='Reading'&&e.passage)body.innerHTML=`<div class="question-grid"><div class="passage">${esc(e.passage)}</div>${question}</div>`;
    else body.innerHTML=(b.section==='Listening'&&session.mode==='coach'?`<button class="button" id="replay-audio">Replay audio</button>`:'')+question;
    bindOptions();
    $('#replay-audio')?.addEventListener('click',()=>playAudio(e,()=>{}));
  } else if(e.type==='sentence') {
    renderSentenceBuilder(e,a,body);
  } else if(['email','discussion','essay','worksheet'].includes(e.type)) {
    if(b.section==='Listening'&&!session.played.includes(e.groupId||e.id)){
      body.innerHTML=audioStage('Listen to the source script.','Then complete the original workbook activity.');
      bindPlay(e,()=>{session.played.push(e.groupId||e.id);renderQuestion();});
      $('#next-question').disabled=true;
      return;
    }
    const exercisePrompt=e.type==='worksheet'&&!resources[e.sourceId]?.path?e.prompt.replace('Of the four underlined choices, one is a pronoun error.','Find the pronoun error in each sentence.'):e.prompt;
    body.innerHTML=`<div class="question-grid"><div><p class="question-prompt" style="font-size:14px">${esc(exercisePrompt)}</p>${e.passage?`<div class="passage">${esc(e.passage)}</div>`:''}</div><div><label class="sr-only" for="writing-response">Your response</label><textarea class="response" id="writing-response" spellcheck="false" autocomplete="off">${esc(a.response)}</textarea><div class="response-footer"><span id="word-count">${countWords(a.response)} words</span><span>Write in complete sentences.</span></div></div></div>`;
    if(e.type==='worksheet')$('.response-footer span:last-child').textContent='Enter numbered answers. For marking activities, list the selected words and corrections.';
    $('#writing-response').oninput=()=>{a.response=$('#writing-response').value;$('#word-count').textContent=countWords(a.response)+' words';saveDraft();};
  } else if(['repeat','interview','oral_activity'].includes(e.type)) {
    if(a.recording||session.phase==='answered')renderRecorded(e,a);
    else {
      if(e.textPrompt){
        body.innerHTML=`<p class="question-prompt">${esc(e.prompt)}</p><p class="small">Extra exercise · ${e.seconds||45} seconds to respond</p>${e.sourceImagePage?`<p>${sourceLink(e)}</p>`:''}`;
        beginSpeakingResponse(e).catch(error=>toast(error.message));
      }else{
        body.innerHTML=audioStage(e.type==='repeat'?'Listen. Then repeat.':'Listen. Then answer.',`${e.seconds||45} seconds to respond · no preparation time`,true);
        playAudio(e,()=>beginSpeakingResponse(e)).catch(error=>toast(error.message));
      }
      $('#next-question').disabled=true;
    }
  }
  if(e.audioMethod||e.referenceMethod||e.simulationEligible===false){
    body.insertAdjacentHTML('afterbegin',`<p class="small">${esc(e.audioMethod||e.referenceMethod||(e.simulationEligible===false?'Extra exercise':''))}</p>`);
  }
  if((e.sourceImagePage||e.type==='worksheet')&&resources[e.sourceId]?.path){
    const start=e.sourceImagePage||e.sourcePage,end=e.sourcePageEnd||start;
    const pages=Array.from({length:end-start+1},(_,i)=>`<img loading="lazy" class="source-page" alt="Original exercise page ${start+i}" src="/api/source-page?sourceId=${encodeURIComponent(e.sourceId)}&page=${start+i}" style="width:100%;object-fit:contain">`).join('');
    body.insertAdjacentHTML('afterbegin',e.type==='worksheet'?`<details><summary>View original exercise pages and formatting</summary>${pages}</details>`:pages);
  }
  if(e.exerciseImage)body.insertAdjacentHTML('afterbegin',`<img class="source-page" alt="Exercise illustration" src="${mediaUrl(e.exerciseImage)}" style="max-width:100%">`);
  $('#next-question').onclick=()=>nextQuestion().catch(e=>toast(e.message));
  $('#previous-question')?.addEventListener('click',()=>{stopPlayback();session.index--;session.itemStarted=null;session.phase='question';renderQuestion();saveDraft();});
  $('#pause-session')?.addEventListener('click',togglePause);
  $('#end-session').onclick=()=>finishSession().catch(e=>toast(e.message));
  saveDraft();tick();
}
function countWords(v){return String(v||'').trim().split(/\s+/).filter(Boolean).length;}
function renderSentenceBuilder(exercise,answer,body){
  const chunks=exercise.chunks||[],slotCount=(exercise.template||'').match(/_+/g)?.length||chunks.length;
  if(!Array.isArray(answer.sentenceSlots)||answer.sentenceSlots.length!==slotCount)answer.sentenceSlots=Array(slotCount).fill(null);
  let grabbed=null;
  function move(chunk,target){
    if(!Number.isInteger(chunk)||chunk<0||chunk>=chunks.length)return;
    const from=answer.sentenceSlots.indexOf(chunk),displaced=target===null?null:answer.sentenceSlots[target];
    if(from>=0)answer.sentenceSlots[from]=null;
    if(target!==null){answer.sentenceSlots[target]=chunk;if(from>=0&&displaced!==null&&displaced!==chunk)answer.sentenceSlots[from]=displaced;}
    update();saveDraft();
  }
  function tile(index){return `<span class="sentence-tile" draggable="false" role="button" tabindex="0" data-word="${index}" aria-label="Drag ${esc(chunks[index])}">${esc(chunks[index])}</span>`;}
  function update(){
    let index=0;
    const slot=()=>{const n=index++;return `<span class="sentence-drop" data-slot="${n}" tabindex="0" aria-label="Blank ${n+1}${answer.sentenceSlots[n]===null?', empty':', '+esc(chunks[answer.sentenceSlots[n]])}">${answer.sentenceSlots[n]===null?'<span class="slot-placeholder">'+(n+1)+'</span>':tile(answer.sentenceSlots[n])}</span>`;};
    const template=exercise.template?esc(exercise.template).replace(/_+/g,slot):Array.from({length:slotCount},slot).join(' ');
    body.innerHTML=`<p class="question-prompt">${esc(exercise.context||exercise.prompt.split('\n')[0])}</p><p class="small">Drag each word or phrase into its blank. Drag it back to the word bank to remove it.</p><div class="sentence-layout" id="sentence-target">${template}</div><div class="sentence-bank" id="sentence-bank" aria-label="Word bank">${chunks.map((_,i)=>answer.sentenceSlots.includes(i)?'':tile(i)).join('')}</div><p class="small">Keyboard: focus a word and press Space, then focus a blank and press Enter.</p><button class="text-button" id="clear-chunks">Clear sentence</button><span class="sr-only" aria-live="polite" id="sentence-live"></span>`;
    let filled=0;
    answer.response=exercise.template?exercise.template.replace(/_+/g,()=>answer.sentenceSlots[filled]===null?(filled++,'_____'):chunks[answer.sentenceSlots[filled++]]):answer.sentenceSlots.map(n=>n===null?'_____':chunks[n]).join(' ');
    $$('[data-word]',body).forEach(word=>{
      word.onpointerdown=event=>{
        if(event.button!==0)return;
        const pointer=event.pointerId,startX=event.clientX,startY=event.clientY;let moved=false,ghost=null;
        word.setPointerCapture(pointer);word.focus();
        function cleanup(){ghost?.remove();$$('.drag-over',body).forEach(el=>el.classList.remove('drag-over'));word.onpointermove=null;word.onpointerup=null;word.onpointercancel=null;if(word.hasPointerCapture(pointer))word.releasePointerCapture(pointer);}
        word.onpointermove=ev=>{
          if(!moved&&Math.hypot(ev.clientX-startX,ev.clientY-startY)<5)return;
          moved=true;ev.preventDefault();
          if(!ghost){ghost=document.createElement('span');ghost.className='sentence-tile sentence-ghost';ghost.textContent=chunks[Number(word.dataset.word)];document.body.append(ghost);}
          ghost.style.left=(ev.clientX+12)+'px';ghost.style.top=(ev.clientY+12)+'px';
          $$('.drag-over',body).forEach(el=>el.classList.remove('drag-over'));
          document.elementFromPoint(ev.clientX,ev.clientY)?.closest('[data-slot]')?.classList.add('drag-over');
        };
        word.onpointerup=ev=>{const target=document.elementFromPoint(ev.clientX,ev.clientY),blank=target?.closest('[data-slot]'),bank=target?.closest('#sentence-bank');cleanup();if(moved&&(blank||bank))move(Number(word.dataset.word),blank?Number(blank.dataset.slot):null);};
        word.onpointercancel=cleanup;
      };
      word.ondragstart=event=>{grabbed=Number(word.dataset.word);event.dataTransfer.setData('text/plain',String(grabbed));event.dataTransfer.effectAllowed='move';};
      word.onkeydown=event=>{if(event.code==='Space'){event.preventDefault();grabbed=Number(word.dataset.word);$('#sentence-live').textContent='Word selected. Focus the target blank and press Enter.';}};
    });
    $$('[data-slot]',body).forEach(blank=>{
      blank.ondragover=event=>{event.preventDefault();blank.classList.add('drag-over');};
      blank.ondragleave=()=>blank.classList.remove('drag-over');
      blank.ondrop=event=>{event.preventDefault();event.stopPropagation();const n=Number(event.dataTransfer.getData('text/plain'));if(event.dataTransfer.getData('text/plain')!=='')move(n,Number(blank.dataset.slot));};
      blank.onkeydown=event=>{if(event.key==='Enter'&&grabbed!==null){event.preventDefault();move(grabbed,Number(blank.dataset.slot));grabbed=null;}};
    });
    const bank=$('#sentence-bank');bank.ondragover=event=>event.preventDefault();bank.ondrop=event=>{event.preventDefault();const text=event.dataTransfer.getData('text/plain');if(text!=='')move(Number(text),null);};
    $('#clear-chunks').onclick=()=>{answer.sentenceSlots.fill(null);update();saveDraft();};
  }
  update();
}
function bindOptions(){$$('input[name="answer"]').forEach(r=>r.onchange=()=>{currentAnswer().response=r.value;saveDraft();});}
function showListeningQuestion(question){$('#question-body').innerHTML=(session.mode==='coach'?'<button class="button" id="replay-audio">Replay audio</button>':'')+question;bindOptions();$('#next-question').disabled=false;$('#replay-audio')?.addEventListener('click',()=>playAudio(currentExercise(),()=>{}));}
function audioStage(title,subtitle,automatic=false){return `<div class="audio-stage"><div class="audio-orb">♫</div><h3>${title}</h3><p>${subtitle}</p><div class="audio-status" id="audio-status">${automatic?'<p>The prompt starts automatically.</p>':'<button class="button primary" id="play-prompt">Play prompt & begin →</button>'}</div></div>`;}
function bindPlay(e,after){$('#play-prompt').onclick=()=>playAudio(e,after).catch(error=>{toast(error.message);if($('#audio-status'))$('#audio-status').innerHTML='<button class="button" id="play-prompt">Retry prompt audio</button>';bindPlay(e,after);});}
function stopPlayback(){if(playback){playback.onended=null;playback.pause();playback=null;}}
async function playAudio(e,after){
  if(!e.audio)throw new Error('The original audio for this exercise is unavailable. Open its source in Resources.');
  stopPlayback();playback=new Audio(mediaUrl(e.audio));
  if($('#audio-status'))$('#audio-status').innerHTML='<p>Listening to the prompt…</p>';
  playback.onended=()=>{playback=null;after();};
  playback.onerror=()=>{toast('The prompt audio could not play. Retry or check the source.');if($('#audio-status')){$('#audio-status').innerHTML='<button class="button" id="play-prompt">Retry prompt audio</button>';bindPlay(e,after);}};
  await playback.play();
}
async function beginSpeakingResponse(e){
  session.phase='responding';session.itemDeadline=Date.now()+(e.seconds||45)*1000;
  if($('#timer-label'))$('#timer-label').textContent='RESPONSE WINDOW';
  $('#question-body').innerHTML=`<div class="audio-stage"><div class="audio-orb recording">●</div><h3>Your microphone is recording.</h3>${e.textPrompt?`<p class="question-prompt">${esc(e.prompt)}</p>`:''}<p>${e.type==='repeat'?'Repeat exactly what you heard.':'Answer the interviewer clearly, with relevant details.'}</p><p class="small">Your recording will stop automatically when time runs out.</p><button class="button" id="finish-response">Finish response</button></div>`;
  $('#next-question').disabled=true;
  $('#finish-response').onclick=()=>completeSpeakingResponse().catch(error=>toast(error.message));
  {
    try{
      await getMicrophone();
      const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
      recorder=new MediaRecorder(stream,mime?{mimeType:mime}:{});
      recorder.chunks=[];recorder.ondataavailable=event=>{if(event.data.size)recorder.chunks.push(event.data);};recorder.start(250);
    }catch(error){session.itemDeadline=null;session.phase='question';toast('Recording could not start. Allow microphone access and retry the prompt.');renderQuestion();return;}
  }
  saveDraft();tick();
}
async function stopRecording(){
  if(!recorder)return null;
  const active=recorder;recorder=null;
  const blob=await new Promise((resolve,reject)=>{active.onstop=()=>resolve(new Blob(active.chunks,{type:active.mimeType}));active.onerror=()=>reject(new Error('The recording failed'));if(active.state==='inactive')resolve(new Blob(active.chunks,{type:active.mimeType}));else active.stop();});
  if(!blob.size)throw new Error('The microphone produced an empty recording.');
  const ext=blob.type.includes('ogg')?'ogg':blob.type.includes('mp4')?'mp4':'webm';
  const r=await fetch('/api/recordings?ext='+ext,{method:'POST',body:blob});const result=await r.json();if(!r.ok)throw new Error(result.error);
  return result.id;
}
async function completeSpeakingResponse(){
  if(advancing||!session||session.phase!=='responding')return;
  advancing=true;
  try{
    session.phase='saving';session.itemDeadline=null;
    const a=currentAnswer();
    if($('#finish-response'))$('#finish-response').disabled=true;
    a.recording=await stopRecording();
    a.elapsed=(Date.now()-session.itemStarted)/1000;
    session.phase='answered';saveDraft();
    if(session.mode==='timed'){advancing=false;await nextQuestion();}
    else {renderRecorded(currentExercise(),a);$('#next-question').disabled=false;}
  }finally{advancing=false;}
}
function renderRecorded(e,a){
  if($('#timer-label'))$('#timer-label').textContent='SECTION';
  $('#question-body').innerHTML=`<div class="audio-stage"><div class="audio-orb">✓</div><h3>Response saved.</h3><p>Your feedback will appear when you finish the session.</p>${a.recording?`<audio controls src="/api/recordings/${esc(a.recording)}"></audio>`:`<p class="feedback-copy">${esc(a.response)}</p>`}${session.mode==='coach'?'<button class="button" id="retry-response">Try again</button>':''}</div>`;
  $('#next-question').disabled=false;
  $('#retry-response')?.addEventListener('click',()=>{session.answers[e.id]={id:e.id,response:''};session.phase='question';session.itemStarted=null;session.itemDeadline=null;renderQuestion();});
}
function startClock(){clearInterval(interval);interval=setInterval(tick,200);tick();}
function tick(){
  if(!session||session.phase==='instructions'||session.paused)return;
  const remaining=((session.itemDeadline||session.blockDeadline)-Date.now())/1000;
  if($('#timer-value'))$('#timer-value').textContent=formatTime(remaining);
  $('#timer')?.classList.toggle('urgent',remaining<=30);
  if(session.phase==='responding'&&remaining<=0){completeSpeakingResponse().catch(e=>toast(e.message));return;}
  if(session.blockDeadline&&Date.now()>=session.blockDeadline&&session.phase!=='saving'&&!advancing){expireBlock().catch(e=>toast(e.message));}
}
function togglePause(){
  if(session.phase==='responding'||recorder){toast('Finish your current recording before pausing.');return;}
  if(!session.paused){session.paused=true;session.pauseAt=Date.now();if(playback)playback.pause();$('#pause-session').textContent='Resume';}
  else {const delta=Date.now()-session.pauseAt;session.blockDeadline+=delta;if(session.itemDeadline)session.itemDeadline+=delta;session.paused=false;playback?.play();$('#pause-session').textContent='Pause';}
  saveDraft();
}
async function nextQuestion(){
  if(advancing)return;advancing=true;
  try{
    if(recorder){const id=await stopRecording();currentAnswer().recording=id;}
    stopPlayback();currentAnswer().elapsed=(Date.now()-session.itemStarted)/1000;
    session.index++;session.itemDeadline=null;session.itemStarted=null;session.phase='question';
    if(session.index>=currentBlock().ids.length)await nextBlock();else renderQuestion();
  }finally{advancing=false;}
}
async function expireBlock(){
  if(advancing)return;advancing=true;
  try{if(recorder)currentAnswer().recording=await stopRecording();stopPlayback();toast('Time is up. Your saved responses are preserved.');await nextBlock();}finally{advancing=false;}
}
async function nextBlock(){
  clearInterval(interval);session.block++;session.index=0;session.itemDeadline=null;session.itemStarted=null;session.blockDeadline=null;
  if(session.block>=session.blocks.length){await finishSession();return;}
  session.phase='instructions';saveDraft();renderInstructions();
}
async function saveAndLeave(){
  if(recorder)currentAnswer().recording=await stopRecording();stopPlayback();clearInterval(interval);saveDraft();releaseMicrophone();session=null;navigate('practice');toast('Session saved. Timed deadlines keep running.');
}
async function finishSession(){
  if(!session)return;
  clearInterval(interval);stopPlayback();
  if(recorder&&session.block<session.blocks.length)currentAnswer().recording=await stopRecording();
  const submitted=session;
  const items=submitted.blocks.flatMap(b=>b.ids).map(id=>submitted.answers[id]||{id,response:''});
  saveDraft();releaseMicrophone();loading('Reviewing your responses');
  try{
    const job=await api('/api/evaluate',{title:submitted.title,mode:submitted.mode,items});
    const result=await waitJob(job.jobId);session=null;localStorage.removeItem(DRAFT_KEY);setNav('history');currentView='history';renderResult(result);
  }catch(error){session=null;toast(error.message);renderPractice();}
}
function renderResources(){
  if(catalog.portableExercisesOnly){content.innerHTML=hero('YOUR EXERCISE LIBRARY','All exercises, ready to practise.','The original documents and full recordings are excluded from this compact edition.')+`<div class="panel">${catalog.resources.map(r=>`<div class="resource-row"><div><h3>${esc(r.title)}</h3><p>${esc(r.section)} · ${r.exerciseCount} exercises</p></div></div>`).join('')}</div>`;return;}
  content.innerHTML=hero('YOUR MATERIALS, IN ONE PLACE','A library that works with you.','All your original files remain available. Current exercises feed timed practice; older templates and books are study references.')+
    `<div class="resource-toolbar"><input id="resource-search" class="search" aria-label="Search resources" placeholder="Search your books, question banks, and recordings…"><select id="resource-section" class="search" aria-label="Filter section"><option value="all">All sections</option>${['Reading','Listening','Writing','Speaking','General'].map(s=>`<option>${s}</option>`).join('')}</select><select id="resource-kind" class="search" aria-label="Filter type"><option value="all">All file types</option><option value="audio">Audio</option><option value="pdf">PDF</option></select></div><div class="panel" id="resource-list"></div><details><summary>About the imported materials</summary><p class="small">${catalog.resources.length} original files are indexed. Exercises with verified answers are available in practice. Printed audio scripts without original recordings remain reference material. Use Audio studio to practise selected clips from full recordings. Older templates are available for study.</p>${(catalog.importReport?.warnings||[]).map(w=>`<p class="small">${esc(w)}</p>`).join('')}</details>`;
  function list(){
    const needle=$('#resource-search').value.toLowerCase(),section=$('#resource-section').value,kind=$('#resource-kind').value;
    const selected=catalog.resources.filter(r=>r.title.toLowerCase().includes(needle)&&(section==='all'||r.section===section)&&(kind==='all'||r.kind===kind));
    $('#resource-list').innerHTML=selected.length?selected.map(r=>`<div class="resource-row"><div><h3>${esc(r.title)}</h3><p><span class="tag ${r.edition==='2026'?'green':'muted'}">${r.edition==='2026'?'2026':'STUDY REFERENCE'}</span>${esc(r.section)} · ${esc(r.kind.toUpperCase())}${r.exerciseCount?' · '+r.exerciseCount+' imported exercises':''}</p></div><div class="resource-actions"><a class="button" href="${mediaUrl(r.path)}" target="_blank" rel="noreferrer">Open ↗</a>${r.kind==='audio'?`<button class="button" data-studio="${esc(r.id)}">Practise a clip</button>`:''}</div></div>`).join(''):'<div class="empty">No resources match these filters.</div>';
    $$('[data-studio]').forEach(b=>b.onclick=()=>{studioResource=b.dataset.studio;navigate('studio');});
  }
  $('#resource-search').oninput=list;$('#resource-section').onchange=list;$('#resource-kind').onchange=list;list();
}
function renderStudio(){
  if(catalog.portableExercisesOnly){content.innerHTML=hero('EXERCISES ONLY','Your prompts are already prepared.','All imported audio prompts are available in section practice. This compact edition excludes the long source recordings.');return;}
  const tracks=catalog.resources.filter(r=>r.kind==='audio');if(!studioResource)studioResource=tracks[0]?.id||'';
  content.innerHTML=hero('USE EVERY RECORDING','Turn an audio clip into practice.','Choose one sentence or one interview question from your saved recordings. The local speech engine prepares that clip as a timed prompt.')+
    `<div class="panel"><div class="field"><label for="studio-track">YOUR RECORDING</label><select id="studio-track">${tracks.map(r=>`<option value="${esc(r.id)}" ${r.id===studioResource?'selected':''}>${esc(r.title)}</option>`).join('')}</select></div><audio id="studio-player" controls preload="metadata" src="${mediaUrl(resources[studioResource]?.path||'')}"></audio><p class="small" id="studio-time">Play the recording and find the start and end of one prompt.</p><div class="studio-fields"><div class="field"><label for="clip-start">START · SECONDS</label><input id="clip-start" type="number" min="0" step="0.1" value="0"></div><button class="button" id="mark-start">Use current time</button><div class="field"><label for="clip-end">END · SECONDS</label><input id="clip-end" type="number" min="0.2" step="0.1" value="10"></div><button class="button" id="mark-end">Use current time</button><div class="field"><label for="clip-type">TASK</label><select id="clip-type"><option value="repeat">Listen and Repeat</option><option value="interview">Interview question</option></select></div></div><div class="practice-options"><button class="button" id="preview-clip">Preview selection</button><button class="button primary" id="create-clip">Create timed exercise →</button></div><p class="warning">Select only the prompt, without beeps, instructions, or a sample answer. The comparison transcript is machine-generated and may need correction after your attempt. This is a custom practice exercise.</p></div><div id="clip-result"></div>`;
  $('#studio-track').onchange=()=>{studioResource=$('#studio-track').value;renderStudio();};
  const player=$('#studio-player');player.onloadedmetadata=()=>{studioDuration=player.duration;$('#studio-time').textContent=`Recording length: ${formatTime(studioDuration)}. Select a clip up to 60 seconds.`;};
  $('#mark-start').onclick=()=>$('#clip-start').value=player.currentTime.toFixed(1);
  $('#mark-end').onclick=()=>$('#clip-end').value=player.currentTime.toFixed(1);
  $('#preview-clip').onclick=()=>{const start=Number($('#clip-start').value),end=Number($('#clip-end').value);player.currentTime=start;player.play();player.ontimeupdate=()=>{if(player.currentTime>=end){player.pause();player.ontimeupdate=null;}};};
  $('#create-clip').onclick=async()=>{
    const payload={resourceId:studioResource,start:Number($('#clip-start').value),end:Number($('#clip-end').value),type:$('#clip-type').value};player.pause();
    try{
      loading('Preparing your selected prompt');
      const job=await api('/api/create-clip',payload);const exercise=await waitJob(job.jobId);exercises[exercise.id]=exercise;catalog.exercises.push(exercise);
      content.innerHTML=hero('YOUR CUSTOM DRILL','Your prompt is ready.','Listen once and respond under the timer. You can inspect the recognized reference after your attempt.')+`<div class="panel"><h3>${esc(typeName[exercise.type])}</h3><p class="small">${exercise.seconds} seconds to respond. Recordings remain local.</p><button class="button primary" id="start-clip">Record my response →</button></div>`;
      $('#start-clip').onclick=()=>launchSession(makeBlocks([exercise]),exercise.title,'timed','record').catch(showStartError);

    }catch(error){toast(error.message);renderStudio();}
  };
}
async function renderHistory(){
  loading('Loading your practice history');
  try{
    const history=await api('/api/history');
    content.innerHTML=hero('REVIEW, THEN TRY AGAIN','See what is getting clearer.','Your saved answers, recordings, and feedback are here. Compare fresh attempts to see which improvements carry over.')+
      `<div class="panel">${history.length?history.map(h=>`<div class="resource-row history-row" data-history="${esc(h.id)}"><div><h3>${esc(h.title)}</h3><p>${esc(new Date(h.created).toLocaleString('en-US'))} · ${esc(h.mode)}</p></div><span class="small">View feedback →</span></div>`).join(''):'<div class="empty">Your first completed practice session will appear here.</div>'}</div>`;
    const removedId=localStorage.getItem(REMOVED_RESULT_KEY);
    if(removedId){
      content.insertAdjacentHTML('afterbegin','<div class="resume"><span>Result removed from your history.</span><button class="button" id="undo-remove">Undo removal</button></div>');
      $('#undo-remove').onclick=async()=>{
        $('#undo-remove').disabled=true;
        try{await api('/api/history/'+encodeURIComponent(removedId)+'/restore',{});localStorage.removeItem(REMOVED_RESULT_KEY);renderResult(await api('/api/history/'+encodeURIComponent(removedId)));toast('Result restored.');}
        catch(error){toast(error.message);if($('#undo-remove'))$('#undo-remove').disabled=false;}
      };
    }
    $$('[data-history]').forEach(b=>b.onclick=async()=>{try{renderResult(await api('/api/history/'+b.dataset.history));}catch(e){toast(e.message);}});
  }catch(e){toast(e.message);}
}
function resultLabel(g){
  if(g.error)return 'Review incomplete';
  if(g.total!==undefined)return `${g.points} / ${g.total} correct`;
  if(g.accuracy!==undefined)return g.score!==undefined&&g.score!==null?`${g.score} / 5 · content estimate · ${g.accuracy}% words`:`${g.accuracy}% word accuracy`;
  if(g.score!==undefined&&g.score!==null)return `${g.score} / 5 · practice estimate`;
  return 'Review required';
}
function renderRubricInfo(g){
  if(!g.rubricSource)return '';
  const source=g.rubricUrl?.startsWith('https://www.ets.org/')?`<a href="${esc(g.rubricUrl)}" target="_blank" rel="noreferrer">${esc(g.rubricSource)} ↗</a>`:esc(g.rubricSource);
  const diagnostics=g.rubric&&Object.keys(g.rubric).length?`<p class="small">App diagnostics: task fulfilment ${g.rubric.taskFulfillment}/5 · development ${g.rubric.development}/5 · language ${g.rubric.language}/5. These are not separate ETS scores.</p>`:'';
  return `<p class="small">${source}. ${esc(g.ratingPolicy)}</p>${diagnostics}${g.checklist?`<p class="small">${g.checklist.words} words</p>`:''}${g.scoringScale?`<details><summary>View the 0–5 task rubric</summary><table class="score-scale"><tbody>${Object.entries(g.scoringScale).sort((a,b)=>Number(b[0])-Number(a[0])).map(([n,text])=>`<tr><th scope="row">${esc(n)}</th><td>${esc(text)}</td></tr>`).join('')}</tbody></table></details>`:''}`;
}
function renderResult(result){
  const hasIncomplete=result.rows.some(row=>row.grade.error||row.grade.rubricScoreError);
  content.innerHTML=hero('YOUR SESSION REVIEW',esc(result.title),'Keep the useful corrections. Choose one or two priorities for your next session.')+
    `<div style="display:flex;gap:10px"><button class="button" id="export-result">Download feedback</button><button class="button" id="new-practice">New practice →</button><button class="button remove-button" id="remove-result">Remove result</button></div><div class="results-grid">${Object.entries(result.summary).map(([section,s])=>`<div class="result-stat"><h3>${section}</h3>${s.accuracy!==null?`<strong>${s.accuracy}%</strong><small>${s.points} / ${s.total} source-key points</small>`:''}${s.rubricAverage!==null?`<strong>${s.rubricAverage}<span style="font-size:14px"> / 5</span></strong><small>Mean practice task rating · 0–5</small>`:''}${s.repeatAccuracy!==null?`<strong>${s.repeatAccuracy}%</strong><small>Repetition word accuracy</small>`:''}${s.incomplete?`<p class="small">${s.incomplete} reviews incomplete</p>`:''}</div>`).join('')}</div><p class="warning">${esc(result.disclaimer)}</p>${result.priorities.length?`<div class="panel"><h3>Your next practice priorities</h3><ul class="feedback-list">${result.priorities.map(p=>`<li>${esc(p)}</li>`).join('')}</ul></div>`:''}`+
    result.rows.map((row,i)=>{
      const g=row.grade;
      return `<article class="feedback-card"><div class="feedback-head"><h3><span class="tag">${row.section}</span>${esc(typeName[row.type])}</h3><span class="feedback-score">${esc(resultLabel(g))}</span></div>${g.scoreExplanation?`<p class="feedback-copy">${esc(g.scoreExplanation)}</p>`:''}${g.scoreScope?`<p class="small">${esc(g.scoreScope)}</p>`:''}${g.rubricScoreError?`<p class="error">${esc(g.rubricScoreError)}</p>`:''}${g.error?`<p class="error">${esc(g.error)}</p>`:''}${g.strengths?.length?`<ul class="feedback-list">${g.strengths.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${g.improvements?.length?`<ul class="feedback-list">${g.improvements.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}<details><summary>View response, corrections, and source</summary><p class="feedback-copy">${esc(row.prompt)}</p>${row.recording?`<audio controls src="/api/recordings/${esc(row.recording)}"></audio>`:''}<div class="small">${row.audio?'Recognized transcript':'Your response'}</div><p class="feedback-copy quote">${esc(Array.isArray(row.response)?row.response.join(', '):row.response||'(No response)')}</p>${g.answer!==undefined?`<div class="small">Source answer</div><p class="feedback-copy">${esc(Array.isArray(g.answer)?g.answer.join(', '):g.answer)}</p>`:''}${g.explanation?`<p class="feedback-copy">${esc(g.explanation)}</p>`:''}${g.reference?`<div class="small">Reference sentence</div><p class="feedback-copy">${esc(g.reference)}</p>`:''}${g.changes?.length?`<ul class="feedback-list">${g.changes.map(c=>`<li>${esc(c.type==='delete'?'Missing':c.type==='insert'?'Added':'Changed')}: ${c.expected?esc(c.expected):''}${c.expected&&c.heard?' → ':''}${esc(c.heard)}</li>`).join('')}</ul>`:''}${g.corrections?.map(c=>`<div class="correction"><del>${esc(c.original)}</del> → <ins>${esc(c.corrected)}</ins><div class="small">${esc(c.reason)}</div></div>`).join('')||''}${renderRubricInfo(g)}${g.betterOpening?`<div class="small" style="margin-top:12px">Possible improved opening</div><p class="feedback-copy">${esc(g.betterOpening)}</p>`:''}${row.audio?`<p class="small">Recorded duration: ${row.audio.metrics.duration}s · Long pauses: ${row.audio.metrics.longPauses}${row.audio.metrics.wordsPerMinute!==undefined?' · Recognized words/min: '+row.audio.metrics.wordsPerMinute:''}</p>`:''}${g.limitations?.length?`<p class="small">${g.limitations.map(esc).join(' ')}</p>`:''}${row.recording?`<label class="field-label" for="transcript-${i}">CORRECT RECOGNITION ERRORS, THEN RE-EVALUATE</label><textarea class="response" id="transcript-${i}" style="min-height:90px">${esc(row.response)}</textarea><button class="button" data-regrade="${i}">Re-evaluate this response</button>`:''}${row.sampleAnswer?`<details><summary>Source sample answer</summary><p class="feedback-copy">${esc(row.sampleAnswer)}</p></details>`:''}<p class="small" style="margin-top:12px">${sourceLink(row)}</p></details></article>`;
    }).join('');
  if(hasIncomplete){
    $('#export-result').insertAdjacentHTML('afterend','<button class="button" id="retry-result">Retry incomplete reviews</button>');
    $('#retry-result').onclick=async()=>{
      try{loading('Reviewing your saved recordings');const job=await api('/api/history/'+encodeURIComponent(result.id)+'/retry',{});renderResult(await waitJob(job.jobId));}
      catch(error){toast(error.message);renderResult(result);}
    };
  }
  $('#new-practice').onclick=()=>navigate('practice');
  result.rows.forEach((row,i)=>{
    if(!row.id.startsWith('audio-')&&!row.id.startsWith('clip-'))return;
    const card=$$('.feedback-card')[i],details=card.querySelector('details');
    const sourceText=row.type==='repeat'?(row.grade.reference||''):row.prompt;
    details.insertAdjacentHTML('beforeend',`<label class="field-label" for="prompt-transcript-${i}">CORRECT THE IMPORTED PROMPT TRANSCRIPT</label><textarea class="response" id="prompt-transcript-${i}" style="min-height:90px">${esc(sourceText)}</textarea><button class="button" data-prompt-correction="${i}">Save prompt correction and review</button><p class="small">Listen to the source audio before changing this text. This corrects the imported prompt, separately from your response.</p>`);
  });
  $$('[data-prompt-correction]').forEach(button=>button.onclick=async()=>{
    const i=Number(button.dataset.promptCorrection),row=result.rows[i],text=$('#prompt-transcript-'+i).value;
    try{await api('/api/reference',{id:row.id,text});loading('Reviewing with the corrected prompt');const job=await api('/api/evaluate',{title:'Prompt correction · '+result.title,mode:'prompt review',items:[{id:row.id,response:row.response,correctedTranscript:row.response,recording:row.recording}]});renderResult(await waitJob(job.jobId));}
    catch(error){toast(error.message);renderResult(result);}
  });
  $('#remove-result').onclick=async()=>{
    $('#remove-result').disabled=true;
    try{await api('/api/history/'+encodeURIComponent(result.id)+'/remove',{});localStorage.setItem(REMOVED_RESULT_KEY,result.id);await renderHistory();toast('Result removed. You can undo this from your history.');}
    catch(error){toast(error.message);if($('#remove-result'))$('#remove-result').disabled=false;}
  };
  $('#export-result').onclick=()=>{const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='TOEFL-feedback-'+result.id.slice(0,8)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
  $$('[data-regrade]').forEach(button=>button.onclick=async()=>{
    const i=Number(button.dataset.regrade),row=result.rows[i],text=$('#transcript-'+i).value;
    try{loading('Reviewing your corrected transcript');const job=await api('/api/evaluate',{title:'Corrected transcript · '+result.title,mode:'transcript review',items:[{id:row.id,response:text,correctedTranscript:text,recording:row.recording}]});renderResult(await waitJob(job.jobId));}catch(e){toast(e.message);renderResult(result);}
  });
}
async function engineStatus(){
  try{health=await api('/api/health');$('#engine-status').innerHTML=`<p><span class="tag ${health.speechAvailable?'green':''}">${health.speechAvailable?'READY':'MISSING'}</span> Offline speech transcription</p>${health.speechError?`<p class="error">${esc(health.speechError)}</p>`:''}<p><span class="tag ${health.feedbackAvailable?'green':''}">${health.feedbackAvailable?'READY':'MISSING'}</span> Local Writing & interview feedback</p><p class="small">No API key is needed. Models may take a moment to load on the first review. Recognition errors can be corrected before re-evaluation. Pronunciation and intonation are not scored.</p>`;$('#status-dialog').showModal();}catch(e){toast(e.message);}
}
async function init(){
  try{
    [catalog,health]=await Promise.all([api('/api/catalog'),api('/api/health')]);exercises=Object.fromEntries(catalog.exercises.map(e=>[e.id,e]));resources=Object.fromEntries(catalog.resources.map(r=>[r.id,r]));
    if(localStorage.getItem('toefl-theme')==='dark')document.body.classList.add('dark');
    $$('.nav-item').forEach(b=>b.onclick=()=>navigate(b.dataset.view));$('.brand').onclick=e=>{e.preventDefault();navigate('practice');};
    $('#engines-button').onclick=engineStatus;$('#theme-button').onclick=()=>{document.body.classList.toggle('dark');localStorage.setItem('toefl-theme',document.body.classList.contains('dark')?'dark':'light');};
    $('#stop-app').onclick=async()=>{try{if(session)await saveAndLeave();await api('/api/shutdown',{});content.innerHTML=hero('PRACTICE SAVED','The app is stopped.','Double-click Start TOEFL in the app folder to reopen it. Your saved results remain available.');}catch(e){toast(e.message);}};
    renderPractice();
    document.addEventListener('visibilitychange',()=>{if(session&&!document.hidden)tick();});
    window.addEventListener('beforeunload',e=>{if(session){saveDraft();e.preventDefault();e.returnValue='';}});
  }catch(e){content.innerHTML=`<div class="error">${esc(e.message)}. Restart the local app and try again.</div>`;}
}
init();
