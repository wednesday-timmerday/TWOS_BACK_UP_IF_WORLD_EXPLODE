 #! Gekke oude code

import pygame
from sprites.blobtigoo.blobtigoo import Blobtigoo
import random

class Enemy_in_world():
    def __init__(self, current_level):
        self.current_level = current_level
        self.enemys = {
            "1": [Blobtigoo()]
        }

    def update_enemy(self, worldloader):
        self.current_level = worldloader.current_level
        #for every enemy in current level
        for enemy in self.enemys[self.current_level]:
            pass

