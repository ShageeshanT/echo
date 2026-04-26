"""ECHO color palette + UI constants."""

WIN_W, WIN_H = 1280, 720
SIDEBAR_W = 60
FPS = 40
FRAME_MS = 25
NUM_DOTS = 7000
NUM_STROKES = 18


class C:
    bg      = "#08080e"
    bg2     = "#0c0c14"
    panel   = "#0b0b14"
    sidebar = "#0a0a12"
    border  = "#1c1c2e"
    card    = "#101020"
    card_br = "#1e1e35"      # card border
    accent  = "#eaeaf4"
    accent2 = "#a0a0bc"
    muted   = "#505068"
    dim     = "#282840"
    green   = "#00e676"
    purple  = "#b040ff"      # primary accent
    purple2 = "#8830cc"
    purple_d = "#2a1548"
    magenta = "#e040a0"
    cyan    = "#00d4ee"
    cyan2   = "#00a5bb"
    cyan_d  = "#003d48"
    danger  = "#ff2255"
    warning = "#ffaa00"
    dot_on  = "#d0d0e0"
    dot_off = "#141420"
    sleep   = "#1a1a30"


def lerp(a, b, t):
    return a + (b - a) * t
