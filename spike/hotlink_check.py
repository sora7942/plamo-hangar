"""이미지 핫링크 검증.

spike/hotlink-test.html 을 만들고 `python -m http.server -d spike 8000` 으로 열어 브라우저가
다른 오리진(localhost)에서 이미지를 띄우는지 본다 (referrerpolicy="no-referrer" + 정책 없음 비교).

- 이미지는 저장하지 않는다. 브라우저가 화면에 띄우는 것만 확인한다.
- 이미지 요청도 1.3초 간격으로 하나씩 로드한다 (페이지 안의 스크립트가 순서대로 src를 설정).
- 서명(만료) URL은 방금 새로 받은 것(FRESH)과 이전에 받은 것(STALE)을 같이 넣어 만료 여부를 본다.
"""
from __future__ import annotations

import html as H
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

import common
from hobby import expires_of, epoch_of, parse_schedule, parse_detail

SPIKE = common.ROOT / "spike"
SHOTS = SPIKE / "screenshots" if common.ENV == "local" else common.OUT / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
PORT = 8000
GAP_MS = 1300
BASE = "https://bandai-hobby.net"


def fresh_signed(b: common.Browser) -> dict:
    """방금 받은 서명 URL (일정 썸네일 4 + 상세 갤러리 4). 이미 센 URL이라 상세 예산은 늘지 않는다."""
    out = {"schedule": [], "detail": []}
    d = b.goto("hobby", f"{BASE}/schedule/", use_cache=False)
    cards = parse_schedule(d["html"])["cards"]
    out["schedule"] = [c["thumb"] for c in cards if c["thumb"] and expires_of(c["thumb"])][:4]
    out["schedule_fetched_at"] = d["fetched_at"]
    d2 = b.goto("hobby", f"{BASE}/item/01_7249/", kind="detail", use_cache=False)
    p = parse_detail(d2["html"], d2["fetched_at"])
    out["detail"] = [u for u in p["gallery"] if expires_of(u)][:4]
    out["detail_fetched_at"] = d2["fetched_at"]
    return out


def collect_rows(b: common.Browser) -> list[dict]:
    imgs = json.loads((common.OUT / "hobby-images.json").read_text(encoding="utf-8"))
    hs = json.loads((common.OUT / "hobby-summary.json").read_text(encoding="utf-8"))
    det = {d["id"]: d for d in hs["details"] if d.get("gallery")}
    now = time.time()

    fresh = fresh_signed(b)
    rows = [
        {"key": "D", "title": "D. CloudFront 서명 URL — FRESH (방금 받음), no-referrer", "policy": "no-referrer",
         "urls": [(f"fresh-sched-{i+1}", u) for i, u in enumerate(fresh["schedule"])] +
                 [(f"fresh-gallery-{i+1}", u) for i, u in enumerate(fresh["detail"])]},
        {"key": "A", "title": "A. akamai 갤러리 (01_4257 HG 에어리얼) _1.._11, no-referrer", "policy": "no-referrer",
         "urls": [(f"ak_{u.rsplit('_', 1)[-1].split('.')[0]}", u) for u in imgs["akamai_gallery"].get("01_4257", [])]},
        {"key": "B", "title": "B. akamai 갤러리, 정책 없음(Referer=http://localhost:8000/ 전송)", "policy": "",
         "urls": [(f"ak-ref_{i+1}", u) for i, u in enumerate(imgs["akamai_gallery"].get("01_4257", [])[:3])]},
        {"key": "C", "title": "C. 호비사이트 정적 이미지 (01_4259 / 01_1547), no-referrer", "policy": "no-referrer",
         "urls": [(f"static-{i+1}", u) for i, u in enumerate(det.get("01_4259", {}).get("gallery", [])[:4])] +
                 [(f"static-old-{i+1}", u) for i, u in enumerate(det.get("01_1547", {}).get("gallery", [])[:1])]},
    ]
    # p-bandai.com 홈의 상품 이미지 (대안 A 소스의 이미지 호스트)
    c = common.cache_get("https://p-bandai.com/us/")
    glb = []
    if c:
        soup = BeautifulSoup(c["html"], "html.parser")
        for img in soup.select("a[href^='/us/item/'] img"):
            u = img.get("src") or img.get("data-src") or ""
            if u.startswith("http") and u not in glb:
                glb.append(u)
    rows.append({"key": "F", "title": "F. p-bandai.com(해외) 상품 이미지, no-referrer", "policy": "no-referrer",
                 "urls": [(f"pb-global-{i+1}", u) for i, u in enumerate(glb[:4])]})
    # G: 갤러리에서 박스아트 위치 확인용 — 안정 URL 상품(캐시된 상세)의 첫 장/마지막 장
    g_urls = []
    for iid in ("01_5373", "01_4259", "01_3024", "01_2909"):
        gal = det.get(iid, {}).get("gallery", [])
        if len(gal) >= 2:
            g_urls += [(f"{iid} 첫장/1of{len(gal)}", gal[0]), (f"{iid} 끝장/{len(gal)}of{len(gal)}", gal[-1])]
    rows.append({"key": "G", "title": "G. 갤러리 첫 장·마지막 장 (박스아트 위치 확인), no-referrer", "policy": "no-referrer", "urls": g_urls})
    # 오래된(만료된) 서명 URL: 받은 시각 + TTL이 지금보다 과거인 것
    stale = [i for i in imgs["cloudfront_signed"] if expires_of(i["url"]) < now - 30]
    seen, stale_urls = set(), []
    for i in stale:
        base = i["url"].split("?")[0]
        if base in seen:
            continue
        seen.add(base)
        stale_urls.append(i["url"])
    rows.append({"key": "E", "title": "E. CloudFront 서명 URL — STALE (이전에 받아 Expires 지남), no-referrer", "policy": "no-referrer",
                 "urls": [(f"stale-{i+1}", u) for i, u in enumerate(stale_urls[:6])]})
    return rows


