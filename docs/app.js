/* 프라 격납고 — UI. 화면은 reference/artifact-v2.html 을 그대로 옮기고, 저장은 GitHub API(github.js), 순수 로직은 pure.js 를 쓴다. */
(function () {
'use strict';

var P = window.PlamoPure, GH = window.PlamoGitHub, C = window.PlamoCatalog, FD = window.PlamoFeed, AS = window.PlamoAssist;
var REPO = 'sora7942/plamo-hangar';
var TOKEN_KEY = 'plamo-token', UI_KEY = 'plamo-ui';
var XLSX_SRC = { url: 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js',
  integrity: 'sha512-r22gChDnGvBylk90+2e/ycr3RVrDi8DIOkIGNhJlKfuyQM4tIRAI062MaV8sfjQKYVGjOBaZBOA87z+IhZE9DA==' };
var PERM_MSG = '토큰에 이 저장소의 Contents: Read and write 권한이 있는지 확인해 주세요.';

var GRADES = P.GRADES, STATUSES = P.STATUSES, SCALES = P.SCALES, STLABEL = P.STLABEL, GAPS = P.GAPS;
var esc = P.esc, gk = P.gk, gname = P.gname, won = P.won, days = P.days, splitTags = P.splitTags, uid = P.uid;

var data = P.normalizeData({});
var loading = true, canWrite = false, store = null, memToken = '';
var photoUrls = {}; // 'photos/k/p.webp' → objectURL (이번 방문에서 올린 사진: Pages 반영 전에도 보이게)
var sel = null; // Set of ids while selecting
var busy = false;
var app = document.getElementById('app');

var SAMPLE = [
 {id:'s1',name:'건담 에어리얼',grade:'HG',scale:'1/144',series:'기동전사 건담 수성의 마녀',brand:'반다이',status:'built',date:'2025-11-02',shop:'예시 매장',price:17000,tags:[],startDate:'2025-11-10',doneDate:'2025-11-16'},
 {id:'s2',name:'RX-78-2 건담 Ver.3.0',grade:'MG',scale:'1/100',series:'기동전사 건담',brand:'반다이',status:'unbuilt',date:'2026-03-15',shop:'',price:0,tags:['재판']},
 {id:'s3',name:'뉴건담',grade:'RG',scale:'1/144',series:'역습의 샤아',brand:'반다이',status:'building',date:'2026-07-20',shop:'예시 매장',price:45000,tags:[],startDate:'2026-09-28'},
 {id:'s4',name:'스트라이크 프리덤 건담',grade:'PG',scale:'1/60',series:'기동전사 건담 SEED DESTINY',brand:'반다이',status:'unbuilt',date:'2026-09-01',shop:'예시 매장',price:290000,tags:['P-반다이']},
 {id:'s5',list:'wish',name:'건담 캘리번',grade:'HG',scale:'1/144',series:'기동전사 건담 수성의 마녀',brand:'반다이',price:22000,tags:[]}
].map(function (k) { k.sample = true; k.memo = ''; return P.normKit(k); });

var ui = { q: '', grade: 'all', status: 'all', sort: 'recent', tab: 'own', tag: 'all', gap: 'all' };
try { var saved = JSON.parse(localStorage.getItem(UI_KEY) || 'null'); if (saved) ui = Object.assign(ui, saved, { q: '' }); } catch (e) {}
function saveUI() { try { localStorage.setItem(UI_KEY, JSON.stringify({ grade: ui.grade, status: ui.status, sort: ui.sort, tab: ui.tab, tag: ui.tag, gap: ui.gap })); } catch (e) {} }

/* ---------- 토큰 (이 브라우저 localStorage에만. 화면·로그·URL에는 절대 안 내보낸다) ---------- */
function getToken() { if (memToken) return memToken; try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; } }
function storeToken(t) { try { localStorage.setItem(TOKEN_KEY, t); memToken = ''; return true; } catch (e) { memToken = t; return false; } }
function clearToken() { memToken = ''; try { localStorage.removeItem(TOKEN_KEY); } catch (e) {} }
function makeStore(token) { return GH.create({ fetch: function (u, i) { return window.fetch(u, i); }, token: token, repo: REPO }); }

function showPurchase() { return canWrite || !data.settings.hidePurchase; }
function isSample() { return !data.kits.length; }
function allKits() { return data.kits.length ? data.kits : SAMPLE; }
function tabKits() { return allKits().filter(function (k) { return k.list === ui.tab; }); }
function today() { return P.ymd(new Date()); }
function findKit(id) { return allKits().filter(function (k) { return k.id === id; })[0]; }
function photoSrc(path) { return P.isSafePhotoPath(path) ? (photoUrls[path] || path) : ''; }

/* ---------- 카탈로그 (보유·위시를 먼저 그리고, 필요할 때 뒤에서 읽는다) ---------- */
var cat = null, catState = 'idle', catPromise = null; // idle | loading | ready | error
function ensureCatalog() {
  if (catPromise) return catPromise;
  catState = 'loading';
  catPromise = C.load(function (u, i) { return window.fetch(u, i); }).then(function (c) { cat = c; catState = 'ready'; return c; },
    function () { catState = 'error'; catPromise = null; return null; });
  return catPromise;
}
function scaleChoices(cur) { var a = SCALES.slice(); if (cur && a.indexOf(cur) < 0) a.splice(a.length - 1, 0, cur); return a; } // 카탈로그의 1/72 등도 잃지 않게
// 재판 공백: 연결된 프라 + 카탈로그를 읽은 뒤에만 (표시 문구·정렬 키는 catalog.js gapInfo)
function gapOf(k) { var it = catItem(k); return it ? C.gapInfo(it, today(), cat.since) : null; }
function hasLinked() { return data.kits.some(function (k) { return k.catalogId; }); }
function official(k) { return cat ? C.officialImages(cat, k, data.settings) : []; }
function catItem(k) { return cat && k && k.catalogId ? (cat.byId[k.catalogId] || null) : null; }
// 사진 항목 → 이미지 주소. 공식 사진의 카드·썸네일은 작은 이미지(/m/)를 먼저 쓰고, 안 뜨면 원본으로 (error 위임 핸들러의 data-alt)
function imgUrl(p, thumb) { return p.kind === 'off' ? (thumb ? C.thumbUrl(p.src) : p.src) : photoSrc(thumb ? p.thumb : p.src); }
function imgAlt(p, thumb) { return p.kind === 'off' && thumb && C.thumbUrl(p.src) !== p.src ? ' data-alt="' + esc(p.src) + '"' : ''; }
function creditHTML(k, shown) {
  var ci = catItem(k), u = ci && C.pageUrl(ci);
  return '<p class="hint credit" id="d-credit"' + (shown ? '' : ' hidden') + '>사진: BANDAI SPIRITS' + (u ? ' · <a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">원본 페이지</a>' : '') + '</p>';
}

/* ---------- 데이터 읽기 ---------- */
function loadVisitor() {
  return window.fetch('data/collection.json?t=' + Date.now(), { cache: 'no-store' }).then(function (r) {
    if (!r.ok) throw new Error('http');
    return r.text();
  }).then(function (t) { data = P.parseData(t); }).catch(function () { data = P.normalizeData({}); });
}
// 소유자 연결. permissions.push는 계정 권한일 수 있어 잠정 판정 — 실제 쓰기 권한은 저장할 때 확인된다
function connectOwner(token) {
  var s = makeStore(token);
  return s.connect().then(function (info) {
    if (!info.push) return { ok: false, reason: 'nopush' };
    return s.read().then(function (r) { data = P.parseData(r.text); store = s; canWrite = true; return { ok: true }; });
  }).catch(function (e) { return { ok: false, reason: (e && e.kind) || 'other' }; });
}
function connectFailMsg(reason) {
  return { nopush: '이 계정에는 이 저장소에 쓸 권한이 없어요. 보기 전용으로 열어요.', auth: '토큰이 만료됐거나 올바르지 않아요.', perm: PERM_MSG,
    ratelimit: 'GitHub 요청 한도에 걸렸어요. 잠시 후 다시 해 주세요.', network: '네트워크에 연결되지 않아 소유자 확인을 못 했어요.' }[reason] || '소유자 확인에 실패했어요.';
}

/* ---------- UI helpers ---------- */
var toastTimer;
function toast(msg) {
  var t = document.getElementById('toast');
  if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
  t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.hidden = true; }, 5000);
}
function setSaving(on, sub) {
  var s = document.getElementById('saving');
  if (on && !s) { s = document.createElement('div'); s.id = 'saving'; s.className = 'saving'; s.setAttribute('role', 'status'); document.body.appendChild(s); }
  if (s) { s.hidden = !on; if (on) s.innerHTML = '저장 중…' + (sub ? '<small>' + esc(sub) + '</small>' : ''); }
}
function opt(v, l, cur) { return '<option value="' + esc(v) + '"' + (v === cur ? ' selected' : '') + '>' + esc(l) + '</option>'; }

// 폼 위에 겹치는 알림 대화상자. 버튼 value를 resolve (Esc/바깥 = null)
var alertResolve = null, alertFocus = null;
function openAlert(title, msg, btns) {
  return new Promise(function (res) {
    closeAlert(null);
    alertResolve = res; alertFocus = document.activeElement;
    var o = document.createElement('div'); o.className = 'overlay'; o.id = 'alert';
    o.innerHTML = '<div class="panel small" role="alertdialog" aria-modal="true" aria-labelledby="a-title" aria-describedby="a-msg"><div class="panel-head"><h2 id="a-title">' + esc(title) + '</h2></div>' +
      '<div class="panel-body"><p id="a-msg">' + esc(msg) + '</p></div><div class="panel-foot"><div class="r">' +
      btns.map(function (b, i) { return '<button class="btn' + (b.primary ? ' primary' : '') + '" data-i="' + i + '">' + esc(b.label) + '</button>'; }).join('') + '</div></div></div>';
    o.addEventListener('click', function (e) { var b = e.target.closest('[data-i]'); if (b) closeAlert(btns[+b.dataset.i].value); });
    document.body.appendChild(o);
    var f = o.querySelector('.btn.primary') || o.querySelector('.btn'); if (f) f.focus();
  });
}
function closeAlert(v) {
  var a = document.getElementById('alert'); if (a) a.remove();
  var r = alertResolve; alertResolve = null;
  if (alertFocus && alertFocus.focus && document.contains(alertFocus)) alertFocus.focus();
  if (r) r(v === undefined ? null : v);
}

/* ---------- 사진: 긴 변 1600px WebP(0.82) + 480px 썸네일 ---------- */
function shrinkTo(bmp, max, q) {
  return new Promise(function (res, rej) {
    var w = bmp.width, h = bmp.height, s = Math.min(1, max / Math.max(w, h));
    var c = document.createElement('canvas'); c.width = Math.max(1, Math.round(w * s)); c.height = Math.max(1, Math.round(h * s));
    var ctx = c.getContext('2d'); ctx.imageSmoothingQuality = 'high'; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height); ctx.drawImage(bmp, 0, 0, c.width, c.height);
    c.toBlob(function (b) { if (b && b.type === 'image/webp') res(b); else rej(new Error('webp')); }, 'image/webp', q);
  });
}
function toWebp(file) {
  return createImageBitmap(file).then(function (bmp) {
    return shrinkTo(bmp, 1600, 0.82).then(function (full) {
      return shrinkTo(bmp, 480, 0.78).then(function (thumb) { if (bmp.close) bmp.close(); return { full: full, thumb: thumb }; });
    });
  });
}
// 방금 만든 사진 파일을 이번 방문에서 바로 보이게 objectURL로 등록하고 경로를 돌려준다
function registerPhoto(kitId, w) {
  var pid = P.makeId('p'), paths = P.photoPaths(kitId, pid);
  photoUrls[paths.src] = URL.createObjectURL(w.full); photoUrls[paths.thumb] = URL.createObjectURL(w.thumb);
  return { id: pid, src: paths.src, thumb: paths.thumb };
}
function dropPhotoUrls(p) {
  [p.src, p.thumb].forEach(function (x) { if (photoUrls[x]) { URL.revokeObjectURL(photoUrls[x]); delete photoUrls[x]; } });
}

// 이미지가 안 뜨면(저장 직후 Pages 반영 전 등) 자리표시로. 인라인 onerror는 CSP가 막으므로 위임
document.addEventListener('error', function (e) {
  var t = e.target;
  if (!t || t.tagName !== 'IMG' || !t.dataset || t.dataset.g == null) return;
  if (t.dataset.alt) { var alt = t.dataset.alt; delete t.dataset.alt; t.src = alt; return; }
  if (t.dataset.g === '') { t.hidden = true; return; }
  var d = document.createElement('div'); d.className = 'ghost'; d.textContent = t.dataset.g;
  if (t.dataset.note) { var p = t.parentNode; t.replaceWith(d); var n = document.createElement('p'); n.className = 'hint'; n.textContent = '사진을 불러오지 못했어요. 방금 저장했다면 사이트 반영(1~2분) 전일 수 있어요.'; if (p && p.parentNode) p.parentNode.insertBefore(n, p.nextSibling); }
  else t.replaceWith(d);
}, true);

