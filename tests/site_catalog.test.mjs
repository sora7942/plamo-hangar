// node tests/site_catalog.test.mjs — docs/catalog.js 순수 로직 (네트워크·DOM 없음, 읽기는 가짜 fetch)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const P = require('../docs/pure.js');
const C = require('../docs/catalog.js');

const IMG = 'https://bandai-a.akamaihd.net/bc/img/model/xl/1000179163_1.jpg';
const raw = (id, over = {}) => ({ id, url: `https://bandai-hobby.net/item/${id.slice(3)}/`, line: 'gunpla', grade: 'HG', scale: '1/144', series: null,
  nameJa: null, nameKo: null, release: { month: '2022-10', date: '2022-10-01' }, kr: [], images: [], ...over });
const LIST = [
  raw('bh-01_1', { nameKo: 'HG 1/144 건담 에어리얼', nameJa: 'HG 1/144 ガンダムエアリアル', series: '기동전사 건담 수성의 마녀', images: [IMG] }),
  raw('bh-01_2', { nameKo: 'HG 1/144 건담 에어리얼 (개수형)', series: '기동전사 건담 수성의 마녀' }),
  raw('bh-01_3', { grade: 'MG', scale: '1/100', nameKo: 'MG 1/100 발바토스 루프스', series: '기동전사 건담 철혈의 오펀스' }),
  raw('bh-01_4', { grade: 'MG', scale: '1/100', nameKo: 'MG 1/100 발바토스 루프스 렉스' }),
  raw('bh-01_5', { grade: 'MGSD', scale: null, nameKo: 'MGSD 에어리얼' }),
  raw('bh-01_6', { grade: 'FULL MECHANICS', scale: '1/100', nameKo: 'FULL MECHANICS 1/100 건담 바르바토스' }),
  raw('bh-01_7', { grade: '30MS', line: 'girl', scale: '1/144', nameKo: '30MS 시시리아', nameJa: '30MS シシリア' }),
  raw('pb-item-9', { grade: 'HG', nameKo: 'HG 1/144 한정 건담', release: { month: '2026-12', date: null } }),
];
const cat = C.build([{ items: LIST.slice(0, 5) }, { items: LIST.slice(5) }], { updatedAt: '2026-10-08T15:40:00+09:00', since: '2024-04-01', crawl: { joyOldest: '2024-01-04' } });

test('norm: 공백·구두점·전각 무시', () => {
  assert.equal(C.norm('건담 에어리얼'), C.norm('건담에어리얼'));
  assert.equal(C.norm('ＨＧ  1/144'), 'hg1144');
  assert.equal(C.norm(null), '');
});

test('stripPrefix: 등급·스케일 머리말만 뗀다', () => {
  assert.equal(C.stripPrefix('HG 1/144 건담 에어리얼', 'HG', '1/144'), '건담 에어리얼');
  assert.equal(C.stripPrefix('MGSD 에어리얼', 'MGSD', null), '에어리얼');
  assert.equal(C.stripPrefix('HGUC 1/144 건담', 'HG', '1/144'), 'HGUC 1/144 건담', '화면용: 등급 변형 머리말은 그대로');
  assert.equal(C.stripPrefix('HGUC 1/144 건담', 'HG', '1/144', true), '건담', '비교용(loose): HGUC·HGCE·HGBD:R 머리말도 뗀다');
  assert.equal(C.stripPrefix('HGBD:R 1/144 네프테이트 웨폰즈', 'HG', '1/144', true), '네프테이트 웨폰즈');
  assert.equal(C.stripPrefix('HG건담', 'HG', null, true), 'HG건담', '공백 없이 붙은 이름은 건드리지 않는다');
  assert.equal(C.stripPrefix('FULL MECHANICS 1/100 건담', 'FULL MECHANICS', '1/100'), '건담');
  assert.equal(C.stripPrefix(null, 'HG', null), '');
});

test('build: 등급 변환(FULL MECHANICS→FM), 제목, 중복 id 무시, since는 joyOldest', () => {
  assert.equal(cat.items.length, 8);
  assert.equal(cat.byId['bh-01_6'].grade, 'FM');
  assert.equal(cat.byId['bh-01_7'].grade, '30MS');
  assert.equal(cat.byId['bh-01_1'].title, '건담 에어리얼');
  assert.equal(cat.since, '2024-01-04');
  assert.equal(C.build([{ items: [raw('bh-01_1'), raw('bh-01_1', { nameKo: 'x' })] }], null).items.length, 1);
  assert.equal(C.build([{ items: [null, {}, { id: 5 }] }], null).items.length, 0);
  assert.equal(C.build([null], null).since, null);
});

test('search: 이름 전체 일치가 접두·부분 일치보다 먼저', () => {
  const r = C.search(cat, '발바토스 루프스').results.map((x) => x.id);
  assert.deepEqual(r, ['bh-01_3', 'bh-01_4']);
  assert.equal(C.search(cat, '에어리얼', { grade: 'HG' }).results[0].id, 'bh-01_1');
});

test('search: 띄어쓰기 달라도 찾고, 일본어·등급 낱말도 된다', () => {
  assert.equal(C.search(cat, '건담에어리얼').results[0].id, 'bh-01_1');
  assert.equal(C.search(cat, 'ガンダムエアリアル').results[0].id, 'bh-01_1');
  assert.equal(C.search(cat, 'mg 발바토스').results[0].id, 'bh-01_3');
  assert.equal(C.search(cat, 'ｈｇ 에어리얼').results[0].id, 'bh-01_1');
});

