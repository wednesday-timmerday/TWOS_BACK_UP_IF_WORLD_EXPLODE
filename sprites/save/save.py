import os

class SaveOBJ:
    def __init__(self) -> None:
        self.pathname = os.path.join(os.path.expanduser("~"), "TWOSFILES", "0.save")
        self.count = 0
        
    def save_state(self, player, world):
        self.count+= 1
        self.world = world
        self.player = player
        self.get_enemie_pos_from_world()
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
            'worldcamy': self.world.cam_y,
            'enemy_data': self.unpacked_sprites
        }

        print(self.count)

        with open(self.pathname, "w") as file:
            file.write(str(data))


    def get_enemie_pos_from_world(self):
        # Fetch current x,y vals
        self.unpacked_sprites = []
        for i, obj in enumerate(self.world.enemies):
            print(obj)
            data = {
                "worldx": obj.world_x,
                "worldy": obj.world_y,
                "id": obj.id,
                "type": obj.type
            }
            self.unpacked_sprites.append(data)
            print(self.unpacked_sprites)
            