"""
JarvisApp — Tkinter shell + animation loop. The orchestrator that ties
capture, brain, TTS and UI together.

Behavior is identical to the original 1828-line jarvis.py — only the
internals are rewired through the echo/ package.
"""
import math
import random
import threading
import time
from datetime import datetime

import numpy as np
import tkinter as tk
from PIL import Image, ImageTk

from echo import state
from echo.brain import call_ai_backend, history
from echo.capture import AudioCapture
from echo.config import PYGAME_OK, SLEEP_TIMEOUT
from echo.workers import transcriber
from echo.context.desktop import get_desktop_context
from echo.context.greeting import build_wake_greeting
from echo.context.system_health import get_system_health
from echo.stt import voice_to_text
from echo.tts import play_wake_song, speak_response
from echo.tts.edge import speak_edge_tts
from echo.tts.minimax import speak_minimax
from echo.tts.pyttsx import speak_pyttsx3
from echo.ui.colors import C, FPS, FRAME_MS, NUM_DOTS, SIDEBAR_W, lerp
from echo.ui.fonts import draw_dot_text
from echo.ui.globe import DotGlobe

if PYGAME_OK:
    import pygame


class JarvisApp:
    def __init__(self):
        # Hidden root stays in taskbar; real UI is a Toplevel
        self._tk_root = tk.Tk()
        self._tk_root.title("E.C.H.O.")
        self._tk_root.attributes("-alpha", 0.0)  # invisible
        self._tk_root.geometry("1x1+0+0")
        self._tk_root.protocol("WM_DELETE_WINDOW", self._quit)
        self._tk_root.iconify()

        self.root = tk.Toplevel(self._tk_root)
        state.set_app_root(self.root)
        self.root.title("E.C.H.O.")
        self.root.configure(bg=C.bg)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.98)
        self._tk_root.bind("<Map>", lambda e: self._restore_from_taskbar())
        sx, sy = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = int(sx * 0.78), int(sy * 0.78)
        self.root.geometry(f"{w}x{h}+{(sx - w) // 2}+{(sy - h) // 2}")
        self._maximized = False

        self.tick = 0
        self.audio_smooth = 0.0
        self.bands_smooth = [0.0] * 8
        self.is_listening = False
        self.is_thinking = False
        self.response_text = ""
        self.tw_idx = 0
        self.tw_active = False
        self.drag = {"x": 0, "y": 0}
        self._ready = False
        self._sidebar_ready = False
        self.globe = None
        self._photo = None
        self._img_id = None
        self._sb_photo = None
        self._sb_img_id = None
        self._sb_peaks = np.zeros(8, dtype=np.float64)
        self._sb_h = 0

        # Sleep / wake state
        self.is_sleeping = True
        self.brightness_mult = 0.15
        self._brightness_target = 0.15
        self.last_interaction = time.time()
        self._waking_up = False

        self.audio = AudioCapture()
        self.audio.start()
        self._build_ui()
        self.root.bind("<Escape>", lambda e: self._quit())
        self.root.bind("<space>", lambda e: self._wake_up() if self.is_sleeping else None)
        self.root.bind("<F1>", lambda e: self._wake_up() if self.is_sleeping else None)
        self.root.after(80, self._animate)
        self._tk_root.mainloop()

    def _build_ui(self):
        # ---- Custom Title Bar ----
        tb = tk.Frame(self.root, bg=C.bg2, height=40)
        tb.pack(fill=tk.X, side=tk.TOP)
        tb.pack_propagate(False)
        tb.bind("<Button-1>", self._ds)
        tb.bind("<B1-Motion>", self._dm)
        tb.bind("<Double-Button-1>", lambda e: self._toggle_max())

        left = tk.Frame(tb, bg=C.bg2)
        left.pack(side=tk.LEFT, padx=14)
        left.bind("<Button-1>", self._ds)
        left.bind("<B1-Motion>", self._dm)
        tk.Label(left, text="◆", font=("Cascadia Code", 9), fg=C.purple,
                 bg=C.bg2).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(left, text="E.C.H.O.", font=("Cascadia Code", 11, "bold"),
                 fg=C.accent, bg=C.bg2).pack(side=tk.LEFT)
        tk.Label(left, text="//", font=("Cascadia Code", 9), fg=C.dim,
                 bg=C.bg2).pack(side=tk.LEFT, padx=(10, 6))
        tk.Label(left, text="Enhanced Cognitive Heuristic Operator",
                 font=("Segoe UI", 7), fg=C.muted, bg=C.bg2).pack(side=tk.LEFT)

        # Window buttons
        btn_frame = tk.Frame(tb, bg=C.bg2)
        btn_frame.pack(side=tk.RIGHT, padx=0)
        btn_h, btn_w = 40, 46
        cx, cy, s = btn_w // 2, btn_h // 2, 5

        # Close
        self._btn_close = tk.Canvas(btn_frame, width=btn_w, height=btn_h,
                                    bg=C.bg2, highlightthickness=0)
        self._btn_close.pack(side=tk.RIGHT)
        self._cl1 = self._btn_close.create_line(cx - s, cy - s, cx + s, cy + s, fill=C.muted, width=1.5)
        self._cl2 = self._btn_close.create_line(cx + s, cy - s, cx - s, cy + s, fill=C.muted, width=1.5)
        self._btn_close.bind("<Button-1>", lambda e: self._quit())
        self._btn_close.bind("<Enter>", lambda e: (
            self._btn_close.config(bg="#cc1830"),
            self._btn_close.itemconfig(self._cl1, fill="white"),
            self._btn_close.itemconfig(self._cl2, fill="white")))
        self._btn_close.bind("<Leave>", lambda e: (
            self._btn_close.config(bg=C.bg2),
            self._btn_close.itemconfig(self._cl1, fill=C.muted),
            self._btn_close.itemconfig(self._cl2, fill=C.muted)))

        # Maximize
        self._btn_max = tk.Canvas(btn_frame, width=btn_w, height=btn_h,
                                  bg=C.bg2, highlightthickness=0)
        self._btn_max.pack(side=tk.RIGHT)
        self._mr = self._btn_max.create_rectangle(cx - s, cy - s, cx + s, cy + s, outline=C.muted, width=1.5)
        self._btn_max.bind("<Button-1>", lambda e: self._toggle_max())
        self._btn_max.bind("<Enter>", lambda e: (
            self._btn_max.config(bg=C.dim), self._btn_max.itemconfig(self._mr, outline=C.accent)))
        self._btn_max.bind("<Leave>", lambda e: (
            self._btn_max.config(bg=C.bg2), self._btn_max.itemconfig(self._mr, outline=C.muted)))

        # Minimize
        self._btn_min = tk.Canvas(btn_frame, width=btn_w, height=btn_h,
                                  bg=C.bg2, highlightthickness=0)
        self._btn_min.pack(side=tk.RIGHT)
        self._ml = self._btn_min.create_line(cx - s, cy, cx + s, cy, fill=C.muted, width=1.5)
        self._btn_min.bind("<Button-1>", lambda e: self._minimize())
        self._btn_min.bind("<Enter>", lambda e: (
            self._btn_min.config(bg=C.dim), self._btn_min.itemconfig(self._ml, fill=C.accent)))
        self._btn_min.bind("<Leave>", lambda e: (
            self._btn_min.config(bg=C.bg2), self._btn_min.itemconfig(self._ml, fill=C.muted)))

        # Clock
        self.clock_lbl = tk.Label(tb, text="", font=("Cascadia Code", 9), fg=C.muted, bg=C.bg2)
        self.clock_lbl.pack(side=tk.RIGHT, padx=(0, 16))

        tk.Frame(self.root, bg=C.border, height=1).pack(fill=tk.X)

        # ---- Middle: sidebar + canvas ----
        mid = tk.Frame(self.root, bg=C.bg)
        mid.pack(fill=tk.BOTH, expand=True)

        self.sidebar = tk.Canvas(mid, bg=C.sidebar, width=SIDEBAR_W, highlightthickness=0)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        tk.Frame(mid, bg=C.border, width=1).pack(side=tk.LEFT, fill=tk.Y)

        self.canvas = tk.Canvas(mid, bg=C.bg, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # ---- Bottom panel ----
        bp = tk.Frame(self.root, bg=C.panel)
        bp.pack(fill=tk.X, side=tk.BOTTOM)

        border_cv = tk.Canvas(bp, bg=C.panel, height=2, highlightthickness=0)
        border_cv.pack(fill=tk.X)
        border_cv.create_line(0, 1, 2000, 1, fill=C.border, width=1)
        border_cv.create_line(80, 0, 400, 0, fill=C.purple_d, width=2)

        # Response area
        resp_frame = tk.Frame(bp, bg=C.panel)
        resp_frame.pack(fill=tk.X, padx=24, pady=(8, 2))

        # Status badge row
        status_row = tk.Frame(resp_frame, bg=C.panel)
        status_row.pack(fill=tk.X)

        self.sdot_cv = tk.Canvas(status_row, width=8, height=8, bg=C.panel, highlightthickness=0)
        self.sdot_cv.pack(side=tk.LEFT, pady=2)
        self.sdot_id = self.sdot_cv.create_oval(1, 1, 7, 7, fill=C.muted, outline="")
        self.slbl = tk.Label(status_row, text="SLEEPING", font=("Cascadia Code", 7, "bold"),
                             fg=C.purple, bg=C.panel)
        self.slbl.pack(side=tk.LEFT, padx=(5, 0))

        # Wake word hint
        self.wake_hint = tk.Label(status_row, text='say "hey echo" or press space',
                                  font=("Segoe UI", 8), fg=C.dim, bg=C.panel)
        self.wake_hint.pack(side=tk.RIGHT)

        # Response text
        self.resp = tk.Label(resp_frame, text="", font=("Segoe UI", 10), fg=C.accent2,
                             bg=C.panel, anchor="w", justify="left", wraplength=800)
        self.resp.pack(fill=tk.X, pady=(4, 4))

        # ---- Input bar ----
        inp_outer = tk.Frame(bp, bg=C.card_br, padx=1, pady=1)
        inp_outer.pack(fill=tk.X, padx=24, pady=(4, 14))
        self._inp_border = inp_outer

        inp_inner = tk.Frame(inp_outer, bg=C.card)
        inp_inner.pack(fill=tk.X)

        tk.Label(inp_inner, text=" >_", font=("Cascadia Code", 12, "bold"),
                 fg=C.purple_d, bg=C.card).pack(side=tk.LEFT, padx=(10, 0))

        self.entry = tk.Entry(inp_inner, font=("Segoe UI", 12), bg=C.card, fg=C.accent,
                              insertbackground=C.purple, relief="flat", border=0)
        self.entry.pack(fill=tk.X, padx=(6, 10), pady=12, side=tk.LEFT, expand=True)
        self.entry.bind("<Return>", self._on_submit)
        self.entry.bind("<FocusIn>", lambda e: (self._clr_ph(), inp_outer.config(bg=C.purple2)))
        self.entry.bind("<FocusOut>", lambda e: inp_outer.config(bg=C.card_br))

        # Mic button
        self.mic_btn = tk.Label(inp_inner, text="◉", font=("Cascadia Code", 16),
                                fg=C.muted, bg=C.card, cursor="hand2")
        self.mic_btn.pack(side=tk.RIGHT, padx=(0, 6))
        self.mic_btn.bind("<Button-1>", self._on_mic)
        self.mic_btn.bind("<Enter>", lambda e: self.mic_btn.config(fg=C.purple))
        self.mic_btn.bind("<Leave>", lambda e: self.mic_btn.config(
            fg=C.muted if not self.is_listening else C.danger))

        # Send button
        self.send_btn = tk.Label(inp_inner, text="↵", font=("Cascadia Code", 16, "bold"),
                                 fg=C.muted, bg=C.card, cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, padx=(0, 4))
        self.send_btn.bind("<Button-1>", self._on_submit)
        self.send_btn.bind("<Enter>", lambda e: self.send_btn.config(fg=C.purple))
        self.send_btn.bind("<Leave>", lambda e: self.send_btn.config(fg=C.muted))

        self._set_ph()

    # ---- Sidebar EQ ----
    def _init_sidebar(self):
        sh = self.sidebar.winfo_height()
        if sh < 50:
            return
        self._sb_h = sh
        img = Image.new("RGB", (SIDEBAR_W, sh), (6, 6, 9))
        self._sb_photo = ImageTk.PhotoImage(img)
        self._sb_img_id = self.sidebar.create_image(0, 0, image=self._sb_photo, anchor="nw")
        self._sidebar_ready = True

    def _draw_sidebar(self, bands, audio, t):
        if not self._sidebar_ready:
            return
        sw, sh = SIDEBAR_W, self._sb_h
        buf = np.zeros((sh, sw, 3), dtype=np.uint8)
        buf[:, :] = [6, 6, 9]

        margin, gap = 4, 2
        bar_w = max(2, (sw - margin * 2 - gap * 7) // 8)
        bar_area_h = sh - 24

        for i in range(8):
            lvl = min(1.0, bands[i] * 3.0)
            if lvl > self._sb_peaks[i]:
                self._sb_peaks[i] = lvl
            else:
                self._sb_peaks[i] *= 0.92

            bx = margin + i * (bar_w + gap)
            bar_bottom, bar_top_max = sh - 4, 20
            fill_h = int(bar_area_h * lvl)
            fill_top = bar_bottom - fill_h

            buf[bar_top_max:bar_bottom, bx:bx + bar_w] = [10, 10, 14]

            if fill_h > 0:
                for y in range(fill_top, bar_bottom):
                    frac = (bar_bottom - y) / bar_area_h
                    if frac < 0.5:
                        r = int(frac * 2 * 40)
                        g = int(80 + frac * 2 * 150)
                        b = int(120 + frac * 2 * 135)
                    else:
                        f2 = (frac - 0.5) * 2
                        r = int(40 + f2 * 180)
                        g = int(230 + f2 * 25)
                        b = 255
                    buf[y, bx:bx + bar_w] = [r, g, b]

            peak_y = max(bar_top_max, min(bar_bottom - 1, bar_bottom - int(bar_area_h * self._sb_peaks[i])))
            if self._sb_peaks[i] > 0.05:
                buf[peak_y, bx:bx + bar_w] = [220, 230, 255]

            if fill_h > 3:
                gt = max(bar_top_max, fill_top - 3)
                gb = min(bar_bottom, fill_top + 4)
                gx0, gx1 = max(0, bx - 2), min(sw, bx + bar_w + 2)
                region = buf[gt:gb, gx0:gx1].astype(np.int16)
                region[:, :, 1] += int(25 + lvl * 40)
                region[:, :, 2] += int(25 + lvl * 40)
                np.clip(region, 0, 255, out=region)
                buf[gt:gb, gx0:gx1] = region.astype(np.uint8)

        rms_w = int(audio * (sw - margin * 2))
        if rms_w > 0:
            intensity = int(60 + audio * 195)
            buf[8:11, margin:margin + rms_w] = [int(intensity * 0.3), int(intensity * 0.8), intensity]

        self._sb_photo.paste(Image.fromarray(buf))

    # ---- Sleep / Wake ----
    def _wake_up(self):
        if not self.is_sleeping:
            return
        self.is_sleeping = False
        # Tell capture/audio.py to stop running wake-word whisper now that
        # we're online. The always-on transcriber stays disabled until the
        # greeting finishes (otherwise it would record our own TTS).
        state.set_sleeping(False)
        self._waking_up = True
        self._brightness_target = 1.0
        self._stat("WAKING UP", "wake")
        self.last_interaction = time.time()

        def _wake_thread():
            health_result = [{}]
            context_result = [{}]

            def _scan_health():
                health_result[0] = get_system_health()

            def _scan_context():
                context_result[0] = get_desktop_context()

            t1 = threading.Thread(target=_scan_health, daemon=True)
            t2 = threading.Thread(target=_scan_context, daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=4)
            t2.join(timeout=4)

            try:
                ctx = context_result[0]
                health = health_result[0]
                greeting = build_wake_greeting(ctx, health)

                context_msg = (
                    f"[SYSTEM CONTEXT: ECHO just woke up. "
                    f"Time: {ctx.get('time', '?')}, {ctx.get('date', '?')}. "
                    f"Open apps: {', '.join(ctx.get('app_names', []))}. "
                    f"Activities: {', '.join(ctx.get('activities', []))}. "
                    f"Battery: {health.get('battery_percent', 'N/A')}%, "
                    f"RAM used: {health.get('ram_percent_used', 'N/A')}%, "
                    f"Internet: {'connected' if health.get('internet') else 'disconnected'}. "
                    f"The user was greeted and asked where to begin.]"
                )
                history.append("system", context_msg)
            except Exception:
                greeting = "Online and ready, Sir. Where shall we begin?"

            # Play song + speak greeting in parallel
            play_wake_song()
            time.sleep(3)  # let the music build

            self.root.after(0, lambda: self.resp.config(text=greeting))

            # Blocking TTS chain so we know when speech finishes
            if not speak_minimax(greeting):
                if not speak_edge_tts(greeting):
                    speak_pyttsx3(greeting)

            self._waking_up = False
            # Greeting finished — start always-on capture. Any speech in the
            # room from now on flows: mic -> bus -> transcriber -> SQLite.
            transcriber.enable()
            self.root.after(0, lambda: self._stat("ONLINE", "idle"))

        threading.Thread(target=_wake_thread, daemon=True).start()

    def _go_to_sleep(self):
        if self.is_sleeping:
            return
        # Stop always-on capture FIRST, then mark sleeping. Order matters:
        # the transcriber's _on_chunk also checks state.is_sleeping, so this
        # double-gate is belt-and-suspenders.
        transcriber.disable()
        state.set_sleeping(True)
        self.is_sleeping = True
        self._waking_up = False
        self._brightness_target = 0.15
        self._stat("SLEEPING", "sleep")

    # ---- Helpers ----
    def _set_ph(self):
        if not self.entry.get():
            self.entry.insert(0, "ask echo something...")
            self.entry.config(fg=C.dim)

    def _clr_ph(self):
        if self.entry.get() == "ask echo something...":
            self.entry.delete(0, tk.END)
            self.entry.config(fg=C.accent)

    def _ds(self, e):
        self.drag["x"] = e.x_root - self.root.winfo_x()
        self.drag["y"] = e.y_root - self.root.winfo_y()

    def _dm(self, e):
        if self._maximized:
            return
        self.root.geometry(f"+{e.x_root - self.drag['x']}+{e.y_root - self.drag['y']}")

    def _minimize(self):
        self.root.withdraw()
        self._tk_root.deiconify()
        self._tk_root.iconify()

    def _restore_from_taskbar(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _toggle_max(self):
        if self._maximized:
            w, h = 1050, 680
            sx, sy = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            self.root.geometry(f"{w}x{h}+{(sx - w) // 2}+{(sy - h) // 2}")
            self._maximized = False
        else:
            sx, sy = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            self.root.geometry(f"{sx}x{sy}+0+0")
            self._maximized = True
        self._ready = False
        self._sidebar_ready = False

    def _on_submit(self, e=None):
        if self.is_sleeping:
            return
        self._clr_ph()
        t = self.entry.get().strip()
        if not t or t == "ask echo something..." or self.is_thinking:
            return
        self.entry.delete(0, tk.END)
        self.last_interaction = time.time()
        self._stat("PROCESSING", "think")
        self.is_thinking = True
        self.resp.config(text="")

        def w():
            r = call_ai_backend(t)
            self.root.after(0, lambda: self._handle_response(r))

        threading.Thread(target=w, daemon=True).start()

    def _handle_response(self, text):
        if text == "__SLEEP__":
            self.is_thinking = False
            self.resp.config(text="Going to sleep, Sir.")
            speak_response("Going to sleep, Sir.")
            self.root.after(2000, self._go_to_sleep)
            self._set_ph()
            return
        if text == "__EXIT__":
            speak_response("Goodbye, Sir.")
            self.root.after(2000, self._quit)
            return
        self._show_resp(text)

    def _on_mic(self, e=None):
        if self.is_sleeping or self.is_listening or self.is_thinking:
            return
        # Pause always-on capture for the duration of the mic press —
        # voice_to_text opens its own 16kHz stream and we don't want both
        # paths transcribing the same words.
        transcriber.disable()
        self.is_listening = True
        self.last_interaction = time.time()
        self.mic_btn.config(fg=C.danger)
        self._stat("LISTENING", "listen")

        def w():
            t = voice_to_text()
            self.root.after(0, lambda: self._vdone(t))

        threading.Thread(target=w, daemon=True).start()

    def _vdone(self, text):
        self.is_listening = False
        self.mic_btn.config(fg=C.muted)
        # Resume always-on capture if we're still online.
        if not self.is_sleeping:
            transcriber.enable()
        if text:
            self.entry.delete(0, tk.END)
            self.entry.config(fg=C.accent)
            self.entry.insert(0, text)
            self._on_submit()
        else:
            self._stat("ONLINE", "idle")

    def _show_resp(self, text):
        self.is_thinking = False
        self.response_text = text
        self.tw_idx = 0
        self.tw_active = True
        self._stat("RESPONDING", "think")
        self._tw()
        speak_response(text)

    def _tw(self):
        if not self.tw_active:
            return
        if self.tw_idx < len(self.response_text):
            self.tw_idx = min(self.tw_idx + random.randint(1, 3), len(self.response_text))
            self.resp.config(text=self.response_text[:self.tw_idx] + "█")
            self.root.after(22, self._tw)
        else:
            self.tw_active = False
            self.resp.config(text=self.response_text)
            self._stat("ONLINE", "idle")
            self._set_ph()

    def _stat(self, text, mode="idle"):
        self.slbl.config(text=text)
        colors = {
            "idle": C.green, "think": C.warning, "listen": C.danger,
            "sleep": C.muted, "wake": C.cyan,
        }
        self.sdot_cv.itemconfig(self.sdot_id, fill=colors.get(mode, C.green))

    def _init_renderer(self, cw, ch):
        self.globe = DotGlobe(NUM_DOTS, cw, ch)
        img = Image.new("RGB", (cw, ch), (6, 6, 9))
        self._photo = ImageTk.PhotoImage(img)
        self._img_id = self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self._cw, self._ch = cw, ch
        self._ready = True

    # ---- Main animation loop ----
    def _animate(self):
        self.tick += 1
        t = self.tick / FPS

        raw = self.audio.rms if self.audio.running else 0.0
        self.audio_smooth = lerp(self.audio_smooth, min(raw * 6, 1.0), 0.22)
        a = self.audio_smooth
        for i in range(8):
            tgt = self.audio.bands[i] if self.audio.running else 0.0
            self.bands_smooth[i] = lerp(self.bands_smooth[i], min(tgt * 4, 1.0), 0.25)

        if self.is_thinking:
            a = max(a, 0.3 + 0.12 * math.sin(t * 3))
        if self.is_listening:
            a = max(a, 0.2 + 0.08 * math.sin(t * 5))

        # Wake from any source (clap / whistle / wakeword)
        if self.audio.wake_detected:
            self.audio.wake_detected = False
            if self.is_sleeping:
                self._wake_up()

        # Auto sleep
        if not self.is_sleeping and not self._waking_up:
            if time.time() - self.last_interaction > SLEEP_TIMEOUT:
                self._go_to_sleep()

        # Smooth brightness transition
        self.brightness_mult = lerp(self.brightness_mult, self._brightness_target, 0.03)

        # Sleep mode breathing
        if self.is_sleeping:
            a = 0.02 + 0.03 * math.sin(t * 0.5)

        if not self._ready:
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            if cw > 100 and ch > 100:
                self._init_renderer(cw, ch)
                self._init_sidebar()
            else:
                self.root.after(50, self._animate)
                return

        self.clock_lbl.config(text=datetime.now().strftime("%H:%M:%S"))

        img = self.globe.render(t, a, self.bands_smooth, self.brightness_mult)
        self._photo.paste(img)

        # Canvas overlays
        self.canvas.delete("ov")
        cw, ch = self._cw, self._ch
        dcx, dcy = cw // 2, ch // 2
        sr = min(cw, ch) * 0.28

        r1 = sr + 20 + a * 8 + math.sin(t * 0.4) * 3
        self.canvas.create_oval(dcx - r1, dcy - r1, dcx + r1, dcy + r1,
                                outline=C.dim, width=1, dash=(3, 8), tags=("ov",))
        r2 = sr + 48 + a * 12 + math.sin(t * 0.6) * 4
        self.canvas.create_oval(dcx - r2, dcy - r2, dcx + r2, dcy + r2,
                                outline="#14141c", width=1, dash=(2, 10), tags=("ov",))

        for i in range(24):
            ang = (i / 24) * math.tau + t * 0.15
            ri, ro = r2 - 3, r2 + 3
            x1 = dcx + math.cos(ang) * ri
            y1 = dcy + math.sin(ang) * ri
            x2 = dcx + math.cos(ang) * ro
            y2 = dcy + math.sin(ang) * ro
            c = C.muted if i % 4 == 0 else "#16161e"
            self.canvas.create_line(x1, y1, x2, y2, fill=c, width=1, tags=("ov",))

        ly = dcy + sr - 10
        draw_dot_text(self.canvas, "E.C.H.O.", dcx, ly,
                      dot=4.0, sp=1.4, color=C.dot_on, ghost=C.dot_off)

        if self.is_sleeping:
            st_, sc = "SLEEPING", C.muted
        elif self._waking_up:
            st_, sc = "WAKING UP", C.cyan
        elif self.is_listening:
            st_, sc = "LISTENING", C.danger
        elif self.is_thinking:
            st_, sc = "PROCESSING", C.warning
        else:
            st_, sc = "ONLINE", C.muted
        draw_dot_text(self.canvas, st_, dcx, ly + 36, dot=2.0, sp=1.3, color=sc, ghost="")

        # Manual wake button when sleeping
        if self.is_sleeping:
            pulse = 0.4 + 0.3 * math.sin(t * 2)
            v = int(pulse * 100)
            wake_col = f"#{v:02x}{v:02x}{int(v * 1.2):02x}"
            wake_id = self.canvas.create_text(
                dcx, ly + 65, text="[ PRESS SPACE TO WAKE ]",
                font=("Cascadia Code", 9), fill=wake_col, tags=("ov",))
            self.canvas.tag_bind(wake_id, "<Button-1>", lambda e: self._wake_up())

        # Sidebar
        self._draw_sidebar(self.bands_smooth, a, t)

        # Status dot pulse
        if self.is_thinking or self.is_listening:
            p = 0.5 + 0.5 * math.sin(t * 6)
            c = C.warning if self.is_thinking else C.danger
            self.sdot_cv.itemconfig(self.sdot_id, fill=c if p > 0.5 else C.dim)

        self.root.after(FRAME_MS, self._animate)

    def _quit(self):
        transcriber.disable()
        self.audio.stop()
        if PYGAME_OK:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        self.root.destroy()
        self._tk_root.destroy()
