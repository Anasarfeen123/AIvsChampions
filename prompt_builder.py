import sys
from typing import Dict, List, Any, Tuple
from poke_env.battle.battle import Battle
from poke_env.battle.pokemon import Pokemon
from poke_env.battle.move import Move
from poke_env.battle.effect import Effect

TYPE_CHART: Dict[str, Dict[str, int]] = {
    "BUG": {
        "BUG": 0, "DARK": 0, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 0,
        "FIGHTING": 2, "FIRE": 1, "FLYING": 1, "GHOST": 0, "GRASS": 2,
        "GROUND": 2, "ICE": 0, "NORMAL": 0, "POISON": 0, "PSYCHIC": 0,
        "ROCK": 1, "STEEL": 0, "WATER": 0,
    },
    "DARK": {
        "BUG": 1, "DARK": 2, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 1,
        "FIGHTING": 1, "FIRE": 0, "FLYING": 0, "GHOST": 2, "GRASS": 0,
        "GROUND": 0, "ICE": 0, "NORMAL": 0, "POISON": 0, "PSYCHIC": 3,
        "ROCK": 0, "STEEL": 0, "WATER": 0,
    },
    "DRAGON": {
        "BUG": 0, "DARK": 0, "DRAGON": 1, "ELECTRIC": 2, "FAIRY": 1,
        "FIGHTING": 0, "FIRE": 2, "FLYING": 0, "GHOST": 0, "GRASS": 2,
        "GROUND": 0, "ICE": 1, "NORMAL": 0, "POISON": 0, "PSYCHIC": 0,
        "ROCK": 0, "STEEL": 0, "WATER": 2,
    },
    "ELECTRIC": {
        "BUG": 0, "DARK": 0, "DRAGON": 0, "ELECTRIC": 2, "FAIRY": 0,
        "FIGHTING": 0, "FIRE": 0, "FLYING": 2, "GHOST": 0, "GRASS": 0,
        "GROUND": 1, "ICE": 0, "NORMAL": 0, "POISON": 0, "PSYCHIC": 0,
        "ROCK": 0, "STEEL": 2, "WATER": 0,
    },
    "FAIRY": {
        "BUG": 2, "DARK": 2, "DRAGON": 3, "ELECTRIC": 0, "FAIRY": 0,
        "FIGHTING": 2, "FIRE": 0, "FLYING": 0, "GHOST": 0, "GRASS": 0,
        "GROUND": 0, "ICE": 0, "NORMAL": 0, "POISON": 1, "PSYCHIC": 0,
        "ROCK": 0, "STEEL": 1, "WATER": 0,
    },
    "FIGHTING": {
        "BUG": 2, "DARK": 2, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 1,
        "FIGHTING": 0, "FIRE": 0, "FLYING": 1, "GHOST": 0, "GRASS": 0,
        "GROUND": 0, "ICE": 0, "NORMAL": 0, "POISON": 0, "PSYCHIC": 1,
        "ROCK": 2, "STEEL": 0, "WATER": 0,
    },
    "FIRE": {
        "BUG": 2, "DARK": 0, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 2,
        "FIGHTING": 0, "FIRE": 2, "FLYING": 0, "GHOST": 0, "GRASS": 2,
        "GROUND": 1, "ICE": 2, "NORMAL": 0, "POISON": 0, "PSYCHIC": 0,
        "ROCK": 1, "STEEL": 2, "WATER": 1,
    },
    "FLYING": {
        "BUG": 2, "DARK": 0, "DRAGON": 0, "ELECTRIC": 1, "FAIRY": 0,
        "FIGHTING": 2, "FIRE": 0, "FLYING": 0, "GHOST": 0, "GRASS": 2,
        "GROUND": 3, "ICE": 1, "NORMAL": 0, "POISON": 0, "PSYCHIC": 0,
        "ROCK": 1, "STEEL": 0, "WATER": 0,
    },
    "GHOST": {
        "BUG": 2, "DARK": 1, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 0,
        "FIGHTING": 3, "FIRE": 0, "FLYING": 0, "GHOST": 1, "GRASS": 0,
        "GROUND": 0, "ICE": 0, "NORMAL": 3, "POISON": 2, "PSYCHIC": 0,
        "ROCK": 0, "STEEL": 0, "WATER": 0,
    },
    "GRASS": {
        "BUG": 1, "DARK": 0, "DRAGON": 0, "ELECTRIC": 2, "FAIRY": 0,
        "FIGHTING": 0, "FIRE": 1, "FLYING": 1, "GHOST": 0, "GRASS": 2,
        "GROUND": 2, "ICE": 1, "NORMAL": 0, "POISON": 1, "PSYCHIC": 0,
        "ROCK": 0, "STEEL": 0, "WATER": 2,
    },
    "GROUND": {
        "BUG": 0, "DARK": 0, "DRAGON": 0, "ELECTRIC": 3, "FAIRY": 0,
        "FIGHTING": 0, "FIRE": 0, "FLYING": 0, "GHOST": 0, "GRASS": 1,
        "GROUND": 0, "ICE": 1, "NORMAL": 0, "POISON": 2, "PSYCHIC": 0,
        "ROCK": 2, "STEEL": 0, "WATER": 1,
    },
    "ICE": {
        "BUG": 0, "DARK": 0, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 0,
        "FIGHTING": 1, "FIRE": 1, "FLYING": 0, "GHOST": 0, "GRASS": 0,
        "GROUND": 0, "ICE": 2, "NORMAL": 0, "POISON": 0, "PSYCHIC": 0,
        "ROCK": 1, "STEEL": 1, "WATER": 0,
    },
    "NORMAL": {
        "BUG": 0, "DARK": 0, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 0,
        "FIGHTING": 1, "FIRE": 0, "FLYING": 0, "GHOST": 3, "GRASS": 0,
        "GROUND": 0, "ICE": 0, "NORMAL": 0, "POISON": 0, "PSYCHIC": 0,
        "ROCK": 0, "STEEL": 0, "WATER": 0,
    },
    "POISON": {
        "BUG": 2, "DARK": 0, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 2,
        "FIGHTING": 2, "FIRE": 0, "FLYING": 0, "GHOST": 0, "GRASS": 2,
        "GROUND": 1, "ICE": 0, "NORMAL": 0, "POISON": 2, "PSYCHIC": 1,
        "ROCK": 0, "STEEL": 0, "WATER": 0,
    },
    "PSYCHIC": {
        "BUG": 1, "DARK": 1, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 0,
        "FIGHTING": 2, "FIRE": 0, "FLYING": 0, "GHOST": 1, "GRASS": 0,
        "GROUND": 0, "ICE": 0, "NORMAL": 0, "POISON": 0, "PSYCHIC": 2,
        "ROCK": 0, "STEEL": 0, "WATER": 0,
    },
    "ROCK": {
        "BUG": 0, "DARK": 0, "DRAGON": 0, "ELECTRIC": 0, "FAIRY": 0,
        "FIGHTING": 1, "FIRE": 2, "FLYING": 2, "GHOST": 0, "GRASS": 1,
        "GROUND": 1, "ICE": 0, "NORMAL": 2, "POISON": 2, "PSYCHIC": 0,
        "ROCK": 0, "STEEL": 1, "WATER": 1,
    },
    "STEEL": {
        "BUG": 2, "DARK": 0, "DRAGON": 2, "ELECTRIC": 0, "FAIRY": 2,
        "FIGHTING": 1, "FIRE": 1, "FLYING": 2, "GHOST": 0, "GRASS": 2,
        "GROUND": 1, "ICE": 2, "NORMAL": 2, "POISON": 3, "PSYCHIC": 2,
        "ROCK": 2, "STEEL": 2, "WATER": 0,
    },
    "WATER": {
        "BUG": 0, "DARK": 0, "DRAGON": 0, "ELECTRIC": 1, "FAIRY": 0,
        "FIGHTING": 0, "FIRE": 2, "FLYING": 0, "GHOST": 0, "GRASS": 1,
        "GROUND": 0, "ICE": 2, "NORMAL": 0, "POISON": 0, "PSYCHIC": 0,
        "ROCK": 0, "STEEL": 2, "WATER": 2,
    },
}

