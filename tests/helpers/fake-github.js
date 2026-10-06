/* 메모리 속 가짜 GitHub (Git Data API + contents). 실제 네트워크·실제 토큰을 쓰지 않는다.
   - node 테스트: const FakeGitHub = require('./helpers/fake-github.js'); const gh = FakeGitHub.create({...}); gh.fetch(url, init)
   - 브라우저(Playwright add_init_script): FakeGitHub.install(window, {...}) → api.github.com 요청만 가로채고 window.__gh 로 상태·요청 로그를 노출 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.FakeGitHub = factory();
})(typeof self !== 'undefined' ? self : this, function () {
'use strict';

function toBytes(x) { return typeof x === 'string' ? new TextEncoder().encode(x) : x; }
function hash40(input) {
  var b = toBytes(input), out = '';
  for (var s = 0; s < 5; s++) {
    var h = (0x811c9dc5 ^ Math.imul(s + 1, 0x9e3779b1)) >>> 0;
    for (var i = 0; i < b.length; i++) { h ^= b[i]; h = Math.imul(h, 0x01000193) >>> 0; }
    h ^= b.length; h = Math.imul(h, 0x01000193) >>> 0;
    out += ('00000000' + h.toString(16)).slice(-8);
  }
  return out;
}
function b64encode(bytes) {
  var s = '', CH = 0x8000;
  for (var i = 0; i < bytes.length; i += CH) s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  return btoa(s);
}
function b64decode(str) {
  var bin = atob(String(str).replace(/\s/g, '')), a = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
  return a;
}
function headerGet(h, name) {
  if (!h) return null;
  if (typeof h.get === 'function') return h.get(name);
  var k = Object.keys(h).filter(function (x) { return x.toLowerCase() === name.toLowerCase(); })[0];
  return k ? h[k] : null;
}

function create(opts) {
  opts = opts || {};
  var owner = opts.owner || 'sora7942', repoName = opts.repo || 'plamo-hangar', branch = opts.branch || 'main';
  var token = opts.token || 'mock-token';
  var blobs = {}, trees = {}, commits = {}, refs = {}, log = [], counter = 0;
  var state = {
    accountPush: opts.accountPush !== false,
    inlineLimit: opts.inlineLimit == null ? 1000000 : opts.inlineLimit,
    deny: opts.deny || null // {status:403|404, ratelimit?:true, at?:'blobs'|'trees'|'commits'|'refs'}
  };
  var hooks = { beforePatchRef: [] };

  function putBlob(x) { var b = toBytes(x), sha = hash40(b); blobs[sha] = b; return sha; }
  function putTree(files) {
    var keys = Object.keys(files).sort(), sha = hash40(JSON.stringify(keys.map(function (k) { return [k, files[k]]; })));
    trees[sha] = { files: Object.assign({}, files) }; return sha;
  }
  function diffFiles(a, b) {
    var added = [], modified = [], deleted = [];
    Object.keys(b).forEach(function (p) { if (!(p in a)) added.push(p); else if (a[p] !== b[p]) modified.push(p); });
    Object.keys(a).forEach(function (p) { if (!(p in b)) deleted.push(p); });
    return { added: added.sort(), modified: modified.sort(), deleted: deleted.sort() };
  }
  function putCommit(treeSha, parents, message, by) {
    var sha = hash40(treeSha + '|' + parents.join(',') + '|' + message + '|' + (++counter));
    var parentFiles = parents.length ? trees[commits[parents[0]].tree].files : {};
    commits[sha] = { sha: sha, tree: treeSha, parents: parents, message: message, by: by, changes: diffFiles(parentFiles, trees[treeSha].files) };
    return sha;
  }
  function isAncestor(a, b) { // a가 b의 조상(또는 같음)인가
    var stack = [b], seen = {};
    while (stack.length) { var c = stack.pop(); if (c === a) return true; if (seen[c] || !commits[c]) continue; seen[c] = 1; stack = stack.concat(commits[c].parents); }
    return false;
  }

  if (opts.restore) { // snapshot()으로 받은 상태에서 이어가기 (새 페이지 = 새로고침·다른 기기 흉내)
    var rs = opts.restore;
    Object.keys(rs.blobs).forEach(function (k) { blobs[k] = b64decode(rs.blobs[k]); });
    trees = rs.trees; commits = rs.commits; refs = rs.refs; counter = rs.counter;
  } else {
    var seedFiles = {};
    Object.keys(opts.seed || {}).forEach(function (p) { seedFiles[p] = putBlob(opts.seed[p]); });
    refs[branch] = putCommit(putTree(seedFiles), [], 'seed', 'seed');
  }

  function headFiles(sha) { return trees[commits[sha || refs[branch]].tree].files; }
  function advanceHead(spec) { // 다른 기기·크롤러의 커밋을 흉내: {files:{path:string|bytes|null}, message}
    var files = Object.assign({}, headFiles());
    Object.keys(spec.files || {}).forEach(function (p) { var v = spec.files[p]; if (v === null) delete files[p]; else files[p] = putBlob(v); });
    var sha = putCommit(putTree(files), [refs[branch]], spec.message || 'external', 'external');
    refs[branch] = sha; return sha;
  }

  function json(status, body, extra) { return { status: status, body: body, headers: extra || {} }; }
  function msg(status, m, extra) { return json(status, { message: m }, extra); }

  function handle(method, u, init) {
    var url = new URL(u), p = url.pathname, m;
    var auth = headerGet(init && init.headers, 'authorization');
    var body = null; if (init && init.body) { try { body = JSON.parse(init.body); } catch (e) { body = null; } }
    var entry = { method: method, path: p + url.search, auth: !!auth, status: 0, body: summarize(body) };
    log.push(entry);
    function done(r) { entry.status = r.status; return r; }

    if (auth !== 'Bearer ' + token) return done(msg(401, 'Bad credentials'));
    var base = '/repos/' + owner + '/' + repoName;
    if (p !== base && p.indexOf(base + '/') !== 0) return done(msg(404, 'Not Found'));
    var rest = p.slice(base.length);

    if (method !== 'GET' && state.deny) {
      var at = state.deny.at, step = /\/git\/blobs$/.test(rest) ? 'blobs' : /\/git\/trees$/.test(rest) ? 'trees' : /\/git\/commits$/.test(rest) ? 'commits' : 'refs';
      if (!at || at === step) {
        return done(msg(state.deny.status || 403, state.deny.status === 404 ? 'Not Found' : 'Resource not accessible by personal access token',
          state.deny.ratelimit ? { 'x-ratelimit-remaining': '0' } : { 'x-ratelimit-remaining': '4999' }));
      }
    }

    if (method === 'GET' && rest === '') return done(json(200, { full_name: owner + '/' + repoName, default_branch: branch, permissions: { push: state.accountPush, pull: true } }));
    if (method === 'GET' && (m = rest.match(/^\/git\/ref\/heads\/(.+)$/))) {
      var r = refs[decodeURIComponent(m[1])];
      return done(r ? json(200, { ref: 'refs/heads/' + m[1], object: { sha: r, type: 'commit' } }) : msg(404, 'Not Found'));
    }
    if (method === 'GET' && (m = rest.match(/^\/contents\/(.+)$/))) {
      var path = decodeURI(m[1]), ref = url.searchParams.get('ref') || branch;
      var csha = commits[ref] ? ref : refs[ref];
      if (!csha) return done(msg(404, 'No commit found for the ref ' + ref));
      var bsha = headFiles(csha)[path];
      if (!bsha) { // 디렉터리 목록 (직접 자식 파일만, 내용 없이 sha)
        var kids = Object.keys(headFiles(csha)).filter(function (f) { return f.indexOf(path + '/') === 0 && f.indexOf('/', path.length + 1) < 0; });
        if (!kids.length) return done(msg(404, 'Not Found'));
        return done(json(200, kids.map(function (f) { return { type: 'file', name: f.split('/').pop(), path: f, sha: headFiles(csha)[f], size: blobs[headFiles(csha)[f]].length }; })));
      }
      var bytes = blobs[bsha], inline = bytes.length <= state.inlineLimit;
      return done(json(200, { type: 'file', name: path.split('/').pop(), path: path, sha: bsha, size: bytes.length,
        encoding: inline ? 'base64' : 'none', content: inline ? b64encode(bytes).replace(/(.{60})/g, '$1\n') + '\n' : '' }));
    }
    if (method === 'GET' && (m = rest.match(/^\/git\/blobs\/([0-9a-f]+)$/))) {
      return done(blobs[m[1]] ? json(200, { sha: m[1], size: blobs[m[1]].length, encoding: 'base64', content: b64encode(blobs[m[1]]) }) : msg(404, 'Not Found'));
    }
    if (method === 'GET' && (m = rest.match(/^\/git\/commits\/([0-9a-f]+)$/))) {
      var c = commits[m[1]];
      return done(c ? json(200, { sha: c.sha, tree: { sha: c.tree }, parents: c.parents.map(function (x) { return { sha: x }; }), message: c.message }) : msg(404, 'Not Found'));
    }
    if (method === 'POST' && rest === '/git/blobs') {
      if (!body || typeof body.content !== 'string') return done(msg(422, 'Invalid request'));
      var bb = body.encoding === 'base64' ? b64decode(body.content) : toBytes(body.content);
      return done(json(201, { sha: putBlob(bb) }));
    }
    if (method === 'POST' && rest === '/git/trees') {
      if (!body || !Array.isArray(body.tree)) return done(msg(422, 'Invalid request'));
      var files = Object.assign({}, body.base_tree ? (commitsByTree(body.base_tree) || {}) : {});
      if (body.base_tree && !trees[body.base_tree]) return done(msg(422, 'base_tree not found'));
      for (var i = 0; i < body.tree.length; i++) {
        var t = body.tree[i];
        if (t.sha === null) { delete files[t.path]; continue; }
        if (typeof t.content === 'string') { files[t.path] = putBlob(t.content); continue; }
        if (!blobs[t.sha]) return done(msg(422, 'tree.sha ' + t.sha + ' not found'));
        files[t.path] = t.sha;
      }
      return done(json(201, { sha: putTree(files) }));
    }
    if (method === 'POST' && rest === '/git/commits') {
      if (!body || !trees[body.tree] || !Array.isArray(body.parents) || !body.parents.every(function (x) { return commits[x]; })) return done(msg(422, 'Invalid request'));
      return done(json(201, { sha: putCommit(body.tree, body.parents, String(body.message || ''), 'client') }));
    }
    if (method === 'PATCH' && (m = rest.match(/^\/git\/refs\/heads\/(.+)$/))) {
      var name = decodeURIComponent(m[1]);
      var hook = hooks.beforePatchRef.shift(); if (hook) hook(api);
      if (!refs[name]) return done(msg(404, 'Reference does not exist'));
      if (!body || !commits[body.sha]) return done(msg(422, 'Object does not exist'));
      if (body.force !== true && !isAncestor(refs[name], body.sha)) return done(msg(422, 'Update is not a fast forward'));
      refs[name] = body.sha;
      return done(json(200, { ref: 'refs/heads/' + name, object: { sha: body.sha } }));
    }
    return done(msg(404, 'Not Found'));
  }
  function commitsByTree(treeSha) { return trees[treeSha] && trees[treeSha].files; }
  function summarize(b) {
    if (!b) return null;
    var o = JSON.parse(JSON.stringify(b));
    if (typeof o.content === 'string') o.content = '<' + o.content.length + ' chars>';
    return o;
  }

  var api = {
    token: token, state: state, hooks: hooks, log: log,
    fetch: function (u, init) {
      var method = ((init && init.method) || 'GET').toUpperCase(), r = handle(method, String(u), init || {});
      var h = Object.assign({ 'content-type': 'application/json' }, r.headers);
      return Promise.resolve(new Response(r.status === 204 ? null : JSON.stringify(r.body), { status: r.status, headers: h }));
    },
    advanceHead: advanceHead,
    headSha: function () { return refs[branch]; },
    listFiles: function (sha) { return Object.keys(headFiles(sha)).sort(); },
    fileBytes: function (path, sha) { var b = headFiles(sha)[path]; return b ? blobs[b] : null; },
    fileText: function (path, sha) { var b = api.fileBytes(path, sha); return b ? new TextDecoder().decode(b) : null; },
    blobSha: function (path, sha) { return headFiles(sha)[path] || null; },
    commit: function (sha) { return commits[sha]; },
    // 현재 head에서 거슬러 올라가며 seed가 아닌 커밋을 오래된 순으로
    history: function () {
      var out = [], c = refs[branch];
      while (c && commits[c] && commits[c].by !== 'seed') { out.push(commits[c]); c = commits[c].parents[0]; }
      return out.reverse();
    },
    clientHistory: function () { return api.history().filter(function (c) { return c.by === 'client'; }); },
    count: function (method, re) { return log.filter(function (e) { return e.method === method && re.test(e.path); }).length; },
    writeCalls: function () { return log.filter(function (e) { return e.method !== 'GET'; }); },
    resetLog: function () { log.length = 0; },
    snapshot: function () {
      var b = {}; Object.keys(blobs).forEach(function (k) { b[k] = b64encode(blobs[k]); });
      return JSON.parse(JSON.stringify({ blobs: b, trees: trees, commits: commits, refs: refs, counter: counter }));
    },
    b64: { encode: b64encode, decode: b64decode }
  };
  return api;
}

function install(win, opts) {
  var server = create(opts), orig = win.fetch.bind(win);
  win.fetch = function (input, init) {
    var u = typeof input === 'string' ? input : (input && input.url);
    if (u && u.indexOf('https://api.github.com/') === 0) return server.fetch(u, init);
    return orig(input, init);
  };
  win.__gh = server;
  return server;
}

return { create: create, install: install, hash40: hash40 };
});
