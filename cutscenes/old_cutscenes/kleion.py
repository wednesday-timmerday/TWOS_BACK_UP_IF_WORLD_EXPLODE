import pygame
import importlib
import sys

class CutsceneLoader():
    def __init__(self):
        self.module_name = None

    def load(self, cutscene_id):
        self.module_name = f"cutscenes.{cutscene_id}"
        cutscene_module = importlib.import_module(self.module_name)
        self.active_cutscene = cutscene_module.cutscene()

    def update(self, dt, player):
        self.active_cutscene.update(dt)
        if self.active_cutscene.cutscene_done:
            sys.modules[self.module_name]

        self.active_cutscene = None
        self.module_name = None
