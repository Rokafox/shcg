class Card:
    def __init__(self, name, cost, card_type):
        self.name = name
        self.cost = cost
        self.type = card_type


class Follower(Card):
    def __init__(self, name, cost, attack, hp, can_enhance):
        super().__init__(name, cost, 'follower')
        self.attack = attack
        self.hp = hp
        self.max_hp = hp
        self.can_enhance: bool = can_enhance # use 1 foxtail to enhance
        self.is_enhanced: bool = False
        self.summoned_this_turn: bool = True
        self.enhanced_this_turn: bool = False
        self.can_attack_status: int = 0  # 0: cannot attack, 1: can attack follower, 2: can attack player
        self.how_many_attacks_max: int = 1  # Number of attacks per turn
        self.how_many_attacks_done: int = 0  # Number of attacks done this turn 
    
    def update_can_attack_status(self):
        self.how_many_attacks_done += 1
        if self.how_many_attacks_done >= self.how_many_attacks_max:
            self.can_attack_status = 0  # Cannot attack anymore this turn

    def reset_attack_status(self):
        self.how_many_attacks_done = 0
        self.can_attack_status = 0
        if not self.summoned_this_turn:
            self.can_attack_status = 2  # Can attack player

    def enhance(self):
        if self.can_enhance and not self.enhanced_this_turn:
            self.attack += 2
            self.hp += 2
            self.max_hp += 2
            self.can_enhance = False
            self.enhanced_this_turn = True
            self.is_enhanced = True
            if self.how_many_attacks_done < self.how_many_attacks_max:
                self.can_attack_status = 1

    def __repr__(self):
        return f"{self.name} ({self.attack}/{self.hp})"


class Spell(Card):
    def __init__(self, name, cost):
        super().__init__(name, cost, 'spell')
    
    def __repr__(self):
        return f"{self.name} (スペル {self.cost}コスト)"


class Amulet(Card):
    def __init__(self, name, cost):
        super().__init__(name, cost, 'amulet')
    
    def __repr__(self):
        return f"{self.name} (アミュレット {self.cost}コスト)"

