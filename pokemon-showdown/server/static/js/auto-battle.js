(function () {
  'use strict';
  var PACKED_TEAM =
    "Pikachu|Pikachu|Light Ball|Static|Volt Tackle,Thunderbolt,Iron Tail,Quick Attack|Naive|0,252,0,4,0,252||31,31,31,31,31,31||100|]" +
    "Espeon|Espeon|Light Clay|Magic Bounce|Psychic,Shadow Ball,Reflect,Calm Mind|Timid|252,0,0,4,0,252||31,31,31,31,31,31||100|]" +
    "Snorlax|Snorlax|Leftovers|Thick Fat|Body Slam,Crunch,Earthquake,Rest|Careful|252,4,0,0,252,0||31,31,31,31,31,31||100|]" +
    "Venusaur|Venusaur|Black Sludge|Overgrow|Giga Drain,Sludge Bomb,Leech Seed,Growth|Timid|252,0,0,4,0,252||31,31,31,31,31,31||100|]" +
    "Charizard|Charizard|Heavy-Duty Boots|Blaze|Flamethrower,Air Slash,Dragon Pulse,Earthquake|Naive|0,4,0,252,0,252||31,31,31,31,31,31||100|]" +
    "Blastoise|Blastoise|White Herb|Torrent|Scald,Ice Beam,Aura Sphere,Rain Dance|Modest|0,0,4,252,0,252||31,31,31,31,31,31||100|";

  var ACCEPTED_KEY = '__aa';

  function toID(s) { return ('' + s).toLowerCase().replace(/[^a-z0-9]+/g, ''); }

  function log(m) { console.log('[AB]', m); }

  function findIncomingChallengeRoom() {
    if (!PS || !PS.rooms) return null;
    for (var id in PS.rooms) {
      var room = PS.rooms[id];
      if (!room || !room.challenged) continue;
      if (!room.challenging) return room;
      if (!room.pmTarget) continue;
      if (toID(room.pmTarget) === 'blueai') return room;
    }
    return null;
  }

  function start() {
    if (!PS || !PS.connection) return void setTimeout(start, 200);
    log('Waiting for connection…');

    var renameRequested = false;
    var teamConfigured = false;

    var ready = setInterval(function () {
      if (!PS.connection || !PS.connection.connected) return;
      clearInterval(ready);
      log('Connected');

      var rename = setInterval(function () {
        if (!PS.user) return;
        if (PS.user.named) {
          if (toID(PS.user.name) !== 'redhuman') {
            if (!renameRequested) {
              log('Wrong name, retrying…');
              renameRequested = true;
              PS.user.changeName('Red Human');
            }
            return;
          }
          clearInterval(rename);
          log('Logged in as ' + PS.user.name);
          // Force animated sprites
          try {
            if (PS.prefs) {
              if (typeof PS.prefs.set === 'function') {
                PS.prefs.set('bwgfx', 1); PS.prefs.set('noanim', false);
              } else { PS.prefs.bwgfx = 1; PS.prefs.noanim = false; }
            }
            if (window.Dex && typeof Dex.loadSpriteData === 'function' && typeof jQuery !== 'undefined') {
              Dex.loadSpriteData('bw');
            }
          } catch (e) {}
          // Set team only once.
          if (!teamConfigured) {
            teamConfigured = true;
            log('Setting team');
            PS.send('/utm ' + PACKED_TEAM);
          }
          // Accept challenges
          setInterval(function () {
            try {
              var room = findIncomingChallengeRoom();
              if (!room) return;
              if (room.challenged) {
                var cid = room.challenged.time || JSON.stringify(room.challenged);
                if (room.__lastCid !== cid) {
                  room.__lastCid = cid;
                  delete room[ACCEPTED_KEY];
                }
              }
              if (room[ACCEPTED_KEY]) return;
              room[ACCEPTED_KEY] = true;
              log('Accepting challenge');
              if (typeof room.send === 'function') {
                try { room.send('/accept'); } catch (e1) {}
              }
              try { PS.send('/accept blueai'); } catch (e2) {}
              try { PS.send('/accept'); } catch (e3) {}
            } catch (e) {}
          }, 500);
          return;
        }
        if (!PS.user.loggingIn && !renameRequested) {
          log('Renaming to Red Human');
          renameRequested = true;
          PS.user.changeName('Red Human');
        }
      }, 300);
    }, 300);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
