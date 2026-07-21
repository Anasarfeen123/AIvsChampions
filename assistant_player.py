import asyncio
import os
import shutil
import subprocess
import argparse
import re
from typing import Optional, Any

from poke_env.player import Player
from poke_env.player.battle_order import DoubleBattleOrder, SingleBattleOrder, PassBattleOrder, DefaultBattleOrder
from poke_env.battle.battle import Battle
from poke_env.battle.double_battle import DoubleBattle
from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder

from poke_env import ShowdownServerConfiguration, LocalhostServerConfiguration
from config_manager import C, startup_wizard
from battle_hybrid import (
    action_template,
    score_double_slot_actions,
    score_single_actions,
    should_skip_llm,
    tune_actions_for_difficulty,
    summarize_actions,
)
from prompt_builder import (
    build_llm_prompt,
    build_doubles_llm_prompt,
    opp_team_summary,
    format_order_for_display,
)
from llm_client import GeminiClient, OllamaClient, PuterClient, SingleBattleDecision, DoublesBattleDecision

def copy_to_clipboard(text: str) -> bool:
    data = text.encode()
    candidates = [
        (["wl-copy"],                          {}),
        (["xclip", "-selection", "clipboard"], {}),
        (["xsel",  "--clipboard", "--input"],  {}),
        (["pbcopy"],                           {}),
    ]
    for cmd, _ in candidates:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=data, check=True, timeout=3)
                return True
            except Exception:
                pass
    return False

def _format_pct(value: Any) -> str:
    try:
        if value is None:
            return "0%"
        return f"{round(float(value) * 100)}%"
    except Exception:
        return "0%"

