#!/usr/bin/env python3
"""Generate a professional 1080x1080 Instagram card using Pillow."""

from __future__ import annotations
import csv, datetime as dt, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT      = Path(__file__).parent
SOCIAL    = Path(__file__).parent / "social"
WIN_SOC   = Path(__file__).parent / "social"
FONT_B    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R    = "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf"
W, H      = 1080, 1080

NAVY=(10,15,30);NAVY2=(15,22,50);NAVY3=(20,30,65);DARK=(8,12,25)
BLUE=(59,130,246);PURPLE=(139,92,246);GREEN=(16,185,129)
RED=(239,68,68);AMBER=(245,158,11);WHITE=(255,255,255)
GRAY=(148,163,184);LGRAY=(71,85,105)
CAT_COL={"GAPPER":RED,"VALUE":BLUE,"MOAT":PURPLE}

def fnt(sz,bold=False):
    try: return ImageFont.truetype(FONT_B if bold else FONT_R,sz)
    except: return ImageFont.load_default()

def rr(draw,xy,r,fill,outline=None,ow=2):
    draw.rounded_rectangle(xy,radius=r,fill=fill,outline=outline,width=ow)

def grad(img,x1,y1,x2,y2,c1,c2):
    d=ImageDraw.Draw(img); w=max(1,x2-x1)
    for i in range(w):
        t=i/w; c=tuple(int(c1[j]+(c2[j]-c1[j])*t) for j in range(3))
        d.line([(x1+i,y1),(x1+i,y2)],fill=c)

def fp(v):
    try: return f"${float(v):,.2f}"
    except: return "N/A"
def fm(v):
    try:
        n=float(v)
        return f"${n/1e9:.1f}B" if n>=1e9 else f"${n/1e6:.0f}M" if n>=1e6 else "N/A"
    except: return "N/A"
def fv(v):
    try:
        n=float(v)
        return f"{n/1e6:.1f}M" if n>=1e6 else f"{n/1e3:.0f}K" if n>=1e3 else str(int(n))
    except: return "N/A"

def cat(t,g,v,m):
    if t in {r.get("ticker","") for r in g}: return "GAPPER"
    if t in {r.get("ticker","") for r in v}: return "VALUE"
    if t in {r.get("ticker","") for r in m}: return "MOAT"
    return "CATALYST"

def narrative(row):
    tags=row.get("tags","").lower()
    T={"+fda approval":"FDA Approval","+definitive agreement":"M&A Agreement",
       "+contract award":"Contract Win","+raises guidance":"Raised Guidance",
       "+record revenue":"Record Revenue","+earnings beat":"Earnings Beat",
       "+share repurchase":"Share Buyback","+buyback":"Share Buyback",
       "+insider_buy_p":"CEO/Director Buying","+dividend":"Dividend Signal",
       "+strategic review":"Strategic Review"}
    for k,v in T.items():
        if k in tags: return v
    fm2={"8-K":"Material 8-K Event","4":"Form 4 Insider","6-K":"Foreign Issuer 6-K","SC 13D":"Activist 13D"}
    return fm2.get(row.get("form","8-K"),row.get("form","8-K")+" Filing")

def company(ticker):
    try:
        d=json.loads((ROOT/".sec_company_names.json").read_text())
        n=d.get(ticker.upper(),"")
        return n[:26]+"..." if len(n)>26 else n
    except: return ""

def load_csv(fname):
    p=ROOT/fname
    if not p.exists(): return []
    rows=[]
    with p.open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t=r.get("ticker","").strip()
            if t and "-" not in t and len(t)<=5: rows.append(r)
    return rows

