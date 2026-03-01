"""
Evaluator for game states from a player's perspective.
Usage: Evaluator.evaluate_new. evaluate(for testing different evaluation methods)(used in simulate_games.py) is not implemented
"""
from typing import TYPE_CHECKING
import cards
if TYPE_CHECKING:
    from ai_player_new import GameStateSnapshot
    

class Evaluator:
    @staticmethod
    def evaluate_new(state: GameStateSnapshot, player: int, only_care_about_winorlose: bool) -> float:
        # Weight constants for evaluation
        HP_WEIGHT = 2.0
        LOW_HP_THRESHOLD = 10
        LOW_HP_URGENCY_WEIGHT = 3.0
        HP_DEFICIT_SPIKE = 10
        HP_DEFICIT_SPIKE_WEIGHT = 4.0
        FIELD_POWER_WEIGHT = 1.0
        FIELD_POWER_OPP_ATTACK_ABILITY_WEIGHT = 0.2 # The opponent followers can attack? bad news bears
        HAND_SIZE_WEIGHT = 2.0 # Could be 4.0, but should prefer board presence more
        LOW_HAND_SIZE_THRESHOLD = 5
        LOW_HAND_SIZE_WEIGHT = 2.0 # If hand size is very low, it's more urgent to have cards in hand
        HAND_POWER_WEIGHT = 0.5
        DECK_SIZE_WEIGHT = 0.1

        # NOTE: this method is called after the player's turn ends
        opponent = 3 - player

        # Check for game end
        if state.concluded:
            if state.winner == player:
                return float('inf')
            elif state.winner == opponent:
                return float('-inf')
            else:
                return 0.0
            
        # Useful when simulating the last turn, for either of the players
        # for example at depth 1, care about score on your turn, but not on opponent turn (last turn)
        # for performance reasons, depth > 1 is not considered.
        if only_care_about_winorlose:
            return 0.0

        score = 100.0 # Base score

        # HP difference
        own_hp_value = state.hp[player]
        opp_hp_value = state.hp[opponent]
        score += (own_hp_value - opp_hp_value) * HP_WEIGHT

        # Low-HP urgency: HP below threshold is much more valuable/critical.
        own_missing_hp = max(0, LOW_HP_THRESHOLD - own_hp_value)
        opp_missing_hp = max(0, LOW_HP_THRESHOLD - opp_hp_value)
        score += (opp_missing_hp - own_missing_hp) * LOW_HP_URGENCY_WEIGHT

        # Large HP gap spike: if one side is behind by 10+ HP, emphasize that disadvantage.
        hp_gap = own_hp_value - opp_hp_value
        if hp_gap <= -HP_DEFICIT_SPIKE:
            score -= (abs(hp_gap) - HP_DEFICIT_SPIKE + 1) * HP_DEFICIT_SPIKE_WEIGHT
        elif hp_gap >= HP_DEFICIT_SPIKE:
            score += (hp_gap - HP_DEFICIT_SPIKE + 1) * HP_DEFICIT_SPIKE_WEIGHT

        # Field power (total attack + hp of followers)
        own_field_power = 0
        own_field_have_protector = False
        amulet_names_on_own_field = set()
        for f in state.fields[player]:
            if isinstance(f, cards.Follower):
                own_field_power += f.attack + f.hp
                # 守護 (.ability_protect) 者のHPの100%を追加ボーナスとして加算
                if f.ability_protect:
                    own_field_power += f.hp
                    own_field_have_protector = True
                # drain 者の攻撃力の100%を追加ボーナスとして加算
                if f.ability_drain:
                    own_field_power += f.attack
                # lethal 4 points, 1 cost
                if f.ability_lethal:
                    own_field_power += 4
            elif isinstance(f, cards.Amulet):
                if f.name not in amulet_names_on_own_field:
                    own_field_power += f.amulet_value_for_evaluate
                    amulet_names_on_own_field.add(f.name)
                else:
                    # If multiple copies of the same amulet are on the field, their value is less than linear.
                    own_field_power += f.amulet_value_for_evaluate * 0.5
        opp_field_power = 0
        opp_field_lethal_power = 0
        amulet_names_on_opp_field = set()
        for f in state.fields[opponent]:
            if isinstance(f, cards.Follower):
                opp_field_power += f.attack + f.hp
                if f.attack_ability == 1 and f.can_attack_this_turn:
                    opp_field_power += f.attack_ability * FIELD_POWER_OPP_ATTACK_ABILITY_WEIGHT
                elif f.attack_ability == 2 and f.can_attack_this_turn:
                    opp_field_power += f.attack_ability * FIELD_POWER_OPP_ATTACK_ABILITY_WEIGHT
                    opp_field_lethal_power += f.attack
                if f.ability_protect:
                    opp_field_power += f.hp
                if f.ability_drain:
                    opp_field_power += f.attack
                if f.ability_lethal:
                    opp_field_power += 4
            elif isinstance(f, cards.Amulet):
                if f.name not in amulet_names_on_opp_field:
                    opp_field_power += f.amulet_value_for_evaluate
                    amulet_names_on_opp_field.add(f.name)
                else:
                    opp_field_power += f.amulet_value_for_evaluate * 0.5
        if own_hp_value <= opp_field_lethal_power and not own_field_have_protector:
            return float('-inf')
        score += (own_field_power - opp_field_power) * FIELD_POWER_WEIGHT

        # Hand size
        score += (len(state.hands[player]) - len(state.hands[opponent])) * HAND_SIZE_WEIGHT

        # Low hand size
        if len(state.hands[player]) < LOW_HAND_SIZE_THRESHOLD:
            score -= (LOW_HAND_SIZE_THRESHOLD - len(state.hands[player])) * LOW_HAND_SIZE_WEIGHT

        # Hand power (for card has cost not equal to original cost, or hp/atk not equal to original)
        own_hand_power = 0
        for c in state.hands[player]:
            if c.cost != c.original_cost:
                own_hand_power += (c.original_cost - c.cost) * 4
            if isinstance(c, cards.Follower) and not isinstance(c, cards.お爺さんとお婆さん):
                if c.attack != c.original_attack:
                    own_hand_power += (c.attack - c.original_attack)
                if c.attack > c.original_attack:
                    if c.ability_super_rush:
                        own_hand_power += (c.attack - c.original_attack) # slightly more valuable
                    elif c.ability_rush:
                        own_hand_power += (c.attack - c.original_attack) * 0.5
                if c.hp != c.original_max_hp:
                    own_hand_power += (c.hp - c.original_max_hp)
        opp_hand_power = 0
        for c in state.hands[opponent]:
            if c.cost != c.original_cost:
                opp_hand_power += (c.original_cost - c.cost) * 4
            if isinstance(c, cards.Follower) and not isinstance(c, cards.お爺さんとお婆さん):
                if c.attack != c.original_attack:
                    opp_hand_power += (c.attack - c.original_attack)
                if c.attack > c.original_attack:
                    if c.ability_super_rush:
                        opp_hand_power += (c.attack - c.original_attack) # slightly more valuable
                    elif c.ability_rush:
                        opp_hand_power += (c.attack - c.original_attack) * 0.5
                if c.hp != c.original_max_hp:
                    opp_hand_power += (c.hp - c.original_max_hp)
        score += (own_hand_power - opp_hand_power) * HAND_POWER_WEIGHT

        # Deck size
        score += (len(state.decks[player]) - len(state.decks[opponent])) * DECK_SIZE_WEIGHT

        # graveyard - Star Phoenix can be summoned from graveyard
        if state.graveyard[player]:
            for c in state.graveyard[player]:
                if isinstance(c, cards.スターフェニックス):
                    score += 4.0  # 2/2

        return score