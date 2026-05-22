#!/usr/bin/env python3

import psutil
import logging
import pygame
from typing import Dict, Optional, Any

import mon_config
from mon_config import CPU_TEMP_LOW, CPU_TEMP_MID, CPU_TEMP_CACHE_TIME
from mon_utils import cache_result

logger = logging.getLogger('mon_cpu')


@cache_result(CPU_TEMP_CACHE_TIME)
def get_cpu_temp() -> Optional[float]:
    """
    获取CPU温度（带缓存）
    
    Returns:
        float: CPU温度（摄氏度），如果无法获取则返回None
    """
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            for sensor in ["coretemp", "cpu_thermal", "k10temp"]:
                if sensor in temps and temps[sensor]:
                    valid_temps = [t.current for t in temps[sensor] if 0 < t.current < 150]
                    if valid_temps:
                        return round(sum(valid_temps)/len(valid_temps), 1)
        
        # 嵌入式设备备用读取方式
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read().strip()) / 1000
            if 0 < temp < 150:
                return round(temp, 1)
    except Exception as e:
        logger.debug(f"获取CPU温度失败: {e}")
    
    return None


@cache_result(CPU_TEMP_CACHE_TIME)
def get_cpu_info() -> Dict[str, Any]:
    """
    获取CPU使用率信息（带缓存）
    
    Returns:
        Dict: 包含CPU总使用率、各核心使用率和温度的字典
    """
    try:
        # 获取CPU使用率（立即返回）
        cpu_percent = psutil.cpu_percent()
        
        # 获取各核心使用率（立即返回）
        cpu_percent_per_core = psutil.cpu_percent(percpu=True)
        
        # 获取CPU温度
        cpu_temp = get_cpu_temp()
        
        return {
            "total": round(cpu_percent, 1),
            "cores": [round(pct, 1) for pct in cpu_percent_per_core],
            "temp": cpu_temp
        }
    except Exception as e:
        logger.error(f"获取CPU信息失败: {e}")
        return {"total": 0.0, "cores": [], "temp": None}


def draw_cpu(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """绘制CPU监控信息"""
    # 获取CPU信息
    cpu_info = get_cpu_info()
    cpu_percent = cpu_info["total"]
    cpu_percents = cpu_info["cores"]
    cpu_temp = cpu_info["temp"]
    
    # 绘制卡片背景
    from mon_utils import draw_card, draw_vertical_title, draw_ring, draw_rounded_rect
    draw_card(surface, rect)
    
    # 绘制垂直标题（按照原版screen_mon_old.py显示"核心"）
    draw_vertical_title(surface, rect, "核心")
    
    # 获取字体和颜色配置
    FONT_LARGE = mon_config.get_font_large()
    FONT_SMALL = mon_config.get_font_small()
    FONT_TINY = mon_config.FONT_TINY
    COLORS = mon_config.COLORS
    BAR_RADIUS = mon_config.BAR_RADIUS
    
    center = (rect.x + 80, rect.centery)
    ring_radius = 65
    
    # 根据温度选择颜色
    if cpu_temp is None or cpu_temp < CPU_TEMP_LOW:
        cpu_color = COLORS["cpu_normal"]
    elif cpu_temp < CPU_TEMP_MID:
        cpu_color = COLORS["cpu_warn"]
    else:
        cpu_color = COLORS["cpu_high"]
    
    # 绘制环形图
    draw_ring(surface, center, ring_radius, cpu_percent, cpu_color)
    
    # 绘制CPU温度文字（使用大字体，位于环形图中心）
    temp_text = f"{cpu_temp or 'N/A'}°C"
    temp_surf = FONT_LARGE.render(temp_text, True, COLORS["text_white"])
    surface.blit(temp_surf, (center[0]-temp_surf.get_width()//2, center[1]-temp_surf.get_height()//2-5))
    
    # 绘制CPU使用率文字（使用小字体，位于环形图中心偏下）
    percent_surf = FONT_SMALL.render(f"{cpu_percent}%", True, COLORS["text_gray"])
    surface.blit(percent_surf, (center[0]-percent_surf.get_width()//2, center[1]+15))
    
    # 绘制核心使用率
    core_x = rect.x + 150
    core_h = 22
    core_gap = 8
    total_core_h = 4 * core_h + 3 * core_gap
    core_y = rect.centery - total_core_h // 2
    core_w = rect.width - core_x - 15
    
    for i, pct in enumerate(cpu_percents[:4]):
        y = core_y + i*(core_h + core_gap)
        draw_rounded_rect(surface, COLORS["bg_dark"], (core_x, y, core_w, core_h), BAR_RADIUS//2)
        draw_rounded_rect(surface, COLORS["bg_light"], (core_x+1, y+1, core_w-2, core_h-2), (BAR_RADIUS//2)-1)
        
        fill_w = int(core_w * (pct/100))
        if fill_w > 0:
            draw_rounded_rect(surface, cpu_color, (core_x+1, y+1, fill_w, core_h-2), (BAR_RADIUS//2)-1)
        
        core_surf = FONT_TINY.render(f"Core{i+1}: {pct}%", True, COLORS["text_white"])
        surface.blit(core_surf, (core_x + core_w//2 - core_surf.get_width()//2, y + core_h//2 - core_surf.get_height()//2))