def _type_name(t) -> str:
    return t.name.upper() if hasattr(t, 'name') else str(t).upper()

def compute_type_multiplier(attacking_type: str, defending_types: List[str]) -> float:
    mult = 1.0
    atk_up = attacking_type.upper()
    for dt in defending_types:
        dt_up = dt.upper()
        chart = TYPE_CHART.get(dt_up, {})
        val = chart.get(atk_up, 0)
        if val == 1:
            mult *= 2.0
        elif val == 2:
            mult *= 0.5
        elif val == 3:
            mult *= 0.0
    return mult

def type_matchup_summary(types) -> str:
    type_names = [_type_name(t) for t in types]
    
    weak_4x = []
    weak_2x = []
    resist_2x = []
    resist_4x = []
    immune = []
    
    for atk_type in TYPE_CHART:
        mult = compute_type_multiplier(atk_type, type_names)
        if mult == 4.0:
            weak_4x.append(atk_type.title())
        elif mult == 2.0:
            weak_2x.append(atk_type.title())
        elif mult == 0.5:
            resist_2x.append(atk_type.title())
        elif mult == 0.25:
            resist_4x.append(atk_type.title())
        elif mult == 0.0:
            immune.append(atk_type.title())
    
    parts = []
    if immune:
        parts.append(f"Immune: {', '.join(immune)}")
    if resist_4x:
        parts.append(f"Strong resist (¼×): {', '.join(resist_4x)}")
    if resist_2x:
        parts.append(f"Resist (½×): {', '.join(resist_2x)}")
    if weak_2x:
        parts.append(f"Weak (2×): {', '.join(weak_2x)}")
    if weak_4x:
        parts.append(f"Extremely weak (4×): {', '.join(weak_4x)}")
    
    return " | ".join(parts) if parts else "Neutral to all"

