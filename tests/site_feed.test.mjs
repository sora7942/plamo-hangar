// node tests/site_feed.test.mjs — docs/feed.js 순수 함수 (네트워크·DOM 없음)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const P = require('../docs/pure.js');
const C = require('../docs/catalog.js');
const F = require('../docs/feed.js');

const raw = (id, over = {}) => ({ id, url: `https://bandai-hobby.net/item/${id.slice(3)}/`, line: 'gunpla', grade: 'HG', scale: '1/144', series: null,
  nameJa: null, nameKo: null, release: { month: '2026-10', date: null }, kr: [], images: ['https://bandai-a.akamaihd.net/bc/img/model/xl/1_1.jpg'], ...over });
const cat = C.build([{ items: [
  raw('bh-01_1', { nameKo: 'HG 1/144 건담 에어리얼' }),
  raw('bh-01_2', { grade: 'MG', scale: '1/100', nameKo: 'MG 1/100 발바토스' }),
  raw('bh-01_3', { grade: '30MS', line: 'girl', nameKo: '30MS 시시리아', images: [] }),
] }], { updatedAt: '2026-10-08T15:40:00+09:00' });

const fi = (id, type, over = {}) => ({ id, type, date: '2026-10-03', added: '2026-10-08T15:40:41+09:00', catalogId: null, title: '원문 ' + id, titleKo: null, url: 'https://www.joyhobby.co.kr/mall/board_view.asp?B_iID=1', image: null, source: 'joyhobby', ...over });
const ITEMS = [
  fi('a', 'kr-restock', { catalogId: 'bh-01_1', titleKo: 'HG 에어리얼' }),
  fi('b', 'kr-new', { catalogId: 'bh-01_2', added: '2026-10-08T15:40:41+09:00' }),
  fi('c', 'kr-new', { titleKo: '연결 안 된 입고 글' }),
  fi('d', 'new', { catalogId: 'bh-01_3', date: '2027-03', added: '2026-10-06T23:01:34+09:00', url: 'https://bandai-hobby.net/item/01_3/', source: 'bandai-hobby' }),
  fi('e', 'pb-new', { catalogId: 'pb-item-9', date: '2027-01', added: '2026-10-06T23:01:34+09:00', url: 'https://p-bandai.jp/item/item-9/', source: 'bandai-hobby' }),
];
const kit = (id, list, catalogId) => P.normKit({ id, name: id, list, catalogId });

test('normalize: 모르는 type·중복 id·이상한 catalogId 는 걸러낸다', () => {
  const n = F.normalize({ items: [fi('a', 'kr-new'), fi('a', 'new'), fi('x', '이상한종류'), null, { id: 5 }, fi('y', 'new', { catalogId: '<script>' }), fi('z', 'new', { catalogId: 'bh-01_5' })] });
  assert.deepEqual(n.map((x) => x.id), ['a', 'y', 'z']);
  assert.equal(n[1].catalogId, null); assert.equal(n[2].catalogId, 'bh-01_5');
  assert.deepEqual(F.normalize(null), []); assert.deepEqual(F.normalize({ items: 'x' }), []);
});

test('safeLink: 공식·조이하비 https 주소만', () => {
  assert.equal(F.safeLink('https://www.joyhobby.co.kr/mall/board_view.asp?B_iID=1'), 'https://www.joyhobby.co.kr/mall/board_view.asp?B_iID=1');
  assert.equal(F.safeLink('https://bandai-hobby.net/item/01_1/'), 'https://bandai-hobby.net/item/01_1/');
  assert.equal(F.safeLink('https://p-bandai.jp/item/item-9/'), 'https://p-bandai.jp/item/item-9/');
  for (const bad of ['javascript:alert(1)', 'http://bandai-hobby.net/', 'https://evil.com/', 'https://bandai-hobby.net.evil.com/', 'nonsense', null, '']) assert.equal(F.safeLink(bad), null, String(bad));
});

test('build: 내 프라(같은 catalogId의 보유·위시), 제목 우선순위, 카탈로그 등급·라인', () => {
  const rows = F.build(F.normalize({ items: ITEMS }), [kit('k1', 'own', 'bh-01_1'), kit('k2', 'wish', 'bh-01_1'), kit('k3', 'own', null)], cat);
  const a = rows.find((r) => r.item.id === 'a'), b = rows.find((r) => r.item.id === 'b'), c = rows.find((r) => r.item.id === 'c');
  assert.equal(a.mine.length, 2); assert.equal(F.mineText(a), '내 프라 · 보유·위시');
  assert.equal(b.mine.length, 0);
  assert.equal(a.title, 'HG 에어리얼'); assert.equal(b.title, '발바토스'); assert.equal(c.title, '연결 안 된 입고 글');
  assert.equal(a.grade, 'HG'); assert.equal(a.line, 'gunpla'); assert.equal(rows.find((r) => r.item.id === 'd').line, 'girl');
  assert.equal(c.grade, null); assert.equal(c.line, null);
  assert.equal(F.mineText({ mine: [kit('k', 'wish', 'bh-01_1')] }), '내 프라 · 위시');
  assert.equal(F.mineText({ mine: [kit('k', 'own', 'bh-01_1')] }), '내 프라 · 보유');
  const noCat = F.build(F.normalize({ items: ITEMS }), [kit('k1', 'own', 'bh-01_1')], null);
  assert.equal(noCat.find((r) => r.item.id === 'a').mine.length, 1, '카탈로그를 못 읽어도 내 프라 판정은 catalogId 로 된다');
  assert.equal(noCat.find((r) => r.item.id === 'a').grade, null);
});

