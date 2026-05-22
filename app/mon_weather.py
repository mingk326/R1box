#!/usr/bin/env python3

import logging
import time
import os
import psutil
import pygame
import requests
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from mon_config import (
    COLORS,
    WEATHER_UPDATE_INTERVAL,
    SENIVERSE_API_KEY,
    ICON_SIZE_1X,
    ICON_SIZE_2X,
    SSD_DEVICES_COUNT,
    HDD_DEVICES_COUNT,
    DISK_LAYOUT_COLS,
    DISK_POSITIONS,
    WEEKDAY_MAP,
    DEFAULT_CURRENT_WEATHER,
    DEFAULT_WEATHER_INFO,
    DASHBOARD_TIME_HEIGHT,
    DASHBOARD_CURRENT_WEATHER_HEIGHT,
    DASHBOARD_FORECAST_HEIGHT,
    DASHBOARD_IP_HEIGHT,
    DASHBOARD_DISK_IO_HEIGHT,
    WEATHER_DISK_IO_UPDATE_INTERVAL,
    get_font_time,
    get_font_temp,
    get_font_ip,
    get_font_temp_range,
    get_font_label,
    get_font_title,
    get_font_medium,
    get_font_small,
    get_font_tiny
)
from mon_utils import cache_result, get_local_ip as _get_local_ip_raw, surface_cache

logger = logging.getLogger('mon_weather')

# 磁盘IO指示灯闪烁控制
_disk_io_blink_state = True
_disk_io_frame_counter = 0

# 时钟冒号闪烁控制
_colon_blink_state = True
_last_colon_blink_time = 0
COLON_BLINK_INTERVAL = 1.0


@cache_result(0.5)
def get_current_time() -> Dict[str, Any]:
    # 获取当前时间和日期信息（带缓存，每0.5秒更新）
    # 
    # Returns:
    #     Dict[str, Any]: 包含时间和日期信息的字典
    #         - hour: 当前小时
    #         - minute: 当前分钟
    #         - date_str: 格式化的日期字符串，格式为"YYYY年MM月DD日"
    #         - weekday_str: 星期几的中文名称
    now = datetime.now()
    return {
        "hour": now.hour,
        "minute": now.minute,
        "date_str": now.strftime("%Y年%m月%d日"),
        "weekday_str": WEEKDAY_MAP[now.weekday()]
    }


@cache_result(5.0)
def get_local_ip() -> str:
    # 获取内网IP地址（带缓存，每5秒更新）
    # 
    # 该函数通过创建一个UDP连接到Google DNS服务器(8.8.8.8)来获取本机的内网IP地址
    # 
    # Returns:
    #     str: 内网IP地址，如果获取失败则返回"未知"
    return _get_local_ip_raw()


@cache_result(WEATHER_UPDATE_INTERVAL)
def get_weather_info() -> Dict[str, Any]:
    # 获取天气信息（带缓存）
    # 
    # 该函数使用思知天气API获取当前天气和天气预报信息，
    # 并通过缓存装饰器减少API调用频率，提高性能。
    # 
    # Returns:
    #     Dict[str, Any]: 包含天气信息的字典
    #         - current: 当前天气信息
    #         - forecast: 天气预报信息列表
    try:
        weather_url = f"https://api.seniverse.com/v3/weather/daily.json?key={SENIVERSE_API_KEY}&location=ip&language=zh-Hans&unit=c"
        logger.info(f"天气API请求URL: {weather_url}")
        response = requests.get(weather_url, timeout=5)
        
        logger.info(f"天气API响应状态码: {response.status_code}")
        logger.info(f"天气API响应内容: {response.text[:500] if response.text else '空'}")
        
        if response.status_code == 200 and response.text:
            data = response.json()
            logger.info(f"天气API解析结果: {data}")
            return parse_seniverse_weather(data)
    except Exception as e:
        logger.error(f"获取天气信息失败: {e}")
    
    return DEFAULT_WEATHER_INFO.copy()


