"""Snapshot open windows and infer a coarse activity description."""

import json
import subprocess
from datetime import datetime


def get_desktop_context():
    ctx = {}
    now = datetime.now()
    hour = now.hour
    ctx['time'] = now.strftime("%I:%M %p")
    ctx['date'] = now.strftime("%A, %B %d")

    if hour < 12:
        ctx['greeting'] = "Good morning"
    elif hour < 17:
        ctx['greeting'] = "Good afternoon"
    elif hour < 21:
        ctx['greeting'] = "Good evening"
    else:
        ctx['greeting'] = "Working late I see"

    # Open windows
    try:
        result = subprocess.run(
            ['powershell', '-Command',
             'Get-Process | Where-Object {$_.MainWindowTitle -ne ""} | '
             'Select-Object ProcessName, MainWindowTitle | ConvertTo-Json'],
            capture_output=True, text=True, timeout=5)
        windows = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(windows, dict):
            windows = [windows]
        ctx['open_windows'] = windows
    except Exception:
        ctx['open_windows'] = []

    # Categorize
    activities = []
    app_names = []
    for w in ctx['open_windows']:
        name = w.get('ProcessName', '').lower()
        title = w.get('MainWindowTitle', '')
        app_names.append(name)

        if any(x in name for x in ['brave', 'chrome', 'firefox', 'edge', 'opera']):
            tl = title.lower()
            if 'youtube' in tl:
                activities.append('watching YouTube')
            elif 'github' in tl:
                activities.append('working on GitHub')
            elif 'gmail' in tl or 'mail' in tl:
                activities.append('checking emails')
            elif 'chatgpt' in tl or 'claude' in tl:
                activities.append('chatting with AI')
            elif 'stackoverflow' in tl:
                activities.append('debugging something')
            elif 'figma' in tl:
                activities.append('designing in Figma')
            else:
                activities.append('browsing the web')
        elif any(x in name for x in ['code', 'vscode', 'cursor']):
            activities.append('coding in VS Code')
        elif 'claude' in name:
            activities.append('using Claude Code')
        elif any(x in name for x in ['word', 'winword']):
            activities.append('writing a document')
        elif 'excel' in name:
            activities.append('working on a spreadsheet')
        elif any(x in name for x in ['powerpoint', 'powerpnt']):
            activities.append('making a presentation')
        elif 'notion' in name:
            activities.append('organizing in Notion')
        elif any(x in name for x in ['slack', 'teams', 'discord']):
            activities.append('in a chat app')
        elif any(x in name for x in ['spotify', 'vlc', 'musicbee']):
            activities.append('listening to music')
        elif any(x in name for x in ['photoshop', 'gimp']):
            activities.append('editing images')
        elif any(x in name for x in ['premiere', 'resolve', 'capcut']):
            activities.append('editing video')
        elif any(x in name for x in ['terminal', 'cmd', 'powershell', 'windowsterminal']):
            activities.append('working in the terminal')

    seen = set()
    unique = [a for a in activities if a not in seen and not seen.add(a)]
    ctx['activities'] = unique
    ctx['app_names'] = list(set(app_names))
    return ctx