def hp_str(mon: Pokemon) -> str:
    if not mon:
        return "Fainted"
    pct = round(mon.current_hp / mon.max_hp * 100) if mon.max_hp > 0 else 0
    return f"{pct}% ({mon.current_hp}/{mon.max_hp})"

def boosts_str(mon: Pokemon) -> str:
    if not mon or not mon.boosts:
        return ""
    active = {k: v for k, v in mon.boosts.items() if v != 0}
    if not active:
        return ""
    return ", ".join(f"{k}: {v:+}" for k, v in active.items())

def status_str(mon: Pokemon) -> str:
    if not mon:
        return ""
    parts = []
    if mon.status:
        parts.append(mon.status.name)
    if mon.is_terastallized:
        parts.append(f"Tera-{mon.tera_type.name}")
    return " | ".join(parts) if parts else "Healthy"

def weather_terrain_str(battle: Battle) -> str:
    states = []
    if battle.weather:
        weather_name = next(iter(battle.weather.keys())).name if isinstance(battle.weather, dict) else str(battle.weather)
        states.append(f"Weather: {weather_name}")
    if battle.fields:
        for f in battle.fields:
            states.append(f.name)
    return ", ".join(states) if states else "Clear/Normal"

def hazards_str(side_hazards) -> str:
    if not side_hazards:
        return "None"
    items = []
    for hazard, count in side_hazards.items():
        if count > 0:
            name = hazard.name if hasattr(hazard, "name") else str(hazard)
            items.append(f"{name} (x{count})" if count > 1 else name)
    return ", ".join(items) if items else "None"

def screens_str(side_effects) -> str:
    if not side_effects:
        return "None"
    active = []
    screen_names = {"REFLECT", "LIGHT_SCREEN", "AURORA_VEIL"}
    for effect in side_effects:
        name = effect.name if hasattr(effect, "name") else str(effect)
        if name in screen_names:
            active.append(name)
    return ", ".join(active) if active else "None"

def opp_team_summary(opp_team: Dict[str, Pokemon]) -> str:
    if not opp_team:
        return "  No info yet"
    lines = []
    for name, mon in opp_team.items():
        boosts = f" [{boosts_str(mon)}]" if boosts_str(mon) else ""
        lines.append(f"  - {mon.species} | HP: {hp_str(mon)} | Status: {status_str(mon)}{boosts}")
    return "\n".join(lines)

def team_summary(team: Dict[str, Pokemon]) -> str:
    if not team:
        return "  (none)"
    lines = []
    for name, mon in team.items():
        boosts = f" [{boosts_str(mon)}]" if boosts_str(mon) else ""
        lines.append(f"  - {mon.species} | HP: {hp_str(mon)} | Status: {status_str(mon)}{boosts}")
    return "\n".join(lines)

def format_move(move: Move) -> str:
    return f"  - {move.id} ({move.type.name}, base power: {move.base_power or 0}, pp: {move.current_pp}/{move.max_pp})"

def format_target(target_value: int) -> str:
    if target_value == 0:
        return "Self/All/Field"
    elif target_value == -1:
        return "Ally Slot 1"
    elif target_value == -2:
        return "Ally Slot 2"
    elif target_value == 1:
        return "Opponent Slot 1"
    elif target_value == 2:
        return "Opponent Slot 2"
    return f"Unknown ({target_value})"

