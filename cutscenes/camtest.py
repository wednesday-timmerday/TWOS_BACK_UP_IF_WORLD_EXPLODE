# cutscenes/pan_camera_to_2000.py
import pygame
import types

def run(cutscene, dt, player, world, joystick, event):
    """Pan camera to x=2000 without moving the player by monkey-patching world.update_camera."""
    def approach(current, target, max_delta):
        if current < target:
            return min(current + max_delta, target)
        else:
            return max(current - max_delta, target)

    # ---------- init once ----------
    if not hasattr(cutscene, "step"):
        cutscene.step = 0

    # create and store fake camera X
    if not hasattr(cutscene, "fake_camera_x"):
        cutscene.fake_camera_x = getattr(player, "world_x", 0)

    # store original update_camera once so we can restore later
    if not hasattr(cutscene, "_orig_update_camera"):
        cutscene._orig_update_camera = world.update_camera

        # create a patched update_camera that uses cutscene.fake_camera_x while override flag is True
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

    # ---------- cutscene parameters ----------
    target_x = 2000
    speed = 600.0  # px/s, tweak to taste
    hold_for = 0.8  # seconds to hold at target before ending

    if not hasattr(cutscene, "hold_timer"):
        cutscene.hold_timer = 0.0

    # ---------- Steps ----------
    # STEP 0: start override and pan
    if cutscene.step == 0:
        cutscene.override_camera = True  # enable the patched_update_camera behavior

        # move fake camera x toward the target
        cutscene.fake_camera_x = approach(cutscene.fake_camera_x, target_x, speed * dt)

        # if reached target, go to hold step
        if cutscene.fake_camera_x == target_x:
            cutscene.step = 1
            cutscene.hold_timer = 0.0

    # STEP 1: hold for a bit, then finish
    elif cutscene.step == 1:
        cutscene.hold_timer += dt
        if cutscene.hold_timer >= hold_for:
            cutscene.step = 2

    # STEP 2: clean up & restore
    elif cutscene.step == 2:
        # disable override so world.update_camera uses original behavior again
        cutscene.override_camera = False

        # restore original update_camera if stored
        try:
            if hasattr(cutscene, "_orig_update_camera") and cutscene._orig_update_camera:
                world.update_camera = cutscene._orig_update_camera
        except Exception:
            pass

        if hasattr(player, "_triggered_once") and hasattr(cutscene, "trigger_idx"):
            player._triggered_once.add(cutscene.trigger_idx)

        cutscene.running = False