test('search: 등급 필터', () => {
  assert.deepEqual(C.search(cat, '에어리얼', { grade: 'MGSD' }).results.map((x) => x.id), ['bh-01_5']);
  assert.deepEqual(C.search(cat, '에어리얼', { grade: 'RG' }).results, []);
  assert.deepEqual(C.search(cat, '건담', { grade: 'FM' }).results.map((x) => x.id), ['bh-01_6']);
  assert.equal(C.search(cat, '에어리얼', { grade: 'all' }).results.length, 3);
});

test('search: 낱말을 모두 못 맞추면 절반 이상 맞는 후보를 partial로, 하나도 아니면 비움', () => {
  const r = C.search(cat, '발바토스 루프스 유니크');
  assert.equal(r.partial, true);
  assert.deepEqual(r.results.map((x) => x.id), ['bh-01_3', 'bh-01_4']);
  const none = C.search(cat, '존재하지않는이름');
  assert.deepEqual(none.results, []); assert.equal(none.partial, false);
  assert.deepEqual(C.search(cat, '   ').results, []);
  assert.equal(C.search(cat, '발바토스 존재안함 없음 아님').partial, false); // 1/4만 맞으면 후보로 삼지 않는다
});

test('search: 개수 제한, 한 낱말 부분 일치는 partial이 아니다', () => {
  const many = C.build([{ items: Array.from({ length: 50 }, (_, i) => raw('bh-01_' + (100 + i), { nameKo: 'HG 1/144 건담 ' + i })) }], null);
  const r = C.search(many, '건담');
  assert.equal(r.results.length, C.SEARCH_LIMIT); assert.equal(r.total, 50); assert.equal(r.partial, false);
});

test('parseRef: 호비 URL·id·상품 번호·P-반다이 URL', () => {
  assert.deepEqual(C.parseRef('https://bandai-hobby.net/item/01_4257/'), { id: 'bh-01_4257', kind: 'hobby' });
  assert.deepEqual(C.parseRef(' https://bandai-hobby.net/item/01_4257/?x=1 '), { id: 'bh-01_4257', kind: 'hobby' });
  assert.deepEqual(C.parseRef('bh-01_4257'), { id: 'bh-01_4257', kind: 'hobby' });
  assert.deepEqual(C.parseRef('01_4257'), { id: 'bh-01_4257', kind: 'hobby' });
  assert.deepEqual(C.parseRef('https://p-bandai.jp/item/item-1000179163/'), { id: 'pb-item-1000179163', kind: 'pbandai' });
  assert.equal(C.parseRef('건담'), null);
  assert.equal(C.parseRef('https://example.com/item/01_4257/'), null);
  assert.equal(C.parseRef(''), null);
  assert.equal(C.parseRef('x'.repeat(400)), null);
});

test('fillPatch: 새 프라는 값을 채우고, 기존 프라는 빈 칸만', () => {
  const it = cat.byId['bh-01_1'];
  const fresh = C.fillPatch(it, { name: '', grade: 'HG', scale: '논스케일', series: '', brand: '반다이' }, { fillAll: true });
  assert.deepEqual(fresh.patch, { name: '건담 에어리얼', scale: '1/144', series: '기동전사 건담 수성의 마녀' });
  const ex = C.fillPatch(it, { name: '내 에어리얼', grade: '기타', scale: '1/144', series: '', brand: '' });
  assert.deepEqual(ex.patch, { grade: 'HG', series: '기동전사 건담 수성의 마녀', brand: '반다이' });
  assert.deepEqual(ex.filled, ['등급', '시리즈', '브랜드']);
  const keep = C.fillPatch(it, { name: '내 에어리얼', grade: 'RG', scale: '1/100', series: '내 시리즈', brand: '반다이' });
  assert.deepEqual(keep.patch, {});
  const rename = C.fillPatch(it, { name: '내 에어리얼', grade: 'HG', scale: '1/144', series: 'x', brand: '반다이' }, { replaceName: true });
  assert.deepEqual(rename.patch, { name: '건담 에어리얼' });
});

test('fillPatch: 카탈로그에 없는 값(스케일 null, 기타 등급)은 덮어쓰지 않는다', () => {
  const mgsd = cat.byId['bh-01_5'];
  const r = C.fillPatch(mgsd, { name: '에어리얼', grade: 'MGSD', scale: '논스케일', series: '', brand: '반다이' });
  assert.deepEqual(r.patch, {});
  assert.deepEqual(C.fillPatch({ ...mgsd, grade: '기타' }, { name: 'a', grade: 'MG', scale: '', series: '', brand: 'b' }, { fillAll: true }).patch, {});
});

test('공식 사진: 안정 URL만, 서명 URL·http·남의 호스트 제외', () => {
  assert.equal(C.isStableImage(IMG), true);
  assert.equal(C.isStableImage('https://bandai-hobby.net/images/a.jpg'), true);
  assert.equal(C.isStableImage('https://bandai-hobby.net/other/a.jpg'), false);
  assert.equal(C.isStableImage('https://d1.cloudfront.net/a.jpg?Expires=123&Signature=x'), false);
  assert.equal(C.isStableImage('https://bandai-a.akamaihd.net/a.jpg?Expires=1'), false);
  assert.equal(C.isStableImage('http://bandai-a.akamaihd.net/a.jpg'), false);
  assert.equal(C.isStableImage('javascript:alert(1)'), false);
  assert.equal(C.isStableImage('https://evil.bandai-hobby.net.example.com/images/a.jpg'), false);
  const c2 = C.build([{ items: [raw('bh-01_9', { images: [IMG, 'https://x.cloudfront.net/a.jpg?Expires=1', 'javascript:1'] })] }], null);
  assert.deepEqual(c2.byId['bh-01_9'].images, [IMG]);
});