def parse_seniverse_weather(data: Dict[str, Any]) -> Dict[str, Any]:
    # 解析思知天气API返回的数据
    # 
    # Args:
    #     data: 思知天气API返回的JSON数据
    # 
    # Returns:
    #     Dict[str, Any]: 解析后的天气信息字典
    #         - current: 当前天气信息
    #         - forecast: 天气预报信息列表
    try:
        results = data.get('results', [])
        if not results:
            return DEFAULT_WEATHER_INFO.copy()
        
        location = results[0].get('location', {})
        city = location.get('name', '未知')
        daily = results[0].get('daily', [])
        
        current_weather = DEFAULT_CURRENT_WEATHER.copy()
        current_weather["city"] = city
        
        if daily:
            today = daily[0]
            current_weather.update({
                "temp": int(today.get('high', 0)),
                "condition": today.get('text_day', '未知'),
                "humidity": int(today.get('humidity', 0)),
                "wind": f"{today.get('wind_direction', '')} {today.get('wind_scale', '')}",
                "code": int(today.get('code_day', 0))
            })
        
        forecast = []
        for i in range(1, min(4, len(daily))):
            day_data = daily[i]
            
            date_str = day_data.get('date', '')
            if date_str:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                weekday = WEEKDAY_MAP[date_obj.weekday()]
                date_short = date_obj.strftime("%m-%d")
            else:
                weekday = "未知"
                date_short = "--"
            
            forecast.append({
                "date": date_short,
                "weekday": weekday,
                "temp_high": int(day_data.get('high', 0)),
                "temp_low": int(day_data.get('low', 0)),
                "condition": day_data.get('text_day', '未知'),
                "humidity": int(day_data.get('humidity', 0)),
                "wind": f"{day_data.get('wind_direction', '')} {day_data.get('wind_scale', '')}",
                "code": int(day_data.get('code_day', 0))
            })
        
        return {
            "current": current_weather,
            "forecast": forecast
        }
    except Exception as e:
        logger.error(f"解析思知天气数据失败: {e}")
        return DEFAULT_WEATHER_INFO.copy()


def get_disk_io_stats() -> Dict[str, Any]:
    # 获取磁盘IO状态信息（带缓存，每0.5秒更新）
    # 
    # 该函数获取所有磁盘的IO状态，包括SSD和HDD设备的读写速率
    # 
    # Returns:
    #     Dict[str, Any]: 包含磁盘IO状态的字典
    #         - ssd: SSD设备的IO状态列表
    #         - hdd: HDD设备的IO状态列表
    try:
        current_time = time.time()
        disk_io = psutil.disk_io_counters(perdisk=True)
        
        # 一次性获取所有设备类型和物理顺序
        device_info_list = _get_device_info_list([])
        
        # 处理设备信息
        ssd_devices, hdd_devices = [], []
        
        for device_info in device_info_list:
            # 计算IO活动
            has_read, has_write = _calculate_io_rates(
                device_info['name'], 
                disk_io, 
                current_time,
                get_disk_io_stats._last_disk_io_stats
            )
            
            # 创建设备信息
            device_data = {
                "name": device_info['display_name'],
                "has_read": has_read,
                "has_write": has_write,
                "type": device_info['type']
            }
            
            # 分类设备
            if device_info['type'] == "SSD":
                ssd_devices.append(device_data)
            else:
                hdd_devices.append(device_data)
        
        # 提取磁盘名称列表
        disk_names = [device_info['name'] for device_info in device_info_list]
        
        # 更新缓存
        get_disk_io_stats._last_disk_io_stats = {
            disk_name: stats
            for disk_name, stats in disk_io.items()
            if disk_name in disk_names or any(d in disk_name for d in disk_names)
        }
        
        # 返回结果
        return {
            "ssd": ssd_devices,
            "hdd": hdd_devices
        }
    except Exception as e:
        logger.error(f"获取磁盘IO状态失败: {e}")
        return {"ssd": [], "hdd": []}

