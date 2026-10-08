// node tests/site_aliases.test.mjs — docs/aliases.js 사전 형식과 검색(별칭·꼬리말·일반어) 동작. 네트워크·DOM 없음.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const A = require('../docs/aliases.js');
const C = require('../docs/catalog.js');

const raw = (id, over = {}) => ({ id, url: `https://bandai-hobby.net/item/${id.slice(3)}/`, line: 'gunpla', grade: 'HG', scale: '1/144', series: null,
  nameJa: null, nameKo: null, release: { month: '2022-10', date: null }, kr: [], images: [], ...over });
const cat = C.build([{ items: [
  raw('bh-1', { nameKo: 'HG 1/144 건담 바르바토스' }),
  raw('bh-2', { nameKo: 'HG 1/144 건담베이스 한정 건담 바르바토스 [클리어 컬러]' }),
  raw('bh-3', { nameKo: 'HG 1/144 건담베이스 한정 세컨드V [클리어 컬러]' }),
  raw('bh-4', { nameKo: 'RG 1/144 Hi-ν 건담', grade: 'RG' }),
  raw('bh-5', { nameKo: 'RG 1/144 RX-93 ν건담', grade: 'RG' }),
  raw('bh-6', { nameKo: 'RG 1/144 RX-78-2 건담 Ver.2.0', grade: 'RG' }),
  raw('bh-7', { nameKo: 'HGUC 1/144 켐퍼 [스페셜 코팅]' }),
  raw('bh-8', { nameKo: 'HG 1/144 켐퍼' }),
  raw('bh-9', { nameKo: 'HG 1/144 건담 루브리스' }),
  raw('bh-10', { nameKo: 'HG 1/144 즈고크' }),
  raw('bh-11', { nameKo: 'HG 1/144 더블오 콴타' }),
  raw('bh-12', { nameKo: 'MG 1/100 건담 에어리얼', grade: 'MG', scale: '1/100' }),
] }], null);
const ids = (q, o) => C.search(cat, q, o).results.map((x) => x.id);

test('사전 형식: 묶음은 둘 이상, 줄임말은 값이 있고, 꼬리말·일반어는 비지 않았다', () => {
  assert.ok(A.GROUPS.length > 5 && A.GROUPS.every((g) => Array.isArray(g) && g.length >= 2 && g.every((w) => typeof w === 'string' && w.trim())));
  assert.ok(Object.values(A.EXPAND).every((v) => Array.isArray(v) && v.length >= 1));
  assert.ok(A.TAILS.every((t) => Array.isArray(t) && t.length >= 1) && A.GENERIC.length > 3);
  const kana = /[ぁ-ゖァ-ヺー]/;
  assert.ok([...A.GROUPS.flat(), ...Object.keys(A.EXPAND), ...Object.values(A.EXPAND).flat(), ...A.TAILS.flat(), ...A.GENERIC].every((w) => !kana.test(w)), '사전에 일본어 가나를 쓰지 않는다');
});

test('build: 묶음은 양방향, 줄임말은 단방향, norm 처리', () => {
  const al = A.build(C.norm);
  assert.deepEqual(al.alts(C.norm('발바토스')).sort(), [C.norm('발바토스'), C.norm('바르바토스')].sort());
  assert.ok(al.alts(C.norm('바르바토스')).includes(C.norm('발바토스')));
  assert.ok(al.alts('퍼건').includes('퍼스트건담') && al.alts('퍼건').includes('퍼건'));
  assert.deepEqual(al.alts('퍼스트건담'), ['퍼스트건담'], '정식 표기로 검색해서 줄임말을 찾지는 않는다');
  assert.deepEqual(al.alts('아무말'), ['아무말']);
  assert.ok(al.isGeneric('건담') && al.isGeneric('한정') && !al.isGeneric('바알'));
});

