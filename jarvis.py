"""
E.C.H.O. — Enhanced Cognitive Heuristic Operator
3D dot-globe · vertical audio visualizer · animated background strokes
"""

import tkinter as tk
import math
import random
import threading
import time
from datetime import datetime

import numpy as np
from PIL import Image, ImageTk

# Audio
AUDIO_OK = False
try:
    import pyaudio
    AUDIO_OK = True
except ImportError:
    pass
try:
    import speech_recognition as sr
    SR_OK = True
except ImportError:
    SR_OK = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WIN_W, WIN_H = 950, 620
PANEL_H = 145
TITLE_H = 38
SIDEBAR_W = 48
FPS = 38
FRAME_MS = int(1000 / FPS)
NUM_DOTS = 7000
NUM_STROKES = 18


class Col:
    bg      = "#080808"
    bg2     = "#0c0c0c"
    panel   = "#0a0a0a"
    sidebar = "#0a0a0a"
    border  = "#1a1a1a"
    accent  = "#d8d8d8"
    accent2 = "#888888"
    muted   = "#444444"
    dim     = "#222222"
    green   = "#00e676"
    cyan    = "#00e5ff"
    cyan_dim = "#004d55"
    danger  = "#ff1744"
    warning = "#ffab00"
    dot_on  = "#d0d0d0"
    dot_off = "#161616"


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# 5x7 Dot-matrix font (compact)
# ---------------------------------------------------------------------------
_F = {
    'A':["01110","10001","10001","11111","10001","10001","10001"],
    'B':["11110","10001","10001","11110","10001","10001","11110"],
    'C':["01110","10001","10000","10000","10000","10001","01110"],
    'D':["11110","10001","10001","10001","10001","10001","11110"],
    'E':["11111","10000","10000","11110","10000","10000","11111"],
    'F':["11111","10000","10000","11110","10000","10000","10000"],
    'G':["01110","10001","10000","10111","10001","10001","01110"],
    'H':["10001","10001","10001","11111","10001","10001","10001"],
    'I':["11111","00100","00100","00100","00100","00100","11111"],
    'J':["00111","00010","00010","00010","00010","10010","01100"],
    'K':["10001","10010","10100","11000","10100","10010","10001"],
    'L':["10000","10000","10000","10000","10000","10000","11111"],
    'M':["10001","11011","10101","10101","10001","10001","10001"],
    'N':["10001","11001","10101","10011","10001","10001","10001"],
    'O':["01110","10001","10001","10001","10001","10001","01110"],
    'P':["11110","10001","10001","11110","10000","10000","10000"],
    'Q':["01110","10001","10001","10001","10101","10010","01101"],
    'R':["11110","10001","10001","11110","10100","10010","10001"],
    'S':["01110","10001","10000","01110","00001","10001","01110"],
    'T':["11111","00100","00100","00100","00100","00100","00100"],
    'U':["10001","10001","10001","10001","10001","10001","01110"],
    'V':["10001","10001","10001","10001","10001","01010","00100"],
    'W':["10001","10001","10001","10101","10101","11011","10001"],
    'X':["10001","10001","01010","00100","01010","10001","10001"],
    'Y':["10001","10001","01010","00100","00100","00100","00100"],
    'Z':["11111","00001","00010","00100","01000","10000","11111"],
    '0':["01110","10001","10011","10101","11001","10001","01110"],
    '1':["00100","01100","00100","00100","00100","00100","01110"],
    '2':["01110","10001","00001","00110","01000","10000","11111"],
    '3':["01110","10001","00001","00110","00001","10001","01110"],
    '4':["00010","00110","01010","10010","11111","00010","00010"],
    '5':["11111","10000","11110","00001","00001","10001","01110"],
    '6':["01110","10000","10000","11110","10001","10001","01110"],
    '7':["11111","00001","00010","00100","01000","01000","01000"],
    '8':["01110","10001","10001","01110","10001","10001","01110"],
    '9':["01110","10001","10001","01111","00001","00001","01110"],
    '.':["00000","00000","00000","00000","00000","00000","01100"],
    ':':["00000","01100","01100","00000","01100","01100","00000"],
    '-':["00000","00000","00000","11111","00000","00000","00000"],
    ' ':["00000","00000","00000","00000","00000","00000","00000"],
    '+':["00000","00100","00100","11111","00100","00100","00000"],
    '!':["00100","00100","00100","00100","00100","00000","00100"],
    '?':["01110","10001","00001","00110","00100","00000","00100"],
    '"':["01010","01010","01010","00000","00000","00000","00000"],
    '/':["00001","00010","00010","00100","01000","01000","10000"],
    ',':["00000","00000","00000","00000","00000","01100","00100"],
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _F[_c] = _F[_c.upper()]


def draw_dot_text(cv, text, x, y, dot=3.0, sp=1.4, color=Col.dot_on,
                  ghost=Col.dot_off, anchor="center", tag="ov"):
    cw = dot * 5 + dot * 4 * (sp - 1)
    gap = dot * 2
    tw = len(text) * (cw + gap) - gap if text else 0
    ox = x - tw / 2 if anchor == "center" else x
    oy = y - (dot * 7 + dot * 6 * (sp - 1)) / 2
    step = dot * sp
    for ci, ch in enumerate(text):
        cx = ox + ci * (cw + gap)
        g = _F.get(ch)
        if not g:
            continue
        for row in range(7):
            for col in range(5):
                dx, dy = cx + col * step, oy + row * step
                if g[row][col] == '1':
                    r = dot * 0.48
                    cv.create_oval(dx-r, dy-r, dx+r, dy+r,
                                   fill=color, outline="", tags=(tag,))
                elif ghost:
                    r = dot * 0.3
                    cv.create_oval(dx-r, dy-r, dx+r, dy+r,
                                   fill=ghost, outline="", tags=(tag,))


# ---------------------------------------------------------------------------
# Background stroke (animated line that fades in/out)
# ---------------------------------------------------------------------------
class Stroke:
    __slots__ = ("x0", "y0", "angle", "length", "speed", "life", "max_life",
                 "brightness", "width")

    def __init__(self, w, h):
        self.respawn(w, h)

    def respawn(self, w, h):
        self.x0 = random.uniform(-50, w + 50)
        self.y0 = random.uniform(-50, h + 50)
        self.angle = random.uniform(0, math.tau)
        self.length = random.uniform(60, 250)
        self.speed = random.uniform(0.3, 1.2)
        self.life = 0.0
        self.max_life = random.uniform(80, 220)
        self.brightness = random.uniform(12, 30)
        self.width = random.choice([1, 1, 1, 2])

    def update(self, w, h):
        self.life += 1
        # Drift
        self.x0 += math.cos(self.angle) * self.speed
        self.y0 += math.sin(self.angle) * self.speed
        if self.life > self.max_life:
            self.respawn(w, h)

    @property
    def alpha(self):
        """Fade-in then fade-out envelope."""
        frac = self.life / self.max_life
        if frac < 0.15:
            return frac / 0.15
        elif frac > 0.75:
            return (1.0 - frac) / 0.25
        return 1.0

    def endpoints(self):
        dx = math.cos(self.angle) * self.length
        dy = math.sin(self.angle) * self.length
        return self.x0, self.y0, self.x0 + dx, self.y0 + dy


# ---------------------------------------------------------------------------
# Bresenham line into numpy buffer
# ---------------------------------------------------------------------------
def draw_line_buf(buf, x0, y0, x1, y1, brightness, h, w):
    """Draw an anti-aliased-ish line into a 2D float32 buffer."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    steps = 0
    max_steps = dx + dy + 1
    while steps < max_steps:
        if 0 <= y0 < h and 0 <= x0 < w:
            buf[y0, x0] = max(buf[y0, x0], brightness)
            # Soften: neighboring pixels
            if y0 + 1 < h:
                buf[y0 + 1, x0] = max(buf[y0 + 1, x0], brightness * 0.3)
            if x0 + 1 < w:
                buf[y0, x0 + 1] = max(buf[y0, x0 + 1], brightness * 0.3)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
        steps += 1


# ---------------------------------------------------------------------------
# 3D Dot Globe
# ---------------------------------------------------------------------------
class DotGlobe:
    def __init__(self, n_dots, render_w, render_h):
        self.n = n_dots
        self.w = render_w
        self.h = render_h

        idx = np.arange(n_dots, dtype=np.float64)
        phi = np.arccos(1.0 - 2.0 * (idx + 0.5) / n_dots)
        theta = math.pi * (1.0 + math.sqrt(5.0)) * idx

        self.base_x = np.sin(phi) * np.cos(theta)
        self.base_y = np.sin(phi) * np.sin(theta)
        self.base_z = np.cos(phi)
        self.phi = phi
        self.theta = theta

        self.buf = np.zeros((render_h, render_w), dtype=np.float32)

        # Background strokes
        self.strokes = [Stroke(render_w, render_h) for _ in range(NUM_STROKES)]

        self._kernel_3 = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                d = abs(dx) + abs(dy)
                f = 1.0 if d == 0 else (0.38 if d == 1 else 0.18)
                self._kernel_3.append((dx, dy, f))

        self._kernel_5 = []
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if abs(dx) <= 1 and abs(dy) <= 1:
                    continue
                d = abs(dx) + abs(dy)
                self._kernel_5.append((dx, dy, 0.08 / max(d, 1)))

    def render(self, t, audio, bands):
        w, h = self.w, self.h
        cx, cy = w / 2, h / 2
        n = self.n

        # --- Deformation ---
        deform = np.ones(n, dtype=np.float64)
        deform += audio * 0.35
        deform += bands[0] * 0.25
        deform += bands[1] * 0.18 * np.cos(self.phi)
        deform += bands[2] * 0.15 * np.sin(self.phi * 2)
        deform += bands[3] * 0.12 * np.cos(self.theta * 2 + t * 2)
        deform += bands[4] * 0.10 * np.sin(self.phi * 3) * np.cos(self.theta * 3 + t * 1.5)
        deform += bands[5] * 0.08 * np.sin(self.theta * 4 + t * 3)
        deform += bands[6] * 0.06 * np.sin(self.theta * 6 + t * 4)
        deform += bands[7] * 0.05 * np.cos(self.phi * 5 + t * 5)

        xs = self.base_x * deform
        ys = self.base_y * deform
        zs = self.base_z * deform

        # --- Rotation ---
        ay = t * 0.25 + audio * t * 0.15
        ax = 0.35 + math.sin(t * 0.15) * 0.12
        az = math.sin(t * 0.1) * 0.08

        c_, s_ = math.cos(ay), math.sin(ay)
        nx = xs * c_ + zs * s_; nz = -xs * s_ + zs * c_
        xs, zs = nx, nz

        c_, s_ = math.cos(ax), math.sin(ax)
        ny = ys * c_ - zs * s_; nz = ys * s_ + zs * c_
        ys, zs = ny, nz

        c_, s_ = math.cos(az), math.sin(az)
        nx = xs * c_ - ys * s_; ny = xs * s_ + ys * c_
        xs, ys = nx, ny

        # --- Projection ---
        radius = min(w, h) * 0.37
        sx = (xs * radius + cx).astype(np.int32)
        sy = (ys * radius + cy).astype(np.int32)

        z_norm = (zs - zs.min()) / (zs.max() - zs.min() + 1e-9)
        bright = (35 + 220 * z_norm).astype(np.float32)

        order = np.argsort(bright)
        sx, sy, bright = sx[order], sy[order], bright[order]

        # --- Fade trail ---
        decay = 0.82 + audio * 0.08
        self.buf *= decay

        # --- Background strokes (draw before globe) ---
        for stroke in self.strokes:
            stroke.update(w, h)
            a = stroke.alpha
            if a < 0.05:
                continue
            x0, y0, x1, y1 = stroke.endpoints()
            draw_line_buf(self.buf, x0, y0, x1, y1, stroke.brightness * a, h, w)

        # --- Plot globe dots ---
        new_frame = np.zeros((h, w), dtype=np.float32)

        for dx, dy, falloff in self._kernel_3:
            gx = sx + dx; gy = sy + dy
            v = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
            np.maximum.at(new_frame, (gy[v], gx[v]), bright[v] * falloff)

        front = bright > 150
        if np.any(front):
            fsx, fsy, fbr = sx[front], sy[front], bright[front]
            for dx, dy, falloff in self._kernel_5:
                gx = fsx + dx; gy = fsy + dy
                v = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
                np.maximum.at(new_frame, (gy[v], gx[v]), fbr[v] * falloff)

        np.maximum(self.buf, new_frame, out=self.buf)
        np.clip(self.buf, 0, 255, out=self.buf)

        # --- RGB with cool blue tint ---
        g = np.clip(self.buf, 0, 255).astype(np.uint8)
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        rgb[:, :, 0] = (g * 0.82).astype(np.uint8)
        rgb[:, :, 1] = (g * 0.92).astype(np.uint8)
        rgb[:, :, 2] = g

        return Image.fromarray(rgb)


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
class AudioCapture:
    def __init__(self):
        self.rms = 0.0
        self.running = False
        self.bands = [0.0] * 8

    def start(self):
        if not AUDIO_OK:
            return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _loop(self):
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=44100,
                             input=True, frames_per_buffer=2048)
            while self.running:
                data = stream.read(2048, exception_on_overflow=False)
                s = np.frombuffer(data, dtype=np.int16).astype(np.float64)
                self.rms = float(np.sqrt(np.mean(s ** 2)) / 32768.0)
                fft = np.abs(np.fft.rfft(s))[:256]
                bs = len(fft) // 8
                self.bands = [
                    float(np.mean(fft[i * bs:(i + 1) * bs])) / 40000
                    for i in range(8)
                ]
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception:
            self.running = False


# ---------------------------------------------------------------------------
# API placeholders
# ---------------------------------------------------------------------------
def call_ai_backend(text: str) -> str:
    time.sleep(1.0)
    return f'Received: "{text}"\n\nPlaceholder. Wire up your AI backend in call_ai_backend().'


def voice_to_text() -> str | None:
    if not SR_OK:
        return None
    r = sr.Recognizer()
    try:
        with sr.Microphone() as src:
            r.adjust_for_ambient_noise(src, duration=0.4)
            a = r.listen(src, timeout=5, phrase_time_limit=10)
        return r.recognize_google(a)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
class JarvisApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("E.C.H.O.")
        self.root.configure(bg=Col.bg)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.98)

        sx, sy = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{WIN_W}x{WIN_H}+{(sx-WIN_W)//2}+{(sy-WIN_H)//2}")

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
        self.globe = None
        self._photo = None
        self._img_id = None

        # Sidebar bar item IDs (pre-created)
        self._bar_ids = []
        self._bar_glow_ids = []
        self._bar_peak = [0.0] * 8  # peak hold per band

        self.audio = AudioCapture()
        self.audio.start()

        self._build_ui()
        self.root.bind("<Escape>", lambda e: self._quit())
        self.root.after(80, self._animate)
        self.root.mainloop()

    # --------------------------------------------------------------- UI
    def _build_ui(self):
        # ---- Title bar ----
        tb = tk.Frame(self.root, bg=Col.bg2, height=TITLE_H)
        tb.pack(fill=tk.X, side=tk.TOP)
        tb.pack_propagate(False)
        tb.bind("<Button-1>", self._ds)
        tb.bind("<B1-Motion>", self._dm)

        lf = tk.Frame(tb, bg=Col.bg2)
        lf.pack(side=tk.LEFT, padx=14)
        lf.bind("<Button-1>", self._ds)
        lf.bind("<B1-Motion>", self._dm)

        tk.Label(lf, text="◆", font=("Consolas", 9), fg=Col.muted,
                 bg=Col.bg2).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(lf, text="E.C.H.O.", font=("Consolas", 10, "bold"),
                 fg=Col.accent, bg=Col.bg2).pack(side=tk.LEFT)

        # Clock
        self.clock_lbl = tk.Label(
            tb, text="", font=("Consolas", 9), fg=Col.muted, bg=Col.bg2)
        self.clock_lbl.pack(side=tk.RIGHT, padx=(0, 8))
        # Separator dot before clock
        tk.Label(tb, text="◇", font=("Consolas", 7), fg=Col.dim,
                 bg=Col.bg2).pack(side=tk.RIGHT, padx=(0, 6))

        # Window controls
        rf = tk.Frame(tb, bg=Col.bg2)
        rf.pack(side=tk.RIGHT, padx=(0, 8))
        for txt, cmd, hc in [("—", lambda: self.root.iconify(), Col.accent2),
                              ("✕", self._quit, Col.danger)]:
            b = tk.Label(rf, text=f" {txt} ", font=("Consolas", 10),
                         fg=Col.muted, bg=Col.bg2, cursor="hand2")
            b.pack(side=tk.LEFT, padx=1)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b, c=hc: w.config(fg=c))
            b.bind("<Leave>", lambda e, w=b: w.config(fg=Col.muted))

        tk.Frame(self.root, bg=Col.border, height=1).pack(fill=tk.X)

        # ---- Middle area: sidebar + canvas ----
        mid = tk.Frame(self.root, bg=Col.bg)
        mid.pack(fill=tk.BOTH, expand=True)

        # Left sidebar (audio visualizer)
        self.sidebar = tk.Canvas(
            mid, bg=Col.sidebar, width=SIDEBAR_W, highlightthickness=0)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        # Thin separator between sidebar and canvas
        tk.Frame(mid, bg=Col.border, width=1).pack(side=tk.LEFT, fill=tk.Y)

        # Main canvas
        self.canvas = tk.Canvas(mid, bg=Col.bg, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # ---- Bottom panel ----
        bp = tk.Frame(self.root, bg=Col.panel, height=PANEL_H)
        bp.pack(fill=tk.X, side=tk.BOTTOM)
        bp.pack_propagate(False)

        # Dashed separator
        dc = tk.Canvas(bp, bg=Col.panel, height=1, highlightthickness=0)
        dc.pack(fill=tk.X, padx=36, pady=(8, 0))
        dc.create_line(0, 0, WIN_W, 0, fill=Col.dim, width=1, dash=(4, 4))

        # Response
        rf2 = tk.Frame(bp, bg=Col.panel)
        rf2.pack(fill=tk.X, padx=40, pady=(6, 2))
        self.resp = tk.Label(rf2, text="", font=("Consolas", 9), fg=Col.accent2,
                             bg=Col.panel, anchor="w", justify="left",
                             wraplength=WIN_W - 110)
        self.resp.pack(fill=tk.X)

        # Status
        sr2 = tk.Frame(bp, bg=Col.panel)
        sr2.pack(fill=tk.X, padx=40, pady=(0, 4))
        self.sdot = tk.Canvas(sr2, width=8, height=8, bg=Col.panel,
                              highlightthickness=0)
        self.sdot.pack(side=tk.LEFT)
        self.sdot_id = self.sdot.create_oval(1, 1, 7, 7, fill=Col.green, outline="")
        self.slbl = tk.Label(sr2, text="ONLINE", font=("Consolas", 7, "bold"),
                             fg=Col.muted, bg=Col.panel)
        self.slbl.pack(side=tk.LEFT, padx=(6, 0))

        # Input
        irow = tk.Frame(bp, bg=Col.panel)
        irow.pack(fill=tk.X, padx=40, pady=(2, 12))
        self.ib = tk.Frame(irow, bg=Col.dim, padx=1, pady=1)
        self.ib.pack(fill=tk.X)
        ii = tk.Frame(self.ib, bg=Col.bg)
        ii.pack(fill=tk.X)

        tk.Label(ii, text="  >", font=("Consolas", 12, "bold"), fg=Col.muted,
                 bg=Col.bg).pack(side=tk.LEFT, padx=(4, 0))
        self.entry = tk.Entry(ii, font=("Consolas", 11), bg=Col.bg, fg=Col.accent,
                              insertbackground=Col.accent, relief="flat", border=0)
        self.entry.pack(fill=tk.X, padx=(4, 10), pady=9, side=tk.LEFT, expand=True)
        self.entry.bind("<Return>", self._on_submit)
        self.entry.bind("<FocusIn>",
                        lambda e: (self._clr_ph(), self.ib.config(bg=Col.accent2)))
        self.entry.bind("<FocusOut>", lambda e: self.ib.config(bg=Col.dim))

        self.mic_btn = tk.Label(ii, text="◉", font=("Consolas", 13), fg=Col.muted,
                                bg=Col.bg, cursor="hand2")
        self.mic_btn.pack(side=tk.RIGHT, padx=(0, 6))
        self.mic_btn.bind("<Button-1>", self._on_mic)
        self.mic_btn.bind("<Enter>", lambda e: self.mic_btn.config(fg=Col.accent2))
        self.mic_btn.bind("<Leave>", lambda e: self.mic_btn.config(
            fg=Col.muted if not self.is_listening else Col.danger))

        snd = tk.Label(ii, text="→", font=("Consolas", 14, "bold"), fg=Col.muted,
                       bg=Col.bg, cursor="hand2")
        snd.pack(side=tk.RIGHT, padx=(0, 3))
        snd.bind("<Button-1>", self._on_submit)
        snd.bind("<Enter>", lambda e: snd.config(fg=Col.accent))
        snd.bind("<Leave>", lambda e: snd.config(fg=Col.muted))

        self._set_ph()

    # ---- Sidebar: pre-create bar items after layout ----
    def _init_sidebar(self):
        sb = self.sidebar
        sw = SIDEBAR_W
        sh = sb.winfo_height()
        if sh < 50:
            return

        # "AUDIO" label at top
        sb.create_text(sw // 2, 12, text="AUDIO", font=("Consolas", 6, "bold"),
                       fill=Col.muted, anchor="center")

        # 8 frequency bars stacked vertically, bottom to top
        # Each bar: background slot + fill bar + peak dot + glow
        bar_area_top = 26
        bar_area_bot = sh - 8
        total_h = bar_area_bot - bar_area_top
        bar_h = total_h / 8
        bar_w = 14
        bar_x = (sw - bar_w) // 2

        self._bar_area_top = bar_area_top
        self._bar_h = bar_h
        self._bar_x = bar_x
        self._bar_w = bar_w

        # Band labels (low freq at bottom)
        labels = ["SUB", "BAS", "LOW", "MID", "HMD", "HI", "TRB", "AIR"]

        for i in range(8):
            y_top = bar_area_top + i * bar_h + 2
            y_bot = y_top + bar_h - 4

            # Background slot
            sb.create_rectangle(bar_x, y_top, bar_x + bar_w, y_bot,
                                fill="#0e0e0e", outline=Col.border)

            # Glow rectangle (behind fill)
            glow_id = sb.create_rectangle(bar_x - 3, y_bot, bar_x + bar_w + 3, y_bot,
                                          fill="", outline="")
            self._bar_glow_ids.append(glow_id)

            # Fill bar (starts at bottom, grows up)
            bar_id = sb.create_rectangle(bar_x + 1, y_bot, bar_x + bar_w - 1, y_bot,
                                         fill=Col.cyan_dim, outline="")
            self._bar_ids.append(bar_id)

            # Label (right side, rotated by placing vertically)
            label_idx = 7 - i  # reverse: bottom = sub, top = air
            sb.create_text(bar_x + bar_w + 10, (y_top + y_bot) / 2,
                           text=labels[label_idx], font=("Consolas", 5),
                           fill=Col.dim, anchor="w")

        self._sidebar_ready = True

    def _update_sidebar(self, bands, audio):
        """Update the 8 frequency bars."""
        sb = self.sidebar
        for i in range(8):
            band_idx = 7 - i  # bottom bar = band 0 (sub), top = band 7 (air)
            level = min(1.0, bands[band_idx] * 2.5)

            # Peak hold (slow decay)
            self._bar_peak[i] = max(self._bar_peak[i] * 0.95, level)

            y_top_slot = self._bar_area_top + i * self._bar_h + 2
            y_bot_slot = y_top_slot + self._bar_h - 4
            fill_h = (y_bot_slot - y_top_slot) * level
            fill_top = y_bot_slot - fill_h

            # Update fill bar
            sb.coords(self._bar_ids[i],
                      self._bar_x + 1, fill_top,
                      self._bar_x + self._bar_w - 1, y_bot_slot)

            # Color based on level
            if level > 0.6:
                col = "#00ffcc"  # hot green-cyan
            elif level > 0.3:
                col = Col.cyan   # bright cyan
            elif level > 0.1:
                col = Col.cyan_dim
            else:
                col = "#0a1a1e"
            sb.itemconfig(self._bar_ids[i], fill=col)

            # Glow: wider rect behind bar when active
            if level > 0.15:
                glow_h = fill_h * 0.6
                glow_top = y_bot_slot - glow_h
                sb.coords(self._bar_glow_ids[i],
                          self._bar_x - 4, glow_top,
                          self._bar_x + self._bar_w + 4, y_bot_slot)
                gv = int(min(30, level * 40))
                sb.itemconfig(self._bar_glow_ids[i],
                              fill=f"#00{gv:02x}{gv:02x}", outline="")
            else:
                sb.coords(self._bar_glow_ids[i], 0, 0, 0, 0)

    # ---- Helpers ----
    def _set_ph(self):
        if not self.entry.get():
            self.entry.insert(0, "Type a command...")
            self.entry.config(fg=Col.muted)

    def _clr_ph(self):
        if self.entry.get() == "Type a command...":
            self.entry.delete(0, tk.END)
            self.entry.config(fg=Col.accent)

    def _ds(self, e):
        self.drag["x"] = e.x_root - self.root.winfo_x()
        self.drag["y"] = e.y_root - self.root.winfo_y()

    def _dm(self, e):
        self.root.geometry(f"+{e.x_root-self.drag['x']}+{e.y_root-self.drag['y']}")

    # --------------------------------------------------------------- Input
    def _on_submit(self, e=None):
        self._clr_ph()
        t = self.entry.get().strip()
        if not t or t == "Type a command..." or self.is_thinking:
            return
        self.entry.delete(0, tk.END)
        self._stat("PROCESSING", "think")
        self.is_thinking = True
        self.resp.config(text="")
        def w():
            r = call_ai_backend(t)
            self.root.after(0, lambda: self._show_resp(r))
        threading.Thread(target=w, daemon=True).start()

    def _on_mic(self, e=None):
        if self.is_listening or self.is_thinking:
            return
        self.is_listening = True
        self.mic_btn.config(fg=Col.danger)
        self._stat("LISTENING", "listen")
        def w():
            t = voice_to_text()
            self.root.after(0, lambda: self._vdone(t))
        threading.Thread(target=w, daemon=True).start()

    def _vdone(self, text):
        self.is_listening = False
        self.mic_btn.config(fg=Col.muted)
        if text:
            self.entry.delete(0, tk.END)
            self.entry.config(fg=Col.accent)
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

    def _tw(self):
        if not self.tw_active:
            return
        if self.tw_idx < len(self.response_text):
            self.tw_idx = min(self.tw_idx + random.randint(1, 3), len(self.response_text))
            self.resp.config(text=self.response_text[:self.tw_idx] + "█")
            self.root.after(20, self._tw)
        else:
            self.tw_active = False
            self.resp.config(text=self.response_text)
            self._stat("ONLINE", "idle")
            self._set_ph()

    def _stat(self, text, mode="idle"):
        self.slbl.config(text=text)
        c = {"idle": Col.green, "think": Col.warning, "listen": Col.danger}.get(mode)
        self.sdot.itemconfig(self.sdot_id, fill=c)

    # --------------------------------------------------------------- Init renderer
    def _init_renderer(self, cw, ch):
        self.globe = DotGlobe(NUM_DOTS, cw, ch)
        init_img = Image.new("RGB", (cw, ch), (8, 8, 8))
        self._photo = ImageTk.PhotoImage(init_img)
        self._img_id = self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self._cw = cw
        self._ch = ch
        self._ready = True
        self._sidebar_ready = False

    # --------------------------------------------------------------- Animate
    def _animate(self):
        self.tick += 1
        t = self.tick / FPS

        # Audio
        raw = self.audio.rms if self.audio.running else 0.0
        self.audio_smooth = lerp(self.audio_smooth, min(raw * 5, 1.0), 0.12)
        a = self.audio_smooth
        for i in range(8):
            tgt = self.audio.bands[i] if self.audio.running else 0.0
            self.bands_smooth[i] = lerp(self.bands_smooth[i], min(tgt * 3, 1.0), 0.14)

        if self.is_thinking:
            a = max(a, 0.3 + 0.15 * math.sin(t * 3.5))
        if self.is_listening:
            a = max(a, 0.2 + 0.1 * math.sin(t * 5))

        # Init renderer
        if not self._ready:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw > 100 and ch > 100:
                self._init_renderer(cw, ch)
            else:
                self.root.after(50, self._animate)
                return

        # Init sidebar bars (once, after layout)
        if not self._sidebar_ready:
            self._init_sidebar()

        # ---- Clock ----
        now = datetime.now()
        self.clock_lbl.config(text=now.strftime("%H:%M:%S"))

        # ---- Render globe + background strokes ----
        img = self.globe.render(t, a, self.bands_smooth)
        self._photo.paste(img)

        # ---- Canvas overlays ----
        self.canvas.delete("ov")

        cw, ch = self._cw, self._ch
        dcx, dcy = cw // 2, ch // 2
        sphere_r = min(cw, ch) * 0.37

        # Orbital rings
        r1 = sphere_r + 20 + a * 8 + math.sin(t * 0.5) * 3
        self.canvas.create_oval(
            dcx-r1, dcy-r1, dcx+r1, dcy+r1,
            outline=Col.dim, width=1, dash=(3, 8), tags=("ov",))

        r2 = sphere_r + 45 + a * 12 + math.sin(t * 0.7) * 4
        self.canvas.create_oval(
            dcx-r2, dcy-r2, dcx+r2, dcy+r2,
            outline="#181818", width=1, dash=(2, 10), tags=("ov",))

        # Tick marks
        for i in range(28):
            angle = (i / 28) * math.tau + t * 0.2
            ri, ro = r2 - 3, r2 + 3
            x1 = dcx + math.cos(angle) * ri
            y1 = dcy + math.sin(angle) * ri
            x2 = dcx + math.cos(angle) * ro
            y2 = dcy + math.sin(angle) * ro
            c = Col.muted if i % 4 == 0 else "#1a1a1a"
            self.canvas.create_line(x1, y1, x2, y2, fill=c, width=1, tags=("ov",))

        # Dot-matrix text
        ly = dcy + sphere_r + 35
        draw_dot_text(self.canvas, "E.C.H.O.", dcx, ly,
                      dot=2.4, sp=1.3, color=Col.dot_on, ghost="")

        if self.is_listening:
            st, sc = "LISTENING", Col.danger
        elif self.is_thinking:
            st, sc = "PROCESSING", Col.warning
        else:
            st, sc = "READY", Col.muted
        draw_dot_text(self.canvas, st, dcx, ly + 24,
                      dot=1.3, sp=1.2, color=sc, ghost="")

        # ---- Sidebar update ----
        if self._sidebar_ready:
            self._update_sidebar(self.bands_smooth, a)

        # Status dot pulse
        if self.is_thinking or self.is_listening:
            p = 0.5 + 0.5 * math.sin(t * 6)
            c = Col.warning if self.is_thinking else Col.danger
            self.sdot.itemconfig(self.sdot_id, fill=c if p > 0.5 else Col.dim)

        self.root.after(FRAME_MS, self._animate)

    def _quit(self):
        self.audio.stop()
        self.root.destroy()


if __name__ == "__main__":
    JarvisApp()
