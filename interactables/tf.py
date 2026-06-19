import pygame



class Interactable:

    def __init__(self, player, world, loader):

        self.dialogue_id = "tf"
        self.player = player

    def fling_player_to_outer_space(self):
        self.player.world_x = -99999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999