def format_order_for_display(order, battle: Battle) -> str:
    from poke_env.player.battle_order import BattleOrder, DoubleBattleOrder
    if order is None:
        return "PASS (Do nothing)"
    if isinstance(order, BattleOrder):
        if order.move:
            target_part = f" target {format_target(order.target)}" if order.target else ""
            return f"MOVE: {order.move.id}{target_part}"
        elif order.pokemon:
            return f"SWITCH: {order.pokemon.species}"
    elif isinstance(order, DoubleBattleOrder):
        part1 = format_order_for_display(order.first_order, battle)
        part2 = format_order_for_display(order.second_order, battle)
        return f"Slot 1 -> {part1} | Slot 2 -> {part2}"
    return str(order)

def format_switches(switches: List[Pokemon]) -> str:
    if not switches:
        return "  (none)"
    return "\n".join(f"  - {mon.species} (HP: {hp_str(mon)}, Status: {status_str(mon)})" for mon in switches)

def build_llm_prompt(battle: Battle, shortlist_text: str = "") -> str:
    mon = battle.active_pokemon
    opp = battle.opponent_active_pokemon

    # 1. My Active Pokémon Info
    if mon:
        mon_block = f"""
[SPECIES]: {mon.species}
[HP]: {hp_str(mon)}
[STATUS]: {status_str(mon)}
[BOOSTS]: {boosts_str(mon) or "None"}
[TYPE]: {', '.join(t.name for t in mon.types)}
[STATS]: {mon.stats or "Unknown"}
""".strip()
    else:
        mon_block = "[NONE]"

    # 2. Opponent Active Pokémon Info
    if opp:
        opp_block = f"""
[SPECIES]: {opp.species}
[HP]: {hp_str(opp)}
[STATUS]: {status_str(opp)}
[BOOSTS]: {boosts_str(opp) or "None"}
[TYPE]: {', '.join(t.name for t in opp.types)}
""".strip()
    else:
        opp_block = "[NONE]"

    # 3. Available moves for my active Pokémon
    my_moves = "  (none)"
    if battle.available_moves:
        my_moves = "\n".join(format_move(m) for m in battle.available_moves)

    # 4. Revealed moves of the opponent
    opp_moves = "  (none)"
    if opp and opp.moves:
        opp_moves = "\n".join(format_move(m) for m in opp.moves.values())

    # 5. Field conditions
    weather_terrain = weather_terrain_str(battle)
    hazards_mine = hazards_str(battle.side_conditions)
    hazards_opp = hazards_str(battle.opponent_side_conditions)
    screens = screens_str(battle.side_conditions)

    # 6. Available switches
    switches = format_switches(battle.available_switches)

    # 7. Type matchups
    my_matchup = type_matchup_summary(mon.types) if mon else ""
    opp_matchup = type_matchup_summary(opp.types) if opp else ""

    return f"""
[ROLE]
You are Blue, the rival trainer from Pallet Town — cocky, confident, and sharp. Your opponent is Red, a skilled challenger. Battle with style: make bold predictions, exploit weaknesses, and talk some light smack.

[STRATEGY GUIDELINES]
- Play the position, not the rule: switch when it clearly improves the position, but stay in if attacking, trading, or setting up is stronger.
- Predict opponent switches: if they resist your STAB, they might switch.
- Use setup moves when you have a free turn (opponent switches or uses a status move), but do not force setup if immediate pressure is better.
- Don't over-predict: if a safe move deals good damage, use it.
- Protect win conditions: keep your sweepers healthy for the late game.
- Hazards (Stealth Rock, Spikes) reward repeated switching — leverage them.
- Consider the opponent's revealed moves and team composition when choosing.

[BATTLE STATE — Turn {battle.turn}]
─── MY ACTIVE ──────────────────────────────────
{mon_block}
[TYPE_MATCHUPS]: {my_matchup}
[TERA]: Disabled (Nat Dex No Tera)

[MY MOVES]:
{my_moves}

─── OPPONENT ACTIVE ────────────────────────────
{opp_block}
[TYPE_MATCHUPS]: {opp_matchup}

[OPPONENT KNOWN MOVES]:
{opp_moves}

─── TEAMS ──────────────────────────────────────
[MY TEAM]:
{team_summary(battle.team)}

[OPPONENT TEAM]:
{opp_team_summary(battle.opponent_team)}

─── FIELD ──────────────────────────────────────
[WEATHER_TERRAIN]: {weather_terrain}
[MY SIDE]: {hazards_mine}  {screens}
[OPP SIDE]: {hazards_opp}

─── BENCH ──────────────────────────────────────
[SWITCH OPTIONS]:
{switches}

{shortlist_text}
""".strip()

