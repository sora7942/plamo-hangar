// node tests/site_pure.test.mjs — docs/pure.js 순수 함수 (네트워크·DOM 없음)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const P = require('../docs/pure.js');

const ph = (kit, id) => ({ id, src: `photos/${kit}/${id}.webp`, thumb: `photos/${kit}/${id}_t.webp` });
const kit = (over = {}) => P.normKit({ id: 'k1', name: '건담 에어리얼', grade: 'HG', list: 'own', ...over });

test('photoOrder: cover가 없으면 내 첫 사진이 대표', () => {
  const k = kit({ photos: [ph('k1', 'pa'), ph('k1', 'pb')] });
  const o = P.photoOrder(k, []);
  assert.equal(o.cover.key, 'my:pa');
  assert.deepEqual(o.list.map((x) => x.key), ['my:pa', 'my:pb']);
});

test('photoOrder: cover 지정 → 대표 먼저, 나머지 공식(사이트 순서), 나머지 내 사진', () => {
  const k = kit({ photos: [ph('k1', 'pa'), ph('k1', 'pb')], cover: 'my:pb' });
  const o = P.photoOrder(k, ['https://bandai-a.akamaihd.net/a.jpg', 'https://bandai-a.akamaihd.net/b.jpg']);
  assert.deepEqual(o.list.map((x) => x.key), ['my:pb', 'off:0', 'off:1', 'my:pa']);
});

test('photoOrder: 공식 사진이 대표(off:n)', () => {
  const k = kit({ photos: [ph('k1', 'pa')], cover: 'off:1' });
  const o = P.photoOrder(k, ['https://bandai-a.akamaihd.net/a.jpg', 'https://bandai-a.akamaihd.net/b.jpg']);
  assert.deepEqual(o.list.map((x) => x.key), ['off:1', 'off:0', 'my:pa']);
});

test('photoOrder: 내 사진이 없으면 공식 첫 사진이 대표, 둘 다 없으면 null', () => {
  assert.equal(P.photoOrder(kit(), ['https://bandai-a.akamaihd.net/a.jpg']).cover.key, 'off:0');
  assert.equal(P.photoOrder(kit(), []).cover, null);
  assert.equal(P.hasPhoto(kit(), []), false);
});

test('photoOrder: 깨진 cover(없는 id, 범위 밖 off)는 기본값으로 폴백', () => {
  const k = kit({ photos: [ph('k1', 'pa')], cover: 'my:zzz' });
  assert.equal(P.photoOrder(k, []).cover.key, 'my:pa');
  const k2 = kit({ photos: [ph('k1', 'pa')], cover: 'off:7' });
  assert.equal(P.photoOrder(k2, ['https://bandai-a.akamaihd.net/a.jpg']).cover.key, 'my:pa');
});

test('사진 추가·이동·삭제·대표 지정', () => {
  let k = kit();
  k = P.addPhotos(k, [ph('k1', 'pa'), ph('k1', 'pb'), ph('k1', 'pc')]);
  assert.deepEqual(k.photos.map((p) => p.id), ['pa', 'pb', 'pc']);
  k = P.movePhoto(k, 'pc', -1);
  assert.deepEqual(k.photos.map((p) => p.id), ['pa', 'pc', 'pb']);
  k = P.movePhoto(k, 'pa', -1); // 맨 앞은 그대로
  assert.deepEqual(k.photos.map((p) => p.id), ['pa', 'pc', 'pb']);
  k = P.setCover(k, 'my:pc');
  assert.equal(k.cover, 'my:pc');
  k = P.removePhoto(k, 'pc'); // 대표를 지우면 cover 초기화
  assert.equal(k.cover, null);
  assert.deepEqual(k.photos.map((p) => p.id), ['pa', 'pb']);
  assert.equal(P.setCover(k, 'my:없음').cover, null); // 없는 사진은 지정 불가
  assert.equal(P.setCover(P.setCover(k, 'my:pa'), null).cover, null);
});