test('pageUrl: 호비사이트·P-반다이 https 주소만', () => {
  assert.equal(C.pageUrl({ url: 'https://bandai-hobby.net/item/01_1/' }), 'https://bandai-hobby.net/item/01_1/');
  assert.equal(C.pageUrl({ url: null, pbUrl: 'https://p-bandai.jp/item/item-1/' }), 'https://p-bandai.jp/item/item-1/');
  assert.equal(C.pageUrl({ url: 'javascript:alert(1)', pbUrl: 'http://p-bandai.jp/x' }), null);
  assert.equal(C.pageUrl({ url: 'https://bandai-hobby.net.evil.com/' }), null);
  assert.equal(C.pageUrl(null), null);
});

test('thumbUrl: akamai xl → m, 그 밖에는 그대로', () => {
  assert.equal(C.thumbUrl(IMG), 'https://bandai-a.akamaihd.net/bc/img/model/m/1000179163_1.jpg');
  assert.equal(C.thumbUrl('https://bandai-hobby.net/images/a.jpg'), 'https://bandai-hobby.net/images/a.jpg');
  assert.equal(C.thumbUrl('nonsense'), 'nonsense');
});

test('officialImages: 연결된 프라만, hideOfficialPhotos면 비움, 못 찾으면 비움', () => {
  const k = P.normKit({ id: 'k1', name: 'a', catalogId: 'bh-01_1' });
  assert.deepEqual(C.officialImages(cat, k, { hideOfficialPhotos: false }), [IMG]);
  assert.deepEqual(C.officialImages(cat, k, { hideOfficialPhotos: true }), []);
  assert.deepEqual(C.officialImages(cat, P.normKit({ id: 'k2', name: 'a' }), {}), []);
  assert.deepEqual(C.officialImages(cat, P.normKit({ id: 'k3', name: 'a', catalogId: 'bh-없음' }), {}), []);
  assert.deepEqual(C.officialImages(null, k, {}), []);
});

test('대표 사진: 공식 대표(off:n)로 photoOrder, 연결이 바뀌면 off 대표만 풀림', () => {
  const imgs = [IMG, IMG.replace('_1', '_2'), IMG.replace('_1', '_3')];
  const k = P.normKit({ id: 'k1', name: 'a', catalogId: 'bh-01_1', cover: 'off:2' });
  const o = P.photoOrder(k, imgs);
  assert.equal(o.cover.key, 'off:2');
  assert.deepEqual(o.list.map((x) => x.key), ['off:2', 'off:0', 'off:1']);
  assert.equal(C.setCatalogId(k, 'bh-01_3').cover, null);
  assert.equal(C.setCatalogId(k, null).catalogId, null);
  const mine = P.normKit({ id: 'k1', name: 'a', catalogId: 'bh-01_1', cover: 'my:pa', photos: [{ id: 'pa', src: 'photos/k1/pa.webp', thumb: 'photos/k1/pa_t.webp' }] });
  assert.equal(C.setCatalogId(mine, 'bh-01_3').cover, 'my:pa');
  assert.equal(C.setCatalogId(k, 'bh-01_1').cover, 'off:2'); // 같은 제품이면 유지
  // 공식 사진이 줄어 off:n 범위를 벗어나면 첫 사진으로 되돌아간다
  assert.equal(P.photoOrder(P.normKit({ id: 'k1', name: 'a', cover: 'off:9' }), imgs).cover.key, 'off:0');
});

const fakeFetch = (files, log = []) => (url) => {
  log.push(url);
  const name = url.split('?')[0].replace('data/', '');
  return Promise.resolve(name in files ? { ok: true, json: () => Promise.resolve(files[name]) } : { ok: false, status: 404, json: () => Promise.reject(new Error('404')) });
};
const FILES = { 'meta.json': { updatedAt: '2026-10-08T15:40:00+09:00', crawl: { joyOldest: '2024-01-04' } },
  'catalog-gunpla.json': { items: LIST.slice(0, 5) }, 'catalog-girl.json': { items: LIST.slice(5) } };

test('load: meta를 먼저 받고 updatedAt을 ?v= 캐시 키로 쓴다', async () => {
  const log = [];
  const c = await C.load(fakeFetch(FILES, log), { now: 1 });
  assert.equal(c.items.length, 8); assert.equal(c.since, '2024-01-04');
  assert.match(log[0], /^data\/meta\.json\?t=1$/);
  assert.ok(log.slice(1).every((u) => u.includes('?v=2026-10-08T15%3A40%3A00%2B09%3A00')), log.join('\n'));
  assert.equal(log.length, 3);
});

test('load: meta를 못 읽어도 시간 단위 키로 카탈로그는 읽는다', async () => {
  const f = { ...FILES }; delete f['meta.json'];
  const log = [];
  const c = await C.load(fakeFetch(f, log), { now: 3600000 * 5 });
  assert.equal(c.items.length, 8); assert.equal(c.updatedAt, null);
  assert.ok(log[1].endsWith('?v=h5'));
});

test('load: 카탈로그 파일 하나라도 못 읽으면 reject', async () => {
  const f = { ...FILES }; delete f['catalog-girl.json'];
  await assert.rejects(C.load(fakeFetch(f)));
});

test('search: scale 힌트는 같은 스케일을 앞으로 (등급을 모를 때)', () => {
  const r = C.search(cat, '건담 에어리얼', { scale: '1/144' }).results.map((x) => x.id);
  assert.equal(r[0], 'bh-01_1');
  const fm = C.search(cat, '건담 바르바토스', { scale: '1/100' }).results[0];
  assert.equal(fm.id, 'bh-01_6');
});

// ---------- 재판 공백 ----------
const TODAY = '2026-10-08', SINCE = '2024-01-04';
const gi = (over) => C.gapInfo(C.normalizeItem(raw('bh-01_50', over)), TODAY, SINCE);
const kr = (...dates) => dates.map((date) => ({ date, type: 'restock', post: '1', code: 'BD1' }));

