#!/usr/bin/env python3

import logging
import psutil
import pygame
from typing import Dict

import mon_config
from mon_config import COLORS
from mon_utils import draw_card, draw_vertical_title, draw_rounded_rect, cache_result

logger = logging.getLogger('mon_memory')


@cache_result(mon_config.MEMORY_CACHE_TIME)
def get_memory_info() -> Dict[str, any]:
    """
    获取内存使用信息（带缓存）
    """
    try:
        # 获取内存信息
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        # 计算使用率
        memory_percent = round(memory.percent, 1)
        swap_percent = round(swap.percent, 1) if swap.total > 0 else 0.0
        
        # 格式化内存大小（GB）
        memory_used_gb = round(memory.used / (1024**3), 1)
        memory_total_gb = round(memory.total / (1024**3), 1)
        swap_used_gb = round(swap.used / (1024**3), 1) if swap.total > 0 else 0.0
        swap_total_gb = round(swap.total / (1024**3), 1) if swap.total > 0 else 0.0
        
        return {
            "memory_percent": memory_percent,
            "memory_used_gb": memory_used_gb,
            "memory_total_gb": memory_total_gb,
            "swap_percent": swap_percent,
            "swap_used_gb": swap_used_gb,
            "swap_total_gb": swap_total_gb
        }
    except Exception as e:
        logger.error(f"获取内存信息失败: {e}")
        return {key: 0.0 for key in ["memory_percent", "memory_used_gb", "memory_total_gb", 
                                    "swap_percent", "swap_used_gb", "swap_total_gb"]}


def draw_memory(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """绘制内存监控信息（按照原版screen_mon_old.py配置）"""
    
    # 获取内存信息（使用缓存）
    memory_info = get_memory_info()
    
    # 绘制卡片背景
    draw_card(surface, rect)
    
    # 绘制垂直标题
    draw_vertical_title(surface, rect, "内存")
    
    # 获取配置
    FONT_MEDIUM = mon_config.get_font_medium()
    FONT_SMALL = mon_config.get_font_small()
    BAR_RADIUS = mon_config.BAR_RADIUS
    
    # 绘制内存进度条（按照原版位置）
    bar_x = rect.x + 45
    bar_y = rect.centery - 18
    bar_w = rect.width - 100
    bar_h = 40
    
    draw_rounded_rect(surface, COLORS["bg_dark"], (bar_x, bar_y, bar_w, bar_h), BAR_RADIUS)
    draw_rounded_rect(surface, COLORS["bg_light"], (bar_x+2, bar_y+2, bar_w-4, bar_h-4), BAR_RADIUS-2)
    
    used_w = int((bar_w - 4) * (memory_info['memory_percent']/100))
    if used_w > 0:
        draw_rounded_rect(surface, COLORS["mem_used"], (bar_x+2, bar_y+2, used_w, bar_h-4), BAR_RADIUS-2)
    
    draw_rounded_rect(surface, COLORS["border"], (bar_x, bar_y, bar_w, bar_h), BAR_RADIUS, 1)
    
    # 绘制内存总量文字（按照原版格式）
    total_gb = memory_info['memory_total_gb']
    total_surf = FONT_MEDIUM.render(f"{total_gb} GB", True, COLORS["text_white"])
    surface.blit(total_surf, (bar_x + bar_w//2 - total_surf.get_width()//2, bar_y + bar_h//2 - total_surf.get_height()//2))
    
    # 绘制使用率文字（按照原版位置和格式）
    used_surf = FONT_SMALL.render(f"已用 {memory_info['memory_percent']:.1f}%", True, COLORS["text_gray"])
    free_surf = FONT_SMALL.render(f"空闲 {100 - memory_info['memory_percent']:.1f}%", True, COLORS["text_gray"])
    
    surface.blit(used_surf, (bar_x + 15, bar_y + bar_h + 3))
    surface.blit(free_surf, (bar_x + bar_w - free_surf.get_width() - 15, bar_y + bar_h + 3))