test('addPhotos: 중복 id 무시, 최대 장수 제한', () => {
  let k = P.addPhotos(kit(), [ph('k1', 'pa'), ph('k1', 'pa')]);
  assert.equal(k.photos.length, 1);
  const many = Array.from({ length: P.MAX_PHOTOS + 5 }, (_, i) => ph('k1', 'p' + i));
  k = P.addPhotos(kit(), many);
  assert.equal(k.photos.length, P.MAX_PHOTOS);
});

test('경로 검증: 안전한 photos/ 경로만 통과', () => {
  assert.equal(P.isSafePhotoPath('photos/k1/pa.webp'), true);
  assert.equal(P.isSafePhotoPath('photos/k1/pa_t.webp'), true);
  for (const bad of ['javascript:alert(1)', 'https://evil.example/x.webp', '../photos/k1/pa.webp', 'photos/../x/pa.webp', 'photos/k1/pa.png', 'photos/k1/a/b.webp', '', null, undefined, 3]) {
    assert.equal(P.isSafePhotoPath(bad), false, String(bad));
  }
  assert.throws(() => P.photoPaths('k1', '../x'));
  assert.deepEqual(P.photoPaths('k1', 'pa'), { src: 'photos/k1/pa.webp', thumb: 'photos/k1/pa_t.webp' });
});

test('normKit: 위험한 사진 경로·깨진 cover 제거, 옛 photo 필드 삭제, 기본값 채움', () => {
  const k = P.normKit({ id: 'k9', name: 'x', photo: 'data:image/jpeg;base64,AAAA', catalogId: 5, cover: 'bad',
    photos: [{ id: 'a', src: 'javascript:1', thumb: 'photos/k9/a_t.webp' }, ph('k9', 'b')], status: 'constructor' });
  assert.equal('photo' in k, false);
  assert.equal(k.catalogId, null);
  assert.equal(k.cover, null);
  assert.deepEqual(k.photos.map((p) => p.id), ['b']);
  assert.equal(k.status, 'unbuilt');
  assert.equal(k.list, 'own');
});

test('planPhotoFiles: 추가·삭제 경로와 장수', () => {
  const prev = [kit({ id: 'k1', photos: [ph('k1', 'pa'), ph('k1', 'pb')] }), kit({ id: 'k2', photos: [ph('k2', 'pz')] })];
  const next = [kit({ id: 'k1', photos: [ph('k1', 'pb'), ph('k1', 'pc')] })]; // pa 삭제, pc 추가, k2 통째 삭제
  const plan = P.planPhotoFiles(prev, next);
  assert.deepEqual(plan.add, ['docs/photos/k1/pc.webp', 'docs/photos/k1/pc_t.webp']);
  assert.deepEqual(plan.remove, ['docs/photos/k1/pa.webp', 'docs/photos/k1/pa_t.webp', 'docs/photos/k2/pz.webp', 'docs/photos/k2/pz_t.webp']);
  assert.equal(plan.addedPhotos, 1);
  assert.equal(plan.removedPhotos, 2);
});

test('중복 판정: 등급 접두어·공백·기호 무시, 등급이 다르면 다른 프라, 자기 자신 제외', () => {
  const pool = [kit({ id: 'a', name: 'HG 건담 에어리얼', grade: 'HG' }), kit({ id: 'b', name: '건담 에어리얼', grade: 'RG' })];
  assert.deepEqual(P.findDups('건담-에어리얼', 'HG', null, pool).map((k) => k.id), ['a']);
  assert.deepEqual(P.findDups('건담 에어리얼', 'RG', null, pool).map((k) => k.id), ['b']);
  assert.deepEqual(P.findDups('건담 에어리얼', 'HG', 'a', pool), []);
  assert.deepEqual(P.findDups('', 'HG', null, pool), []);
  assert.deepEqual(P.findDups('다른 건담', 'HG', null, pool), []);
});