def build_doubles_llm_prompt(battle: Battle, shortlist_text: str = "") -> str:
    # Double battles helper
    active_my = battle.active_pokemon
    active_opp = battle.opponent_active_pokemon

    # My actives
    mon1 = active_my[0] if len(active_my) > 0 else None
    mon2 = active_my[1] if len(active_my) > 1 else None

    # Opponent actives
    opp1 = active_opp[0] if len(active_opp) > 0 else None
    opp2 = active_opp[1] if len(active_opp) > 1 else None

    def mon_block_func(mon):
        if not mon:
            return "  [NONE / EMPTY SLOT]"
        matchup = type_matchup_summary(mon.types)
        return f"""
  Species: {mon.species}
  HP: {hp_str(mon)}
  Status: {status_str(mon)}
  Boosts: {boosts_str(mon) or "None"}
  Types: {', '.join(t.name for t in mon.types)}
  Type matchups: {matchup}
        """.strip()

    mon1_block = mon_block_func(mon1)
    mon2_block = mon_block_func(mon2)
    opp1_block = mon_block_func(opp1)
    opp2_block = mon_block_func(opp2)

    # Moves
    my_moves_1 = "  (none)"
    if len(battle.available_moves) > 0 and battle.available_moves[0]:
        my_moves_1 = "\n".join(format_move(m) for m in battle.available_moves[0])
    my_moves_2 = "  (none)"
    if len(battle.available_moves) > 1 and battle.available_moves[1]:
        my_moves_2 = "\n".join(format_move(m) for m in battle.available_moves[1])

    opp_moves_1 = "  (none)"
    if opp1 and opp1.moves:
        opp_moves_1 = "\n".join(format_move(m) for m in opp1.moves.values())
    opp_moves_2 = "  (none)"
    if opp2 and opp2.moves:
        opp_moves_2 = "\n".join(format_move(m) for m in opp2.moves.values())

    # Field/hazards
    weather_terrain = weather_terrain_str(battle)
    hazards_mine = hazards_str(battle.side_conditions)
    hazards_opp = hazards_str(battle.opponent_side_conditions)
    screens = screens_str(battle.side_conditions)

    # Switches
    switches_1 = format_switches(battle.available_switches[0]) if len(battle.available_switches) > 0 else "  (none)"
    switches_2 = format_switches(battle.available_switches[1]) if len(battle.available_switches) > 1 else "  (none)"

    return f"""
[ROLE]
You are Blue, the rival trainer from Pallet Town. This is a Doubles battle — two Pokemon on each side. Your opponent is Red. Be sharp, use synergies, and keep the pressure on.

[DOUBLES STRATEGY GUIDELINES]
- Spread moves hit both opponents — great when you're outnumbered.
- Target the bigger threat first: a setup sweeper or a Pokemon that resists your moves.
- Protect is powerful in doubles: use it to scout, stall, or block a double-target.
- Pair Pokemon that cover each other's weaknesses (e.g., Fire + Water, Electric + Ground).
- Speed control (Tailwind, Thunder Wave, Icy Wind) is extra valuable in doubles.
- Redirection moves (Follow Me, Rage Powder) protect your fragile attacker.
- Exploit your opponent's positioning: if they double-target one slot, the other is free.
- Consider Fake Out pressure — getting a free flinch is huge in doubles.

[BATTLE STATE — Turn {battle.turn}]
─── MY SLOT 1 ───────────────────────────────────
{mon1_block}

[SLOT 1 MOVES]:
{my_moves_1}

─── MY SLOT 2 ───────────────────────────────────
{mon2_block}

[SLOT 2 MOVES]:
{my_moves_2}

─── OPPONENT SLOT 1 ─────────────────────────────
{opp1_block}

[OPPONENT 1 KNOWN MOVES]:
{opp_moves_1}

─── OPPONENT SLOT 2 ─────────────────────────────
{opp2_block}

[OPPONENT 2 KNOWN MOVES]:
{opp_moves_2}

─── TEAMS ───────────────────────────────────────
[MY TEAM]:
{team_summary(battle.team)}

[OPPONENT TEAM]:
{opp_team_summary(battle.opponent_team)}

─── FIELD ───────────────────────────────────────
[WEATHER_TERRAIN]: {weather_terrain}
[MY SIDE]: {hazards_mine}  {screens}
[OPP SIDE]: {hazards_opp}

─── BENCH ───────────────────────────────────────
[SLOT 1 SWITCHES]:
{switches_1}
[SLOT 2 SWITCHES]:
{switches_2}

─── DOUBLES TARGET KEY ─────────────────────────
Target values for slot actions:
  Ally slot 1 → -1    Ally slot 2 → -2
  Opponent slot 1 → 1  Opponent slot 2 → 2
  Self / All targets → 0

{shortlist_text}
""".strip()
