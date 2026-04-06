"""
E.C.H.O. — Enhanced Cognitive Heuristic Operator
3D dot-globe · waveform sidebar · minimal floating UI
"""

import tkinter as tk
import math
import random
import threading
import time
from datetime import datetime

import numpy as np
from PIL import Image, ImageTk

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
WIN_W, WIN_H = 1050, 700
SIDEBAR_W = 55
FPS = 40
FRAME_MS = 25
NUM_DOTS = 7000
NUM_STROKES = 18


class C:
    bg      = "#060609"
    bg2     = "#0a0a0f"
    panel   = "#08080c"
    sidebar = "#08080c"
    border  = "#151520"
    accent  = "#d0d4dc"
    accent2 = "#808898"
    muted   = "#3a3e4a"
    dim     = "#1e2028"
    green   = "#00e676"
    cyan    = "#00d4ee"
    cyan2   = "#00a5bb"
    cyan_d  = "#003d48"
    danger  = "#ff2255"
    warning = "#ffaa00"
    dot_on  = "#c8ccd4"
    dot_off = "#141418"


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# 5x7 Dot-matrix font
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
    '!':["00100","00100","00100","00100","00100","00000","00100"],
    '?':["01110","10001","00001","00110","00100","00000","00100"],
    '"':["01010","01010","01010","00000","00000","00000","00000"],
    '/':["00001","00010","00010","00100","01000","01000","10000"],
    ',':["00000","00000","00000","00000","00000","01100","00100"],
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _F[_c] = _F[_c.upper()]


def draw_dot_text(cv, text, x, y, dot=3.0, sp=1.4, color=C.dot_on,
                  ghost="", anchor="center", tag="ov"):
    cw = dot * 5 + dot * 4 * (sp - 1)
    gap = dot * 2
    tw = len(text) * (cw + gap) - gap if text else 0
    ox = x - tw / 2 if anchor == "center" else x
    oy = y - (dot * 7 + dot * 6 * (sp - 1)) / 2
    step = dot * sp
    for ci, ch in enumerate(text):
        cx_ = ox + ci * (cw + gap)
        g = _F.get(ch)
        if not g:
            continue
        for row in range(7):
            for col in range(5):
                dx, dy = cx_ + col * step, oy + row * step
                if g[row][col] == '1':
                    r = dot * 0.48
                    cv.create_oval(dx-r, dy-r, dx+r, dy+r,
                                   fill=color, outline="", tags=(tag,))
                elif ghost:
                    r = dot * 0.3
                    cv.create_oval(dx-r, dy-r, dx+r, dy+r,
                                   fill=ghost, outline="", tags=(tag,))


# ---------------------------------------------------------------------------
# Background stroke
# ---------------------------------------------------------------------------
class Stroke:
    __slots__ = ("x0","y0","angle","length","speed","life","max_life","brightness")
    def __init__(self, w, h):
        self.respawn(w, h)
    def respawn(self, w, h):
        self.x0 = random.uniform(-50, w + 50)
        self.y0 = random.uniform(-50, h + 50)
        self.angle = random.uniform(0, math.tau)
        self.length = random.uniform(60, 250)
        self.speed = random.uniform(0.3, 1.0)
        self.life = 0.0
        self.max_life = random.uniform(100, 260)
        self.brightness = random.uniform(10, 26)
    def update(self, w, h):
        self.life += 1
        self.x0 += math.cos(self.angle) * self.speed
        self.y0 += math.sin(self.angle) * self.speed
        if self.life > self.max_life:
            self.respawn(w, h)
    @property
    def alpha(self):
        f = self.life / self.max_life
        if f < 0.15: return f / 0.15
        elif f > 0.75: return (1.0 - f) / 0.25
        return 1.0
    def endpoints(self):
        dx = math.cos(self.angle) * self.length
        dy = math.sin(self.angle) * self.length
        return self.x0, self.y0, self.x0 + dx, self.y0 + dy


