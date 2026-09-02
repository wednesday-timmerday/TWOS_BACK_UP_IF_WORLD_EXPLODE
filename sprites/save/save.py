class SaveOBJ:
    def __init__(self) -> None:
        pass
    def save_state(self, player, world):
        self.world = world
        self.player = player
        data = {
            'player_x': self.player.world_x,
            'player_y': self.player.world_y
        }

        print(data)