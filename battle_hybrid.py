from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from poke_env.battle.move import Move
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.pokemon import Pokemon
from poke_env.battle.side_condition import SideCondition
from poke_env.player.battle_order import BattleOrder


@dataclass(frozen=True)
class RankedAction:
    kind: str
    index: int
    label: str
    score: float
    reason: str
    order: Any = None
    slot: Optional[int] = None


ENTRY_HAZARDS = {
    "spikes": SideCondition.SPIKES,
    "stealthrock": SideCondition.STEALTH_ROCK,
    "stickyweb": SideCondition.STICKY_WEB,
    "toxicspikes": SideCondition.TOXIC_SPIKES,
}

ANTI_HAZARDS = {"rapidspin", "defog"}
SETUP_MOVES = {"swordsdance", "nastyplot", "calmmind", "dragondance", "bulkup", "shellsmash", "quiverdance"}
PIVOT_MOVES = {"uturn", "voltswitch", "flipturn"}
RECOVERY_MOVES = {"recover", "roost", "slackoff", "morningsun", "moonlight", "synthesis", "milkdrink", "softboiled"}


def _type_name(t: Any) -> str:
    return t.name.upper() if hasattr(t, "name") else str(t).upper()


def _stat_estimation(mon: Pokemon, stat: str) -> float:
    boosts = mon.boosts.get(stat, 0) if mon.boosts else 0
    if boosts > 1:
        boost = (2 + boosts) / 2
    else:
        boost = 2 / (2 - boosts)
    return ((2 * mon.base_stats[stat] + 31) + 5) * boost


def estimate_matchup(mon: Pokemon, opponent: Pokemon) -> float:
    if not mon or not opponent:
        return 0.0
    score = max([opponent.damage_multiplier(t) for t in mon.types if t is not None], default=1.0)
    score -= max([mon.damage_multiplier(t) for t in opponent.types if t is not None], default=1.0)
    if mon.base_stats["spe"] > opponent.base_stats["spe"]:
        score += 0.1
    elif opponent.base_stats["spe"] > mon.base_stats["spe"]:
        score -= 0.1
    score += mon.current_hp_fraction * 0.4
    score -= opponent.current_hp_fraction * 0.4
    return score


def _move_offense_score(move: Move, active: Pokemon, opponent: Pokemon) -> Tuple[float, str]:
    base_power = float(move.base_power or 0)
    accuracy = float(move.accuracy or 1.0)
    if accuracy > 1:
        accuracy /= 100.0
    hits = float(move.expected_hits or 1)
    stab = float(active.stab_multiplier(move.type)) if hasattr(active, "stab_multiplier") else 1.0
    effectiveness = float(opponent.damage_multiplier(move))

    if move.category == MoveCategory.PHYSICAL:
        ratio = _stat_estimation(active, "atk") / max(_stat_estimation(opponent, "def"), 1.0)
    elif move.category == MoveCategory.SPECIAL:
        ratio = _stat_estimation(active, "spa") / max(_stat_estimation(opponent, "spd"), 1.0)
    else:
        ratio = 1.0

    score = base_power * stab * effectiveness * accuracy * hits * ratio
    notes: List[str] = []
    if stab > 1:
        notes.append("STAB")
    if effectiveness >= 2:
        notes.append("super-effective")
    elif effectiveness == 0:
        notes.append("immune")
    elif effectiveness < 1:
        notes.append("resisted")
    if move.priority:
        score += move.priority * 12
        notes.append(f"priority +{move.priority}")
    if move.recoil:
        score -= 5
        notes.append("recoil")
    if move.drain:
        score += 4
        notes.append("drain")
    if move.force_switch:
        score += 10
        notes.append("forces switch")
    return score, ", ".join(notes) if notes else "direct damage"


