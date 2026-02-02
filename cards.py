import random
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from super_hard_card_game import SHCGGameState


class Card:
    def __init__(self, name, cost, card_type):
        self.name = name
        self.cost = cost
        self.type = card_type
        self.unique_id: int = random.randint(1, 1_000_000_000)
        self.description = ""
        self.effect_description = ""
        self.request_card_selection_on_play: str = "" # e.g., "field"
        # field: player field
        # field_opponent: opponent field
        # field_both: both fields
        self.request_card_selection_on_play_amount: int = 0
        self.request_card_target_on_play: str = ""

    def tooltip_str(self):
        s = f"{self.name}\n"
        if self.effect_description:
            s += f"{self.effect_description}\n"
        if self.description:
            s += f"{self.description}\n"
        return s

    def on_play_effect(self, player: int):
        pass

    def on_leave_field_effect(self, player: int):
        pass

    def start_of_turn_on_field_effect(self, player: int):
        pass

    def end_of_turn_on_field_effect(self, game_state: SHCGGameState, draw_ui, set_text, the_actual_textbox):
        pass




class Follower(Card):
    def __init__(self, name, cost, attack, hp, can_enhance):
        super().__init__(name, cost, 'follower')
        self.description_e = ""  # enhanced description
        self.attack = attack
        self.hp = hp
        self.max_hp = hp
        self.can_enhance: bool = can_enhance # use 1 foxtail to enhance
        self.is_enhanced: bool = False
        self.summoned_this_turn: bool = True
        self.enhanced_this_turn: bool = False
        self.request_card_selection_on_enhance: str = ""
        self.attack_ability: int = 0  # 0: cannot attack, 1: can attack follower, 2: can attack player
        self.how_many_attacks_max_of_turn: int = 1  # Number of attacks per turn
        self.how_many_attacks_done_of_turn: int = 0  # Number of attacks done this turn
        self.can_attack_this_turn: bool = False
        self.ability_protect: bool = False  # Opponent's followers cannot target leader while this follower is on field
    
    def tooltip_str(self):
        s = f"{self.name}\n"
        s += f"Attack: {self.attack}  HP: {self.hp}/{self.max_hp}\n"
        if self.ability_protect:
            s += "【守護】\n"
        if self.effect_description:
            s += f"{self.effect_description}\n"
        if self.is_enhanced and self.description_e:
            s += f"{self.description_e}\n"
        elif self.description:
            s += f"{self.description}\n"
        return s

    def advance_attack_ability(self):
        """
        increase the attack ability by 1, up to 2
        """
        if self.attack_ability < 2:
            self.attack_ability += 1

    def decrease_attack_ability(self):
        """
        decrease the attack ability by 1, down to 0
        """
        if self.attack_ability > 0:
            self.attack_ability -= 1
    
    def start_of_turn_on_field_effect(self, player):
        self.enhanced_this_turn = False
        self.how_many_attacks_done_of_turn = 0
        self.summoned_this_turn = False
        self.advance_attack_ability()
        self.can_attack_this_turn = True

    def after_attack_effect(self):
        self.how_many_attacks_done_of_turn += 1
        if self.how_many_attacks_done_of_turn >= self.how_many_attacks_max_of_turn:
            self.can_attack_this_turn = False

    def on_enhance_effect_default(self):
        if self.can_enhance and not self.enhanced_this_turn:
            self.attack += 2
            self.hp += 2
            self.max_hp += 2
            self.can_enhance = False
            self.enhanced_this_turn = True
            self.is_enhanced = True
            self.advance_attack_ability()
            if self.how_many_attacks_done_of_turn < self.how_many_attacks_max_of_turn:
                self.can_attack_this_turn = True
            
    def on_enhance_effect(self, game_state: SHCGGameState, draw_ui, set_text, the_actual_textbox,
                          selected_card_for_effect: Card | None):
        self.on_enhance_effect_default()

    def take_damage(self, damage_amount: int, game_state: SHCGGameState, draw_ui, set_text, the_actual_textbox,
                    attacker: Card | None):
        self.hp -= damage_amount
        # find out which player's field this follower is on
        for p in [1, 2]:
            if self in game_state.fields[p]:
                player = p
                break
        if self.hp <= 0:
            # Follower is destroyed
            game_state.fields[player].remove(self)
            if set_text:
                the_actual_textbox.append_html_text(f"{self} on field of player {player} was destroyed by {attacker}.\n")
        else:
            if set_text:
                the_actual_textbox.append_html_text(f"{self} took {damage_amount} damage from {attacker}.\n")
        if draw_ui:
            game_state.draw_field_ui(player)

    def __repr__(self):
        return f"{self.name} ({self.attack}/{self.hp})"


