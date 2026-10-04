"""Replace six slides of the patched video with the new layered slides (same timings, same music)."""
import json, subprocess, sys
import cv2
import numpy as np

SRC, OUT, LAYERS, BG = sys.argv[1:5]
FPS, W, H = 30, 1920, 1080
bg = cv2.imread(BG).astype(np.float32)
meta = json.load(open(LAYERS + "/layers.json"))
layers = {k: [(cv2.imread(p, cv2.IMREAD_UNCHANGED).astype(np.float32), t) for p, t in v] for k, v in meta.items()}

# name: (replace_from, replace_to, content_start, content_end, fade_out)
PLAN = {"s01_title": (0.0, 7.2, 0.3, 6.9, True),
        "s05_tested": (44.9, 60.2, 45.5, 59.9, True),
        "s06_actions": (60.2, 72.2, 60.5, 71.9, True),
        "s09_quiet": (97.9, 110.2, 98.5, 109.9, True),
        "s11_live": (127.0, 139.1, 127.5, 138.9, True),
        "s12_end": (139.1, 999, 139.3, 999, False)}
FADE_IN, FADE_OUT = 0.45, 0.4


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def render(name, t):
    a0, a1, c0, c1, fo = PLAN[name]
    out = bg.copy()
    k = 1.0 if not fo else ease((c1 - t) / FADE_OUT)
    for img, ti in layers[name]:
        a = ease((t - c0 - ti) / FADE_IN) * k
        if a <= 0:
            continue
        al = img[..., 3:] / 255.0 * a
        # a small rise as each element appears, like the original
        dy = int(round((1 - ease((t - c0 - ti) / FADE_IN)) * 10))
        src = img[..., :3]
        if dy:
            src = np.roll(src, dy, axis=0); al = np.roll(al, dy, axis=0)
        out = out * (1 - al) + src * al
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
    for name, (a0, a1, *_r) in PLAN.items():
        if a0 <= t < a1:
            f = render(name, t)
            break
    enc.stdin.write(f.tobytes())
    i += 1
enc.stdin.close(); enc.wait()
print("frames", i)
