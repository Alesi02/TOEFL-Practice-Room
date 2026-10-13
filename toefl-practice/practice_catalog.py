"""One classification shared by practice views and full-test assembly."""
TASKS_2026={
    'Reading':{'complete_words','mcq'},
    'Listening':{'mcq'},
    'Writing':{'sentence','email','discussion'},
    'Speaking':{'repeat','interview'},
}

def is_toefl_2026(item):
    return (item.get('type') in TASKS_2026.get(item.get('section'),set())
            and item.get('edition')!='supplementary'
            and not item.get('textPrompt'))

def classify(item):
    item['practiceCategory']='toefl2026' if is_toefl_2026(item) else 'extra'
    return item