class Spell(Card):
    def __init__(self, name, cost):
        super().__init__(name, cost, 'spell')
    
    def __repr__(self):
        return f"{self.name}"


class Amulet(Card):
    def __init__(self, name, cost):
        super().__init__(name, cost, 'amulet')
    
    def __repr__(self):
        return f"{self.name}"


# ==============================
# Followers
# Each cost is evaluated as 4 points
# ==============================

class ゴブリン(Follower):
    def __init__(self):
        super().__init__(name="ゴブリン", cost=1, attack=2, hp=2, can_enhance=True)
        self.description = "ゴブリンの世界にあるのはエモノだけ。欲しいものを持った獲物、奪い取って身に着けた得物。"
        self.description_e = "ゴブリンは純粋に、無垢に、エモノを追いかけ回す。彼らを見れば分かる通り、純粋も無垢も善の同義語ではない。"

class ファイター(Follower):
    def __init__(self):
        super().__init__(name="ファイター", cost=2, attack=4, hp=4, can_enhance=False)
        self.description = "争いだらけの世界の中で、頼れるのは自分だけ。この得た力だけは、決して裏切らない。"

class ゴリアテ(Follower):
    def __init__(self):
        super().__init__(name="ゴリアテ", cost=3, attack=6, hp=6, can_enhance=True)
        self.description = "見上げた時にはもう遅い。巨人はお前を見下ろすこともなく踏み潰す。"
        self.description_e = "思い出が染みついた家も、思い出を振り返る人も、巨人にとっては踏みしめるべき道に過ぎない。"

class ガブリエル(Follower):
    def __init__(self):
        super().__init__(name="ガブリエル", cost=4, attack=4, hp=3, can_enhance=False)
        self.effect_description = "場に出す時、他のフォロワー1体を選ぶ。それは攻撃力+4/体力+3する。"
        self.request_card_selection_on_play = "field"
        self.request_card_selection_on_play_amount = 1

    def on_play_effect(self, player: int, target_follower: Follower | None = None):
        if target_follower is not None:
            target_follower.attack += 4
            target_follower.hp += 3
            target_follower.max_hp += 3


class ハンサ(Follower):
    def __init__(self):
        super().__init__(name="ハンサ", cost=1, attack=0, hp=2, can_enhance=False)
        self.description = "聖鳥は純朴な瞳を誘い、旺盛な食欲を誘う。「ボクはキミたちの心を映す鏡さ！」"
        self.effect_description = "場に出す時、これは攻撃力+Xする。Xは「自分のデッキの上1枚カードのコスト」である。"
        self.request_card_target_on_play = "deck_top"

    def on_play_effect(self, player: int, target_card: Card | None = None):
        if target_card is not None:
            self.attack += target_card.cost


class 唯我の絶傑マゼルベイン(Follower):
    def __init__(self):
        super().__init__(name="唯我の絶傑・マゼルベイン", cost=4, attack=5, hp=5, can_enhance=True)
        self.effect_description = "自分のエンドフェイズが来た、自分のフェルトこれしかないとき、相手の場のフォロワーすべてに3ダメージ。進化後なら5ダメージ。"

    def end_of_turn_on_field_effect(self, game_state: SHCGGameState, draw_ui, set_text, the_actual_textbox):
        if len(game_state.fields[game_state.current_player]) == 1 and game_state.fields[game_state.current_player][0].name == self.name:
            damage_amount = 5 if self.is_enhanced else 3
            for c in game_state.fields[game_state.opponent].copy():
                if isinstance(c, Follower):
                    c.take_damage(damage_amount, game_state, draw_ui, set_text, the_actual_textbox, attacker=self)


