#!/usr/bin/env python3

import logging
import pygame
import math
import socket
import time
from functools import wraps
from typing import Tuple, Dict, Any

logger = logging.getLogger('mon_utils')

from mon_config import (
    surface_cache, card_templates, SURFACE_CACHE_MAX,
    COLORS, SHADOW_ALPHA, CARD_ALPHA, CARD_RADIUS
)

# ==================== 性能优化：缓存管理 ====================

def get_cached_surface(key: str, size: Tuple[int, int], alpha: bool = True) -> pygame.Surface:
    """获取缓存的Surface对象，避免重复创建"""
    global surface_cache
    
    if key in surface_cache:
        surface = surface_cache[key]
        if surface.get_size() == size and (surface.get_flags() & pygame.SRCALPHA) == (alpha and pygame.SRCALPHA):
            return surface
    
    # 创建新的Surface并缓存
    surface = pygame.Surface(size, pygame.SRCALPHA if alpha else 0)
    surface_cache[key] = surface
    
    # 限制缓存大小
    if len(surface_cache) > SURFACE_CACHE_MAX:
        # 移除最旧的缓存项
        oldest_key = next(iter(surface_cache))
        del surface_cache[oldest_key]
    
    return surface


def clear_surface_cache():
    """清理Surface缓存"""
    global surface_cache
    surface_cache.clear()


def create_card_template(width: int, height: int) -> pygame.Surface:
    """创建卡片模板（带阴影）并缓存"""
    cache_key = f"card_{width}x{height}"
    
    if cache_key in card_templates:
        return card_templates[cache_key].copy()
    
    # 创建卡片模板
    card_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    
    # 绘制阴影层
    shadow_rect = pygame.Rect(0, 0, width, height)
    draw_rounded_rect(card_surf, (*COLORS["card_shadow"], SHADOW_ALPHA), shadow_rect, CARD_RADIUS+3)
    
    # 绘制卡片主体
    card_rect = pygame.Rect(3, 3, width-6, height-6)
    draw_rounded_rect(card_surf, (*COLORS["card_bg"], CARD_ALPHA), card_rect, CARD_RADIUS)
    
    # 缓存模板
    card_templates[cache_key] = card_surf
    return card_surf.copy()


# ==================== 绘图工具函数 ====================

def draw_rounded_rect(surface: pygame.Surface, color: Tuple[int, ...], rect: pygame.Rect, radius: int = 0, width: int = 0) -> None:
    """
    绘制圆角矩形
    
    功能：在指定Surface上绘制圆角矩形
    参数：
        surface: 目标Surface
        color: 颜色 (RGB或RGBA)
        rect: 矩形区域
        radius: 圆角半径
        width: 边框宽度（0表示填充）
    """
    if len(color) == 3:
        color = (*color, 255)  # 添加Alpha通道
    
    # 绘制圆角矩形
    pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)


def draw_ring(surface: pygame.Surface, center: Tuple[int, int], radius: int, 
              percent: float, color: Tuple[int, ...]) -> None:
    """
    绘制环形进度条
    
    功能：在指定位置绘制环形进度条
    参数：
        surface: 目标Surface
        center: 圆心坐标 (x, y)
        radius: 半径
        percent: 进度百分比 (0-100)
        color: 颜色
    """
    from mon_config import RING_WIDTH, RING_START_ANGLE, COLORS
    
    inner_radius = radius - RING_WIDTH
    
    # 绘制环形图背景层
    pygame.draw.circle(surface, COLORS["bg_dark"], center, radius)
    pygame.draw.circle(surface, COLORS["bg_light"], center, inner_radius)
    
    # 绘制百分比填充层
    if percent > 0 and percent <= 100:
        start_angle = RING_START_ANGLE
        end_angle = start_angle - math.radians(percent * 3.6)
        
        # 100%填充时绘制完整圆环
        if percent == 100:
            for r in range(inner_radius, radius):
                alpha_ratio = (r - inner_radius) / RING_WIDTH
                r_val = min(int(color[0] * (0.7 + alpha_ratio * 0.3)), 255)
                g_val = min(int(color[1] * (0.7 + alpha_ratio * 0.3)), 255)
                b_val = min(int(color[2] * (0.7 + alpha_ratio * 0.3)), 255)
                ring_color = (r_val, g_val, b_val)
                pygame.draw.circle(surface, ring_color, center, r, 1)
        else:
            # 渐变填充环形段
            for r in range(inner_radius, radius):
                alpha_ratio = (r - inner_radius) / RING_WIDTH
                r_val = min(int(color[0] * (0.7 + alpha_ratio * 0.3)), 255)
                g_val = min(int(color[1] * (0.7 + alpha_ratio * 0.3)), 255)
                b_val = min(int(color[2] * (0.7 + alpha_ratio * 0.3)), 255)
                ring_color = (r_val, g_val, b_val)
                pygame.draw.arc(surface, ring_color, 
                              (center[0]-r, center[1]-r, r*2, r*2), 
                              end_angle, start_angle, 1)
    
    # 绘制环形图边框
    pygame.draw.circle(surface, COLORS["border"], center, radius, 1)


