import os

class SaveOBJ:
    def __init__(self) -> None:
        self.pathname = os.path.join(os.path.expanduser("~"), "TWOSFILES", "0.save")
        
    def save_state(self, player, world):
        self.world = world
        self.player = player
        data = {
            'player_x': self.player.world_x,
            'player_y': self.player.world_y,
            'currlevel': self.world.current_level,
            'xp': 0, #Placeholder
            'money': self.player.money,
            'atk': self.player.atk,
            'def': self.player.defense,
            'killed': 0, #Placeholder
            'items': self.player.items,
            'triggered_idx': self.player._triggered_once,
            # 'player_moveable': self.player.can_move,
            'playerlightradius': self.world._player_light_radius,
            'worldcamx': self.world.cam_x,
            'worldcamy': self.world.cam_y
        }

        with open(self.pathname, "w") as file:
            file.write(str(data))