def build_html(rows: list[dict]) -> str:
    parts = ["""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>hotlink test</title>
<style>body{font:13px system-ui;margin:16px}figure{display:inline-block;margin:4px;vertical-align:top;width:150px}
img{height:120px;max-width:150px;object-fit:contain;background:#eee;border:1px solid #ccc}
figcaption{font-size:11px;word-break:break-all}h2{font-size:14px;margin:18px 0 4px}.fail img{outline:2px solid red}</style></head><body>
<h1>hotlink test (spike)</h1>
<p>이미지는 저장하지 않고 원본 URL로만 링크합니다. 스크립트가 1.3초 간격으로 하나씩 로드합니다.</p>"""]
    for r in rows:
        parts.append(f"<h2>{H.escape(r['title'])}</h2><div>")
        for label, u in r["urls"]:
            rp = f' referrerpolicy="{r["policy"]}"' if r["policy"] else ""
            parts.append(f'<figure><img data-src="{H.escape(u, quote=True)}" data-label="{H.escape(label)}" data-row="{r["key"]}"{rp} alt="{H.escape(label)}">'
                         f'<figcaption>{H.escape(label)}</figcaption></figure>')
        parts.append("</div>")
    parts.append(f"""<script>
const imgs=[...document.querySelectorAll('img[data-src]')];window.__results=[];window.__done=false;
function next(i){{ if(i>=imgs.length){{ setTimeout(()=>{{window.__done=true}},1500); return; }}
  const im=imgs[i];
  const fin=()=>{{window.__results.push({{label:im.dataset.label,row:im.dataset.row,ok:im.complete&&im.naturalWidth>0,w:im.naturalWidth,h:im.naturalHeight}});
    if(!(im.complete&&im.naturalWidth>0)) im.closest('figure').classList.add('fail'); setTimeout(()=>next(i+1),{GAP_MS});}};
  im.addEventListener('load',fin,{{once:true}}); im.addEventListener('error',fin,{{once:true}}); im.src=im.dataset.src; }}
next(0);
</script></body></html>""")
    return "\n".join(parts)


def run(b: common.Browser) -> dict:
    rows = collect_rows(b)
    page_html = build_html(rows)
    (SPIKE / "hotlink-test.html").write_text(page_html, encoding="utf-8")
    n_img = sum(len(r["urls"]) for r in rows)
    print(f"[hotlink] {n_img} images, ~{n_img * GAP_MS / 1000:.0f}s")

    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "-d", str(SPIKE)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    res: dict = {"origin": f"http://localhost:{PORT}", "images": n_img, "rows": {}}
    try:
        bt = common.Browser("ja-JP", block_assets=False)
        net: dict[str, dict] = {}
        bt.page.on("response", lambda r: net.__setitem__(r.url, {"status": r.status}) if r.request.resource_type == "image" else None)
        bt.page.on("requestfailed", lambda r: net.__setitem__(r.url, {"failed": (r.failure or "")}) if r.resource_type == "image" else None)
        bt.page.goto(f"http://localhost:{PORT}/hotlink-test.html")
        bt.page.wait_for_function("window.__done === true", timeout=int(n_img * GAP_MS * 2 + 30000))
        results = bt.page.evaluate("window.__results")
        shot = SHOTS / "hotlink-local.png"
        bt.page.screenshot(path=str(shot), full_page=True)
        res["screenshot"] = str(shot.relative_to(common.ROOT))
        bt.close()
    finally:
        srv.terminate()
    url_by_label = {l: u for r in rows for l, u in r["urls"]}
    for r in rows:
        rr = [x for x in results if x["row"] == r["key"]]
        statuses = {}
        for x in rr:
            u = url_by_label[x["label"]]
            st = net.get(u, {})
            key = str(st.get("status") or st.get("failed") or "?")
            statuses[key] = statuses.get(key, 0) + 1
        res["rows"][r["key"]] = {"title": r["title"], "policy": r["policy"] or "(default)", "total": len(rr),
                                 "ok": sum(1 for x in rr if x["ok"]), "http_status": statuses,
                                 "hosts": sorted({urlparse(u).netloc for _, u in r["urls"]})}
    stale_urls = next((r["urls"] for r in rows if r["key"] == "E"), [])
    if stale_urls:
        import requests
        common._wait()
        try:
            r0 = requests.get(stale_urls[0][1], headers={"User-Agent": common.UA}, timeout=common.TIMEOUT_S, stream=True)
            head = next(r0.iter_content(200), b"")
            res["stale_probe"] = {"status": r0.status_code, "content_type": r0.headers.get("content-type"),
                                  "body_head": head.decode("utf-8", "replace")[:160]}
            r0.close()
            common.log_request("GET", stale_urls[0][1].split("?")[0], r0.status_code, "", 0, "img-stale-probe")
        except requests.RequestException as e:
            res["stale_probe"] = {"error": repr(e)}
    res["detail"] = results
    res["run_at"] = datetime.now(common.KST).isoformat(timespec="seconds")
    common.summary_write("hotlink-summary.json", res)
    return res


if __name__ == "__main__":
    b = common.Browser("ja-JP")
    try:
        out = run(b)
    finally:
        b.close(); common.shutdown()
    for k, v in out["rows"].items():
        print(k, f"{v['ok']}/{v['total']}", v["http_status"], v["hosts"])
