import pygame
import types

def RandomAhhFunction(x: float) -> float:
    if x == 0:
        return 0
    elif x == 1:
        return 1
    elif x < 0.5:
        return (2 ** (20 * x - 10)) / 2
    else:
        return (2 - 2 ** (-20 * x + 10)) / 2
    
def find_phys_obj(world, name):
    name = name.lower()
    for engine in world.all_physic_objects:
        obj = engine.object
        if getattr(obj, "phys_type", "").lower() == name:
            return engine
    return None



def run(cutscene, dt, player, world, joystick, event):

    def approach(current, target, max_delta):
        if current < target:
            return min(current + max_delta, target)
        else:
            return max(current - max_delta, target)

    # ---------- init once ----------
    if not hasattr(cutscene, "step"):
        cutscene.step = "Start"

    if not hasattr(cutscene, "fake_camera_x"):
        cutscene.fake_camera_x = getattr(player, "world_x", 0)

    if not hasattr(cutscene, "_orig_update_camera"):
        cutscene._orig_update_camera = world.update_camera

        def patched_update_camera(player_x, player_y):
            # if cutscene requests override and the cutscene is running, use fake x
            if getattr(cutscene, "override_camera", False) and getattr(cutscene, "running", True):
                half_width = world.Screen_resolution[0] // 2
                # use fake_camera_x to compute cam_x (same logic as original)
                world.cam_x = max(0, min(world.max_cam_x, cutscene.fake_camera_x - half_width))
                world.Cam_locked = world.cam_x <= 0 or world.cam_x >= world.max_cam_x
                world.cam_y = 0
            else:
                # call original method
                return cutscene._orig_update_camera(player_x, player_y)

        # bind patched method to world instance (so self behaves like before)
        # but our patched_update_camera uses the 'world' closure directly, so just assign it
        world.update_camera = types.MethodType(lambda self, px, py: patched_update_camera(px, py), world)


    target_x = 1020
    speed = 600.0  # px/s, tweak to taste
    hold_for = 0.8  # seconds to hold at target before ending

    if not hasattr(cutscene, "hold_timer"):
        cutscene.hold_timer = 0.0

    # Get enemies
    mrtutor = next((e for e in world.enemies if e.__class__.__name__.lower() == "mrtutor"), None)

    hammer = next((e for e in world.enemies if e.__class__.__name__.lower() == "hammer"), None)

    #Find physic objects
    orb = find_phys_obj(world, "orb")



    # if not mrtutor or not hammer:
    #     return

    # Dummy joystick if none
    if joystick is None:
        class DummyJoy:
            def get_button(self, i): return False
            def get_axis(self, i): return 0
        joystick = DummyJoy()

    # Initialize step
    if not hasattr(cutscene, "step"):
        cutscene.step = "Start"
        print("yes")

    # Helper: X skip input
    def x_pressed():
        return cutscene.x_just_pressed or pygame.key.get_pressed()[pygame.K_x] or joystick.get_button(0)

    # Helper: Z next input
    def z_pressed():
        return cutscene.z_just_pressed or joystick.get_button(0)

    # -----------------------------
    if cutscene.step == "Start":
        player.can_move = False

        cutscene.override_camera = True
        cutscene.fake_camera_x = approach(cutscene.fake_camera_x, target_x, speed * dt)
        if cutscene.fake_camera_x == target_x:
            cutscene.step = "Dialouge_MonsterYap_1"

    elif cutscene.step == "Dialouge_MonsterYap_1":
        cutscene.text_engine.start_text(
            "Mr. Tutorion: * See that slime&over there?",
            "mrtutor"
        )
        cutscene.step = "Dialouge_MonsterYap_1_Typewait"

    elif cutscene.step == "Dialouge_MonsterYap_1_Typewait":
        cutscene.text_engine.update(dt)

        if x_pressed() and not cutscene.text_engine.finished:
            cutscene.text_engine.char_index = len(cutscene.text_engine.text)
            cutscene.text_engine.finished = True
        
        elif cutscene.text_engine.finished and z_pressed():
            cutscene.step = "Dialouge_MonsterYap_2"

    elif cutscene.step == "Dialouge_MonsterYap_2":
        cutscene.text_engine.start_text(
            "Mr. Tutorion: * Go ahead!^wait500&Try running into it!", #DONT TOUCH THAT DIAL
            "mrtutor" #Panic, in static, out manic
        )
        cutscene.step = "End" #just dont change the channel

    elif cutscene.step == "End":
        cutscene.text_engine.update(dt)

        if x_pressed() and not cutscene.text_engine.finished:
            cutscene.text_engine.char_index = len(cutscene.text_engine.text)
            cutscene.text_engine.finished = True
        
        elif cutscene.text_engine.finished and z_pressed():
            cutscene.running = False
            player.can_move = True
            cutscene.override_camera = False
            if hasattr(player, "_triggered_once") and hasattr(cutscene, "trigger_idx"):
                player._triggered_once.add(cutscene.trigger_idx)