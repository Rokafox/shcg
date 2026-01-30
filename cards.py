class Card:
    def __init__(self, name, cost, card_type):
        self.name = name
        self.cost = cost
        self.type = card_type
        self.description = ""

    def tooltip_str(self):
        s = f"{self.name}\n"
        if self.description:
            s += f"{self.description}\n"
        return s

    def on_play_effect(self, player: int):
        pass

    def on_leave_field_effect(self, player: int):
        pass

    def start_of_turn_on_field_effect(self, player: int):
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
        self.attack_ability: int = 0  # 0: cannot attack, 1: can attack follower, 2: can attack player
        self.how_many_attacks_max_of_turn: int = 1  # Number of attacks per turn
        self.how_many_attacks_done_of_turn: int = 0  # Number of attacks done this turn
        self.can_attack_this_turn: bool = False
    
    def tooltip_str(self):
        s = f"{self.name}\n"
        s += f"Attack: {self.attack}  HP: {self.hp}/{self.max_hp}\n"
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
            
    def on_enhance_effect(self, player: int):
        self.on_enhance_effect_default()

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
# Classic
# ==============================

class ゴブリン(Follower):
    def __init__(self):
        super().__init__(name="ゴブリン", cost=1, attack=1, hp=1, can_enhance=True)
        self.description = "ゴブリンの世界にあるのはエモノだけ。欲しいものを持った獲物、奪い取って身に着けた得物。"
        self.description_e = "ゴブリンは純粋に、無垢に、エモノを追いかけ回す。彼らを見れば分かる通り、純粋も無垢も善の同義語ではない。"

class ファイター(Follower):
    def __init__(self):
        super().__init__(name="ファイター", cost=2, attack=2, hp=2, can_enhance=False)
        self.description = "争いだらけの世界の中で、頼れるのは自分だけ。この得た力だけは、決して裏切らない。"

class ゴリアテ(Follower):
    def __init__(self):
        super().__init__(name="ゴリアテ", cost=3, attack=3, hp=3, can_enhance=True)
        self.description = "見上げた時にはもう遅い。巨人はお前を見下ろすこともなく踏み潰す。"
        self.description_e = "思い出が染みついた家も、思い出を振り返る人も、巨人にとっては踏みしめるべき道に過ぎない。"