def draw_card(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """绘制卡片（带阴影）"""
    card_template = create_card_template(rect.width, rect.height)
    surface.blit(card_template, (rect.x, rect.y))


def draw_vertical_title(surface: pygame.Surface, rect: pygame.Rect, title: str) -> None:
    """绘制垂直标题"""
    from mon_config import get_font_title, COLORS
    
    start_x = rect.x + 18
    start_y = rect.y + 12
    font = get_font_title()
    for i, char in enumerate(title):
        char_surf = font.render(char, True, COLORS["text_white"])
        char_x = start_x - char_surf.get_width()//2
        surface.blit(char_surf, (char_x, start_y + i * 25))


def draw_text_with_shadow(surface: pygame.Surface, font: pygame.font.Font, text: str, 
                           color: Tuple[int, int, int], pos: Tuple[int, int], 
                           shadow_color: Tuple[int, int, int] = (0, 0, 0), 
                           shadow_offset: Tuple[int, int] = (1, 1)) -> int:
    """
    绘制带阴影的文字，提高可读性
    
    Args:
        surface: 目标Surface
        font: 字体对象
        text: 要绘制的文字
        color: 文字颜色
        pos: 文字位置 (x, y)
        shadow_color: 阴影颜色，默认为黑色
        shadow_offset: 阴影偏移量，默认为(1, 1)
    
    Returns:
        文字宽度
    """
    # 绘制阴影
    shadow_surf = font.render(text, True, shadow_color)
    surface.blit(shadow_surf, (pos[0] + shadow_offset[0], pos[1] + shadow_offset[1]))
    
    # 绘制前景文字
    text_surf = font.render(text, True, color)
    surface.blit(text_surf, pos)
    
    return text_surf.get_width()


def draw_text_centered_with_shadow(surface: pygame.Surface, font: pygame.font.Font, 
                                  text: str, color: Tuple[int, int, int], 
                                  rect: Tuple[int, int, int, int]) -> None:
    """绘制带阴影的居中文字"""
    text_surf = font.render(text, True, color)
    x = rect[0] + (rect[2] - text_surf.get_width()) // 2
    y = rect[1] + (rect[3] - text_surf.get_height()) // 2
    surface.blit(text_surf, (x, y))


def draw_table_header(surface: pygame.Surface, rect: pygame.Rect, 
                     columns: Tuple[Tuple[str, int], ...], font: pygame.font.Font, 
                     header_y: int) -> None:
    """绘制表格表头"""
    from mon_config import COLORS
    
    x = rect.x + 40
    for col_name, col_width in columns:
        col_surf = font.render(col_name, True, COLORS["text_white"])
        surface.blit(col_surf, (x + col_width//2 - col_surf.get_width()//2, header_y))
        x += col_width


def draw_table_row(surface: pygame.Surface, rect: pygame.Rect, proc: Dict[str, Any], 
                  columns: Tuple[Tuple[str, int], ...], font: pygame.font.Font, 
                  y: int, start_x: int = 40, line_height: int = 32) -> None:
    """绘制表格行（按照原版screen_mon_old.py的居中对齐方式）"""
    from mon_config import COLORS
    
    x = rect.x + start_x
    
    # PID列（居中对齐）
    pid_rect = (x, y + 2, columns[0][1], 20)
    draw_text_centered_with_shadow(surface, font, str(proc.get('pid', 'N/A')), COLORS["text_white"], pid_rect)
    x += columns[0][1]
    
    # 进程名列（截断过长的名称，居中对齐）
    name = proc.get('name', 'N/A')
    if len(name) > 9:
        name = name[:9]
    name_rect = (x, y + 2, columns[1][1], 20)
    draw_text_centered_with_shadow(surface, font, name, COLORS["text_white"], name_rect)
    x += columns[1][1]
    
    # CPU使用率列（居中对齐）
    cpu_rect = (x, y + 2, columns[2][1], 20)
    draw_text_centered_with_shadow(surface, font, f"{proc.get('cpu_percent', 0):.1f}", COLORS["text_white"], cpu_rect)
    x += columns[2][1]
    
    # 内存列（居中对齐）- 支持显示实际内存大小或百分比
    mem_rect = (x, y + 2, columns[3][1], 20)
    if 'memory_str' in proc:
        # 显示格式化后的内存大小（如 512.0 MB）
        draw_text_centered_with_shadow(surface, font, proc.get('memory_str', 'N/A'), COLORS["text_white"], mem_rect)
    else:
        # 显示内存百分比（兼容旧格式）
        draw_text_centered_with_shadow(surface, font, f"{proc.get('memory_percent', 0):.1f}", COLORS["text_white"], mem_rect)
    
    # 绘制分隔线（按照原版screen_mon_old.py）
    pygame.draw.line(surface, COLORS["bg_light"], (rect.x + start_x, y + line_height - 2), (rect.x + rect.width - 20, y + line_height - 2), 1)


# ==================== 性能优化：缓存管理 ====================

def cache_result(cache_time: float):
    """
    通用缓存装饰器
    
    Args:
        cache_time: 缓存时间（秒）
    """
    def decorator(func):
        func._cache = None
        func._cache_time = 0.0
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_time = time.time()
            if func._cache is not None and current_time - func._cache_time < cache_time:
                return func._cache
            
            result = func(*args, **kwargs)
            func._cache = result
            func._cache_time = current_time
            return result
        return wrapper
    return decorator

# ==================== 其他工具函数 ====================

def get_local_ip() -> str:
    """获取本地IP地址"""
    try:
        # 创建一个临时socket连接来获取本地IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def run_command_with_timeout(cmd: list, timeout: int = 3, use_sudo: bool = False):
    """
    通用的子进程运行函数，支持超时和sudo
    
    参数：
        cmd: 命令列表
        timeout: 超时时间（秒）
        use_sudo: 是否使用sudo
    
    返回值：
        subprocess.CompletedProcess对象或None
    """
    import subprocess
    
    try:
        if use_sudo:
            cmd = ["sudo"] + cmd
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        return None