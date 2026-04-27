#!/usr/bin/env python3
"""Generate Google Business Profile verification video.
Creates clean PNG slides + ffmpeg slideshow with crossfades.
"""
import csv, struct, subprocess, tempfile, zlib
from pathlib import Path

ROOT = Path(__file__).parent
OUT  = Path(__file__).parent / "assets" / "business_verification.mp4"
TMP  = Path(tempfile.mkdtemp(prefix="catslides_"))

W, H = 1280, 720

# ── Colors ─────────────────────────────────────────────────────────────────
NAVY   = (10, 15, 30)
DARK   = (15, 22, 50)
BLUE   = (59, 130, 246)
PURPLE = (139, 92, 246)
WHITE  = (255, 255, 255)
GRAY   = (148, 163, 184)
GREEN  = (16, 185, 129)
RED    = (239, 68, 68)
AMBER  = (245, 158, 11)

def lerp(c1, c2, t):
    return tuple(int(c1[i]*(1-t)+c2[i]*t) for i in range(3))

# ── PNG writer ─────────────────────────────────────────────────────────────
def write_png(path, pixels):
    h_img, w_img = len(pixels), len(pixels[0])
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in pixels)
    def chunk(n, d):
        c = struct.pack(">I",len(d))+n+d
        return c+struct.pack(">I",zlib.crc32(n+d)&0xFFFFFFFF)
    sig  = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB",w_img,h_img,8,2,0,0,0))
    idat = chunk(b"IDAT", zlib.compress(raw,1))
    iend = chunk(b"IEND", b"")
    Path(path).write_bytes(sig+ihdr+idat+iend)

# ── Drawing ────────────────────────────────────────────────────────────────
def canvas(bg=NAVY):
    return [[list(bg) for _ in range(W)] for _ in range(H)]

def rect(px, x1, y1, x2, y2, c):
    for y in range(max(0,y1),min(H,y2)):
        for x in range(max(0,x1),min(W,x2)):
            px[y][x] = list(c)

def grad_h(px, x1, y1, x2, y2, c1, c2):
    for y in range(max(0,y1),min(H,y2)):
        for x in range(max(0,x1),min(W,x2)):
            t = (x-x1)/max(1,x2-x1)
            px[y][x] = list(lerp(c1,c2,t))

def circle(px, cx, cy, r, c):
    for y in range(max(0,cy-r),min(H,cy+r+1)):
        for x in range(max(0,cx-r),min(W,cx+r+1)):
            if (x-cx)**2+(y-cy)**2<=r**2:
                px[y][x] = list(c)

def bolt(px, ox, oy, s, c1=BLUE, c2=PURPLE):
    pts=[(230,60),(140,220),(195,220),(170,340),(290,175),(225,175),(260,60)]
    sc=[(int((p[0]-200)*s)+ox,int((p[1]-200)*s)+oy) for p in pts]
    for y in range(max(0,min(p[1]for p in sc)),min(H,max(p[1]for p in sc)+1)):
        xs=[]
        n=len(sc)
        for i in range(n):
            x1_,y1_=sc[i]; x2_,y2_=sc[(i+1)%n]
            if (y1_<=y<y2_)or(y2_<=y<y1_):
                if y2_!=y1_:
                    xs.append(int(x1_+(y-y1_)*(x2_-x1_)/(y2_-y1_)))
        xs.sort()
        for k in range(0,len(xs)-1,2):
            for x in range(max(0,xs[k]),min(W,xs[k+1]+1)):
                t=((x-ox)+(y-oy))/(s*280*2)
                px[y][x]=list(lerp(c1,c2,max(0,min(1,t))))

# ── Slides ──────────────────────────────────────────────────────────────────
def slide_01():
    """Business identity."""
    px = canvas(NAVY)
    grad_h(px, 0, 0, W, H, NAVY, (12, 18, 50))
    # Left accent
    grad_h(px, 0, 0, 8, H, BLUE, PURPLE)
    # Top bar
    rect(px, 0, 0, W, 88, DARK)
    grad_h(px, 0, 84, W, 88, BLUE, PURPLE)
    # Logo
    circle(px, 64, 44, 30, (20, 30, 65))
    bolt(px, 42, 10, 0.18)
    # Right side large logo
    circle(px, 950, 360, 200, (15, 22, 48))
    circle(px, 950, 360, 196, NAVY)
    bolt(px, 870, 220, 1.2)
    # Content
    grad_h(px, 60, 130, 700, 180, WHITE, (200, 220, 255))  # Title block
    rect(px, 60, 190, 500, 210, GRAY)  # subtitle
    rect(px, 60, 240, 3, 260, BLUE)  # accent
    grad_h(px, 70, 265, 420, 285, BLUE, (100, 160, 246))  # Business Name label
    rect(px, 70, 295, 560, 340, (20, 32, 70))  # Category
    rect(px, 70, 350, 4, 350+120, GRAY)
    rect(px, 80, 360, 460, 378, GRAY)  # website
    rect(px, 80, 388, 390, 406, GRAY)  # email
    rect(px, 80, 416, 320, 432, GRAY)  # location
    # Bottom bar
    grad_h(px, 0, H-60, W, H, BLUE, PURPLE)
    rect(px, 0, H-58, W, H, DARK)
    rect(px, 40, H-45, 600, H-18, (40, 60, 120))
    return px

