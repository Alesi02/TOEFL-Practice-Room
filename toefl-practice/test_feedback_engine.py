"""Behavior checks for structured assessment and app-owned feedback wording."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from feedback_engine import (VERSION, ASSESSMENT_FLAGS, build_request, evaluate,
                             response_parts, upgrade_saved_grade)
from review_store import upgrade_history


def assessment():
    flags = {key: True for key in ASSESSMENT_FLAGS}
    flags.update(noMeaningfulResponse=False, frequentSubstantiveErrors=False,
                 grammarErrors=0, mechanicalErrors=0)
    return {'score': 5, 'rubric': {'taskFulfillment': 5, 'development': 5, 'language': 5},
            'assessment': flags, 'strengths': [{'code': 'task_coverage', 'part': 1}],
            'improvements': [], 'corrections': []}


def completion(data, reason='stop'):
    return lambda payload: {'choices': [{'finish_reason': reason, 'message': {'content': json.dumps(data)}}]}


class StructuredFeedbackTests(unittest.TestCase):
    def test_model_does_not_write_feedback_paragraphs_or_explanations(self):
        payload = build_request({'type': 'interview', 'prompt': 'What do you prefer?'},
                                'I prefer movies. I watch them twice a week.')
        schema = payload['response_format']['json_schema']['schema']
        self.assertNotIn('scoreExplanation', schema['properties'])
        self.assertNotIn('betterOpening', schema['properties'])
        self.assertNotIn('reason', schema['properties']['corrections']['items']['properties'])
        self.assertNotIn('maxLength', json.dumps(schema))
        self.assertIn('enum', schema['properties']['improvements']['items']['properties']['code'])
        self.assertNotIn('response[:', str(payload))

    def test_the_reported_foreign_suffix_cannot_supply_displayed_explanations(self):
        data = assessment()
        # Even a nonconforming transport that includes an obsolete prose field
        # cannot supply user-facing explanation text to this design.
        data['scoreExplanation'] = 'The response is relevant and developed, showing a合理'
        grade = evaluate({'type': 'interview'}, 'I prefer movies.', None, completion(data))
        self.assertEqual(grade['score'], 5)
        self.assertEqual(grade['feedbackVersion'], VERSION)
        self.assertTrue(grade['scoreExplanation'].endswith('.'))
        self.assertNotIn('合理', json.dumps(grade, ensure_ascii=False))
        self.assertIn('I prefer movies.', grade['strengths'][0])

    def test_edits_and_findings_keep_specific_evidence_without_model_prose(self):
        data = assessment()
        data.update(score=3, improvements=[{'code': 'verb_agreement', 'part': 1}],
                    corrections=[{'original': 'She go', 'corrected': 'She goes', 'kind': 'verb_agreement'}])
        data['assessment'].update(grammarErrors=1, nearErrorFree=False)
        grade = evaluate({'type': 'interview'}, 'She go to the cinema every week.', None, completion(data))
        self.assertEqual(grade['corrections'][0]['reason'], 'Make the verb agree with its subject.')
        self.assertEqual(grade['betterOpening'], 'She goes to the cinema every week.')
        self.assertIn('She go to the cinema every week.', grade['improvements'][0])
        self.assertNotIn('different', grade['scoreExplanation'])

    def test_rubric_policy_still_controls_the_final_writing_band(self):
        data = assessment()
        data['assessment']['frequentSubstantiveErrors'] = True
        grade = evaluate({'type': 'email'}, 'A relevant message.', None, completion(data))
        self.assertEqual(grade['score'], 3)
        self.assertIn('Recurring substantive language errors', grade['scoreExplanation'])

    def test_cut_off_assessment_is_not_misrepresented_as_a_completed_score(self):
        with self.assertRaisesRegex(RuntimeError, 'did not finish'):
            evaluate({'type': 'interview'}, 'A response.', None, completion(assessment(), 'length'))

    def test_no_learner_or_task_text_is_silently_shortened(self):
        response = ('This is part of the response.\n'*350)+'Final detail.'
        prompt = 'Original task. '*600
        request = build_request({'type': 'essay', 'prompt': prompt}, response)
        data = json.loads(request['messages'][1]['content'])
        self.assertEqual(data['task'], prompt)
        self.assertEqual([part['text'] for part in data['responseParts']], response_parts(response))
        self.assertEqual(data['responseParts'][-1]['text'], 'Final detail.')

    def test_saved_review_upgrade_preserves_scores_answers_and_recordings(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            (private/'history').mkdir()
            (private/'recordings').mkdir()
            recording = private/'recordings'/'original.webm'
            recording.write_bytes(b'original audio bytes')
            grade = {**assessment(), 'method': 'local AI rubric review',
                     'scoreExplanation': 'The response is relevant and developed, showing a合理',
                     'strengths': ['Old model-written wording.'], 'corrections': [], 'improvements': []}
            result = {'id': 'a'*32, 'created': '2026-10-16', 'title': 'Saved practice', 'mode': 'timed',
                      'rows': [{'id': 'question', 'type': 'interview', 'section': 'Speaking',
                                'response': 'I prefer movies.', 'recording': recording.name, 'grade': grade}]}
            original = json.dumps(result, ensure_ascii=False).encode()
            path = private/'history'/(result['id']+'.json')
            path.write_bytes(original)
            self.assertEqual(upgrade_history(private, {'question': {'type': 'interview'}}), [result['id']])
            upgraded = json.loads(path.read_text(encoding='utf8'))
            row = upgraded['rows'][0]
            self.assertEqual(row['grade']['score'], 5)
            self.assertEqual(row['response'], 'I prefer movies.')
            self.assertEqual(row['recording'], recording.name)
            self.assertEqual(upgraded['created'], result['created'])
            self.assertEqual(recording.read_bytes(), b'original audio bytes')
            self.assertEqual((private/'feedback-backups'/VERSION/path.name).read_bytes(), original)
            self.assertNotIn('合理', row['grade']['scoreExplanation'])
            unchanged = path.read_bytes()
            self.assertEqual(upgrade_history(private, {'question': {'type': 'interview'}}), [])
            self.assertEqual(path.read_bytes(), unchanged)

    def test_legacy_reading_answers_are_preserved(self):
        grade = {'method': 'source answer key', 'points': 1, 'total': 1, 'answer': 'B'}
        before = copy.deepcopy(grade)
        self.assertEqual(upgrade_saved_grade(grade, {'type': 'mcq'}, 'B'), before)


if __name__ == '__main__':
    unittest.main()
