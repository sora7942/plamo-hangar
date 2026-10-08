/* 프라 격납고 — 순수 함수 모음. DOM·네트워크·저장소를 건드리지 않는다.
   브라우저에서는 window.PlamoPure, node에서는 require()로 쓴다 (tests/site_pure.test.mjs). */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PlamoPure = factory();
})(typeof self !== 'undefined' ? self : this, function () {
'use strict';

var GRADES = ['HG','RG','MG','PG','EG','SD','SDCS','SDEX','BB','MGEX','MGSD','RE/100','FM','30MM','30MS','30MP','Figure-rise Standard','Figure-rise Standard Amplified','기타'];
// 카탈로그(호비사이트) 등급 이름 → 사이트 등급. 목록에 없으면 '기타'
var GRADE_ALIAS = { 'FULL MECHANICS': 'FM', 'FIGURE-RISE STANDARD (AMPLIFIED)': 'Figure-rise Standard Amplified' };
// 카드 모서리 배지용 짧은 이름 (저장·필터에는 원래 이름을 쓴다)
var GRADE_SHORT = { 'Figure-rise Standard': 'FRS', 'Figure-rise Standard Amplified': 'FRS-A' };
var STATUSES = [{k:'unbuilt',l:'미개봉'},{k:'building',l:'조립 중'},{k:'built',l:'완성'},{k:'custom',l:'도색·개조'}];
var SCALES = ['1/144','1/100','1/60','1/48','논스케일'];
var TAG_SUGGEST = ['P-반다이','건담베이스 한정','이벤트 한정','클리어','코팅','재판'];
var STLABEL = {}; STATUSES.forEach(function (s) { STLABEL[s.k] = s.l; });
var BULK_KEEP = '__keep';
var MAX_PHOTOS = 20;
var ID_RE = /^[A-Za-z0-9_-]+$/;
var PHOTO_RE = /^photos\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+(_t)?\.webp$/;
var COVER_RE = /^(my:[A-Za-z0-9_-]+|off:\d+)$/;
var CATALOG_ID_RE = /^(bh|pb)-[A-Za-z0-9_-]{1,60}$/;
var DEFAULT_SETTINGS = { name: '프라 격납고', hidePurchase: true, hideOfficialPhotos: false };

/* ---------- 작은 도구 ---------- */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function gk(g) { var k = String(g || '').replace(/[^A-Za-z0-9]/g, ''); return GRADES.indexOf(g) >= 0 && k ? k : 'etc'; }
function gname(g) { return GRADES.indexOf(g) >= 0 ? g : '기타'; }
function glabel(g) { var n = gname(g); return GRADE_SHORT[n] || n; }
function catalogGrade(g) { g = String(g || '').trim(); if (GRADES.indexOf(g) >= 0) return g; var a = GRADE_ALIAS[g.toUpperCase()]; return a || '기타'; }
function won(n) { return (Number(n) || 0).toLocaleString('ko-KR') + '원'; }
function ymd(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
function days(a, b) {
  if (!a || !b) return null;
  var d = Math.round((new Date(b) - new Date(a)) / 864e5);
  return isNaN(d) || d < 0 ? null : d + 1;
}
function splitTags(s) {
  var seen = {};
  return String(s || '').split(/[,;|#]/).map(function (t) { return t.trim(); }).filter(function (t) {
    if (!t || seen[t]) return false; seen[t] = 1; return true;
  });
}
function makeId(prefix) { return prefix + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
function uid() { return makeId('k'); }
function clone(x) { return JSON.parse(JSON.stringify(x)); }
function hasOwn(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

/* ---------- 사진 경로 ---------- */
function isSafePhotoPath(p) { return typeof p === 'string' && p.length < 200 && PHOTO_RE.test(p); }
function photoPaths(kitId, photoId) {
  if (!ID_RE.test(String(kitId)) || !ID_RE.test(String(photoId))) throw new Error('bad id');
  return { src: 'photos/' + kitId + '/' + photoId + '.webp', thumb: 'photos/' + kitId + '/' + photoId + '_t.webp' };
}
function cleanPhotos(arr) {
  if (!Array.isArray(arr)) return [];
  var seen = {};
  return arr.filter(function (p) {
    if (!p || typeof p !== 'object' || !ID_RE.test(String(p.id)) || seen[p.id]) return false;
    if (!isSafePhotoPath(p.src) || !isSafePhotoPath(p.thumb)) return false;
    seen[p.id] = 1; return true;
  }).map(function (p) { return { id: String(p.id), src: p.src, thumb: p.thumb }; });
}

/* ---------- 데이터 정규화·직렬화 ---------- */
function normKit(k) {
  if (!k.id || typeof k.id !== 'string') k.id = uid();
  k.list = k.list === 'wish' ? 'wish' : 'own';
  k.tags = Array.isArray(k.tags) ? k.tags.filter(Boolean) : [];
  if (!hasOwn(STLABEL, k.status)) k.status = 'unbuilt';
  k.startDate = k.startDate || ''; k.doneDate = k.doneDate || '';
  k.photos = cleanPhotos(k.photos);
  k.cover = typeof k.cover === 'string' && COVER_RE.test(k.cover) ? k.cover : null;
  k.catalogId = typeof k.catalogId === 'string' && CATALOG_ID_RE.test(k.catalogId) ? k.catalogId : null;
  delete k.photo; // v2의 data URI 사진은 가져오기 때 파일로 바뀐다 (parseV2Json)
  return k;
}
function normalizeData(d) {
  d = d && typeof d === 'object' ? d : {};
  var s = Object.assign({}, DEFAULT_SETTINGS, d.settings && typeof d.settings === 'object' ? d.settings : {});
  s.name = String(s.name || DEFAULT_SETTINGS.name);
  s.hidePurchase = s.hidePurchase !== false;
  s.hideOfficialPhotos = s.hideOfficialPhotos === true;
  var kits = (Array.isArray(d.kits) ? d.kits : []).filter(function (k) { return k && typeof k === 'object'; }).map(normKit);
  return { version: 3, settings: s, kits: kits };
}
// kit 하나 = 한 줄: git diff가 읽히고, 한 줄 단위로 충돌이 난다
function serialize(data) {
  var d = normalizeData(clone(data));
  var kits = d.kits.length ? '[\n' + d.kits.map(function (k) { return ' ' + JSON.stringify(k); }).join(',\n') + '\n]' : '[]';
  return '{"version":3,"settings":' + JSON.stringify(d.settings) + ',\n"kits":' + kits + '}\n';
}
function parseData(text) {
  if (text == null || !String(text).trim()) return normalizeData({});
  return normalizeData(JSON.parse(text));
}

/* ---------- 사진 순서·대표 ---------- */
function photoItems(kit, official) {
  var my = (kit.photos || []).filter(function (p) { return p && isSafePhotoPath(p.src) && isSafePhotoPath(p.thumb); })
    .map(function (p) { return { key: 'my:' + p.id, kind: 'my', id: p.id, src: p.src, thumb: p.thumb }; });
  var off = (official || []).map(function (u, i) { return { key: 'off:' + i, kind: 'off', src: u, thumb: u }; });
  return { my: my, off: off };
}
// 대표: cover가 가리키는 사진 → 없으면 내 첫 사진 → 없으면 공식 첫 사진.
// 갤러리 순서: [대표, 나머지 공식(사이트 순서), 나머지 내 사진]
function photoOrder(kit, official) {
  var it = photoItems(kit, official), all = it.my.concat(it.off);
  var cover = (kit.cover && all.filter(function (x) { return x.key === kit.cover; })[0]) || it.my[0] || it.off[0] || null;
  if (!cover) return { cover: null, list: [] };
  var list = [cover].concat(it.off.filter(function (x) { return x !== cover; }), it.my.filter(function (x) { return x !== cover; }));
  return { cover: cover, list: list };
}
function hasPhoto(kit, official) { return photoOrder(kit, official).list.length > 0; }
function addPhotos(kit, photos) {
  var k = clone(kit), have = {};
  k.photos = cleanPhotos(k.photos); k.photos.forEach(function (p) { have[p.id] = 1; });
  cleanPhotos(photos).forEach(function (p) { if (!have[p.id] && k.photos.length < MAX_PHOTOS) k.photos.push(p); });
  return k;
}
function removePhoto(kit, id) {
  var k = clone(kit);
  k.photos = cleanPhotos(k.photos).filter(function (p) { return p.id !== id; });
  if (k.cover === 'my:' + id) k.cover = null;
  return k;
}
function movePhoto(kit, id, delta) {
  var k = clone(kit), a = cleanPhotos(k.photos), i = a.map(function (p) { return p.id; }).indexOf(id), j = i + delta;
  if (i < 0 || j < 0 || j >= a.length) { k.photos = a; return k; }
  var t = a[i]; a[i] = a[j]; a[j] = t; k.photos = a; return k;
}
function setCover(kit, key) {
  var k = clone(kit);
  if (key == null) { k.cover = null; return k; }
  if (!COVER_RE.test(String(key))) return k;
  if (key.indexOf('my:') === 0 && !cleanPhotos(k.photos).some(function (p) { return 'my:' + p.id === key; })) return k;
  k.cover = key; return k;
}
function photoFileSet(kits) {
  var s = {}, ids = {};
  (kits || []).forEach(function (k) { (k.photos || []).forEach(function (p) {
    if (!isSafePhotoPath(p.src) || !isSafePhotoPath(p.thumb)) return;
    s['docs/' + p.src] = 1; s['docs/' + p.thumb] = 1; ids[k.id + '/' + p.id] = 1;
  }); });
  return { files: s, ids: ids };
}
// 저장 전후 비교로 이번 커밋에서 올릴/지울 사진 파일 경로를 구한다
function planPhotoFiles(prevKits, nextKits) {
  var a = photoFileSet(prevKits), b = photoFileSet(nextKits);
  var add = Object.keys(b.files).filter(function (p) { return !a.files[p]; });
  var remove = Object.keys(a.files).filter(function (p) { return !b.files[p]; });
  var addedPhotos = Object.keys(b.ids).filter(function (i) { return !a.ids[i]; }).length;
  var removedPhotos = Object.keys(a.ids).filter(function (i) { return !b.ids[i]; }).length;
  return { add: add.sort(), remove: remove.sort(), addedPhotos: addedPhotos, removedPhotos: removedPhotos };
}

/* ---------- 중복·빈 칸·필터·정렬 ---------- */
function normName(s) {
  return String(s || '').toLowerCase().replace(/^\s*(hguc|hgce|hg|rg|mgex|mgsd|mg|pg|eg|sd|re\/?100|fm|30mm)\b/, '').replace(/[\s\-_·.,()\[\]'"]/g, '');
}
function findDups(name, grade, exceptId, pool) {
  var n = normName(name); if (!n) return [];
  return (pool || []).filter(function (k) { return k.id !== exceptId && normName(k.name) === n && gname(k.grade) === gname(grade); });
}
var GAPS = {
  purchase: { l: '구매 정보 빈 칸', t: function (k) { return k.list === 'own' && (!k.date || !k.shop || !k.price); } },
  photo: { l: '사진 없음', t: function (k) { return !hasPhoto(k); } },
  unlinked: { l: '반다이 제품 미연결', t: function (k) { return !k.catalogId; } },
  series: { l: '시리즈 빈 칸', t: function (k) { return !k.series; } },
  done: { l: '완성일 빈 칸', t: function (k) { return k.list === 'own' && (k.status === 'built' || k.status === 'custom') && !k.doneDate; } }
};
// ctx.gap(kit) → {group, key} | null : 재판 공백 정렬용(연결된 카탈로그 항목이 있을 때만). null이면 맨 뒤 묶음
function filterSort(kits, ui, ctx) {
  var q = String(ui.q || '').trim().toLowerCase();
  var list = kits.filter(function (k) {
    if (k.list !== ui.tab) return false;
    if (ui.grade !== 'all' && gname(k.grade) !== ui.grade) return false;
    if (ui.tab === 'own' && ui.status !== 'all' && k.status !== ui.status) return false;
    if (ui.tag !== 'all' && k.tags.indexOf(ui.tag) < 0) return false;
    if (ui.gap !== 'all' && GAPS[ui.gap] && !GAPS[ui.gap].t(k)) return false;
    if (q && [k.name, k.series, k.memo, k.grade, k.brand, k.shop, k.tags.join(' ')].join(' ').toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
  var gi = function (g) { var i = GRADES.indexOf(g); return i < 0 ? 99 : i; };
  var byName = function (a, b) { return String(a.name).localeCompare(String(b.name), 'ko'); };
  list.sort(function (a, b) {
    if (ui.sort === 'name') return byName(a, b);
    if (ui.sort === 'gap') {
      var ga = ctx && ctx.gap ? ctx.gap(a) : null, gb = ctx && ctx.gap ? ctx.gap(b) : null;
      var ra = ga ? ga.group : 2, rb = gb ? gb.group : 2;
      return ra - rb || (ga && gb ? (ga.key < gb.key ? -1 : ga.key > gb.key ? 1 : 0) : 0) || byName(a, b);
    }
    if (ui.sort === 'grade') return gi(a.grade) - gi(b.grade) || byName(a, b);
    if (ui.sort === 'price') return (Number(b.price) || 0) - (Number(a.price) || 0);
    if (ui.sort === 'done') return String(b.doneDate || '').localeCompare(String(a.doneDate || '')) || byName(a, b);
    if (ui.tab === 'wish') return String(b.created || '').localeCompare(String(a.created || ''));
    return String(b.date || '').localeCompare(String(a.date || '')) || String(b.created || '').localeCompare(String(a.created || ''));
  });
  return list;
}

/* ---------- 일괄 수정 (next 사본에 직접 적용) ---------- */
function applyBulk(kits, ids, spec) {
  var set = {}; ids.forEach(function (i) { set[i] = 1; });
  var sets = spec.sets || {}, fills = spec.fills || {}, onlyEmpty = spec.onlyEmpty !== false;
  var add = spec.add || [], rem = spec.rem || [], price = Number(spec.price) || 0;
  kits.forEach(function (k) {
    if (!set[k.id]) return;
    Object.keys(sets).forEach(function (f) { if (sets[f] !== BULK_KEEP) k[f] = sets[f]; });
    Object.keys(fills).forEach(function (f) { if (fills[f] && (!onlyEmpty || !k[f])) k[f] = fills[f]; });
    if (price && (!onlyEmpty || !k.price)) k.price = price;
    var tags = (k.tags || []).filter(function (t) { return rem.indexOf(t) < 0; });
    add.forEach(function (t) { if (tags.indexOf(t) < 0) tags.push(t); });
    k.tags = tags;
  });
  return kits;
}

/* ---------- 엑셀·CSV 가져오기/백업 ---------- */
var COLS = [['list','목록'],['name','이름'],['grade','등급'],['scale','스케일'],['series','시리즈'],['brand','브랜드'],['status','상태'],['date','구매일'],['shop','구매처'],['price','가격'],
  ['tags','태그'],['startDate','조립 시작일'],['doneDate','완성일'],['memo','메모'],['catalogId','반다이 제품 ID']];
function exportRows(kits) {
  return [COLS.map(function (c) { return c[1]; })].concat(kits.map(function (k) {
    return COLS.map(function (c) {
      var f = c[0], v = k[f];
      if (f === 'list') return v === 'wish' ? '위시리스트' : '보유';
      if (f === 'status') return k.list === 'wish' ? '' : STLABEL[v];
      if (f === 'tags') return v.join(', ');
      if (f === 'price') return Number(v) || '';
      return v == null ? '' : v;
    });
  }));
}
var ALIASES = { list: ['목록','구분'], name: ['이름','제품명','모델명','킷','상품명','name','제품'], grade: ['등급','grade','그레이드'], scale: ['스케일','scale','비율'],
  series: ['시리즈','작품','series','작품명'], brand: ['브랜드','제조사','brand','메이커'], status: ['상태','status','진행'],
  date: ['구매일','구입일','날짜','date','구매날짜'], shop: ['구매처','구입처','shop','판매처','매장'], price: ['가격','구매가','구입가','price','금액','예상 가격'],
  tags: ['태그','tag','tags'], startDate: ['조립 시작일','시작일'], doneDate: ['완성일','조립 완료일','완료일'], memo: ['메모','비고','note','memo'], catalogId: ['반다이 제품 id','반다이제품id','catalogid','카탈로그 id'] };
var DEFAULT_ORDER = ['name','grade','scale','series','status','date','shop','price','memo'];

function parseDelimited(text) {
  var delim = text.indexOf('\t') >= 0 ? '\t' : ',', rows = [], row = [], cur = '', q = false;
  for (var i = 0; i < text.length; i++) {
    var ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += ch; continue; }
    if (ch === '"' && cur === '') { q = true; continue; }
    if (ch === delim) { row.push(cur); cur = ''; continue; }
    if (ch === '\r') continue;
    if (ch === '\n') { row.push(cur); rows.push(row); row = []; cur = ''; continue; }
    cur += ch;
  }
  if (cur !== '' || row.length) { row.push(cur); rows.push(row); }
  return rows.filter(function (r) { return r.some(function (c) { return String(c).trim(); }); });
}
function normGrade(g, name) {
  var s = String(g || '').toUpperCase().replace(/\s/g, '');
  // 긴 이름 먼저: 'SD'가 'SDCS'보다, 'MG'가 'MGSD'보다 먼저 걸리면 안 된다
  var order = ['FIGURE-RISESTANDARDAMPLIFIED','FIGURERISESTANDARDAMPLIFIED','FIGURE-RISESTANDARD','FIGURERISESTANDARD','FULLMECHANICS','MGEX','MGSD','SDCS','SDEX',
    'RE/100','RE100','30MM','30MS','30MP','HG','RG','MG','PG','EG','SD','FM','BB'];
  var out = { 'RE100': 'RE/100', 'FULLMECHANICS': 'FM', 'FIGURERISESTANDARD': 'Figure-rise Standard', 'FIGURE-RISESTANDARD': 'Figure-rise Standard',
    'FIGURERISESTANDARDAMPLIFIED': 'Figure-rise Standard Amplified', 'FIGURE-RISESTANDARDAMPLIFIED': 'Figure-rise Standard Amplified' };
  var hit = function (str) { for (var i = 0; i < order.length; i++) { if (str.indexOf(order[i]) >= 0) { var o = order[i]; return out[o] || o; } } return ''; };
  return (s && hit(s)) || hit(String(name || '').toUpperCase()) || '기타';
}
function normStatus(s) {
  s = String(s || '').replace(/\s/g, '');
  if (/도색|개조|커스텀|먹선/.test(s)) return 'custom';
  if (/조립중|진행|작업중|가조립중/.test(s)) return 'building';
  if (/완성|완료|조립완|가조립/.test(s)) return 'built';
  return 'unbuilt';
}
function normScale(s, grade) {
  s = String(s || '').replace(/\s/g, ''); var m = s.match(/1\/(\d+)/); if (m) return '1/' + m[1];
  if (/논|non|없/i.test(s)) return '논스케일';
  return { HG: '1/144', RG: '1/144', EG: '1/144', MG: '1/100', PG: '1/60', 'RE/100': '1/100', FM: '1/100', MGEX: '1/100', SD: '논스케일', MGSD: '논스케일' }[grade] || '논스케일';
}
function normDate(s) {
  s = String(s || '').trim(); if (!s) return '';
  var m = s.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (m) return m[1] + '-' + ('0' + m[2]).slice(-2) + '-' + ('0' + m[3]).slice(-2);
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (m) { var y = m[3].length === 2 ? '20' + m[3] : m[3]; return y + '-' + ('0' + m[1]).slice(-2) + '-' + ('0' + m[2]).slice(-2); }
  if (/^\d{5}$/.test(s)) { var d = new Date(Math.round((Number(s) - 25569) * 864e5)); return d.toISOString().slice(0, 10); }
  return '';
}
function rowsToKits(rows, opts) {
  opts = opts || {};
  var idFn = opts.idFn || uid, now = opts.now == null ? Date.now() : opts.now;
  if (!rows.length) return { kits: [], skipped: 0 };
  var map = null, start = 0;
  for (var r = 0; r < Math.min(rows.length, 5) && !map; r++) {
    var m = {}, found = 0;
    rows[r].forEach(function (cell, i) {
      var c = String(cell).trim().toLowerCase(); if (!c) return;
      var keys = Object.keys(ALIASES);
      var exact = keys.filter(function (key) { return m[key] == null && ALIASES[key].some(function (a) { return c === a.toLowerCase(); }); })[0];
      var key = exact || keys.filter(function (key) { return m[key] == null && ALIASES[key].some(function (a) { return c.indexOf(a.toLowerCase()) === 0; }); })[0];
      if (key) { m[key] = i; found++; }
    });
    if (found >= 2 && m.name != null) { map = m; start = r + 1; }
  }
  if (!map) { map = {}; DEFAULT_ORDER.forEach(function (k, i) { map[k] = i; }); start = 0; }
  var out = [], skipped = 0;
  rows.slice(start).forEach(function (row, i) {
    var get = function (k) { return map[k] == null ? '' : String(row[map[k]] == null ? '' : row[map[k]]).trim(); };
    var name = get('name'); if (!name) { skipped++; return; }
    var grade = normGrade(get('grade'), name), wish = /위시|wish|희망/i.test(get('list'));
    out.push(normKit({ id: idFn() + i, created: new Date(now + i).toISOString(), list: wish ? 'wish' : 'own', name: name, grade: grade, scale: normScale(get('scale'), grade), series: get('series'), brand: get('brand') || '반다이',
      status: wish ? 'unbuilt' : normStatus(get('status')), date: wish ? '' : normDate(get('date')), shop: wish ? '' : get('shop'), price: Number(get('price').replace(/[^0-9]/g, '')) || 0,
      tags: splitTags(get('tags')), startDate: normDate(get('startDate')), doneDate: normDate(get('doneDate')), memo: get('memo'), catalogId: get('catalogId') }));
  });
  return { kits: out, skipped: skipped };
}

/* ---------- v2 데이터(JSON) 가져오기: photo(data URI) → 별도 목록으로 분리 ---------- */
var DATA_URI_RE = /^data:(image\/(?:jpeg|png|webp|gif));base64,([A-Za-z0-9+\/=\s]+)$/;
function parseV2Json(text) {
  var t = String(text || '').trim(), m = t.match(/<script[^>]*id=["']kit-data["'][^>]*>([\s\S]*?)<\/script>/i);
  if (m) t = m[1].trim();
  var raw = JSON.parse(t), arr = Array.isArray(raw) ? raw : (raw && raw.kits);
  if (!Array.isArray(arr)) throw new Error('kits 없음');
  var legacy = {}, kits = [];
  arr.forEach(function (k) {
    if (!k || typeof k !== 'object' || !String(k.name || '').trim()) return;
    var kit = normKit(Object.assign({}, k, { photos: [], cover: null, catalogId: null }));
    if (typeof k.photo === 'string' && DATA_URI_RE.test(k.photo)) legacy[kit.id] = k.photo;
    kits.push(kit);
  });
  return { kits: kits, legacy: legacy };
}
function dataUriToBytes(uri) {
  var m = String(uri).match(DATA_URI_RE); if (!m) return null;
  var bin = atob(m[2].replace(/\s/g, '')), a = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
  return { type: m[1], bytes: a };
}

/* ---------- 커밋 메시지 ---------- */
function clip(s, n) { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
function commitMessage(kind, o) {
  o = o || {};
  var base = {
    add: '추가 ' + clip(o.name, 40), edit: '수정 ' + clip(o.name, 40), move: '보유로 이동 ' + clip(o.name, 40), delete: '삭제 ' + clip(o.name, 40),
    assist: '반다이 제품 ' + (o.n || 0) + '개 연결 (연결 도우미)', link: '반다이 제품 연결 ' + clip(o.name, 40), unlink: '반다이 제품 연결 해제 ' + clip(o.name, 40),
    autolink: [o.links ? '반다이 제품 ' + o.links + '개 자동 연결' : '', o.series ? '시리즈 ' + o.series + '개 한국어로' : '', o.fills ? '빈 칸 ' + o.fills + '개 채움' : ''].filter(Boolean).join(' · '),
    'bulk-edit': (o.n || 0) + '개 일괄 수정', 'bulk-delete': (o.n || 0) + '개 일괄 삭제', 'import': (o.n || 0) + '개 가져오기', settings: '설정'
  }[kind] || '변경';
  var ph = [];
  if (o.photosAdded) ph.push('+' + o.photosAdded);
  if (o.photosRemoved) ph.push('-' + o.photosRemoved);
  return 'collection: ' + base + (ph.length ? ' · 사진 ' + ph.join(' ') : '');
}

return {
  GRADES: GRADES, STATUSES: STATUSES, SCALES: SCALES, TAG_SUGGEST: TAG_SUGGEST, STLABEL: STLABEL, BULK_KEEP: BULK_KEEP, MAX_PHOTOS: MAX_PHOTOS, COLS: COLS, GAPS: GAPS,
  esc: esc, gk: gk, gname: gname, glabel: glabel, catalogGrade: catalogGrade, won: won, ymd: ymd, days: days, splitTags: splitTags, uid: uid, makeId: makeId, clone: clone,
  isSafePhotoPath: isSafePhotoPath, photoPaths: photoPaths,
  normKit: normKit, normalizeData: normalizeData, serialize: serialize, parseData: parseData,
  photoOrder: photoOrder, hasPhoto: hasPhoto, addPhotos: addPhotos, removePhoto: removePhoto, movePhoto: movePhoto, setCover: setCover, planPhotoFiles: planPhotoFiles,
  normName: normName, findDups: findDups, filterSort: filterSort, applyBulk: applyBulk,
  exportRows: exportRows, parseDelimited: parseDelimited, normGrade: normGrade, normStatus: normStatus, normScale: normScale, normDate: normDate, rowsToKits: rowsToKits,
  parseV2Json: parseV2Json, dataUriToBytes: dataUriToBytes, commitMessage: commitMessage
};
});
