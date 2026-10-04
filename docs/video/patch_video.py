"""Patch three stale spots in heatbot_hackathon.mp4 with fresh viewer screenshots.

A (31.8-45.2 s): Round 1 heat map + evidence panel -> new docs/viewer_heatmap.png / viewer_evidence.png
B (90.8-98.2 s): old "recorded replay" cards + caption -> new docs/viewer_action_panel.png
C (142-148 s):   "branch submission · full write-up in REPORT.md" -> "full write-up in REPORT.md"
Opacity of each patch follows the original slide's own fade, estimated from the old pixels.
"""
import subprocess, sys
import cv2
import numpy as np

SRC, OUT, DOCS = sys.argv[1], sys.argv[2], sys.argv[3]
FPS = 30
W, H = 1920, 1080


def frame_at(t):
    cap = cv2.VideoCapture(SRC)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * FPS)))
    ok, f = cap.read()
    cap.release()
    return f


def rounded_mask(w, h, r):
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r - 1, r), (r, h - r - 1), (w - r - 1, h - r - 1)):
        cv2.circle(m, (cx, cy), r, 255, -1)
    return (m / 255.0)[..., None]


def window(content, w, h, r=16):
    """content (h x w) inside a rounded panel with a 1px border."""
    panel = np.zeros((h, w, 3), np.float32)
    panel[:] = (37, 27, 18)                      # BGR #121b25
    panel[:content.shape[0], :content.shape[1]] = content
    border = np.zeros((h, w), np.uint8)
    cv2.rectangle(border, (0, 0), (w - 1, h - 1), 255, 1)
    m = rounded_mask(w, h, r)
    inner = rounded_mask(w - 2, h - 2, r - 1)
    ring = m.copy()
    ring[1:-1, 1:-1] -= inner
    panel = panel * (1 - ring) + np.array((66, 52, 37), np.float32) * ring   # #253442 line
    return panel, m


def shadow(bg, x, y, w, h, alpha):
    s = np.zeros(bg.shape[:2], np.float32)
    cv2.rectangle(s, (x, y + 12), (x + w, y + h + 12), 1.0, -1)
    s = cv2.GaussianBlur(s, (0, 0), 22) * 0.55 * alpha
    return bg * (1 - s[..., None])


def region_mean(f, box):
    x0, y0, x1, y1 = box
    return cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).mean()


# ---- A: heat map then evidence -------------------------------------------------
A_WIN = (860, 110, 930, 820)                     # x, y, w, h of the old window
A_PATCH = (800, 60, 1880, 1010)                  # area restored to background
A_PROBE = (880, 130, 1770, 910)
hm = cv2.imread(DOCS + "/viewer_heatmap.png").astype(np.float32)
s = A_WIN[3] / hm.shape[0]
hm = cv2.resize(hm, (int(hm.shape[1] * s), A_WIN[3]), interpolation=cv2.INTER_AREA)
ev = cv2.imread(DOCS + "/viewer_evidence.png").astype(np.float32)
s = A_WIN[2] / ev.shape[1]
ev = cv2.resize(ev, (A_WIN[2], int(ev.shape[0] * s)), interpolation=cv2.INTER_AREA)
EV_Y0, EV_Y1 = int(285 * s), int(ev.shape[0] - A_WIN[3])   # start below the old 138 score
A_T = (31.8, 45.2)
A_SWITCH = 38.28
A_BG = frame_at(31.5).astype(np.float32)
A_M_BG = region_mean(frame_at(31.5), A_PROBE)
A_M_HM = np.median([region_mean(frame_at(t), A_PROBE) for t in (33, 34, 35, 36, 37)])
A_M_EV = np.median([region_mean(frame_at(t), A_PROBE) for t in (40, 41, 42, 43)])