# 初始化缓存
get_disk_io_stats._last_disk_io_stats = None
get_disk_io_stats = cache_result(WEATHER_DISK_IO_UPDATE_INTERVAL)(get_disk_io_stats)


@cache_result(5.0)
def _get_disk_info_with_types() -> Tuple[List[str], Dict[str, str]]:
    # 一次性获取所有磁盘信息（名称和类型）
    # 
    # 该函数通过执行lsblk命令获取所有物理磁盘设备的名称和类型，
    # 并过滤掉MMC设备（通常是系统盘），保持lsblk输出的物理接口顺序
    # 
    # Returns:
    #     Tuple[List[str], Dict[str, str]]: (磁盘名称列表, 设备类型映射)
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-o", "NAME,ROTA"],
            capture_output=True, text=True, timeout=3
        )
        
        if result.returncode == 0:
            disk_names = []
            device_types = {}
            
            lines = result.stdout.strip().split('\n')[1:]
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    dev_name = parts[0]
                    rota_value = parts[1]
                    # 过滤MMC设备
                    if 'mmc' not in dev_name.lower():
                        disk_names.append(dev_name)
                        # ROTA=0 表示非旋转设备（SSD），ROTA=1 表示旋转设备（HDD）
                        device_types[dev_name] = "SSD" if rota_value == "0" else "HDD"
            
            return disk_names, device_types
        return [], {}
    except Exception:
        return {}, {}


def _get_device_type_from_name(dev_name: str) -> str:
    # 根据设备名称判断设备类型
    # 
    # Args:
    #     dev_name: 设备名称
    # 
    # Returns:
    #     str: 设备类型（"SSD"或"HDD"）
    return "SSD" if "nvme" in dev_name else "HDD"


def _get_device_info_list(disk_names: List[str]) -> List[Dict[str, Any]]:
    # 获取设备信息列表（按物理接口顺序）
    # 
    # Args:
    #     disk_names: 磁盘设备名称列表
    # 
    # Returns:
    #     List[Dict[str, Any]]: 设备信息列表
    #         - name: 设备名称
    #         - display_name: 显示名称
    #         - type: 设备类型（SSD/HDD）
    disk_names, device_types = _get_disk_info_with_types()
    
    return [{
        "name": disk_name,
        "display_name": disk_name.upper(),
        "type": device_types.get(disk_name, _get_device_type_from_name(disk_name))
    } for disk_name in disk_names]


def _find_io_stats(disk_name: str, disk_io: Dict[str, Any]) -> Optional[Any]:
    # 查找匹配的磁盘IO统计数据
    # 
    # Args:
    #     disk_name: 磁盘设备名称
    #     disk_io: 磁盘IO统计数据字典
    # 
    # Returns:
    #     Optional[Any]: 匹配的IO统计数据，未找到返回None
    return next((stats for device, stats in disk_io.items() 
                if disk_name in device or device in disk_name), None)


def _calculate_io_rates(
    disk_name: str,
    disk_io: Dict[str, Any],
    current_time: float,
    last_stats: Optional[Dict[str, Any]] = None
) -> Tuple[bool, bool]:
    # 检测磁盘IO活动
    # 
    # 该函数检测磁盘是否有读写活动，通过比较当前和上次的IO统计数据
    # 
    # Args:
    #     disk_name: 磁盘设备名称
    #     disk_io: 当前磁盘IO统计数据
    #     current_time: 当前时间戳
    #     last_stats: 上次IO统计数据
    # 
    # Returns:
    #     Tuple[bool, bool]: 读写活动状态元组
    #         - 第一个元素表示是否有读取活动
    #         - 第二个元素表示是否有写入活动
    io_stats = _find_io_stats(disk_name, disk_io)
    
    if not io_stats:
        return False, False
    
    if last_stats is not None:
        last_io_stats = _find_io_stats(disk_name, last_stats)
        if last_io_stats:
            read_diff = io_stats.read_bytes - last_io_stats.read_bytes
            write_diff = io_stats.write_bytes - last_io_stats.write_bytes
            return read_diff > 0, write_diff > 0
    
    # 第一次调用时，假设所有设备都有活动（避免初始状态不闪烁）
    return True, True





