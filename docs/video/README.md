# How the video was made

`docs/heatbot_hackathon.mp4` started as Greg's side's 2½-minute slide video, made on 3–4 Oct. On 4 Oct it was updated in two passes to match the live system. The music and the timing are unchanged.

1. `patch_video.py` replaces three things with Adam's fresh viewer screenshots:
   - the Round 1 heat map and evidence panel;
   - the notices panel;
   - the stale branch name on the last slide.
2. `slides.py` renders six rewritten slides as separate layers, using Playwright. `compose.py` then puts them back in their original time slots.

The rewritten slides are the title, "tested it like we meant it", "the other half", "quiet enough to trust", "live now" and the end card.

```
python3 patch_video.py original.mp4 patched.mp4 ../
python3 slides.py layers && python3 compose.py patched.mp4 final.mp4 layers bg.png
```

`bg.png` is a blank frame of the original video, taken at 7.2 s.