/* ---------- 저장: 1회 = 커밋 1개 ---------- */
// mutate(next): 최신 데이터 사본에 변경 적용. kind/info: 커밋 메시지. o.files: {저장소경로: Blob}(이번에 올릴 사진), o.okMsg
function commit(mutate, kind, info, o) {
  o = o || {};
  if (busy) return Promise.resolve(false);
  if (!canWrite || !store) { toast('이 화면에서는 저장할 수 없어요.'); return Promise.resolve(false); }
  var blobs = o.files || {}, cur;
  function build(base) {
    var next = P.normalizeData(P.clone(base)); mutate(next);
    var pf = P.planPhotoFiles(base.kits, next.kits);
    return { next: next, pf: pf, text: P.serialize(next), noop: P.serialize(next) === P.serialize(base) && !pf.add.length && !pf.remove.length,
      message: P.commitMessage(kind, Object.assign({}, info, { photosAdded: pf.addedPhotos, photosRemoved: pf.removedPhotos })) };
  }
  function toPlan(b) {
    var paths = b.pf.add.filter(function (p) { return blobs[p]; });
    return Promise.all(paths.map(function (p) { return blobs[p].arrayBuffer().then(function (buf) { return { path: p, bytes: new Uint8Array(buf) }; }); })).then(function (files) {
      return { message: b.message, collectionText: b.text, files: files, deletes: b.pf.remove, onProgress: progress, onConflict: onConflict };
    });
  }
  function progress(done, total) { if (total > 1) setSaving(true, '사진 올리는 중 (' + done + '/' + total + ')'); }
  function onConflict(latest) {
    try { data = P.parseData(latest.text); } catch (e) { /* 읽을 수 없으면 현재 화면 유지 */ }
    renderAll();
    return openAlert('먼저 저장된 변경이 있어요', '다른 곳에서 먼저 저장된 변경이 있어서 최신 내용을 불러왔어요. 방금 한 작업을 최신 내용 위에 다시 적용할까요?',
      [{ label: '취소', value: false }, { label: '다시 적용', value: true, primary: true }]).then(function (yes) {
      if (!yes) return null;
      cur = build(data);
      if (cur.noop) { toast('이미 같은 내용이 저장돼 있어요.'); return null; }
      return toPlan(cur);
    });
  }
  cur = build(data);
  if (cur.noop) { toast('바뀐 내용이 없어요.'); return Promise.resolve(false); }
  busy = true; setSaving(true);
  return toPlan(cur).then(function (plan) { return store.commit(plan); }).then(function (res) {
    busy = false; setSaving(false);
    if (res.cancelled) return false;
    data = cur.next; sel = null; closeModal(); renderAll();
    toast((o.okMsg || '저장했어요.') + ' 사이트 반영까지 1~2분 걸려요.');
    return true;
  }).catch(function (err) { busy = false; setSaving(false); showSaveError(err); return false; });
}
function showSaveError(err) {
  var kind = err && err.kind;
  var toSettings = [{ label: '닫기', value: false }, { label: '설정 열기', value: true, primary: true }];
  var open = function (v) { if (v) { closeModal(); openSettings(); } };
  if (kind === 'perm') openAlert('저장하지 못했어요', PERM_MSG, toSettings).then(open);
  else if (kind === 'auth') openAlert('저장하지 못했어요', '토큰이 만료됐거나 올바르지 않아요. 설정에서 다시 연결해 주세요.', toSettings).then(open);
  else if (kind === 'ratelimit') toast('GitHub 요청 한도에 걸렸어요. 잠시 후 다시 저장해 주세요.');
  else if (kind === 'retry-exhausted') toast('저장 경쟁이 계속돼요. 잠시 후 다시 저장해 주세요.');
  else if (kind === 'conflict') toast('다른 곳에서 계속 바뀌고 있어요. 새로고침한 뒤 다시 시도해 주세요.');
  else if (kind === 'network') toast('네트워크에 연결되지 않아 저장하지 못했어요.');
  else toast('저장하지 못했어요. 잠시 후 다시 시도해 주세요.');
}

/* ---------- render ---------- */
function sortOptions() {
  var o = ui.tab === 'own' ? [['recent','최근 구매순'],['done','최근 완성순'],['name','이름순'],['grade','등급순']] : [['recent','최근 추가순'],['name','이름순'],['grade','등급순']];
  if (hasLinked()) o.push(['gap', '재판 공백 긴 순']);
  if (showPurchase()) o.push(['price', '가격 높은순']);
  if (!o.some(function (x) { return x[0] === ui.sort; })) ui.sort = 'recent';
  return o;
}
function renderAll() {
  var name = data.settings.name || '프라 격납고';
  if (loading) { app.innerHTML = '<div class="wrap"><p class="eyebrow">GUNPLA INVENTORY</p><h1>' + esc(name) + '</h1><p class="count-line">목록을 불러오는 중이에요.</p></div>'; return; }
  document.title = name;
  var all = allKits(), nOwn = all.filter(function (k) { return k.list === 'own'; }).length, nWish = all.length - nOwn;
  if (!canWrite) ui.gap = 'all';
  app.innerHTML = '<div class="wrap' + (sel && ui.tab !== 'feed' ? ' has-selbar' : '') + '">' +
   '<header class="top"><div><p class="eyebrow">GUNPLA INVENTORY</p><h1>' + esc(name) + '</h1></div>' +
   (canWrite ? '<div class="actions"><button class="btn primary" data-act="add">+ 추가</button>' +
     (isSample() || ui.tab === 'feed' ? '' : '<button class="btn" data-act="select">' + (sel ? '선택 끝내기' : '여러 개 선택') + '</button>') +
     '<button class="btn" data-act="import">가져오기</button><button class="btn" data-act="export">엑셀 백업</button><button class="btn" data-act="settings">설정</button></div>' : '') +
   '</header>' +
   '<nav class="tabs" role="tablist" aria-label="목록"><button class="tab" role="tab" data-tab="own" aria-selected="' + (ui.tab === 'own') + '">보유<span class="n">' + nOwn + '</span></button>' +
     '<button class="tab" role="tab" data-tab="wish" aria-selected="' + (ui.tab === 'wish') + '">위시리스트<span class="n">' + nWish + '</span></button>' +
     '<button class="tab" role="tab" data-tab="feed" aria-selected="' + (ui.tab === 'feed') + '">신제품·입고</button></nav>' +
   (ui.tab === 'feed' ? '<div id="feed-root"></div>' : '<section class="stats" id="stats" aria-label="현황"></section>' +
   '<section class="controls" aria-label="필터">' +
     '<div class="ctl-row"><input class="search" id="q" type="search" placeholder="이름·시리즈·태그·메모로 찾기" value="' + esc(ui.q) + '" aria-label="검색">' +
     (ui.tab === 'own' ? '<select class="sel" id="f-status" aria-label="상태">' + opt('all', '모든 상태', ui.status) + STATUSES.map(function (s) { return opt(s.k, s.l, ui.status); }).join('') + '</select>' : '') +
     (canWrite ? '<select class="sel" id="f-gap" aria-label="빈 칸 모아보기"></select>' : '') +
     '<select class="sel" id="f-sort" aria-label="정렬">' + sortOptions().map(function (o) { return opt(o[0], o[1], ui.sort); }).join('') + '</select></div>' +
     '<div class="chips" id="chips"></div><div class="chips" id="tagchips"></div>' +
   '</section>' +
   (isSample() ? '<div class="banner">아래는 예시 데이터예요. ' + (canWrite ? '첫 프라를 추가하거나 엑셀 목록을 가져오면 사라져요.' : '소유자가 프라를 추가하면 사라져요.') + '</div>' : '') +
   '<p class="count-line" id="countline"></p><div class="gap-tools" id="gap-tools"></div>' +
   '<div class="grid" id="grid"></div>') +
  '</div>' + (canWrite ? '' : '<footer class="foot"><button class="linkbtn" data-act="settings">소유자 설정</button></footer>');
  if (ui.tab === 'feed') { bindShell(); feedView.mount(document.getElementById('feed-root')); return; }
  bindShell(); renderStats(); renderList(); renderSelbar();
  // 연결된 프라가 있으면 첫 화면을 그린 뒤에 카탈로그를 받아 공식 사진을 붙인다
  if (catState === 'idle' && !isSample() && hasLinked()) ensureCatalog().then(function () { if (!loading && document.getElementById('grid')) renderList(); });
}

function renderStats() {
  var list = tabKits(), n = list.length, el = document.getElementById('stats');
  if (ui.tab === 'wish') {
    var sum = 0; list.forEach(function (k) { sum += Number(k.price) || 0; });
    el.innerHTML = '<div class="tiles"><div class="stat"><span class="k">사고 싶은 프라</span><span class="v">' + n + '<small>개</small></span></div>' +
     (showPurchase() ? '<div class="stat"><span class="k">예상 합계</span><span class="v mono" style="font-size:22px">' + won(sum) + '</span></div>' : '') + '</div>';
  } else {
    var c = { unbuilt: 0, building: 0, built: 0, custom: 0 }, spent = 0, yr = String(new Date().getFullYear()), doneYr = 0, dur = [];
    list.forEach(function (k) { c[k.status]++; spent += Number(k.price) || 0;
      if (k.doneDate && k.doneDate.slice(0, 4) === yr) doneYr++; var d = days(k.startDate, k.doneDate); if (d) dur.push(d); });
    var avg = dur.length ? Math.round(dur.reduce(function (a, b) { return a + b; }, 0) / dur.length) : null;
    var pct = function (x) { return n ? (x / n * 100) : 0; };
    var colors = { unbuilt: 'var(--st-unbuilt)', building: 'var(--st-building)', built: 'var(--st-built)', custom: 'var(--st-custom)' };
    el.innerHTML = '<div class="tiles">' +
     '<div class="stat"><span class="k">총 보유</span><span class="v">' + n + '<small>개</small></span></div>' +
     '<div class="stat hl"><span class="k">적프라 (미개봉)</span><span class="v">' + c.unbuilt + '<small>개</small></span></div>' +
     '<div class="stat"><span class="k">조립 중</span><span class="v">' + c.building + '<small>개</small></span></div>' +
     '<div class="stat"><span class="k">완성 · 도색</span><span class="v">' + (c.built + c.custom) + '<small>개</small></span></div>' +
     '<div class="stat"><span class="k">' + yr + '년 완성' + (avg ? ' · 평균 ' + avg + '일' : '') + '</span><span class="v">' + doneYr + '<small>개</small></span></div>' +
     (showPurchase() ? '<div class="stat"><span class="k">총 구매액</span><span class="v mono" style="font-size:22px">' + won(spent) + '</span></div>' : '') + '</div>' +
     '<div class="bar"><div class="bar-track" role="img" aria-label="상태 비율">' + STATUSES.map(function (s) { return '<span style="width:' + pct(c[s.k]) + '%;background:' + colors[s.k] + '"></span>'; }).join('') + '</div>' +
     '<div class="legend">' + STATUSES.map(function (s) { return '<span><i style="background:' + colors[s.k] + '"></i>' + s.l + ' <span class="mono">' + c[s.k] + '</span></span>'; }).join('') + '</div></div>';
  }
  var gc = {}, tc = {}; list.forEach(function (k) { var g = gname(k.grade); gc[g] = (gc[g] || 0) + 1; k.tags.forEach(function (t) { tc[t] = (tc[t] || 0) + 1; }); });
  if (ui.grade !== 'all' && !gc[ui.grade]) ui.grade = 'all';
  if (ui.tag !== 'all' && !tc[ui.tag]) ui.tag = 'all';
  document.getElementById('chips').innerHTML = '<button class="chip" data-grade="all" aria-pressed="' + (ui.grade === 'all') + '">전체<span class="n">' + n + '</span></button>' +
   GRADES.filter(function (g) { return gc[g]; }).map(function (g) { return '<button class="chip" data-grade="' + esc(g) + '" aria-pressed="' + (ui.grade === g) + '">' + esc(g) + '<span class="n">' + gc[g] + '</span></button>'; }).join('');
  var tags = Object.keys(tc).sort(function (a, b) { return tc[b] - tc[a] || a.localeCompare(b, 'ko'); });
  document.getElementById('tagchips').innerHTML = tags.length ? '<span class="chip-label">태그</span><button class="chip tag" data-tag="all" aria-pressed="' + (ui.tag === 'all') + '">전체</button>' +
   tags.map(function (t) { return '<button class="chip tag" data-tag="' + esc(t) + '" aria-pressed="' + (ui.tag === t) + '">#' + esc(t) + '<span class="n">' + tc[t] + '</span></button>'; }).join('') : '';
  var gapSel = document.getElementById('f-gap');
  if (gapSel) {
    if (ui.gap !== 'all' && !GAPS[ui.gap]) ui.gap = 'all';
    gapSel.innerHTML = opt('all', '빈 칸 모아보기', ui.gap) + Object.keys(GAPS).filter(function (g) { return ui.tab === 'own' || g === 'photo' || g === 'series' || g === 'unlinked'; }).map(function (g) {
      return opt(g, GAPS[g].l + ' (' + list.filter(GAPS[g].t).length + ')', ui.gap); }).join('');
    if (ui.tab === 'wish' && (ui.gap === 'purchase' || ui.gap === 'done')) { ui.gap = 'all'; gapSel.value = 'all'; }
  }
}