test('monthEnd·releaseSortKey: 월만 알면 월 말일(정렬용), 윤년·12월', () => {
  assert.equal(C.monthEnd('2022-10'), '2022-10-31');
  assert.equal(C.monthEnd('2024-02'), '2024-02-29');
  assert.equal(C.monthEnd('2023-02'), '2023-02-28');
  assert.equal(C.monthEnd('2022-12'), '2022-12-31');
  assert.equal(C.monthEnd('2022-13'), null);
  assert.equal(C.monthEnd(null), null);
  assert.equal(C.releaseSortKey({ release: { month: '2022-10', date: null } }), '2022-10-31');
  assert.equal(C.releaseSortKey({ release: { month: '2022-10', date: '2022-10-01' } }), '2022-10-01');
  assert.equal(C.releaseSortKey({ release: {} }), null);
});

test('releaseLabel: 화면에는 월만 알면 월까지만, 날짜를 지어내지 않는다', () => {
  assert.equal(C.releaseLabel({ release: { month: '2022-10', date: null } }), '2022-10');
  assert.equal(C.releaseLabel({ release: { month: '2022-10', date: '2022-10-15' } }), '2022-10-15');
  assert.equal(C.releaseLabel({ release: {} }), '');
  assert.equal(C.releaseLabel(null), '');
});

test('gapInfo: 국내 마지막 입고 · N일 전 (마지막 날짜는 가장 최근 것)', () => {
  const g = gi({ kr: kr('2026-03-01', '2026-10-01', '2025-01-01') });
  assert.equal(g.text, '국내 마지막 입고 2026-10-01 · 7일 전');
  assert.equal(g.short, '마지막 입고 2026-10-01 · 7일 전');
  assert.equal(g.group, 0); assert.equal(g.key, '2026-10-01'); assert.equal(g.days, 7); assert.equal(g.recent, true);
  assert.equal(gi({ kr: kr('2026-10-08') }).text, '국내 마지막 입고 2026-10-08 · 오늘');
  const old = gi({ kr: kr('2024-04-01') });
  assert.equal(old.recent, false); assert.equal(old.days, 920);
});

test('gapInfo: 입고 기록 없음 (기준일) · 일본 발매 — 월만 알면 월까지만', () => {
  assert.equal(gi({ release: { month: '2022-10', date: null } }).text, '국내 입고 기록 없음 (2024-01-04 이후 기준) · 일본 발매 2022-10');
  assert.equal(gi({ release: { month: '2022-10', date: '2022-10-01' } }).text, '국내 입고 기록 없음 (2024-01-04 이후 기준) · 일본 발매 2022-10-01');
  assert.equal(gi({ release: { month: '2022-10', date: null } }).short, '입고 기록 없음 · 일본 발매 2022-10');
  const g = gi({ release: { month: '2022-10', date: null } });
  assert.equal(g.group, 1); assert.equal(g.key, '2022-10-31');
  assert.equal(C.gapInfo(C.normalizeItem(raw('bh-01_51', { release: {} })), TODAY, null).text, '국내 입고 기록 없음');
  assert.equal(gi({ release: {} }).key, '9999-12-31');
});

test('gapInfo: 일본 발매가 미래면 "일본 발매 예정", 이번 달인데 날짜를 모르면 예정이라 단정하지 않는다', () => {
  assert.equal(gi({ release: { month: '2026-12', date: null } }).text, '일본 발매 예정 2026-12');
  assert.equal(gi({ release: { month: '2026-10', date: '2026-10-20' } }).text, '일본 발매 예정 2026-10-20');
  assert.match(gi({ release: { month: '2026-10', date: null } }).text, /^국내 입고 기록 없음/);
  assert.match(gi({ release: { month: '2026-10', date: '2026-10-08' } }).text, /^국내 입고 기록 없음/);
});

test('gapInfo: 국내 입고 예정(미래 kr.date) 문구', () => {
  const g = gi({ kr: kr('2026-10-15') });
  assert.equal(g.text, '국내 입고 예정 2026-10-15'); assert.equal(g.short, '입고 예정 2026-10-15');
  assert.equal(g.group, 1);
  const both = gi({ kr: kr('2026-03-01', '2026-10-15') });
  assert.equal(both.text, '국내 입고 예정 2026-10-15 · 마지막 입고 2026-03-01'); assert.equal(both.group, 0); assert.equal(both.key, '2026-03-01');
});

test('gapInfo: 이상한 kr 날짜는 무시', () => {
  assert.match(gi({ kr: [{ date: 'x' }, { date: '2026-13-45x' }, { date: null }] }).text, /^국내 입고 기록 없음/);
});

// ---------- 자동 연결 후보 · 시리즈 한국어 · 리뷰 링크 ----------
const SER_JA = '機動戦士ガンダム 水星の魔女', SER_KO = '기동전사 건담 수성의 마녀';
const acat = C.build([{ items: [
  raw('bh-02_1', { nameKo: 'HG 1/144 건담 에어리얼', series: SER_JA, seriesKo: SER_KO }),
  raw('bh-02_2', { grade: 'MG', scale: '1/100', nameKo: 'MG 1/100 발바토스 루프스' }),
  raw('bh-02_3', { grade: 'MG', scale: '1/100', nameKo: 'MG 1/100 발바토스 루프스' }),
  raw('bh-02_4', { grade: 'MGSD', scale: null, nameKo: 'MGSD 에어리얼' }),
  raw('bh-02_5', { grade: '30MS', line: 'girl', scale: '1/144', nameKo: '30MS 시시리아' }),
] }], null);
const kitOf = (over) => P.normKit({ id: 'k' + Math.random().toString(36).slice(2, 6), list: 'own', name: '건담 에어리얼', grade: 'HG', scale: '1/144', series: '', brand: '반다이', ...over });