def fill_device_list(
    devices: List[Dict],
    device_type: str,
    count: int
) -> List[Tuple[str, Optional[Dict]]]:
    # 填充设备列表
    # 
    # 该函数根据指定的数量填充设备列表，不足的位置用None填充
    # 
    # Args:
    #     devices: 设备信息列表
    #     device_type: 设备类型
    #     count: 需要填充的数量
    # 
    # Returns:
    #     List[Tuple[str, Optional[Dict]]]: 填充后的设备列表
    #         - 每个元素是一个元组，第一个元素是设备类型，第二个元素是设备信息或None
    return [(device_type, devices[i] if i < len(devices) else None) 
            for i in range(count)]


def load_weather_icon(
    weather_code: int,
    icon_size: str = "2x"
) -> Optional[pygame.Surface]:
    # 加载天气图标（带缓存）
    # 
    # 该函数根据天气代码和图标尺寸加载对应的天气图标
    # 使用缓存避免重复加载相同图片
    # 
    # Args:
    #     weather_code: 天气代码
    #     icon_size: 图标尺寸，"1x"或"2x"
    # 
    # Returns:
    #     Optional[pygame.Surface]: 天气图标Surface对象，如果加载失败则返回None
    cache_key = f"weather_icon_{weather_code}_{icon_size}"
    
    if cache_key in surface_cache:
        return surface_cache[cache_key].copy()
    
    icon_path = f"weather-icons/{weather_code}@{icon_size}.png"
    try:
        if os.path.exists(icon_path):
            icon_surf = pygame.image.load(icon_path)
            target_size = ICON_SIZE_2X if icon_size == "2x" else ICON_SIZE_1X
            icon_surf = pygame.transform.scale(icon_surf, (target_size, target_size))
            # 缓存图标
            surface_cache[cache_key] = icon_surf
            return icon_surf.copy()
        else:
            logger.warning(f"天气图片不存在: {icon_path}")
    except Exception as e:
        logger.error(f"加载天气图片失败: {e}")
    return None


def draw_weather_icon_with_fallback(
    surface: pygame.Surface,
    weather_code: int,
    icon_size: str,
    x: int,
    y: int,
    condition_text: str,
    centerx: bool = True
) -> int:
    # 绘制天气图标（带文字 fallback）
    # 
    # 该函数尝试绘制天气图标，如果图标不存在则绘制天气状况文字
    # 
    # Args:
    #     surface: 绘制表面
    #     weather_code: 天气代码
    #     icon_size: 图标尺寸，"1x"或"2x"
    #     x: 绘制起始X坐标
    #     y: 绘制起始Y坐标
    #     condition_text: 天气状况文字
    #     centerx: 是否水平居中绘制
    # 
    # Returns:
    #     int: 绘制后的下一个Y坐标位置
    icon_surf = load_weather_icon(weather_code, icon_size)
    
    if icon_surf:
        if centerx:
            icon_rect = icon_surf.get_rect(centerx=x, top=y)
        else:
            icon_rect = icon_surf.get_rect(left=x, top=y)
        surface.blit(icon_surf, icon_rect)
        return y + (100 if icon_size == "2x" else 80)
    else:
        font_size = 24 if icon_size == "2x" else 20
        condition_font = get_font_medium()
        condition_surf = condition_font.render(condition_text, True, COLORS["text_gray"])
        if centerx:
            condition_rect = condition_surf.get_rect(centerx=x, top=y)
        else:
            condition_rect = condition_surf.get_rect(left=x, top=y)
        surface.blit(condition_surf, condition_rect)
        return y + condition_surf.get_height() + 8