function gapLine(k) { var g = gapOf(k); return g ? '<span class="gapline' + (g.recent ? ' recent' : '') + '">' + esc(g.short) + '</span>' : ''; }
function cardHTML(k) {
  var g = gname(k.grade), on = sel && sel.has(k.id), cover = P.photoOrder(k, official(k)).cover;
  return '<button class="card' + (on ? ' selected' : '') + '" data-id="' + esc(k.id) + '" aria-label="' + esc(k.name) + (sel ? (on ? ' 선택됨' : ' 선택하기') : ' 자세히 보기') + '"' + (sel ? ' aria-pressed="' + !!on + '"' : '') + '>' +
   '<div class="ph">' + (cover ? '<img src="' + esc(imgUrl(cover, true)) + '"' + imgAlt(cover, true) + ' alt="" loading="lazy" referrerpolicy="no-referrer" data-g="' + esc(g) + '">' : '<div class="ghost">' + esc(g) + '</div>') +
   '<span class="grade g-' + gk(k.grade) + '">' + esc(P.glabel(k.grade)) + '</span>' + (k.sample ? '<span class="sample-tag">예시</span>' : '') +
   (sel ? '<span class="selbox" aria-hidden="true">' + (on ? '✓' : '') + '</span>' : '') + '</div>' +
   '<div class="meta">' + (k.series ? '<span class="series">' + esc(k.series) + '</span>' : '') + '<h3>' + esc(k.name) + '</h3>' + gapLine(k) +
   (k.tags.length ? '<span class="tagline">' + k.tags.slice(0, 3).map(function (t) { return '#' + esc(t); }).join(' ') + '</span>' : '') +
   '<div class="row"><span class="scale">' + esc(k.scale || '') + '</span>' +
   (k.list === 'own' ? '<span class="pill st-' + k.status + '">' + esc(STLABEL[k.status]) + '</span>' : (showPurchase() && k.price ? '<span class="scale">' + won(k.price) + '</span>' : '')) +
   '</div></div></button>';
}

var lastList = [];
function renderList() {
  lastList = P.filterSort(allKits(), ui, { gap: gapOf });
  document.getElementById('countline').textContent = lastList.length + '개 표시 중';
  var gt = document.getElementById('gap-tools');
  if (gt) {
    var unl = canWrite && ui.gap === 'unlinked' ? lastList.filter(function (k) { return !k.catalogId && !k.sample; }) : [];
    gt.innerHTML = unl.length ? '<button class="btn" type="button" id="gap-assist">연결 도우미로 시작 (' + unl.length + '개)</button><span class="hint">지금 보이는 순서대로 하나씩 연결해요.</span>' : '';
    var gb = document.getElementById('gap-assist'); if (gb) gb.addEventListener('click', function () { openAssist(unl); });
  }
  var cl = document.getElementById('countline');
  if (catState === 'error' && hasLinked()) cl.textContent += ' · 카탈로그를 불러오지 못해 공식 사진이 빠져 있어요';
  var empty = tabKits().length ? '조건에 맞는 프라가 없어요. 검색어나 필터를 바꿔 보세요.' : (ui.tab === 'wish' ? '위시리스트가 비어 있어요. 사고 싶은 프라를 추가해 보세요.' : '아직 등록한 프라가 없어요.');
  document.getElementById('grid').innerHTML = lastList.length ? lastList.map(cardHTML).join('') : '<div class="empty" style="grid-column:1/-1">' + empty + '</div>';
}

function renderSelbar() {
  var b = document.getElementById('selbar');
  if (!sel) { if (b) b.remove(); return; }
  if (!b) { b = document.createElement('div'); b.id = 'selbar'; b.className = 'selbar'; b.setAttribute('role', 'region'); b.setAttribute('aria-label', '선택한 프라'); document.body.appendChild(b); }
  b.innerHTML = '<span class="cnt">' + sel.size + '개 선택됨</span><button class="btn" data-s="all">보이는 것 모두 선택</button><button class="btn" data-s="none">선택 해제</button>' +
    '<button class="btn primary" data-s="edit"' + (sel.size ? '' : ' disabled') + '>일괄 수정</button><button class="btn" data-s="exit">끝내기</button>';
  b.onclick = function (e) { var t = e.target.closest('[data-s]'); if (!t) return; var a = t.dataset.s;
    if (a === 'all') { lastList.forEach(function (k) { sel.add(k.id); }); renderList(); renderSelbar(); }
    else if (a === 'none') { sel.clear(); renderList(); renderSelbar(); }
    else if (a === 'edit') { if (sel.size) openBulk(); }
    else if (a === 'exit') { sel = null; renderAll(); } };
}

function bindShell() {
  var q = document.getElementById('q');
  if (q) q.addEventListener('input', function () { ui.q = q.value; renderList(); });
  var on = function (id, key, full) { var el = document.getElementById(id); if (el) el.addEventListener('change', function () { ui[key] = el.value; saveUI(); if (full) renderStats(); renderList(); }); };
  on('f-status', 'status'); on('f-sort', 'sort'); on('f-gap', 'gap');
  app.querySelector('.tabs').addEventListener('click', function (e) { var t = e.target.closest('[data-tab]'); if (!t || t.dataset.tab === ui.tab) return; ui.tab = t.dataset.tab; ui.grade = 'all'; ui.tag = 'all'; if (sel) sel.clear(); saveUI(); renderAll(); });
  if (ui.tab !== 'feed') document.getElementById('chips').addEventListener('click', function (e) { var b = e.target.closest('.chip'); if (!b) return; ui.grade = b.dataset.grade; saveUI(); renderStats(); renderList(); });
  if (ui.tab !== 'feed') document.getElementById('tagchips').addEventListener('click', function (e) { var b = e.target.closest('.chip'); if (!b) return; ui.tag = b.dataset.tag; saveUI(); renderStats(); renderList(); });
  if (ui.tab !== 'feed') document.getElementById('grid').addEventListener('click', function (e) { var c = e.target.closest('.card'); if (!c) return;
    if (sel) { var id = c.dataset.id; if (sel.has(id)) sel.delete(id); else sel.add(id); renderList(); renderSelbar(); var n = document.querySelector('.card[data-id="' + CSS.escape(id) + '"]'); if (n) n.focus(); }
    else openDetail(c.dataset.id); });
  app.querySelectorAll('[data-act]').forEach(function (b) { b.addEventListener('click', function () {
    var a = b.dataset.act;
    if (a === 'add') openForm(null); else if (a === 'import') openImport(); else if (a === 'settings') openSettings(); else if (a === 'export') exportXlsx();
    else if (a === 'select') { sel = sel ? null : new Set(); renderAll(); }
  }); });
}

/* ---------- modal ---------- */
var lastFocus = null;
function openModal(title, body, foot) {
  closeModal(); lastFocus = document.activeElement;
  var o = document.createElement('div'); o.className = 'overlay'; o.id = 'modal';
  o.innerHTML = '<div class="panel" role="dialog" aria-modal="true" aria-labelledby="m-title"><div class="panel-head"><h2 id="m-title">' + esc(title) + '</h2><button class="x" data-close aria-label="닫기">×</button></div>' +
    '<div class="panel-body">' + body + '</div>' + (foot ? '<div class="panel-foot">' + foot + '</div>' : '') + '</div>';
  o.addEventListener('click', function (e) { if (e.target === o || e.target.closest('[data-close]')) closeModal(); });
  document.body.appendChild(o);
  var f = o.querySelector('input:not([type=file]),select,textarea,button:not(.x)') || o.querySelector('.x'); if (f) f.focus();
  return o;
}
function closeModal(force) {
  var m = document.getElementById('modal');
  if (m && !force && m._guard && !m._guard()) return;          // 저장하지 않은 작업이 있으면 확인을 거친다 (연결 도우미)
  if (m) { if (m._cleanup) m._cleanup(); m.remove(); if (lastFocus && lastFocus.focus && document.contains(lastFocus)) lastFocus.focus(); }
}
document.addEventListener('keydown', function (e) {
  if (e.key !== 'Escape') return;
  if (document.getElementById('alert')) { closeAlert(null); return; }
  closeModal();
});

/* ---------- 반다이 제품 찾기 (추가·수정 폼과 상세의 연결 창이 함께 쓴다) ---------- */
function relText(it) { return it.release.date || it.release.month || ''; } // 월만 아는 발매일은 월까지만 보인다 (날짜를 지어내지 않음)
function usedBy(id, exceptId) { return data.kits.filter(function (x) { return x.catalogId === id && x.id !== exceptId; }); }
function pickerHTML(o) {
  return '<div class="picker" id="pk"><div class="pk-row"><input id="pk-q" type="search" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="한국어·일본어 이름, 또는 호비사이트 상품 주소" aria-label="반다이 제품 찾기" value="' + esc(o.query || '') + '">' +
    '<select id="pk-grade" aria-label="등급 필터">' + opt('all', '모든 등급', o.grade || 'all') + GRADES.filter(function (g) { return g !== '기타'; }).map(function (g) { return opt(g, g, o.grade); }).join('') + '</select></div>' +
    '<p class="hint" id="pk-status" role="status"></p><ul class="pk-results" id="pk-results"></ul></div>';
}
function pickRow(it, exceptId) {
  var im = it.images[0], used = usedBy(it.id, exceptId);
  return '<li class="pk-item" data-id="' + esc(it.id) + '"><div class="pk-thumb">' + (im ? '<img src="' + esc(C.thumbUrl(im)) + '"' + (C.thumbUrl(im) !== im ? ' data-alt="' + esc(im) + '"' : '') + ' alt="" loading="lazy" referrerpolicy="no-referrer" data-g="' + esc(P.glabel(it.grade)) + '">' : '<div class="ghost">' + esc(P.glabel(it.grade)) + '</div>') + '</div>' +
    '<div class="pk-body"><b>' + esc(it.title) + '</b><span class="hint">' + esc([it.grade, it.scale, relText(it), it.seriesText].filter(Boolean).join(' · ')) + '</span>' +
    (used.length ? '<span class="hint pk-used">이미 ' + esc(used.slice(0, 2).map(function (x) { return '"' + x.name + '"'; }).join(', ')) + (used.length > 2 ? ' 외 ' + (used.length - 2) + '개' : '') + '에 연결돼 있어요</span>' : '') + '</div>' +
    '<button type="button" class="btn" data-pick="' + esc(it.id) + '">선택</button></li>';
}
// root 안의 #pk-* 를 묶는다. o.onPick({id, item|null}) · o.getScale() · o.exceptId. 반환: {paint}
function bindPicker(root, o) {
  var q = root.querySelector('#pk-q'), g = root.querySelector('#pk-grade'), st = root.querySelector('#pk-status'), ul = root.querySelector('#pk-results'), timer, picked = null;
  function status(msg, retry) {
    st.textContent = msg;
    if (retry) { var b = document.createElement('button'); b.type = 'button'; b.className = 'linkbtn'; b.textContent = '다시 시도'; b.addEventListener('click', function () { start(); }); st.appendChild(b); }
  }
  function paint() {
    ul.innerHTML = '';
    if (catState !== 'ready') { if (catState === 'error') status('카탈로그를 불러오지 못했어요. ', true); else status('카탈로그를 불러오는 중이에요…'); return; }
    var text = q.value.trim();
    if (!text) { status('이름을 입력하면 반다이 제품 ' + cat.items.length.toLocaleString('ko-KR') + '개 중에서 찾아요. 호비사이트 상품 주소를 붙여넣어도 돼요.'); return; }
    var ref = C.parseRef(text);
    if (ref) {
      var hit = cat.byId[ref.id];
      if (hit) { status('주소로 찾은 제품이에요.'); ul.innerHTML = pickRow(hit, o.exceptId); }
      else if (ref.kind === 'hobby') {
        status('이 제품은 아직 카탈로그에 없어요.');
        ul.innerHTML = '<li class="pk-item pk-ref" data-id="' + esc(ref.id) + '"><div class="pk-body"><b>' + esc(ref.id) + '</b><span class="hint">연결만 저장해 두면 다음 수집 때 이름·등급·사진이 채워져요. 이름은 직접 적어 주세요.</span></div>' +
          '<button type="button" class="btn" data-pick-ref="' + esc(ref.id) + '">이 주소로 연결</button></li>';
      } else status('P-반다이 한정 상품은 카탈로그에 있는 것만 연결할 수 있어요. 이름으로 찾아 보세요.');
      return;
    }
    var r = C.search(cat, text, { grade: g.value, scale: o.getScale && o.getScale(), limit: o.limit });
    if (!r.results.length) { status('찾지 못했어요.' + (g.value !== 'all' ? ' 등급을 "모든 등급"으로 바꿔 보세요.' : ' 카탈로그는 수집이 진행 중이라 일부 제품이 아직 없을 수 있어요. 호비사이트 상품 주소를 붙여넣으면 연결만 해 둘 수 있어요.')); return; }
    status(r.partial ? '정확히 같은 이름은 없어요. 비슷한 후보예요.' : (r.total > r.results.length ? r.total + '개 중 ' + r.results.length + '개를 보여 줘요. 더 구체적으로 적어 보세요.' : r.total + '개를 찾았어요.'));
    ul.innerHTML = r.results.map(function (it) { return pickRow(it, o.exceptId); }).join('');
    if (picked) { var cur = ul.querySelector('[data-id="' + CSS.escape(picked) + '"]'); if (cur) cur.classList.add('picked'); }
  }
  function start() { if (catState === 'error') catPromise = null; paint(); ensureCatalog().then(paint); }
  q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(paint, 120); });
  g.addEventListener('change', paint);
  q.addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); }); // 폼 제출·저장 방지
  ul.addEventListener('click', function (e) {
    var b = e.target.closest('[data-pick],[data-pick-ref]'); if (!b) return;
    var id = b.dataset.pick || b.dataset.pickRef;
    picked = id; ul.querySelectorAll('.pk-item').forEach(function (li) { li.classList.toggle('picked', li.dataset.id === id); });
    o.onPick({ id: id, item: b.dataset.pick ? (cat.byId[id] || null) : null });
  });
  start();
  return { paint: paint };
}