class 機構翼の少女ローザ(Follower):
    def __init__(self):
        super().__init__(name="機構翼の少女・ローザ", cost=2, attack=1, hp=3, can_enhance=True)
        self.description = "相応なんでしょう、私には、この鳥籠の世界が。飛べるだけで幸せなんです。だから、きっとこれでいい。"
        self.description_e = "壮観なんでしょう、本当の空から見下ろす景色は。桃源郷はここなんです。だけど、いつかはきっと――。"
        self.effect_description = "進化時1枚引く。"
        self.ability_protect = True

    def on_enhance_effect(self, game_state: SHCGGameState, draw_ui, set_text, the_actual_textbox,
                          selected_card_for_effect: Card | None):
        self.on_enhance_effect_default()
        if game_state.decks[game_state.current_player] and len(game_state.hands[game_state.current_player]) < 9:
            drawn_card = game_state.decks[game_state.current_player].pop()
            game_state.hands[game_state.current_player].append(drawn_card)
            if set_text:
                the_actual_textbox.append_html_text(f"Player {game_state.current_player} drew 1 card {drawn_card} due to 機構翼の少女・ローザ's effect. \n")
            if draw_ui:
                game_state.draw_hand_ui(game_state.current_player)
                game_state.draw_deck_ui(game_state.current_player)


class 飢餓の使徒(Follower):
    def __init__(self):
        super().__init__(name="飢餓の使徒", cost=2, attack=2, hp=2, can_enhance=True)
        self.description_e = "必死になって、追い立てられて、身を捩るほどに苦悩して。無垢なままでは終わってしまうわよ。"
        self.effect_description = "場に出す時、自分の場の他のフォロワー1体を選ぶ。それは突進を持つ。" \
        "進化時、場のフォロワー1体を選ぶ。それに3ダメージ。それは攻撃力+3する。これを選ぶ時、この効果は無効になる。"
        self.request_card_selection_on_enhance = "field_both"
        self.request_card_selection_on_play = "field"
        self.request_card_selection_on_play_amount = 1

    def on_play_effect(self, player: int, target_follower: Follower | None = None):
        if target_follower is not None:
            if target_follower.attack_ability < 1:
                target_follower.advance_attack_ability()
                if target_follower.how_many_attacks_done_of_turn < target_follower.how_many_attacks_max_of_turn:
                    target_follower.can_attack_this_turn = True

    def on_enhance_effect(self, game_state: SHCGGameState, draw_ui, set_text, the_actual_textbox,
                          selected_card_for_effect: Card | None):
        self.on_enhance_effect_default()
        target = selected_card_for_effect
        if target is not None and isinstance(target, Follower) and target != self:
            target.take_damage(3, game_state, draw_ui, set_text, the_actual_textbox, attacker=self)
            target.attack += 3
            if set_text:
                the_actual_textbox.append_html_text(f"{target} gained +3 attack.\n")



# ==============================
# Spells
# ==============================

class 天なる大河(Spell):
    def __init__(self):
        super().__init__(name="天なる大河", cost=1)
        self.description = "宝石を零したような光景を、憧憬するは人の常。神話となった者だけが、憧れ叶えて天へと至る。"
        self.effect_description = "手札の全てのカードをデッキの下に置く。同じ枚数+1枚のカードをデッキから引く。"

class ミヒライテ(Spell):
    def __init__(self):
        super().__init__(name="ミヒライテ", cost=1)
        self.effect_description = "自分の場のフォロワー1体を選ぶ。それは攻撃力+2/体力+1する。それが『唯我の絶傑・マゼルベイン』なら、代わりに攻撃力+4/体力+2する。" \
        "自分の場のフォロワーがないとき、相手のリーダーに1ダメージ。"
        self.request_card_selection_on_play = "field"
        self.request_card_selection_on_play_amount = 1

    def on_play_effect(self, player: int, target_follower: Follower | None = None):
        if target_follower is not None:
            if target_follower.name == "唯我の絶傑・マゼルベイン":
                target_follower.attack += 4
                target_follower.hp += 2
                target_follower.max_hp += 2
            else:
                target_follower.attack += 2
                target_follower.hp += 1
                target_follower.max_hp += 1

class フェアリーアサルト(Spell):
    def __init__(self):
        super().__init__(name="フェアリーアサルト", cost=2)
        self.effect_description = "場のフォロワー1体を選び、それに6ダメージ。" \
        "場にフォロワーがないとき、相手のリーダーに6ダメージ。"
        self.request_card_selection_on_play = "field_both"
        self.request_card_selection_on_play_amount = 1

    def on_play_effect(self, player: int, target_follower: Follower | None = None):
        pass