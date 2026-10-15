// Run with Node.js: node test_ui.cjs. No browser packages or grading models required.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const elements=new Map(),storage=new Map(),sleeps=[];
let now=100000,audioStarts=0,recordingStarts=0,reviewDone=false;
const element=selector=>{
  if(!elements.has(selector))elements.set(selector,{innerHTML:'',textContent:'',style:{},classList:{toggle(){}},addEventListener(){},insertAdjacentHTML(){},querySelectorAll(){return[];}});
  return elements.get(selector);
};
const requests=[];
const sandbox={console,URL,Blob,Date:class extends Date{static now(){return now;}},
  document:{querySelector:element,querySelectorAll:()=>[]},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  setTimeout:(callback,delay)=>{if(delay===1500)sleeps.push(callback);return 1;},clearTimeout(){},
  setInterval:()=>123,clearInterval(){},
  fetch:async(path,options)=>{
    requests.push({path,body:options?.body&&JSON.parse(options.body)});
    let value;
    if(path==='/api/evaluate')value={jobId:'review-1'};
    else if(path==='/api/prepare')value={jobId:'prepare-1'};
    else if(path==='/api/jobs/prepare-1')value={status:'done',result:{failed:[]}};
    else if(path==='/api/jobs/review-1')value=reviewDone?{status:'done',result:{id:'saved-review'}}:{status:'working',message:'Reviewing response 1 of 4'};
    else if(path==='/api/history/saved-review')value={id:'saved-review'};
    else throw Error('Unexpected request '+path);
    return{ok:true,json:async()=>value};
  }};
const context=vm.createContext(sandbox);
const run=code=>vm.runInContext(code,context);
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(setImmediate);};
vm.runInContext(fs.readFileSync(__dirname+'/static/app.js','utf8').replace(/init\(\);\s*$/,''),context);
run(`resources={};exercises={r:{id:'r',section:'Reading',type:'mcq',prompt:'Read',options:[]},
  repeat:{id:'repeat',section:'Speaking',type:'repeat',audio:'repeat.wav'},
  interview:{id:'interview',section:'Speaking',type:'interview',audio:'interview.wav'},
  interview2:{id:'interview2',section:'Speaking',type:'interview',audio:'interview2.wav'}};
  renderPractice=()=>{content.innerHTML='Practice choices';};
  session={title:'Earlier practice',mode:'timed',blocks:[{section:'Reading',ids:['r'],seconds:120}],block:0,index:0,answers:{r:{id:'r',response:'A'}},played:[],phase:'question',blockDeadline:220000};`);

(async()=>{
  await run('finishSession()');await flush();
  assert.equal(run('session'),null,'A submitted attempt must release the active session');
  assert.equal(run("reviews[0].status"),'working');
  assert.equal(storage.has('toefl-practice-draft-v1'),false);
  await run("launchSession([{section:'Reading',label:'Reading',ids:['r'],seconds:120}],'New practice','timed','record')");
  run("document.querySelector('#begin-block').onclick();session.answers.r.response='B';saveDraft();");
  const activeHTML=element('#content').innerHTML,draft=storage.get('toefl-practice-draft-v1');
  reviewDone=true;sleeps.shift()();await flush();
  assert.equal(run('reviews[0].status'),'done');
  assert.equal(run('session.title'),'New practice');
  assert.equal(run('session.answers.r.response'),'B');
  assert.equal(storage.get('toefl-practice-draft-v1'),draft,'Completion must not erase the new draft');
  assert.equal(element('#content').innerHTML,activeHTML,'Completion must not replace the new question');
  assert.equal(run('interval'),123,'Completion must not stop the new timer');
  await run("openReview('review-1')");
  assert.equal(element('#content').innerHTML,activeHTML,'Feedback cannot interrupt an active session');
  assert.equal(requests.find(r=>r.path==='/api/evaluate').body.items[0].response,'A','The earlier answer must remain a separate snapshot');
  // Pending reviews must be recovered after refresh without starting duplicate grading.
  run("reviews[0].status='working';persistReviews();reviews=[];restoreReviews();");await flush();
  assert.equal(run('reviews[0].status'),'done');
  assert.equal(requests.filter(r=>r.path==='/api/evaluate').length,1);

  sandbox.onAudio=()=>audioStarts++;sandbox.onRecord=()=>recordingStarts++;
  run(`playAudio=async(e,after)=>{onAudio();};beginSpeakingResponse=async()=>{onRecord();};
    session={title:'Speaking',mode:'timed',blocks:[{section:'Speaking',label:'Speaking',ids:['repeat','interview','interview2'],seconds:480}],block:0,index:0,answers:{repeat:{id:'repeat',recording:'saved.webm'}},played:[],phase:'answered',blockDeadline:580000,itemStarted:99000};`);
  await run('nextQuestion()');
  assert.equal(run('session.phase'),'interview-break');
  assert.equal(audioStarts,0,'The interview prompt must wait behind the break');
  assert.equal(recordingStarts,0);
  assert.equal(element('#break-timer').textContent,''); // Initial value is rendered in the HTML.
  assert.match(element('#content').innerHTML,/0:30/);
  now+=10000;run('tick()');assert.equal(element('#break-timer').textContent,'0:20');
  run("document.querySelector('#continue-interview').onclick()");
  assert.equal(audioStarts,1);
  assert.equal(run('session.blockDeadline'),590000,'Break time must not consume Speaking time');
  await run('nextQuestion()');assert.equal(audioStarts,2,'Only one break is allowed before the interview');

  // Interview-only practice also gets a break; zero triggers the prompt exactly once.
  run("session.index=1;session.interviewBreaks=[];session.answers={};session.phase='question';session.blockDeadline=590000;renderQuestion();");
  now+=30000;run('tick();tick();');
  assert.equal(audioStarts,3,'The countdown must automatically continue once');
  assert.equal(run('session.blockDeadline'),620000);
  // Refresh while on the break keeps the break and its countdown, without audio.
  run("session.index=1;session.interviewBreaks=[];session.answers={};session.phase='question';renderQuestion();saveDraft();session=null;getMicrophone=async()=>{};");
  now+=5000;await run('resumeSession()');
  assert.equal(run('session.phase'),'interview-break');assert.equal(element('#break-timer').textContent,'0:25');
  assert.equal(audioStarts,3);
  console.log('Passed: independent background grading, new-session draft/timer safety, feedback guard, refresh recovery, interview transition, early Continue, countdown, and break resume.');
})().catch(error=>{console.error(error);process.exitCode=1;});
