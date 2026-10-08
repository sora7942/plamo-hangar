/* 프라 격납고 — 신제품·입고 탭. feed.json(크롤러가 씀)을 읽기만 한다.
   순수 함수(정규화·필터·정렬·문구)는 DOM 없이 계산하고, createView 가 그리기·이벤트를 맡는다.
   브라우저에서는 window.PlamoFeed, node에서는 require()로 쓴다 (tests/site_feed.test.mjs). */
(function (root, factory) {
  var node = typeof module === 'object' && module.exports;
  var P = node ? require('./pure.js') : root.PlamoPure, C = node ? require('./catalog.js') : root.PlamoCatalog;
  if (node) module.exports = factory(P, C);
  else root.PlamoFeed = factory(P, C);
})(typeof self !== 'undefined' ? self : this, function (P, C) {
'use strict';

var TYPES = [{ k: 'new', l: '신제품' }, { k: 'pb-new', l: 'P-반다이 한정' }, { k: 'kr-restock', l: '국내 재입고' }, { k: 'kr-new', l: '국내 신규' }];
var TYPE_LABEL = {}; TYPES.forEach(function (t) { TYPE_LABEL[t.k] = t.l; });
var TYPE_PRIO = { 'kr-restock': 0, 'kr-new': 1, 'pb-new': 2, 'new': 3 }; // 같은 시각에 발견된 항목의 순서 (디스코드와 같은 순서)
var LINES = [{ k: 'gunpla', l: '건프라' }, { k: 'girl', l: '걸프라' }];
var LINK_HOSTS = ['bandai-hobby.net', 'p-bandai.jp', 'www.joyhobby.co.kr'];
var PAGE = 60, FRESH_DAYS = 3;

/* ---------- 읽기·정규화 ---------- */
function str(v) { return typeof v === 'string' && v ? v : null; }
function normalize(json) {
  var arr = json && Array.isArray(json.items) ? json.items : [], seen = {};
  return arr.filter(function (x) {
    if (!x || typeof x !== 'object' || typeof x.id !== 'string' || !x.id || seen[x.id] || !TYPE_LABEL[x.type]) return false;
    seen[x.id] = 1; return true;
  }).map(function (x) {
    var cid = typeof x.catalogId === 'string' && /^(bh|pb)-[A-Za-z0-9_-]{1,60}$/.test(x.catalogId) ? x.catalogId : null;
    return { id: x.id, type: x.type, date: str(x.date) || '', added: str(x.added) || '', catalogId: cid, title: str(x.title) || '', titleKo: str(x.titleKo), url: str(x.url), source: str(x.source) };
  });
}
// 링크는 공식 사이트·조이하비 https 주소만 (feed.json 이 이상한 값을 가져도 링크로 만들지 않는다)
function safeLink(u) {
  try { var p = new URL(String(u)); return p.protocol === 'https:' && LINK_HOSTS.indexOf(p.hostname) >= 0 ? p.href : null; } catch (e) { return null; }
}

/* ---------- 행 만들기·필터·정렬 ---------- */
// 내 프라: 같은 catalogId 를 가진 보유·위시 (연결 안 된 항목은 내 프라인지 알 수 없다)
function build(items, kits, cat) {
  var mine = {};
  (kits || []).forEach(function (k) { if (k.catalogId) (mine[k.catalogId] = mine[k.catalogId] || []).push(k); });
  return items.map(function (it) {
    var ci = cat && it.catalogId ? (cat.byId[it.catalogId] || null) : null;
    return { item: it, cat: ci, mine: it.catalogId && mine[it.catalogId] ? mine[it.catalogId] : [],
      title: it.titleKo || (ci && ci.title) || it.title, grade: ci ? ci.grade : null, line: ci ? ci.line : null };
  });
}
function filterRows(rows, f, skip) {
  f = f || {};
  return rows.filter(function (r) {
    if (skip !== 'type' && f.type && f.type !== 'all' && r.item.type !== f.type) return false;
    if (skip !== 'line' && f.line && f.line !== 'all' && r.line !== f.line) return false;
    if (skip !== 'grade' && f.grade && f.grade !== 'all' && r.grade !== f.grade) return false;
    if (skip !== 'mine' && f.mine && !r.mine.length) return false;
    return true;
  });
}
// 내 프라가 맨 위. 그다음 발견 시각 최신순 → (같은 시각이면) 국내 입고 → P-반다이 → 신제품 → 날짜 → id
function sortRows(rows) {
  var cmp = function (a, b) { return a < b ? 1 : a > b ? -1 : 0; };
  return rows.slice().sort(function (a, b) {
    return (b.mine.length ? 1 : 0) - (a.mine.length ? 1 : 0) || cmp(a.item.added, b.item.added) ||
      (TYPE_PRIO[a.item.type] - TYPE_PRIO[b.item.type]) || cmp(a.item.date, b.item.date) || (a.item.id < b.item.id ? -1 : 1);
  });
}
function gradeOptions(rows) {
  var n = {}; rows.forEach(function (r) { if (r.grade) n[r.grade] = (n[r.grade] || 0) + 1; });
  return P.GRADES.filter(function (g) { return n[g]; }).map(function (g) { return { k: g, n: n[g] }; });
}

/* ---------- 문구 ---------- */
function isFresh(item, today) {
  var a = C.dayNum(String(item.added || '').slice(0, 10)), t = C.dayNum(today);
  return a !== null && t !== null && t - a <= FRESH_DAYS && t - a >= 0;
}
function dateText(item, today) {
  var d = item.date; if (!d) return '';
  var future = C.dayNum(d) !== null ? C.dayNum(d) > C.dayNum(today) : (/^\d{4}-\d{2}$/.test(d) && C.dayNum(d + '-01') > C.dayNum(today));
  if (item.type === 'new') return (future ? '일본 발매 예정 ' : '일본 발매 ') + d;
  if (item.type === 'pb-new') return (future ? 'P-반다이 발매 예정 ' : 'P-반다이 발매 ') + d;
  return (future ? '국내 입고 예정 ' : '국내 입고 ') + d;
}
function mineText(row) {
  var own = row.mine.some(function (k) { return k.list === 'own'; }), wish = row.mine.some(function (k) { return k.list === 'wish'; });
  return '내 프라 · ' + (own && wish ? '보유·위시' : own ? '보유' : '위시');
}
// 위시리스트에 추가할 때 폼에 미리 채울 값. 카탈로그에 연결된 항목은 catalogId 와 함께, 아닌 항목은 이름만(찾기로 직접 연결)
function wishPrefill(row) {
  var ci = row.cat;
  if (ci) return { prefill: { list: 'wish', catalogId: ci.id, name: ci.title, grade: ci.grade, scale: ci.scale || '논스케일', series: ci.series || '', brand: '반다이', date: '' }, openPicker: false };
  var name = row.item.titleKo || row.item.title, g = P.normGrade('', name);
  return { prefill: { list: 'wish', name: name, grade: g, scale: P.normScale('', g), series: '', brand: '반다이', date: '' }, openPicker: true };
}

/* ---------- 화면 ---------- */
// deps: {esc, getKits(), getCat(), ensureCatalog(), fetchJson(url), canWrite(), today(), onWish(row)}
function createView(deps) {
  var esc = deps.esc;
  var st = { status: 'idle', items: [], f: { type: 'all', line: 'all', grade: 'all', mine: false }, limit: PAGE, root: null };

  function all() { return build(st.items, deps.getKits(), deps.getCat()); }
  function load() {
    st.status = 'loading'; draw();
    return deps.ensureCatalog().then(function (cat) {
      return deps.fetchJson('data/feed.json?v=' + encodeURIComponent(C.cacheKey({ updatedAt: cat && cat.updatedAt })));
    }).then(function (json) { st.items = normalize(json); st.status = 'ready'; draw(); }, function () { st.status = 'error'; draw(); });
  }
  function chip(group, val, label, n, on) {
    return '<button type="button" class="chip" data-fk="' + group + '" data-fv="' + esc(val) + '" aria-pressed="' + on + '">' + esc(label) + (n == null ? '' : '<span class="n">' + n + '</span>') + '</button>';
  }
  function thumb(r) {
    var im = r.cat && r.cat.images[0], g = r.grade ? P.glabel(r.grade) : '';
    if (!im) return '<div class="ghost">' + esc(g || '–') + '</div>';
    var t = C.thumbUrl(im);
    return '<img src="' + esc(t) + '"' + (t !== im ? ' data-alt="' + esc(im) + '"' : '') + ' alt="" loading="lazy" referrerpolicy="no-referrer" data-g="' + esc(g || '–') + '">';
  }
  function itemHTML(r, today) {
    var it = r.item, link = safeLink(it.url), meta = [r.grade, r.cat && r.cat.scale, dateText(it, today)].filter(Boolean).join(' · ');
    var title = link ? '<a class="fd-title" href="' + esc(link) + '" target="_blank" rel="noopener noreferrer">' + esc(r.title) + '</a>' : '<span class="fd-title">' + esc(r.title) + '</span>';
    return '<article class="fd-item' + (r.mine.length ? ' mine' : '') + '" data-id="' + esc(it.id) + '"><div class="fd-thumb">' + thumb(r) + '</div><div class="fd-body">' +
      '<div class="fd-tags"><span class="fd-type t-' + esc(it.type) + '">' + esc(TYPE_LABEL[it.type]) + '</span>' + (r.mine.length ? '<span class="fd-mine">' + esc(mineText(r)) + '</span>' : '') +
      (isFresh(it, today) ? '<span class="fd-new">NEW</span>' : '') + '</div>' + title +
      '<span class="hint">' + esc(meta) + '</span>' +
      (!r.cat ? '<span class="hint">반다이 제품과 연결되지 않은 입고 글이에요.</span>' : '') + '</div>' +
      (deps.canWrite() && !r.mine.length ? '<div class="fd-act"><button type="button" class="btn" data-wish="' + esc(it.id) + '">위시리스트에 추가</button></div>' : '') + '</article>';
  }
  function html() {
    if (st.status === 'idle' || st.status === 'loading') return '<p class="count-line">신제품·입고 소식을 불러오는 중이에요.</p>';
    if (st.status === 'error') return '<p class="count-line">소식을 불러오지 못했어요. <button type="button" class="linkbtn" data-retry>다시 시도</button></p>';
    var today = deps.today(), rows = all(), f = st.f;
    if (f.grade !== 'all' && !gradeOptions(rows).some(function (g) { return g.k === f.grade; })) f.grade = 'all';
    var shown = sortRows(filterRows(rows, f)), page = shown.slice(0, st.limit);
    var typeRows = filterRows(rows, f, 'type'), lineRows = filterRows(rows, f, 'line'), gradeRows = filterRows(rows, f, 'grade'), mineRows = filterRows(rows, f, 'mine');
    var cnt = function (list, test) { return list.filter(test).length; };
    var nMine = mineRows.filter(function (r) { return r.mine.length; }).length, cat = deps.getCat();
    var out = '<section class="controls fd-controls" aria-label="필터">' +
      '<div class="chips"><span class="chip-label">종류</span>' + chip('type', 'all', '전체', typeRows.length, f.type === 'all') +
        TYPES.map(function (t) { return chip('type', t.k, t.l, cnt(typeRows, function (r) { return r.item.type === t.k; }), f.type === t.k); }).join('') + '</div>' +
      '<div class="chips"><span class="chip-label">라인</span>' + chip('line', 'all', '전체', null, f.line === 'all') +
        LINES.map(function (l) { return chip('line', l.k, l.l, cnt(lineRows, function (r) { return r.line === l.k; }), f.line === l.k); }).join('') + '</div>' +
      '<div class="chips"><span class="chip-label">등급</span>' + chip('grade', 'all', '전체', null, f.grade === 'all') +
        gradeOptions(gradeRows).map(function (g) { return chip('grade', g.k, g.k, g.n, f.grade === g.k); }).join('') + '</div>' +
      '<div class="chips"><button type="button" class="chip tag" data-fk="mine" data-fv="toggle" aria-pressed="' + !!f.mine + '">내 프라만<span class="n">' + nMine + '</span></button></div></section>';
    if (!cat) out += '<div class="banner">카탈로그를 불러오지 못해 사진·등급·내 프라 표시가 빠져 있어요.</div>';
    out += '<p class="count-line">' + shown.length + '개 표시 중 · 새로 발견한 순서 (내 프라가 맨 위)</p>';
    out += shown.length ? '<div class="fd-list">' + page.map(function (r) { return itemHTML(r, today); }).join('') + '</div>' : '<div class="empty">조건에 맞는 소식이 없어요. 필터를 바꿔 보세요.</div>';
    if (shown.length > page.length) out += '<div class="fd-more"><button type="button" class="btn" data-more>더 보기 (' + (shown.length - page.length) + '개 남음)</button></div>';
    return out;
  }
  function draw() { if (st.root && st.root.isConnected) st.root.innerHTML = html(); }
  function onClick(e) {
    var b = e.target.closest('[data-fk],[data-wish],[data-more],[data-retry]'); if (!b) return;
    if (b.dataset.retry !== undefined) { load(); return; }
    if (b.dataset.more !== undefined) { st.limit += PAGE; draw(); return; }
    if (b.dataset.wish) {
      var row = all().filter(function (r) { return r.item.id === b.dataset.wish; })[0];
      if (row) deps.onWish(row, wishPrefill(row));
      return;
    }
    if (b.dataset.fk === 'mine') st.f.mine = !st.f.mine; else st.f[b.dataset.fk] = b.dataset.fv;
    st.limit = PAGE; draw();
  }
  return {
    // 탭이 그려질 때마다 새 root 로 부른다. 읽어 둔 소식은 다시 받지 않는다
    mount: function (el) {
      st.root = el; el.addEventListener('click', onClick);
      if (st.status === 'idle' || st.status === 'error') load(); else draw();
    },
    state: st
  };
}

return {
  TYPES: TYPES, LINES: LINES, PAGE: PAGE, normalize: normalize, safeLink: safeLink, build: build, filterRows: filterRows, sortRows: sortRows, gradeOptions: gradeOptions,
  isFresh: isFresh, dateText: dateText, mineText: mineText, wishPrefill: wishPrefill, createView: createView
};
});
