class dog:
    def __init__(self, loader, player, world):
        self.player = player
        self.healamount = 15 #hp
        self.item_name = "dog"
        
        
    def use(self):
        self.player.hp += self.healamount
        if self.player.hp >= self.player.max_hp:
            self.player.hp = self.player.max_hp
      
        for i, item in enumerate(self.player.items):
            if item["short_name"] == self.item_name:
                self.player.items.pop(i)