def draw_weather_page(surface: pygame.Surface, rect: pygame.Rect) -> None:
    # 绘制天气页面

    # 该函数绘制整个天气页面，包括时间日期、天气、内网IP和磁盘IO指示灯
    # 
    # Args:
    #     surface: 绘制表面
    #     rect: 绘制区域矩形
    # 
    # Returns:
    #     None
    surface.fill((0, 0, 0))
    
    time_info = get_current_time()
    weather_info = get_weather_info()
    disk_io = get_disk_io_stats()
    local_ip = get_local_ip()
    
    padding = 20
    current_y = rect.y + padding
    
    # 模块1：时间日期
    draw_time_date_module(surface, rect, current_y, time_info)
    current_y += DASHBOARD_TIME_HEIGHT + 25
    
    # 模块2：当天天气
    draw_current_weather_module(surface, rect, current_y, weather_info)
    current_y += DASHBOARD_CURRENT_WEATHER_HEIGHT + 25
    
    # 模块3：预报天气
    draw_forecast_module(surface, rect, current_y, weather_info)
    current_y += DASHBOARD_FORECAST_HEIGHT + 25
    
    # 模块4：内网IP
    draw_ip_module(surface, rect, current_y, local_ip)
    current_y += DASHBOARD_IP_HEIGHT + 25
    
    # 模块5：磁盘读写指示灯
    disk_io_y = rect.bottom - DASHBOARD_DISK_IO_HEIGHT - padding
    draw_disk_io_module(surface, rect, disk_io_y, disk_io)


def draw_time_date_module(
    surface: pygame.Surface,
    rect: pygame.Rect,
    y: int,
    time_info: Dict[str, Any]
) -> int:
    # 绘制时间日期模块
    # 
    # 该函数绘制时间和日期信息，包括当前时间、日期和星期几
    # 
    # Args:
    #     surface: 绘制表面
    #     rect: 绘制区域矩形
    #     y: 绘制起始Y坐标
    #     time_info: 时间信息字典
    # 
    # Returns:
    #     int: 绘制后的下一个Y坐标位置
    # 更新冒号闪烁状态
    global _colon_blink_state, _last_colon_blink_time
    current_time = time.time()
    if current_time - _last_colon_blink_time >= COLON_BLINK_INTERVAL:
        _colon_blink_state = not _colon_blink_state
        _last_colon_blink_time = current_time
    
    # 分别渲染小时、冒号和分钟
    hour_str = f"{time_info['hour']:02d}"
    minute_str = f"{time_info['minute']:02d}"
    colon_str = ":"
    
    time_font = get_font_time()
    
    # 渲染小时
    hour_surf = time_font.render(hour_str, True, COLORS["text_white"])
    hour_width = hour_surf.get_width()
    
    # 渲染冒号（通过颜色变化实现闪烁）
    colon_color = COLORS["text_white"] if _colon_blink_state else COLORS["text_gray"]
    colon_surf = time_font.render(colon_str, True, colon_color)
    colon_width = colon_surf.get_width()
    
    # 渲染分钟
    minute_surf = time_font.render(minute_str, True, COLORS["text_white"])
    
    # 计算总宽度和起始位置
    total_width = hour_width + colon_width + minute_surf.get_width()
    start_x = rect.centerx - total_width // 2
    
    # 绘制时间
    surface.blit(hour_surf, (start_x, y))
    surface.blit(colon_surf, (start_x + hour_width, y))
    surface.blit(minute_surf, (start_x + hour_width + colon_width, y))
    
    date_str = time_info['date_str']
    weekday_str = time_info['weekday_str']
    date_weekday_str = f"{date_str} {weekday_str}"
    
    date_font = get_font_medium()
    date_surf = date_font.render(date_weekday_str, True, COLORS["text_white"])
    date_rect = date_surf.get_rect(centerx=rect.centerx, top=y + hour_surf.get_height() + 5)
    surface.blit(date_surf, date_rect)
    
    return y + hour_surf.get_height() + date_surf.get_height() + 10


