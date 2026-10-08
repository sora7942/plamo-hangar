// node tests/site_assist.test.mjs — docs/assist.js 연결 도우미의 진행 상태 (순수, 네트워크·DOM 없음)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const S = require('../docs/assist.js');

const kit = (id, extra = {}) => ({ id, name: '프라 ' + id, ...extra });
const KITS = ['a', 'b', 'c', 'd'].map((i) => kit(i));

test('큐: 연결된 프라는 빼고, 나중에로 미룬 프라는 맨 끝으로, 건너뛴 프라는 이어 가기에서 뺀다', () => {
  const s = S.createSession([kit('a'), kit('b', { catalogId: 'bh-01_1' }), kit('c'), kit('d'), kit('e')], { deferred: ['c'], skipped: ['d'] });
  const seen = [];
  while (!s.done()) { seen.push(s.current().id); s.skip(); }
  assert.deepEqual(seen, ['a', 'e', 'c']);                                   // a, e 다음에 나중에로 미룬 c. b(연결됨)·d(건너뜀)는 없다
  assert.deepEqual(S.createSession([], {}).current(), null);
  assert.equal(S.createSession([kit('a'), kit('a')], {}).position().total, 1, '같은 id는 한 번만');
});

test('연결: 대기열에 모으고 다음으로, 통계·pendingMap', () => {
  const s = S.createSession(KITS);
  assert.deepEqual(s.stats(), { pending: 0, skipped: 0, later: 0, left: 4 });
  assert.equal(s.current().id, 'a');
  assert.equal(s.link('bh-01_5'), true);
  assert.equal(s.current().id, 'b');
  assert.equal(s.link(''), false, 'catalogId가 없으면 연결하지 않는다');
  s.skip(); s.later();
  assert.deepEqual(s.stats(), { pending: 1, skipped: 1, later: 1, left: 1 });
  assert.deepEqual(s.pendingMap(), { a: 'bh-01_5' });
  assert.deepEqual(s.deferredIds(), ['c']); assert.deepEqual(s.skippedIds(), ['b']);
  assert.deepEqual(s.position(), { index: 3, total: 4 });
  s.link('bh-01_6');
  assert.equal(s.done(), true); assert.equal(s.current(), null);
  assert.equal(s.link('x'), false); assert.equal(s.skip(), false); assert.equal(s.later(), false);
});

test('이전(되돌리기): 마지막 동작을 취소하고 그 프라로 돌아간다 — 연결·건너뛰기·나중에 모두', () => {
  const s = S.createSession(KITS);
  s.link('bh-01_1'); s.skip(); s.later();
  assert.equal(s.canBack(), true);
  assert.equal(s.back(), true); assert.equal(s.current().id, 'c'); assert.deepEqual(s.deferredIds(), []);
  assert.equal(s.back(), true); assert.equal(s.current().id, 'b'); assert.deepEqual(s.skippedIds(), []);
  assert.equal(s.back(), true); assert.equal(s.current().id, 'a'); assert.deepEqual(s.pendingMap(), {});
  assert.equal(s.canBack(), false); assert.equal(s.back(), false);
  const d = S.createSession(KITS, { deferred: ['a'] });
  assert.equal(d.current().id, 'b');                                       // a는 미뤄 둔 상태라 끝으로
  d.skip(); d.skip(); d.skip();
  assert.equal(d.current().id, 'a');
  d.link('bh-01_2');                                                       // 미뤄 둔 프라를 연결하면 나중에 목록에서 빠진다
  assert.deepEqual(d.deferredIds(), []);
  d.back();
  assert.deepEqual(d.deferredIds(), ['a'], '되돌리면 다시 나중에 목록에');
  d.later(); assert.deepEqual(d.deferredIds(), ['a']);
  d.back(); assert.deepEqual(d.deferredIds(), ['a'], '이미 미뤄 둔 프라를 다시 나중에 했다가 되돌려도 유지');
});

test('끝에서 다시 보기: 건너뛴 것·나중에로 미룬 것을 이어서 보여 준다 (연결 대기 중인 것은 제외)', () => {
  const s = S.createSession(KITS);
  s.link('bh-01_1'); s.skip(); s.later(); s.skip();
  assert.equal(s.done(), true);
  assert.equal(s.reviewSkipped(), 2);                                      // b, d
  assert.deepEqual(s.skippedIds(), []);
  assert.equal(s.current().id, 'b');
  s.link('bh-01_2'); assert.equal(s.current().id, 'd');
  s.later();                                                               // d는 이제 나중에로
  assert.equal(s.done(), true);
  assert.equal(s.reviewLater(), 2); assert.equal(s.current().id, 'c');       // c, d
  assert.equal(s.reviewLater(), 2, '다시 눌러도 같은 목록이 이어진다');
  assert.equal(S.createSession(KITS).reviewSkipped(), 0);
  assert.equal(S.createSession(KITS).reviewLater(), 0);
});

test('저장 후: afterSave는 대기열만 비운다 (건너뜀·나중에는 유지)', () => {
  const s = S.createSession(KITS);
  s.link('bh-01_1'); s.link('bh-01_2'); s.skip(); s.later();
  assert.equal(s.pendingCount(), 2);
  assert.equal(s.afterSave(), 2);
  assert.deepEqual(s.stats(), { pending: 0, skipped: 1, later: 1, left: 0 });
  // 저장 뒤 다시 열 때: 연결된 프라는 빠지고 건너뛴 프라는 이어서 넘긴다
  const next = S.createSession([kit('a', { catalogId: 'bh-01_1' }), kit('b', { catalogId: 'bh-01_2' }), ...KITS.slice(2)], { skipped: ['c'], deferred: ['d'] });
  assert.equal(next.done(), false); assert.equal(next.current().id, 'd');
});

test('나중에 목록 정리: 실제로 미연결인 프라 id만, 중복·이상한 값 제거, 상한', () => {
  const kits = [kit('a'), kit('b', { catalogId: 'bh-01_1' }), kit('c')];
  assert.deepEqual(S.cleanLater(['a', 'b', 'c', 'a', 5, null, '없는id'], kits), ['a', 'c']);
  assert.deepEqual(S.cleanLater('x', kits), []);
  const many = Array.from({ length: 600 }, (_, i) => kit('k' + i));
  assert.equal(S.cleanLater(many.map((k) => k.id), many).length, S.MAX_LATER);
  const s = S.createSession(many);
  for (let i = 0; i < S.MAX_LATER; i++) assert.equal(s.later(), true);
  assert.equal(s.later(), false, '상한에 닿으면 더 미룰 수 없다');
});
