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
  assert.equal(C.stripPrefix('HGUC 건담', 'HG', '1/144'), 'HGUC 건담');
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
  const r = C.search(cat, '발바토스 루프스 클리어');
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