test('autoLinks: 이름·등급·스케일이 같고 후보가 정확히 1개일 때만', () => {
  const ok = kitOf({ name: '건담 에어리얼' }), prefixed = kitOf({ name: 'HG 1/144 건담  에어리얼' });
  const r = C.autoLinks([ok, prefixed], acat);
  assert.deepEqual(r.map((x) => x.item.id), ['bh-02_1', 'bh-02_1'], '머리말·띄어쓰기는 무시');
  assert.deepEqual(r[0].filled, ['시리즈'], '채워지는 항목 안내(빈 시리즈칸은 한국어 시리즈로)');
});

test('autoLinks: 애매하면 연결하지 않는다 (이름 다름·등급 기타·스케일 다름·후보 2개·이미 연결)', () => {
  const none = (k) => assert.deepEqual(C.autoLinks([k], acat), [], JSON.stringify([k.name, k.grade, k.scale]));
  none(kitOf({ name: '에어리얼' }));
  none(kitOf({ grade: '기타' }));
  none(kitOf({ scale: '1/100' }));
  none(kitOf({ name: '발바토스 루프스', grade: 'MG', scale: '1/100' })); // 같은 이름·등급·스케일 후보가 2개
  none(kitOf({ catalogId: 'bh-02_1' }));
  none(kitOf({ name: '시시리아', grade: '30MM' }));
  assert.deepEqual(C.autoLinks([kitOf({ name: '에어리얼', grade: 'MGSD', scale: '논스케일' })], acat).map((x) => x.item.id), ['bh-02_4'], '카탈로그에 스케일이 없으면 논스케일끼리');
  assert.deepEqual(C.autoLinks([kitOf({ name: '시시리아', grade: '30MS' })], acat).map((x) => x.item.id), ['bh-02_5']);
  assert.deepEqual(C.autoLinks([kitOf()], null), []);
});

test('seriesKoSuggestions: 시리즈 칸이 카탈로그 일본어와 정확히 같을 때만', () => {
  const same = kitOf({ catalogId: 'bh-02_1', series: SER_JA }), mine = kitOf({ catalogId: 'bh-02_1', series: '내가 쓴 시리즈' });
  const ko = kitOf({ catalogId: 'bh-02_1', series: SER_KO }), blank = kitOf({ catalogId: 'bh-02_1', series: '' }), unlinked = kitOf({ series: SER_JA });
  const noKo = kitOf({ catalogId: 'bh-02_2', series: 'x' });
  const r = C.seriesKoSuggestions([same, mine, ko, blank, unlinked, noKo], acat);
  assert.deepEqual(r.map((x) => [x.kit.id, x.from, x.to]), [[same.id, SER_JA, SER_KO]]);
});

test('applyAuto: 선택한 것만 연결(빈 칸만 채움)·시리즈 변경, 이름은 그대로', () => {
  const a = kitOf({ name: '건담 에어리얼' }), b = kitOf({ name: '건담 에어리얼', series: '내 값' }), s = kitOf({ catalogId: 'bh-02_1', series: SER_JA }), s2 = kitOf({ catalogId: 'bh-02_1', series: SER_JA });
  const n = C.applyAuto([a, b, s, s2], acat, { [a.id]: 'bh-02_1', [b.id]: 'bh-02_1' }, [s.id]);
  assert.deepEqual(n, { links: 2, series: 1, fills: 0 });
  assert.equal(a.catalogId, 'bh-02_1'); assert.equal(a.series, SER_KO); assert.equal(a.name, '건담 에어리얼');
  assert.equal(b.series, '내 값', '이미 적은 시리즈는 그대로');
  assert.equal(s.series, SER_KO); assert.equal(s2.series, SER_JA, '선택하지 않은 것은 그대로');
  const t = kitOf({ catalogId: 'bh-02_1', series: '사용자가 고침' });
  assert.deepEqual(C.applyAuto([t], acat, {}, [t.id]), { links: 0, series: 0, fills: 0 }, '그 사이 값이 바뀌었으면 건드리지 않는다');
});

test('fillPatch·검색: 시리즈는 한국어(seriesKo)를 먼저, 일본어로도 찾아진다', () => {
  const it = acat.byId['bh-02_1'];
  assert.equal(it.seriesText, SER_KO);
  assert.equal(C.fillPatch(it, { name: 'x', grade: 'HG', scale: '1/144', series: '', brand: 'b' }).patch.series, SER_KO);
  assert.equal(C.normalizeItem(raw('bh-02_9', { series: SER_JA })).seriesText, SER_JA, 'seriesKo가 없으면 일본어 series');
  assert.equal(C.search(acat, '수성의 마녀').results[0].id, 'bh-02_1');
  assert.equal(C.search(acat, '水星の魔女').results[0].id, 'bh-02_1');
});

test('reviewLinks: "<등급> <이름> 리뷰" 유튜브·네이버 블로그', () => {
  const r = C.reviewLinks({ name: '건담 에어리얼', grade: 'HG' });
  assert.equal(r.query, 'HG 건담 에어리얼 리뷰');
  assert.equal(r.youtube, 'https://www.youtube.com/results?search_query=' + encodeURIComponent('HG 건담 에어리얼 리뷰'));
  assert.equal(r.naver, 'https://search.naver.com/search.naver?where=blog&query=' + encodeURIComponent('HG 건담 에어리얼 리뷰'));
  assert.equal(C.reviewLinks({ name: '에어리얼', grade: '기타' }).query, '에어리얼 리뷰');
  assert.equal(C.reviewLinks({ name: 'HG 건담 에어리얼', grade: 'HG' }).query, 'HG 건담 에어리얼 리뷰', '이름이 이미 등급으로 시작하면 중복하지 않는다');
  assert.equal(C.reviewLinks({ name: '"&<x>', grade: 'MG' }).youtube.includes('<'), false);
  assert.equal(C.reviewLinks(null).query, '리뷰');
});