function openLink(k) {
  var chosen = null, rename;
  var body = '<p class="hint" style="font-size:14px">"' + esc(k.name) + '"에 연결할 반다이 제품을 골라요. 이름·등급·스케일·시리즈는 비어 있는 칸만 채우고, 이미 적은 값은 그대로 둬요.</p>' +
    pickerHTML({ query: k.name, grade: gname(k.grade) === '기타' ? 'all' : gname(k.grade) }) +
    '<label class="check"><input type="checkbox" id="pk-rename"><span>이름도 카탈로그 이름으로 바꾸기</span></label><p class="hint" id="pk-sum">제품을 고르면 채워질 항목을 알려 드려요.</p>';
  var foot = '<span class="hint" style="align-self:center">저장하면 저장소에 커밋이 하나 생겨요.</span><div class="r"><button class="btn" data-close>취소</button><button class="btn primary" id="pk-go" disabled>연결</button></div>';
  var m = openModal('반다이 제품 연결', body, foot);
  var go = m.querySelector('#pk-go'); rename = m.querySelector('#pk-rename');
  function summary() {
    var s = m.querySelector('#pk-sum');
    if (!chosen) return;
    if (!chosen.item) { s.textContent = '연결만 저장해요. 이름·등급·사진은 다음 수집 때 채워져요.'; return; }
    var r = C.fillPatch(chosen.item, k, { replaceName: rename.checked });
    s.textContent = '"' + chosen.item.title + '"에 연결해요. ' + (r.filled.length ? '채워지는 항목: ' + r.filled.join(', ') : '채울 빈 칸은 없어요.');
  }
  rename.addEventListener('change', summary);
  bindPicker(m, { exceptId: k.id, getScale: function () { return k.scale === '논스케일' ? null : k.scale; }, onPick: function (sel) { chosen = sel; go.disabled = false; summary(); } });
  go.addEventListener('click', function () {
    if (!chosen) return;
    var pick = chosen, repl = rename.checked;
    commit(function (d) {
      var x = d.kits.filter(function (y) { return y.id === k.id; })[0]; if (!x) return;
      if (pick.item) Object.assign(x, C.fillPatch(pick.item, x, { replaceName: repl }).patch);
      if (x.catalogId !== pick.id && x.cover && x.cover.indexOf('off:') === 0) x.cover = null;
      x.catalogId = pick.id;
    }, 'link', { name: k.name }, { okMsg: '"' + k.name + '"을(를) 반다이 제품에 연결했어요.' });
  });
}

/* ---------- 설정: 자동 연결 후보 보기 (이름·등급·스케일이 모두 같고 카탈로그 후보가 1개뿐인 것만) ---------- */
function openAutoLink() {
  var body = '<div id="al-body"><p class="hint">카탈로그를 불러오는 중이에요…</p></div>';
  var foot = '<span class="hint" style="align-self:center">저장하면 저장소에 커밋이 하나 생겨요.</span><div class="r"><button class="btn" data-close>취소</button><button class="btn primary" id="al-go" disabled>적용</button></div>';
  var m = openModal('자동 연결 후보', body, foot);
  var box = m.querySelector('#al-body'), go = m.querySelector('#al-go'), links = [], sers = [], fills = [];
  function thumbHTML(it) {
    var im = it.images[0], t = im ? C.thumbUrl(im) : '';
    return '<div class="pk-thumb">' + (im ? '<img src="' + esc(t) + '"' + (t !== im ? ' data-alt="' + esc(im) + '"' : '') + ' alt="" loading="lazy" referrerpolicy="no-referrer" data-g="' + esc(P.glabel(it.grade)) + '">' : '<div class="ghost">' + esc(P.glabel(it.grade)) + '</div>') + '</div>';
  }
  function section(title, hint, rows, kind) {
    if (!rows.length) return '';
    return '<div class="al-sec"><div class="al-head"><h3>' + esc(title) + ' <span class="n">' + rows.length + '</span></h3><button type="button" class="linkbtn" data-all="' + kind + '">전체 해제</button></div>' +
      '<p class="hint">' + esc(hint) + '</p><ul class="pk-results al-list">' + rows.join('') + '</ul></div>';
  }
  function paint() {
    if (!cat) { box.innerHTML = '<p class="hint">카탈로그를 불러오지 못했어요. <button type="button" class="linkbtn" id="al-retry">다시 시도</button></p>'; return; }
    links = C.autoLinks(data.kits, cat); sers = C.seriesKoSuggestions(data.kits, cat); fills = C.fillCandidates(data.kits, cat);
    if (!links.length && !sers.length && !fills.length) {
      box.innerHTML = '<p class="hint" style="font-size:14px">제안할 게 없어요. 이름·등급·스케일이 모두 같고 카탈로그 후보가 하나뿐인 미연결 프라가 없고, 시리즈를 한국어로 바꿀 연결 프라도 없어요. (이름이 조금이라도 다르거나 등급이 "기타"인 프라는 상세에서 직접 연결해 주세요.)</p>';
      go.disabled = true; return;
    }
    var lrows = links.map(function (x) {
      return '<li class="pk-item"><label class="al-check"><input type="checkbox" data-kind="link" data-id="' + esc(x.kit.id) + '" checked></label>' + thumbHTML(x.item) +
        '<div class="pk-body"><b>' + esc(x.kit.name) + '</b><span class="hint">→ ' + esc(x.item.title) + '</span><span class="hint">' + esc([x.item.grade, x.item.scale, relText(x.item)].filter(Boolean).join(' · ')) +
        (x.filled.length ? ' · 채워질 항목: ' + esc(x.filled.join(', ')) : '') + '</span></div></li>';
    });
    var srows = sers.map(function (x) {
      return '<li class="pk-item"><label class="al-check"><input type="checkbox" data-kind="series" data-id="' + esc(x.kit.id) + '" checked></label>' +
        '<div class="pk-body"><b>' + esc(x.kit.name) + '</b><span class="hint">' + esc(x.from) + '</span><span class="hint">→ ' + esc(x.to) + '</span></div></li>';
    });
    var frows = fills.map(function (x) {
      return '<li class="pk-item"><label class="al-check"><input type="checkbox" data-kind="fill" data-id="' + esc(x.kit.id) + '" checked></label>' + thumbHTML(x.item) +
        '<div class="pk-body"><b>' + esc(x.kit.name) + '</b>' + x.changes.map(function (c) { return '<span class="hint">' + esc(c.label) + ': ' + esc(c.from || '(비어 있음)') + ' → ' + esc(c.to) + '</span>'; }).join('') + '</div></li>';
    });
    box.innerHTML = '<p class="hint" style="font-size:14px">체크한 것만 적용해요. 연결하면 이름·등급·스케일은 그대로 두고 비어 있는 칸(시리즈 등)만 채워요.</p>' +
      section('반다이 제품에 연결', '이름·등급·스케일이 모두 같은 제품이 카탈로그에 하나뿐인 프라예요.', lrows, 'link') +
      section('시리즈를 한국어로 바꾸기', '시리즈 칸이 카탈로그의 일본어 시리즈와 똑같은 프라만 보여요. 직접 적은 값은 건드리지 않아요.', srows, 'series') +
      section('빈 칸 채우기', '이미 연결된 프라 중 등급(기타)·스케일(논스케일)·시리즈가 비어 있는데 카탈로그에 값이 생긴 것이에요. 직접 적은 값은 건드리지 않아요.', frows, 'fill');
    count();
  }
  function picked(kind) { return Array.prototype.slice.call(box.querySelectorAll('input[data-kind="' + kind + '"]:checked')).map(function (i) { return i.dataset.id; }); }
  function count() {
    var a = picked('link').length, b = picked('series').length, c = picked('fill').length;
    go.disabled = !(a + b + c); go.textContent = !(a + b + c) ? '적용' : [a ? a + '개 연결' : '', b ? '시리즈 ' + b + '개 변경' : '', c ? '빈 칸 ' + c + '개 채움' : ''].filter(Boolean).join(' · ') + ' 적용';
  }
  box.addEventListener('change', function (e) { if (e.target.matches('input[data-kind]')) count(); });
  box.addEventListener('click', function (e) {
    if (e.target.closest('#al-retry')) { ensureCatalog().then(paint); return; }
    var all = e.target.closest('[data-all]'); if (!all) return;
    var boxes = box.querySelectorAll('input[data-kind="' + all.dataset.all + '"]'), on = all.textContent === '전체 선택';
    boxes.forEach(function (i) { i.checked = on; }); all.textContent = on ? '전체 해제' : '전체 선택'; count();
  });
  go.addEventListener('click', function () {
    var linkMap = {}; picked('link').forEach(function (id) { var x = links.filter(function (l) { return l.kit.id === id; })[0]; if (x) linkMap[id] = x.item.id; });
    var serIds = picked('series'), fillIds = picked('fill'), result = { links: 0, series: 0, fills: 0 };
    commit(function (d) { result = C.applyAuto(d.kits, cat, linkMap, serIds, fillIds); }, 'autolink', { links: Object.keys(linkMap).length, series: serIds.length, fills: fillIds.length },
      { okMsg: [Object.keys(linkMap).length ? '반다이 제품 ' + Object.keys(linkMap).length + '개를 연결' : '', serIds.length ? '시리즈 ' + serIds.length + '개를 한국어로 변경' : '', fillIds.length ? '빈 칸 ' + fillIds.length + '개를 채움' : ''].filter(Boolean).join(', ') + '했어요.' });
  });
  ensureCatalog().then(function () { if (m.isConnected) paint(); });
}

/* ---------- 연결 도우미: 미연결 프라를 하나씩 보며 후보 5개 + 검색으로 연결 (연결은 모아서 한 번에 저장) ---------- */
var LATER_KEY = 'plamo-later';
function getLater() { try { var a = JSON.parse(localStorage.getItem(LATER_KEY) || '[]'); return Array.isArray(a) ? a : []; } catch (e) { return []; } }
function setLater(ids) { try { localStorage.setItem(LATER_KEY, JSON.stringify(ids)); } catch (e) {} } // "나중에"는 이 브라우저에만 기억한다
function unlinkedKits() { return data.kits.filter(function (k) { return k.list === 'own' && !k.catalogId; }).concat(data.kits.filter(function (k) { return k.list === 'wish' && !k.catalogId; })); }