test('빈 칸 모아보기: 사진 없음은 photos 기준', () => {
  assert.equal(P.GAPS.photo.t(kit()), true);
  assert.equal(P.GAPS.photo.t(kit({ photos: [ph('k1', 'pa')] })), false);
  assert.equal(P.GAPS.purchase.t(kit({ date: '2026-01-01', shop: 'a', price: 1 })), false);
  assert.equal(P.GAPS.done.t(kit({ status: 'built' })), true);
});

test('filterSort: 탭·등급·상태·검색·정렬', () => {
  const kits = [
    kit({ id: '1', name: '가', grade: 'HG', date: '2026-01-01', status: 'built', tags: ['재판'] }),
    kit({ id: '2', name: '나', grade: 'MG', date: '2026-03-01', status: 'unbuilt' }),
    kit({ id: '3', name: '다', grade: 'HG', list: 'wish', created: '2026-02-01' }),
  ];
  const ui = { tab: 'own', q: '', grade: 'all', status: 'all', tag: 'all', gap: 'all', sort: 'recent' };
  assert.deepEqual(P.filterSort(kits, ui).map((k) => k.id), ['2', '1']);
  assert.deepEqual(P.filterSort(kits, { ...ui, grade: 'HG' }).map((k) => k.id), ['1']);
  assert.deepEqual(P.filterSort(kits, { ...ui, status: 'unbuilt' }).map((k) => k.id), ['2']);
  assert.deepEqual(P.filterSort(kits, { ...ui, tag: '재판' }).map((k) => k.id), ['1']);
  assert.deepEqual(P.filterSort(kits, { ...ui, q: '재판' }).map((k) => k.id), ['1']);
  assert.deepEqual(P.filterSort(kits, { ...ui, sort: 'name' }).map((k) => k.id), ['1', '2']);
  assert.deepEqual(P.filterSort(kits, { ...ui, tab: 'wish' }).map((k) => k.id), ['3']);
});

test('applyBulk: 값이 빈 항목에만 채우기 on/off, 목록·상태는 항상 변경, 태그 붙이기·떼기', () => {
  const mk = () => [kit({ id: 'a', shop: '', price: 0, tags: ['x', 'old'] }), kit({ id: 'b', shop: '기존점', price: 5000 }), kit({ id: 'c', shop: '', price: 0 })];
  let k = P.applyBulk(mk(), ['a', 'b'], { sets: { status: 'built', grade: P.BULK_KEEP }, fills: { shop: '새점' }, price: 9000, add: ['new', 'x'], rem: ['old'], onlyEmpty: true });
  assert.equal(k[0].shop, '새점'); assert.equal(k[0].price, 9000); assert.deepEqual(k[0].tags, ['x', 'new']);
  assert.equal(k[1].shop, '기존점'); assert.equal(k[1].price, 5000); // 비어 있지 않아 유지
  assert.equal(k[0].status, 'built'); assert.equal(k[1].status, 'built'); assert.equal(k[0].grade, 'HG');
  assert.equal(k[2].status, 'unbuilt'); // 선택 안 한 것
  k = P.applyBulk(mk(), ['b'], { fills: { shop: '새점' }, price: 9000, onlyEmpty: false });
  assert.equal(k[1].shop, '새점'); assert.equal(k[1].price, 9000);
});

test('가져오기 파싱: 헤더 자동 인식, 위시, 날짜 형식', () => {
  const rows = P.parseDelimited('목록,이름,등급,스케일,상태,구매일,가격,태그\n위시리스트,"건담, 캘리번",HG,,,,22000,P-반다이\n보유,RX-78-2 Ver.3.0,MG,,완성,2026.3.15,"45,000",재판;클리어\n,,,,,,,\n');
  const { kits, skipped } = P.rowsToKits(rows, { idFn: () => 'k', now: 0 });
  assert.equal(kits.length, 2); assert.equal(skipped, 0);
  assert.equal(kits[0].list, 'wish'); assert.equal(kits[0].name, '건담, 캘리번'); assert.equal(kits[0].price, 22000); assert.equal(kits[0].date, '');
  assert.equal(kits[1].grade, 'MG'); assert.equal(kits[1].scale, '1/100'); assert.equal(kits[1].status, 'built');
  assert.equal(kits[1].date, '2026-03-15'); assert.equal(kits[1].price, 45000); assert.deepEqual(kits[1].tags, ['재판', '클리어']);
  assert.deepEqual(kits.map((k) => k.photos), [[], []]);
});