test('line:"other"(manual) 항목: 검색·연결은 되지만 등급이 없어 자동 연결 후보에는 올라가지 않는다', () => {
  const oc = C.build([{ items: [{ id: 'bh-77_1', url: 'https://bandai-hobby.net/item/77_1/', line: 'other', manual: true, grade: null, scale: null, series: 'ドラゴンクエスト', seriesKo: '드래곤 퀘스트',
    nameJa: 'ドラゴンクエスト スライム', nameKo: '드래곤 퀘스트 슬라임', release: { month: '2026-10', date: null }, kr: [], images: [] }] }], null);
  const it = oc.byId['bh-77_1'];
  assert.equal(it.manual, true); assert.equal(it.grade, '기타'); assert.equal(it.title, '드래곤 퀘스트 슬라임');
  assert.equal(C.search(oc, '슬라임').results[0].id, 'bh-77_1');
  assert.equal(C.search(oc, 'ドラゴン').results[0].id, 'bh-77_1');
  assert.deepEqual(C.autoLinks([P.normKit({ id: 'k1', name: '드래곤 퀘스트 슬라임', grade: 'HG', scale: '논스케일' })], oc), []);
  assert.deepEqual(C.fillPatch(it, { name: '', grade: 'HG', scale: '논스케일', series: '', brand: '반다이' }, { fillAll: true }).patch, { name: '드래곤 퀘스트 슬라임', series: '드래곤 퀘스트' });
});

// ---------- 빈 칸 채우기 (이미 연결된 프라) ----------
test('fillCandidates: 연결된 프라의 빈 등급(기타)·스케일(논스케일)·시리즈만, 직접 적은 값은 제외', () => {
  const blank = kitOf({ catalogId: 'bh-02_1', grade: '기타', scale: '논스케일', series: '' });
  const onlySeries = kitOf({ catalogId: 'bh-02_1', series: '' });
  const mine = kitOf({ catalogId: 'bh-02_1', grade: 'RG', scale: '1/100', series: '내 시리즈' });                       // 직접 적은 값 (카탈로그와 달라도)
  const unlinked = kitOf({ grade: '기타', scale: '논스케일', series: '' });
  const unknown = kitOf({ catalogId: 'bh-없음', series: '' });
  const noValue = kitOf({ catalogId: 'bh-02_4', grade: 'MGSD', scale: '논스케일', series: '' });                          // 카탈로그에도 스케일·시리즈가 없다
  const r = C.fillCandidates([blank, onlySeries, mine, unlinked, unknown, noValue], acat);
  assert.deepEqual(r.map((x) => x.kit.id), [blank.id, onlySeries.id]);
  assert.deepEqual(r[0].changes.map((c) => [c.field, c.from, c.to]), [['grade', '기타', 'HG'], ['scale', '논스케일', '1/144'], ['series', '', SER_KO]]);
  assert.deepEqual(r[1].changes.map((c) => c.field), ['series']);
  assert.deepEqual(C.fillCandidates([blank], null), []);
});

test('applyAuto(fillIds): 선택한 것만 빈 칸을 채우고, 그 사이 사용자가 적은 값은 건드리지 않는다', () => {
  const a = kitOf({ catalogId: 'bh-02_1', grade: '기타', scale: '논스케일', series: '' }), b = kitOf({ catalogId: 'bh-02_1', grade: '기타', scale: '논스케일', series: '' });
  const c = kitOf({ catalogId: 'bh-02_1', grade: '기타', scale: '논스케일', series: '그 사이 적음' });
  const n = C.applyAuto([a, b, c], acat, null, null, [a.id, c.id]);
  assert.deepEqual(n, { links: 0, series: 0, fills: 2 });
  assert.deepEqual([a.grade, a.scale, a.series], ['HG', '1/144', SER_KO]);
  assert.deepEqual([b.grade, b.scale, b.series], ['기타', '논스케일', ''], '선택하지 않은 프라는 그대로');
  assert.deepEqual([c.grade, c.scale, c.series], ['HG', '1/144', '그 사이 적음'], '이미 적은 시리즈는 그대로, 비어 있던 칸만');
  assert.equal(a.name, '건담 에어리얼');
  assert.equal(C.applyAuto([a], acat, null, null, [a.id]).fills, 0, '다시 적용해도 바뀐 게 없다');
});

test('자동 연결 후보: 카탈로그 이름의 HGUC 같은 머리말은 비교에서만 떼고, 후보에 보이는 이름은 그대로', () => {
  const c = C.build([{ items: [raw('bh-03_1', { nameKo: 'HGUC 1/144 돔 트로펜' }), raw('bh-03_2', { nameKo: 'HGCE 1/144 데스티니 건담' })] }], null);
  const r = C.autoLinks([kitOf({ name: '돔 트로펜' }), kitOf({ name: 'HGCE 데스티니 건담', scale: '1/144' }), kitOf({ name: '데스티니 건담' })], c);
  assert.deepEqual(r.map((x) => x.item.id), ['bh-03_1', 'bh-03_2', 'bh-03_2']);
  assert.equal(r[0].item.title, 'HGUC 1/144 돔 트로펜');
  assert.equal(C.fillPatch(c.byId['bh-03_1'], { name: '', grade: 'HG', scale: '1/144', series: '', brand: 'b' }).patch.name, 'HGUC 1/144 돔 트로펜', '이름을 채울 때도 원래 이름');
});

