"""Build the SVG assets for the GitHub profile README.

GitHub strips CSS from READMEs, so the typography lives inside SVG images:
Manrope (body) and Space Grotesk (display) are subset per image and embedded
as base64 WOFF. Every asset is written twice, light and dark, and the README
switches between them with <picture> + prefers-color-scheme.

Run:  python tools/build_assets.py
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
FONTS = Path(__file__).resolve().parent / "fonts"
OUT = ROOT / "assets"

# ---------------------------------------------------------------- fonts

FACES = {
    "display": ("SpaceGrotesk.ttf", 600),
    "display-b": ("SpaceGrotesk.ttf", 700),
    "label": ("SpaceGrotesk.ttf", 500),
    "body": ("Manrope.ttf", 400),
    "body-m": ("Manrope.ttf", 500),
    "body-s": ("Manrope.ttf", 600),
}

_instances: dict[str, bytes] = {}
_metrics: dict[str, tuple[dict, dict, int]] = {}


def _instance(face: str) -> bytes:
    if face not in _instances:
        file, weight = FACES[face]
        font = TTFont(FONTS / file)
        inst = instancer.instantiateVariableFont(font, {"wght": weight})
        buf = io.BytesIO()
        inst.save(buf)
        _instances[face] = buf.getvalue()
        f = TTFont(io.BytesIO(_instances[face]))
        _metrics[face] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
    return _instances[face]


def measure(text: str, face: str, size: float, tracking: float = 0) -> float:
    _instance(face)
    cmap, hmtx, upm = _metrics[face]
    total = 0
    for ch in text:
        glyph = cmap.get(ord(ch))
        if glyph is None:
            raise ValueError(f"{face} has no glyph for {ch!r}")
        total += hmtx[glyph][0]
    return total * size / upm + tracking * max(len(text) - 1, 0)


def wrap(text: str, face: str, size: float, width: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if measure(trial, face, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def font_css(used: dict[str, set[str]]) -> str:
    rules = []
    for face, chars in sorted(used.items()):
        opts = subset.Options()
        opts.flavor = "woff"
        opts.layout_features = ["kern", "liga", "calt"]
        opts.name_IDs = []
        opts.notdef_outline = True
        font = TTFont(io.BytesIO(_instance(face)))
        sub = subset.Subsetter(opts)
        sub.populate(text="".join(chars) + " ")
        sub.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff"
        font.save(buf)
        data = base64.b64encode(buf.getvalue()).decode()
        rules.append(
            f"@font-face{{font-family:'{face}';src:url(data:font/woff;base64,{data}) format('woff');}}"
        )
    return "".join(rules)


# ---------------------------------------------------------------- themes
# shadcn/ui "zinc" tokens

THEMES = {
    "light": dict(
        bg="#ffffff", card="#ffffff", fg="#09090b", muted="#71717a", subtle="#a1a1aa",
        secondary="#f4f4f5", border="#e4e4e7", ring="#d4d4d8", primary="#18181b",
        primary_fg="#fafafa", dot="#e4e4e7", shadow="0.06",
    ),
    "dark": dict(
        bg="#09090b", card="#09090b", fg="#fafafa", muted="#a1a1aa", subtle="#71717a",
        secondary="#18181b", border="#27272a", ring="#3f3f46", primary="#fafafa",
        primary_fg="#18181b", dot="#27272a", shadow="0",
    ),
}

ACCENTS = {
    "blue": "#3b82f6", "violet": "#8b5cf6", "amber": "#f59e0b",
    "emerald": "#10b981", "rose": "#f43f5e", "sky": "#0ea5e9",
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Svg:
    def __init__(self, w: int, h: int, theme: str, title: str):
        self.w, self.h, self.t = w, h, THEMES[theme]
        self.title = title
        self.parts: list[str] = []
        self.defs: list[str] = []
        self.used: dict[str, set[str]] = {}

    def add(self, s: str) -> None:
        self.parts.append(s)

    def text(self, x, y, s, face="body", size=14, fill=None, anchor="start",
             tracking=0.0, opacity=None) -> float:
        self.used.setdefault(face, set()).update(s)
        fill = fill or self.t["fg"]
        extra = f' letter-spacing="{tracking}"' if tracking else ""
        extra += f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{face}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}"{extra}>{esc(s)}</text>'
        )
        return measure(s, face, size, tracking)

    def rect(self, x, y, w, h, r=8, fill=None, stroke=None, sw=1, extra=""):
        fill = fill or "none"
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
            f'fill="{fill}"{st}{extra}/>'
        )

    def card(self, x, y, w, h, r=14):
        t = self.t
        if t["shadow"] != "0":
            self.rect(x, y + 1, w, h, r, fill="#000", extra=f' opacity="{t["shadow"]}"')
        self.rect(x, y, w, h, r, fill=t["card"], stroke=t["border"])

    def chip(self, x, y, label, variant="outline", size=13, h=28, pad=12,
             face="body-m", dot=None) -> float:
        t = self.t
        tw = measure(label, face, size)
        dw = 14 if dot else 0
        w = tw + pad * 2 + dw
        if variant == "primary":
            self.rect(x, y, w, h, h / 2, fill=t["primary"])
            col = t["primary_fg"]
        elif variant == "secondary":
            self.rect(x, y, w, h, h / 2, fill=t["secondary"])
            col = t["fg"]
        else:
            self.rect(x + 0.5, y + 0.5, w - 1, h - 1, h / 2, fill=t["card"], stroke=t["border"])
            col = t["fg"]
        if dot:
            self.add(f'<circle cx="{x + pad + 3.5:.1f}" cy="{y + h / 2:.1f}" r="3.5" fill="{dot}"/>')
        self.text(x + pad + dw, y + h / 2 + size * 0.36, label, face, size, col)
        return w

    def arrow(self, x1, y, x2, color=None):
        c = color or self.t["subtle"]
        self.add(
            f'<path d="M{x1:.1f} {y:.1f}H{x2 - 1:.1f}" stroke="{c}" stroke-width="1.5" '
            f'stroke-linecap="round"/>'
            f'<path d="M{x2 - 5:.1f} {y - 4:.1f}L{x2:.1f} {y:.1f}L{x2 - 5:.1f} {y + 4:.1f}" '
            f'fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round" '
            f'stroke-linejoin="round"/>'
        )

    def render(self) -> str:
        css = font_css(self.used) + "text{font-kerning:normal;}"
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(self.title)}">'
            f"<title>{esc(self.title)}</title>"
            f"<defs><style>{css}</style>{''.join(self.defs)}</defs>"
            + "".join(self.parts)
            + "</svg>"
        )


def save(name: str, build) -> None:
    for theme in THEMES:
        svg = build(theme)
        path = OUT / f"{name}-{theme}.svg"
        path.write_text(svg.render(), encoding="utf-8")
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")


# ---------------------------------------------------------------- header

def header(theme: str) -> Svg:
    W, H = 1200, 380
    s = Svg(W, H, theme, "Albert Mwangwa. Software engineer building applied AI and data products.")
    t = s.t
    s.defs.append(
        f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="1.5" cy="1.5" r="1.2" fill="{t["dot"]}"/></pattern>'
        '<radialGradient id="fade" cx="78%" cy="35%" r="70%">'
        '<stop offset="0" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset="0.65" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        '<mask id="m"><rect width="1200" height="380" fill="url(#fade)"/></mask>'
        '<clipPath id="clip"><rect x="1" y="1" width="1198" height="376" rx="18"/></clipPath>'
    )
    s.card(1, 1, W - 2, H - 4, 18)
    s.add('<g clip-path="url(#clip)"><rect width="1200" height="380" fill="url(#dots)" mask="url(#m)"/></g>')

    x = 56
    s.chip(x, 52, "Open to collaboration", "outline", 13, 30, 13, "body-m", dot=ACCENTS["emerald"])
    s.text(x - 3, 150, "Albert Mwangwa", "display-b", 64, tracking=-1.6)
    sub = ("Software engineer building applied AI: computer vision, "
           "signal processing and data products that work outside the lab.")
    for i, line in enumerate(wrap(sub, "body-m", 20, 640)):
        s.text(x, 198 + i * 30, line, "body-m", 20, t["muted"])
    cx = x
    for label in ["Computer vision", "Machine learning", "Probabilistic models", "Full-stack"]:
        cx += s.chip(cx, 290, label, "secondary", 13, 30, 13) + 8

    # "Now building" panel
    px, py, pw, ph = 790, 52, 354, 270
    s.rect(px, py, pw, ph, 14, fill=t["card"], stroke=t["border"])
    s.text(px + 24, py + 38, "NOW BUILDING", "label", 12, t["muted"], tracking=1.4)
    s.add(f'<circle cx="{px + pw - 30}" cy="{py + 34}" r="4" fill="{ACCENTS["emerald"]}"/>'
          f'<circle cx="{px + pw - 30}" cy="{py + 34}" r="8" fill="{ACCENTS["emerald"]}" opacity="0.18"/>')
    s.text(px + 24, py + 80, "Darubini", "display", 28, tracking=-0.4)
    desc = "A malaria microscopy copilot. It counts parasites field by field and reports in Kiswahili or English."
    for i, line in enumerate(wrap(desc, "body", 15, pw - 48)):
        s.text(px + 24, py + 112 + i * 23, line, "body", 15, t["muted"])
    s.add(f'<path d="M{px} {py + 200}H{px + pw}" stroke="{t["border"]}"/>')
    bx = px + 24
    for label in ["Python", "SAM 3.1", "Muse Spark"]:
        bx += s.chip(bx, py + 220, label, "outline", 12, 26, 10) + 6
    return s


# ---------------------------------------------------------------- overview diagram

INPUTS = [
    ("Microscope fields", "thick-film blood smears", "cv"),
    ("Camera streams", "ONVIF / RTSP video", "cv"),
    ("EEG recordings", "multichannel CSV", "sig"),
    ("Bookmaker markets", "200 to 950 markets a fixture", "prob"),
    ("Market & fund data", "DSE, unit trusts, BoT", "data"),
    ("Biometric devices", "ZKTeco attendance", "web"),
]
METHODS = {
    "cv": ("Computer vision", "segmentation, tracking, OCR", ACCENTS["blue"]),
    "sig": ("Signal processing & ML", "MNE, scikit-learn, TensorFlow", ACCENTS["violet"]),
    "prob": ("Probabilistic models", "Dixon-Coles, negative binomial", ACCENTS["amber"]),
    "data": ("Data pipelines", "scheduled refresh, de-vig, EV", ACCENTS["emerald"]),
    "web": ("Product engineering", "React, Next.js, Express, SQL", ACCENTS["rose"]),
}
PRODUCTS = [
    ("Darubini", "malaria parasite counts", ["cv", "web"]),
    ("Trakt", "text search across cameras", ["cv", "sig"]),
    ("EEG-Analysis", "brain-signal classifiers", ["sig"]),
    ("Jakita", "match predictions & value picks", ["prob", "data", "web"]),
    ("Mtaji", "Tanzania investment planner", ["data", "web"]),
    ("HRMastermind", "HR platform with biometrics", ["web"]),
]


def overview(theme: str) -> Svg:
    W, H = 1200, 600
    s = Svg(W, H, theme, "Diagram: the data I start from, the methods I use, and the projects they become.")
    t = s.t
    s.card(1, 1, W - 2, H - 4, 18)

    cols = [(48, "01", "Signals in"), (470, "02", "Methods"), (892, "03", "Shipped as")]
    nw, nh = 260, 58
    for x, num, label in cols:
        s.text(x, 58, num, "label", 13, t["subtle"], tracking=0.5)
        s.text(x + 28, 58, label.upper(), "label", 13, t["muted"], tracking=1.4)
    s.add(f'<path d="M48 80H{W - 48}" stroke="{t["border"]}"/>')

    top, bottom = 104, H - 40

    def ys(n):
        gap = (bottom - top - n * nh) / (n - 1)
        return [top + i * (nh + gap) for i in range(n)]

    in_y = ys(len(INPUTS))
    m_keys = list(METHODS)
    m_y = dict(zip(m_keys, ys(len(m_keys))))
    p_y = ys(len(PRODUCTS))

    def curve(x1, y1, x2, y2, color, op):
        mx = (x1 + x2) / 2
        s.add(f'<path d="M{x1} {y1:.1f}C{mx} {y1:.1f} {mx} {y2:.1f} {x2} {y2:.1f}" fill="none" '
              f'stroke="{color}" stroke-width="1.5" opacity="{op}"/>')

    # connectors first, so nodes sit above them
    for (_, _, key), y in zip(INPUTS, in_y):
        curve(48 + nw, y + nh / 2, 470, m_y[key] + nh / 2, METHODS[key][2], 0.55)
    for (_, _, keys), y in zip(PRODUCTS, p_y):
        for k in keys:
            curve(470 + nw, m_y[k] + nh / 2, 892, y + nh / 2, METHODS[k][2], 0.55)

    def node(x, y, title, sub, color=None, strong=False):
        s.rect(x, y, nw, nh, 10, fill=t["secondary"] if strong else t["card"], stroke=t["border"])
        tx = x + 16
        if color:
            s.rect(x + 14, y + 17, 8, 24, 4, fill=color)
            tx = x + 34
        s.text(tx, y + 25, title, "display", 16, tracking=-0.1)
        s.text(tx, y + 44, sub, "body", 12.5, t["muted"])

    for (title, sub, _), y in zip(INPUTS, in_y):
        node(48, y, title, sub)
        s.add(f'<circle cx="{48 + nw}" cy="{y + nh / 2:.1f}" r="3" fill="{t["card"]}" stroke="{t["ring"]}" stroke-width="1.5"/>')
    for k, y in m_y.items():
        title, sub, color = METHODS[k]
        node(470, y, title, sub, color, strong=True)
    for (title, sub, _), y in zip(PRODUCTS, p_y):
        node(892, y, title, sub)
        s.add(f'<circle cx="892" cy="{y + nh / 2:.1f}" r="3" fill="{t["card"]}" stroke="{t["ring"]}" stroke-width="1.5"/>')
    return s


# ---------------------------------------------------------------- project cards

PROJECTS = {
    "darubini": dict(
        title="Darubini", lang=("Python", "#3572A5"),
        desc="Turns an ordinary lab microscope into a malaria counting copilot. "
             "Every count is audited, and reports come out in Kiswahili or English.",
        steps=["Eyepiece camera", "SAM 3.1 segment", "Count & audit", "Report"],
    ),
    "trakt": dict(
        title="Trakt", lang=("Python", "#3572A5"),
        desc="Reads text from existing IP cameras: plates, container codes, serials. "
             "Logs every detection and alerts on the patterns you care about.",
        steps=["RTSP stream", "EAST detect", "OCR / CRNN", "SQLite + alerts"],
    ),
    "mtaji": dict(
        title="Mtaji", lang=("HTML", "#e34c26"),
        desc="A Tanzania investment planner with live data for unit trusts, DSE shares "
             "and Bank of Tanzania securities. No build step, refreshed on a schedule.",
        steps=["UTT, DSE, BoT", "Actions refresh", "Static site", "Plan"],
    ),
    "jakita": dict(
        title="Jakita", lang=("Python", "#3572A5"),
        desc="Football and basketball predictions anchored on the full bookmaker book, "
             "adjusted with stats, team news and tipster consensus.",
        steps=["Market book", "De-vig", "Fit models", "EV picks"],
    ),
    "hrmastermind": dict(
        title="HRMastermind", lang=("TypeScript", "#3178c6"),
        desc="Full-stack HR platform covering recruitment to payroll, with four-tier "
             "role-based access and ZKTeco biometric attendance.",
        steps=["ZKTeco device", "Express API", "PostgreSQL", "React app"],
    ),
    "eeg": dict(
        title="EEG-Analysis", lang=("Jupyter Notebook", "#DA5B0B"),
        desc="EEG recordings from raw CSV to trained models: MNE preprocessing, "
             "topographies, feature extraction and scikit-learn evaluation.",
        steps=["CSV signals", "MNE filter", "Features", "Classify / rank"],
    ),
}


def project_card(key: str):
    p = PROJECTS[key]

    def build(theme: str) -> Svg:
        W, H, pad = 580, 212, 28
        s = Svg(W, H, theme, f"{p['title']}: {p['desc']}")
        t = s.t
        s.card(1, 1, W - 2, H - 4, 14)
        s.text(pad, 52, p["title"], "display", 23, tracking=-0.3)
        lang, color = p["lang"]
        lw = measure(lang, "body-m", 12.5)
        s.text(W - pad, 48, lang, "body-m", 12.5, t["muted"], anchor="end")
        s.add(f'<circle cx="{W - pad - lw - 10:.1f}" cy="44" r="4.5" fill="{color}"/>')
        for i, line in enumerate(wrap(p["desc"], "body", 14.5, W - pad * 2)[:3]):
            s.text(pad, 84 + i * 22, line, "body", 14.5, t["muted"])

        # mini pipeline
        steps, gap, size = p["steps"], 26, 12.5
        avail = W - pad * 2
        while True:
            widths = [measure(x, "body-m", size) + 22 for x in steps]
            total = sum(widths) + gap * (len(steps) - 1)
            if total <= avail or size <= 10:
                break
            size -= 0.5
        extra = (avail - total) / len(steps)
        x, y, h = pad, 144, 36
        for i, (label, w) in enumerate(zip(steps, widths)):
            w += extra
            last = i == len(steps) - 1
            if last:
                s.rect(x, y, w, h, 8, fill=t["primary"])
            else:
                s.rect(x + 0.5, y + 0.5, w - 1, h - 1, 8, fill=t["secondary"], stroke=t["border"])
            s.text(x + w / 2, y + h / 2 + size * 0.36, label, "body-m", size,
                   t["primary_fg"] if last else t["fg"], anchor="middle")
            if not last:
                s.arrow(x + w + 6, y + h / 2, x + w + gap - 6)
            x += w + gap
        return s

    return build


# ---------------------------------------------------------------- stack

STACK = [
    ("Languages", ["Python", "TypeScript", "SQL", "Shell", "HTML / CSS"]),
    ("AI & data", ["TensorFlow", "scikit-learn", "MNE", "SAM 3.1", "OpenCV", "Jupyter"]),
    ("Web", ["React", "Next.js", "Express", "Tailwind CSS", "shadcn/ui", "Drizzle ORM"]),
    ("Data & ops", ["PostgreSQL", "SQLite", "GitHub Actions", "GitHub Pages", "Git"]),
]


def stack(theme: str) -> Svg:
    W = 1200
    row_h, top = 56, 40
    H = top + row_h * len(STACK) + 24
    s = Svg(W, H, theme, "Tools I use: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in STACK))
    t = s.t
    s.card(1, 1, W - 2, H - 4, 18)
    for i, (label, items) in enumerate(STACK):
        y = top + i * row_h
        if i:
            s.add(f'<path d="M40 {y - 14}H{W - 40}" stroke="{t["border"]}" stroke-dasharray="3 4"/>')
        s.text(48, y + 20, label.upper(), "label", 12.5, t["muted"], tracking=1.4)
        x = 230
        for item in items:
            x += s.chip(x, y, item, "outline", 13.5, 30, 14) + 10
    return s


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    save("header", header)
    save("overview", overview)
    for k in PROJECTS:
        save(f"project-{k}", project_card(k))
    save("stack", stack)
