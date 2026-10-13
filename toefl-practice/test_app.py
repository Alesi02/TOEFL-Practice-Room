"""Focused checks for grading, provenance protection, and real local audio recognition."""
import unittest
import tempfile
import json
import wave
from pathlib import Path
from unittest.mock import patch
import server

class GradingTests(unittest.TestCase):
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
        with patch.object(server.importlib, 'import_module', side_effect=ModuleNotFoundError("No module named 'faster_whisper.audio'")):
            status=server.speech_status()
        self.assertFalse(status['speechAvailable'])
        self.assertIn('faster_whisper.audio',status['speechError'])

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
            for key in ['answer','reference','sampleAnswer','explanation']:
                self.assertNotIn(key,public)

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
