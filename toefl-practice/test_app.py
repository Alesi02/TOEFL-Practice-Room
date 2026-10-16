"""Focused checks for grading, provenance protection, and real local audio recognition."""
import unittest
import tempfile
import json
import wave
import threading
from pathlib import Path
from unittest.mock import patch
import server

class GradingTests(unittest.TestCase):
    def test_preparation_can_run_while_both_grading_workers_are_busy(self):
        release = threading.Event()
        started = [threading.Event(), threading.Event()]
        def busy(job, ready):
            ready.set()
            release.wait(5)
            return 'graded'
        identifiers = [server.submit_job(lambda job, ready=ready: busy(job, ready)) for ready in started]
        try:
            self.assertTrue(all(ready.wait(2) for ready in started))
            prepared = threading.Event()
            identifier = server.submit_job(lambda job: prepared.set(), executor=server.PREPARE_POOL)
            self.assertTrue(prepared.wait(2), 'New practice must not wait for grading workers')
        finally:
            release.set()

    def test_generated_audio_is_removed_from_old_banks_and_source_tests(self):
        from practice_catalog import remove_generated_audio, is_toefl_2026
        human={'id':'original','section':'Listening','type':'mcq','sourceId':'source','audio':'original.mp3'}
        generated={**human,'id':'generated','audioAvailability':'synthesized','audio':'assets/compressed.opus'}
        catalog={'resources':[{'id':'source'}],'exercises':[human,generated],
                 'tests':[{'id':'source-test','sections':{'Listening':['original','generated']}}]}
        self.assertFalse(is_toefl_2026(generated))
        remove_generated_audio(catalog)
        self.assertEqual([e['id'] for e in catalog['exercises']],['original'])
        self.assertEqual(catalog['tests'][0]['sections']['Listening'],['original'])
        self.assertEqual(catalog['tests'][0]['missingItemCounts']['Listening'],1)
        self.assertTrue(catalog['tests'][0]['partial'])
        remove_generated_audio(catalog)
        self.assertEqual(catalog['tests'][0]['missingItemCounts']['Listening'],1)

    @classmethod
    def setUpClass(cls):
        server.load_catalog()

    def test_gap_answers_are_graded_individually(self):
        exercise={'type':'complete_words','answer':['rm','nd','in']}
        grade=server.objective_grade(exercise,['rm','xx','in'])
        self.assertEqual((grade['points'],grade['total']),(2,3))
        self.assertEqual(grade['matched'],[True,False,True])

    def test_source_key_not_length_drives_objective_grade(self):
        self.assertEqual(server.objective_grade({'type':'mcq','answer':'B'},'A')['points'],0)
        self.assertEqual(server.objective_grade({'type':'sentence','answer':'He explained where we would stop.'},'He explained where we would stop!')['points'],1)

    def test_missing_key_is_not_fabricated(self):
        self.assertIsNone(server.objective_grade({'type':'mcq','answer':None},'A')['score'])

    def test_result_removal_is_reversible_and_preserves_content(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'PRIVATE', Path(directory)):
            identifier='a'*32
            history=Path(directory)/'history'
            history.mkdir()
            result=history/(identifier+'.json')
            content=b'{"title":"Removal test"}'
            result.write_bytes(content)
            server.set_result_removed(identifier,True)
            self.assertFalse(result.exists())
            self.assertEqual((Path(directory)/'removed-results'/(identifier+'.json')).read_bytes(),content)
            server.set_result_removed(identifier,False)
            self.assertEqual(result.read_bytes(),content)
            with self.assertRaises(ValueError):server.set_result_removed('../outside',True)

    def test_repetition_reports_word_edits(self):
        grade=server.repetition_grade('Please return all books before Friday.','Please return books before Friday.')
        self.assertEqual(grade['wordEdits'],1)
        self.assertIn('all',str(grade['changes']))
        self.assertEqual(server.repetition_grade('Welcome to the library.','')['accuracy'],0)

    def test_speech_status_detects_a_broken_decoder(self):
        with patch.object(server,'SPEECH_STATUS',None), patch.object(server,'SPEECH_CHECK_THREAD',None), patch.object(server,'run_speech_worker',side_effect=RuntimeError("No module named 'faster_whisper.audio'")):
            status=server.speech_status(wait=True)
        self.assertFalse(status['speechAvailable'])
        self.assertIn('faster_whisper.audio',status['speechError'])

    def test_speech_status_recovers_a_stale_host_import(self):
        with patch.object(server,'SPEECH_STATUS',None), patch.object(server,'SPEECH_CHECK_THREAD',None), patch.object(server.importlib,'import_module',side_effect=ModuleNotFoundError("No module named 'faster_whisper.audio'")), patch.object(server,'run_speech_worker',return_value={'speechAvailable':True,'speechError':None}) as worker:
            self.assertTrue(server.speech_status(wait=True)['speechAvailable'])
            worker.assert_called_once_with('status')

    def test_transcription_recovers_without_restarting_or_losing_recording(self):
        recovered={'text':'Welcome to the library.','metrics':{'duration':2},'segments':[]}
        with patch.object(server.os,'environ',{'TOEFL_SPEECH_WORKER':'1'}), patch.object(server,'transcribe_local',side_effect=ModuleNotFoundError("No module named 'faster_whisper.audio'")) as host, patch.object(server,'run_speech_worker',return_value=recovered) as worker:
            self.assertEqual(server.transcribe(Path('saved.webm')),recovered)
            worker.assert_called_once_with('transcribe',path=Path('saved.webm'),samples=None)
            host.assert_not_called()

    def test_speech_recovery_does_not_hide_unrelated_dependency_errors(self):
        with patch.object(server,'run_speech_worker',side_effect=RuntimeError("No module named 'numpy'")):
            with self.assertRaisesRegex(RuntimeError,'numpy'):server.transcribe(Path('saved.webm'))

    def test_speech_runtime_repairs_itself_offline_when_source_is_damaged(self):
        from speech_runtime import prepare_runtime
        with tempfile.TemporaryDirectory() as folder:
            base,private=Path(folder)/'app',Path(folder)/'private'
            originals={'.runtime/python.exe':b'embedded interpreter',
                       '.deps/faster_whisper/audio.py':b'def decode_audio(): pass',
                       '.deps/faster_whisper/transcribe.py':b'class WhisperModel: pass',
                       '.deps/av/__init__.py':b'# decoder', 'server.py':b'# worker'}
            for name,data in originals.items():
                path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            private.mkdir()
            with patch('speech_runtime.subprocess.run') as probe:
                probe.return_value.returncode=0
                ready=prepare_runtime(base,private)
                probe.assert_called_once()
            decoder=ready['directory']/'.deps/faster_whisper/audio.py'
            decoder.unlink()
            self.assertEqual(prepare_runtime(base,private)['repaired'],1)
            decoder.write_bytes(b'# damaged cache')
            (base/'.deps/faster_whisper/audio.py').unlink()
            (base/'.runtime/python.exe').unlink()
            repaired=prepare_runtime(base,private)
            self.assertTrue(repaired['portable'])
            self.assertEqual(decoder.read_bytes(),originals['.deps/faster_whisper/audio.py'])
            self.assertEqual(repaired['repaired'],1)
            self.assertNotIn('import site',(repaired['python'].parent/'python312._pth').read_text())

    def test_partial_installation_does_not_become_the_offline_repair_backup(self):
        from speech_runtime import make_backup
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            for name in ('.runtime/python.exe','.deps/faster_whisper/audio.py',
                         '.deps/faster_whisper/transcribe.py','.deps/av/__init__.py'):
                path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'partial setup')
            with patch('speech_runtime.subprocess.run') as probe:
                probe.return_value.returncode=1
                with self.assertRaisesRegex(RuntimeError,'initial check'):
                    make_backup(base,base/'backup.zip')
            self.assertFalse((base/'backup.zip').exists())

    def test_audio_decoder_reads_a_real_wave_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'recording.wav'
            with wave.open(str(path),'wb') as recording:
                recording.setnchannels(1)
                recording.setsampwidth(2)
                recording.setframerate(16000)
                recording.writeframes(b'\x00\x00'*1600)
            samples=server.read_audio(path)
            self.assertEqual(len(samples),1600)
            self.assertTrue(server.audio_metrics(samples)['silent'])

    def test_retry_recognizes_failed_recordings_and_keeps_completed_feedback(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server,'PRIVATE',Path(directory)):
            private=Path(directory)
            (private/'history').mkdir()
            (private/'recordings').mkdir()
            recording='b'*32+'.webm'
            (private/'recordings'/recording).write_bytes(b'recorded audio')
            identifier='c'*32
            completed={'id':'read','section':'Reading','type':'mcq','grade':{'points':1,'total':1,'method':'source answer key','improvements':[]},'response':'B'}
            failed={'id':'speak','section':'Speaking','type':'repeat','grade':{'error':'decoder unavailable'},'recording':recording,'response':'','elapsed':10}
            previous={'id':identifier,'created':'2026-10-01','title':'Saved session','mode':'practice','rows':[completed,failed]}
            target=private/'history'/(identifier+'.json')
            original=json.dumps(previous).encode()
            target.write_bytes(original)
            exercises={'read':{'id':'read','section':'Reading','type':'mcq','answer':'B'},'speak':{'id':'speak','section':'Speaking','type':'repeat','reference':'Welcome to the library.'}}
            recognized={'text':'Welcome to the library.','metrics':{'duration':2},'segments':[]}
            with patch.object(server,'EXERCISES',exercises), patch.object(server,'transcribe',return_value=recognized) as transcription:
                result=server.retry_result(identifier,{})
            transcription.assert_called_once_with(private/'recordings'/recording)
            self.assertEqual(result['id'],identifier)
            self.assertEqual(result['created'],previous['created'])
            self.assertEqual(result['rows'][0],completed)
            self.assertEqual(result['rows'][1]['grade']['accuracy'],100)
            self.assertEqual(result['summary']['Speaking']['incomplete'],0)
            self.assertEqual((private/'retry-backups'/(identifier+'.json')).read_bytes(),original)
            self.assertEqual(len(list((private/'history').glob('*.json'))),1)
            self.assertTrue((private/'recordings'/recording).exists())

    def test_answers_are_not_in_public_catalog(self):
        for exercise in server.CATALOG['exercises']:
            public=server.public_exercise(exercise)
            for key in ['answer','reference','sampleAnswer','explanation','answerGuide','ttsText']:
                self.assertNotIn(key,public)

    def test_supplementary_exercises_are_excluded_from_full_tests(self):
        from practice_catalog import is_toefl_2026
        for test in server.CATALOG['tests']:
            if not test.get('prepared'):continue
            for identifiers in test['sections'].values():
                for identifier in identifiers:
                    self.assertTrue(is_toefl_2026(server.EXERCISES[identifier]))

    def test_official_top_band_conditions_allow_timed_typos(self):
        from feedback_rubric import apply_rubric
        def strong():
            return {'score':5,'rubric':{'taskFulfillment':5,'development':5,'language':5},
                    'assessment':{'fullyAddressesTask':True,'wellElaborated':True,'effectiveLanguageRange':True,
                                  'clearAndCoherent':True,'nearErrorFree':True,'socialConventionsAppropriate':True,
                                  'grammarErrors':0,'mechanicalErrors':3},'corrections':[]}
        grade=strong()
        self.assertEqual(apply_rubric(grade,'An accurate developed answer.',{'type':'email'})['score'],5)
        self.assertIn('ETS TOEFL iBT',grade['rubricSource'])
        self.assertNotIn('suggestedWordTarget',grade['checklist'])
        for limitation in ('fullyAddressesTask','wellElaborated','effectiveLanguageRange','clearAndCoherent'):
            grade=strong();grade['assessment'][limitation]=False
            self.assertEqual(apply_rubric(grade,'An answer.',{'type':'interview'})['score'],4)
        grade=strong();grade['assessment']['nearErrorFree']=False
        self.assertEqual(apply_rubric(grade,'An answer.',{'type':'discussion'})['score'],4)
        grade=strong();grade['assessment']['socialConventionsAppropriate']=False
        self.assertEqual(apply_rubric(grade,'An answer.',{'type':'email'})['score'],4)
        grade=strong();grade['assessment']['socialConventionsAppropriate']=False
        self.assertEqual(apply_rubric(grade,'An answer.',{'type':'discussion'})['score'],5)
        grade=strong()
        self.assertEqual(apply_rubric(grade,'An answer.',{'type':'interview'},{'longPauses':5})['score'],5)
        self.assertIn('auditory intelligibility',grade['unassessedDimensions'])
        grade=strong();grade['assessment']['frequentSubstantiveErrors']=True
        self.assertEqual(apply_rubric(grade,'An answer.',{'type':'email'})['score'],3)
        grade=strong();grade['assessment']['frequentSubstantiveErrors']=True;grade['assessment']['clearAndCoherent']=False
        self.assertEqual(apply_rubric(grade,'An answer.',{'type':'discussion'})['score'],3)
        grade=strong();grade['assessment']['frequentSubstantiveErrors']=True
        self.assertEqual(apply_rubric(grade,'An answer.',{'type':'interview'})['score'],4)

    def test_repetition_scale_preserves_verbatim_and_semantic_distinctions(self):
        e={'type':'repeat','reference':"I'm working in the laboratory."}
        self.assertEqual(server.repetition_rubric_grade(e,"I'm working in the laboratory.")['score'],5)
        self.assertEqual(server.repetition_rubric_grade(e,'I am working in the laboratory.')['score'],4)
        self.assertEqual(server.repetition_rubric_grade(e,'')['score'],0)
        e={'type':'repeat','reference':'The laboratory will not open on Monday.'}
        with patch.object(server,'language_feedback',return_value={'score':3,'scoreExplanation':'Negation omitted; the meaning changes.'}):
            grade=server.repetition_rubric_grade(e,'The laboratory will open on Monday.')
        self.assertEqual(grade['score'],3)
        self.assertGreater(grade['accuracy'],80)
        self.assertEqual(len(grade['scoringScale']),6)

    def test_repetition_comparison_survives_missing_feedback_engine(self):
        with patch.object(server,'language_feedback',side_effect=RuntimeError('model missing')):
            grade=server.repetition_rubric_grade({'type':'repeat','reference':'Please return the book.'},'Please return book.')
        self.assertIn('accuracy',grade)
        self.assertIn('rubricScoreError',grade)
        self.assertNotIn('score',grade)

    def test_retry_recovers_a_missing_numerical_repetition_review(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server,'PRIVATE',Path(directory)):
            private=Path(directory);(private/'history').mkdir();(private/'recordings').mkdir()
            identifier='d'*32;recording='e'*32+'.webm'
            (private/'recordings'/recording).write_bytes(b'audio')
            exercise={'id':'repeat','section':'Speaking','type':'repeat','reference':'Please return the book.'}
            previous={'id':identifier,'created':'2026-10-13','title':'Retry','mode':'practice','rows':[
                {'id':'repeat','section':'Speaking','type':'repeat','response':'Please return book.',
                 'recording':recording,'grade':{'method':'transcript word comparison','accuracy':80,'rubricScoreError':'Model missing'}}]}
            (private/'history'/(identifier+'.json')).write_text(json.dumps(previous),encoding='utf8')
            with patch.object(server,'EXERCISES',{'repeat':exercise}),patch.object(server,'transcribe',return_value={'text':'Please return book.','metrics':{'duration':2}}),patch.object(server,'language_feedback',return_value={'score':4,'scoreExplanation':'A minor article omission preserves meaning.'}):
                result=server.retry_result(identifier,{})
            self.assertEqual(result['id'],identifier)
            self.assertEqual(result['summary']['Speaking']['incomplete'],0)
            self.assertEqual(result['summary']['Speaking']['rubricAverage'],4)
            self.assertEqual(result['rows'][0]['grade']['score'],4)

    def test_copied_writing_receives_zero_without_model(self):
        with patch.object(server,'ensure_llama') as model:
            grade=server.language_feedback({'type':'email','prompt':'Write an email to your professor.'},'Write an email to your professor.')
        model.assert_not_called()
        self.assertEqual(grade['score'],0)

    def test_official_writing_criteria_do_not_apply_to_extra_essays(self):
        from feedback_rubric import apply_rubric, guidance
        grade=apply_rubric({'score':4},'An essay.',{'type':'essay'})
        self.assertNotIn('rubricUrl',grade)
        self.assertIn('Extra practice',grade['rubricSource'])
        self.assertIn('original instructions',guidance({'type':'worksheet'}))

    def test_old_topics_and_workbooks_are_extra(self):
        from practice_catalog import classify
        self.assertEqual(classify({'section':'Speaking','type':'interview','textPrompt':True})['practiceCategory'],'extra')
        self.assertEqual(classify({'section':'Writing','type':'essay'})['practiceCategory'],'extra')
        self.assertEqual(classify({'section':'Reading','type':'worksheet'})['practiceCategory'],'extra')
        self.assertEqual(classify({'section':'Speaking','type':'interview','audio':'prompt.opus'})['practiceCategory'],'toefl2026')

    def test_audio_import_removes_video_instructions_and_sample_answers(self):
        from convert_audio import prompts
        chunks=[("Let's begin.",0),("This is an advanced practice video with longer sentences.",12),("Welcome to the campus library.",30),("Use these sample answers for ideas only.",70)]
        words=[]
        for text,start in chunks:
            words.extend({'word':' '+word,'start':start+i*.2,'end':start+(i+1)*.2} for i,word in enumerate(text.split()))
        clips=prompts({'duration':100,'segments':[{'words':words}]},'repeat')
        self.assertEqual([clip['text'] for clip in clips],['Welcome to the campus library.'])

    def test_conversion_preserves_original_question_bank_and_ignores_non_exercises(self):
        if not any(e['id'].startswith('extra-') for e in server.CATALOG['exercises']):
            self.skipTest('Expanded private material is not part of the public source checkout')
        source=next(r['id'] for r in server.CATALOG['resources'] if r['path']=='Speaking/GfG- Speaking-Questions.pdf')
        self.assertEqual(sum(e['sourceId']==source for e in server.CATALOG['exercises']),180)
        for path in ('Speaking/Speaking Vocabulary.pdf','Writing/Writing Vocabulary.pdf','Phrasal verbs.pdf','TOEFL-three-week-schedule.md','Writing/Practicando escritura.txt'):
            resource=next(r for r in server.CATALOG['resources'] if r['path']==path)
            self.assertEqual(resource['exerciseCount'],0)

    def test_worksheet_contains_questions_not_just_an_instruction_header(self):
        for exercise in server.CATALOG['exercises']:
            if exercise['type']=='worksheet':
                self.assertGreater(len(exercise['prompt']),300,exercise['title'])
                self.assertNotIn('Exercise Answer Key',exercise['prompt'])

    def test_local_files_are_allowlisted(self):
        with self.assertRaises(ValueError):server.media_path('../secret.txt')
        with self.assertRaises(ValueError):server.media_path('toefl-practice/server.py')
        with self.assertRaises(ValueError):server.media_path('https://example.com/unlisted.mp3')

    def test_blank_open_response_is_zero_without_model(self):
        grade=server.language_feedback({'type':'email'},'')
        self.assertEqual(grade['score'],0)

    def test_catalog_ids_and_test_references(self):
        ids=[x['id'] for x in server.CATALOG['exercises']]
        self.assertEqual(len(ids),len(set(ids)))
        for test in server.CATALOG['tests']:
            for section, refs in test['sections'].items():
                for identifier in refs:
                    exercise=server.EXERCISES[identifier]
                    self.assertEqual(exercise['section'],section)
                    if section=='Listening':self.assertTrue(exercise.get('audio'))

    def test_twenty_prepared_forms_have_complete_task_mix(self):
        if not server.CATALOG['exercises']:
            self.skipTest('Private exercise data is not included in the public source checkout')
        from make_tests import prepared_tests, build_test, listening_type
        forms=prepared_tests(server.CATALOG)
        self.assertEqual(len(forms),20)
        signatures=[]
        for form in forms:
            selected=[server.EXERCISES[i] for ids in form['sections'].values() for i in ids]
            self.assertEqual(len(selected),len({x['id'] for x in selected}))
            signatures.append(tuple(x['id'] for x in selected))
            read=[x for x in selected if x['section']=='Reading']
            self.assertEqual(sum(x.get('questionCount',1) for x in read),50)
            listen=[x for x in selected if x['section']=='Listening']
            self.assertEqual(len(listen),47)
            self.assertEqual({listening_type(x) for x in listen},{'short','conversation','announcement','talk'})
            self.assertEqual(sum(x['type']=='sentence' for x in selected),10)
            self.assertEqual(sum(x['type']=='email' for x in selected),1)
            self.assertEqual(sum(x['type']=='discussion' for x in selected),1)
            self.assertEqual(sum(x['type']=='repeat' for x in selected),7)
            self.assertEqual(sum(x['type']=='interview' for x in selected),4)
        self.assertEqual(len(signatures),len(set(signatures)))
        first=build_test(server.CATALOG,1,'one','One')
        second=build_test(server.CATALOG,2,'two','Two')
        self.assertNotEqual(first['sections'],second['sections'])

if __name__ == '__main__':
    unittest.main()
