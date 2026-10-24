#!/usr/bin/env python3
"""求人の掲載日を更新し、エリア別ページに JobPosting を配る道具。

なぜ道具にするか
----------------
掲載日は放っておくと必ず古くなる。実測で `datePosted` が 112日前になっていた。
Google しごと検索は古い求人を落とすので、**作ったときは正しくても、置くだけで壊れる**型。
手で直すと次も忘れるので、1コマンドで直せるようにする。

エリア別ページも、手で4枚書くと本体とズレる。
**本体の index.html にある JobPosting を唯一の正本**として、そこから派生させる。

★対応エリア外のページ（千葉・埼玉）には配らない。
  実際には募集していないので、JobPosting を置くと実態と違う求人を出すことになる。
  このスクリプトは AREAS に書いた分だけを扱い、それ以外には触らない。

使い方:
  python tools/refresh_posting.py            # 中身を見るだけ（書き換えない）
  python tools/refresh_posting.py --write    # 実際に書き換える
"""
import argparse
import copy
import datetime
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://richend0913.github.io/recruit"
VALID_MONTHS = 6          # 掲載期限を今日から何か月先にするか

# 実際に募集しているエリアだけ。千葉・埼玉は対応エリア外なので入れない。
AREAS = {
    "area/tokyo.html": {
        "title": "業務委託 軽貨物配送ドライバー（東京・世田谷／大田）",
        "places": [("世田谷区", "東京都"), ("大田区", "東京都")],
    },
    "area/kanagawa.html": {
        "title": "業務委託 軽貨物配送ドライバー（神奈川・横浜／座間／相模原）",
        "places": [("横浜市", "神奈川県"), ("座間市", "神奈川県"), ("相模原市", "神奈川県")],
    },
}

LD_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)


def read(p):
    return io.open(os.path.join(ROOT, p), encoding="utf-8").read()


def write(p, s):
    io.open(os.path.join(ROOT, p), "w", encoding="utf-8", newline="\n").write(s)


def find_jobposting(html):
    """ページ内の JobPosting を (辞書, その<script>の全文) で返す。"""
    for m in LD_RE.finditer(html):
        try:
            d = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for o in (d if isinstance(d, list) else [d]):
            if isinstance(o, dict) and o.get("@type") == "JobPosting":
                return o, m.group(0), m.group(1)
    return None, None, None


def place(locality, region):
    return {"@type": "Place",
            "address": {"@type": "PostalAddress",
                        "addressLocality": locality,
                        "addressRegion": region,
                        "addressCountry": "JP"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="実際に書き換える")
    a = ap.parse_args()

    today = datetime.date.today()
    valid = today + datetime.timedelta(days=VALID_MONTHS * 30)

    idx = read("index.html")
    jp, block, inner = find_jobposting(idx)
    if not jp:
        print("index.html に JobPosting が無い。止める。")
        return 1

    old_posted = jp.get("datePosted")
    age = (today - datetime.date.fromisoformat(str(old_posted)[:10])).days
    print(f"本体の掲載日: {old_posted}（{age}日前）→ {today}")
    print(f"掲載期限:     {jp.get('validThrough')} → {valid}")

    # --- 本体の日付を更新
    new_jp = copy.deepcopy(jp)
    new_jp["datePosted"] = today.isoformat()
    new_jp["validThrough"] = valid.isoformat()
    new_idx = idx.replace(inner, json.dumps(new_jp, ensure_ascii=False, indent=2))
    if new_idx == idx:
        print("★本体を置き換えられなかった。中身を確認する。")
        return 1

    # --- エリア別ページへ配る
    plans = []
    for path, spec in AREAS.items():
        if not os.path.exists(os.path.join(ROOT, path)):
            print(f"  {path}: 無いので飛ばす")
            continue
        html = read(path)
        area_jp = copy.deepcopy(new_jp)
        area_jp["title"] = spec["title"]
        area_jp["jobLocation"] = [place(l, r) for l, r in spec["places"]]
        area_jp["url"] = f"{BASE}/{path}"
        ident = dict(area_jp.get("identifier") or {})
        ident["value"] = f"BB-DRIVER-{os.path.basename(path).split('.')[0].upper()}"
        area_jp["identifier"] = ident
        tag = ('<script type="application/ld+json">\n'
               + json.dumps(area_jp, ensure_ascii=False, indent=2) + "\n</script>")

        existing, blk, _ = find_jobposting(html)
        if existing:
            new_html = html.replace(blk, tag)
            how = "差し替え"
        else:
            if "</head>" not in html:
                print(f"  {path}: </head> が無いので飛ばす")
                continue
            new_html = html.replace("</head>", tag + "\n</head>", 1)
            how = "新規追加"
        plans.append((path, new_html, how, len(spec["places"])))
        print(f"  {path}: JobPosting を{how}（対象地域 {len(spec['places'])}件）")

    # --- sitemap の更新日
    sm_path, new_sm = "sitemap.xml", None
    if os.path.exists(os.path.join(ROOT, sm_path)):
        sm = read(sm_path)
        olds = sorted(set(re.findall(r"<lastmod>([^<]+)</lastmod>", sm)))
        new_sm = re.sub(r"<lastmod>[^<]+</lastmod>",
                        f"<lastmod>{today}</lastmod>", sm)
        print(f"sitemap.xml の更新日: {olds[:2]}… → {today}（{len(olds)}種類）")

    if not a.write:
        print("\n（--write を付けていないので、何も書き換えていない）")
        return 0

    write("index.html", new_idx)
    for path, html, _, _ in plans:
        write(path, html)
    if new_sm:
        write(sm_path, new_sm)
    print(f"\n書き換えた: index.html, {', '.join(p for p, _, _, _ in plans)}"
          + (", sitemap.xml" if new_sm else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
