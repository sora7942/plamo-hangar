/* 프라 격납고 — 연결 도우미의 진행 상태 (순수 로직: DOM·저장소 없음). 화면은 app.js의 openAssist.
   미연결 프라를 하나씩 보여주고 [연결] [건너뛰기] [나중에]를 고른다. 연결은 모아 두었다가 한 번에 저장한다(커밋 1개).
   - 건너뛰기: 이번 도우미에서만 넘긴다 (다음에 다시 열면 또 나온다).
   - 나중에: 이 브라우저에 기억해 두고(localStorage는 app.js가 맡음) 다음부터 목록 맨 끝으로 미룬다. 끝에서 "나중에 N개 보기"로 다시 본다.
   브라우저에서는 window.PlamoAssist, node에서는 require()로 쓴다 (tests/site_assist.test.mjs). */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PlamoAssist = factory();
})(typeof self !== 'undefined' ? self : this, function () {
'use strict';

var MAX_LATER = 500;

// kits: 보여 줄 순서대로의 프라 목록(미연결만 넣어도 되고, 연결된 건 알아서 뺀다). o.deferred: 이전에 "나중에"로 미룬 id들. o.skipped: 이번 열기 전에 건너뛴 id들(저장 후 다시 열 때 이어 가려고)
function createSession(kits, o) {
  o = o || {};
  var byId = {}, order = [];
  (kits || []).forEach(function (k) { if (k && !k.catalogId && !byId[k.id]) { byId[k.id] = k; order.push(k.id); } });
  var deferred = {}, skipped = {}, pending = {}, history = [];
  (o.deferred || []).forEach(function (id) { deferred[id] = 1; });
  (o.skipped || []).forEach(function (id) { skipped[id] = 1; });
  var queue = order.filter(function (id) { return !deferred[id] && !skipped[id]; }).concat(order.filter(function (id) { return deferred[id] && !skipped[id]; }));
  var cursor = 0;                                   // queue[cursor]가 지금 보여 주는 프라
  var cur = function () { return cursor < queue.length ? queue[cursor] : null; };

  function advance(kind, id, extra) { history.push({ kind: kind, id: id, extra: extra || null }); cursor++; }

  var s = {
    current: function () { var id = cur(); return id ? byId[id] : null; },
    position: function () { return { index: Math.min(cursor, queue.length), total: queue.length }; },
    // [연결]: 고른 catalogId를 대기열(pending)에 넣고 다음으로. "나중에" 목록에 있었으면 거기서 뺀다
    link: function (catalogId) {
      var id = cur(); if (!id || !catalogId) return false;
      var wasDeferred = !!deferred[id];
      pending[id] = String(catalogId); delete deferred[id];
      advance('link', id, { wasDeferred: wasDeferred });
      return true;
    },
    skip: function () { var id = cur(); if (!id) return false; skipped[id] = 1; advance('skip', id); return true; },
    later: function () {
      var id = cur(); if (!id) return false;
      var was = !!deferred[id];
      if (!was && Object.keys(deferred).length >= MAX_LATER) return false;
      deferred[id] = 1; advance('later', id, { wasDeferred: was }); return true;
    },
    // [이전]: 마지막 동작을 취소하고 그 프라로 돌아간다
    back: function () {
      var h = history.pop(); if (!h) return false;
      cursor--;
      if (h.kind === 'link') { delete pending[h.id]; if (h.extra.wasDeferred) deferred[h.id] = 1; }
      else if (h.kind === 'skip') delete skipped[h.id];
      else if (h.kind === 'later' && !h.extra.wasDeferred) delete deferred[h.id];
      return true;
    },
    canBack: function () { return history.length > 0; },
    done: function () { return cur() === null; },
    stats: function () {
      var later = Object.keys(deferred).filter(function (id) { return byId[id]; }).length;
      return { pending: Object.keys(pending).length, skipped: Object.keys(skipped).length, later: later, left: queue.length - Math.min(cursor, queue.length) };
    },
    pendingMap: function () { var m = {}; Object.keys(pending).forEach(function (id) { m[id] = pending[id]; }); return m; },
    pendingCount: function () { return Object.keys(pending).length; },
    deferredIds: function () { return Object.keys(deferred); },
    skippedIds: function () { return Object.keys(skipped); },
    // 끝에서 다시 보기: 건너뛴 것 / 나중에로 미룬 것을 큐 끝에 다시 넣는다 (이미 연결 대기인 것은 제외)
    reviewSkipped: function () { return requeue(Object.keys(skipped), function (id) { delete skipped[id]; }); },
    reviewLater: function () { return requeue(Object.keys(deferred).filter(function (id) { return byId[id]; }), null); },
    // 저장이 끝났다: 대기열을 비운다 (저장한 프라는 이제 연결돼 있으니 다음에 도우미를 열면 목록에서 빠진다)
    afterSave: function () { var n = Object.keys(pending).length; pending = {}; return n; }
  };

  function requeue(ids, clear) {
    var add = ids.filter(function (id) { return byId[id] && !pending[id]; });
    if (!add.length) return 0;
    if (clear) add.forEach(clear);
    queue = queue.slice(0, cursor).concat(add);      // 지나온 프라는 그대로 두고 이어서 보여 준다
    history = [];                                     // 되돌리기 기준이 바뀌므로 비운다
    return add.length;
  }
  return s;
}

// "나중에" 목록(localStorage에 저장할 값) 정리: 실제로 있는 프라 id만, 문자열만, 중복 없이, 상한 안에서
function cleanLater(ids, kits) {
  var have = {}; (kits || []).forEach(function (k) { if (k && !k.catalogId) have[k.id] = 1; });
  var seen = {}, out = [];
  (Array.isArray(ids) ? ids : []).forEach(function (id) { if (typeof id === 'string' && have[id] && !seen[id]) { seen[id] = 1; out.push(id); } });
  return out.slice(0, MAX_LATER);
}

return { createSession: createSession, cleanLater: cleanLater, MAX_LATER: MAX_LATER };
});
