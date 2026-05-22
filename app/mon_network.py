#!/usr/bin/env python3

import logging
import time
import psutil
import pygame
from typing import Tuple

import mon_config
from mon_config import MAX_NET_HISTORY, g_net_last_update, g_net_send, g_net_recv, g_net_history, g_net_last_io
from mon_utils import get_local_ip, draw_card, draw_vertical_title, draw_rounded_rect, draw_text_centered_with_shadow, draw_text_with_shadow

logger = logging.getLogger('mon_network')


def update_net_info() -> Tuple[float, float, str, str]:

    # 更新网络信息（带缓存和速率计算）
    
    global g_net_last_update, g_net_send, g_net_recv, g_net_history, g_net_last_io
    
    current_time = time.time()
    
    # 使用配置的间隔更新网络信息
    from mon_config import NETWORK_UPDATE_INTERVAL
    if current_time - g_net_last_update >= NETWORK_UPDATE_INTERVAL:
        try:
            # 获取当前网络IO统计
            net_io = psutil.net_io_counters()
            
            # 初始化或更新网络速率
            if g_net_last_io is None:
                # 第一次调用，初始化数据
                g_net_send = 0.0
                g_net_recv = 0.0
            else:
                # 计算时间间隔（秒）
                time_diff = current_time - g_net_last_update
                
                # 计算字节差
                bytes_sent_diff = net_io.bytes_sent - g_net_last_io.bytes_sent
                bytes_recv_diff = net_io.bytes_recv - g_net_last_io.bytes_recv
                
                # 计算速率（字节/秒）
                bytes_sent_per_sec = bytes_sent_diff / time_diff
                bytes_recv_per_sec = bytes_recv_diff / time_diff
                
                # 转换为MB/s
                g_net_send = bytes_sent_per_sec / (1024 * 1024)
                g_net_recv = bytes_recv_per_sec / (1024 * 1024)
            
            # 添加历史数据
            g_net_history.append((g_net_send, g_net_recv))
            
            # 限制历史数据长度
            if len(g_net_history) > MAX_NET_HISTORY:
                g_net_history.popleft()
            
            # 更新最后IO统计和时间戳
            g_net_last_io = net_io
            g_net_last_update = current_time
            
        except Exception as e:
            logger.error(f"更新网络信息失败: {e}")
    
    # 格式化速率和单位
    send_val, send_unit = format_net_speed(g_net_send)
    recv_val, recv_unit = format_net_speed(g_net_recv)
    
    return send_val, recv_val, send_unit, recv_unit


def format_net_speed(speed_mb: float) -> Tuple[float, str]:

    # 格式化网络速度
    
    if speed_mb < 1.0:
        # 转换为KB/s
        speed_kb = speed_mb * 1024
        if speed_kb < 1.0:
            # 转换为B/s
            speed_b = speed_kb * 1024
            return round(speed_b, 1), "B/s"
        return round(speed_kb, 1), "KB/s"
    else:
        return round(speed_mb, 1), "MB/s"


def draw_network(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """绘制网络监控信息"""
    
    # 更新网络信息
    send_val, recv_val, send_unit, recv_unit = update_net_info()
    
    # 绘制卡片背景
    draw_card(surface, rect)
    
    # 绘制垂直标题
    draw_vertical_title(surface, rect, "网络")
    
    # 获取配置
    FONT_MEDIUM = mon_config.get_font_medium()
    FONT_SMALL = mon_config.get_font_small()
    COLORS = mon_config.COLORS
    BAR_RADIUS = mon_config.BAR_RADIUS
    LINE_WIDTH = mon_config.LINE_WIDTH
    
    # 折线图区域配置
    chart_x = rect.x + 30
    chart_y = rect.y + 15
    chart_w = rect.width - 50
    chart_h = rect.height - 56
        
    # 绘制折线图背景框
    draw_rounded_rect(surface, COLORS["bg_dark"], (chart_x, chart_y, chart_w, chart_h), BAR_RADIUS)
    draw_rounded_rect(surface, COLORS["bg_light"], (chart_x+1, chart_y+1, chart_w-2, chart_h-2), BAR_RADIUS-1)
    
    # 绘制局域网IP
    ip = get_local_ip()
    ip_rect = (chart_x, chart_y + 10, chart_w, 30)
    draw_text_centered_with_shadow(surface, FONT_MEDIUM, f"局域网IP: {ip}", COLORS["text_white"], ip_rect)
    
    # 绘制网络速度折线图
    if len(g_net_history) > 0:
        all_vals = [v for pair in g_net_history for v in pair]
        max_val = max(all_vals) if all_vals and max(all_vals) > 0 else 1.0
        points_send = []
        points_recv = []
        
        # 使用列表推导优化点计算
        x_coords = [chart_x + 5 + i * (chart_w - 10) / max(len(g_net_history)-1, 1) for i in range(len(g_net_history))]
        
        for i, (s, r) in enumerate(g_net_history):
            x = chart_x + 5 + i * (chart_w - 10) / max(len(g_net_history)-1, 1)
            y_s = chart_y + chart_h - 10 - int((s / max_val) * (chart_h - 50))
            y_r = chart_y + chart_h - 10 - int((r / max_val) * (chart_h - 50))
            
            points_send.append((x, y_s))
            points_recv.append((x, y_r))
        
        # 绘制折线
        if len(points_send) > 1:
            pygame.draw.lines(surface, COLORS["net_send"], False, points_send, LINE_WIDTH)
        if len(points_recv) > 1:
            pygame.draw.lines(surface, COLORS["net_recv"], False, points_recv, LINE_WIDTH)
        
        # 绘制端点圆点标记（按照原版screen_mon_old.py）
        if points_send:
            pygame.draw.circle(surface, COLORS["net_send"], (int(points_send[-1][0]), int(points_send[-1][1])), 3)
            pygame.draw.circle(surface, COLORS["net_recv"], (int(points_recv[-1][0]), int(points_recv[-1][1])), 3)
    
    # 绘制当前网速文字（按照原版screen_mon_old.py的布局和字体大小）
    text_y = rect.y + rect.height - 40
    send_text = f"上传: {send_val}{send_unit}"
    recv_text = f"下载: {recv_val}{recv_unit}"
    
    # 计算总宽度
    send_width = FONT_MEDIUM.size(send_text)[0]
    recv_width = FONT_MEDIUM.size(recv_text)[0]
    total_w = send_width + recv_width + 25
    start_x = rect.centerx - total_w // 2
    
    # 绘制上传速度
    draw_text_with_shadow(surface, FONT_MEDIUM, send_text, COLORS["net_send"], (start_x, text_y))
    
    # 绘制下载速度
    recv_x = start_x + send_width + 25
    draw_text_with_shadow(surface, FONT_MEDIUM, recv_text, COLORS["net_recv"], (recv_x, text_y))