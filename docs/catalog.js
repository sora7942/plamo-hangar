/* 프라 격납고 — 카탈로그(크롤러가 만든 catalog-*.json) 순수 로직.
   검색·URL 파싱·채우기·공식 사진은 DOM 없이 계산하고, 읽기(load)만 fetch 함수를 받아 쓴다.
   브라우저에서는 window.PlamoCatalog, node에서는 require()로 쓴다 (tests/site_catalog.test.mjs). */
(function (root, factory) {
  var P = (typeof module === 'object' && module.exports) ? require('./pure.js') : root.PlamoPure;
  if (typeof module === 'object' && module.exports) module.exports = factory(P);
  else root.PlamoCatalog = factory(P);
})(typeof self !== 'undefined' ? self : this, function (P) {
'use strict';

var FILES = ['catalog-gunpla.json', 'catalog-girl.json'];
var SEARCH_LIMIT = 30;
var AKAMAI = 'bandai-a.akamaihd.net', HOBBY = 'bandai-hobby.net';

/* ---------- 문자열 ---------- */
// 검색용: NFKC(전각·반각 통일) + 소문자 + 글자·숫자만 남긴다 ("건담 에어리얼"="건담에어리얼", "ＨＧ"="hg")
function norm(s) { return String(s == null ? '' : s).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''); }

// "HG 1/144 건담 에어리얼" → "건담 에어리얼" (내 프라 이름은 보통 등급·스케일 없이 적는다)
function stripPrefix(name, grade, scale) {
  var s = String(name == null ? '' : name).trim();
  if (grade) {
    var g = String(grade);
    if (s.slice(0, g.length).toLowerCase() === g.toLowerCase() && /^\s/.test(s.slice(g.length) + ' ')) s = s.slice(g.length).trim();
  }
  if (scale) {
    var c = String(scale);
    if (s.slice(0, c.length) === c && /^\s/.test(s.slice(c.length) + ' ')) s = s.slice(c.length).trim();
  }
  return s;
}
function displayName(item) {
  var base = item.nameKo || item.nameJa || '';
  return stripPrefix(base, item.grade, item.scale) || base;
}

/* ---------- 공식 이미지 (안정 URL만) ---------- */
function parseUrl(u) { try { return new URL(String(u)); } catch (e) { return null; } }
function isStableImage(u) {
  var p = parseUrl(u);
  if (!p || p.protocol !== 'https:' || /expires=/i.test(p.search)) return false;
  return p.hostname === AKAMAI || (p.hostname === HOBBY && p.pathname.indexOf('/images/') === 0);
}
// 카드·썸네일용 작은 이미지. akamai의 /model/xl/ 은 /model/m/ 으로 (약 12KB ↔ 187KB). 없으면 원본
function thumbUrl(u) {
  var p = parseUrl(u);
  if (!p || p.hostname !== AKAMAI || p.pathname.indexOf('/bc/img/model/xl/') !== 0) return String(u);
  return p.protocol + '//' + p.hostname + p.pathname.replace('/model/xl/', '/model/m/') + p.search;
}

/* ---------- 항목 정규화·색인 ---------- */
function normalizeItem(raw) {
  if (!raw || typeof raw !== 'object' || typeof raw.id !== 'string' || !raw.id) return null;
  var str = function (v) { return typeof v === 'string' && v ? v : null; };
  var rel = raw.release && typeof raw.release === 'object' ? raw.release : {};
  var it = {
    id: raw.id, url: str(raw.url), pbUrl: str(raw.pbUrl), line: str(raw.line), channel: str(raw.channel),
    grade: P.catalogGrade(raw.grade), rawGrade: str(raw.grade), scale: str(raw.scale), series: str(raw.series),
    nameJa: str(raw.nameJa), nameKo: str(raw.nameKo), priceJpy: Number(raw.priceJpy) || 0,
    release: { month: str(rel.month), date: str(rel.date) },
    kr: (Array.isArray(raw.kr) ? raw.kr : []).filter(function (e) { return e && typeof e.date === 'string'; }),
    images: (Array.isArray(raw.images) ? raw.images : []).filter(isStableImage),
    manual: raw.manual === true
  };
  it.title = displayName(it);
  it.kn = norm(stripPrefix(it.nameKo, it.rawGrade, it.scale));
  it.jn = norm(stripPrefix(it.nameJa, it.rawGrade, it.scale));
  it.sn = norm(it.series);
  it.all = norm(it.nameKo) + '|' + norm(it.nameJa) + '|' + it.sn + '|' + norm(it.rawGrade) + '|' + norm(it.scale);
  return it;
}
function build(lists, meta) {
  var items = [], byId = {};
  lists.forEach(function (l) {
    (l && Array.isArray(l.items) ? l.items : []).forEach(function (raw) {
      var it = normalizeItem(raw);
      if (it && !byId[it.id]) { byId[it.id] = it; items.push(it); }
    });
  });
  var crawl = meta && meta.crawl && typeof meta.crawl === 'object' ? meta.crawl : {};
  return { items: items, byId: byId,
    updatedAt: meta && meta.updatedAt || null,
    since: crawl.joyOldest || (meta && meta.since) || null }; // 조이하비 기록 시작일: joyOldest가 기준
}

/* ---------- 검색 ---------- */
// 모든 낱말이 들어 있는 항목만(AND). 하나도 없으면 절반 이상 맞는 항목을 partial로.
// 점수: 이름 전체 일치 > 접두 > 연속 포함 > 낱말별 이름·작품·등급 일치. 같으면 이름이 짧은 쪽, 사진 있는 쪽, 최신 발매.
function search(cat, query, o) {
  o = o || {};
  var tokens = String(query || '').split(/\s+/).map(norm).filter(Boolean);
  if (!tokens.length) return { results: [], partial: false, total: 0 };
  var q = tokens.join(''), grade = o.grade && o.grade !== 'all' ? o.grade : null, limit = o.limit || SEARCH_LIMIT;
  var strict = [], loose = [], need = Math.ceil(tokens.length / 2);
  cat.items.forEach(function (it) {
    if (grade && it.grade !== grade) return;
    var hit = 0, score = 0;
    tokens.forEach(function (t) {
      if (it.kn.indexOf(t) >= 0 || it.jn.indexOf(t) >= 0) { hit++; score += 3; }
      else if (it.all.indexOf(t) >= 0) { hit++; score += 1; }
    });
    if (!hit || (hit < tokens.length && (tokens.length < 2 || hit < need))) return;
    var core = it.kn.indexOf(q) >= 0 ? it.kn : it.jn;
    if (it.kn === q || it.jn === q) score += 100;
    else if (it.kn.indexOf(q) === 0 || it.jn.indexOf(q) === 0) score += 40;
    else if (it.kn.indexOf(q) >= 0 || it.jn.indexOf(q) >= 0) score += 20;
    score -= Math.min(core.length, 60) * 0.05;
    if (it.images.length) score += 0.5;
    if (o.scale && it.scale === o.scale) score += 2; // 내 프라의 스케일과 같은 쪽을 앞으로 (등급 '기타'일 때 특히)
    var row = { item: it, score: score, rel: it.release.date || it.release.month || '' };
    (hit === tokens.length ? strict : loose).push(row);
  });
  var rows = strict.length ? strict : loose;
  rows.sort(function (a, b) { return b.score - a.score || (a.rel < b.rel ? 1 : a.rel > b.rel ? -1 : 0); });
  return { results: rows.slice(0, limit).map(function (r) { return r.item; }), partial: !strict.length && !!loose.length, total: rows.length };
}

/* ---------- URL·ID 붙여넣기 ---------- */
// 호비사이트 상품 URL(bandai-hobby.net/item/01_4257/), 카탈로그 id(bh-01_4257), 상품 번호(01_4257), P-반다이 상품 URL을 알아본다
function parseRef(text) {
  var s = String(text == null ? '' : text).trim();
  if (!s || s.length > 300) return null;
  var m = s.match(/bandai-hobby\.net\/item\/(\d{2}_\d+)/i);
  if (m) return { id: 'bh-' + m[1], kind: 'hobby' };
  m = s.match(/^(?:bh-)?(\d{2}_\d+)$/i);
  if (m) return { id: 'bh-' + m[1], kind: 'hobby' };
  m = s.match(/p-bandai\.jp\/item\/(item-\d+)/i) || s.match(/^pb-(item-\d+)$/i);
  if (m) return { id: 'pb-' + m[1], kind: 'pbandai' };
  return null;
}

/* ---------- 연결할 때 채울 값 ---------- */
// cur: 폼/프라의 현재 값 {name, grade, scale, series, brand}.
// o.fillAll(새 프라): 등급·스케일·시리즈를 카탈로그 값으로 채운다. 아니면 빈 칸만(등급 '기타', 스케일 '논스케일'은 빈 칸으로 본다).
// 이름은 비었거나 o.replaceName일 때만. 카탈로그에 없는 값은 건드리지 않는다.
function fillPatch(item, cur, o) {
  o = o || {}; cur = cur || {};
  var patch = {}, filled = [];
  var set = function (k, v, label) { patch[k] = v; filled.push(label); };
  var name = item.title;
  if (name && (!cur.name || o.replaceName) && name !== cur.name) set('name', name, '이름');
  if (item.grade && item.grade !== '기타' && item.grade !== cur.grade && (o.fillAll || !cur.grade || cur.grade === '기타')) set('grade', item.grade, '등급');
  if (item.scale && item.scale !== cur.scale && (o.fillAll || !cur.scale || cur.scale === '논스케일')) set('scale', item.scale, '스케일');
  if (item.series && item.series !== cur.series && (o.fillAll || !cur.series)) set('series', item.series, '시리즈');
  if (!cur.brand) set('brand', '반다이', '브랜드');
  return { patch: patch, filled: filled };
}

/* ---------- 공식 사진 ---------- */
function officialImages(cat, kit, settings) {
  if (!cat || !kit || !kit.catalogId || (settings && settings.hideOfficialPhotos)) return [];
  var it = cat.byId[kit.catalogId];
  return it ? it.images.slice() : [];
}
// 연결이 바뀌면 이전 제품의 공식 사진을 가리키던 대표(off:n)는 풀어 둔다
function setCatalogId(kit, id) {
  var k = P.clone(kit);
  if ((k.catalogId || null) !== (id || null) && k.cover && k.cover.indexOf('off:') === 0) k.cover = null;
  k.catalogId = id || null;
  return k;
}

/* ---------- 읽기 ---------- */
// meta.json(작음)을 먼저 받아 updatedAt을 캐시 키(?v=)로 쓴다: 다음 수집 전까지는 브라우저 캐시를 그대로 쓴다.
// fetchFn(url, init) → Promise<Response>. 실패하면 reject (화면은 보유·위시만 보여 주고 다시 시도 버튼을 준다)
function cacheKey(meta, now) { return meta && meta.updatedAt ? String(meta.updatedAt) : 'h' + Math.floor((now == null ? Date.now() : now) / 3600000); }
function load(fetchFn, o) {
  o = o || {};
  var base = o.base || 'data/';
  var getJson = function (url, init) {
    return fetchFn(url, init).then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); });
  };
  return getJson(base + 'meta.json?t=' + (o.now == null ? Date.now() : o.now), { cache: 'no-store' }).catch(function () { return null; }).then(function (meta) {
    var v = encodeURIComponent(cacheKey(meta, o.now));
    return Promise.all(FILES.map(function (f) { return getJson(base + f + '?v=' + v); })).then(function (lists) { return build(lists, meta); });
  });
}

return {
  FILES: FILES, SEARCH_LIMIT: SEARCH_LIMIT,
  norm: norm, stripPrefix: stripPrefix, displayName: displayName, isStableImage: isStableImage, thumbUrl: thumbUrl,
  normalizeItem: normalizeItem, build: build, search: search, parseRef: parseRef, fillPatch: fillPatch,
  officialImages: officialImages, setCatalogId: setCatalogId, cacheKey: cacheKey, load: load
};
});
