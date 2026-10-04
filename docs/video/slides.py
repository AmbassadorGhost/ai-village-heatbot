"""New slides for the heatbot video: each element rendered as its own transparent layer."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;background:transparent}
body{font-family:'Liberation Sans',Arial,sans-serif;color:#c3ccd9;-webkit-font-smoothing:antialiased}
.wrap{position:absolute;left:130px;top:104px;width:1660px}
.eyebrow{font-weight:700;font-size:27px;letter-spacing:.24em;color:#f3c46c;text-transform:uppercase;margin-bottom:34px}
.title{font-weight:700;font-size:92px;line-height:1.07;letter-spacing:-.035em;color:#eef2f8}
.title.teal{color:#4fd1c5;margin-bottom:44px}
.h{font-weight:700;font-size:46px;line-height:1.22;letter-spacing:-.015em;color:#eef2f8;max-width:1500px;margin-bottom:34px}
.p{font-size:38px;line-height:1.42;color:#c3ccd9;max-width:1500px;margin-bottom:26px}
.p b,.h b{color:#eef2f8}
.li{font-size:36px;line-height:1.38;color:#c3ccd9;max-width:1480px;margin-bottom:22px;padding-left:40px;position:relative}
.li:before{content:'';position:absolute;left:4px;top:.55em;width:12px;height:12px;border-radius:50%;background:#4fd1c5}
.li b{color:#eef2f8}
.amber{color:#f3c46c}.teal{color:#4fd1c5}
.mono{font-family:'DejaVu Sans Mono',monospace}
.big{font-weight:700;font-size:150px;letter-spacing:-.04em;color:#eef2f8;line-height:1}
.big small{font-size:64px;font-weight:400;color:#9aa6b6;letter-spacing:-.01em}
.repo{font-family:'DejaVu Sans Mono',monospace;font-size:46px;color:#eef2f8;margin:10px 0 18px}
.foot{position:absolute;left:130px;top:968px;font-size:31px;letter-spacing:.02em;color:#a9b3c1}
"""

TITLE = ['<div class="title" data-t="0.25">Hear what agents say.</div>',
         '<div class="title teal" data-t="0.85">Watch what they do.</div>']

SLIDES = {
 "s01_title": ['<div class="eyebrow" data-t="0">AI Swarm Dynamics Hackathon · 3–4 Oct 2026</div>', *TITLE,
   '<div class="p" data-t="1.7"><b>heatbot</b>: cheap, always-on oversight for AI agent swarms. <span class="teal">Heat</span> reads what agents say for context; a <span class="amber">tripwire</span> watches what they do for harm.</div>',
   '<div class="foot" data-t="2.4">Adam Golsby &amp; Gregory Kasper · with AI collaborators</div>'],
 "s05_tested": ['<div class="eyebrow" data-t="0">Then we tested it like we meant it</div>',
   '<div class="h" data-t="0.3">Pre-registered. Frozen model. Results sealed until scored, on a month it had never seen.</div>',
   '<div class="p" data-t="2.6">What we learned shaped the design:</div>',
   '<div class="li" data-t="4.2"><b>Language is context.</b> Heat shows what is going on around each agent, with the exact messages behind every score.</div>',
   '<div class="li" data-t="6.6"><b>Actions are evidence.</b> What an agent does to the outside world is what an admin needs to see first.</div>',
   '<div class="li" data-t="9.0"><b>heatbot uses both</b>, each for the job it does best.</div>'],
 "s06_actions": ['<div class="eyebrow" data-t="0">Round 2 · What agents do</div>',
   '<div class="h" data-t="0.3">Then we added the other half: <span class="teal">the commands each agent runs.</span></div>',
   '<div class="p" data-t="2.6">Our first action signals fired on the Botme swarm\'s own site, <b>within three hours</b> of that day\'s first Botme message.</div>',
   '<div class="p" data-t="5.6">Then we sharpened them from what is <b>new</b> to what could do <span class="amber">harm</span>.</div>'],
 "s09_quiet": ['<div class="eyebrow" data-t="0">Quiet enough to trust</div>',
   '<div class="big" data-t="0.3">2 alerts <small>in 29 days</small></div>',
   '<div class="p" data-t="1.6" style="margin-top:30px"><span class="mono teal">0.48</span> a week, on a month never used for development.</div>',
   '<div class="h" data-t="3.4" style="margin-top:20px">Low noise means every notice gets read.</div>',
   '<div class="p" data-t="5.4"><span class="amber">URGENT</span> is reserved for direct harm: CAPTCHA-solving services and payments. Everything else arrives as a quiet <b>Detection</b>.</div>'],
 "s11_live": ['<div class="eyebrow" data-t="0">Live now</div>',
   '<div class="h" data-t="0.3">Running on both villages, from one command.</div>',
   '<div class="li" data-t="1.9"><b>Action notices</b> answer who, doing what, where, who else and who hasn\'t.</div>',
   '<div class="li" data-t="3.3">Each one links to <b>the exact moment</b> in the village replay.</div>',
   '<div class="li" data-t="4.7"><b>Heat</b> puts it in context, with the messages behind every score, and a <b>Needs help</b> channel for agents stuck on a blocker.</div>',
   '<div class="li" data-t="6.1">Scores a month of commands <b>in seconds on one CPU</b>, and can\'t be talked out of firing.</div>'],
 "s12_end": [*TITLE,
   '<div class="p" data-t="1.4"><b>heatbot</b>: cheap, always-on oversight for AI agent swarms, live on both villages.</div>',
   '<div class="repo" data-t="2.4">github.com/AmbassadorGhost/ai-village-heatbot</div>',
   '<div class="p" data-t="2.9">full write-up in <span class="mono teal">REPORT.md</span></div>',
   '<div class="foot" data-t="3.6">Adam Golsby &amp; Gregory Kasper · AI Swarm Dynamics Hackathon (AI Village × Grove Research), 2026</div>'],
}

meta = {}
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    for name, els in SLIDES.items():
        foot = [e for e in els if 'class="foot"' in e]
        body = [e for e in els if e not in foot]
        pg.set_content("<style>%s</style><div class=wrap>%s</div>%s" % (CSS, "".join(body), "".join(foot)))
        n = pg.evaluate("document.querySelectorAll('[data-t]').length")
        times = pg.evaluate("[...document.querySelectorAll('[data-t]')].map(e=>+e.dataset.t)")
        layers = []
        for i in range(n):
            pg.evaluate("i=>document.querySelectorAll('[data-t]').forEach((e,k)=>e.style.visibility=k===i?'visible':'hidden')", i)
            p = OUT / ("%s_%02d.png" % (name, i))
            pg.screenshot(path=str(p), omit_background=True)
            layers.append([str(p), times[i]])
        pg.evaluate("document.querySelectorAll('[data-t]').forEach(e=>e.style.visibility='visible')")
        pg.screenshot(path=str(OUT / ("%s_full.png" % name)), omit_background=True)
        meta[name] = layers
    b.close()
(OUT / "layers.json").write_text(json.dumps(meta, indent=1))
print("ok", {k: len(v) for k, v in meta.items()})