def slide_02():
    """Newsletter showcase."""
    px = canvas(DARK)
    # Header
    rect(px, 0, 0, W, 80, NAVY)
    grad_h(px, 0, 76, W, 80, BLUE, PURPLE)
    grad_h(px, 40, 15, 420, 60, WHITE, (200, 220, 255))
    rect(px, 40, 70, 640, 82, GRAY)
    # Newsletter card
    rect(px, 30, 100, W-30, H-30, NAVY)
    grad_h(px, 30, 100, W-30, 170, (10,15,30), (20,30,60))
    grad_h(px, 30, 166, W-30, 170, BLUE, PURPLE)
    rect(px, 50, 110, 300, 140, GRAY)  # title
    rect(px, 50, 148, 500, 162, (40,60,100))  # subtitle
    # Stats row
    for i,(c,lbl) in enumerate([(BLUE,"GAPPERS"),(GREEN,"VALUE"),(PURPLE,"MOAT"),(AMBER,"PICKS")]):
        x = 50 + i*290
        rect(px, x, 185, x+260, 240, (18,26,55))
        rect(px, x, 185, x+260, 190, c)
        rect(px, x+10, 200, x+120, 222, c)
        rect(px, x+10, 228, x+180, 238, GRAY)
    # Picks section
    rect(px, 50, 260, W-60, 266, (30,50,100))
    for i,(c,label) in enumerate([(RED,"GAPPER"),(BLUE,"VALUE"),(PURPLE,"MOAT")]):
        y = 280 + i*115
        rect(px, 50, y, W-60, y+100, (14,20,45))
        rect(px, 50, y, 54, y+100, c)
        circle(px, 90, y+50, 22, c)
        rect(px, 120, y+14, 280, y+38, c)
        rect(px, 120, y+46, 500, y+62, GRAY)
        rect(px, 750, y+20, 200, 40, (c[0]//3,c[1]//3,c[2]//3))
        grad_h(px, 760, y+24, 760+int(180*0.8), y+52, c, lerp(c,WHITE,0.3))
    return px

def slide_03():
    """Today's picks."""
    px = canvas(NAVY)
    grad_h(px, 0, 0, W, H, NAVY, (10,18,50))
    rect(px, 0, 0, W, 80, DARK)
    grad_h(px, 0, 76, W, 80, BLUE, PURPLE)
    grad_h(px, 40, 8, 320, 50, RED, AMBER)
    rect(px, 40, 58, 700, 72, GRAY)
    # Load picks
    try:
        rows = list(csv.DictReader((ROOT/"combined_priority.csv").open()))
        picks = [(r["ticker"], r.get("total_score","0")) for r in rows[:5] if r.get("ticker")]
    except:
        picks = [("APTV","13.2"),("CRMD","11.0"),("BXP","10.8"),("DINO","9.5"),("YPF","8.1")]
    picks = (picks + [("---","0")]*5)[:5]
    colors = [BLUE, GREEN, PURPLE, RED, AMBER]
    for i, ((ticker, score), c) in enumerate(zip(picks, colors)):
        y = 100 + i*110
        rect(px, 40, y, W-40, y+96, (14,20,46))
        grad_h(px, 40, y, 46, y+96, c, lerp(c,PURPLE,0.5))
        circle(px, 88, y+48, 28, c)
        rect(px, 130, y+12, 130+len(ticker)*18, y+44, c)
        try: sc = float(score)
        except: sc = 8.0
        bw = min(400, int(sc*28))
        grad_h(px, 130, y+58, 130+bw, y+78, c, lerp(c,WHITE,0.3))
        rect(px, W-300, y+20, 200, 56, (c[0]//3,c[1]//3,c[2]//3))
        rect(px, W-290, y+28, 180, 20, c)
        rect(px, W-290, y+52, 140, 12, GRAY)
    grad_h(px, 0, H-50, W, H, BLUE, PURPLE)
    rect(px, 0, H-48, W, H, DARK)
    rect(px, 40, H-38, 500, H-12, (30,50,100))
    return px

def slide_04():
    """Website proof."""
    px = canvas((15,20,40))
    # Browser
    rect(px, 20, 20, W-20, 90, (35,45,75))
    circle(px, 55, 55, 10, RED)
    circle(px, 82, 55, 10, AMBER)
    circle(px, 109, 55, 10, GREEN)
    rect(px, 135, 35, W-160, 75, (20,28,65))
    grad_h(px, 140, 40, 140+500, 70, BLUE, PURPLE)
    rect(px, 660, 40, 200, 30, (30,40,80))
    rect(px, 870, 40, 160, 30, (30,40,80))
    # Page content
    rect(px, 20, 90, W-20, H-20, (245,247,250))
    rect(px, 20, 90, W-20, 180, (10,15,30))
    bolt(px, 50, 95, 0.25)
    rect(px, 110, 100, 350, 135, WHITE)
    rect(px, 110, 142, 600, 162, GRAY)
    rect(px, 950, 105, 200, 55, BLUE)
    # Content sections
    for i in range(3):
        x = 50 + i*400
        rect(px, x, 200, x+370, 380, WHITE)
        rect(px, x, 200, x+370, 230, (10,15,30))
        c = [BLUE, GREEN, PURPLE][i]
        rect(px, x, 200, x+4, 380, c)
        rect(px, x+10, 208, x+200, 224, c)
        for j in range(5):
            y2 = 248 + j*26
            rect(px, x+10, y2, x+300+j*10, y2+14, (220,225,235))
    # Footer
    grad_h(px, 20, H-60, W-20, H-20, (10,15,30), (15,22,50))
    rect(px, 50, H-50, 400, H-28, (30,50,100))
    return px

def slide_05():
    """CTA outro."""
    px = canvas(NAVY)
    grad_h(px, 0, 0, W, H, NAVY, (10,15,50))
    grad_h(px, 0, 0, W, 8, BLUE, PURPLE)
    grad_h(px, 0, H-8, W, H, BLUE, PURPLE)
    grad_h(px, 0, 0, 8, H, BLUE, PURPLE)
    grad_h(px, W-8, 0, W, H, PURPLE, BLUE)
    cx, cy = W//2, H//2-40
    circle(px, cx, cy, 100, (18,26,58))
    circle(px, cx, cy, 96, NAVY)
    bolt(px, cx-78, cy-120, 1.55)
    grad_h(px, cx-240, cy+75, cx+240, cy+120, BLUE, PURPLE)
    rect(px, cx-200, cy+130, 400, 4, (40,60,120))
    rect(px, cx-180, cy+144, 360, 30, (30,50,100))
    rect(px, cx-150, cy+184, 300, 26, (20,35,80))
    rect(px, cx-130, cy+222, 260, 26, (20,35,80))
    rect(px, cx-120, cy+280, 240, 52, BLUE)
    return px

slides = [
    (slide_01, 7),
    (slide_02, 7),
    (slide_03, 6),
    (slide_04, 6),
    (slide_05, 4),
]

print("Generating slides...")
slide_files = []
for i, (fn, dur) in enumerate(slides):
    print(f"  Slide {i+1}/5...", end=" ", flush=True)
    img_path = TMP / f"slide_{i:02d}.png"
    write_png(img_path, fn())
    slide_files.append((img_path, dur))
    print("done")

# ── Build ffmpeg concat with xfade ────────────────────────────────────────
print("\nBuilding video with ffmpeg...")

# Write concat input list
input_args = []
for img_path, dur in slide_files:
    input_args += ["-loop", "1", "-t", str(dur+1), "-i", str(img_path)]

n = len(slide_files)
fc_parts = []
for i in range(n):
    fc_parts.append(f"[{i}:v]scale={W}:{H},setsar=1,fps=25[v{i}]")

# Chain xfades
prev = "v0"
offset = 0
for i in range(1, n):
    offset += slide_files[i-1][1] - 1
    out = f"x{i}"
    fc_parts.append(f"[{prev}][v{i}]xfade=transition=fade:duration=0.8:offset={offset}[{out}]")
    prev = out
fc_parts.append(f"[{prev}]null[vout]")

fc = ";".join(fc_parts)

cmd = (
    ["ffmpeg", "-y"] +
    input_args +
    ["-filter_complex", fc,
     "-map", "[vout]",
     "-c:v", "libx264", "-preset", "fast", "-crf", "23",
     "-pix_fmt", "yuv420p", "-movflags", "+faststart",
     str(OUT)]
)

result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print("ffmpeg error:", result.stderr[-800:])
    raise SystemExit(1)

import shutil
shutil.rmtree(TMP, ignore_errors=True)

mb = OUT.stat().st_size / 1e6
print(f"\n✅ Video ready! {mb:.1f} MB | 30 seconds")
print(f"Windows path:")
print(f"  C:\\Users\\YourName\\Desktop\\catalyst-edge\\assets\\business_verification.mp4")