// kitsList: 보여 줄 순서의 프라(없으면 보유 → 위시리스트의 미연결 전부). o.skipped: 중간 저장 뒤 이어 갈 때 이미 건너뛴 id들
function openAssist(kitsList, o) {
  o = o || {};
  var kits = (kitsList || unlinkedKits()).filter(function (k) { return !k.catalogId; });
  if (!kits.length) { toast('연결할 프라가 없어요. 모두 반다이 제품과 연결돼 있어요.'); return; }
  var session = AS.createSession(kits, { deferred: getLater(), skipped: o.skipped || [] }), kitIds = kits.map(function (k) { return k.id; });
  var chosen = null, saving = false;
  var body = '<div id="as-count" class="as-count" aria-live="polite"></div><div id="as-main"></div>';
  var foot = '<button class="btn" id="as-save" disabled>중간 저장</button><div class="r"><button class="btn" id="as-back" disabled>이전</button><button class="btn" id="as-skip">건너뛰기</button><button class="btn" id="as-later">나중에</button><button class="btn primary" id="as-link" disabled>연결</button></div>';
  var m = openModal('연결 도우미', body, foot);
  var main = m.querySelector('#as-main'), cnt = m.querySelector('#as-count');
  var $ = function (id) { return m.querySelector('#' + id); };
  var persistLater = function () { setLater(AS.cleanLater(session.deferredIds(), data.kits)); };

  // 저장하지 않은 연결이 있는데 닫으려 하면 한 번 확인한다
  m._guard = function () {
    if (saving || !session.pendingCount()) return true;
    openAlert('저장하지 않은 연결이 ' + session.pendingCount() + '개 있어요', '지금 닫으면 이 연결은 저장되지 않아요.',
      [{ label: '계속하기', value: false }, { label: '저장하지 않고 닫기', value: true, primary: true }]).then(function (yes) { if (yes) closeModal(true); });
    return false;
  };

  function save(reopen) {
    var map = session.pendingMap(), n = session.pendingCount(); if (!n) return;
    saving = true;
    commit(function (d) { C.applyAuto(d.kits, cat, map, null, null); }, 'assist', { n: n }, { okMsg: '반다이 제품 ' + n + '개를 연결했어요.' }).then(function (ok) {
      saving = false;
      if (!ok) return;
      session.afterSave(); persistLater();
      if (reopen) openAssist(kitIds.map(findKit).filter(function (k) { return k && !k.catalogId; }), { skipped: session.skippedIds() }); // 중간 저장: 이어서
    });
  }

  function stat() {
    var st = session.stats();
    cnt.innerHTML = '<span><b>' + st.pending + '</b> 연결 대기</span><span><b>' + st.left + '</b> 남음</span><span>건너뜀 ' + st.skipped + '</span><span>나중에 ' + st.later + '</span>';
    $('as-save').disabled = !st.pending; $('as-save').textContent = st.pending ? '중간 저장 (' + st.pending + ')' : '중간 저장';
    $('as-back').disabled = !session.canBack();
    return st;
  }
  function kitCard(k) {
    var cover = P.photoOrder(k, []).cover;
    return '<div class="as-kit"><div class="pk-thumb as-thumb">' + (cover ? '<img src="' + esc(photoSrc(cover.thumb)) + '" alt="" referrerpolicy="no-referrer" data-g="' + esc(P.glabel(k.grade)) + '">' : '<div class="ghost">' + esc(P.glabel(k.grade)) + '</div>') + '</div>' +
      '<div class="pk-body"><b>' + esc(k.name) + '</b><span class="hint">' + esc([k.list === 'wish' ? '위시리스트' : '보유', gname(k.grade), k.scale, k.series].filter(Boolean).join(' · ')) + '</span>' +
      (k.tags.length ? '<span class="hint">' + k.tags.slice(0, 4).map(function (t) { return '#' + esc(t); }).join(' ') + '</span>' : '') + '</div></div>';
  }
  function paint() {
    chosen = null; $('as-link').disabled = true;
    var st = stat(), k = session.current();
    if (catState !== 'ready') { main.innerHTML = '<p class="hint">' + (catState === 'error' ? '카탈로그를 불러오지 못했어요. <button type="button" class="linkbtn" id="as-retry">다시 시도</button>' : '카탈로그를 불러오는 중이에요…') + '</p>'; ensureCatalog().then(function () { if (m.isConnected) paint(); }); setActions(false); return; }
    if (!k) { endScreen(st); return; }
    setActions(true);
    var gv = gname(k.grade);
    main.innerHTML = kitCard(k) + pickerHTML({ query: k.name, grade: gv === '기타' ? 'all' : gv }) + '<p class="hint" id="as-sel">후보를 골라 [연결]을 누르세요. 맞는 게 없으면 [건너뛰기]나 [나중에].</p>';
    bindPicker(main, { exceptId: k.id, limit: 5, getScale: function () { return k.scale === '논스케일' ? null : k.scale; },
      onPick: function (sel) {
        chosen = sel; $('as-link').disabled = false;
        var r = sel.item ? C.fillPatch(sel.item, k) : null;
        main.querySelector('#as-sel').textContent = sel.item ? '"' + sel.item.title + '"에 연결해요.' + (r.filled.length ? ' 채워질 항목: ' + r.filled.join(', ') : '') : '연결만 저장해요. 이름·등급·사진은 다음 수집 때 채워져요.';
      } });
  }
  function setActions(on) { ['as-skip', 'as-later'].forEach(function (id) { $(id).disabled = !on; }); }
  function endScreen(st) {
    setActions(false);
    main.innerHTML = '<div class="as-end"><h3>모두 훑었어요</h3><p class="hint">' + (st.pending ? '연결 대기 ' + st.pending + '개를 저장하면 반다이 제품과 연결돼요.' : '연결 대기 중인 프라는 없어요.') + '</p><div class="row-btns">' +
      (st.pending ? '<button class="btn primary" id="as-end-save">' + st.pending + '개 저장하고 닫기</button>' : '') +
      (st.skipped ? '<button class="btn" id="as-review-skip">건너뛴 ' + st.skipped + '개 다시 보기</button>' : '') +
      (st.later ? '<button class="btn" id="as-review-later">나중에 미룬 ' + st.later + '개 보기</button>' : '') + '</div></div>';
  }
  m.addEventListener('click', function (e) {
    var id = e.target && e.target.id;
    if (id === 'as-retry') { ensureCatalog().then(paint); }
    else if (id === 'as-end-save') { save(false); }
    else if (id === 'as-review-skip') { session.reviewSkipped(); paint(); }
    else if (id === 'as-review-later') { session.reviewLater(); paint(); }
  });
  $('as-link').addEventListener('click', function () { if (chosen && session.link(chosen.id)) paint(); });
  $('as-skip').addEventListener('click', function () { if (session.skip()) paint(); });
  $('as-later').addEventListener('click', function () { if (session.later()) { persistLater(); paint(); } else toast('나중에 미룰 수 있는 개수(' + AS.MAX_LATER + '개)에 닿았어요.'); });
  $('as-back').addEventListener('click', function () { if (session.back()) { persistLater(); paint(); } });
  $('as-save').addEventListener('click', function () { save(true); });
  paint();
}

function openDetail(id) {
  var k = findKit(id); if (!k) return;
  var own = k.list === 'own', rows = [['목록', own ? '보유' : '위시리스트'], ['등급', gname(k.grade)], ['스케일', k.scale], ['시리즈', k.series], ['브랜드', k.brand]];
  if (own) rows.push(['상태', STLABEL[k.status]]);
  if (own && showPurchase()) rows.push(['구매일', k.date], ['구매처', k.shop], ['가격', k.price ? won(k.price) : '']);
  if (!own && showPurchase()) rows.push(['예상 가격', k.price ? won(k.price) : '']);
  if (own) { var d = days(k.startDate, k.doneDate); rows.push(['조립 시작', k.startDate], ['완성', k.doneDate ? k.doneDate + (d ? ' (' + d + '일 걸림)' : '') : '']); }
  if (k.tags.length) rows.push(['태그', k.tags.map(function (t) { return '#' + t; }).join(' ')]);
  var gi = gapOf(k); if (gi) rows.splice(5, 0, ['재판 공백', gi.text]);
  var show = rows.filter(function (r) { return r[1] || (canWrite && !k.sample); });
  var order = P.photoOrder(k, official(k)).list, g = gname(k.grade), ci = catItem(k), pu = ci && C.pageUrl(ci);
  var gallery = order.length ? '<div class="detail-photo"><img id="d-main" src="' + esc(imgUrl(order[0], false)) + '" alt="' + esc(k.name) + ' 사진" referrerpolicy="no-referrer" data-g="' + esc(g) + '" data-note="' + (order[0].kind === 'off' ? '' : '1') + '">' +
      (order.length > 1 ? '<span class="count" id="d-count">1 / ' + order.length + '</span>' : '') + '</div>' + creditHTML(k, order[0].kind === 'off') +
    (order.length > 1 ? '<div class="thumbs">' + order.map(function (p, i) { return '<button type="button" class="th" data-i="' + i + '" aria-label="사진 ' + (i + 1) + '" aria-current="' + (i === 0) + '"><img src="' + esc(imgUrl(p, true)) + '"' + imgAlt(p, true) + ' alt="" loading="lazy" referrerpolicy="no-referrer" data-g=""></button>'; }).join('') + '</div>' : '') :
    // 연결됐는데 쓸 수 있는 사진이 없을 때(서명 URL뿐인 신제품 등): 등급 글자 자리표시 + 공식 페이지 버튼
    (k.catalogId && catState === 'ready' && !k.sample ? '<div class="detail-photo"><div class="ghost">' + esc(P.glabel(k.grade)) + '</div></div>' +
      '<p class="hint official-link">' + (data.settings.hideOfficialPhotos ? '공식 사진 숨김 설정이 켜져 있어요. ' : '이 제품은 쓸 수 있는 공식 사진이 없어요. ') +
      (pu ? '<a class="btn" href="' + esc(pu) + '" target="_blank" rel="noopener noreferrer">공식 사진 보기</a>' : '') + '</p>' : '');
  var linkInfo = !k.catalogId ? '' : '<div class="linkbox"><span class="lk">반다이 제품</span>' + (ci
      ? '<span>' + esc(ci.title) + ' <span class="hint">' + esc([ci.grade, ci.scale, ci.seriesText].filter(Boolean).join(' · ')) + '</span>' + (pu ? ' · <a href="' + esc(pu) + '" target="_blank" rel="noopener noreferrer">공식 페이지</a>' : '') + '</span>'
      : '<span class="hint">' + (catState === 'ready' ? '카탈로그에 아직 없는 제품이에요 (' + esc(k.catalogId) + '). 다음 수집 때 채워져요.' : catState === 'error' ? '카탈로그를 불러오지 못했어요.' : '카탈로그를 불러오는 중이에요…') + '</span>') + '</div>';
  var rv = k.sample ? null : C.reviewLinks(k);
  var reviews = rv ? '<p class="reviews"><span class="lk">리뷰 찾아보기</span><a href="' + esc(rv.youtube) + '" target="_blank" rel="noopener noreferrer">유튜브</a><a href="' + esc(rv.naver) + '" target="_blank" rel="noopener noreferrer">네이버 블로그</a></p>' : '';
  var body = gallery + linkInfo + reviews +
    '<dl class="specs">' + show.map(function (r) { return '<dt>' + r[0] + '</dt>' + (r[1] ? '<dd' + (/가격/.test(r[0]) ? ' class="mono"' : '') + '>' + esc(r[1]) + '</dd>' : '<dd class="missing">미입력</dd>'); }).join('') + '</dl>' +
    (k.memo ? '<p class="memo">' + esc(k.memo) + '</p>' : '');
  var foot = (canWrite && !k.sample) ? '<button class="btn danger" id="del">삭제</button><div class="r">' + '<button class="btn" id="relink">' + (k.catalogId ? '제품 연결 변경' : '반다이 제품 연결') + '</button>' + (k.catalogId ? '<button class="btn" id="unlink">연결 해제</button>' : '') +
    (own ? '' : '<button class="btn" id="move">샀어요 · 보유로 옮기기</button>') + '<button class="btn primary" id="edit">수정</button></div>' : '';
  var m = openModal(k.name, body, foot);
  m.dataset.kit = k.id;
  if (k.catalogId && catState !== 'ready') ensureCatalog().then(function () { if (m.isConnected && m.dataset.kit === k.id) openDetail(k.id); }); // 카탈로그가 도착하면 같은 상세를 다시 그린다
  m.addEventListener('click', function (e) {
    var t = e.target.closest('.th'); if (!t) return;
    var i = +t.dataset.i, main = m.querySelector('#d-main'); if (!main || !order[i]) return;
    main.src = imgUrl(order[i], false); main.dataset.note = order[i].kind === 'off' ? '' : '1';
    var cr = m.querySelector('#d-credit'); if (cr) cr.hidden = order[i].kind !== 'off';
    var c = m.querySelector('#d-count'); if (c) c.textContent = (i + 1) + ' / ' + order.length;
    m.querySelectorAll('.th').forEach(function (b) { b.setAttribute('aria-current', String(b === t)); });
  });
  if (foot) {
    m.querySelector('#edit').addEventListener('click', function () { openForm(k); });
    m.querySelector('#relink').addEventListener('click', function () { openLink(k); });
    var unl = m.querySelector('#unlink');
    if (unl) unl.addEventListener('click', function () {
      commit(function (d) { var x = d.kits.filter(function (y) { return y.id === k.id; })[0]; if (!x) return; x.catalogId = null; if (x.cover && x.cover.indexOf('off:') === 0) x.cover = null; },
        'unlink', { name: k.name }, { okMsg: '"' + k.name + '"의 반다이 제품 연결을 해제했어요. 채워 둔 값은 그대로예요.' });
    });
    var mv = m.querySelector('#move'); if (mv) mv.addEventListener('click', function () { openForm(k, { moveToOwn: true }); });
    var del = m.querySelector('#del');
    del.addEventListener('click', function () {
      if (!del.classList.contains('armed')) { del.classList.add('armed'); del.textContent = '한 번 더 누르면 삭제'; return; }
      commit(function (d) { d.kits = d.kits.filter(function (x) { return x.id !== k.id; }); }, 'delete', { name: k.name }, { okMsg: '"' + k.name + '"을(를) 삭제했어요.' });
    });
  }
}

