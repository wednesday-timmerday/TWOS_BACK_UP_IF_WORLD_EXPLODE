import pygame
import os


# def run(cutscene, dt, player, world, joystick, event):



#     def z_pressed():

#         return pygame.key.get_pressed()[pygame.K_z] or joystick.get_button(0) or pygame.key.get_pressed()[pygame.K_y]

#     if not hasattr(cutscene, "step"):

#         cutscene.step = 0



#     if joystick is None:

#         class DummyJoy:

#             def get_button(self, i): return False

#             def get_axis(self, i): return 0

#         joystick = DummyJoy()

#     if cutscene.step == 0:

#         if z_pressed():

#             cutscene.step = 1

#         return



#     if cutscene.step == 1:

#         player.curr_animation = "Idle"

#         player.curr_frame = 0

#         player.can_move = False

#         cutscene.text_engine.start_text(

#             "* The painting reminds you of a&game you used to play.&&^wait500* Despite its age,&it is still a fun game",

#             ""

#         )

#         cutscene.step = 2

#     elif cutscene.step == 2:

#         cutscene.text_engine.update(dt)



#         if cutscene.text_engine.finished and z_pressed():

#             player.can_move = True

#             cutscene.running = False



class Interactable:

    def __init__(self, player, world, loader):

        # self.text = [

        #     "[shadowrock]", #Who is talking?!

        #     "* The painting reminds you of a&game you used to play.",

        #     "({&&^wait500})",

        #     "[potato]",

        #     "* Despite its age,&it is still a fun game.",

        #     "{print}",

        #     "ENDOFCONVERSATION"



        # ]
        self.player = player

        self.loader = loader

        self.dialogue_id = "t_flowey_r1" #Name so we can look the text up in the BIG_TEXT.txt file
        

    def check_if_ut(self):
        if os.path.exists(os.path.join(os.path.expanduser("~"), "AppData", "Local", "UNDERTALE")) or os.path.exists(os.path.join(os.path.expanduser("~"), "AppData", "Local", "DELTARUNE")) or os.path.exists(os.path.join(os.path.expanduser("~"), "AppData", "Local", "DONTFORGET")):
            return "YES"
        else:
            self.player.can_move = True
            self.loader.running = False
            


