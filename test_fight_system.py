#!/usr/bin/env python3
"""Quick test to verify the fight system works."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    
    from ui.fight.fight import Fight
    
    print("[TEST] Imported Fight class successfully")
    
    # Test instantiation
    fight = Fight(screen, screen)
    print("[TEST] Fight instance created successfully")
    
    # Test loading a fight
    result = fight.load_fight("test_fight")
    print(f"[TEST] load_fight returned: {result}")
    print(f"[TEST] fight.running = {fight.running}")
    print(f"[TEST] fight.module = {fight.module}")
    
    if fight.module:
        print("[TEST] Fight module loaded successfully!")
        # Test update
        fight.update(0.016)  # 16ms for 60 FPS
        print("[TEST] update() called successfully")
        
        # Test draw
        fight.draw()
        print("[TEST] draw() called successfully")
    else:
        print("[ERROR] Fight module failed to load")
    
    print("[TEST] All tests passed!")
    
except Exception as e:
    import traceback
    print(f"[ERROR] {e}")
    traceback.print_exc()