function tagSuggest() {
  var seen = {}, out = []; data.kits.forEach(function (k) { k.tags.forEach(function (t) { if (!seen[t]) { seen[t] = 1; out.push(t); } }); });
  P.TAG_SUGGEST.forEach(function (t) { if (!seen[t]) { seen[t] = 1; out.push(t); } });
  return out.slice(0, 14);
}
function bindTagSugg(root, input) {
  var box = root.querySelector('.sugg'); if (!box) return;
  var paint = function () { var cur = splitTags(input.value); box.querySelectorAll('.chip').forEach(function (c) { c.setAttribute('aria-pressed', String(cur.indexOf(c.dataset.t) >= 0)); }); };
  box.addEventListener('click', function (e) { var c = e.target.closest('.chip'); if (!c) return; var cur = splitTags(input.value), t = c.dataset.t, i = cur.indexOf(t);
    if (i >= 0) cur.splice(i, 1); else cur.push(t); input.value = cur.join(', '); paint(); });
  input.addEventListener('input', paint); paint();
}
function suggHTML() { return '<div class="sugg">' + tagSuggest().map(function (t) { return '<button type="button" class="chip" data-t="' + esc(t) + '">#' + esc(t) + '</button>'; }).join('') + '</div>'; }

function openForm(k, o) {
  o = o || {}; var isNew = !k, move = !!o.moveToOwn;
  k = k || { name: '', grade: 'HG', scale: '1/144', series: '', brand: '반다이', status: 'unbuilt', date: ui.tab === 'wish' ? '' : today(), shop: '', price: '', memo: '', tags: [], startDate: '', doneDate: '', list: ui.tab === 'wish' ? 'wish' : 'own', photos: [], cover: null, catalogId: null };
  if (isNew && o.prefill) k = Object.assign(k, o.prefill); // 신제품·입고 탭의 '위시리스트에 추가'
  var kitId = isNew ? uid() : k.id;
  var list = move ? 'own' : k.list, status = move ? 'unbuilt' : k.status, date = move ? (k.date || today()) : k.date;
  var dupOk = false;
  var work = { photos: (k.photos || []).map(P.clone), cover: k.cover || null }; // 사진 편집 중 상태 (저장 전)
  var pend = {}, savedFlag = false; // 이번 폼에서 새로 만든 사진 파일 {photoId: {full, thumb, src, thumb}}
  var link = k.catalogId ? { id: k.catalogId, item: null } : null; // 반다이 제품 연결 (저장 전 상태)
  if (link && catState === 'idle') ensureCatalog();
  var body = '<form class="form' + (list === 'wish' ? ' is-wish' : '') + '" id="kit-form" novalidate>' +
   '<div class="field full pk-field"><span class="lbl">반다이 제품 연결</span><div id="pk-linked"></div><div id="pk-open-wrap"><button type="button" class="btn" id="pk-open" aria-expanded="false">반다이 제품에서 찾기</button></div><div id="pk-box" hidden></div></div>' +
   '<div class="field full"><label for="f-name">이름 *</label><input id="f-name" required value="' + esc(k.name) + '" placeholder="예: 건담 에어리얼"><div class="warn" id="dup" hidden></div></div>' +
   '<div class="field"><label for="f-list">목록</label><select id="f-list">' + opt('own', '보유', list) + opt('wish', '위시리스트', list) + '</select></div>' +
   '<div class="field own-only"><label for="k-status">상태</label><select id="k-status">' + STATUSES.map(function (s) { return opt(s.k, s.l, status); }).join('') + '</select></div>' +
   '<div class="field"><label for="f-grade">등급</label><select id="f-grade">' + GRADES.map(function (g) { return opt(g, g, gname(k.grade)); }).join('') + '</select></div>' +
   '<div class="field"><label for="f-scale">스케일</label><select id="f-scale">' + scaleChoices(k.scale).map(function (s) { return opt(s, s, scaleChoices(k.scale).indexOf(k.scale) >= 0 ? k.scale : '논스케일'); }).join('') + '</select></div>' +
   '<div class="field"><label for="f-series">시리즈·작품</label><input id="f-series" value="' + esc(k.series) + '" placeholder="예: 수성의 마녀"></div>' +
   '<div class="field"><label for="f-brand">브랜드</label><input id="f-brand" value="' + esc(k.brand) + '"></div>' +
   '<p class="sect own-only">구매 정보 · 비워 두고 나중에 채워도 돼요</p>' +
   '<div class="field own-only"><label for="f-date">구매일</label><input id="f-date" type="date" value="' + esc(date) + '"></div>' +
   '<div class="field"><label for="f-price"><span class="lbl-own">가격</span><span class="lbl-wish">예상 가격</span> (원)</label><input id="f-price" inputmode="numeric" value="' + esc(k.price || '') + '" placeholder="0"></div>' +
   '<div class="field full own-only"><label for="f-shop">구매처</label><input id="f-shop" value="' + esc(k.shop) + '" placeholder="예: 건담베이스, 온라인몰"></div>' +
   '<p class="sect own-only">조립 기록</p>' +
   '<div class="field own-only"><label for="f-start">조립 시작일</label><input id="f-start" type="date" value="' + esc(k.startDate) + '"></div>' +
   '<div class="field own-only"><label for="f-done">완성일</label><input id="f-done" type="date" value="' + esc(k.doneDate) + '"></div>' +
   '<p class="sect">태그 · 사진 · 메모</p>' +
   '<div class="field full"><label for="f-tags">태그 (쉼표로 구분)</label><input id="f-tags" value="' + esc(k.tags.join(', ')) + '" placeholder="예: P-반다이, 클리어">' + suggHTML() + '</div>' +
   '<div class="field full"><label for="f-photo">사진 (여러 장)</label><div class="pm" id="pm"></div>' +
     '<input id="f-photo" type="file" accept="image/*" multiple><p class="hint" id="pm-status">고른 사진은 긴 변 1600px WebP로 줄여 저장소에 올려요. "대표"로 지정한 사진(내 사진·공식 사진 모두 가능)이 목록 카드와 상세 맨 앞에 나와요.</p><p class="hint" id="pm-off-note"></p></div>' +
   '<div class="field full"><label for="f-memo">메모</label><textarea id="f-memo" placeholder="파츠 분실, 데칼, 도색 계획 등">' + esc(k.memo) + '</textarea></div>' +
   '</form>';
  var foot = '<span class="hint" style="align-self:center">저장하면 저장소에 커밋이 하나 생겨요.</span><div class="r"><button class="btn" data-close>취소</button><button class="btn primary" id="save">' + (isNew ? '추가' : '저장') + '</button></div>';
  var m = openModal(isNew ? '프라 추가' : move ? '보유로 옮기기' : '프라 수정', body, foot);
  m._cleanup = function () { if (!savedFlag) Object.keys(pend).forEach(function (id) { dropPhotoUrls(pend[id]); }); };
  var $ = function (id) { return m.querySelector('#' + id); };
  var form = $('kit-form'), saveBtn = $('save'), dupBox = $('dup');
  $('f-list').addEventListener('change', function () { form.classList.toggle('is-wish', $('f-list').value === 'wish'); checkDup(); });
  $('k-status').addEventListener('change', function () { var s = $('k-status').value;
    if (s === 'building' && !$('f-start').value) $('f-start').value = today();
    if ((s === 'built' || s === 'custom') && !$('f-done').value) $('f-done').value = today(); });
  function checkDup() {
    dupOk = false; saveBtn.textContent = isNew ? '추가' : '저장';
    var d = P.findDups($('f-name').value, $('f-grade').value, isNew ? null : k.id, data.kits);
    if (!d.length) { dupBox.hidden = true; dupBox.innerHTML = ''; return; }
    var wish = d.filter(function (x) { return x.list === 'wish'; })[0];
    dupBox.innerHTML = '<span>이미 같은 프라가 있어요: ' + d.map(function (x) { return '<b>' + esc(x.name) + '</b> (' + esc(gname(x.grade)) + ', ' + (x.list === 'wish' ? '위시리스트' : STLABEL[x.status]) + ')'; }).join(', ') + '</span>' +
      (isNew && wish && $('f-list').value === 'own' ? '<button type="button" class="btn" id="dup-move">위시리스트에 있는 걸 보유로 옮기기</button>' : '');
    dupBox.hidden = false;
    var mvb = dupBox.querySelector('#dup-move'); if (mvb) mvb.addEventListener('click', function () { openForm(wish, { moveToOwn: true }); });
  }
  var dt; $('f-name').addEventListener('input', function () { clearTimeout(dt); dt = setTimeout(checkDup, 250); });
  $('f-grade').addEventListener('change', checkDup);
  if (isNew && k.name) checkDup();
  bindTagSugg(m, $('f-tags'));

  /* 반다이 제품 연결 (저장을 눌러야 반영) */
  function linkItem() { return link ? (link.item || (cat && cat.byId[link.id]) || null) : null; }
  function offList() { var it = linkItem(); return it && !data.settings.hideOfficialPhotos ? it.images : []; }
  function coverFor() { // 공식 사진이 줄어 범위를 벗어났거나 연결이 없으면 대표를 푼다. 카탈로그를 아직 못 읽었으면 그대로 둔다
    var c = work.cover; if (!c || c.indexOf('off:') !== 0) return c;
    if (!link) return null;
    var it = linkItem(); return it && +c.slice(4) >= it.images.length ? null : c;
  }
  function paintLinked() {
    var it = linkItem(), box = $('pk-linked');
    if (!link) { box.innerHTML = '<p class="hint">연결 안 됨 — 연결하면 비어 있는 등급·스케일·시리즈를 채우고 공식 사진이 붙어요.</p>'; return; }
    box.innerHTML = '<div class="linkbox"><span class="lk">연결됨</span><span>' + (it ? esc(it.title) + ' <span class="hint">' + esc([it.grade, it.scale].filter(Boolean).join(' · ')) + '</span>' : '<span class="hint">' + esc(link.id) + (catState === 'ready' ? ' (카탈로그 반영 대기)' : '') + '</span>') +
      '</span><button type="button" class="linkbtn" id="pk-unlink">연결 해제</button></div>';
  }
  function setScaleSel(v) {
    var sel = $('f-scale');
    if (!Array.prototype.some.call(sel.options, function (o) { return o.value === v; })) { var op = document.createElement('option'); op.value = v; op.textContent = v; sel.insertBefore(op, sel.lastElementChild); }
    sel.value = v;
  }
  function applyPick(sel) {
    var cur = { name: $('f-name').value.trim(), grade: $('f-grade').value, scale: $('f-scale').value, series: $('f-series').value.trim(), brand: $('f-brand').value.trim() };
    if ((!link || link.id !== sel.id) && work.cover && work.cover.indexOf('off:') === 0) work.cover = null;
    link = sel;
    var note;
    if (sel.item) {
      var rn = $('pk-rename'), r = C.fillPatch(sel.item, cur, { fillAll: isNew, replaceName: !!(rn && rn.checked) }), p = r.patch;
      if (p.name != null) $('f-name').value = p.name;
      if (p.grade != null) $('f-grade').value = p.grade;
      if (p.scale != null) setScaleSel(p.scale);
      if (p.series != null) $('f-series').value = p.series;
      if (p.brand != null) $('f-brand').value = p.brand;
      note = r.filled.length ? '연결했어요. 채운 항목: ' + r.filled.join(', ') + '.' : '연결했어요. 채울 빈 칸은 없었어요.';
    } else note = '연결만 저장돼요. 이름·등급은 직접 적어 주세요. 다음 수집 때 카탈로그 내용이 채워져요.';
    $('pk-note').textContent = note + ' 저장을 눌러야 반영돼요.';
    paintLinked(); paintPhotos(); checkDup();
  }
  var pkBuilt = false;
  function togglePicker(open) {
    var box = $('pk-box'), btn = $('pk-open');
    if (open == null) open = box.hidden;
    box.hidden = !open; btn.setAttribute('aria-expanded', String(open)); btn.textContent = open ? '찾기 닫기' : '반다이 제품에서 찾기';
    if (open && !pkBuilt) {
      pkBuilt = true;
      var gv = $('f-grade').value;
      box.innerHTML = pickerHTML({ query: $('f-name').value.trim(), grade: gv === '기타' ? 'all' : gv }) +
        (isNew ? '' : '<label class="check"><input type="checkbox" id="pk-rename"><span>고를 때 이름도 카탈로그 이름으로 바꾸기</span></label>') + '<p class="hint" id="pk-note"></p>';
      bindPicker(box, { exceptId: isNew ? null : k.id, getScale: function () { var s = $('f-scale').value; return s === '논스케일' ? null : s; }, onPick: applyPick });
    }
    if (open) { var qi = $('pk-q'); if (qi) qi.focus(); }
  }
  $('pk-open').addEventListener('click', function () { togglePicker(); });
  $('pk-linked').addEventListener('click', function (e) {
    if (!e.target.closest('#pk-unlink')) return;
    link = null; if (work.cover && work.cover.indexOf('off:') === 0) work.cover = null;
    paintLinked(); paintPhotos();
    toast('연결을 풀었어요. 채워 둔 값은 그대로예요. 저장을 눌러야 반영돼요.');
  });
  paintLinked();
  if (link && catState !== 'ready') ensureCatalog().then(function () { if (m.isConnected) { paintLinked(); paintPhotos(); } });
  if (isNew && (!k.name || o.openPicker)) togglePicker(true);

  /* 사진 관리: 추가·순서·대표·삭제는 저장 누를 때 한 커밋으로 */
  var pm = $('pm'), status$ = $('pm-status'), fileIn = $('f-photo');
  function paintPhotos() {
    var offs = offList(), oc = P.photoOrder(work, offs).cover, ck = oc ? oc.key : null, n = work.photos.length;
    var mine = work.photos.map(function (p, i) {
      var isC = ck === 'my:' + p.id;
      return '<div class="pm-item" data-pid="' + esc(p.id) + '" data-key="my:' + esc(p.id) + '"><div class="pm-img"><img src="' + esc(photoSrc(p.thumb)) + '" alt="사진 ' + (i + 1) + '" referrerpolicy="no-referrer" data-g="">' + (isC ? '<span class="pm-badge">대표</span>' : '') + '</div>' +
        '<div class="pm-btns"><button type="button" data-pm="up" aria-label="앞으로 옮기기"' + (i ? '' : ' disabled') + '>←</button><button type="button" data-pm="down" aria-label="뒤로 옮기기"' + (i < n - 1 ? '' : ' disabled') + '>→</button>' +
        '<button type="button" data-pm="cover" aria-pressed="' + isC + '" aria-label="대표 사진으로 지정">대표</button><button type="button" class="del" data-pm="del" aria-label="사진 삭제">삭제</button></div></div>';
    }).join('');
    var official = offs.map(function (u, i) {
      var isC = ck === 'off:' + i, t = C.thumbUrl(u);
      return '<div class="pm-item pm-official" data-key="off:' + i + '"><div class="pm-img"><img src="' + esc(t) + '"' + (t !== u ? ' data-alt="' + esc(u) + '"' : '') + ' alt="공식 사진 ' + (i + 1) + '" loading="lazy" referrerpolicy="no-referrer" data-g="">' +
        '<span class="pm-tag">공식</span>' + (isC ? '<span class="pm-badge">대표</span>' : '') + '</div>' +
        '<div class="pm-btns"><button type="button" data-pm="cover" aria-pressed="' + isC + '" aria-label="공식 사진 ' + (i + 1) + '을 대표 사진으로 지정">대표</button></div></div>';
    }).join('');
    pm.innerHTML = (mine || official) ? mine + official : '<div class="pm-empty">사진 없음</div>';
    var offNote = $('pm-off-note');
    if (offNote) offNote.textContent = link && !offs.length ? (data.settings.hideOfficialPhotos ? '공식 사진 숨기기가 켜져 있어서 공식 사진은 나오지 않아요.' : linkItem() ? '이 제품은 쓸 수 있는 공식 사진이 없어요.' : '') : '';
  }
  paintPhotos();
  pm.addEventListener('click', function (e) {
    var b = e.target.closest('[data-pm]'); if (!b) return;
    var pid = b.closest('.pm-item').dataset.pid, a = b.dataset.pm; // 공식 사진 항목은 pid 없이 data-key(off:n)만 있다
    if (a === 'up') work = P.movePhoto(work, pid, -1);
    else if (a === 'down') work = P.movePhoto(work, pid, 1);
    else if (a === 'cover') work = P.setCover(work, b.closest('.pm-item').dataset.key);
    else if (a === 'del') { work = P.removePhoto(work, pid); if (pend[pid]) { dropPhotoUrls(pend[pid]); delete pend[pid]; } }
    paintPhotos();
  });
  fileIn.addEventListener('change', function () {
    var files = Array.prototype.slice.call(fileIn.files || []); fileIn.value = ''; if (!files.length) return;
    var i = 0, bad = 0;
    (function next() {
      if (i >= files.length) { status$.textContent = bad ? bad + '장은 읽을 수 없는 이미지라 건너뛰었어요.' : '사진을 추가했어요. 저장을 눌러야 저장소에 올라가요.'; return; }
      if (work.photos.length >= P.MAX_PHOTOS) { status$.textContent = '사진은 프라 하나에 ' + P.MAX_PHOTOS + '장까지 올릴 수 있어요.'; return; }
      status$.textContent = '줄이는 중… (' + (i + 1) + '/' + files.length + ')';
      toWebp(files[i++]).then(function (w) {
        var ph = registerPhoto(kitId, w); pend[ph.id] = { full: w.full, thumbBlob: w.thumb, src: ph.src, thumb: ph.thumb };
        work = P.addPhotos(work, [ph]); paintPhotos();
      }, function () { bad++; }).then(next);
    })();
  });

  saveBtn.addEventListener('click', function () {
    var v = function (id) { return $(id).value.trim(); };
    var name = v('f-name'); if (!name) { toast('이름을 입력해 주세요.'); $('f-name').focus(); return; }
    if (isNew && !dupBox.hidden && !dupOk) { dupOk = true; saveBtn.textContent = '그래도 추가'; toast('같은 프라가 이미 있어요. 그래도 추가하려면 한 번 더 눌러 주세요.'); return; }
    var lst = v('f-list'), own = lst === 'own';
    var rec = Object.assign({}, isNew ? {} : k, { id: kitId, created: isNew ? new Date().toISOString() : (k.created || ''), list: lst, name: name, grade: v('f-grade'), scale: v('f-scale'), series: v('f-series'), brand: v('f-brand'),
      status: own ? v('k-status') : 'unbuilt', date: own ? v('f-date') : '', shop: own ? v('f-shop') : '', price: Number(v('f-price').replace(/[^0-9]/g, '')) || 0,
      startDate: own ? v('f-start') : '', doneDate: own ? v('f-done') : '', tags: splitTags(v('f-tags')), memo: $('f-memo').value.trim(),
      photos: work.photos, cover: coverFor(), catalogId: link ? link.id : null });
    var files = {}; work.photos.forEach(function (p) { var pd = pend[p.id]; if (pd) { files['docs/' + p.src] = pd.full; files['docs/' + p.thumb] = pd.thumbBlob; } });
    var kind = move ? 'move' : isNew ? 'add' : 'edit';
    savedFlag = true;
    commit(function (d) {
      if (isNew) d.kits.push(P.normKit(P.clone(rec))); else d.kits = d.kits.map(function (x) { return x.id === rec.id ? P.normKit(P.clone(rec)) : x; });
    }, kind, { name: name }, { files: files, okMsg: move ? '"' + name + '"을(를) 보유 목록으로 옮겼어요.' : isNew ? '"' + name + '"을(를) 추가했어요.' : '"' + name + '"을(를) 저장했어요.' })
      .then(function (ok) { if (!ok) savedFlag = false; });
  });
}

