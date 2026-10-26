// 由 tools/build_site.py 產生，請改產生器而不是改這個檔
(function () {
  'use strict';
  var PREFIX = 'ymp5-';

  // 私密視窗或封鎖儲存時 localStorage 會丟例外，一律吞掉讓頁面照常運作
  function storeGet(key) {
    try { return window.localStorage.getItem(PREFIX + key); } catch (e) { return null; }
  }
  function storeSet(key, value) {
    try {
      if (value === null) { window.localStorage.removeItem(PREFIX + key); }
      else { window.localStorage.setItem(PREFIX + key, value); }
    } catch (e) { /* 無法儲存時只是不記住 */ }
  }
  function isDone(id) { return storeGet('done-' + id) === '1'; }

  function toast(msg) {
    var el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 3000);
  }

  // ── 首頁：完成打勾與進度條 ──
  function initIndex() {
    var cards = document.querySelectorAll('.unit-card');
    var doneCount = 0;
    cards.forEach(function (card) {
      if (isDone(card.dataset.id)) { card.classList.add('done'); doneCount++; }
    });
    var text = document.getElementById('progress-text');
    var fill = document.getElementById('progress-fill');
    if (!text || !fill) return;
    var total = Number(text.dataset.total) || 0;
    text.textContent = doneCount + ' / ' + total + ' 單元完成';
    fill.style.width = (total ? Math.round(doneCount * 100 / total) : 0) + '%';
  }

  // ── 程式碼複製 ──
  function copyText(str) {
    if (navigator.clipboard && window.isSecureContext) { return navigator.clipboard.writeText(str); }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = str; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy') ? resolve() : reject(new Error('copy failed')); }
      catch (e) { reject(e); } finally { ta.remove(); }
    });
  }
  function initCopy() {
    document.querySelectorAll('.copy-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var code = btn.closest('.code-block').querySelector('code');
        copyText(code.textContent).then(function () {
          btn.textContent = '已複製 ✔';
          setTimeout(function () { btn.textContent = '複製'; }, 1500);
        }).catch(function () { toast('複製失敗，請手動選取文字'); });
      });
    });
  }

  // ── YouTube：點縮圖才載入 iframe ──
  function initYoutube() {
    document.querySelectorAll('.yt-thumb').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var fig = btn.closest('.yt');
        var iframe = document.createElement('iframe');
        iframe.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(fig.dataset.yt) + '?autoplay=1&rel=0';
        iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
        iframe.allowFullscreen = true;
        iframe.title = btn.getAttribute('aria-label') || 'YouTube';
        btn.replaceWith(iframe);
      });
    });
  }

  // ── 旁白播放 ──
  function initPlayer() {
    var player = document.getElementById('player');
    if (!player) return;
    var rateSel = document.getElementById('rate');
    var status = document.getElementById('now-playing');
    var playAllBtn = document.getElementById('play-all');
    var targets = Array.prototype.slice.call(document.querySelectorAll('[data-audio]'));
    var queue = [], current = null;

    var savedRate = storeGet('rate');
    if (savedRate && rateSel.querySelector('option[value="' + savedRate + '"]')) { rateSel.value = savedRate; }
    rateSel.addEventListener('change', function () {
      player.playbackRate = Number(rateSel.value);
      storeSet('rate', rateSel.value);
    });

    function label(el) {
      var h = el.querySelector('h2, h1');
      return h ? h.textContent : '';
    }
    function clearHighlight() { targets.forEach(function (t) { t.classList.remove('playing'); }); }
    function stop() {
      player.pause(); queue = []; current = null; clearHighlight();
      status.textContent = ''; playAllBtn.textContent = '▶ 全部播放';
    }
    function playEl(el) {
      current = el;
      clearHighlight();
      el.classList.add('playing');
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      player.src = el.dataset.audio;
      player.playbackRate = Number(rateSel.value);
      status.textContent = '播放中：' + label(el);
      var p = player.play();
      if (p && p.catch) {
        p.catch(function (err) {
          if (err && err.name === 'AbortError') return;
          toast('語音無法播放：' + (err && err.message ? err.message : '未知錯誤'));
          stop();
        });
      }
    }
    player.addEventListener('ended', function () {
      if (queue.length) { playEl(queue.shift()); } else { stop(); }
    });
    player.addEventListener('error', function () {
      toast('找不到語音檔：' + (current ? current.dataset.audio : ''));
      if (queue.length) { playEl(queue.shift()); } else { stop(); }
    });

    playAllBtn.addEventListener('click', function () {
      if (current) { stop(); return; }
      if (!targets.length) { toast('這個單元還沒有語音'); return; }
      queue = targets.slice(1);
      playAllBtn.textContent = '■ 停止播放';
      playEl(targets[0]);
    });
    document.querySelectorAll('.play-one').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sec = btn.closest('[data-audio]');
        queue = [];
        playAllBtn.textContent = '■ 停止播放';
        playEl(sec);
      });
    });
  }

  // ── 小測驗 ──
  function initQuiz() {
    var quiz = document.getElementById('quiz');
    if (!quiz) return;
    var scoreEl = quiz.querySelector('.score');
    var score = 0;
    quiz.querySelectorAll('.quiz-item').forEach(function (item) {
      var answer = Number(item.dataset.answer);
      var explainEl = item.querySelector('.explain');
      var explainText = item.querySelector('.explain-text').innerHTML;
      var opts = item.querySelectorAll('.opt');
      opts.forEach(function (opt) {
        opt.addEventListener('click', function () {
          if (item.dataset.answered) return;
          item.dataset.answered = '1';
          var chosen = Number(opt.dataset.i);
          opts.forEach(function (o) { o.disabled = true; });
          opts[answer].classList.add('correct');
          var ok = chosen === answer;
          if (!ok) { opt.classList.add('wrong'); } else { score++; }
          explainEl.hidden = false;
          explainEl.className = 'explain ' + (ok ? 'ok' : 'bad');
          explainEl.textContent = (ok ? '✔ 答對了！' : '✘ 答錯了。') + ' ';
          var span = document.createElement('span');
          span.innerHTML = explainText; // 已在產生器端跳脫
          explainEl.appendChild(span);
          scoreEl.textContent = String(score);
        });
      });
    });
  }

  // ── 標記完成 ──
  function initDone() {
    var main = document.querySelector('main.lesson');
    var btn = document.getElementById('mark-done');
    if (!main || !btn) return;
    var id = main.dataset.lessonId;
    var foot = btn.closest('.lesson-foot');
    function render() {
      var done = isDone(id);
      btn.textContent = done ? '✔ 已完成（再按取消）' : '✔ 標記為完成';
      foot.classList.toggle('is-done', done);
    }
    btn.addEventListener('click', function () {
      storeSet('done-' + id, isDone(id) ? null : '1');
      render();
    });
    render();
  }

  document.addEventListener('DOMContentLoaded', function () {
    try {
      initIndex(); initCopy(); initYoutube(); initPlayer(); initQuiz(); initDone();
    } catch (e) {
      toast('頁面初始化失敗：' + e.message);
    }
  });
})();
