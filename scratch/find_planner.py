with open('student.src.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, l in enumerate(lines):
    if 'function initplanner' in l.lower() or 'function savecountdown' in l.lower() or 'function addgoal' in l.lower() or 'function addrevision' in l.lower():
        print(f'{i+1}: {l.strip()[:100]}')
