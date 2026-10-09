/* 프라 격납고 — 카탈로그(크롤러가 만든 catalog-*.json) 순수 로직.
   검색·URL 파싱·채우기·공식 사진은 DOM 없이 계산하고, 읽기(load)만 fetch 함수를 받아 쓴다.
   브라우저에서는 window.PlamoCatalog, node에서는 require()로 쓴다 (tests/site_catalog.test.mjs). */
(function (root, factory) {
  var node = typeof module === 'object' && module.exports;
  var P = node ? require('./pure.js') : root.PlamoPure, A = node ? require('./aliases.js') : root.PlamoAliases;
  if (node) module.exports = factory(P, A);
  else root.PlamoCatalog = factory(P, A);
})(typeof self !== 'undefined' ? self : this, function (P, A) {
'use strict';

var FILES = ['catalog-gunpla.json', 'catalog-girl.json'];
var ALIAS = null; // 별칭 사전 (norm이 정의된 뒤 한 번 만든다)
var SEARCH_LIMIT = 30;
var AKAMAI = 'bandai-a.akamaihd.net', HOBBY = 'bandai-hobby.net';

/* ---------- 문자열 ---------- */
// 검색용: NFKC(전각·반각 통일) + 소문자 + 글자·숫자만 남긴다 ("건담 에어리얼"="건담에어리얼", "ＨＧ"="hg")
// ∀(턴에이 건담의 기호)는 글자가 아니라 지워지므로, 먼저 ターンエー로 바꿔 둔다 → "∀건담"·"∀ガンダム"가 "턴에이"(aliases.js 묶음)로 찾아진다.
function norm(s) { return String(s == null ? '' : s).normalize('NFKC').replace(/∀/g, 'ターンエー').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''); }

// "HG 1/144 건담 에어리얼" → "건담 에어리얼" (내 프라 이름은 보통 등급·스케일 없이 적는다).
// loose=true(비교용)면 HGUC·HGCE·HGBD:R 같은 등급 변형 머리말도 뗀다. 화면에 보이는 이름(displayName)은 loose 없이 — 카탈로그 원래 이름을 그대로 보여 준다.
function stripPrefix(name, grade, scale, loose) {
  var s = String(name == null ? '' : name).trim();
  if (grade) {
    var g = String(grade);
    if (s.slice(0, g.length).normalize('NFKC').toLowerCase() === g.toLowerCase() && /^\s/.test(s.slice(g.length) + ' ')) s = s.slice(g.length).trim();   // 전각 ＭＧ도 등급 머리말로 뗀다 (일본어 이름)
  }
  if (grade && loose) {                                  // HGCE·HGUC·HGBD:R 같은 등급 변형 머리말 (등급 글자로 시작하는 영문 낱말)
    var g2 = String(grade).replace(/[^A-Za-z]/g, ''), m = g2 && new RegExp('^' + g2 + '[A-Za-z]{1,4}(?::[A-Za-z])?(?=\\s)', 'i').exec(s);
    if (m) s = s.slice(m[0].length).trim();
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

// 공식 상품 페이지 링크. 호비사이트·P-반다이 주소만 (카탈로그가 이상한 값을 가져도 링크로 만들지 않는다)
function pageUrl(item) {
  var ok = function (u, host) { var p = parseUrl(u); return !!p && p.protocol === 'https:' && p.hostname === host; };
  if (item && ok(item.url, HOBBY)) return item.url;
  if (item && ok(item.pbUrl, 'p-bandai.jp')) return item.pbUrl;
  return null;
}

/* ---------- 항목 정규화·색인 ---------- */
function normalizeItem(raw) {
  if (!raw || typeof raw !== 'object' || typeof raw.id !== 'string' || !raw.id) return null;
  var str = function (v) { return typeof v === 'string' && v ? v : null; };
  var rel = raw.release && typeof raw.release === 'object' ? raw.release : {};
  var it = {
    id: raw.id, url: str(raw.url), pbUrl: str(raw.pbUrl), line: str(raw.line), channel: str(raw.channel),
    grade: P.catalogGrade(raw.grade), rawGrade: str(raw.grade), scale: str(raw.scale), series: str(raw.series), seriesKo: str(raw.seriesKo),
    nameJa: str(raw.nameJa), nameKo: str(raw.nameKo), nameKoAi: str(raw.nameKoAi), nameKoJoy: str(raw.nameKoJoy), priceJpy: Number(raw.priceJpy) || 0,
    priceKrw: Number.isInteger(raw.priceKrw) && raw.priceKrw > 0 ? raw.priceKrw : 0, priceKrwAt: str(raw.priceKrwAt),
    mallGno: typeof raw.mallGno === 'string' && /^\d+$/.test(raw.mallGno) ? raw.mallGno : null, mallSoldOut: raw.mallSoldOut === true, mallEnded: raw.mallEnded === true,
    release: { month: str(rel.month), date: str(rel.date) },
    kr: (Array.isArray(raw.kr) ? raw.kr : []).filter(function (e) { return e && typeof e.date === 'string'; }),
    images: (Array.isArray(raw.images) ? raw.images : []).filter(isStableImage),
    manual: raw.manual === true
  };
  it.title = displayName(it);
  it.kn = norm(stripPrefix(it.nameKo, it.rawGrade, it.scale, true));       // 비교용 이름 (변형 머리말도 뗀 것)
  it.jn = norm(stripPrefix(it.nameJa, it.rawGrade, it.scale, true));
  it.cmp = norm(stripPrefix(it.nameKo || it.nameJa, it.rawGrade, it.scale, true));   // 자동 연결 후보 비교 키
  // 같은 상품의 다른 한국어 이름(AI 번역·조이하비 이름) — 몰 이름으로 바뀌어 모델번호·옛 표기가 빠져도 검색·자동 연결이 계속 맞는다
  it.alts = [it.nameKoAi, it.nameKoJoy].map(function (n) { return n ? norm(stripPrefix(n, it.rawGrade, it.scale, true)) : ''; })
    .filter(function (n, i, a) { return n && n !== it.kn && a.indexOf(n) === i; });
  it.ka = it.alts.join('|');
  it.seriesText = it.seriesKo || it.series;   // 화면·채우기에는 한국어(seriesKo)를 먼저 쓴다
  it.sn = norm(it.seriesKo) + norm(it.series);
  it.meta = norm(it.rawGrade) + '|' + norm(it.scale);                  // 등급·스케일은 낱말이 맞아도 '이름이 맞았다'로 치지 않는다
  it.all = norm(it.nameKo) + '|' + norm(it.nameJa) + '|' + it.ka + '|' + it.sn + '|' + it.meta;
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
function aliasSet() { return ALIAS || (ALIAS = A ? A.build(norm) : null); }
// 낱말 AND 검색 + 별칭(aliases.js). 규칙:
//  - 낱말은 별칭으로 넓혀 하나라도 맞으면 맞은 것. "클리어·코팅" 같은 꼬리말은 필수가 아니라 **있으면 가산**.
//  - 이름(또는 시리즈)에서 일반어가 아닌 낱말이 하나는 맞아야 후보 ("발길 클리어"가 "[클리어 컬러] 한정판"에 연결되지 않게). 검색어가 전부 일반어면 그대로.
//  - 낱말을 모두 못 맞추면 절반 이상 맞는 후보를 partial로. o.aliases === false면 별칭 없이(개선 전 비교용).
//  - 점수: 이름 전체 일치 > 접두 > 연속 포함 > 낱말별 일치. 같으면 이름이 짧은 쪽, 사진 있는 쪽, 최신 발매.
function search(cat, query, o) {
  o = o || {};
  var raw = String(query || '').split(/\s+/).map(norm).filter(Boolean);
  if (!raw.length) return { results: [], partial: false, total: 0 };
  var al = o.aliases === false ? null : aliasSet();
  var sp = al ? al.splitTails(raw) : { core: raw, tails: [] };
  var tokens = sp.core.length ? sp.core : raw, tails = sp.core.length ? sp.tails : [];  // 꼬리말만 입력했으면 그대로 검색
  var altsOf = tokens.map(function (t) { return al ? al.alts(t) : [t]; });
  var tailBonus = tails.map(function (t) { return { all: t.all, words: t.words }; });
  var needDistinct = !!al && tokens.some(function (t) { return !al.isGeneric(t); });
  var q = tokens.join(''), grade = o.grade && o.grade !== 'all' ? o.grade : null, limit = o.limit || SEARCH_LIMIT;
  var strict = [], loose = [], need = Math.ceil(tokens.length / 2);
  var has = function (str, list) { for (var i = 0; i < list.length; i++) if (str.indexOf(list[i]) >= 0) return true; return false; };
  cat.items.forEach(function (it) {
    if (grade && it.grade !== grade) return;
    var hit = 0, score = 0, distinct = 0;
    tokens.forEach(function (t, i) {
      var alts = altsOf[i], real = !(al && al.isGeneric(t));
      if (has(it.kn, alts) || has(it.jn, alts)) { hit++; score += 3; if (real) distinct++; }
      else if (it.ka && has(it.ka, alts)) { hit++; score += 2; if (real) distinct++; }      // 다른 한국어 이름(nameKoAi·nameKoJoy)으로 맞음 — 현재 이름보다 약간 낮게
      else if (has(it.sn, alts)) { hit++; score += 1; if (real) distinct++; }
      else if (has(it.all, alts)) { hit++; score += 1; }
    });
    if (!hit || (needDistinct && !distinct) || (hit < tokens.length && (tokens.length < 2 || hit < need))) return;
    var qs = [q];
    if (tokens.length === 1) qs = altsOf[0];
    var eq = function (s) { return qs.some(function (x) { return s === x; }); }, pre = function (s) { return qs.some(function (x) { return s.indexOf(x) === 0; }); }, inc = function (s) { return qs.some(function (x) { return s.indexOf(x) >= 0; }); };
    var core = inc(it.kn) ? it.kn : it.jn;
    if (eq(it.kn) || eq(it.jn)) score += 100;
    else if (pre(it.kn) || pre(it.jn)) score += 40;
    else if (inc(it.kn) || inc(it.jn)) score += 20;
    tailBonus.forEach(function (tb) {
      if (it.kn.indexOf(tb.all) >= 0 || it.jn.indexOf(tb.all) >= 0 || it.all.indexOf(tb.all) >= 0) score += 75;
      else if (tb.words.some(function (w) { return it.kn.indexOf(w) >= 0 || it.jn.indexOf(w) >= 0; })) score += 65;   // '철혈 코팅' → 카탈로그엔 '[아이언 블러드 코팅]'
    });
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
  if (item.seriesText && item.seriesText !== cur.series && (o.fillAll || !cur.series)) set('series', item.seriesText, '시리즈');
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

/* ---------- 재판 공백 ---------- */
// 날짜는 'YYYY-MM-DD' 문자열끼리 비교한다. 월만 아는 발매일은 정렬에만 월 말일(화면에는 월까지만 — 날짜를 지어내지 않는다)
function dayNum(s) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || '')); return m ? Math.floor(Date.UTC(+m[1], +m[2] - 1, +m[3]) / 864e5) : null; }
function monthEnd(m) {
  var x = /^(\d{4})-(\d{2})$/.exec(String(m || '')); if (!x || +x[2] < 1 || +x[2] > 12) return null;
  var last = new Date(Date.UTC(+x[1], +x[2], 0)).getUTCDate();
  return x[1] + '-' + x[2] + '-' + (last < 10 ? '0' : '') + last;
}
function releaseLabel(it) { var r = it && it.release || {}; return dayNum(r.date) != null ? r.date : (/^\d{4}-\d{2}$/.test(r.month || '') ? r.month : ''); }
function releaseSortKey(it) { var r = it && it.release || {}; return dayNum(r.date) != null ? r.date : monthEnd(r.month); }
// 일본 발매가 미래인지: 날짜를 알면 그 날, 월만 알면 그 달 1일 기준 (이번 달 발매인데 날짜만 모르면 "예정"이라 단정하지 않는다)
function releaseIsFuture(it, today) {
  var r = it && it.release || {}, t = dayNum(today);
  if (dayNum(r.date) != null) return dayNum(r.date) > t;
  return /^\d{4}-\d{2}$/.test(r.month || '') ? dayNum(r.month + '-01') > t : false;
}
// 연결된 카탈로그 항목 → 재판 공백 표시·정렬 정보. text는 상세용 전체 문구, short는 카드용.
// group 0: 국내 입고 기록(오늘까지) 있음 → key=마지막 입고일(오래된 쪽이 공백 김)
// group 1: 기록 없음/예정만 있음 → key=일본 발매일(월만이면 월 말일, 모르면 맨 뒤)
function gapInfo(item, today, since) {
  var t = dayNum(today);
  var dates = (item.kr || []).map(function (e) { return e && e.date; }).filter(function (d) { return dayNum(d) != null; }).sort();
  var past = dates.filter(function (d) { return dayNum(d) <= t; }), up = dates.filter(function (d) { return dayNum(d) > t; });
  var last = past.length ? past[past.length - 1] : null, next = up.length ? up[0] : null;
  var label = releaseLabel(item), n = last ? t - dayNum(last) : null;
  var ago = n === null ? '' : (n <= 0 ? '오늘' : n + '일 전');
  var out = { group: last ? 0 : 1, key: last || releaseSortKey(item) || '9999-12-31', last: last, next: next, days: n, recent: n !== null && n <= 30 };
  if (next) { out.text = '국내 입고 예정 ' + next + (last ? ' · 마지막 입고 ' + last : ''); out.short = '입고 예정 ' + next; }
  else if (last) { out.text = '국내 마지막 입고 ' + last + ' · ' + ago; out.short = '마지막 입고 ' + last + ' · ' + ago; }
  else if (releaseIsFuture(item, today)) { out.text = out.short = '일본 발매 예정 ' + label; }
  else {
    out.text = '국내 입고 기록 없음' + (since ? ' (' + since + ' 이후 기준)' : '') + (label ? ' · 일본 발매 ' + label : '');
    out.short = '입고 기록 없음' + (label ? ' · 일본 발매 ' + label : '');
  }
  return out;
}

/* ---------- 정가 (반다이남코코리아몰 가격 · 호비 일본 정가) ---------- */
var MALL_BASE = 'https://www.bnkrmall.co.kr';
function mallUrl(gno) { return /^\d+$/.test(String(gno == null ? '' : gno)) ? MALL_BASE + '/goods/detail.do?gno=' + gno : null; }   // 상품 URL은 사이트가 만든다 (카탈로그에는 gno만)
function fmtMoney(sym, n) { return sym + Math.round(Number(n) || 0).toLocaleString('ko-KR'); }
// 상세의 "정가" 줄 정보. 몰 가격이 있으면 ₩ · 반다이남코코리아몰(링크), 없으면 호비의 엔 정가(세금 포함). 둘 다 없으면 null.
// 몰에서 사라졌으면(mallEnded) 마지막 값과 날짜를 그대로 보이되 링크는 걸지 않는다. 카드에는 쓰지 않는다 (내 구매가와 헷갈리지 않게).
// today(YYYY-MM-DD)를 주면: 몰 가격 확인 시각(priceKrwAt = PC가 몰 목록을 읽은 날)이 STALE_DAYS일보다 오래됐을 때 "가격 확인 YYYY-MM-DD"를 덧붙인다 (stale: true).
// 몰이 클라우드 IP를 막아 목록은 사용자 PC가 읽는다 — PC가 꺼져 있던 기간에는 가격이 오래된 값일 수 있다는 표시.
var STALE_DAYS = 7;       // crawler/config.py MALL_STALE_DAYS와 같은 값
function priceInfo(item, today) {
  if (!item) return null;
  var url = mallUrl(item.mallGno);
  if (item.priceKrw > 0 && url) {
    var checked = String(item.priceKrwAt || '').slice(0, 10), ended = !!item.mallEnded, sold = !ended && !!item.mallSoldOut;
    var t = dayNum(today), c = dayNum(checked), stale = !ended && t != null && c != null && t - c > STALE_DAYS;
    var note = ended ? '판매 종료' + (checked ? '(마지막 확인 ' + checked + ')' : '') : [sold ? '품절' : '', stale ? '가격 확인 ' + checked : ''].filter(Boolean).join(' · ');
    return { kind: 'krw', amount: fmtMoney('₩', item.priceKrw), label: '반다이남코코리아몰', url: ended ? null : url, ended: ended, soldOut: sold, stale: stale, note: note };
  }
  if (item.priceJpy > 0) return { kind: 'jpy', amount: fmtMoney('¥', item.priceJpy), label: '일본 정가(세금 포함)', url: null, ended: false, soldOut: false, note: '' };
  return null;
}
// 구매 가격(원): 직접 입력한 price가 있으면 그 값, 비어 있으면 연결된 제품의 몰 정가(priceKrw). collection.json에는 저장하지 않는 화면 계산값이다.
// 엔 정가(priceJpy)만 있는 제품은 원화로 환산하지 않고 null — 합계에도 넣지 않는다. → { amount, listed } | null (listed: 정가 기준)
function purchasePrice(kit, item) {
  var own = Number(kit && kit.price) || 0;
  if (own > 0) return { amount: own, listed: false };
  var pi = item ? priceInfo(item) : null;
  return pi && pi.kind === 'krw' ? { amount: item.priceKrw, listed: true } : null;
}
// 합계: 직접 입력 + 정가 기준. listed는 정가 기준으로 들어간 개수. itemOf(kit)는 연결된 카탈로그 항목(없으면 null)
function purchaseTotal(kits, itemOf) {
  var total = 0, listed = 0;
  (kits || []).forEach(function (k) { var p = purchasePrice(k, itemOf ? itemOf(k) : null); if (p) { total += p.amount; if (p.listed) listed++; } });
  return { total: total, listed: listed };
}
function priceShort(item) { var p = priceInfo(item); return p ? p.amount : ''; }          // 연결 후보 목록의 작은 가격 (₩ 또는 ¥)

/* ---------- 자동 연결 후보 · 시리즈 한국어 · 리뷰 링크 ---------- */
// 연결 후보 키: 정규화한 이름(등급·스케일 머리말 뗌) + 등급 + 스케일. 카탈로그에 스케일이 없으면 '논스케일'로 본다
function linkKey(name, grade, scale) { return norm(name) + '|' + grade + '|' + (scale || '논스케일'); }
// 아직 연결 안 된 프라 중 이름·등급·스케일이 모두 같고 카탈로그 후보가 정확히 1개인 것만. 등급 '기타'는 제외 (애매하면 연결하지 않는다).
// → [{kit, item, filled}] (filled: 연결하면 빈 칸이 채워지는 항목)
function autoLinks(kits, cat) {
  if (!cat) return [];
  var index = {};
  cat.items.forEach(function (it) {
    if (it.grade === '기타' || !it.cmp) return;
    [it.cmp].concat(it.alts).forEach(function (cmp) {         // 현재 이름 + 다른 한국어 이름 모두 키로 (같은 항목은 키마다 한 번)
      var k = linkKey(cmp, it.grade, it.scale);
      (index[k] = index[k] || []).push(it);
    });
  });
  var out = [];
  (kits || []).forEach(function (kit) {
    if (kit.catalogId) return;
    var g = P.gname(kit.grade); if (g === '기타') return;
    var c = index[linkKey(stripPrefix(kit.name, kit.grade, kit.scale, true), g, kit.scale)];
    if (c && c.length === 1) out.push({ kit: kit, item: c[0], filled: fillPatch(c[0], kit).filled });
  });
  return out;
}
// 이미 연결된 프라 중 시리즈 칸이 카탈로그의 일본어 series 와 정확히 같고 한국어(seriesKo)가 있는 것 → 한국어로 바꾸자는 제안.
// 사용자가 직접 적은 값(일본어 원문과 다른 값)은 건드리지 않는다.
function seriesKoSuggestions(kits, cat) {
  if (!cat) return [];
  var out = [];
  (kits || []).forEach(function (kit) {
    var it = kit.catalogId ? cat.byId[kit.catalogId] : null;
    if (it && it.series && it.seriesKo && kit.series === it.series && it.seriesKo !== kit.series) out.push({ kit: kit, item: it, from: kit.series, to: it.seriesKo });
  });
  return out;
}
// 이미 연결된 프라 중 등급(기타)·스케일(논스케일)·시리즈(빈 칸)가 비어 있는데 카탈로그에는 값이 생긴 것 → 채우자는 제안.
// fillPatch의 "빈 칸만" 규칙 그대로라 사용자가 적은 값은 건드리지 않는다. 이름·브랜드는 제안하지 않는다.
var FILL_FIELDS = [['grade', '등급'], ['scale', '스케일'], ['series', '시리즈']];
function fillCandidates(kits, cat) {
  if (!cat) return [];
  var out = [];
  (kits || []).forEach(function (kit) {
    var it = kit.catalogId ? cat.byId[kit.catalogId] : null;
    if (!it) return;
    var patch = fillPatch(it, kit).patch, changes = [];
    FILL_FIELDS.forEach(function (f) { if (patch[f[0]] != null) changes.push({ field: f[0], label: f[1], from: kit[f[0]] || '', to: patch[f[0]] }); });
    if (changes.length) out.push({ kit: kit, item: it, changes: changes });
  });
  return out;
}
// 고른 제안을 next(데이터 사본)의 kits 에 적용한다. links: {kitId→catalogId}, seriesIds: [kitId], fillIds: [kitId](빈 칸 채우기). 적용한 수를 돌려준다.
function applyAuto(kits, cat, links, seriesIds, fillIds) {
  var n = { links: 0, series: 0, fills: 0 };
  (kits || []).forEach(function (k) {
    var it = links && links[k.id] ? cat.byId[links[k.id]] : null;
    if (it && !k.catalogId) { Object.assign(k, fillPatch(it, k).patch); k.catalogId = it.id; n.links++; }
    if (seriesIds && seriesIds.indexOf(k.id) >= 0) {
      var cur = k.catalogId ? cat.byId[k.catalogId] : null;
      if (cur && cur.seriesKo && k.series === cur.series) { k.series = cur.seriesKo; n.series++; }
    }
    if (fillIds && fillIds.indexOf(k.id) >= 0 && k.catalogId && cat.byId[k.catalogId]) {   // 그 사이 값이 채워졌거나 바뀌었으면 fillPatch가 알아서 건드리지 않는다
      var patch = fillPatch(cat.byId[k.catalogId], k).patch, did = false;
      FILL_FIELDS.forEach(function (f) { if (patch[f[0]] != null) { k[f[0]] = patch[f[0]]; did = true; } });
      if (did) n.fills++;
    }
  });
  return n;
}
// 리뷰 찾아보기: "<등급> <이름> 리뷰" 검색 링크 (유튜브·네이버 블로그). 등급을 모르면(기타) 이름만, 이름이 이미 등급으로 시작하면 중복하지 않는다
function reviewLinks(kit) {
  var name = String(kit && kit.name || '').trim(), g = P.gname(kit && kit.grade);
  var q = ((g !== '기타' && name.toLowerCase().indexOf(g.toLowerCase()) !== 0 ? g + ' ' : '') + name + ' 리뷰').trim();
  var e = encodeURIComponent(q);
  return { query: q, youtube: 'https://www.youtube.com/results?search_query=' + e, naver: 'https://search.naver.com/search.naver?where=blog&query=' + e };
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
  norm: norm, stripPrefix: stripPrefix, displayName: displayName, isStableImage: isStableImage, thumbUrl: thumbUrl, pageUrl: pageUrl,
  normalizeItem: normalizeItem, build: build, search: search, parseRef: parseRef, fillPatch: fillPatch,
  officialImages: officialImages, setCatalogId: setCatalogId, gapInfo: gapInfo, priceInfo: priceInfo, priceShort: priceShort, purchasePrice: purchasePrice, purchaseTotal: purchaseTotal, mallUrl: mallUrl, autoLinks: autoLinks, seriesKoSuggestions: seriesKoSuggestions, fillCandidates: fillCandidates, applyAuto: applyAuto, reviewLinks: reviewLinks, dayNum: dayNum, monthEnd: monthEnd, releaseLabel: releaseLabel, releaseSortKey: releaseSortKey, cacheKey: cacheKey, load: load
};
});