test('가져오기 파싱: 제목 없는 표는 기본 열 순서, 이름 없는 행은 건너뜀', () => {
  const { kits, skipped } = P.rowsToKits(P.parseDelimited('건담 에어리얼\tHG\t1/144\t수성의 마녀\t완성\n\tHG\n'), { idFn: () => 'k', now: 0 });
  assert.equal(kits.length, 1); assert.equal(skipped, 1);
  assert.equal(kits[0].series, '수성의 마녀'); assert.equal(kits[0].status, 'built');
});

test('엑셀 백업 행: 목록·상태·태그·가격 변환', () => {
  const rows = P.exportRows([kit({ name: 'a', tags: ['x', 'y'], price: 100, status: 'building' }), kit({ id: 'k2', name: 'b', list: 'wish' })]);
  assert.equal(rows[0][1], '이름');
  assert.equal(rows[1][0], '보유'); assert.equal(rows[1][6], '조립 중'); assert.equal(rows[1][10], 'x, y'); assert.equal(rows[1][9], 100);
  assert.equal(rows[2][0], '위시리스트'); assert.equal(rows[2][6], '');
});

test('serialize: 한 kit 한 줄, 왕복, 빈 컬렉션', () => {
  const d = P.normalizeData({ settings: { name: '내 격납고' }, kits: [kit({ id: 'k1', name: '가', photos: [ph('k1', 'pa')], cover: 'my:pa' }), kit({ id: 'k2', name: '한글 "따옴표"' })] });
  const text = P.serialize(d);
  const NL = String.fromCharCode(10);
  const lines = text.trimEnd().split(NL);
  assert.equal(lines.length, 5); // 헤더 / "kits":[ / kit / kit / ]}
  assert.ok(lines[2].startsWith(' {') && lines[2].endsWith('},'));
  assert.ok(text.endsWith(NL));
  assert.deepEqual(P.parseData(text), d);
  const empty = P.serialize({});
  assert.equal(empty, '{"version":3,"settings":{"name":"프라 격납고","hidePurchase":true,"hideOfficialPhotos":false},' + NL + '"kits":[]}' + NL);
  assert.deepEqual(P.parseData(empty).kits, []);
  assert.deepEqual(P.parseData('').kits, []);
});

test('normalizeData: 설정 기본값과 version', () => {
  const d = P.normalizeData({ settings: { hidePurchase: false }, kits: [null, { name: 'a' }, 'x'] });
  assert.equal(d.version, 3);
  assert.equal(d.settings.hidePurchase, false);
  assert.equal(d.settings.hideOfficialPhotos, false);
  assert.equal(d.settings.name, '프라 격납고');
  assert.equal(d.kits.length, 1);
  assert.ok(d.kits[0].id);
});

test('parseV2Json: 옛 photo(data URI)를 분리하고 id를 보존, kit-data 스크립트 통째로도 읽음', () => {
  const uri = 'data:image/jpeg;base64,/9j/4AAQ';
  const json = JSON.stringify({ settings: { name: 'v2' }, kits: [{ id: 'kold', name: '건담', grade: 'HG', photo: uri, tags: ['a'] }, { id: 'k2', name: '사진없음', photo: '' }, { name: '' }] });
  for (const input of [json, `<html><script type="application/json" id="kit-data">${json}</script></html>`]) {
    const r = P.parseV2Json(input);
    assert.equal(r.kits.length, 2);
    assert.equal(r.kits[0].id, 'kold');
    assert.deepEqual(r.kits[0].photos, []);
    assert.equal('photo' in r.kits[0], false);
    assert.deepEqual(Object.keys(r.legacy), ['kold']);
  }
  assert.throws(() => P.parseV2Json('{"x":1}'));
  const bad = P.parseV2Json(JSON.stringify({ kits: [{ name: 'a', photo: 'https://evil.example/x.png' }, { name: 'b', photo: 'data:text/html;base64,PGI+' }] }));
  assert.deepEqual(bad.legacy, {}); // 이미지가 아닌 data URI·외부 URL은 받지 않는다
});