test('splitTails: 꼬리말(연속 낱말열)을 떼어 낸다', () => {
  const al = A.build(C.norm);
  assert.deepEqual(al.splitTails(['발바토스', '클리어']), { core: ['발바토스'], tails: [{ all: '클리어', words: ['클리어'] }] });
  const r = al.splitTails(['프리덤', '크로스', '컨트라스트', '컬러']);
  assert.deepEqual(r.core, ['프리덤']); assert.equal(r.tails[0].all, '크로스컨트라스트컬러');
  assert.deepEqual(al.splitTails(['크로스본', '마오']).core, ['크로스본', '마오'], '낱말 전체가 같을 때만 (크로스본은 꼬리말이 아니다)');
  const t = al.splitTails(['발바토스', '철혈', '코팅']);
  assert.deepEqual(t.core, ['발바토스']); assert.deepEqual(t.tails[0].words, ['철혈', '코팅']);
});

test('철자 변형·줄임말·기호: 발바토스↔바르바토스, 캠퍼↔켐퍼, 하이뉴→Hi-ν, 뉴→ν, 퍼건', () => {
  assert.equal(ids('발바토스')[0], 'bh-1');
  assert.equal(ids('르브리스')[0], 'bh-9');
  assert.equal(ids('캠퍼', { grade: 'HG' }).includes('bh-8'), true);
  assert.equal(ids('하이뉴 건담')[0], 'bh-4');
  assert.equal(ids('뉴 건담', { grade: 'RG' }).includes('bh-5'), true);
  assert.equal(ids('퍼건 2.0')[0], 'bh-6');
  assert.equal(ids('즈곡그')[0], 'bh-10');
  assert.equal(ids('퀀터')[0], 'bh-11');
  assert.deepEqual(ids('발바토스', { aliases: false }), [], '별칭을 끄면(개선 전) 못 찾는다');
  assert.deepEqual(ids('하이뉴', { aliases: false }), []);
});

test('꼬리말은 필수가 아니라 가산: 기본형도 찾고, 변형이 있으면 그쪽이 먼저', () => {
  assert.deepEqual(ids('발바토스 클리어').slice(0, 2), ['bh-2', 'bh-1']);        // 클리어 컬러 제품이 앞, 기본형도 후보
  assert.deepEqual(ids('발바토스').slice(0, 2).sort(), ['bh-1', 'bh-2']);
  assert.equal(ids('르브리스 클리어')[0], 'bh-9', '클리어 제품이 없으면 기본형이 1순위');
  assert.equal(ids('켐퍼 철혈 코팅', { grade: 'HG' })[0], 'bh-7', '"철혈 코팅"은 카탈로그의 "스페셜 코팅"과 낱말(코팅)만 맞아도 가산');
  assert.deepEqual(ids('클리어').length > 0, true, '꼬리말만 입력해도 그대로 검색된다');
});

test('일반어만 맞은 후보는 버린다 (발길 클리어 → 세컨드V[클리어 컬러] 같은 엉뚱한 연결 방지)', () => {
  assert.deepEqual(ids('발길 클리어'), []);
  assert.deepEqual(ids('바알 한정 클리어'), []);
  assert.ok(ids('건담').length >= 4, '검색어가 전부 일반어면 그대로 찾는다');
  assert.deepEqual(ids('한정 컬러').length > 0, true);
});

test('등급·스케일 낱말은 "이름이 맞았다"로 치지 않는다 (MG 바알 → MG 전체가 나오지 않는다)', () => {
  assert.deepEqual(ids('mg 존재안함'), []);
  assert.equal(ids('mg 에어리얼')[0], 'bh-12');
  assert.equal(ids('1/100 에어리얼')[0], 'bh-12');
});

test('stripPrefix: 등급 변형 머리말(HGUC·HGCE·HGBD:R)도 뗀다 → 짧은 이름이 접두 일치로 앞선다', () => {
  assert.equal(C.stripPrefix('HGUC 1/144 켐퍼 [스페셜 코팅]', 'HG', '1/144'), '켐퍼 [스페셜 코팅]');
  assert.equal(cat.byId['bh-7'].title, '켐퍼 [스페셜 코팅]');
});

test('성능: 카탈로그 3천 개에서 검색 한 번이 10ms 안쪽', () => {
  const many = C.build([{ items: Array.from({ length: 3000 }, (_, i) => raw('bh-' + (100 + i), { nameKo: `HG 1/144 건담 테스트 ${i}번` })) }], null);
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < 20; i++) C.search(many, '하이뉴 건담 클리어 ' + i);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6 / 20;
  assert.ok(ms < 10, `검색 1회 ${ms.toFixed(2)}ms`);
});
