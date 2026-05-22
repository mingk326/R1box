#!/usr/bin/env python3

import logging
import psutil
import pygame
from typing import List, Dict, Any

import mon_config
from mon_config import PROCESS_CPU_THRESHOLD, PROCESS_SORT_LIMIT
from mon_utils import draw_card, draw_vertical_title, draw_table_header, draw_table_row, cache_result

logger = logging.getLogger('mon_process')


def format_memory(size: int) -> str:
    """
    格式化内存大小，根据大小自动选择单位（KB/MB/GB）
    
    参数：
        size: 内存大小（字节）
    返回值：
        str: 格式化后的内存大小字符串
    """
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


@cache_result(mon_config.PROCESS_UPDATE_INTERVAL)
def get_top_processes() -> List[Dict[str, Any]]:
    """获取CPU使用率TOP5进程（带CPU阈值过滤和缓存）"""
    
    try:
        procs = []
        # 获取CPU核心数，用于归一化CPU使用率
        cpu_count = psutil.cpu_count()
        
        # 获取进程的内存使用量（字节）而不是百分比
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
            try:
                cpu_percent = proc.info['cpu_percent']
                memory_bytes = proc.info['memory_info'].rss  # 实际内存使用量（字节）
                
                # 将CPU使用率转换为基于总CPU容量的百分比（0-100%）
                normalized_cpu = (cpu_percent / (cpu_count * 100)) * 100
                
                if normalized_cpu >= PROCESS_CPU_THRESHOLD:  # 只处理CPU使用率>阈值的进程
                    # 创建新的进程信息字典
                    proc_info = {
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cpu_percent': normalized_cpu,
                        'memory_bytes': memory_bytes,
                        'memory_str': format_memory(memory_bytes)  # 格式化后的内存字符串
                    }
                    procs.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # 只排序前N个进程
        top_procs = sorted(procs, key=lambda x: x['cpu_percent'], reverse=True)[:PROCESS_SORT_LIMIT]
        
        return top_procs
    except Exception as e:
        logger.error(f"获取进程信息失败: {e}")
        return []


def draw_processes(surface, procs: List[Dict[str, Any]], rect) -> None:
    """绘制进程模块（TOP5进程列表）"""
    
    # 获取配置
    FONT_SMALL = mon_config.get_font_small()
    FONT_TINY = mon_config.get_font_tiny()
    COLORS = mon_config.COLORS
    
    draw_card(surface, rect)
    draw_vertical_title(surface, rect, "进程")
    
    # 绘制表头
    cols = [("PID", 55), ("名称", 100), ("CPU%", 55), ("内存", 65)]
    draw_table_header(surface, rect, cols, FONT_SMALL, header_y=rect.y + 15)
    
    # 绘制进程列表
    proc_y = rect.y + 45
    line_h = 32
    
    for i, proc in enumerate(procs[:5]):
        y = proc_y + i*line_h
        draw_table_row(surface, rect, proc, cols, FONT_TINY, y, start_x=40, line_height=line_h)
        
        # 只在非最后一行绘制分隔线
        if i < 4:
            pygame.draw.line(surface, COLORS["bg_light"], (40, y + line_h - 2), (rect.x + rect.width - 20, y + line_h - 2), 1)