test('정가: 몰 가격이 있으면 ₩ + 몰 링크, 없으면 엔 정가, 판매 종료·품절 표시, 링크는 사이트가 만든다', () => {
  const base = { id: 'bh-1', url: 'https://bandai-hobby.net/item/01_1/', line: 'gunpla', grade: 'HG', scale: '1/144', nameKo: 'HG 1/144 테스트', priceJpy: 4950, release: {}, kr: [], images: [] };
  const norm = (o) => C.normalizeItem({ ...base, ...o });
  assert.deepEqual(C.priceInfo(norm({})), { kind: 'jpy', amount: '¥4,950', label: '일본 정가(세금 포함)', url: null, ended: false, soldOut: false, note: '' });
  const live = C.priceInfo(norm({ priceKrw: 46800, priceKrwAt: '2026-10-09T10:00:00+09:00', mallGno: '58992' }));
  assert.equal(live.kind, 'krw'); assert.equal(live.amount, '₩46,800'); assert.equal(live.label, '반다이남코코리아몰');
  assert.equal(live.url, 'https://www.bnkrmall.co.kr/goods/detail.do?gno=58992'); assert.equal(live.note, '');
  const sold = C.priceInfo(norm({ priceKrw: 46800, priceKrwAt: '2026-10-09T10:00:00+09:00', mallGno: '58992', mallSoldOut: true }));
  assert.equal(sold.soldOut, true); assert.equal(sold.note, '품절'); assert.ok(sold.url);
  const ended = C.priceInfo(norm({ priceKrw: 46800, priceKrwAt: '2026-10-09T10:00:00+09:00', mallGno: '58992', mallSoldOut: true, mallEnded: true }));
  assert.equal(ended.ended, true); assert.equal(ended.amount, '₩46,800'); assert.equal(ended.note, '판매 종료(마지막 확인 2026-10-09)'); assert.equal(ended.url, null, '사라진 상품에는 링크를 걸지 않는다'); assert.equal(ended.soldOut, false);
  assert.equal(C.priceInfo(norm({ priceJpy: 0 })), null);
  assert.equal(C.priceInfo(null), null);
  // 값이 이상하면 몰 가격을 쓰지 않는다 (gno가 숫자가 아니거나 가격이 정수가 아님) → 엔 정가로
  assert.equal(C.priceInfo(norm({ priceKrw: 46800, mallGno: '58992/../x' })).kind, 'jpy');
  assert.equal(C.priceInfo(norm({ priceKrw: '46800', mallGno: '58992' })).kind, 'jpy');
  assert.equal(C.mallUrl('12'), 'https://www.bnkrmall.co.kr/goods/detail.do?gno=12'); assert.equal(C.mallUrl('x'), null); assert.equal(C.mallUrl(null), null);
  assert.equal(C.priceShort(norm({ priceKrw: 26400, mallGno: '1' })), '₩26,400'); assert.equal(C.priceShort(norm({})), '¥4,950'); assert.equal(C.priceShort(norm({ priceJpy: 0 })), '');
});

// ---------- 몰 이름으로 바뀐 뒤에도 nameKoAi·nameKoJoy·nameJa로 찾는다 (모델번호·옛 표기가 빠지지 않게) ----------
const renamed = C.build([{ items: [
  raw('bh-r1', { nameKo: 'HG 1/144 사자비', nameKoSource: 'bnkrmall', nameKoAi: 'HG 1/144 MSN-04 사자비', nameKoJoy: 'HG 1/144 MSN-04 샤아 전용 사자비', nameJa: 'HG 1/144 サザビー' }),
  raw('bh-r2', { nameKo: 'HG 1/144 즈고크 개수형', nameKoSource: 'bnkrmall', nameKoAi: 'HG 1/144 즈곡 개수형', nameJa: 'HG 1/144 ズゴック改' }),
  raw('bh-r3', { nameKo: 'HG 1/144 완전히 다른 기체', nameJa: 'HG 1/144 別の機体' }),
] }], null);


