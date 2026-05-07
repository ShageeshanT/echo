"""Build a contextual wake-up greeting from health + desktop snapshots."""


def build_wake_greeting(ctx, health):
    parts = []

    # Greeting + time
    parts.append(f"{ctx['greeting']}. It's {ctx['time']} on {ctx['date']}.")

    # System health
    notes = []
    bp = health.get('battery_percent')
    if bp is not None:
        if health.get('battery_plugged'):
            notes.append("fully charged and plugged in" if bp >= 95 else f"charging at {bp}%")
        else:
            if bp < 20:
                notes.append(f"battery is critically low at {bp}%, you should plug in")
            elif bp < 40:
                notes.append(f"battery at {bp}%, might want to plug in soon")
            else:
                notes.append(f"battery at {bp}%")

    wifi = health.get('wifi_name')
    internet = health.get('internet', False)
    ping = health.get('ping_ms')
    if not internet:
        notes.append("no internet connection detected")
    elif wifi:
        if ping and ping > 150:
            notes.append(f"connected to {wifi} but sluggish at {ping}ms")
        elif ping and ping > 50:
            notes.append(f"connected to {wifi}, decent at {ping}ms")
        else:
            notes.append(f"connected to {wifi}, network looks solid")

    ram = health.get('ram_percent_used')
    ram_avail = health.get('ram_available_gb')
    if ram and ram > 85:
        notes.append(f"RAM running tight at {ram}% used, only {ram_avail}GB free")
    elif ram and ram > 70:
        notes.append(f"{ram_avail}GB RAM available")

    cpu = health.get('cpu_percent')
    if cpu and cpu > 80:
        notes.append(f"CPU running hot at {cpu}%")

    disk = health.get('disk_free_gb')
    if disk is not None and disk < 20:
        notes.append(f"disk space getting low, {disk}GB free")

    if notes:
        if len(notes) == 1:
            parts.append(f"System check: {notes[0]}.")
        else:
            parts.append(f"System check: {', '.join(notes[:-1])}, and {notes[-1]}.")
    else:
        parts.append("All systems are running smooth.")

    # Desktop activity
    acts = ctx.get('activities', [])
    if not acts:
        parts.append("Your desktop is clean. Fresh start.")
    elif len(acts) == 1:
        parts.append(f"Looks like you were {acts[0]}.")
    elif len(acts) == 2:
        parts.append(f"I see you were {acts[0]} and {acts[1]}.")
    else:
        listed = ', '.join(acts[:3])
        rem = len(acts) - 3
        if rem > 0:
            parts.append(f"You've got quite a bit going on, {listed}, and {rem} other {'thing' if rem == 1 else 'things'}.")
        else:
            parts.append(f"Looks like you were {listed}.")

    parts.append("What's on the agenda?")
    return ' '.join(parts)
