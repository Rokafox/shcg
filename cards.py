class Card:
    def __init__(self, name, cost, card_type, image):
        self.name = name
        self.cost = cost
        self.type = card_type
        self.image = image


class Follower(Card):
    def __init__(self, name, cost, attack, hp, image):
        super().__init__(name, cost, 'follower', image)
        self.attack = attack
        self.hp = hp
        self.max_hp = hp
    
    def __repr__(self):
        return f"{self.name} ({self.cost}コスト {self.attack}/{self.hp})"


class Spell(Card):
    def __init__(self, name, cost, image):
        super().__init__(name, cost, 'spell', image)
    
    def __repr__(self):
        return f"{self.name} (スペル {self.cost}コスト)"


class Amulet(Card):
    def __init__(self, name, cost, image):
        super().__init__(name, cost, 'amulet', image)
    
    def __repr__(self):
        return f"{self.name} (アミュレット {self.cost}コスト)"


goblin = Follower(
    name="goblin",
    cost=1,
    attack=1,
    hp=1,
    image="goblin"
)

fighter = Follower(
    name="fighter",
    cost=2,
    attack=2,
    hp=2,
    image="fighter"
)
