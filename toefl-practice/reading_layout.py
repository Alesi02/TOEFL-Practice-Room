"""Recover source paragraph boundaries without changing the passage's words."""
import re
import unicodedata


def _indexed_text(text):
    characters, positions = [], []
    for index, character in enumerate(text):
        for normalized in unicodedata.normalize('NFKC', character):
            if not normalized.isspace():
                characters.append(normalized)
                positions.append(index)
    return ''.join(characters), positions


def restore_layout(passage, source_layout):
    """Copy only verified source boundaries; printed line wrapping is discarded."""
    target, target_positions = _indexed_text(passage)
    source, source_positions = _indexed_text(source_layout)
    start = source.find(target) if target else -1
    if start < 0:
        return passage
    boundaries = {}
    for index in range(1, len(target)):
        left = source_positions[start + index - 1]
        right = source_positions[start + index]
        whitespace = source_layout[left + 1:right]
        if '\n' not in whitespace:
            continue
        previous_line = source_layout[:left + 1].split('\n')[-1].strip()
        next_line = source_layout[right:].split('\n')[0].strip()
        if whitespace.count('\n') >= 2:
            boundaries[target_positions[index]] = '\n\n'
        elif (re.match(r'^(?:Subject:|From:|To:|Date:|Dear\b|Hello\b|Hi\b)', next_line)
              or re.match(r'^(?:Read (?:a|an)\b|Subject:|From:|To:|Date:|Best regards|Kind regards|Sincerely|Thank you[,!]?\s*$)', previous_line)):
            boundaries[target_positions[index]] = '\n'
    result, cursor = [], 0
    for position, separator in sorted(boundaries.items()):
        result.extend((passage[cursor:position].rstrip(), separator))
        cursor = position
    result.append(passage[cursor:])
    return ''.join(result)