/* ---------- bulk edit ---------- */
function openBulk() {
  var ids = Array.from(sel), n = ids.length, KEEP = P.BULK_KEEP;
  var body = '<p class="hint" style="font-size:14px">선택한 <b>' + n + '개</b>에 한꺼번에 적용해요. 비워 두거나 "그대로"인 항목은 바뀌지 않아요.</p>' +
   '<form class="form" id="bulk-form" novalidate>' +
   '<div class="field"><label for="b-list">목록</label><select id="b-list">' + opt(KEEP, '그대로', '') + opt('own', '보유', '') + opt('wish', '위시리스트', '') + '</select></div>' +
   '<div class="field"><label for="b-status">상태</label><select id="b-status">' + opt(KEEP, '그대로', '') + STATUSES.map(function (s) { return opt(s.k, s.l, ''); }).join('') + '</select></div>' +
   '<div class="field"><label for="b-grade">등급</label><select id="b-grade">' + opt(KEEP, '그대로', '') + GRADES.map(function (g) { return opt(g, g, ''); }).join('') + '</select></div>' +
   '<div class="field"><label for="b-scale">스케일</label><select id="b-scale">' + opt(KEEP, '그대로', '') + SCALES.map(function (s) { return opt(s, s, ''); }).join('') + '</select></div>' +
   '<div class="field"><label for="b-series">시리즈·작품</label><input id="b-series"></div>' +
   '<div class="field"><label for="b-brand">브랜드</label><input id="b-brand"></div>' +
   '<p class="sect">구매 정보 · 조립 기록</p>' +
   '<div class="field"><label for="b-date">구매일</label><input id="b-date" type="date"></div>' +
   '<div class="field"><label for="b-price">가격 (원, 각각)</label><input id="b-price" inputmode="numeric"></div>' +
   '<div class="field full"><label for="b-shop">구매처</label><input id="b-shop"></div>' +
   '<div class="field"><label for="b-start">조립 시작일</label><input id="b-start" type="date"></div>' +
   '<div class="field"><label for="b-done">완성일</label><input id="b-done" type="date"></div>' +
   '<label class="check full"><input type="checkbox" id="b-onlyempty" checked><span>값이 비어 있는 항목에만 채우기<br><span class="hint">끄면 이미 적어 둔 값도 덮어써요. 목록·상태·등급·스케일은 항상 바뀌어요.</span></span></label>' +
   '<p class="sect">태그</p>' +
   '<div class="field full"><label for="b-tagadd">태그 붙이기</label><input id="b-tagadd" placeholder="예: P-반다이">' + suggHTML() + '</div>' +
   '<div class="field full"><label for="b-tagdel">태그 떼기</label><input id="b-tagdel" placeholder="뗄 태그를 쉼표로 구분"></div>' +
   '</form>';
  var foot = '<button class="btn danger" id="b-del">' + n + '개 삭제</button><div class="r"><button class="btn" data-close>취소</button><button class="btn primary" id="b-apply">' + n + '개에 적용</button></div>';
  var m = openModal('일괄 수정', body, foot);
  var $ = function (id) { return m.querySelector('#' + id); };
  bindTagSugg(m, $('b-tagadd'));
  var del = $('b-del');
  del.addEventListener('click', function () {
    if (!del.classList.contains('armed')) { del.classList.add('armed'); del.textContent = '한 번 더 누르면 ' + n + '개 삭제'; return; }
    var set = {}; ids.forEach(function (i) { set[i] = 1; });
    commit(function (d) { d.kits = d.kits.filter(function (x) { return !set[x.id]; }); }, 'bulk-delete', { n: n }, { okMsg: n + '개를 삭제했어요.' });
  });
  $('b-apply').addEventListener('click', function () {
    var v = function (id) { return $(id).value.trim(); }, onlyEmpty = $('b-onlyempty').checked;
    var sets = { list: v('b-list'), status: v('b-status'), grade: v('b-grade'), scale: v('b-scale') };
    var fills = { series: v('b-series'), brand: v('b-brand'), date: v('b-date'), shop: v('b-shop'), startDate: v('b-start'), doneDate: v('b-done') };
    var price = Number(v('b-price').replace(/[^0-9]/g, '')) || 0, add = splitTags(v('b-tagadd')), rem = splitTags(v('b-tagdel'));
    var any = Object.keys(sets).some(function (f) { return sets[f] !== KEEP; }) || Object.keys(fills).some(function (f) { return fills[f]; }) || price || add.length || rem.length;
    if (!any) { toast('바꿀 항목을 하나 이상 입력해 주세요.'); return; }
    commit(function (d) { P.applyBulk(d.kits, ids, { sets: sets, fills: fills, price: price, add: add, rem: rem, onlyEmpty: onlyEmpty }); }, 'bulk-edit', { n: n }, { okMsg: n + '개를 수정했어요.' });
  });
}