def _move_status_score(move: Move, battle, active: Pokemon, opponent: Pokemon) -> Tuple[float, str]:
    move_id = move.id
    notes: List[str] = []
    score = 8.0

    if move_id in ENTRY_HAZARDS:
        if ENTRY_HAZARDS[move_id] not in battle.opponent_side_conditions:
            score += 25
            notes.append("hazard setup")
        else:
            score -= 6
            notes.append("hazard already up")
    if move_id in ANTI_HAZARDS and battle.side_conditions:
        score += 18
        notes.append("hazard removal")
    if move_id in SETUP_MOVES:
        if active.current_hp_fraction >= 0.7 and estimate_matchup(active, opponent) >= 0:
            score += 30
            notes.append("safe setup")
        else:
            score += 8
            notes.append("setup")
    if move_id in PIVOT_MOVES:
        score += 14
        notes.append("pivot")
    if move_id in RECOVERY_MOVES:
        if active.current_hp_fraction <= 0.55:
            score += 26
            notes.append("needed recovery")
        else:
            score += 4
            notes.append("minor recovery")
    if move.status and active.status is None and opponent.status is None:
        score += 12
        notes.append("status pressure")
    if move.self_boost:
        boost_sum = sum(v for v in move.self_boost.values() if v > 0)
        score += boost_sum * 5
        notes.append("self boost")
    if move.side_condition:
        score += 10
        notes.append("side condition")
    if move.weather or move.terrain:
        score += 6
        notes.append("field control")
    if move.heal:
        score += 10
        notes.append("healing")
    if move.self_destruct or move.self_switch:
        score -= 20
        notes.append("self-sacrifice")
    return score, ", ".join(notes) if notes else "utility"


def score_single_actions(battle) -> List[RankedAction]:
    active = battle.active_pokemon
    opponent = battle.opponent_active_pokemon
    if not active or not opponent:
        return []

    actions: List[RankedAction] = []

    for idx, move in enumerate(battle.available_moves):
        if move.base_power and move.base_power > 0:
            score, reason = _move_offense_score(move, active, opponent)
        else:
            score, reason = _move_status_score(move, battle, active, opponent)
        label = f"{move.id.replace('-', ' ').title()}"
        actions.append(RankedAction("move", idx, label, score, reason, order=move))

    for idx, switch in enumerate(battle.available_switches):
        matchup = estimate_matchup(switch, opponent)
        current = estimate_matchup(active, opponent)
        score = (matchup - current) * 45 + switch.current_hp_fraction * 20
        notes = ["better matchup" if matchup > current else "safer switch"]
        if switch.current_hp_fraction < 0.3:
            score -= 10
            notes.append("low HP")
        if switch.status:
            score -= 4
            notes.append("status")
        actions.append(
            RankedAction("switch", idx, f"Switch to {switch.species}", score, ", ".join(notes), order=switch)
        )

    actions.sort(key=lambda a: a.score, reverse=True)
    return actions


def score_double_slot_actions(battle, slot: int) -> List[RankedAction]:
    active = battle.active_pokemon[slot] if len(battle.active_pokemon) > slot else None
    opponents = [p for p in battle.opponent_active_pokemon if p]
    if not active:
        return []

    actions: List[RankedAction] = []
    slot_orders = battle.valid_orders[slot]
    for idx, order in enumerate(slot_orders):
        if not isinstance(order, BattleOrder):
            continue
        label = "PASS" if order.pokemon is None and order.move is None else str(order)
        score = 0.0
        reason = "fallback"
        if order.move:
            move = order.move
            target_scores = []
            for opp in opponents:
                if move.base_power and move.base_power > 0:
                    target_scores.append(_move_offense_score(move, active, opp)[0])
                else:
                    target_scores.append(_move_status_score(move, battle, active, opp)[0])
            score = max(target_scores) if target_scores else 0.0
            reason = "best target among active opponents"
        elif order.pokemon:
            best_opp = max((estimate_matchup(order.pokemon, opp) for opp in opponents), default=0.0)
            current = max((estimate_matchup(active, opp) for opp in opponents), default=0.0)
            score = (best_opp - current) * 45 + order.pokemon.current_hp_fraction * 20
            reason = "better slot matchup"
        actions.append(RankedAction("order", idx, label, score, reason, order=order, slot=slot))

    actions.sort(key=lambda a: a.score, reverse=True)
    return actions


def summarize_actions(actions: List[RankedAction], limit: int = 3) -> str:
    lines = []
    for i, action in enumerate(actions[:limit], 1):
        lines.append(f"{i}. {action.label} (score {action.score:.1f}) - {action.reason}")
    return "\n".join(lines) if lines else "  (no options)"


def should_skip_llm(actions: List[RankedAction]) -> bool:
    if not actions:
        return True
    if len(actions) == 1:
        return True
    top = actions[0]
    second = actions[1]
    if top.score >= second.score + 18:
        return True
    if top.kind == "move" and top.score >= 85 and (top.score - second.score) >= 10:
        return True
    if top.kind == "switch" and top.score >= 40 and (top.score - second.score) >= 15:
        return True
    return False


def action_template(action: RankedAction) -> str:
    if action.kind == "move":
        return f"Blue sees the opening and uses {action.label}."
    if action.kind == "switch":
        return f"Blue pivots to {action.label.replace('Switch to ', '')}."
    return "Blue keeps pressure on."
