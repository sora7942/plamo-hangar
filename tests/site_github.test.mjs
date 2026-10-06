// node tests/site_github.test.mjs — docs/github.js 를 가짜 GitHub(tests/helpers/fake-github.js)으로 (네트워크·실제 토큰 없음)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const FakeGitHub = require('./helpers/fake-github.js');
const GH = require('../docs/github.js');

const TOKEN = 'ghp_SECRET_value_that_must_never_leak';
const REPO = 'sora7942/plamo-hangar';
const COLL = 'docs/data/collection.json';
const FEED = 'docs/data/feed.json';
const text = (n) => `{"version":3,"settings":{"name":"한글 격납고"},\n"kits":[${n}]}\n`;

function setup(extra = {}) {
  const fake = FakeGitHub.create({ token: TOKEN, seed: { [COLL]: text('"seed"'), [FEED]: '{"n":1}', 'docs/data/meta.json': '{}' }, ...extra });
  const seen = []; // 토큰이 URL·본문에 새는지 보려고 실제 전송 내용을 기록
  const fetch = (u, init) => { seen.push({ url: String(u), body: init && init.body ? String(init.body) : '', auth: init && init.headers && init.headers.Authorization }); return fake.fetch(u, init); };
  const store = GH.create({ fetch, token: TOKEN, repo: REPO });
  return { fake, store, seen };
}
const plan = (collectionText, more = {}) => ({ message: 'collection: 테스트', collectionText, files: [], deletes: [], ...more });
const noLeak = (err) => { assert.ok(!String(err.message).includes(TOKEN)); assert.ok(!JSON.stringify(err).includes(TOKEN)); };

/* ---------- 소유자 판정 · 읽기 ---------- */
test('connect: push true/false, default_branch', async () => {
  const a = setup(); assert.deepEqual(await a.store.connect(), { push: true, branch: 'main' });
  const b = setup({ accountPush: false }); assert.equal((await b.store.connect()).push, false);
});

test('connect: 잘못된 토큰은 auth 오류', async () => {
  const fake = FakeGitHub.create({ token: TOKEN, seed: {} });
  const store = GH.create({ fetch: fake.fetch, token: 'wrong', repo: REPO });
  await assert.rejects(store.connect(), (e) => { assert.equal(e.kind, 'auth'); assert.equal(e.status, 401); return true; });
});

test('read: 한글 본문 디코드, baseSha·baseBlobSha 보관', async () => {
  const { fake, store } = setup();
  const r = await store.read();
  assert.equal(r.text, text('"seed"'));
  assert.equal(r.head, fake.headSha());
  assert.equal(r.blobSha, fake.blobSha(COLL));
  assert.deepEqual(store.state().baseSha, fake.headSha());
});