def build(picks,g,v,m,date_str):
    img=Image.new("RGB",(W,H),NAVY)
    d=ImageDraw.Draw(img)

    # Grid
    for x in range(0,W,60): d.line([(x,0),(x,H)],fill=(14,20,42),width=1)
    for y in range(0,H,60): d.line([(0,y),(W,y)],fill=(14,20,42),width=1)

    # Header gradient
    grad(img,0,0,W,116,BLUE,PURPLE)
    d.rectangle([0,110,W,116],fill=NAVY)

    # Lightning bolt
    bolt=[(54,16),(32,62),(50,62),(40,96),(74,46),(54,46),(66,16)]
    d.polygon(bolt,fill=WHITE)

    # Brand text
    d.text((92,18),"CATALYST EDGE",font=fnt(34,True),fill=WHITE)
    d.text((92,60),"Daily SEC Catalyst Intelligence",font=fnt(19),fill=(200,220,255))
    d.text((W-180,40),date_str,font=fnt(17),fill=(180,200,240))

    # Top pick card
    top=picks[0] if picks else {}
    tk=top.get("ticker","—")
    cc=CAT_COL.get(cat(tk,g,v,m),BLUE)
    co=company(tk)
    sc=top.get("value_score") or top.get("gapper_score") or top.get("moat_score") or "0"

    rr(d,[30,128,W-30,470],16,NAVY2,outline=cc,ow=2)

    # Category + TOP PICK badges
    ct=cat(tk,g,v,m); bw=len(ct)*14+24
    rr(d,[52,148,52+bw,190],8,cc)
    d.text((62,154),ct,font=fnt(24,True),fill=WHITE)
    d.text((W-190,154),"TOP PICK",font=fnt(18,True),fill=cc)

    # Ticker
    d.text((52,200),f"${tk}",font=fnt(76,True),fill=WHITE)
    if co: d.text((52,288),co,font=fnt(22),fill=GRAY)

    # Divider
    grad(img,52,316,W-52,318,cc,PURPLE)

    # Metrics
    mets=[("PRICE",fp(top.get("price",""))),
          ("MKT CAP",fm(top.get("market_cap",""))),
          ("AVG VOL",fv(top.get("avg_vol_3m","")))]
    mx=52; mw=(W-104)//3
    for lb,val in mets:
        d.text((mx+10,330),lb,font=fnt(16),fill=GRAY)
        d.text((mx+10,355),val,font=fnt(27,True),fill=WHITE)
        mx+=mw
        if mx<W-52: d.line([(mx-1,326),(mx-1,398)],fill=NAVY3,width=1)

    # Score bar
    d.text((52,408),"CATALYST SCORE",font=fnt(16),fill=GRAY)
    try: pct=min(1.0,float(sc)/25.0)
    except: pct=0.4
    rr(d,[52,428,W-52,450],7,NAVY3)
    if pct>0: grad(img,52,428,int(52+(W-104)*pct),450,cc,PURPLE)
    d.text((W-96,408),str(sc),font=fnt(19,True),fill=cc)

    # Catalyst signal
    rr(d,[30,462,W-30,534],10,NAVY3)
    d.text((50,474),"⚡  CATALYST SIGNAL",font=fnt(17,True),fill=cc)
    d.text((50,502),narrative(top),font=fnt(21),fill=WHITE)

    # Watchlist
    d.text((52,548),"TODAY'S WATCHLIST",font=fnt(18,True),fill=GRAY)
    grad(img,52,570,W//2,572,BLUE,PURPLE)

    ry=580
    for i,pk in enumerate(picks[1:5]):
        t2=pk.get("ticker","—"); cc2=CAT_COL.get(cat(t2,g,v,m),BLUE)
        bg=NAVY2 if i%2==0 else NAVY3
        rr(d,[30,ry,W-30,ry+72],8,bg)
        d.line([(30,ry),(34,ry+72)],fill=cc2,width=4)
        rr(d,[46,ry+18,82,ry+54],16,cc2)
        d.text((54,ry+20),str(i+2),font=fnt(20,True),fill=WHITE)
        d.text((94,ry+10),f"${t2}",font=fnt(27,True),fill=WHITE)
        co2=company(t2)
        if co2: d.text((94,ry+42),co2[:22],font=fnt(15),fill=GRAY)
        d.text((W-200,ry+20),fp(pk.get("price","")),font=fnt(22,True),fill=WHITE)
        nv=narrative(pk); nvw=len(nv)*9+20
        rr(d,[W-nvw-44,ry+42,W-44,ry+66],6,cc2)
        d.text((W-nvw-36,ry+44),nv[:18],font=fnt(14,True),fill=WHITE)
        ry+=76

    # Footer
    grad(img,0,H-66,W,H,BLUE,PURPLE)
    d.rectangle([0,H-64,W,H],fill=DARK)
    d.text((52,H-50),"catalystedge.agency",font=fnt(21,True),fill=BLUE)
    d.text((W-270,H-50),"Not investment advice",font=fnt(17),fill=LGRAY)
    grad(img,0,0,W,4,BLUE,PURPLE)

    return img

def main():
    today=dt.date.today()
    date_str=today.strftime("%b %d, %Y").upper()
    g=load_csv("sec_clean_gappers.csv")
    v=load_csv("sec_clean_value.csv")
    m=load_csv("sec_clean_moat_core.csv")

    # Build lookup for category data
    cat_data = {}
    for row in g+v+m:
        t=row.get("ticker","")
        if t and "-" not in t: cat_data[t]=row

    # Use combined_priority for pick ORDER (quality-scored tickers first)
    # Fall back to clean CSVs for price/mcap data
    picks=[]; seen=set()
    for row in load_csv("combined_priority.csv"):
        t=row.get("ticker","")
        if not t or "-" in t or len(t)>5: continue
        # Merge: use cat_data row if available (has price), else use combined row
        r = cat_data.get(t, row)
        # Skip tickers with no market data
        try:
            price = float(r.get("price","") or 0)
            if price <= 0: continue
        except: continue
        if t not in seen: picks.append(r); seen.add(t)
        if len(picks)>=5: break

    # Fallback to clean CSVs if combined has no priced tickers
    if len(picks)<5:
        for row in g+v+m:
            t=row.get("ticker","")
            try:
                if float(row.get("price","") or 0)<=0: continue
            except: continue
            if t and t not in seen: picks.append(row); seen.add(t)
            if len(picks)>=5: break
    if not picks: print("No picks."); return 1
    picks=picks[:5]
    print(f"Building card: {', '.join(p.get('ticker','') for p in picks)}")
    img=build(picks,g,v,m,date_str)
    SOCIAL.mkdir(parents=True,exist_ok=True)
    for out in [ROOT/"instagram_card.png", SOCIAL/f"instagram_{today.isoformat()}.png"]:
        img.save(out); print(f"  Saved: {out}")
    try: WIN_SOC.mkdir(parents=True,exist_ok=True); img.save(WIN_SOC/f"instagram_{today.isoformat()}.png")
    except: pass
    print("✅ Done!")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
# This line intentionally left blank — trigger re-read
