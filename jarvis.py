"""
E.C.H.O. — Enhanced Cognitive Heuristic Operator
3D dot-globe with voice-reactive deformation.
Clean dark dot-matrix theme.
"""

import tkinter as tk
import math
import random
import threading
import time

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
WIN_W, WIN_H = 1200, 800
PANEL_H = 170
TITLE_H = 40
FPS = 38
FRAME_MS = int(1000 / FPS)
NUM_DOTS = 7000  # dense globe


class Col:
    bg      = "#080808"
    bg2     = "#0c0c0c"
    panel   = "#0a0a0a"
    border  = "#1a1a1a"
    accent  = "#d8d8d8"
    accent2 = "#888888"
    muted   = "#444444"
    dim     = "#222222"
    green   = "#00e676"
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
# 3D Dot Globe (Fibonacci sphere, numpy-rendered)
# ---------------------------------------------------------------------------
class DotGlobe:
    """Massive 3D sphere of dots, rendered to a numpy buffer."""

    def __init__(self, n_dots, render_w, render_h):
        self.n = n_dots
        self.w = render_w
        self.h = render_h

        # Fibonacci sphere distribution
        idx = np.arange(n_dots, dtype=np.float64)
        phi = np.arccos(1.0 - 2.0 * (idx + 0.5) / n_dots)
        theta = math.pi * (1.0 + math.sqrt(5.0)) * idx

        # Base unit-sphere coordinates
        self.base_x = np.sin(phi) * np.cos(theta)
        self.base_y = np.sin(phi) * np.sin(theta)
        self.base_z = np.cos(phi)

        # Store spherical coords for deformation mapping
        self.phi = phi      # 0..pi (pole to pole)
        self.theta = theta  # azimuthal

        # Trail buffer (persistence)
        self.buf = np.zeros((render_h, render_w), dtype=np.float32)

        # Pre-compute glow kernel offsets (3x3 + 5x5 outer)
        self._kernel_3 = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                d = abs(dx) + abs(dy)
                if d == 0:
                    f = 1.0
                elif d == 1:
                    f = 0.38
                else:
                    f = 0.18
                self._kernel_3.append((dx, dy, f))

        self._kernel_5 = []
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if abs(dx) <= 1 and abs(dy) <= 1:
                    continue
                d = abs(dx) + abs(dy)
                self._kernel_5.append((dx, dy, 0.08 / max(d, 1)))

    def render(self, t, audio, bands):
        """Render one frame. Returns PIL Image (RGB)."""
        w, h = self.w, self.h
        cx, cy = w / 2, h / 2
        n = self.n

        # --- Deformation ---
        deform = np.ones(n, dtype=np.float64)
        deform += audio * 0.35                                   # overall pulse
        deform += bands[0] * 0.25                                # bass: breathe
        deform += bands[1] * 0.18 * np.cos(self.phi)            # low: Y-stretch
        deform += bands[2] * 0.15 * np.sin(self.phi * 2)        # low-mid: equator bulge
        deform += bands[3] * 0.12 * np.cos(self.theta * 2 + t * 2)  # mid: latitude wave
        deform += bands[4] * 0.10 * np.sin(self.phi * 3) * np.cos(self.theta * 3 + t * 1.5)
        deform += bands[5] * 0.08 * np.sin(self.theta * 4 + t * 3)  # hi-mid: ripple
        deform += bands[6] * 0.06 * np.sin(self.theta * 6 + t * 4)  # treble: fine ripple
        deform += bands[7] * 0.05 * np.cos(self.phi * 5 + t * 5)    # air: shimmer

        xs = self.base_x * deform
        ys = self.base_y * deform
        zs = self.base_z * deform

        # --- Rotation ---
        ay = t * 0.25 + audio * t * 0.15   # Y-rotation, speeds up with voice
        ax = 0.35 + math.sin(t * 0.15) * 0.12  # gentle X-tilt wobble
        az = math.sin(t * 0.1) * 0.08           # slight Z-roll

        # Rotate Y
        cy_r, sy_r = math.cos(ay), math.sin(ay)
        nx = xs * cy_r + zs * sy_r
        nz = -xs * sy_r + zs * cy_r
        xs, zs = nx, nz

        # Rotate X
        cx_r, sx_r = math.cos(ax), math.sin(ax)
        ny = ys * cx_r - zs * sx_r
        nz = ys * sx_r + zs * cx_r
        ys, zs = ny, nz

        # Rotate Z
        cz_r, sz_r = math.cos(az), math.sin(az)
        nx = xs * cz_r - ys * sz_r
        ny = xs * sz_r + ys * cz_r
        xs, ys = nx, ny

        # --- Projection ---
        radius = min(w, h) * 0.37
        sx = (xs * radius + cx).astype(np.int32)
        sy = (ys * radius + cy).astype(np.int32)

        # --- Depth-based brightness ---
        # z ranges roughly -1..1 (before deform stretches it)
        z_norm = (zs - zs.min()) / (zs.max() - zs.min() + 1e-9)
        bright = (35 + 220 * z_norm).astype(np.float32)  # 35..255 range

        # --- Sort by brightness ascending (so bright dots overwrite dim) ---
        order = np.argsort(bright)
        sx = sx[order]
        sy = sy[order]
        bright = bright[order]

        # --- Fade trail ---
        decay = 0.82 + audio * 0.08  # longer trail when loud (0.82..0.90)
        self.buf *= decay

        # --- Plot dots with glow ---
        new_frame = np.zeros((h, w), dtype=np.float32)

        for dx, dy, falloff in self._kernel_3:
            gx = sx + dx
            gy = sy + dy
            v = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
            np.maximum.at(new_frame, (gy[v], gx[v]), bright[v] * falloff)

        # Extra outer glow for front-facing dots
        front = bright > 150
        if np.any(front):
            fsx = sx[front]
            fsy = sy[front]
            fbr = bright[front]
            for dx, dy, falloff in self._kernel_5:
                gx = fsx + dx
                gy = fsy + dy
                v = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
                np.maximum.at(new_frame, (gy[v], gx[v]), fbr[v] * falloff)

        # --- Merge with trail ---
        np.maximum(self.buf, new_frame, out=self.buf)
        np.clip(self.buf, 0, 255, out=self.buf)

        # --- Convert to RGB with cool blue tint ---
        g = np.clip(self.buf, 0, 255).astype(np.uint8)
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        rgb[:, :, 0] = (g * 0.82).astype(np.uint8)   # R: dimmer
        rgb[:, :, 1] = (g * 0.92).astype(np.uint8)   # G: mid
        rgb[:, :, 2] = g                               # B: full

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

        self.audio = AudioCapture()
        self.audio.start()

        self._build_ui()
        self.root.bind("<Escape>", lambda e: self._quit())
        self.root.after(80, self._animate)
        self.root.mainloop()

    # --------------------------------------------------------------- UI
    def _build_ui(self):
        # Title bar
        tb = tk.Frame(self.root, bg=Col.bg2, height=TITLE_H)
        tb.pack(fill=tk.X, side=tk.TOP)
        tb.pack_propagate(False)
        tb.bind("<Button-1>", self._ds)
        tb.bind("<B1-Motion>", self._dm)

        lf = tk.Frame(tb, bg=Col.bg2)
        lf.pack(side=tk.LEFT, padx=16)
        lf.bind("<Button-1>", self._ds)
        lf.bind("<B1-Motion>", self._dm)

        tk.Label(lf, text="◆", font=("Consolas", 9), fg=Col.muted,
                 bg=Col.bg2).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(lf, text="E.C.H.O.", font=("Consolas", 11, "bold"),
                 fg=Col.accent, bg=Col.bg2).pack(side=tk.LEFT)
        tk.Label(lf, text="v3.0", font=("Consolas", 8), fg=Col.muted,
                 bg=Col.bg2).pack(side=tk.LEFT, padx=(8, 0))

        rf = tk.Frame(tb, bg=Col.bg2)
        rf.pack(side=tk.RIGHT, padx=12)
        for txt, cmd, hc in [("—", lambda: self.root.iconify(), Col.accent2),
                              ("✕", self._quit, Col.danger)]:
            b = tk.Label(rf, text=f" {txt} ", font=("Consolas", 11),
                         fg=Col.muted, bg=Col.bg2, cursor="hand2")
            b.pack(side=tk.LEFT, padx=2)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b, c=hc: w.config(fg=c))
            b.bind("<Leave>", lambda e, w=b: w.config(fg=Col.muted))

        tk.Frame(self.root, bg=Col.border, height=1).pack(fill=tk.X)

        # Canvas
        self.canvas = tk.Canvas(self.root, bg=Col.bg, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bottom panel
        bp = tk.Frame(self.root, bg=Col.panel, height=PANEL_H)
        bp.pack(fill=tk.X, side=tk.BOTTOM)
        bp.pack_propagate(False)

        # Dashed separator
        dc = tk.Canvas(bp, bg=Col.panel, height=1, highlightthickness=0)
        dc.pack(fill=tk.X, padx=40, pady=(10, 0))
        dc.create_line(0, 0, WIN_W, 0, fill=Col.dim, width=1, dash=(4, 4))

        # Response
        rf2 = tk.Frame(bp, bg=Col.panel)
        rf2.pack(fill=tk.X, padx=44, pady=(8, 3))
        self.resp = tk.Label(rf2, text="", font=("Consolas", 10), fg=Col.accent2,
                             bg=Col.panel, anchor="w", justify="left",
                             wraplength=WIN_W - 120)
        self.resp.pack(fill=tk.X)

        # Status
        sr2 = tk.Frame(bp, bg=Col.panel)
        sr2.pack(fill=tk.X, padx=44, pady=(0, 5))
        self.sdot = tk.Canvas(sr2, width=8, height=8, bg=Col.panel,
                              highlightthickness=0)
        self.sdot.pack(side=tk.LEFT)
        self.sdot_id = self.sdot.create_oval(1, 1, 7, 7, fill=Col.green, outline="")
        self.slbl = tk.Label(sr2, text="ONLINE", font=("Consolas", 8, "bold"),
                             fg=Col.muted, bg=Col.panel)
        self.slbl.pack(side=tk.LEFT, padx=(6, 0))

        # Mic meter
        mf = tk.Frame(sr2, bg=Col.panel)
        mf.pack(side=tk.RIGHT)
        tk.Label(mf, text="MIC", font=("Consolas", 7, "bold"), fg=Col.dim,
                 bg=Col.panel).pack(side=tk.LEFT, padx=(0, 6))
        self.mcv = tk.Canvas(mf, width=80, height=4, bg=Col.panel,
                             highlightthickness=0)
        self.mcv.pack(side=tk.LEFT)
        self.mcv.create_rectangle(0, 0, 80, 4, fill=Col.border, outline="")
        self.mbar = self.mcv.create_rectangle(0, 0, 0, 4, fill=Col.muted, outline="")

        # Input
        irow = tk.Frame(bp, bg=Col.panel)
        irow.pack(fill=tk.X, padx=44, pady=(2, 16))
        self.ib = tk.Frame(irow, bg=Col.dim, padx=1, pady=1)
        self.ib.pack(fill=tk.X)
        ii = tk.Frame(self.ib, bg=Col.bg)
        ii.pack(fill=tk.X)

        tk.Label(ii, text="  >", font=("Consolas", 13, "bold"), fg=Col.muted,
                 bg=Col.bg).pack(side=tk.LEFT, padx=(6, 0))
        self.entry = tk.Entry(ii, font=("Consolas", 12), bg=Col.bg, fg=Col.accent,
                              insertbackground=Col.accent, relief="flat", border=0)
        self.entry.pack(fill=tk.X, padx=(4, 12), pady=11, side=tk.LEFT, expand=True)
        self.entry.bind("<Return>", self._on_submit)
        self.entry.bind("<FocusIn>",
                        lambda e: (self._clr_ph(), self.ib.config(bg=Col.accent2)))
        self.entry.bind("<FocusOut>", lambda e: self.ib.config(bg=Col.dim))

        self.mic_btn = tk.Label(ii, text="◉", font=("Consolas", 14), fg=Col.muted,
                                bg=Col.bg, cursor="hand2")
        self.mic_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.mic_btn.bind("<Button-1>", self._on_mic)
        self.mic_btn.bind("<Enter>", lambda e: self.mic_btn.config(fg=Col.accent2))
        self.mic_btn.bind("<Leave>", lambda e: self.mic_btn.config(
            fg=Col.muted if not self.is_listening else Col.danger))

        snd = tk.Label(ii, text="→", font=("Consolas", 16, "bold"), fg=Col.muted,
                       bg=Col.bg, cursor="hand2")
        snd.pack(side=tk.RIGHT, padx=(0, 4))
        snd.bind("<Button-1>", self._on_submit)
        snd.bind("<Enter>", lambda e: snd.config(fg=Col.accent))
        snd.bind("<Leave>", lambda e: snd.config(fg=Col.muted))

        self._set_ph()

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

    # --------------------------------------------------------------- Animate
    def _animate(self):
        self.tick += 1
        t = self.tick / FPS

        # Audio smooth
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

        # Init on first real frame
        if not self._ready:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw > 100 and ch > 100:
                self._init_renderer(cw, ch)
            else:
                self.root.after(50, self._animate)
                return

        # Render globe
        img = self.globe.render(t, a, self.bands_smooth)
        self._photo.paste(img)

        # Clear overlays
        self.canvas.delete("ov")

        cw, ch = self._cw, self._ch
        dcx, dcy = cw // 2, ch // 2
        sphere_r = min(cw, ch) * 0.37

        # Orbital ring (dashed, outside the globe)
        r1 = sphere_r + 25 + a * 10 + math.sin(t * 0.5) * 3
        self.canvas.create_oval(
            dcx - r1, dcy - r1, dcx + r1, dcy + r1,
            outline=Col.dim, width=1, dash=(3, 8), tags=("ov",))

        r2 = sphere_r + 55 + a * 15 + math.sin(t * 0.7) * 4
        self.canvas.create_oval(
            dcx - r2, dcy - r2, dcx + r2, dcy + r2,
            outline="#181818", width=1, dash=(2, 10), tags=("ov",))

        # Rotating tick marks on outer ring
        n_ticks = 32
        for i in range(n_ticks):
            angle = (i / n_ticks) * math.tau + t * 0.2
            ri = r2 - 4
            ro = r2 + 4
            x1 = dcx + math.cos(angle) * ri
            y1 = dcy + math.sin(angle) * ri
            x2 = dcx + math.cos(angle) * ro
            y2 = dcy + math.sin(angle) * ro
            c = Col.muted if i % 4 == 0 else "#1a1a1a"
            self.canvas.create_line(x1, y1, x2, y2, fill=c, width=1, tags=("ov",))

        # Dot-matrix text
        ly = dcy + sphere_r + 45
        draw_dot_text(self.canvas, "E.C.H.O.", dcx, ly,
                      dot=2.8, sp=1.3, color=Col.dot_on, ghost="")

        # State
        if self.is_listening:
            st, sc = "LISTENING", Col.danger
        elif self.is_thinking:
            st, sc = "PROCESSING", Col.warning
        else:
            st, sc = "READY", Col.muted
        draw_dot_text(self.canvas, st, dcx, ly + 28,
                      dot=1.5, sp=1.2, color=sc, ghost="")

        # Mic meter
        bw = int(a * 80)
        self.mcv.coords(self.mbar, 0, 0, bw, 4)
        if a > 0.3:
            self.mcv.itemconfig(self.mbar, fill=Col.green)
        elif a > 0.1:
            self.mcv.itemconfig(self.mbar, fill=Col.accent2)
        else:
            self.mcv.itemconfig(self.mbar, fill=Col.dim)

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
