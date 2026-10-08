/* 프라 격납고 — 검색 별칭 사전 (사이트 쪽. 크롤러·config와 무관 — 검색어를 다루는 일이라 여기에 둔다).
   카탈로그 이름은 AI 번역이라 내가 부르는 이름·줄임말·철자와 다를 수 있다. 검색할 때 낱말을 이 사전으로 넓혀서 찾는다.
   틀린 후보가 자주 나오거나 못 찾는 이름이 있으면 아래 표에 한 줄 추가하면 된다 (tests/site_aliases.test.mjs가 형식을 검사한다).
   브라우저에서는 window.PlamoAliases, node에서는 require()로 쓴다. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PlamoAliases = factory();
})(typeof self !== 'undefined' ? self : this, function () {
'use strict';

/* 1) 같은 말의 표기 변형 — 어느 쪽으로 검색해도 모두 찾는다 (양방향).
      철자(캠퍼/켐퍼, 발바토스/바르바토스), 기호(뉴/ν), 영문 표기(하이뉴/Hi-ν)처럼 "이름은 같은데 글자가 다른" 경우. */
var GROUPS = [
  ['발바토스', '바르바토스'],
  ['캠퍼', '켐퍼'],
  ['르브리스', '루브리스'],
  ['담드', '댐드'],
  ['퀀터', '콴타', '쿠안타'],
  ['즈곡그', '즈고크', '즈고쿠'],
  ['판넬', '펀넬'],
  ['트란잠', '트랜잠'],
  ['커멘드', '코만도', '커맨드'],
  ['아카쓰키', '아카츠키'],
  ['하이뉴', 'Hi-ν'],
  ['뉴', 'ν'],
  ['턴엑스', '턴X'],
  ['턴에이', '턴A'],
  ['지쿠악스', '지크악스', 'GQuuuuuuX']
];

/* 2) 줄임말 → 정식 표기 (단방향: 줄임말로 검색하면 정식 표기도 찾지만, 정식 표기로 검색해서 줄임말을 찾을 일은 없다).
      값은 하나 이상의 대체 표기이고, 어느 하나라도 이름에 들어 있으면 맞는 것으로 본다. */
var EXPAND = {
  '퍼건': ['퍼스트건담', 'RX-78-2', 'RX78-2']
};

/* 3) 검색할 때 무시할 꼬리말 — 내 프라 이름에는 "클리어/코팅" 같은 변형 표시가 붙지만 카탈로그에는 기본형만 있는 경우가 많다.
      필수 조건이 아니라 **있으면 가산점**만 준다(클리어 컬러 제품이 있으면 그쪽이 앞에 온다). 낱말 순서 그대로의 연속 낱말열. */
var TAILS = [
  ['크로스', '컨트라스트', '컬러'],
  ['컨트라스트', '컬러'],
  ['철혈', '코팅'],
  ['클리어'],
  ['코팅'],
  ['무등급']
];

/* 4) 일반어 — 이 말만 맞았다고 후보가 되지는 않는다 (예: "발길 클리어"가 "건담베이스 한정 …[클리어 컬러]"로 연결되는 것을 막는다).
      검색어가 전부 일반어일 때("건담")는 예외로 그대로 찾는다. */
var GENERIC = ['건담', '한정', '건담베이스', '세트', '컬러', '웨폰', '웨폰즈', '유닛', '파츠'];

/* norm: catalog.js의 norm (NFKC·소문자·글자와 숫자만). 사전 값도 같은 방식으로 맞춘다. */
function build(norm) {
  var alts = {}, tails = TAILS.map(function (seq) { return seq.map(norm); }), generic = {};
  var add = function (k, v) { (alts[k] = alts[k] || {})[v] = 1; };
  GROUPS.forEach(function (g) {
    var n = g.map(norm);
    n.forEach(function (a) { n.forEach(function (b) { add(a, b); }); });
  });
  Object.keys(EXPAND).forEach(function (k) {
    var kn = norm(k); add(kn, kn);
    EXPAND[k].forEach(function (v) { add(kn, norm(v)); });
  });
  GENERIC.forEach(function (g) { generic[norm(g)] = 1; });
  tails.sort(function (a, b) { return b.length - a.length; }); // 긴 꼬리말 먼저
  return {
    // 낱말 하나의 대체 표기들 (자기 자신 포함)
    alts: function (t) { return alts[t] ? Object.keys(alts[t]) : [t]; },
    isGeneric: function (t) { return !!generic[t]; },
    // 낱말 목록 → {core: 꼬리말을 뺀 낱말들, tails: 뺀 꼬리말들 [{all: 이어 붙인 문자열, words: 구성 낱말}]}
    splitTails: function (tokens) {
      var core = [], out = [], i = 0;
      while (i < tokens.length) {
        var hit = null;
        for (var s = 0; s < tails.length && !hit; s++) {
          var seq = tails[s];
          if (seq.length <= tokens.length - i && seq.every(function (w, j) { return tokens[i + j] === w; })) hit = seq;
        }
        if (hit) { out.push({ all: hit.join(''), words: hit.filter(function (w) { return w.length >= 2 && !generic[w]; }) }); i += hit.length; } else { core.push(tokens[i]); i++; }
      }
      return { core: core, tails: out };
    }
  };
}

return { GROUPS: GROUPS, EXPAND: EXPAND, TAILS: TAILS, GENERIC: GENERIC, build: build };
});
