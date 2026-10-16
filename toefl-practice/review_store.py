"""Saved reviews, summaries and one-time presentation upgrades."""
import json
from pathlib import Path
import uuid


def summaries(rows):
    summary, priorities = {}, []
    for section in ('Reading', 'Listening', 'Writing', 'Speaking'):
        group = [row for row in rows if row['section'] == section]
        if not group:
            continue
        grades = [row['grade'] for row in group]
        objective = [grade for grade in grades if 'points' in grade]
        rubric = [grade['score'] for grade in grades if isinstance(grade.get('score'), (int, float))
                  and grade.get('method') in ('local AI rubric review', 'local rubric review', 'transcript word comparison')]
        repeat = [grade['accuracy'] for grade in grades if 'accuracy' in grade]
        points, total = sum(grade['points'] for grade in objective), sum(grade['total'] for grade in objective)
        summary[section] = {'attempted': len(group), 'points': points, 'total': total,
                            'accuracy': round(points/total*100, 1) if total else None,
                            'rubricAverage': round(sum(rubric)/len(rubric), 2) if rubric else None,
                            'repeatAccuracy': round(sum(repeat)/len(repeat), 1) if repeat else None,
                            'incomplete': sum(bool(grade.get('error') or grade.get('rubricScoreError')) for grade in grades)}
    for row in rows:
        for tip in row['grade'].get('improvements', []):
            text = row['section']+': '+tip
            if text not in priorities:
                priorities.append(text)
    return summary, priorities[:6]


def save_result(private, result):
    directory = Path(private)/'history'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/(result['id']+'.json')
    temporary = directory/('.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def upgrade_history(private, exercises):
    """Keep scores, responses, dates and recordings; rebuild legacy feedback text."""
    from feedback_engine import VERSION, upgrade_saved_grade
    changed = []
    for path in sorted((Path(private)/'history').glob('*.json')):
        try:
            original = path.read_bytes()
            result = json.loads(original)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # An unrelated damaged history file must not prevent app startup.
            continue
        before = json.dumps(result, ensure_ascii=False, sort_keys=True)
        for row in result.get('rows', []):
            exercise = exercises.get(row['id'], {'type': row['type']})
            upgrade_saved_grade(row['grade'], exercise, str(row.get('response', '')))
        if json.dumps(result, ensure_ascii=False, sort_keys=True) == before:
            continue
        backup = Path(private)/'feedback-backups'/VERSION/path.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(original)
        result['summary'], result['priorities'] = summaries(result['rows'])
        save_result(private, result)
        changed.append(result['id'])
    return changed