def draw_current_weather_module(
    surface: pygame.Surface,
    rect: pygame.Rect,
    y: int,
    weather_info: Dict[str, Any]
) -> int:
    # 绘制当天天气模块
    # 
    # 该函数绘制当天的天气信息，包括城市名、天气图标、温度、湿度和风力
    # 
    # Args:
    #     surface: 绘制表面
    #     rect: 绘制区域矩形
    #     y: 绘制起始Y坐标
    #     weather_info: 天气信息字典
    # 
    # Returns:
    #     int: 绘制后的下一个Y坐标位置
    current_weather = weather_info["current"]
    
    city_font = get_font_title()
    city_surf = city_font.render(f"{current_weather['city']}", True, COLORS["text_gray"])
    city_rect = city_surf.get_rect(centerx=rect.centerx, top=y)
    surface.blit(city_surf, city_rect)
    
    current_y = y + city_surf.get_height() + 8
    
    current_y = draw_weather_icon_with_fallback(
        surface, current_weather.get('code', 0), "2x",
        rect.centerx, current_y, current_weather['condition'], centerx=True
    )
    
    temp_str = f"{current_weather['temp']}°C"
    temp_font = get_font_temp()
    temp_surf = temp_font.render(temp_str, True, COLORS["text_white"])
    temp_rect = temp_surf.get_rect(centerx=rect.centerx, top=current_y)
    surface.blit(temp_surf, temp_rect)
    
    current_y += temp_surf.get_height() + 12
    
    detail_font = get_font_small()
    wind_info = current_weather.get('wind', '--')
    detail_str = f"湿度:{current_weather['humidity']}% 风力:{wind_info}"
    detail_surf = detail_font.render(detail_str, True, COLORS["text_gray"])
    detail_rect = detail_surf.get_rect(centerx=rect.centerx, top=current_y)
    surface.blit(detail_surf, detail_rect)
    
    return current_y + detail_surf.get_height() + 15


def draw_forecast_module(
    surface: pygame.Surface,
    rect: pygame.Rect,
    y: int,
    weather_info: Dict[str, Any]
) -> int:
    # 绘制天气预报模块
    # 
    # 该函数绘制未来几天的天气预报信息
    # 
    # Args:
    #     surface: 绘制表面
    #     rect: 绘制区域矩形
    #     y: 绘制起始Y坐标
    #     weather_info: 天气信息字典
    # 
    # Returns:
    #     int: 绘制后的下一个Y坐标位置
    forecast = weather_info["forecast"]
    
    if not forecast:
        return y
    
    forecast_count = len(forecast)
    item_width = (rect.width - 60) // forecast_count
    
    max_bottom_y = y
    for i in range(forecast_count):
        x = rect.x + 20 + i * (item_width + 20)
        day_weather = forecast[i]
        bottom_y = draw_forecast_item(surface, x, y, item_width, day_weather)
        max_bottom_y = max(max_bottom_y, bottom_y)
    
    return max_bottom_y + 15


def draw_ip_module(
    surface: pygame.Surface,
    rect: pygame.Rect,
    y: int,
    local_ip: str
) -> int:
    # 绘制内网IP模块
    # 
    # 该函数绘制内网IP地址信息
    # 
    # Args:
    #     surface: 绘制表面
    #     rect: 绘制区域矩形
    #     y: 绘制起始Y坐标
    #     local_ip: 内网IP地址
    # 
    # Returns:
    #     int: 绘制后的下一个Y坐标位置
    ip_font = get_font_ip()
    local_ip_str = f"内网: {local_ip}"
    
    local_ip_surf = ip_font.render(local_ip_str, True, COLORS["text_gray"])
    local_ip_rect = local_ip_surf.get_rect(centerx=rect.centerx, top=y - 7)
    surface.blit(local_ip_surf, local_ip_rect)
    
    return y + local_ip_surf.get_height() + 15


