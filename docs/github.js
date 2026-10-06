/* 프라 격납고 — GitHub API 클라이언트 (소유자 판정, collection.json 읽기, 한 커밋 저장).
   브라우저에서는 window.PlamoGitHub, node에서는 require()로 쓴다. fetch는 주입한다 (tests/site_github.test.mjs).
   토큰은 Authorization 헤더로만 보내고, 오류 객체에는 kind·status만 담는다 (요청 헤더·응답 본문을 UI로 내보내지 않는다). */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PlamoGitHub = factory();
})(typeof self !== 'undefined' ? self : this, function () {
'use strict';

// kind: auth(401) · perm(403/404) · ratelimit · unprocessable(422) · conflict · retry-exhausted · network · other
class GhError extends Error {
  constructor(kind, status) {
    super('github:' + kind + (status ? ':' + status : ''));
    this.kind = kind;
    this.status = status || 0;
  }
}

function bytesToBase64(bytes) {
  var s = '', CH = 0x8000;
  for (var i = 0; i < bytes.length; i += CH) s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  return btoa(s);
}
function base64ToText(b64) {
  var bin = atob(String(b64).replace(/\s/g, '')), a = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
  return new TextDecoder('utf-8').decode(a);
}
function utf8(text) { return new TextEncoder().encode(text); }

function classify(res) {
  var s = res.status;
  if (s === 401) return new GhError('auth', s);
  if (s === 403) return new GhError(res.headers && res.headers.get('x-ratelimit-remaining') === '0' ? 'ratelimit' : 'perm', s);
  if (s === 404) return new GhError('perm', s);
  if (s === 429) return new GhError('ratelimit', s);
  if (s === 422) return new GhError('unprocessable', s);
  return new GhError('other', s);
}

function create(cfg) {
  var fetchFn = cfg.fetch, token = cfg.token, repo = cfg.repo;
  var apiBase = cfg.apiBase || 'https://api.github.com';
  var path = cfg.path || 'docs/data/collection.json';
  var dir = path.replace(/\/[^\/]+$/, '');
  var maxAttempts = cfg.maxAttempts || 3, maxConflicts = cfg.maxConflicts || 3, concurrency = cfg.concurrency || 4;
  var st = { branch: cfg.branch || 'main', baseSha: null, baseBlobSha: null };

  function request(method, apiPath, body) {
    var headers = { 'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ' + token, 'X-GitHub-Api-Version': '2022-11-28' };
    var init = { method: method, headers: headers, cache: 'no-store' }; // GitHub의 max-age=60 캐시를 피한다
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
    return fetchFn(apiBase + apiPath, init).then(function (res) {
      if (res.ok) return res.status === 204 ? null : res.json();
      throw classify(res);
    }, function () { throw new GhError('network'); }).catch(function (e) { throw e instanceof GhError ? e : new GhError('other'); });
  }
  var R = function (s) { return '/repos/' + repo + s; };

  // 계정 권한(permissions.push)이라 토큰 권한과 다를 수 있다 → 소유자 UI를 켜는 잠정 판정일 뿐
  async function connect() {
    var r = await request('GET', R(''));
    st.branch = r.default_branch || 'main';
    return { push: !!(r.permissions && r.permissions.push), branch: st.branch };
  }
  async function getHead() {
    var r = await request('GET', R('/git/ref/heads/' + encodeURI(st.branch)));
    return r.object.sha;
  }
  async function getFile(head) {
    var r;
    try { r = await request('GET', R('/contents/' + encodeURI(path) + '?ref=' + head)); }
    catch (e) { if (e.kind === 'perm' && e.status === 404) return { text: null, blobSha: null }; throw e; }
    var text;
    if (r.encoding === 'base64') text = base64ToText(r.content || '');
    else text = base64ToText((await request('GET', R('/git/blobs/' + r.sha))).content); // 1MB 넘으면 content가 비어 온다
    return { text: text, blobSha: r.sha };
  }
  // 충돌 판정용: 파일 내용 없이 blob sha만 (디렉터리 목록)
  async function getFileSha(head) {
    var list;
    try { list = await request('GET', R('/contents/' + encodeURI(dir) + '?ref=' + head)); }
    catch (e) { if (e.kind === 'perm' && e.status === 404) return null; throw e; }
    var hit = Array.isArray(list) ? list.filter(function (x) { return x.path === path; })[0] : null;
    return hit ? hit.sha : null;
  }

  async function read() {
    var head = await getHead(), f = await getFile(head);
    st.baseSha = head; st.baseBlobSha = f.blobSha;
    return { text: f.text, head: head, blobSha: f.blobSha };
  }

  async function ensureBlob(content, cache) {
    var key = typeof content === 'string' ? 's:' + content : content;
    if (cache.has(key)) return cache.get(key);
    var b64 = bytesToBase64(typeof content === 'string' ? utf8(content) : content);
    var r = await request('POST', R('/git/blobs'), { content: b64, encoding: 'base64' });
    cache.set(key, r.sha);
    return r.sha;
  }
  async function uploadAll(plan, cache) {
    var files = plan.files || [], total = files.length + 1, done = 0, shas = {};
    var tick = function () { done++; if (plan.onProgress) plan.onProgress(done, total); };
    shas.collection = await ensureBlob(plan.collectionText, cache); tick();
    var i = 0;
    async function worker() {
      while (i < files.length) {
        var f = files[i++];
        shas[f.path] = await ensureBlob(f.bytes, cache); tick();
      }
    }
    var ws = []; for (var n = 0; n < Math.min(concurrency, files.length); n++) ws.push(worker());
    await Promise.all(ws);
    return shas;
  }

  // 한 번의 저장 시도(최대 maxAttempts회). 다른 파일만 바뀐 head 전진·422는 최신 head 위에 다시 만들어 조용히 재시도한다.
  // collection.json 자체가 바뀌었을 때만 {conflict:true}
  async function attempt(plan, shas) {
    for (var n = 1; n <= maxAttempts; n++) {
      var head = await getHead();
      if (head !== st.baseSha) {
        if ((await getFileSha(head)) !== st.baseBlobSha) return { conflict: true };
        st.baseSha = head;
      }
      var hc = await request('GET', R('/git/commits/' + head));
      var entries = [{ path: path, mode: '100644', type: 'blob', sha: shas.collection }];
      (plan.files || []).forEach(function (f) { entries.push({ path: f.path, mode: '100644', type: 'blob', sha: shas[f.path] }); });
      (plan.deletes || []).forEach(function (p) { entries.push({ path: p, mode: '100644', type: 'blob', sha: null }); });
      var tree = await request('POST', R('/git/trees'), { base_tree: hc.tree.sha, tree: entries });
      var nc = await request('POST', R('/git/commits'), { message: plan.message, tree: tree.sha, parents: [head] });
      try { await request('PATCH', R('/git/refs/heads/' + encodeURI(st.branch)), { sha: nc.sha, force: false }); }
      catch (e) { if (e.kind === 'unprocessable') continue; throw e; }
      st.baseSha = nc.sha; st.baseBlobSha = shas.collection;
      return { ok: true, sha: nc.sha, blobSha: shas.collection, attempts: n };
    }
    throw new GhError('retry-exhausted');
  }

  // plan: {message, collectionText, files:[{path, bytes}], deletes:[path], onProgress(done,total), onConflict({text}) → 새 plan | null}
  async function commit(plan) {
    var cache = new Map(), conflicts = 0, cur = plan;
    for (;;) {
      var shas = await uploadAll(cur, cache);
      var out = await attempt(cur, shas);
      if (out.ok) return out;
      if (++conflicts > maxConflicts) throw new GhError('conflict');
      var latest = await read(); // 화면도 최신으로 맞추도록 알린다
      var next = cur.onConflict ? await cur.onConflict({ text: latest.text }) : null;
      if (!next) return { cancelled: true };
      cur = Object.assign({}, cur, next);
    }
  }

  return { connect: connect, read: read, commit: commit, state: function () { return { branch: st.branch, baseSha: st.baseSha, baseBlobSha: st.baseBlobSha }; } };
}

return { create: create, GhError: GhError, bytesToBase64: bytesToBase64, base64ToText: base64ToText };
});