class PokémonAssistant(Player):
    def __init__(
        self,
        *args,
        gemini_api_key: Optional[str] = None,
        llm_provider: str = "gemini",
        ollama_model: str = "qwen2.5:7b",
        puter_model: str = "claude-3-5-sonnet",
        auto_play: bool = True,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.llm_provider = llm_provider
        self.ollama_model = ollama_model
        self.puter_model = puter_model
        self.auto_play = auto_play
        self._pending_dialogue: dict[str, str] = {}
        self._gemini_api_key = gemini_api_key
        self.difficulty_event = asyncio.Event()
        self.rematch_event = asyncio.Event()
        self.current_difficulty: Optional[str] = None
        self.browser_username: Optional[str] = None
        if llm_provider == "puter":
            self.llm_client = PuterClient(model_name=puter_model)
        elif llm_provider == "ollama":
            self.llm_client = OllamaClient(model_name=ollama_model)
        else:
            self.llm_client = GeminiClient(api_key=gemini_api_key)
        self._install_ps_message_hook()

    def _update_provider(self, provider_name: str):
        provider_name = provider_name.lower()
        if provider_name == "puter":
            self.llm_provider = "puter"
            self.llm_client = PuterClient(model_name=getattr(self, "puter_model", "claude-3-5-sonnet"))
            print(f"\n⚙️  LLM Provider switched to Puter.js ({getattr(self, 'puter_model', 'claude-3-5-sonnet')})")
        elif provider_name == "ollama":
            self.llm_provider = "ollama"
            self.llm_client = OllamaClient(model_name=getattr(self, "ollama_model", "qwen2.5:7b"))
            print(f"\n⚙️  LLM Provider switched to Ollama ({getattr(self, 'ollama_model', 'qwen2.5:7b')})")
        elif provider_name == "gemini":
            self.llm_provider = "gemini"
            self.llm_client = GeminiClient(api_key=getattr(self, "_gemini_api_key", None))
            print(f"\n⚙️  LLM Provider switched to Gemini API")

    async def _set_difficulty(self, level: str):
        self.current_difficulty = level
        print(f"\n⚙️  Difficulty set to: {level}")

    def _install_ps_message_hook(self):
        original_handle_message = self.ps_client._handle_message

        async def wrapped_handle_message(message: str):
            consumed = await self._process_browser_command(message)
            if consumed:
                return
            await original_handle_message(message)

        self.ps_client._handle_message = wrapped_handle_message

    async def _process_browser_command(self, message: str):
        try:
            consumed = False
            lines = message.split("\n")
            for line in lines:
                parts = line.split("|")
                if len(parts) >= 4 and parts[1] == "pm":
                    user1 = parts[2].strip() if len(parts) > 2 else ""
                    user2 = parts[3].strip() if len(parts) > 3 else ""
                    if self._is_valid_browser_user(user1) and user2 and user2.lower() == "blue ai":
                        self.browser_username = user1
                    elif self._is_valid_browser_user(user2) and user1 and user1.lower() == "blue ai":
                        self.browser_username = user2
                    for part in parts:
                        text = part.strip()
                        if text.startswith(("/text ", "/nonotify ", "/log ")):
                            text = text.split(" ", 1)[1].strip() if " " in text else ""
                        if text.startswith("battle-control "):
                            text = text.split(" ", 1)[1].strip() if " " in text else ""
                        if text.startswith("puter "):
                            val = text.split(" ", 1)[1].strip().lower()
                            if val in ("on", "true"):
                                self._update_provider("puter")
                            elif val in ("off", "false"):
                                self._update_provider("ollama" if hasattr(self, "ollama_model") else "gemini")
                            return True
                        if text.startswith("provider "):
                            p_val = text.split(" ", 1)[1].strip().lower()
                            self._update_provider(p_val)
                            return True
                        if text.startswith("!difficulty"):
                            parts2 = text.split(" ", 1)
                            level = parts2[1].strip().lower() if len(parts2) > 1 else None
                            if level in ("easy", "medium", "hard"):
                                await self._set_difficulty(level)
                                self.difficulty_event.set()
                                return True
                        if text.startswith("difficulty "):
                            level = text.split(" ", 1)[1].strip().lower()
                            if level in ("easy", "medium", "hard"):
                                await self._set_difficulty(level)
                                self.difficulty_event.set()
                                return True
                        elif text == "!rematch":
                            self.rematch_event.set()
                            return True
                        elif text == "rematch":
                            self.rematch_event.set()
                            return True
                if len(parts) >= 4 and parts[1] == "c:" and "battle-control " in line:
                    consumed = True
                    self.logger.info("Received battle-control line: %s", line)
                    sender = parts[3].strip() if len(parts) > 3 else ""
                    if self._is_valid_browser_user(sender):
                        self.browser_username = sender
                        self.logger.info("Browser username set to: %s", self.browser_username)
                    else:
                        self.logger.warning("Ignoring invalid browser username from control line: %r", sender)
                    match = re.search(r"battle-control\s+([a-zA-Z]+)(?:\s+([a-zA-Z]+))?", line)
                    if not match:
                        continue
                    action = match.group(1).lower()
                    value = (match.group(2) or "").lower()
                    if action == "puter":
                        if value in ("on", "true", ""):
                            self._update_provider("puter")
                        elif value in ("off", "false"):
                            self._update_provider("ollama" if hasattr(self, "ollama_model") else "gemini")
                        return True
                    if action == "provider" and value:
                        self._update_provider(value)
                        return True
                    if action == "difficulty" and value in ("easy", "medium", "hard"):
                        await self._set_difficulty(value)
                        self.difficulty_event.set()
                        return True
                    if action == "rematch":
                        self.rematch_event.set()
                        return True
            return consumed
        except Exception as e:
            self.logger.error("Error handling browser command: %s", e)
            return False

    def _is_valid_browser_user(self, name: str) -> bool:
        userid = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
        return bool(userid) and userid not in {"blueai", "guest", "guest1", "guest2", "system"}

    def get_browser_username(self) -> Optional[str]:
        return self.browser_username

    def _non_tera_orders(self, orders):
        return [order for order in orders if not getattr(order, "terastallize", False)]

    def _battle_dialogue_values(self, battle, action: Optional[Any] = None) -> dict[str, str]:
        def first_active(pokemon_or_list):
            if isinstance(pokemon_or_list, (list, tuple)):
                for mon in pokemon_or_list:
                    if mon:
                        return mon
                return None
            return pokemon_or_list

        pokemon = first_active(battle.active_pokemon)
        opponent = first_active(battle.opponent_active_pokemon)

        move_name = ""
        if action is not None:
            move_name = getattr(action, "label", "") or getattr(getattr(action, "move", None), "name", "") or ""
            if move_name.startswith("Switch to "):
                move_name = move_name.replace("Switch to ", "", 1)

        weather = "none"
        if getattr(battle, "weather", None):
            try:
                weather = next(iter(battle.weather.keys())).name
            except Exception:
                weather = str(battle.weather)

        terrain = "none"
        if getattr(battle, "fields", None):
            try:
                terrain = ", ".join(field.name for field in battle.fields) or "none"
            except Exception:
                terrain = str(battle.fields)

        status = ""
        if pokemon and getattr(pokemon, "status", None):
            status = pokemon.status.name

        return {
            "pokemon": getattr(pokemon, "species", "Blue") if pokemon else "Blue",
            "opponent": getattr(opponent, "species", "Red") if opponent else "Red",
            "move": move_name or "that play",
            "my_hp": _format_pct(getattr(pokemon, "current_hp_fraction", 0)),
            "opp_hp": _format_pct(getattr(opponent, "current_hp_fraction", 0)),
            "status": status or "healthy",
            "weather": weather,
            "terrain": terrain,
            "turn": str(getattr(battle, "turn", 0)),
        }

    def _render_dialogue(self, battle, raw_dialogue: Optional[str], action: Optional[Any] = None) -> Optional[str]:
        if not raw_dialogue:
            return None
        text = " ".join(str(raw_dialogue).replace("\n", " ").split()).strip().strip('"').strip("'")
        if not text:
            return None
        values = self._battle_dialogue_values(battle, action)

        def replace_placeholder(match):
            key = match.group(1).lower()
            return values.get(key, match.group(0))

        text = re.sub(r"%([a-z_]+)%", replace_placeholder, text)
        return text[:240]

    def _battle_finished_callback(self, battle):
        tag = battle.battle_tag
        dialogue = self._pending_dialogue.pop(tag, None)
        messages = []
        if dialogue:
            messages.append(dialogue)
        if battle.won:
            messages.append("Hah! Too easy. Better luck next time, Red!")
        elif battle.lost:
            messages.append("Tch... You got me this time, Red. But I'll be back!")
        else:
            messages.append("A tie? Let's call it a draw, Red.")
        asyncio.ensure_future(self._send_delayed(tag, messages))

    async def _send_delayed(self, tag: str, messages: list[str]):
        for msg in messages:
            try:
                await self.ps_client.send_message(msg, room=tag)
            except Exception:
                self.logger.debug("Skipping post-battle message for %s", tag, exc_info=True)
                break

    def _auto_single_order(self, battle):
        if battle.available_moves:
            move = battle.available_moves[0]
            print(f"\n🤖  Auto fallback: move {move.id}")
            return self.create_order(move)
        if battle.available_switches:
            switch = battle.available_switches[0]
            print(f"\n🤖  Auto fallback: switch to {switch.species}")
            return self.create_order(switch)
        return self.choose_random_move(battle)

    # ── TEAM PREVIEW ──────────────────────────────────────────────────────────
    async def teampreview(self, battle) -> str:
        await self.ps_client.send_message(f"/join {battle.battle_tag}")
        print("\n" + "═" * 70)
        print("🔍  STRATEGY PHASE: TEAM PREVIEW")
        print(f"\nOpponent's revealed team:\n{opp_team_summary(battle.opponent_team)}")
        print("═" * 70)

        team_list = list(battle.team.values())
        print("\n📋  YOUR TEAM:")
        for i, mon in enumerate(team_list, 1):
            print(f"  [{i}] {mon.species}")

        is_doubles = isinstance(battle, DoubleBattle)
        if self.auto_play:
            if is_doubles:
                lead_count = min(2, len(team_list))
                leads = " and ".join(mon.species for mon in team_list[:lead_count])
                print(f"\n🤖  Auto lead: {leads}")
                return "/team " + "".join(str(i) for i in range(1, len(team_list) + 1))
            print(f"\n🤖  Auto lead: {team_list[0].species}")
            return "/team " + "".join(str(i) for i in range(1, len(team_list) + 1))

        if is_doubles:
            print("\n[DECISION] Choose Lead 1 and Lead 2 (Enter number 1–6)")
            lead_idx_1 = -1
            lead_idx_2 = -1
            while True:
                try:
                    choice1 = await asyncio.to_thread(input, "Lead 1 > ")
                    idx1 = int(choice1.strip()) - 1
                    if 0 <= idx1 < len(team_list):
                        lead_idx_1 = idx1
                        break
                    print(f"❌  Pick a number between 1 and {len(team_list)}")
                except (ValueError, EOFError):
                    print("❌  Invalid input. Please enter a number.")
            while True:
                try:
                    choice2 = await asyncio.to_thread(input, "Lead 2 > ")
                    idx2 = int(choice2.strip()) - 1
                    if 0 <= idx2 < len(team_list) and idx2 != lead_idx_1:
                        lead_idx_2 = idx2
                        break
                    if idx2 == lead_idx_1:
                        print("❌  Lead 2 cannot be the same as Lead 1.")
                    else:
                        print(f"❌  Pick a number between 1 and {len(team_list)}")
                except (ValueError, EOFError):
                    print("❌  Invalid input. Please enter a number.")
            
            order = list(range(1, len(team_list) + 1))
            val1 = lead_idx_1 + 1
            val2 = lead_idx_2 + 1
            order.remove(val1)
            order.remove(val2)
            order.insert(0, val2)
            order.insert(0, val1)
            return "/team " + "".join(map(str, order))
        else:
            print("\n[DECISION] Who should LEAD? (Enter number 1–6)")
            while True:
                try:
                    choice = await asyncio.to_thread(input, "Lead > ")
                    idx = int(choice.strip()) - 1
                    if 0 <= idx < len(team_list):
                        order = list(range(1, len(team_list) + 1))
                        order.insert(0, order.pop(idx))
                        return "/team " + "".join(map(str, order))
                    print(f"❌  Pick a number between 1 and {len(team_list)}")
                except (ValueError, EOFError):
                    print("❌  Invalid input. Please enter a number.")

    # ── MAIN DECISION LOOP ────────────────────────────────────────────────────
    async def choose_move(self, battle) -> DoubleBattleOrder | SingleBattleOrder | DefaultBattleOrder:
        if isinstance(battle, DoubleBattle):
            return await self.choose_doubles_move(battle)

        await self.ps_client.send_message(f"/join {battle.battle_tag}")
        me  = battle.active_pokemon
        opp = battle.opponent_active_pokemon

        if not me or not opp:
            return self.choose_random_move(battle)

        if self.auto_play and (self.llm_client is None or not self.llm_client.is_configured()):
            return self._auto_single_order(battle)

        ranked_actions = score_single_actions(battle)
        if not ranked_actions:
            return self._auto_single_order(battle) if self.auto_play else self.choose_random_move(battle)

        shortlist = tune_actions_for_difficulty(ranked_actions, self.current_difficulty)[:3]
        shortlist_text = "─── TOP OPTIONS ───────────────────────────────────────\n" + summarize_actions(shortlist)
        prompt = build_llm_prompt(battle, shortlist_text=shortlist_text)
        clipboard_ok = copy_to_clipboard(prompt)

        print("\n" + "═" * 70)
        print(prompt)
        print("═" * 70)

        if clipboard_ok:
            print("\n✅  Prompt copied to clipboard — paste into your AI chat (Ctrl+V).")
        else:
            print("\n⚠️   Clipboard unavailable. Copy the prompt above manually.")

        print("\n📋  TOP ACTIONS:")
        for i, a in enumerate(shortlist, 1):
            print(f"    [{i}]  →  {a.label}  (score {a.score:.1f})")
        if len(ranked_actions) > len(shortlist):
            print(f"    ... {len(ranked_actions) - len(shortlist)} more legal actions hidden")

        if should_skip_llm(shortlist):
            chosen_action = shortlist[0]
            print(f"\n🤖  Heuristic Decision: {chosen_action.label}")
            print(f"💬  Reasoning: {chosen_action.reason}")
            dialogue = self._render_dialogue(battle, action_template(chosen_action), chosen_action)
            if dialogue:
                self._pending_dialogue[battle.battle_tag] = dialogue
            if chosen_action.kind == "move":
                return self.create_order(chosen_action.order)
            if chosen_action.kind == "switch":
                return self.create_order(chosen_action.order)
            return self._auto_single_order(battle)

        # Query Gemini if configured
        if self.llm_client and self.llm_client.is_configured():
            # Send previous turn's dialogue after the turn resolved
            prev_dialogue = self._pending_dialogue.pop(battle.battle_tag, None)
            if prev_dialogue:
                await self.ps_client.send_message(prev_dialogue, room=battle.battle_tag)

            full_prompt = f"{prompt}\n\nSelect one top option above. If a lower option is clearly safer, explain why in the reasoning. Respond with the schema."
            
            decision = await self.llm_client.get_decision(full_prompt, SingleBattleDecision)
            if decision:
                reason = decision.get("reasoning_summary")
                action_idx = decision.get("action_index", 1) - 1
                
                if 0 <= action_idx < len(shortlist):
                    chosen_action = shortlist[action_idx]
                    provider_title = "Ollama" if self.llm_provider == "ollama" else "Gemini"
                    print(f"\n🤖  {C.GREEN}{C.BOLD}{provider_title} Decision:{C.RESET} {chosen_action.label}")
                    print(f"💬  {C.YELLOW}Reasoning:{C.RESET} {reason}")
                    
                    dialogue_clean = None
                    dialogue = decision.get("rival_dialogue")
                    if dialogue:
                        dialogue_clean = self._render_dialogue(battle, dialogue, chosen_action)
                        if not dialogue_clean:
                            dialogue_clean = self._render_dialogue(battle, action_template(chosen_action), chosen_action)
                    if dialogue_clean:
                        print(f"🗣️  {C.CYAN}{C.BOLD}Rival Dialogue:{C.RESET} {dialogue_clean}")
                        self._pending_dialogue[battle.battle_tag] = dialogue_clean
                    
                    if chosen_action.kind in ("move", "switch"):
                        return self.create_order(chosen_action.order)
                else:
                    print(f"\n❌  Gemini selected invalid action index: {action_idx + 1}")

        # Fallback to manual selection
        if self.auto_play:
            return self._auto_single_order(battle)

        print("\nCommands:  move <n>  |  switch <n>  |  c (re-copy prompt)")

        while True:
            try:
                raw = await asyncio.to_thread(input, "\n[DECISION] > ")
            except (EOFError, KeyboardInterrupt):
                print("\nInterrupted — picking random move.")
                return self.choose_random_move(battle)

            tokens = raw.strip().lower().split()
            if not tokens:
                continue

            if tokens[0] == "c":
                if copy_to_clipboard(prompt):
                    print("✅  Prompt copied to clipboard!")
                else:
                    print("⚠️   Clipboard unavailable.")
                continue

            try:
                if tokens[0] == "tera":
                    print("❌  Terastalization is disabled: format is National Dex OU (No Tera).")
                    continue

                if tokens[0] == "move" and len(tokens) > 1:
                    idx = int(tokens[1]) - 1
                    return self.create_order(battle.available_moves[idx])

                elif tokens[0] == "switch" and len(tokens) > 1:
                    idx = int(tokens[1]) - 1
                    return self.create_order(battle.available_switches[idx])

                else:
                    print("❌  Unknown command. Use:  move <n>  |  switch <n>  |  c")

            except (ValueError, IndexError):
                print(
                    f"❌  Invalid index. "
                    f"Moves: 1–{len(battle.available_moves)}  |  "
                    f"Switches: 1–{len(battle.available_switches)}"
                )

    async def choose_doubles_move(self, battle: DoubleBattle) -> DoubleBattleOrder:
        await self.ps_client.send_message(f"/join {battle.battle_tag}")
        slot_ranked = [score_double_slot_actions(battle, 0), score_double_slot_actions(battle, 1)]
        slot_shortlists = [
            tune_actions_for_difficulty(ranked, self.current_difficulty)[:3]
            for ranked in slot_ranked
        ]

        if all(slot_shortlists[slot] and should_skip_llm(slot_shortlists[slot]) for slot in range(2)):
            final_orders = [slot_shortlists[0][0].order, slot_shortlists[1][0].order]
            print(f"\n🤖  Heuristic Doubles Decision: Slot 1 -> {slot_shortlists[0][0].label} | Slot 2 -> {slot_shortlists[1][0].label}")
            print(f"💬  Slot 1: {slot_shortlists[0][0].reason}")
            print(f"💬  Slot 2: {slot_shortlists[1][0].reason}")
            return DoubleBattleOrder(first_order=final_orders[0], second_order=final_orders[1])

        slot_texts = []
        for slot in range(2):
            slot_texts.append(
                f"─── TOP OPTIONS SLOT {slot + 1} ─────────────────────────\n"
                + summarize_actions(slot_shortlists[slot])
            )
        prompt = build_doubles_llm_prompt(battle, shortlist_text="\n\n".join(slot_texts))
        clipboard_ok = copy_to_clipboard(prompt)

        print("\n" + "═" * 70)
        print(prompt)
        print("═" * 70)

        if clipboard_ok:
            print("\n✅  Prompt copied to clipboard — paste into your AI chat (Ctrl+V).")
        else:
            print("\n⚠️   Clipboard unavailable. Copy the prompt above manually.")

        final_orders = [None, None]
        slot_actions = slot_shortlists

        # Query Gemini if configured
        if self.llm_client and self.llm_client.is_configured():
            # Send previous turn's dialogue after the turn resolved
            prev_dialogue = self._pending_dialogue.pop(battle.battle_tag, None)
            if prev_dialogue:
                await self.ps_client.send_message(prev_dialogue, room=battle.battle_tag)

            actions_str = ""
            for slot in range(2):
                actions_str += f"\n─── ACTIONS SLOT {slot+1} ───────────────────────────\n"
                if not slot_actions[slot]:
                    actions_str += "  [1] PASS (No action available)\n"
                else:
                    for i, a in enumerate(slot_actions[slot]):
                        actions_str += f"  [{i+1}] {a.label}\n"
            
            full_prompt = f"{prompt}\n\n{actions_str}\n\nPick one top option for Slot 1 and one for Slot 2. Respond with the schema."
            
            decision = await self.llm_client.get_decision(full_prompt, DoublesBattleDecision)
            if decision:
                reason = decision.get("reasoning_summary")
                provider_title = "Ollama" if self.llm_provider == "ollama" else "Gemini"
                print(f"\n🤖  {C.GREEN}{C.BOLD}{provider_title} Doubles Decision:{C.RESET}")
                print(f"💬  {C.YELLOW}Reasoning:{C.RESET} {reason}")
                
                dialogue_clean = None
                dialogue = decision.get("rival_dialogue")
                if dialogue:
                    chosen_candidates = []
                    for slot in range(2):
                        if not slot_actions[slot]:
                            continue
                        key = f"slot{slot+1}_action_index"
                        action_idx = decision.get(key, 1) - 1
                        if 0 <= action_idx < len(slot_actions[slot]):
                            chosen_candidates.append(slot_actions[slot][action_idx])
                    if chosen_candidates:
                        chosen_candidates.sort(key=lambda a: a.score, reverse=True)
                        dialogue_clean = self._render_dialogue(battle, dialogue, chosen_candidates[0])
                    if not dialogue_clean and slot_actions[0]:
                        dialogue_clean = self._render_dialogue(battle, action_template(slot_actions[0][0]), slot_actions[0][0])
                    if dialogue_clean:
                        print(f"🗣️  {C.CYAN}{C.BOLD}Rival Dialogue:{C.RESET} {dialogue_clean}")
                        self._pending_dialogue[battle.battle_tag] = dialogue_clean
                
                for slot in range(2):
                    active_mon = battle.active_pokemon[slot]
                    if not slot_actions[slot]:
                        final_orders[slot] = PassBattleOrder()
                        continue
                    
                    key = f"slot{slot+1}_action_index"
                    action_idx = decision.get(key, 1) - 1
                    
                    if 0 <= action_idx < len(slot_actions[slot]):
                        chosen = slot_actions[slot][action_idx]
                        print(f"  Slot {slot+1} action: {chosen.label}")
                        final_orders[slot] = chosen.order
                    else:
                        print(f"  Slot {slot+1} action index invalid ({action_idx+1}), using first option.")
                        final_orders[slot] = slot_actions[slot][0].order
                
                return DoubleBattleOrder(first_order=final_orders[0] or PassBattleOrder(), second_order=final_orders[1] or PassBattleOrder())

        # Fallback to manual selection
        if self.auto_play:
            for slot in range(2):
                if slot_actions[slot]:
                    final_orders[slot] = slot_actions[slot][0].order
                    print(f"\n🤖  Auto fallback slot {slot + 1}: {slot_actions[slot][0].label}")
                else:
                    final_orders[slot] = PassBattleOrder()
            return DoubleBattleOrder(first_order=final_orders[0] or PassBattleOrder(), second_order=final_orders[1] or PassBattleOrder())

        for slot in range(2):
            active_mon = battle.active_pokemon[slot]
            non_pass_orders = [a.order for a in slot_actions[slot]]

            if not non_pass_orders:
                final_orders[slot] = PassBattleOrder()
                print(f"\nSlot {slot + 1} ({active_mon.species if active_mon else 'Empty'}): PASS (No action available)")
                continue

            print(f"\n📋  AVAILABLE ACTIONS FOR SLOT {slot + 1} ({active_mon.species if active_mon else 'Empty'}):")
            for idx, action in enumerate(slot_actions[slot], 1):
                print(f"    [{idx}]  →  {action.label}")

            print(f"Commands for Slot {slot + 1}: Enter choice number (1-{len(non_pass_orders)}) | 'c' to copy prompt")

            while True:
                try:
                    raw = await asyncio.to_thread(input, f"[SLOT {slot + 1} DECISION] > ")
                except (EOFError, KeyboardInterrupt):
                    print("\nInterrupted — picking random move.")
                    return self.choose_random_move(battle)

                choice = raw.strip().lower()
                if not choice:
                    continue

                if choice == "c":
                    if copy_to_clipboard(prompt):
                        print("✅  Prompt copied to clipboard!")
                    else:
                        print("⚠️   Clipboard unavailable.")
                    continue

                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(non_pass_orders):
                        final_orders[slot] = non_pass_orders[idx]
                        break
                    print(f"❌  Pick a number between 1 and {len(non_pass_orders)}")
                except ValueError:
                    print(f"❌  Invalid input. Enter a choice number.")

        return DoubleBattleOrder(first_order=final_orders[0] or PassBattleOrder(), second_order=final_orders[1] or PassBattleOrder())

    async def choose_move_order(self, battle) -> DoubleBattleOrder | SingleBattleOrder | DefaultBattleOrder:
        return await self.choose_move(battle)


async def main():
    parser = argparse.ArgumentParser(description="Pokémon Showdown AI Assistant")
    parser.add_argument("--wizard", "-w", action="store_true", help="Run the interactive setup wizard")
    parser.add_argument("--provider", "-p", choices=["gemini", "ollama"], default="ollama", help="LLM Provider (default: ollama)")
    parser.add_argument("--model", "-m", default="qwen2.5:7b", help="Ollama model name (default: qwen2.5:7b)")
    parser.add_argument("--server", "-s", choices=["localhost", "showdown"], default="localhost", help="Server to connect to (default: localhost)")
    parser.add_argument("--battles", "-b", type=int, default=1, help="Number of battles to play (default: 1)")
    parser.add_argument("--opponent", "-o", default="AI", help="Opponent username to challenge (default: AI)")
    
    args = parser.parse_args()

    if args.wizard:
        cfg = startup_wizard()
        team_str  = cfg["_team"]
        opponent  = cfg["_opponent"]
        username  = cfg["username"]
        password  = cfg["password"] or None
        fmt       = cfg["format"]
        num       = cfg["num_battles"]
        mode      = cfg["mode"]
        server    = cfg["server"]
        llm_provider = cfg.get("llm_provider", "gemini")
        ollama_model = cfg.get("ollama_model", "qwen2.5:7b")
        gemini_api_key = cfg.get("gemini_api_key")
    else:
        # Load from config files or default
        from config_manager import RED_MT_SILVER_TEAM, BLUE_TEAM
        team_str = RED_MT_SILVER_TEAM
        opponent = args.opponent
        username = "User"
        password = None
        fmt = "gen9nationaldexounotera"
        num = args.battles
        mode = "challenge"
        server = args.server
        llm_provider = args.provider
        ollama_model = args.model
        gemini_api_key = os.environ.get("GEMINI_API_KEY")

    server_cfg = (
        LocalhostServerConfiguration if server == "localhost"
        else ShowdownServerConfiguration
    )

    teambuilder = ConstantTeambuilder(team_str)

    bot = PokémonAssistant(
        account_configuration=AccountConfiguration(username, password),
        gemini_api_key=gemini_api_key,
        llm_provider=llm_provider,
        ollama_model=ollama_model,
        auto_play=True,
        battle_format=fmt,
        team=teambuilder,
        server_configuration=server_cfg,
    )

    print(f"\n{C.GREEN}{C.BOLD}🤖  Bot '{username}' is online.{C.RESET}")
    print(f"📦  Team loaded.")
    print(f"🎮  Format: {fmt}")
    
    if llm_provider == "ollama":
        print(f"🧠  LLM Model: Ollama ({ollama_model})")
    else:
        print(f"🧠  LLM Model: Gemini API")

    if mode == "accept":
        print("⏳  Waiting for an incoming challenge…\n")
        await bot.accept_challenges(None, num)

    elif mode == "challenge":
        print(f"⚔️   Challenging {C.YELLOW}{opponent}{C.RESET}…\n")
        await bot.send_challenges(opponent, num)

    elif mode == "ladder":
        print("🔍  Seeking a ladder match…\n")
        await bot.ladder(num)


if __name__ == "__main__":
    asyncio.run(main())