def draw_forecast_item(
    surface: pygame.Surface,
    x: int,
    y: int,
    width: int,
    day_weather: Dict[str, Any]
) -> int:
    # 绘制单个天气预报项
    # 
    # 该函数绘制单个天气预报项，包括日期、星期、天气图标、温度范围、湿度和风力
    # 
    # Args:
    #     surface: 绘制表面
    #     x: 绘制起始X坐标
    #     y: 绘制起始Y坐标
    #     width: 绘制宽度
    #     day_weather: 单日天气信息字典
    # 
    # Returns:
    #     int: 绘制后的下一个Y坐标位置
    date_font = get_font_small()
    date_surf = date_font.render(f"{day_weather['date']} {day_weather['weekday']}", True, COLORS["text_white"])
    date_rect = date_surf.get_rect(centerx=x + width // 2, top=y)
    surface.blit(date_surf, date_rect)
    
    current_y = draw_weather_icon_with_fallback(
        surface, day_weather.get('code', 0), "1x",
        x + width // 2, y + 25, day_weather['condition'], centerx=True
    )
    
    # 温度范围：向上调整，靠近天气图标
    temp_range_str = f"{day_weather['temp_low']}°~{day_weather['temp_high']}°"
    temp_range_font = get_font_temp_range()
    temp_range_surf = temp_range_font.render(temp_range_str, True, COLORS["text_white"])
    temp_range_rect = temp_range_surf.get_rect(centerx=x + width // 2, top=current_y - 10)
    surface.blit(temp_range_surf, temp_range_rect)
    
    # 湿度风力：保持在温度范围下方
    detail_font = get_font_tiny()
    detail_str = f"湿度:{day_weather['humidity']}% 风力:{day_weather['wind']}"
    detail_surf = detail_font.render(detail_str, True, COLORS["text_gray"])
    detail_rect = detail_surf.get_rect(centerx=x + width // 2, top=temp_range_rect.bottom + 5)
    surface.blit(detail_surf, detail_rect)

    return detail_rect.bottom + 5


def draw_disk_io_module(
    surface: pygame.Surface,
    rect: pygame.Rect,
    y: int,
    disk_io: Dict[str, Any]
) -> None:
    # 绘制磁盘IO模块
    # 
    # 该函数绘制磁盘IO读写指示灯，包括SSD和HDD设备
    # 
    # Args:
    #     surface: 绘制表面
    #     rect: 绘制区域矩形
    #     y: 绘制起始Y坐标
    #     disk_io: 磁盘IO状态字典
    # 
    # Returns:
    #     None
    global _disk_io_blink_state, _disk_io_frame_counter
    
    start_y = y + 70
    row_height = 100
    col_width = (rect.width - 60) // DISK_LAYOUT_COLS
    
    ssd_devices = disk_io.get("ssd", [])
    hdd_devices = disk_io.get("hdd", [])
    
    devices = _prepare_disk_devices(ssd_devices, hdd_devices)
    
    # 统一更新闪烁状态（在循环外更新一次，确保所有灯同步）
    _disk_io_frame_counter += 1
    if _disk_io_frame_counter >= 1:
        _disk_io_blink_state = not _disk_io_blink_state
        _disk_io_frame_counter = 0
    
    for idx, (label, row, col) in enumerate(DISK_POSITIONS):
        device_type, device_info = devices[idx]
        
        x = rect.x + 15 + col * col_width
        y_pos = start_y + row * row_height
        draw_single_disk_io(surface, x, y_pos, label, device_info, _disk_io_blink_state)


def _prepare_disk_devices(
    ssd_devices: List[Dict],
    hdd_devices: List[Dict]
) -> List[Tuple[str, Optional[Dict]]]:
    # 准备磁盘设备列表
    # 
    # 该函数根据DISK_POSITIONS配置，将SSD和HDD设备按顺序排列
    # 
    # Args:
    #     ssd_devices: SSD设备列表
    #     hdd_devices: HDD设备列表
    # 
    # Returns:
    #     List[Tuple[str, Optional[Dict]]]: 按位置排列的设备列表
    #         - 每个元素是一个元组，第一个元素是设备类型，第二个元素是设备信息或None
    ssd_list = fill_device_list(ssd_devices, "SSD", SSD_DEVICES_COUNT)
    hdd_list = fill_device_list(hdd_devices, "HDD", HDD_DEVICES_COUNT)
    
    devices = []
    for label, _, _ in DISK_POSITIONS:
        if label.startswith("SSD"):
            idx = int(label[3:]) - 1
            devices.append(ssd_list[idx] if idx < len(ssd_list) else ("SSD", None))
        else:
            idx = int(label[3:]) - 1
            devices.append(hdd_list[idx] if idx < len(hdd_list) else ("HDD", None))
    
    return devices


def _draw_io_indicator(
    surface: pygame.Surface,
    x: int,
    y: int,
    has_activity: bool,
    blink_state: bool,
    active_color: Tuple[int, int, int],
    label_text: str
) -> None:
    # 绘制单个IO指示灯
    # 
    # Args:
    #     surface: 绘制表面
    #     x: 指示灯X坐标
    #     y: 指示灯Y坐标
    #     has_activity: 是否有IO活动
    #     blink_state: 闪烁状态
    #     active_color: 激活状态颜色
    #     label_text: 标签文字
    color = active_color if has_activity and blink_state else (30, 30, 40)
    radius = 8 if has_activity and blink_state else 6
    
    pygame.draw.circle(surface, color, (int(x), int(y)), radius)
    
    label_font = get_font_label()
    label = label_font.render(label_text, True, COLORS["text_gray"])
    label_rect = label.get_rect(centerx=x, top=y + 12)
    surface.blit(label, label_rect)


def draw_single_disk_io(
    surface: pygame.Surface,
    x: int,
    y: int,
    label: str,
    device: Optional[Dict[str, Any]],
    blink_state: bool
) -> None:
    # 绘制单个磁盘的读写指示灯
    # 
    # 该函数绘制单个磁盘的读写指示灯，包括设备名称、读取指示灯和写入指示灯
    # 只要有读写活动（不为0）就会高频闪烁
    # 
    # Args:
    #     surface: 绘制表面
    #     x: 绘制起始X坐标
    #     y: 绘制起始Y坐标
    #     label: 设备标签（如"SSD1"、"HDD1"）
    #     device: 设备信息字典，如果为None表示未插硬盘
    #     blink_state: 闪烁状态
    # 
    # Returns:
    #     None
    name_font = get_font_small()
    
    if device is None:
        # 未插硬盘，显示标签和灰色指示灯
        name_surf = name_font.render(label, True, COLORS["text_gray"])
        name_rect = name_surf.get_rect(centerx=x + 60, top=y - 10)
        surface.blit(name_surf, name_rect)
        
        lights_y = y + 30
        
        # 绘制灰色读指示灯
        _draw_io_indicator(surface, x + 45, lights_y, False, False, (60, 60, 70), "读")
        
        # 绘制灰色写指示灯
        _draw_io_indicator(surface, x + 75, lights_y, False, False, (60, 60, 70), "写")
    else:
        # 已插硬盘，显示设备名称和正常指示灯
        name_surf = name_font.render(f"{device['name']}", True, COLORS["text_white"])
        name_rect = name_surf.get_rect(centerx=x + 60, top=y - 10)
        surface.blit(name_surf, name_rect)
        
        lights_y = y + 30
        
        # 检查是否有读写活动
        has_read = device.get("has_read", False)
        has_write = device.get("has_write", False)
        
        # 绘制读取指示灯
        _draw_io_indicator(surface, x + 45, lights_y, has_read, blink_state, COLORS["net_recv"], "读")
        
        # 绘制写入指示灯
        _draw_io_indicator(surface, x + 75, lights_y, has_write, blink_state, (255, 60, 60), "写")
