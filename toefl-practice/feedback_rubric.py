"""Strict practice criteria adapted from the saved TSP Prep 2026 checklists.

The source supplies self-review targets, not a calibrated numerical scale.
The 0–5 rating and its conservative top-score rule belong to this app.
"""
import re

SOURCE = 'Self-grading rubrics 2026 · TSP Prep (self-review checklist)'
GUIDANCE = '''Use these TSP Prep 2026 self-review criteria. For interview responses,
assess a direct answer, a developed relevant example, connected ideas, varied
accurate sentences and precise varied vocabulary. Natural spoken contractions
are valid. For emails, cover every requested point, use an appropriate opening
and closing, a polite register, cohesive support, accurate complex sentences
and suitable vocabulary. For discussions, give a clear position, relevant
reasons and an example, connected ideas and accurate varied language. Assess
grammar, usage, spelling and punctuation with exact evidence. Distinguish errors
from optional stylistic changes. Suggested checklist targets: interview 110+
words and 42+ seconds, fewer than 3 fillers/hesitations and two transitions;
email 100+ words, discussion 120+ words, at least two multi-clause sentences.
These are self-review targets, not automatic deductions or demands for padding.
The source has no numerical scores. This app's strict 0–5 scale requires a 5
in every assessed area for an overall 5: fully fulfilled and developed task,
strong cohesion, broad precise vocabulary, proficient grammatical range and
almost no actual errors (at most one minor grammar/mechanics error in total).
A response with simple/repetitive language, weak support or several errors
cannot receive 5. Rate 4 for a strong response with a meaningful limitation;
3 for partial success; 2 for substantial weaknesses; 1 for minimal success;
0 for no meaningful English response. Count confirmed error occurrences only;
do not penalize machine recognition mistakes as if confirmed learner errors.
For extra worksheets and historical essays apply their own instructions,
not modern task length or email conventions. Do not assess pronunciation or
intonation from a transcript. A 5 means near-perfect in assessed areas only.'''

def apply_strict_rating(grade, response, exercise, metrics=None):
    assessment = grade.get('assessment', {})
    rubric = grade.get('rubric', {})
    top = (all(rubric.get(k) == 5 for k in ('taskFulfillment', 'development', 'language'))
           and all(assessment.get(k) is True for k in
                   ('complexGrammar', 'preciseVocabulary', 'strongCohesion', 'completeSupport'))
           and assessment.get('grammarErrors', 99) + assessment.get('mechanicalErrors', 99) <= 1
           and len(grade.get('corrections', [])) <= 1)
    if metrics and (metrics.get('longPauses', 0) >= 3 or
                    len(re.findall(r'\b(?:um|uh|erm)\b', response, re.I)) >= 3):
        top = False
    if grade.get('score', 0) >= 5 and not top:
        grade['score'] = 4
        grade.setdefault('improvements', []).append(
            'A 5 requires complete support, strong cohesion, varied precise language and almost no confirmed errors.')
    grade['rubricSource'] = SOURCE
    grade['ratingPolicy'] = 'Strict practice rating; the source checklist is not a numerical TOEFL scoring scale.'
    words = len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", response))
    grade['checklist'] = {'words': words}
    if exercise['type'] in ('email', 'discussion', 'interview'):
        grade['checklist']['suggestedWordTarget'] = {'email':100,'discussion':120,'interview':110}[exercise['type']]
    if metrics:
        grade['checklist'].update(duration=metrics.get('duration'), longPauses=metrics.get('longPauses'),
                                  recognizedFillers=len(re.findall(r'\b(?:um|uh|erm)\b', response, re.I)))
    return grade