# ---- B: action notices ---------------------------------------------------------
B_PATCH = (90, 525, 1840, 1000)
B_PROBE = (140, 600, 1780, 860)
B_X, B_Y, B_W = 130, 540, 1660
an = cv2.imread(DOCS + "/viewer_action_panel.png").astype(np.float32)
s = B_W / an.shape[1]
an = cv2.resize(an, (B_W, int(an.shape[0] * s)), interpolation=cv2.INTER_AREA)
B_T = (90.8, 98.2)
B_BG = frame_at(90.5).astype(np.float32)
B_M_BG = region_mean(frame_at(90.5), B_PROBE)
B_M_ON = np.median([region_mean(frame_at(t), B_PROBE) for t in (93, 94, 95, 96)])

# ---- C: drop "branch submission ·" --------------------------------------------
C_BAND = (120, 588, 1000, 650)                   # x0, y0, x1, y1
C_FROM = 505                                     # "full write-up in REPORT.md" starts here
C_TO = 123
C_T = (141.0, 148.1)
C_BG = frame_at(140.5).astype(np.float32)


def alpha(m, bg, on):
    return float(np.clip((m - bg) / max(on - bg, 1e-3), 0, 1))


def patch(f, t):
    out = f.astype(np.float32)
    if A_T[0] <= t <= A_T[1]:
        x0, y0, x1, y1 = A_PATCH
        out[y0:y1, x0:x1] = A_BG[y0:y1, x0:x1]
        x, y, w, h = A_WIN
        if t < A_SWITCH:
            a = alpha(region_mean(f, A_PROBE), A_M_BG, A_M_HM)
            p = (t - A_T[0]) / (A_SWITCH - A_T[0])
            ox = int(p * (hm.shape[1] - w))
            content = hm[:, ox:ox + w]
        else:
            a = alpha(region_mean(f, A_PROBE), A_M_BG, A_M_EV)
            p = (t - A_SWITCH) / (A_T[1] - 0.3 - A_SWITCH)
            oy = int(EV_Y0 + min(p, 1) * (EV_Y1 - EV_Y0))
            content = ev[oy:oy + h]
        if a > 0:
            out = shadow(out, x, y, w, h, a)
            pane, m = window(content, w, h)
            m = m * a
            out[y:y + h, x:x + w] = out[y:y + h, x:x + w] * (1 - m) + pane * m
    if B_T[0] <= t <= B_T[1]:
        x0, y0, x1, y1 = B_PATCH
        out[y0:y1, x0:x1] = B_BG[y0:y1, x0:x1]
        a = alpha(region_mean(f, B_PROBE), B_M_BG, B_M_ON)
        if a > 0:
            h, w = an.shape[:2]
            out = shadow(out, B_X, B_Y, w, h, a)
            pane, m = window(an, w, h)
            m = m * a
            out[B_Y:B_Y + h, B_X:B_X + w] = out[B_Y:B_Y + h, B_X:B_X + w] * (1 - m) + pane * m
    if C_T[0] <= t <= C_T[1]:
        x0, y0, x1, y1 = C_BAND
        piece = f[y0:y1, C_FROM:x1].astype(np.float32)
        bgp = C_BG[y0:y1, C_FROM:x1]
        out[y0:y1, x0:x1] = C_BG[y0:y1, x0:x1]
        # move the text (difference from background) left, keeping its own fade
        diff = piece - bgp
        tw = x1 - C_FROM
        out[y0:y1, C_TO:C_TO + tw] = C_BG[y0:y1, C_TO:C_TO + tw] + diff
    return np.clip(out, 0, 255).astype(np.uint8)


cap = cv2.VideoCapture(SRC)
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "%dx%d" % (W, H),
                        "-r", str(FPS), "-i", "-", "-i", SRC, "-map", "0:v", "-map", "1:a", "-c:a", "copy",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", OUT], stdin=subprocess.PIPE)
i = 0
while True:
    ok, f = cap.read()
    if not ok:
        break
    t = i / FPS
    enc.stdin.write(patch(f, t).tobytes())
    i += 1
enc.stdin.close()
enc.wait()
print("frames", i)
