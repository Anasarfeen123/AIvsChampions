(function () {
  'use strict';

  var OID = 'waiting-overlay';
  var phase = 'boot'; // boot | choose | waiting | incoming | battle | result
  var pendingPM = null;
  var pendingPMSince = 0;
  var currentDifficulty = null;
  var activeChallengeRoomId = null;
  var lobbyJoinRequested = false;
  var autoAcceptTimer = null;
  var battlePollTimer = null;
  var challengePollTimer = null;
  var resultPollTimer = null;
  var thinkingPollTimer = null;
  var battleMusic = null;
  var puterEnabled = (function() {
    try {
      var val = localStorage.getItem('showdown_puter_enabled');
      return val === null ? true : val === 'true';
    } catch (e) {
      return true;
    }
  })();

  function setPuterEnabled(state) {
    puterEnabled = !!state;
    try {
      localStorage.setItem('showdown_puter_enabled', puterEnabled ? 'true' : 'false');
    } catch (e) {}
    sendControlMessage('puter ' + (puterEnabled ? 'on' : 'off'));
    updatePuterToggleUI();
  }

  function getPuterToggleHTML() {
    var isON = puterEnabled;
    return '' +
      '<div class="overlay-puter-box" style="margin: 12px 0 16px 0; padding: 12px 14px; background: rgba(15, 23, 42, 0.7); border: 1px solid ' + (isON ? 'rgba(59, 130, 246, 0.45)' : 'rgba(148, 163, 184, 0.2)') + '; border-radius: 10px; display: flex; align-items: center; justify-content: space-between; gap: 12px; transition: all 0.2s ease;">' +
        '<div style="text-align: left; flex: 1;">' +
          '<div style="font-weight: 700; font-size: 13px; color: #f8fafc; display: flex; align-items: center; gap: 8px;">' +
            '<span>⚡ Puter.js AI</span>' +
            '<span id="puter-badge" style="font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 12px; background: ' + (isON ? '#2563eb' : '#475569') + '; color: #ffffff; text-transform: uppercase; letter-spacing: 0.5px;">' +
              (isON ? 'ON' : 'OFF') +
            '</span>' +
          '</div>' +
          '<div id="puter-desc" style="font-size: 11px; color: #94a3b8; margin-top: 2px;">' +
            (isON ? 'Cloud AI model enabled via Puter.js (Claude / GPT)' : 'Using standard local/gemini LLM model') +
          '</div>' +
        '</div>' +
        '<button type="button" id="btn-toggle-puter" style="padding: 6px 14px; font-size: 12px; height: 32px; border-radius: 8px; background: ' + (isON ? '#2563eb' : '#334155') + '; color: #ffffff; cursor: pointer; border: 1px solid ' + (isON ? '#3b82f6' : '#475569') + '; font-weight: 600; white-space: nowrap; transition: all 0.15s ease;">' +
          (isON ? 'Disable Puter' : 'Enable Puter') +
        '</button>' +
      '</div>';
  }

  function updatePuterToggleUI() {
    var badge = document.getElementById('puter-badge');
    var btn = document.getElementById('btn-toggle-puter');
    var desc = document.getElementById('puter-desc');
    var box = document.querySelector('.overlay-puter-box');
    if (badge && btn && desc) {
      badge.textContent = puterEnabled ? 'ON' : 'OFF';
      badge.style.background = puterEnabled ? '#2563eb' : '#475569';
      btn.textContent = puterEnabled ? 'Disable Puter' : 'Enable Puter';
      btn.style.background = puterEnabled ? '#2563eb' : '#334155';
      btn.style.borderColor = puterEnabled ? '#3b82f6' : '#475569';
      desc.textContent = puterEnabled ? 'Cloud AI model enabled via Puter.js (Claude / GPT)' : 'Using standard local/gemini LLM model';
      if (box) box.style.borderColor = puterEnabled ? 'rgba(59, 130, 246, 0.45)' : 'rgba(148, 163, 184, 0.2)';
    }
  }

  function toID(s) {
    return ('' + s).toLowerCase().replace(/[^a-z0-9]+/g, '');
  }

  function ready() {
    return !!(window.PS && PS.connection && PS.connection.connected && PS.user && PS.user.named);
  }

  function getOverlay() {
    var node = document.getElementById(OID);
    if (node && node.parentNode === document.body) return node;
    if (node) node.parentNode.removeChild(node);

    node = document.createElement('div');
    node.id = OID;
    node.setAttribute('role', 'dialog');
    node.setAttribute('aria-live', 'polite');
    document.body.insertBefore(node, document.body.firstChild);
    return node;
  }

  function render(content) {
    var node = getOverlay();
    node.classList.remove('fade-out');
    node.style.display = 'flex';
    node.style.pointerEvents = 'auto';
    node.innerHTML = content;
  }

  function escapeHTML(text) {
    return ('' + text).replace(/[&<>"]/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]);
    });
  }

  function shell(inner, phaseClass) {
    return '' +
      '<div class="overlay-shell ' + (phaseClass || '') + '">' +
        '<div class="overlay-card">' +
          inner +
        '</div>' +
      '</div>';
  }

  function heroLine(title, subtitle, status) {
    return '' +
      '<div class="overlay-header">' +
        '<div class="overlay-kicker">Mic Showdown</div>' +
        '<div class="overlay-title">' + title + '</div>' +
        '<div class="overlay-subtitle">' + subtitle + '</div>' +
        '<div class="overlay-status">' + status + '</div>' +
      '</div>';
  }

  function sigil() {
    return '' +
      '<div class="overlay-logo" aria-hidden="true">' +
        '<img src="/mic-logo.svg" alt="" />' +
      '</div>';
  }

  function stopBattleMusic() {
    if (!battleMusic) return;
    try {
      battleMusic.pause();
      battleMusic.currentTime = 0;
    } catch (err) {}
    battleMusic = null;
  }

  function startBattleMusic() {
    if (!window.HTMLAudioElement) return;
    try {
      if (PS && PS.prefs && PS.prefs.mute) return;
      if (battleMusic && !battleMusic.paused) return;
      if (!battleMusic) {
        battleMusic = new Audio('https://play.pokemonshowdown.com/audio/bw-rival.mp3');
        battleMusic.loop = true;
        battleMusic.preload = 'auto';
        battleMusic.volume = 0.35;
      }
      var playPromise = battleMusic.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(function () {});
      }
    } catch (err) {}
  }

  function resultPortrait(won) {
    var avatar = won ? 'blue' : 'red';
    var label = won ? 'Blue AI' : 'Red Human';
    return '' +
      '<div class="overlay-result-avatar overlay-result-avatar--' + (won ? 'win' : 'loss') + '">' +
        '<img src="/sprites/trainers/' + avatar + '.png" alt="' + label + '" />' +
      '</div>';
  }

  function showBoot() {
    phase = 'boot';
    activeChallengeRoomId = null;
    stopBattleMusic();
    render(shell(
      sigil() +
      heroLine('Connecting', 'Waiting for the local Showdown client to finish loading.', ready() ? 'Client connected, preparing controls.' : 'Connecting to Showdown...') +
      '<div class="overlay-note">The browser UI will unlock as soon as your account is ready.</div>'
    , 'phase-boot'));
  }

  function showChoose() {
    if (phase === 'battle') return;
    stopBattleMusic();
    phase = 'choose';
    currentDifficulty = null;
    activeChallengeRoomId = null;
    render(shell(
      sigil() +
      heroLine('Pick a difficulty', 'Choose the AI personality before it challenges you.', ready() ? 'Ready to send your first challenge.' : 'Logging in...') +
      '<div class="overlay-chiprow">' +
        '<span class="overlay-chip">Red Human</span>' +
        '<span class="overlay-chip">Blue AI</span>' +
        '<span class="overlay-chip">Local host</span>' +
        '<span class="overlay-chip ' + (puterEnabled ? 'overlay-chip--accent' : '') + '">Puter.js: ' + (puterEnabled ? 'ON' : 'OFF') + '</span>' +
      '</div>' +
      getPuterToggleHTML() +
      '<div class="overlay-actions overlay-actions--stack">' +
        '<button class="overlay-btn overlay-btn--easy" data-d="easy">' +
          '<strong>Easy</strong><span>Light bias</span><em>More mistakes, less pressure</em>' +
        '</button>' +
        '<button class="overlay-btn overlay-btn--medium" data-d="medium">' +
          '<strong>Medium</strong><span>Balanced bias</span><em>Shared brain, steadier lines</em>' +
        '</button>' +
        '<button class="overlay-btn overlay-btn--hard" data-d="hard">' +
          '<strong>Hard</strong><span>Sharper bias</span><em>Shared brain, riskier lines</em>' +
        '</button>' +
      '</div>' +
      '<div class="overlay-footnote">All three use the same AI path, with slightly different heuristic bias.</div>'
    , 'phase-choose'));

    var overlay = getOverlay();
    var buttons = overlay.querySelectorAll('.overlay-btn[data-d]');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('click', function () {
        pickDifficulty(this.getAttribute('data-d'));
      });
    }

    var toggleBtn = overlay.querySelector('#btn-toggle-puter');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        setPuterEnabled(!puterEnabled);
      });
    }
  }

  function showWaiting(mode) {
    phase = 'waiting';
    activeChallengeRoomId = null;
    render(shell(
      sigil() +
      heroLine('Waiting for battle', 'Blue AI is preparing the match.', ready() ? 'Challenge queued and being sent.' : 'Queued locally until login completes.') +
      '<div class="overlay-chiprow">' +
        '<span class="overlay-chip overlay-chip--accent">' + escapeHTML(mode || currentDifficulty || 'unknown') + '</span>' +
        '<span class="overlay-chip">Red Human</span>' +
        '<span class="overlay-chip ' + (puterEnabled ? 'overlay-chip--accent' : '') + '">Puter.js: ' + (puterEnabled ? 'ON' : 'OFF') + '</span>' +
      '</div>' +
      '<div class="overlay-progress"><span></span></div>' +
      '<div class="overlay-note">' + (ready() ? 'Sending challenge to Blue AI.' : 'The challenge will send automatically once the client finishes connecting.') + '</div>' +
      '<div class="overlay-actions">' +
        '<button class="overlay-btn overlay-btn--ghost" data-action="cancel">Cancel</button>' +
      '</div>'
    , 'phase-waiting'));

    var cancel = getOverlay().querySelector('[data-action="cancel"]');
    if (cancel) {
      cancel.addEventListener('click', function () {
        pendingPM = null;
        currentDifficulty = null;
        showChoose();
      });
    }
  }

  function showIncomingChallenge(room) {
    if (phase === 'battle' || phase === 'result') return;
    stopBattleMusic();
    phase = 'incoming';
    activeChallengeRoomId = room ? room.id : null;

    var challenge = room && room.challenged ? room.challenged : null;
    var format = challenge && challenge.formatName ? challenge.formatName : 'Battle request';
    var message = challenge && challenge.message ? challenge.message : 'Blue AI is challenging you.';

    render(shell(
      sigil() +
      heroLine('Incoming challenge', format, message) +
      '<div class="overlay-chiprow">' +
        '<span class="overlay-chip overlay-chip--danger">Blue AI</span>' +
        '<span class="overlay-chip">' + escapeHTML(format) + '</span>' +
      '</div>' +
      '<div class="overlay-actions">' +
        '<button class="overlay-btn overlay-btn--success" data-action="accept">Accept</button>' +
        '<button class="overlay-btn overlay-btn--ghost" data-action="reject">Reject</button>' +
      '</div>' +
      '<div class="overlay-note">If you do nothing, the client will auto-accept after a moment.</div>'
    , 'phase-incoming'));

    var overlay = getOverlay();
    var accept = overlay.querySelector('[data-action="accept"]');
    var reject = overlay.querySelector('[data-action="reject"]');
    if (accept) accept.addEventListener('click', acceptChallenge);
    if (reject) reject.addEventListener('click', rejectChallenge);

    if (autoAcceptTimer) clearTimeout(autoAcceptTimer);
    autoAcceptTimer = setTimeout(function () {
      if (phase === 'incoming') acceptChallenge();
    }, 1000);
  }

  function showBattle() {
    if (phase === 'battle') return;
    phase = 'battle';
    hideOverlay();
    startBattleMusic();
    startResultWatcher();
  }

  function showResult(won) {
    if (phase === 'result') return;
    phase = 'result';
    activeChallengeRoomId = null;
    stopPollers();
    stopBattleMusic();
    render(shell(
      resultPortrait(won) +
      '<div class="overlay-result ' + (won ? 'overlay-result--win' : 'overlay-result--loss') + '">' +
        '<div class="overlay-title">' + (won ? 'Victory' : 'Defeat') + '</div>' +
        '<div class="overlay-subtitle">' + (won ? 'Blue AI takes this one.' : 'Red Human takes this one.') + '</div>' +
      '</div>' +
      '<div class="overlay-actions overlay-actions--stack">' +
        '<button class="overlay-btn overlay-btn--success" data-action="rematch">Play again</button>' +
        '<button class="overlay-btn overlay-btn--ghost" data-action="difficulty">Change difficulty</button>' +
      '</div>' +
      '<div class="overlay-note">The next battle can be queued instantly.</div>'
    , 'phase-result'));

    var overlay = getOverlay();
    var rematch = overlay.querySelector('[data-action="rematch"]');
    var difficulty = overlay.querySelector('[data-action="difficulty"]');
    if (rematch) rematch.addEventListener('click', rematchBattle);
    if (difficulty) difficulty.addEventListener('click', showChoose);
  }

  function hideOverlay() {
    var node = document.getElementById(OID);
    if (!node) return;
    node.classList.add('fade-out');
    setTimeout(function () {
      node.style.display = 'none';
      node.style.pointerEvents = 'none';
    }, 300);
  }

  function getActiveBattleRoom() {
    if (!window.PS || !PS.rooms) return null;
    if (PS.room && PS.room.type === 'battle' && PS.room.battle && PS.room.battle.started && !PS.room.battle.ended) {
      return PS.room;
    }
    for (var id in PS.rooms) {
      var room = PS.rooms[id];
      if (!room || room.type !== 'battle' || !room.battle) continue;
      if (room.battle.started && !room.battle.ended) return room;
    }
    return null;
  }

  function ensureThinkingBadge() {
    return document.getElementById('ai-thinking-banner');
  }

  function hideThinkingBadge() {
    var node = document.getElementById('ai-thinking-banner');
    if (!node) return;
    node.classList.remove('is-visible');
  }

  function updateThinkingIndicator() {
    var room = getActiveBattleRoom();
    var battle = room && room.battle;
    var choicesDone = !!(room && room.choices && typeof room.choices.isDone === 'function' && room.choices.isDone());
    var shouldShow = !!(battle && battle.started && !battle.ended && room && room.side && room.request && choicesDone);
    if (!shouldShow) {
      hideThinkingBadge();
      return;
    }
    var node = ensureThinkingBadge();
    if (!node) return;
    node.classList.add('is-visible');
  }

  function stopPollers() {
    if (battlePollTimer) clearInterval(battlePollTimer);
    if (challengePollTimer) clearInterval(challengePollTimer);
    if (resultPollTimer) clearInterval(resultPollTimer);
    if (autoAcceptTimer) clearTimeout(autoAcceptTimer);
    battlePollTimer = null;
    challengePollTimer = null;
    resultPollTimer = null;
    autoAcceptTimer = null;
  }

  function startResultWatcher() {
    if (resultPollTimer) return;
    resultPollTimer = setInterval(function () {
      if (phase !== 'battle') return;
      var text = document.body ? (document.body.innerText || '') : '';
      if (text.indexOf('won the battle') === -1) return;
      var userName = PS && PS.user ? PS.user.name : '';
      var won = userName && text.indexOf(userName + ' won') !== -1;
      stopPollers();
      setTimeout(function () {
        showResult(won);
      }, 1200);
    }, 800);
  }

  function sendControlMessage(msg) {
    if (ready() && PS.send) {
      try {
        PS.send('/pm Blue AI, battle-control ' + msg);
        PS.send('/pm Blue AI, ' + msg);
      } catch (err) {}
    }
    var room = PS && PS.rooms && PS.rooms.lobby;
    if (ready() && room && room.connected) {
      try {
        room.send('battle-control ' + msg);
        return true;
      } catch (err) {}
    }
    pendingPM = msg;
    pendingPMSince = Date.now() - 1500;
    if (ready() && !lobbyJoinRequested) {
      try {
        PS.send('/join lobby');
        lobbyJoinRequested = true;
      } catch (err) {}
    }
    return false;
  }

  function flushPendingPM() {
    if (!pendingPM || !ready()) return;
    if (Date.now() - pendingPMSince < 1500) return;
    try {
      var room = PS.rooms && PS.rooms.lobby;
      if (!room || !room.connected) {
        return;
      }
      room.send('battle-control ' + pendingPM);
      pendingPM = null;
      pendingPMSince = 0;
      lobbyJoinRequested = false;
    } catch (err) {}
  }

  function pickDifficulty(level) {
    currentDifficulty = level;
    startBattleMusic();
    showWaiting(level);
    sendControlMessage('puter ' + (puterEnabled ? 'on' : 'off'));
    sendControlMessage('difficulty ' + level);
  }

  function rematchBattle() {
    startBattleMusic();
    var room = findIncomingChallengeRoom();
    if (room) {
      delete room['__aa'];
      delete room.__lastChallengeId;
    }
    showWaiting(currentDifficulty || 'rematch');
    sendControlMessage('rematch');
  }

  function findIncomingChallengeRoom() {
    if (!window.PS || !PS.rooms) return null;
    for (var id in PS.rooms) {
      var room = PS.rooms[id];
      if (!room || !room.challenged) continue;
      if (!room.challenging) return room;
      if (!room.pmTarget) continue;
      if (toID(room.pmTarget) === 'blueai') return room;
    }
    return null;
  }

  function acceptChallenge() {
    var room = findIncomingChallengeRoom();
    if (room && room.challenged) {
      var challengeId = room.challenged.time || JSON.stringify(room.challenged);
      room.__lastChallengeId = challengeId;
      delete room['__aa'];
    }
    try {
      PS.send('/accept blueai');
    } catch (e1) {}
    try {
      PS.send('/accept');
    } catch (e2) {}
    if (room && typeof room.send === 'function') {
      try {
        room.send('/accept');
      } catch (e3) {}
    }
    return true;
  }

  function rejectChallenge() {
    var room = findIncomingChallengeRoom();
    if (room && typeof room.send === 'function') {
      try {
        room.send('/reject');
        showChoose();
        return;
      } catch (err) {}
    }
    try {
      PS.send('/reject');
    } catch (err2) {}
    showChoose();
  }

  function detectBattleStart() {
    if (battlePollTimer) return;
    battlePollTimer = setInterval(function () {
      if (phase === 'battle' || phase === 'result') return;
      if (!document.querySelector('.battle')) return;
      showBattle();
    }, 400);
  }

  function detectChallenge() {
    if (challengePollTimer) return;
    challengePollTimer = setInterval(function () {
      if (phase === 'battle' || phase === 'result') return;
      var room = findIncomingChallengeRoom();
      if (room && (phase !== 'incoming' || activeChallengeRoomId !== room.id)) {
        showIncomingChallenge(room);
      } else if (!room && phase === 'incoming') {
        activeChallengeRoomId = null;
        showWaiting(currentDifficulty || 'pending');
      }
    }, 450);
  }

  function attachGlobalKeyBlocker() {
    function shouldBlock() {
      var node = document.getElementById(OID);
      return !!(node && node.style.display !== 'none' && !node.classList.contains('fade-out'));
    }
    ['keydown', 'keyup', 'keypress'].forEach(function (eventName) {
      document.addEventListener(eventName, function (e) {
        if (!shouldBlock()) return;
        e.preventDefault();
        e.stopPropagation();
      }, true);
    });
  }

  function setAnimatedSprites() {
    try {
      if (PS && PS.prefs) {
        if (typeof PS.prefs.set === 'function') {
          PS.prefs.set('bwgfx', 1);
          PS.prefs.set('noanim', false);
        } else {
          PS.prefs.bwgfx = 1;
          PS.prefs.noanim = false;
        }
      }
      if (window.Dex && typeof Dex.loadSpriteData === 'function' && typeof jQuery !== 'undefined') {
        Dex.loadSpriteData('bw');
      }
    } catch (err) {}
  }

  function init() {
    attachGlobalKeyBlocker();
    showBoot();

    setInterval(flushPendingPM, 350);
    setInterval(updateThinkingIndicator, 300);

    var connectPoll = setInterval(function () {
      try {
        if (!window.PS || !PS.connection || !PS.connection.connected) return;
        clearInterval(connectPoll);

        var namePoll = setInterval(function () {
          if (!PS.user || !PS.user.named) return;
          clearInterval(namePoll);
          try { PS.send('/avatar red'); } catch (err) {}
          setAnimatedSprites();
          lobbyJoinRequested = false;
          showChoose();
          detectChallenge();
          detectBattleStart();
        }, 200);
      } catch (err2) {}
    }, 200);

    setTimeout(function () {
      if (phase === 'boot') showChoose();
    }, 7000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