test('dataUriToBytes: base64 → 바이트', () => {
  const r = P.dataUriToBytes('data:image/png;base64,iVBORw0KGgo=');
  assert.equal(r.type, 'image/png');
  assert.deepEqual(Array.from(r.bytes), [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  assert.equal(P.dataUriToBytes('javascript:alert(1)'), null);
});

test('commitMessage: collection: 접두어, 요약, 사진 증감, 긴 이름 자르기·개행 제거', () => {
  assert.equal(P.commitMessage('add', { name: '건담 에어리얼' }), 'collection: 추가 건담 에어리얼');
  assert.equal(P.commitMessage('edit', { name: 'a', photosAdded: 2, photosRemoved: 1 }), 'collection: 수정 a · 사진 +2 -1');
  assert.equal(P.commitMessage('bulk-edit', { n: 3 }), 'collection: 3개 일괄 수정');
  assert.equal(P.commitMessage('bulk-delete', { n: 2 }), 'collection: 2개 일괄 삭제');
  assert.equal(P.commitMessage('import', { n: 7 }), 'collection: 7개 가져오기');
  assert.equal(P.commitMessage('settings'), 'collection: 설정');
  const long = P.commitMessage('add', { name: '가'.repeat(100) + String.fromCharCode(10) + '둘째줄' });
  assert.ok(!long.includes(String.fromCharCode(10)) && long.length < 70);
});

test('esc: HTML 특수문자 이스케이프', () => {
  assert.equal(P.esc(`<img src=x onerror="a()">&'`), '&lt;img src=x onerror=&quot;a()&quot;&gt;&amp;&#39;');
  assert.equal(P.esc(null), '');
  assert.equal(P.gk('RE/100'), 'RE100');
  assert.equal(P.gk('<b>'), 'etc');
  assert.equal(P.gname('<b>'), '기타');
});

test('days / splitTags / won', () => {
  assert.equal(P.days('2026-01-01', '2026-01-03'), 3);
  assert.equal(P.days('2026-01-03', '2026-01-01'), null);
  assert.equal(P.days('', '2026-01-01'), null);
  assert.deepEqual(P.splitTags('a, b;a #c'), ['a', 'b', 'c']);
  assert.equal(P.won(45000), '45,000원');
});

test('등급: 카탈로그 등급 이름 → 사이트 등급, FULL MECHANICS는 FM', () => {
  assert.equal(P.catalogGrade('FULL MECHANICS'), 'FM');
  assert.equal(P.catalogGrade('30MS'), '30MS');
  assert.equal(P.catalogGrade('Figure-rise Standard Amplified'), 'Figure-rise Standard Amplified');
  assert.equal(P.catalogGrade('SDCS'), 'SDCS');
  assert.equal(P.catalogGrade('모르는 등급'), '기타');
  assert.equal(P.gname('Figure-rise Standard'), 'Figure-rise Standard');
  assert.equal(P.gk('Figure-rise Standard'), 'FigureriseStandard');
  assert.equal(P.glabel('Figure-rise Standard Amplified'), 'FRS-A');
  assert.equal(P.glabel('HG'), 'HG');
});

test('엑셀 가져오기 등급 매핑: 긴 이름 먼저, BB는 BB로 유지', () => {
  assert.equal(P.normGrade('SDCS', ''), 'SDCS');
  assert.equal(P.normGrade('', 'SDEX 건담'), 'SDEX');
  assert.equal(P.normGrade('BB', ''), 'BB');
  assert.equal(P.normGrade('Full Mechanics', ''), 'FM');
  assert.equal(P.normGrade('30MS', ''), '30MS');
  assert.equal(P.normGrade('Figure-rise Standard', ''), 'Figure-rise Standard');
  assert.equal(P.normGrade('Figure-rise Standard Amplified', ''), 'Figure-rise Standard Amplified');
  assert.equal(P.normGrade('MGSD', ''), 'MGSD');
  assert.equal(P.normGrade('MG', ''), 'MG');
  assert.equal(P.normGrade('RE100', ''), 'RE/100');
  assert.equal(P.normGrade('', '이름만'), '기타');
});

test('catalogId: bh-/pb- 형식만 받고 나머지는 null, 연결 커밋 메시지', () => {
  assert.equal(P.normKit({ id: 'k1', name: 'a', catalogId: 'bh-01_4257' }).catalogId, 'bh-01_4257');
  assert.equal(P.normKit({ id: 'k1', name: 'a', catalogId: 'pb-item-1000179163' }).catalogId, 'pb-item-1000179163');
  for (const bad of ['', '01_4257', 'x-1', 'bh-', 'bh-<script>', 'bh-' + 'a'.repeat(70), 5, {}]) assert.equal(P.normKit({ id: 'k1', name: 'a', catalogId: bad }).catalogId, null, String(bad));
  assert.equal(P.commitMessage('link', { name: '건담 에어리얼' }), 'collection: 반다이 제품 연결 건담 에어리얼');
  assert.equal(P.commitMessage('unlink', { name: '건담 에어리얼' }), 'collection: 반다이 제품 연결 해제 건담 에어리얼');
});

test('재판 공백 정렬: 국내 입고 오래된 순 → 기록 없음(일본 발매 오래된 순) → 미연결, 같으면 이름', () => {
  const mk = (id, name, extra) => P.normKit({ id, name, list: 'own', grade: 'HG', ...extra });
  const kits = [
    mk('u1', '가 미연결'), mk('n2', '나 기록없음 최근발매', { catalogId: 'bh-01_2' }), mk('k2', '다 입고 최근', { catalogId: 'bh-01_3' }),
    mk('n1', '라 기록없음 오래된발매', { catalogId: 'bh-01_1' }), mk('k1', '마 입고 오래전', { catalogId: 'bh-01_4' }), mk('x1', '바 카탈로그에 없음', { catalogId: 'bh-01_9' }),
  ];
  const gaps = { 'bh-01_1': { group: 1, key: '2019-05-31' }, 'bh-01_2': { group: 1, key: '2025-03-31' }, 'bh-01_3': { group: 0, key: '2026-09-29' }, 'bh-01_4': { group: 0, key: '2024-04-01' } };
  const ctx = { gap: (k) => gaps[k.catalogId] || null };
  const ui = { q: '', grade: 'all', status: 'all', sort: 'gap', tab: 'own', tag: 'all', gap: 'all' };
  assert.deepEqual(P.filterSort(kits, ui, ctx).map((k) => k.id), ['k1', 'k2', 'n1', 'n2', 'u1', 'x1']);
  assert.deepEqual(P.filterSort(kits, ui).map((k) => k.id), ['u1', 'n2', 'k2', 'n1', 'k1', 'x1'].sort((a, b) => kits.find((k) => k.id === a).name.localeCompare(kits.find((k) => k.id === b).name, 'ko')), 'ctx가 없으면 모두 미연결 취급 → 이름순');
});

test('빈 칸 모아보기: 반다이 제품 미연결', () => {
  assert.equal(P.GAPS.unlinked.t(P.normKit({ id: 'a', name: 'a' })), true);
  assert.equal(P.GAPS.unlinked.t(P.normKit({ id: 'a', name: 'a', catalogId: 'bh-01_1' })), false);
  const kits = [P.normKit({ id: 'a', name: 'a' }), P.normKit({ id: 'b', name: 'b', catalogId: 'bh-01_1' })];
  assert.deepEqual(P.filterSort(kits, { q: '', grade: 'all', status: 'all', sort: 'name', tab: 'own', tag: 'all', gap: 'unlinked' }).map((k) => k.id), ['a']);
});