test('sortRows: 내 프라 맨 위 → 발견 최신순 → 같은 시각이면 국내 입고 먼저', () => {
  const rows = F.build(F.normalize({ items: ITEMS }), [kit('k1', 'wish', 'bh-01_3')], cat); // d(신제품)가 내 프라
  assert.deepEqual(F.sortRows(rows).map((r) => r.item.id), ['d', 'a', 'b', 'c', 'e']);
  const plain = F.sortRows(F.build(F.normalize({ items: ITEMS }), [], cat)).map((r) => r.item.id);
  assert.deepEqual(plain.slice(0, 3).sort(), ['a', 'b', 'c']);
  assert.deepEqual(plain.slice(3), ['e', 'd'], '같은 시각이면 P-반다이 → 신제품 순');
  assert.equal(plain.indexOf('a') < plain.indexOf('b'), true, 'kr-restock 이 kr-new 보다 먼저');
});

test('filterRows: 종류·라인·등급·내 프라만, 연결 안 된 항목은 라인·등급 필터에서 빠진다', () => {
  const rows = F.build(F.normalize({ items: ITEMS }), [kit('k1', 'own', 'bh-01_1')], cat);
  const ids = (f, skip) => F.filterRows(rows, f, skip).map((r) => r.item.id).sort();
  assert.deepEqual(ids({}), ['a', 'b', 'c', 'd', 'e']);
  assert.deepEqual(ids({ type: 'kr-new' }), ['b', 'c']);
  assert.deepEqual(ids({ line: 'girl' }), ['d']);
  assert.deepEqual(ids({ line: 'gunpla' }), ['a', 'b']);
  assert.deepEqual(ids({ grade: 'MG' }), ['b']);
  assert.deepEqual(ids({ mine: true }), ['a']);
  assert.deepEqual(ids({ type: 'kr-new', line: 'gunpla', grade: 'MG' }), ['b']);
  assert.deepEqual(ids({ type: 'new', line: 'gunpla' }, 'type'), ['a', 'b'], 'skip: 해당 필터만 무시(칩 개수 계산용)');
  assert.deepEqual(F.gradeOptions(rows).map((g) => g.k + g.n), ['HG1', 'MG1', '30MS1']);
});

test('dateText: 종류별 문구와 예정·월 표기', () => {
  const T = '2026-10-08';
  assert.equal(F.dateText({ type: 'new', date: '2027-03' }, T), '일본 발매 예정 2027-03');
  assert.equal(F.dateText({ type: 'new', date: '2026-10' }, T), '일본 발매 2026-10', '이번 달인데 날짜를 모르면 예정이라 단정하지 않는다');
  assert.equal(F.dateText({ type: 'new', date: '2026-09' }, T), '일본 발매 2026-09');
  assert.equal(F.dateText({ type: 'pb-new', date: '2027-01' }, T), 'P-반다이 발매 예정 2027-01');
  assert.equal(F.dateText({ type: 'kr-restock', date: '2026-10-03' }, T), '국내 입고 2026-10-03');
  assert.equal(F.dateText({ type: 'kr-new', date: '2026-10-15' }, T), '국내 입고 예정 2026-10-15');
  assert.equal(F.dateText({ type: 'kr-new', date: '' }, T), '');
});

test('isFresh: 발견 3일 이내만 NEW', () => {
  assert.equal(F.isFresh({ added: '2026-10-08T15:40:41+09:00' }, '2026-10-08'), true);
  assert.equal(F.isFresh({ added: '2026-10-05T01:00:00+09:00' }, '2026-10-08'), true);
  assert.equal(F.isFresh({ added: '2026-10-04T23:00:00+09:00' }, '2026-10-08'), false);
  assert.equal(F.isFresh({ added: '' }, '2026-10-08'), false);
});

test('wishPrefill: 연결된 항목은 catalogId 와 값을, 연결 안 된 항목은 이름만 주고 찾기를 연다', () => {
  const rows = F.build(F.normalize({ items: ITEMS }), [], cat);
  const a = F.wishPrefill(rows.find((r) => r.item.id === 'a'));
  assert.equal(a.openPicker, false);
  assert.deepEqual(a.prefill, { list: 'wish', catalogId: 'bh-01_1', name: '건담 에어리얼', grade: 'HG', scale: '1/144', series: '', brand: '반다이', date: '' });
  assert.equal(P.normKit({ id: 'k', ...a.prefill }).catalogId, 'bh-01_1');
  const c = F.wishPrefill(rows.find((r) => r.item.id === 'c'));
  assert.equal(c.openPicker, true); assert.equal(c.prefill.name, '연결 안 된 입고 글'); assert.equal(c.prefill.catalogId, undefined); assert.equal(c.prefill.list, 'wish');
  assert.equal(F.wishPrefill(rows.find((r) => r.item.id === 'd')).prefill.scale, '1/144');
});