test('정가: 몰 가격 확인이 7일보다 오래되면 "가격 확인 날짜"를 덧붙인다 (today를 줄 때만, 판매 종료·엔 정가에는 붙이지 않는다)', () => {
  const base = { id: 'bh-1', url: 'https://bandai-hobby.net/item/01_1/', line: 'gunpla', grade: 'HG', scale: '1/144', nameKo: 'HG 1/144 테스트', priceJpy: 4950, release: {}, kr: [], images: [] };
  const norm = (o) => C.normalizeItem({ ...base, ...o });
  const mall = { priceKrw: 46800, priceKrwAt: '2026-10-01T06:30:00+09:00', mallGno: '58992' };
  assert.equal(C.priceInfo(norm(mall)).note, '', 'today를 안 주면 오래됨 판정을 하지 않는다');
  assert.equal(C.priceInfo(norm(mall), '2026-10-08').stale, false, '정확히 7일은 아직 최신');
  assert.equal(C.priceInfo(norm(mall), '2026-10-08').note, '');
  const old = C.priceInfo(norm(mall), '2026-10-09');
  assert.equal(old.stale, true); assert.equal(old.note, '가격 확인 2026-10-01'); assert.equal(old.amount, '₩46,800'); assert.ok(old.url, '링크는 그대로');
  assert.equal(C.priceInfo(norm({ ...mall, mallSoldOut: true }), '2026-10-20').note, '품절 · 가격 확인 2026-10-01');
  const ended = C.priceInfo(norm({ ...mall, mallEnded: true }), '2026-10-20');
  assert.equal(ended.stale, false); assert.equal(ended.note, '판매 종료(마지막 확인 2026-10-01)');
  assert.equal(C.priceInfo(norm({}), '2026-10-20').kind, 'jpy');
  assert.equal(C.priceInfo(norm({ priceKrw: 46800, mallGno: '58992' }), '2026-10-20').stale, false, '확인 시각을 모르면 오래됨으로 보지 않는다');
});
test('구매 가격: 직접 입력 > 몰 정가, 엔 정가만 있으면 없음(환산 안 함), 합계에는 정가 기준 개수를 따로 센다', () => {
  const base = { id: 'bh-1', url: 'https://bandai-hobby.net/item/01_1/', line: 'gunpla', grade: 'RG', scale: '1/144', nameKo: 'RG 1/144 테스트', priceJpy: 3080, release: {}, kr: [], images: [] };
  const norm = (o) => C.normalizeItem({ ...base, ...o });
  const krw = norm({ priceKrw: 33600, priceKrwAt: '2026-10-09T10:00:00+09:00', mallGno: '56343' }), jpyOnly = norm({ id: 'bh-2' });
  assert.deepEqual(C.purchasePrice({ price: 0 }, krw), { amount: 33600, listed: true });
  assert.deepEqual(C.purchasePrice({ price: '' }, krw), { amount: 33600, listed: true });
  assert.deepEqual(C.purchasePrice({ price: 30000 }, krw), { amount: 30000, listed: false }, '직접 입력이 우선 — 정가 표시 없음');
  assert.equal(C.purchasePrice({ price: 0 }, jpyOnly), null, '엔화만 있는 제품은 원화 가격이 없다');
  assert.equal(C.purchasePrice({ price: 0 }, null), null);
  assert.deepEqual(C.purchasePrice({ price: 12000 }, jpyOnly), { amount: 12000, listed: false });
  const ended = norm({ priceKrw: 33600, priceKrwAt: '2026-10-09T10:00:00+09:00', mallGno: '56343', mallEnded: true });
  assert.deepEqual(C.purchasePrice({ price: 0 }, ended), { amount: 33600, listed: true }, '판매 종료여도 마지막 정가를 쓴다');
  const kits = [{ id: 'a', price: 30000, catalogId: 'k' }, { id: 'b', price: 0, catalogId: 'k' }, { id: 'c', price: 0, catalogId: 'j' }, { id: 'd', price: 0 }, { id: 'e', price: 5000 }];
  const itemOf = (k) => ({ k: krw, j: jpyOnly })[k.catalogId] || null;
  assert.deepEqual(C.purchaseTotal(kits, itemOf), { total: 30000 + 33600 + 5000, listed: 1 });
  assert.deepEqual(C.purchaseTotal([], itemOf), { total: 0, listed: 0 });
  assert.deepEqual(C.purchaseTotal(kits), { total: 35000, listed: 0 }, '카탈로그가 아직 없으면 직접 입력만');
});

test('검색: 몰 이름에 없는 모델번호·옛 표기도 nameKoAi·nameKoJoy로 찾고, 현재 이름 일치가 더 앞선다', () => {
  assert.equal(C.search(renamed, 'MSN-04').results[0].id, 'bh-r1', '모델번호는 AI 번역·조이하비 이름에 남아 있다');
  assert.equal(C.search(renamed, '샤아 전용').results[0].id, 'bh-r1', '조이하비 이름의 낱말');
  assert.equal(C.search(renamed, '즈곡').results[0].id, 'bh-r2', '옛 표기(즈곡)로도');
  assert.equal(C.search(renamed, '즈고크').results[0].id, 'bh-r2', '현재 표기');
  assert.deepEqual(C.search(renamed, 'MSN-04 존재안함').results.map((x) => x.id).filter((i) => i === 'bh-r3'), []);
  const it = renamed.byId['bh-r1'];
  assert.equal(it.title, '사자비', '화면에 보이는 이름은 현재 nameKo (등급·스케일 머리말만 뗌)');
  const order = C.build([{ items: [raw('bh-o1', { nameKo: 'HG 1/144 건담 옛이름', nameKoAi: 'HG 1/144 건담 새이름' }), raw('bh-o2', { nameKo: 'HG 1/144 건담 새이름 개' })] }], null);
  assert.deepEqual(C.search(order, '새이름').results.map((x) => x.id), ['bh-o2', 'bh-o1'], '현재 이름이 맞은 쪽이 앞, 다른 이름으로 맞은 쪽도 후보');
  assert.deepEqual(it.alts.sort(), ['msn04사자비', 'msn04샤아전용사자비'], '비교용 다른 이름들 (등급·스케일 머리말 뗌)');
  assert.equal(renamed.byId['bh-r3'].alts.length, 0);
});

test('autoLinks: 옛 이름(nameKoAi)으로 적은 내 프라도 연결 후보가 되고, 후보가 둘이면 여전히 연결하지 않는다', () => {
  const kit = (name) => P.normKit({ id: 'k' + name, list: 'own', name, grade: 'HG', scale: '1/144', series: '', brand: '반다이' });
  assert.deepEqual(C.autoLinks([kit('즈곡 개수형')], renamed).map((x) => x.item.id), ['bh-r2']);
  assert.deepEqual(C.autoLinks([kit('즈고크 개수형')], renamed).map((x) => x.item.id), ['bh-r2']);
  assert.deepEqual(C.autoLinks([kit('MSN-04 사자비')], renamed).map((x) => x.item.id), ['bh-r1']);
  const dup = C.build([{ items: [raw('bh-d1', { nameKo: 'HG 1/144 몰 이름', nameKoAi: 'HG 1/144 옛 이름' }), raw('bh-d2', { nameKo: 'HG 1/144 옛 이름' })] }], null);
  assert.deepEqual(C.autoLinks([kit('옛 이름')], dup), [], '다른 두 상품이 같은 이름 키를 가지면 애매하므로 연결하지 않는다');
});