test('read: 1MB 넘어 content가 비어 오면 blob API로 읽는다', async () => {
  const { fake, store } = setup({ inlineLimit: 10 });
  const r = await store.read();
  assert.equal(r.text, text('"seed"'));
  assert.equal(fake.count('GET', /\/git\/blobs\//), 1);
});

test('read: 파일이 아직 없으면 text null', async () => {
  const fake = FakeGitHub.create({ token: TOKEN, seed: { [FEED]: '{}' } });
  const store = GH.create({ fetch: fake.fetch, token: TOKEN, repo: REPO });
  const r = await store.read();
  assert.equal(r.text, null); assert.equal(r.blobSha, null);
});

/* ---------- 저장 1회 = 커밋 1개 ---------- */
test('commit: 정확히 커밋 POST 1 + ref PATCH 1, 사진 추가·삭제가 한 커밋 트리에', async () => {
  const { fake, store, seen } = setup({ seed: { [COLL]: text('"seed"'), 'docs/photos/k0/old.webp': 'OLD', 'docs/photos/k0/old_t.webp': 'OLDT' } });
  await store.read();
  fake.resetLog();
  const img = (s) => new TextEncoder().encode(s);
  const r = await store.commit(plan(text('"new"'), {
    files: [{ path: 'docs/photos/k1/pa.webp', bytes: img('FULL') }, { path: 'docs/photos/k1/pa_t.webp', bytes: img('THUMB') }],
    deletes: ['docs/photos/k0/old.webp', 'docs/photos/k0/old_t.webp'],
  }));
  assert.equal(r.ok, true);
  assert.equal(fake.count('POST', /\/git\/commits$/), 1);
  assert.equal(fake.count('PATCH', /\/git\/refs\/heads\/main$/), 1);
  assert.equal(fake.count('POST', /\/git\/blobs$/), 3); // collection + 사진 2
  assert.equal(fake.count('POST', /\/git\/trees$/), 1);
  const h = fake.clientHistory(); assert.equal(h.length, 1);
  assert.equal(h[0].message, 'collection: 테스트');
  assert.deepEqual(h[0].changes.added, ['docs/photos/k1/pa.webp', 'docs/photos/k1/pa_t.webp']);
  assert.deepEqual(h[0].changes.modified, [COLL]);
  assert.deepEqual(h[0].changes.deleted, ['docs/photos/k0/old.webp', 'docs/photos/k0/old_t.webp']);
  assert.equal(fake.fileText(COLL), text('"new"'));
  assert.equal(fake.fileText('docs/photos/k1/pa.webp'), 'FULL');
  // 토큰은 Authorization 헤더로만: URL·본문에는 없다
  assert.ok(seen.every((s) => s.auth === 'Bearer ' + TOKEN));
  assert.ok(seen.every((s) => !s.url.includes(TOKEN) && !s.body.includes(TOKEN)));
});

test('commit: 진행 콜백(onProgress)이 blob 업로드마다 호출', async () => {
  const { store } = setup(); await store.read();
  const ticks = [];
  await store.commit(plan(text('1'), { files: [{ path: 'docs/photos/k/a.webp', bytes: new Uint8Array([1]) }, { path: 'docs/photos/k/a_t.webp', bytes: new Uint8Array([2]) }], onProgress: (d, t) => ticks.push([d, t]) }));
  assert.deepEqual(ticks.map((x) => x[1]), [3, 3, 3]);
  assert.equal(ticks[ticks.length - 1][0], 3);
});

test('commit 연속 2회: 두 번째는 첫 커밋의 sha·blob 위에서 충돌 없이', async () => {
  const { fake, store } = setup(); await store.read();
  await store.commit(plan(text('1')));
  let called = 0;
  const r = await store.commit(plan(text('2'), { onConflict: () => { called++; return null; } }));
  assert.equal(r.ok, true); assert.equal(called, 0);
  assert.equal(fake.clientHistory().length, 2);
});

/* ---------- 충돌 판정: collection.json blob sha 기준 ---------- */
test('다른 파일만 바뀜(크롤러 커밋) → 대화상자 없이 1커밋, 부모=최신 head, 그 파일 변경 보존', async () => {
  const { fake, store } = setup(); await store.read();
  const crawl = fake.advanceHead({ files: { [FEED]: '{"n":2}', 'docs/data/catalog-gunpla.json': '[]' }, message: 'data: crawl' });
  let called = 0;
  const r = await store.commit(plan(text('"mine"'), { onConflict: () => { called++; return null; } }));
  assert.equal(called, 0);
  assert.equal(r.ok, true);
  assert.deepEqual(fake.commit(r.sha).parents, [crawl]);
  assert.equal(fake.fileText(FEED), '{"n":2}');
  assert.equal(fake.fileText('docs/data/catalog-gunpla.json'), '[]');
  assert.equal(fake.fileText(COLL), text('"mine"'));
  assert.equal(fake.clientHistory().length, 1);
  assert.deepEqual(fake.commit(r.sha).changes.modified, [COLL]); // 내 커밋은 collection.json만 건드렸다
});

test('ref PATCH가 422(GET ref와 PATCH 사이에 다른 파일 커밋) → 조용히 재시도해 1커밋', async () => {
  const { fake, store } = setup(); await store.read();
  fake.hooks.beforePatchRef.push((api) => api.advanceHead({ files: { 'docs/data/meta.json': '{"at":1}' }, message: 'data: crawl' }));
  let called = 0;
  const r = await store.commit(plan(text('"mine"'), { onConflict: () => { called++; return null; } }));
  assert.equal(called, 0);
  assert.equal(r.ok, true); assert.equal(r.attempts, 2);
  assert.equal(fake.clientHistory().length, 1);
  assert.equal(fake.fileText('docs/data/meta.json'), '{"at":1}');
  assert.equal(fake.fileText(COLL), text('"mine"'));
});

test('422가 3회 연속 → retry-exhausted(충돌 콜백 없음), 커밋 0', async () => {
  const { fake, store } = setup(); await store.read();
  for (let i = 0; i < 3; i++) fake.hooks.beforePatchRef.push((api) => api.advanceHead({ files: { 'docs/data/meta.json': '{"at":' + i + '}' } }));
  let called = 0;
  await assert.rejects(store.commit(plan(text('"mine"'), { onConflict: () => { called++; return null; } })), (e) => { assert.equal(e.kind, 'retry-exhausted'); noLeak(e); return true; });
  assert.equal(called, 0);
  assert.equal(fake.clientHistory().length, 0);
  assert.equal(fake.fileText(COLL), text('"seed"'));
});

test('collection.json이 바뀜 → 콜백 1회, 취소하면 커밋 0', async () => {
  const { fake, store } = setup(); await store.read();
  fake.advanceHead({ files: { [COLL]: text('"remote"') }, message: '다른 기기' });
  const seenText = [];
  const r = await store.commit(plan(text('"mine"'), { onConflict: ({ text: t }) => { seenText.push(t); return null; } }));
  assert.equal(r.cancelled, true);
  assert.deepEqual(seenText, [text('"remote"')]);
  assert.equal(fake.count('PATCH', /\/git\/refs\//), 0);
  assert.equal(fake.clientHistory().length, 0);
  assert.equal(fake.fileText(COLL), text('"remote"'));
});

test('collection.json이 바뀜 → 다시 적용하면 1커밋·원격 변경 유지', async () => {
  const { fake, store } = setup(); await store.read();
  const remote = fake.advanceHead({ files: { [COLL]: text('"remote"'), [FEED]: '{"n":9}' }, message: '다른 기기' });
  const r = await store.commit(plan(text('"mine"'), {
    files: [{ path: 'docs/photos/k1/pa.webp', bytes: new Uint8Array([7]) }],
    onConflict: ({ text: t }) => ({ collectionText: t.replace('"remote"]', '"remote","mine"]') }),
  }));
  assert.equal(r.ok, true);
  assert.deepEqual(fake.commit(r.sha).parents, [remote]);
  assert.equal(fake.fileText(COLL), text('"remote","mine"'));
  assert.equal(fake.fileText(FEED), '{"n":9}');
  assert.ok(fake.listFiles().includes('docs/photos/k1/pa.webp')); // 사진(blob 재사용)도 같은 커밋
  assert.equal(fake.clientHistory().length, 1);
});

test('재시도 중에 collection.json이 바뀌어도 충돌 경로로', async () => {
  const { fake, store } = setup(); await store.read();
  fake.hooks.beforePatchRef.push((api) => api.advanceHead({ files: { [COLL]: text('"remote"') } }));
  let called = 0;
  const r = await store.commit(plan(text('"mine"'), { onConflict: () => { called++; return null; } }));
  assert.equal(called, 1); assert.equal(r.cancelled, true);
  assert.equal(fake.clientHistory().length, 0);
});

test('충돌이 계속되면(4회) conflict 오류', async () => {
  const { fake, store } = setup(); await store.read();
  for (let i = 0; i < 4; i++) fake.hooks.beforePatchRef.push((api) => api.advanceHead({ files: { [COLL]: text('"r' + i + '"') } }));
  await assert.rejects(store.commit(plan(text('"mine"'), { onConflict: ({ text: t }) => ({ collectionText: t }) })), (e) => { assert.equal(e.kind, 'conflict'); return true; });
  assert.equal(fake.clientHistory().length, 0);
});

/* ---------- 권한·네트워크 오류 ---------- */
for (const status of [403, 404]) {
  for (const at of ['blobs', 'trees', 'commits', 'refs']) {
    test(`권한 오류: ${at} 단계 ${status} → kind perm, 커밋 0, 토큰 비노출`, async () => {
      const { fake, store } = setup(); await store.read();
      fake.state.deny = { status, at };
      await assert.rejects(store.commit(plan(text('"mine"'))), (e) => { assert.equal(e.kind, 'perm'); assert.equal(e.status, status); noLeak(e); return true; });
      assert.equal(fake.clientHistory().length, 0);
      assert.equal(fake.fileText(COLL), text('"seed"'));
    });
  }
}

test('403 + x-ratelimit-remaining:0 → ratelimit (권한 오류와 구분)', async () => {
  const { fake, store } = setup(); await store.read();
  fake.state.deny = { status: 403, ratelimit: true };
  await assert.rejects(store.commit(plan(text('"mine"'))), (e) => { assert.equal(e.kind, 'ratelimit'); noLeak(e); return true; });
});

test('저장 중 401 → auth', async () => {
  const { fake } = setup();
  const store = GH.create({ fetch: fake.fetch, token: TOKEN, repo: REPO });
  await store.read();
  const bad = GH.create({ fetch: fake.fetch, token: 'revoked', repo: REPO });
  await assert.rejects(bad.commit(plan(text('1'))), (e) => e.kind === 'auth');
});

test('네트워크 실패 → network (원인 객체·토큰 비노출)', async () => {
  const store = GH.create({ fetch: () => Promise.reject(new TypeError('Failed to fetch https://api.github.com/ Bearer ' + TOKEN)), token: TOKEN, repo: REPO });
  await assert.rejects(store.read(), (e) => { assert.equal(e.kind, 'network'); noLeak(e); return true; });
});

test('읽기 중 403/404 → perm', async () => {
  const fake = FakeGitHub.create({ token: TOKEN, seed: { [COLL]: '{}' } });
  const store = GH.create({ fetch: fake.fetch, token: TOKEN, repo: 'someone/else' }); // 이 토큰으로는 없는/접근 불가 저장소
  await assert.rejects(store.read(), (e) => { assert.equal(e.kind, 'perm'); assert.equal(e.status, 404); return true; });
});

test('base64 도우미: 한글·큰 바이트 왕복', () => {
  const s = '프라 격납고 ' + 'ㄱ'.repeat(50000);
  const bytes = new TextEncoder().encode(s);
  assert.equal(GH.base64ToText(GH.bytesToBase64(bytes)), s);
  // GitHub contents API는 base64를 줄바꿈 섞어 준다
  const wrapped = Buffer.from('프라 격납고', 'utf8').toString('base64').replace(/(.{8})/g, '$1' + String.fromCharCode(10));
  assert.equal(GH.base64ToText(wrapped), '프라 격납고');
});