def draw_line_buf(buf, x0, y0, x1, y1, bri, h, w):
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx, dy = abs(x1-x0), abs(y1-y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    for _ in range(dx + dy + 2):
        if 0 <= y0 < h and 0 <= x0 < w:
            buf[y0, x0] = max(buf[y0, x0], bri)
            if y0+1 < h: buf[y0+1, x0] = max(buf[y0+1, x0], bri * 0.3)
            if x0+1 < w: buf[y0, x0+1] = max(buf[y0, x0+1], bri * 0.3)
        if x0 == x1 and y0 == y1: break
        e2 = 2 * err
        if e2 > -dy: err -= dy; x0 += sx
        if e2 < dx: err += dx; y0 += sy


# ---------------------------------------------------------------------------
# 3D Dot Globe — buttery smooth
# ---------------------------------------------------------------------------
class DotGlobe:
    def __init__(self, n, w, h):
        self.n, self.w, self.h = n, w, h
        idx = np.arange(n, dtype=np.float64)
        phi = np.arccos(1.0 - 2.0 * (idx + 0.5) / n)
        theta = math.pi * (1 + math.sqrt(5)) * idx
        self.bx = np.sin(phi) * np.cos(theta)
        self.by = np.sin(phi) * np.sin(theta)
        self.bz = np.cos(phi)
        self.phi, self.theta = phi, theta
        self.buf = np.zeros((h, w), dtype=np.float32)
        # Smooth deform state (interpolated each frame)
        self._deform_cur = np.ones(n, dtype=np.float64)
        self.strokes = [Stroke(w, h) for _ in range(NUM_STROKES)]
        self._k3 = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                d = abs(dx) + abs(dy)
                self._k3.append((dx, dy, 1.0 if d == 0 else (0.4 if d == 1 else 0.2)))
        self._k5 = []
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if abs(dx) <= 1 and abs(dy) <= 1: continue
                self._k5.append((dx, dy, 0.08 / max(abs(dx)+abs(dy), 1)))

    def render(self, t, audio, bands):
        w, h, n = self.w, self.h, self.n
        cx, cy = w / 2, h / 2

        # Target deformation
        d_tgt = np.ones(n, dtype=np.float64)
        d_tgt += audio * 0.3
        d_tgt += bands[0] * 0.22
        d_tgt += bands[1] * 0.16 * np.cos(self.phi)
        d_tgt += bands[2] * 0.13 * np.sin(self.phi * 2)
        d_tgt += bands[3] * 0.10 * np.cos(self.theta * 2 + t * 1.8)
        d_tgt += bands[4] * 0.08 * np.sin(self.phi * 3) * np.cos(self.theta * 3 + t * 1.2)
        d_tgt += bands[5] * 0.06 * np.sin(self.theta * 4 + t * 2.5)
        d_tgt += bands[6] * 0.04 * np.sin(self.theta * 6 + t * 3.5)
        d_tgt += bands[7] * 0.03 * np.cos(self.phi * 5 + t * 4)

        # Smooth interpolation toward target (buttery!)
        self._deform_cur += (d_tgt - self._deform_cur) * 0.08
        deform = self._deform_cur

        xs = self.bx * deform
        ys = self.by * deform
        zs = self.bz * deform

        # Slow smooth rotation
        ay = t * 0.18 + audio * t * 0.08
        ax = 0.32 + math.sin(t * 0.1) * 0.1
        az = math.sin(t * 0.07) * 0.06

        co, si = math.cos(ay), math.sin(ay)
        nx = xs*co + zs*si; nz = -xs*si + zs*co; xs, zs = nx, nz
        co, si = math.cos(ax), math.sin(ax)
        ny = ys*co - zs*si; nz = ys*si + zs*co; ys, zs = ny, nz
        co, si = math.cos(az), math.sin(az)
        nx = xs*co - ys*si; ny = xs*si + ys*co; xs, ys = nx, ny

        radius = min(w, h) * 0.36
        sx = (xs * radius + cx).astype(np.int32)
        sy = (ys * radius + cy).astype(np.int32)
        z_norm = (zs - zs.min()) / (zs.max() - zs.min() + 1e-9)
        bright = (30 + 225 * z_norm).astype(np.float32)
        order = np.argsort(bright)
        sx, sy, bright = sx[order], sy[order], bright[order]

        # Longer trail persistence
        decay = 0.86 + audio * 0.06
        self.buf *= decay

        # Background strokes
        for s in self.strokes:
            s.update(w, h)
            a = s.alpha
            if a > 0.05:
                x0, y0, x1, y1 = s.endpoints()
                draw_line_buf(self.buf, x0, y0, x1, y1, s.brightness * a, h, w)

        # Globe dots
        nf = np.zeros((h, w), dtype=np.float32)
        for dx, dy, f in self._k3:
            gx = sx + dx; gy = sy + dy
            v = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
            np.maximum.at(nf, (gy[v], gx[v]), bright[v] * f)
        front = bright > 140
        if np.any(front):
            fs, fy2, fb = sx[front], sy[front], bright[front]
            for dx, dy, f in self._k5:
                gx = fs + dx; gy = fy2 + dy
                v = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
                np.maximum.at(nf, (gy[v], gx[v]), fb[v] * f)

        np.maximum(self.buf, nf, out=self.buf)
        np.clip(self.buf, 0, 255, out=self.buf)

        g = np.clip(self.buf, 0, 255).astype(np.uint8)
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        rgb[:,:,0] = (g * 0.80).astype(np.uint8)
        rgb[:,:,1] = (g * 0.90).astype(np.uint8)
        rgb[:,:,2] = g
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
        if not AUDIO_OK: return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
    def stop(self):
        self.running = False
    def _loop(self):
        try:
            pa = pyaudio.PyAudio()
            st = pa.open(format=pyaudio.paInt16, channels=1, rate=44100,
                         input=True, frames_per_buffer=2048)
            while self.running:
                data = st.read(2048, exception_on_overflow=False)
                s = np.frombuffer(data, dtype=np.int16).astype(np.float64)
                self.rms = float(np.sqrt(np.mean(s**2)) / 32768)
                fft = np.abs(np.fft.rfft(s))[:256]
                bs = len(fft) // 8
                self.bands = [float(np.mean(fft[i*bs:(i+1)*bs])) / 40000 for i in range(8)]
            st.stop_stream(); st.close(); pa.terminate()
        except Exception:
            self.running = False


def call_ai_backend(text: str) -> str:
    time.sleep(1.0)
    return f'Received: "{text}"\n\nPlaceholder. Wire up your AI backend in call_ai_backend().'

def voice_to_text() -> str | None:
    if not SR_OK: return None
    r = sr.Recognizer()
    try:
        with sr.Microphone() as src:
            r.adjust_for_ambient_noise(src, duration=0.4)
            a = r.listen(src, timeout=5, phrase_time_limit=10)
        return r.recognize_google(a)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class JarvisApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("E.C.H.O.")
        self.root.configure(bg=C.bg)
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
        self._sidebar_ready = False
        self.globe = None
        self._photo = None
        self._img_id = None
        # Waveform history for sidebar (circular buffer per band)
        self._wave_hist = [[] for _ in range(8)]
        self._wave_max_len = 30

        self.audio = AudioCapture()
        self.audio.start()
        self._build_ui()
        self.root.bind("<Escape>", lambda e: self._quit())
        self.root.after(80, self._animate)
        self.root.mainloop()

    def _build_ui(self):
        # ---- Title bar ----
        tb = tk.Canvas(self.root, bg=C.bg2, height=36, highlightthickness=0)
        tb.pack(fill=tk.X, side=tk.TOP)
        tb.bind("<Button-1>", self._ds)
        tb.bind("<B1-Motion>", self._dm)

        tb.create_text(16, 18, text="◆", font=("Consolas", 8), fill=C.muted, anchor="w")
        tb.create_text(32, 18, text="E.C.H.O.", font=("Consolas", 10, "bold"), fill=C.accent, anchor="w")

        # Clock (right side)
        self._clock_id = tb.create_text(WIN_W - 80, 18, text="", font=("Consolas", 9), fill=C.muted, anchor="w")
        self._tb = tb

        # Close / min
        close_id = tb.create_text(WIN_W - 16, 18, text="✕", font=("Consolas", 10), fill=C.muted)
        min_id = tb.create_text(WIN_W - 42, 18, text="—", font=("Consolas", 10), fill=C.muted)
        tb.tag_bind(close_id, "<Button-1>", lambda e: self._quit())
        tb.tag_bind(close_id, "<Enter>", lambda e: tb.itemconfig(close_id, fill=C.danger))
        tb.tag_bind(close_id, "<Leave>", lambda e: tb.itemconfig(close_id, fill=C.muted))
        tb.tag_bind(min_id, "<Button-1>", lambda e: self.root.iconify())
        tb.tag_bind(min_id, "<Enter>", lambda e: tb.itemconfig(min_id, fill=C.accent))
        tb.tag_bind(min_id, "<Leave>", lambda e: tb.itemconfig(min_id, fill=C.muted))

        # Separator
        tk.Frame(self.root, bg=C.border, height=1).pack(fill=tk.X)

        # ---- Middle: sidebar + canvas ----
        mid = tk.Frame(self.root, bg=C.bg)
        mid.pack(fill=tk.BOTH, expand=True)

        # Left sidebar (waveform visualizer)
        self.sidebar = tk.Canvas(mid, bg=C.sidebar, width=SIDEBAR_W, highlightthickness=0)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        tk.Frame(mid, bg=C.border, width=1).pack(side=tk.LEFT, fill=tk.Y)

        # Main canvas
        self.canvas = tk.Canvas(mid, bg=C.bg, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # ---- Bottom: floating overlay-style panel ----
        bp = tk.Frame(self.root, bg=C.panel)
        bp.pack(fill=tk.X, side=tk.BOTTOM)

        # Thin top border (gradient-ish)
        border_cv = tk.Canvas(bp, bg=C.panel, height=1, highlightthickness=0)
        border_cv.pack(fill=tk.X)
        border_cv.create_line(0, 0, WIN_W, 0, fill=C.border, width=1)

        # Response text — minimal, no box
        self.resp = tk.Label(
            bp, text="", font=("Consolas", 9), fg=C.accent2,
            bg=C.panel, anchor="w", justify="left", wraplength=WIN_W - 140,
            padx=20, pady=0)
        self.resp.pack(fill=tk.X, padx=20, pady=(8, 2))

        # Status row
        sf = tk.Frame(bp, bg=C.panel)
        sf.pack(fill=tk.X, padx=20, pady=(0, 4))

        self.sdot_cv = tk.Canvas(sf, width=6, height=6, bg=C.panel, highlightthickness=0)
        self.sdot_cv.pack(side=tk.LEFT, pady=2)
        self.sdot_id = self.sdot_cv.create_oval(0, 0, 6, 6, fill=C.green, outline="")

        self.slbl = tk.Label(sf, text="ONLINE", font=("Consolas", 7), fg=C.muted, bg=C.panel)
        self.slbl.pack(side=tk.LEFT, padx=(5, 0))

        # Input: ultra-minimal — just a thin line, no box
        inp_frame = tk.Frame(bp, bg=C.panel)
        inp_frame.pack(fill=tk.X, padx=20, pady=(2, 14))

        # Prompt char
        tk.Label(inp_frame, text=">", font=("Consolas", 12, "bold"),
                 fg=C.muted, bg=C.panel).pack(side=tk.LEFT)

        self.entry = tk.Entry(
            inp_frame, font=("Consolas", 11), bg=C.panel, fg=C.accent,
            insertbackground=C.cyan, relief="flat", border=0,
        )
        self.entry.pack(fill=tk.X, padx=(6, 8), pady=4, side=tk.LEFT, expand=True)
        self.entry.bind("<Return>", self._on_submit)
        self.entry.bind("<FocusIn>", lambda e: self._clr_ph())

        # Mic button — pulsing dot style
        self.mic_btn = tk.Label(
            inp_frame, text="◉", font=("Consolas", 12), fg=C.muted,
            bg=C.panel, cursor="hand2")
        self.mic_btn.pack(side=tk.RIGHT, padx=(0, 2))
        self.mic_btn.bind("<Button-1>", self._on_mic)
        self.mic_btn.bind("<Enter>", lambda e: self.mic_btn.config(fg=C.cyan))
        self.mic_btn.bind("<Leave>", lambda e: self.mic_btn.config(
            fg=C.muted if not self.is_listening else C.danger))

        # Send
        self.send_btn = tk.Label(
            inp_frame, text="→", font=("Consolas", 13, "bold"), fg=C.muted,
            bg=C.panel, cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, padx=(0, 6))
        self.send_btn.bind("<Button-1>", self._on_submit)
        self.send_btn.bind("<Enter>", lambda e: self.send_btn.config(fg=C.accent))
        self.send_btn.bind("<Leave>", lambda e: self.send_btn.config(fg=C.muted))

        # Underline for input area
        ul = tk.Canvas(bp, bg=C.panel, height=1, highlightthickness=0)
        ul.pack(fill=tk.X, padx=20, pady=(0, 0))
        ul.create_line(24, 0, WIN_W - 44, 0, fill=C.dim, width=1)

        self._set_ph()

    # ---- Sidebar waveform ----
    def _init_sidebar(self):
        self._sidebar_ready = True

    def _draw_sidebar(self, bands, audio, t):
        sb = self.sidebar
        sb.delete("all")
        sw = SIDEBAR_W
        sh = sb.winfo_height()
        if sh < 50:
            return

        # 8 bands, each gets a horizontal waveform lane
        lane_h = sh / 8
        labels = ["SUB", "BAS", "LOW", "MID", "HMD", "HI", "TRB", "AIR"]

        for i in range(8):
            level = min(1.0, bands[i] * 2.8)
            # Push to history
            hist = self._wave_hist[i]
            hist.append(level)
            if len(hist) > self._wave_max_len:
                hist.pop(0)

            lane_top = i * lane_h
            lane_mid = lane_top + lane_h / 2
            lane_bot = lane_top + lane_h

            # Thin separator
            if i > 0:
                sb.create_line(4, lane_top, sw - 4, lane_top, fill=C.dim, width=1)

            # Label
            sb.create_text(sw // 2, lane_top + 7, text=labels[i],
                           font=("Consolas", 5), fill=C.dim)

            # Waveform: draw the history as a smooth polyline
            n = len(hist)
            if n < 2:
                continue

            pts = []
            for j, val in enumerate(hist):
                x = 6 + (sw - 12) * j / (self._wave_max_len - 1)
                amp = (lane_h / 2 - 10) * val
                y = lane_mid + 3 + amp * math.sin(t * 2 + j * 0.3 + i)
                pts.append(x)
                pts.append(y)

            # Color based on current level
            if level > 0.5:
                col = C.cyan
            elif level > 0.2:
                col = C.cyan2
            else:
                col = C.muted

            if len(pts) >= 4:
                sb.create_line(pts, fill=col, width=1.5, smooth=True)

            # Active dot at the end (latest value)
            if n > 0:
                lx = 6 + (sw - 12) * min(n - 1, self._wave_max_len - 1) / (self._wave_max_len - 1)
                ly = pts[-1] if len(pts) >= 2 else lane_mid
                dot_r = 2 + level * 2.5
                sb.create_oval(lx - dot_r, ly - dot_r, lx + dot_r, ly + dot_r,
                               fill=col, outline="")
                # Glow
                if level > 0.2:
                    gr = dot_r * 2.5
                    gv = int(min(40, level * 50))
                    sb.create_oval(lx - gr, ly - gr, lx + gr, ly + gr,
                                   fill=f"#00{gv:02x}{gv:02x}", outline="")

        # Overall level bar at bottom (thin horizontal)
        bar_y = sh - 3
        bar_w = int(audio * (sw - 8))
        col = C.cyan if audio > 0.15 else C.muted
        sb.create_line(4, bar_y, 4 + bar_w, bar_y, fill=col, width=2)

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
        self.root.geometry(f"+{e.x_root-self.drag['x']}+{e.y_root-self.drag['y']}")

    def _on_submit(self, e=None):
        self._clr_ph()
        t = self.entry.get().strip()
        if not t or t == "ask echo something..." or self.is_thinking:
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
        if self.is_listening or self.is_thinking: return
        self.is_listening = True
        self.mic_btn.config(fg=C.danger)
        self._stat("LISTENING", "listen")
        def w():
            t = voice_to_text()
            self.root.after(0, lambda: self._vdone(t))
        threading.Thread(target=w, daemon=True).start()

    def _vdone(self, text):
        self.is_listening = False
        self.mic_btn.config(fg=C.muted)
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
        self.tw_idx = 0; self.tw_active = True
        self._stat("RESPONDING", "think")
        self._tw()

    def _tw(self):
        if not self.tw_active: return
        if self.tw_idx < len(self.response_text):
            self.tw_idx = min(self.tw_idx + random.randint(1, 3), len(self.response_text))
            self.resp.config(text=self.response_text[:self.tw_idx] + "▌")
            self.root.after(22, self._tw)
        else:
            self.tw_active = False
            self.resp.config(text=self.response_text)
            self._stat("ONLINE", "idle")
            self._set_ph()

    def _stat(self, text, mode="idle"):
        self.slbl.config(text=text)
        c = {"idle": C.green, "think": C.warning, "listen": C.danger}.get(mode)
        self.sdot_cv.itemconfig(self.sdot_id, fill=c)

    def _init_renderer(self, cw, ch):
        self.globe = DotGlobe(NUM_DOTS, cw, ch)
        img = Image.new("RGB", (cw, ch), (6, 6, 9))
        self._photo = ImageTk.PhotoImage(img)
        self._img_id = self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self._cw, self._ch = cw, ch
        self._ready = True

    def _animate(self):
        self.tick += 1
        t = self.tick / FPS

        raw = self.audio.rms if self.audio.running else 0.0
        self.audio_smooth = lerp(self.audio_smooth, min(raw * 5, 1.0), 0.10)
        a = self.audio_smooth
        for i in range(8):
            tgt = self.audio.bands[i] if self.audio.running else 0.0
            self.bands_smooth[i] = lerp(self.bands_smooth[i], min(tgt * 3, 1.0), 0.12)

        if self.is_thinking: a = max(a, 0.3 + 0.12 * math.sin(t * 3))
        if self.is_listening: a = max(a, 0.2 + 0.08 * math.sin(t * 5))

        if not self._ready:
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            if cw > 100 and ch > 100:
                self._init_renderer(cw, ch)
            else:
                self.root.after(50, self._animate); return

        # Clock
        self._tb.itemconfig(self._clock_id, text=datetime.now().strftime("%H:%M:%S"))

        # Render globe
        img = self.globe.render(t, a, self.bands_smooth)
        self._photo.paste(img)

        # Canvas overlays
        self.canvas.delete("ov")
        cw, ch = self._cw, self._ch
        dcx, dcy = cw // 2, ch // 2
        sr = min(cw, ch) * 0.36

        # Orbital rings
        r1 = sr + 20 + a * 8 + math.sin(t * 0.4) * 3
        self.canvas.create_oval(dcx-r1, dcy-r1, dcx+r1, dcy+r1,
                                outline=C.dim, width=1, dash=(3, 8), tags=("ov",))
        r2 = sr + 48 + a * 12 + math.sin(t * 0.6) * 4
        self.canvas.create_oval(dcx-r2, dcy-r2, dcx+r2, dcy+r2,
                                outline="#14141c", width=1, dash=(2, 10), tags=("ov",))

        # Tick marks
        for i in range(24):
            ang = (i / 24) * math.tau + t * 0.15
            ri, ro = r2 - 3, r2 + 3
            x1 = dcx + math.cos(ang) * ri; y1 = dcy + math.sin(ang) * ri
            x2 = dcx + math.cos(ang) * ro; y2 = dcy + math.sin(ang) * ro
            c = C.muted if i % 4 == 0 else "#16161e"
            self.canvas.create_line(x1, y1, x2, y2, fill=c, width=1, tags=("ov",))

        # Dot-matrix title
        ly = dcy + sr + 40
        draw_dot_text(self.canvas, "E.C.H.O.", dcx, ly,
                      dot=4.0, sp=1.4, color=C.dot_on, ghost=C.dot_off)

        if self.is_listening:   st, sc = "LISTENING", C.danger
        elif self.is_thinking:  st, sc = "PROCESSING", C.warning
        else:                   st, sc = "READY", C.muted
        draw_dot_text(self.canvas, st, dcx, ly + 38,
                      dot=2.0, sp=1.3, color=sc, ghost="")

        # Sidebar waveform
        self._draw_sidebar(self.bands_smooth, a, t)

        # Status pulse
        if self.is_thinking or self.is_listening:
            p = 0.5 + 0.5 * math.sin(t * 6)
            c = C.warning if self.is_thinking else C.danger
            self.sdot_cv.itemconfig(self.sdot_id, fill=c if p > 0.5 else C.dim)

        self.root.after(FRAME_MS, self._animate)

    def _quit(self):
        self.audio.stop()
        self.root.destroy()


if __name__ == "__main__":
    JarvisApp()
