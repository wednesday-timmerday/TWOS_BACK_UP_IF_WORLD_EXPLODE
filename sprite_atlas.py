
import pygame


def build_atlas(surfaces, padding=1):
    # pack surfaces in a single row horizontally
    widths = [s.get_width() for s in surfaces]
    heights = [s.get_height() for s in surfaces]
    total_w = sum(widths) + padding * (len(surfaces) - 1)
    max_h = max(heights) if heights else 0
    atlas = pygame.Surface((total_w, max_h), pygame.SRCALPHA).convert_alpha()
    rects = []
    x = 0
    for s in surfaces:
        rect = pygame.Rect(x, 0, s.get_width(), s.get_height())
        atlas.blit(s, rect)
        rects.append(rect)
        x += s.get_width() + padding
    return atlas, rects


def blit_from_atlas(dst_surface, atlas, src_rect, dest_pos):
    dst_surface.blit(atlas, dest_pos, src_rect)