/* ---------- 설정 (이름·구매정보 숨김 + GitHub 토큰) ---------- */
function openSettings() {
  var hasToken = !!getToken();
  var tokenStatus = canWrite ? '<span class="status-ok">소유자 모드</span> · 이 브라우저에 토큰이 저장돼 있어요.' : hasToken ? '토큰이 저장돼 있지만 소유자로 확인되지 않았어요. 다시 연결해 보세요.' : '토큰이 없어요 (방문자 모드).';
  var body = (canWrite ? '<div class="settings-sec"><div class="field"><label for="s-name">컬렉션 이름</label><input id="s-name" value="' + esc(data.settings.name) + '"></div>' +
     '<label class="check"><input type="checkbox" id="s-hide"' + (data.settings.hidePurchase ? ' checked' : '') + '><span>방문자 화면에서 구매일·구매처·가격 숨기기<br><span class="hint">화면에서만 숨겨요. 저장소가 공개라서 data/collection.json에는 그대로 보여요. 꼭 비공개여야 하는 정보는 적지 마세요.</span></span></label>' +
     '<label class="check"><input type="checkbox" id="s-offhide"' + (data.settings.hideOfficialPhotos ? ' checked' : '') + '><span>공식 사진 숨기기<br><span class="hint">반다이 제품과 연결된 프라에 공식 사진을 붙이지 않아요. 내가 올린 사진만 나와요.</span></span></label></div>' : '') +
   (canWrite ? '<div class="settings-sec"><h3>반다이 제품 연결</h3><p class="hint">이름·등급·스케일이 카탈로그와 똑같은 프라를 한꺼번에 연결해 줘요. 확인한 것만 한 번에 저장해요.</p><div class="row-btns"><button class="btn" id="s-auto">자동 연결 후보 보기</button><button class="btn" id="s-assist">연결 도우미 시작</button></div></div>' : '') +
   '<div class="settings-sec"><h3>GITHUB 토큰</h3><p id="s-tstatus" style="font-size:14px">' + tokenStatus + '</p>' +
     '<div class="field"><label for="s-token">fine-grained 토큰</label><input id="s-token" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="' + (canWrite ? '다른 토큰으로 바꾸려면 붙여넣기' : 'github_pat_…') + '"></div>' +
     '<p class="hint">이 저장소(' + esc(REPO) + ')만, Contents: Read and write 권한으로 만든 토큰이어야 해요. 토큰은 이 브라우저에만 저장되고 화면에 다시 보여주지 않아요. 공용 PC에서는 쓰지 마세요.</p>' +
     '<div class="row-btns"><button class="btn primary" id="s-connect">연결</button>' + (hasToken ? '<button class="btn danger" id="s-forget">토큰 지우기</button>' : '') + '</div></div>';
  var foot = '<div class="r"><button class="btn" data-close>' + (canWrite ? '취소' : '닫기') + '</button>' + (canWrite ? '<button class="btn primary" id="s-save">저장</button>' : '') + '</div>';
  var m = openModal('설정', body, foot);
  var $ = function (id) { return m.querySelector('#' + id); };
  $('s-connect').addEventListener('click', function () {
    var inp = $('s-token'), t = inp.value.trim(); inp.value = '';
    if (!t) { toast('토큰을 붙여넣어 주세요.'); return; }
    var btn = $('s-connect'); btn.disabled = true; btn.textContent = '확인 중…';
    connectOwner(t).then(function (r) {
      if (!r.ok) { btn.disabled = false; btn.textContent = '연결'; toast(connectFailMsg(r.reason)); return; }
      var persisted = storeToken(t);
      loading = false; sel = null; closeModal(); renderAll();
      toast('소유자 모드로 연결했어요. 저장할 때 토큰 권한을 한 번 더 확인해요.' + (persisted ? '' : ' (이 브라우저는 토큰을 저장하지 못해 이번 방문 동안만 유지돼요.)'));
    });
  });
  var sa = $('s-auto'); if (sa) sa.addEventListener('click', openAutoLink);
  var sas = $('s-assist'); if (sas) sas.addEventListener('click', function () { openAssist(); });
  var fg = $('s-forget');
  if (fg) fg.addEventListener('click', function () {
    clearToken(); store = null; canWrite = false; sel = null;
    loadVisitor().then(function () { closeModal(); renderAll(); toast('토큰을 지웠어요. 방문자 모드로 돌아왔어요.'); });
  });
  var sv = $('s-save');
  if (sv) sv.addEventListener('click', function () {
    var nm = $('s-name').value.trim() || '프라 격납고', hide = $('s-hide').checked, offHide = $('s-offhide').checked;
    commit(function (d) { d.settings.name = nm; d.settings.hidePurchase = hide; d.settings.hideOfficialPhotos = offHide; }, 'settings', {}, { okMsg: '설정을 저장했어요.' });
  });
}

/* ---------- excel ---------- */
function loadXLSX() {
  if (window.XLSX) return Promise.resolve(window.XLSX);
  return new Promise(function (res, rej) {
    var s = document.createElement('script'); s.src = XLSX_SRC.url; s.integrity = XLSX_SRC.integrity; s.crossOrigin = 'anonymous';
    s.onload = function () { window.XLSX ? res(window.XLSX) : rej(new Error('xlsx')); }; s.onerror = function () { rej(new Error('xlsx')); };
    document.head.appendChild(s);
  });
}
function downloadBlob(filename, blob) {
  var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
}
function exportXlsx() {
  if (!data.kits.length) { toast('아직 백업할 프라가 없어요.'); return; }
  var rows = P.exportRows(data.kits);
  var d = new Date(), stamp = d.getFullYear() + ('0' + (d.getMonth() + 1)).slice(-2) + ('0' + d.getDate()).slice(-2);
  toast('엑셀 파일을 만드는 중이에요.');
  loadXLSX().then(function (X) {
    var ws = X.utils.aoa_to_sheet(rows); ws['!cols'] = P.COLS.map(function (c) { return { wch: c[0] === 'name' || c[0] === 'memo' ? 30 : c[0] === 'series' ? 22 : 12 }; });
    var wb = X.utils.book_new(); X.utils.book_append_sheet(wb, ws, '프라 목록');
    var buf = X.write(wb, { type: 'array', bookType: 'xlsx' });
    downloadBlob('프라격납고_' + stamp + '.xlsx', new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
    toast('엑셀 백업을 내려받았어요.');
  }, function () { toast('엑셀 도구를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.'); });
}

/* ---------- import (엑셀·CSV·붙여넣기, v2 데이터 JSON) ---------- */
function openImport() {
  var parsed = null, dups = [];
  var body = '<p class="hint" style="font-size:14px">엑셀 파일(.xlsx)이나 CSV를 고르거나, 엑셀에서 표를 복사해 아래 칸에 붙여넣어 주세요. 첫 줄에 <b>이름, 등급, 스케일, 시리즈, 상태, 구매일, 구매처, 가격, 태그, 메모</b> 같은 제목이 있으면 자동으로 맞춰요. "엑셀 백업"으로 받은 파일도 그대로 가져올 수 있어요. 이전 버전(v2)의 데이터 JSON(사진 포함)도 가져올 수 있어요.</p>' +
   '<div class="field"><label for="i-file">파일</label><input id="i-file" type="file" accept=".xlsx,.xls,.csv,.tsv,.txt,.json"></div>' +
   '<div class="field"><label for="i-text">붙여넣기</label><textarea id="i-text" placeholder="이름&#9;등급&#9;상태&#10;건담 에어리얼&#9;HG&#9;완성"></textarea></div>' +
   '<div id="i-prev"></div>';
  var foot = '<div class="r"><button class="btn" data-close>취소</button><button class="btn primary" id="i-go" disabled>가져오기</button></div>';
  var m = openModal('엑셀·CSV 가져오기', body, foot);
  var prev = m.querySelector('#i-prev'), go = m.querySelector('#i-go'), ta = m.querySelector('#i-text');
  var count = function () { var skip = m.querySelector('#i-skip'); var n = parsed.kits.length - (skip && skip.checked ? dups.length : 0); go.disabled = !n; go.textContent = n + '개 가져오기'; };
  var show = function (res) {
    parsed = res;
    if (!parsed.kits.length) { prev.innerHTML = '<p class="hint">이름이 있는 행을 찾지 못했어요. 첫 줄 제목에 "이름"이 있는지 확인해 주세요.</p>'; go.disabled = true; go.textContent = '가져오기'; return; }
    var seen = data.kits.slice(); dups = [];
    parsed.kits.forEach(function (k) { if (P.findDups(k.name, k.grade, null, seen).length) dups.push(k.id); seen.push(k); });
    var nPhoto = Object.keys(parsed.legacy || {}).length;
    prev.innerHTML = '<p class="hint">' + parsed.kits.length + '개를 찾았어요' + (parsed.skipped ? ' (이름 없는 ' + parsed.skipped + '행 제외)' : '') + (nPhoto ? ' · 사진 ' + nPhoto + '장은 WebP 파일로 바꿔 올려요' : '') + '. 앞의 8개 미리보기:</p>' +
     '<div class="tbl-wrap"><table class="prev"><thead><tr><th>목록</th><th>이름</th><th>등급</th><th>스케일</th><th>상태</th><th>구매일</th><th>가격</th><th>태그</th></tr></thead><tbody>' +
     parsed.kits.slice(0, 8).map(function (k) { return '<tr><td>' + (k.list === 'wish' ? '위시' : '보유') + '</td><td>' + esc(k.name) + (dups.indexOf(k.id) >= 0 ? ' <b>(중복)</b>' : '') + '</td><td>' + esc(k.grade) + '</td><td>' + esc(k.scale) + '</td><td>' + (k.list === 'wish' ? '' : STLABEL[k.status]) + '</td><td class="mono">' + esc(k.date) + '</td><td class="mono">' + (k.price ? won(k.price) : '') + '</td><td>' + esc(k.tags.join(', ')) + '</td></tr>'; }).join('') +
     '</tbody></table></div>' +
     (dups.length ? '<label class="check"><input type="checkbox" id="i-skip" checked><span>이미 있는 것과 겹치는 ' + dups.length + '개는 건너뛰기</span></label>' : '');
    var sk = m.querySelector('#i-skip'); if (sk) sk.addEventListener('change', count);
    count();
  };
  var showText = function (t) {
    if (/^\s*[\[{]/.test(t) || /id=["']kit-data["']/.test(t)) {
      try { var r = P.parseV2Json(t); show({ kits: r.kits, skipped: 0, legacy: r.legacy }); }
      catch (e) { prev.innerHTML = '<p class="hint">v2 데이터(JSON)로 읽지 못했어요.</p>'; go.disabled = true; go.textContent = '가져오기'; }
    } else show(Object.assign(P.rowsToKits(P.parseDelimited(t)), { legacy: {} }));
  };
  ta.addEventListener('input', function () { if (ta.value.trim()) showText(ta.value); else { prev.innerHTML = ''; go.disabled = true; } });
  m.querySelector('#i-file').addEventListener('change', function (e) {
    var f = e.target.files && e.target.files[0]; if (!f) return; prev.innerHTML = '<p class="hint">읽는 중…</p>';
    if (/\.(xlsx|xls)$/i.test(f.name)) {
      Promise.all([loadXLSX(), f.arrayBuffer()]).then(function (r) {
        var wb = r[0].read(r[1], { type: 'array', cellDates: true }); var ws = wb.Sheets[wb.SheetNames[0]];
        show(Object.assign(P.rowsToKits(r[0].utils.sheet_to_json(ws, { header: 1, raw: false, dateNF: 'yyyy-mm-dd', defval: '' })), { legacy: {} }));
      }).catch(function () { prev.innerHTML = '<p class="hint">엑셀 파일을 읽지 못했어요. 엑셀에서 표를 복사해 붙여넣거나 CSV로 저장해서 올려 주세요.</p>'; });
    } else f.text().then(showText);
  });
  go.addEventListener('click', function () {
    if (!parsed || !parsed.kits.length) return; var sk = m.querySelector('#i-skip'), skip = sk && sk.checked;
    var picked = parsed.kits.filter(function (k) { return !(skip && dups.indexOf(k.id) >= 0); }); if (!picked.length) return;
    go.disabled = true;
    var files = {}, legacy = parsed.legacy || {}, todo = [];
    var add = picked.map(function (k, i) { var nk = P.clone(k), old = k.id; nk.id = uid() + i; nk.photos = []; nk.cover = null; if (legacy[old]) todo.push({ kit: nk, uri: legacy[old] }); return nk; });
    var done = 0, failed = 0;
    (function next() {
      if (done >= todo.length) {
        if (failed) toast('사진 ' + failed + '장은 변환하지 못해 건너뛰었어요.');
        commit(function (d) { d.kits = d.kits.concat(add); }, 'import', { n: add.length }, { files: files, okMsg: add.length + '개를 가져왔어요.' }).then(function (ok) { if (!ok) { go.disabled = false; } });
        return;
      }
      var t = todo[done++]; go.textContent = '사진 변환 중 (' + done + '/' + todo.length + ')';
      var raw = P.dataUriToBytes(t.uri);
      (raw ? toWebp(new Blob([raw.bytes], { type: raw.type })) : Promise.reject()).then(function (w) {
        var ph = registerPhoto(t.kit.id, w); t.kit.photos = [ph]; files['docs/' + ph.src] = w.full; files['docs/' + ph.thumb] = w.thumb;
      }, function () { failed++; }).then(next);
    })();
  });
}

/* ---------- 신제품·입고 탭 (feed.js) ---------- */
var feedView = FD.createView({
  esc: esc, getKits: function () { return data.kits; }, getCat: function () { return cat; }, ensureCatalog: ensureCatalog, canWrite: function () { return canWrite && !!store; }, today: today,
  fetchJson: function (u) { return window.fetch(u).then(function (r) { if (!r.ok) throw new Error('http'); return r.json(); }); },
  onWish: function (row, w) { openForm(null, { prefill: w.prefill, openPicker: w.openPicker }); }
});

/* ---------- boot ---------- */
renderAll();
var token = getToken();
(token ? connectOwner(token) : Promise.resolve({ ok: false, reason: 'none' })).then(function (r) {
  if (r.ok) return null;
  if (r.reason !== 'none') toast(connectFailMsg(r.reason) + (r.reason === 'nopush' ? '' : ' 보기 전용으로 열었어요.'));
  return loadVisitor();
}).then(function () { loading = false; renderAll(); });
})();
