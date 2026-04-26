"""3D dot-globe renderer + background strokes (the visual heart of ECHO)."""

import math
import random

import numpy as np
from PIL import Image

from echo.ui.colors import NUM_STROKES


class Stroke:
    __slots__ = ("x0", "y0", "angle", "length", "speed", "life", "max_life", "brightness")

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
        if f < 0.15:
            return f / 0.15
        elif f > 0.75:
            return (1.0 - f) / 0.25
        return 1.0

    def endpoints(self):
        dx = math.cos(self.angle) * self.length
        dy = math.sin(self.angle) * self.length
        return self.x0, self.y0, self.x0 + dx, self.y0 + dy


def draw_line_buf(buf, x0, y0, x1, y1, bri, h, w):
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx_, dy_ = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx_ - dy_
    for _ in range(dx_ + dy_ + 2):
        if 0 <= y0 < h and 0 <= x0 < w:
            buf[y0, x0] = max(buf[y0, x0], bri)
            if y0 + 1 < h:
                buf[y0 + 1, x0] = max(buf[y0 + 1, x0], bri * 0.3)
            if x0 + 1 < w:
                buf[y0, x0 + 1] = max(buf[y0, x0 + 1], bri * 0.3)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy_:
            err -= dy_
            x0 += sx
        if e2 < dx_:
            err += dx_
            y0 += sy


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
                if abs(dx) <= 1 and abs(dy) <= 1:
                    continue
                self._k5.append((dx, dy, 0.08 / max(abs(dx) + abs(dy), 1)))

    def render(self, t, audio, bands, brightness_mult=1.0):
        w, h, n = self.w, self.h, self.n
        cx, cy = w / 2, h / 2

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

        self._deform_cur += (d_tgt - self._deform_cur) * 0.22
        deform = self._deform_cur
        xs = self.bx * deform
        ys = self.by * deform
        zs = self.bz * deform

        ay = t * 0.35 + audio * t * 0.2
        ax = 0.35 + math.sin(t * 0.15) * 0.15
        az = math.sin(t * 0.1) * 0.08

        co, si = math.cos(ay), math.sin(ay)
        nx = xs * co + zs * si
        nz = -xs * si + zs * co
        xs, zs = nx, nz
        co, si = math.cos(ax), math.sin(ax)
        ny = ys * co - zs * si
        nz = ys * si + zs * co
        ys, zs = ny, nz
        co, si = math.cos(az), math.sin(az)
        nx = xs * co - ys * si
        ny = xs * si + ys * co
        xs, ys = nx, ny

        radius = min(w, h) * 0.28
        sx = (xs * radius + cx).astype(np.int32)
        sy = (ys * radius + cy).astype(np.int32)
        z_norm = (zs - zs.min()) / (zs.max() - zs.min() + 1e-9)
        bright = (30 + 225 * z_norm).astype(np.float32) * brightness_mult
        order = np.argsort(bright)
        sx, sy, bright = sx[order], sy[order], bright[order]

        decay = 0.78 + audio * 0.1
        self.buf *= decay

        for s in self.strokes:
            s.update(w, h)
            a = s.alpha
            if a > 0.05:
                x0, y0, x1, y1 = s.endpoints()
                draw_line_buf(self.buf, x0, y0, x1, y1, s.brightness * a * brightness_mult, h, w)

        nf = np.zeros((h, w), dtype=np.float32)
        for dx, dy, f in self._k3:
            gx = sx + dx
            gy = sy + dy
            v = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
            np.maximum.at(nf, (gy[v], gx[v]), bright[v] * f)
        front = bright > 140 * brightness_mult
        if np.any(front):
            fs, fy2, fb = sx[front], sy[front], bright[front]
            for dx, dy, f in self._k5:
                gx = fs + dx
                gy = fy2 + dy
                v = (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
                np.maximum.at(nf, (gy[v], gx[v]), fb[v] * f)

        np.maximum(self.buf, nf, out=self.buf)
        np.clip(self.buf, 0, 255, out=self.buf)

        g = np.clip(self.buf, 0, 255).astype(np.uint8)
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        rgb[:, :, 0] = (g * 0.80).astype(np.uint8)
        rgb[:, :, 1] = (g * 0.90).astype(np.uint8)
        rgb[:, :, 2] = g
        return Image.fromarray(rgb)
