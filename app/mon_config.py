#!/usr/bin/env python3

import os
import math
import logging
import pygame
from collections import deque

logger = logging.getLogger('mon_config')

# =============================================================================
# 全局基础设置 - 适用于整个应用的基础配置
# =============================================================================

# 屏幕基础参数 - 适配海康R1设备376x960竖屏
SCREEN_WIDTH = 376      # 屏幕宽度（像素）
SCREEN_HEIGHT = 960     # 屏幕高度（像素）
FB_DEV = "/dev/fb0"     # 帧缓冲设备路径

# 屏幕状态缓存配置
SCREEN_CHECK_INTERVAL = 1.0  # 屏幕状态检查间隔（秒）
DEFAULT_SCREEN_ENABLED = True  # 默认屏幕开启状态

# 鼠标事件配置
MOUSE_WHEEL_BRIGHT_TIME = 15  # 滚轮亮屏时间（秒）
BRIGHTNESS_STEP = 2000  # 亮度调整步长

# 飞牛应用开放平台权限目录配置
PERMISSION_DIRS = []        # 可读取权限目录列表
BACKGROUND_IMAGES = []      # 背景图片列表
CURRENT_BG_INDEX = 0        # 当前背景图片索引
LAST_BG_CHANGE_TIME = 0     # 最后背景切换时间
BG_CHANGE_INTERVAL = int(os.environ.get('config_bg_interval', '1'))  # 背景切换间隔（秒）
current_accessible_paths = ""  # 当前可访问路径（用于检测变更）

# 性能优化配置
FRAME_RATE = 12.0                    # 主循环帧率（FPS），降低CPU占用

# 字体配置（全局使用）
DASHBOARD_FONT_NAME = "WenQuanYi Micro Hei"

# =============================================================================
# 资源监控页配置 - 特定于资源监控页面的设置
# =============================================================================

# 背景图片路径配置
background_path_raw = "${TRIM_APPDEST}/background.png"
BACKGROUND_PATH = os.path.expandvars(background_path_raw)

# 模块间距配置
GAP = 14                # 模块间距（像素）
CARD_WIDTH = SCREEN_WIDTH - 2 * GAP  # 卡片宽度（屏幕宽度减去两侧间距）

# 视觉样式配置
CARD_RADIUS = 15        # 卡片圆角半径（像素）
CARD_ALPHA = 190        # 卡片透明度（0-255）
SHADOW_ALPHA = 30       # 阴影透明度（0-255）
RING_WIDTH = 18         # 环形图宽度（像素）
RING_START_ANGLE = math.pi/2  # 环形图起始角度（12点方向）
BAR_RADIUS = 10         # 进度条圆角半径（像素）
LINE_WIDTH = 1          # 折线图线条粗细（像素）

# 渲染优化配置
SURFACE_CACHE_MAX = 5               # Surface缓存最大数量，减少内存占用
ENABLE_PARTIAL_UPDATE = True        # 启用部分更新，只更新变化区域
LOG_UPDATE_INTERVAL = 30            # 日志输出间隔（秒），减少日志开销

# 系统资源监控配置
ENABLE_PERFORMANCE_MONITOR = False  # 启用性能监控（调试时开启）
PERFORMANCE_SAMPLE_INTERVAL = 10    # 性能采样间隔（秒）

# 配色方案 - 统一的视觉色彩配置
COLORS = {
    # 卡片和背景颜色
    "card_bg": (70, 75, 85),        # 卡片背景色（深灰色）
    "card_shadow": (20, 20, 25),    # 卡片阴影色（深黑色）
    "bg_dark": (45, 50, 60),        # 深色背景（深灰）
    "bg_light": (80, 85, 95),       # 浅色背景（浅灰）
    
    # CPU相关颜色
    "cpu_normal": (80, 200, 120),   # CPU正常状态（绿色）
    "cpu_warn": (255, 180, 60),     # CPU警告状态（橙色）
    "cpu_high": (255, 80, 80),      # CPU高负载状态（红色）
    
    # 内存和磁盘颜色
    "mem_used": (80, 200, 120),     # 内存使用（绿色）
    "disk_used": (140, 100, 240),   # 磁盘使用（紫色）
    "disk_temp_normal": (80, 200, 120),    # 磁盘温度正常（绿色）
    "disk_temp_warm": (255, 180, 60),      # 磁盘温度警告（橙色）
    "disk_temp_hot": (255, 80, 80),        # 磁盘温度过高（红色）
    
    # 网络颜色
    "net_send": (255, 100, 160),    # 网络发送（粉色）
    "net_recv": (60, 180, 240),     # 网络接收（蓝色）
    
    # 文字和边框颜色
    "text_white": (255, 255, 255),  # 白色文字
    "text_gray": (200, 200, 210),   # 灰色文字
    "border": (90, 95, 105),        # 边框颜色（中灰）
    "proc_text": (240, 80, 80),     # 进程文字（红色）
    "disk_text": (255, 255, 255),   # 磁盘文字（白色）
    "disk_text_shadow": (0, 0, 0, 128)  # 文字阴影（半透明黑色）
}

# 资源监控字体变量（在模块导入时初始化）
FONT_TITLE = None       # 标题字体（20px）
FONT_LARGE = None       # 大号字体（28px）
FONT_MEDIUM = None      # 中号字体（22px）
FONT_SMALL = None       # 小号字体（16px）
FONT_TINY = None        # 极小字体（14px）

# 模块高度配置 - 各功能模块的显示高度
CPU_HEIGHT = 180        # CPU模块高度（像素）
MEM_HEIGHT = 110        # 内存模块高度（像素）
DISK_HEIGHT = 180       # 磁盘模块高度（像素）
NET_HEIGHT = 200        # 网络模块高度（像素）
PROC_HEIGHT = 210       # 进程模块高度（像素）

# CPU模块配置
CPU_TEMP_LOW = 50       # 低温阈值（正常显示）
CPU_TEMP_MID = 80       # 中温阈值（警告显示）
CPU_TEMP_CACHE_TIME = 3.0  # CPU温度缓存时间（秒）

# 内存模块配置
MEMORY_CACHE_TIME = 3.0  # 内存信息缓存时间（秒）

# 存储模块配置
DISK_INIT_DELAY = 1     # 磁盘信息初始化延迟（秒）
DISK_UPDATE_INTERVAL = 5.0  # 磁盘信息更新间隔（秒）
DISK_DISPLAY_COUNT = 6  # 最大显示分区数量
ALLOWED_MOUNT_PREFIXES = ["/vol1", "/vol2", "/vol3", "/vol4", "/vol5", "/vol6"]  # 允许显示的挂载点前缀

# 网络模块配置
NETWORK_UPDATE_INTERVAL = 3.0  # 网络信息更新间隔（秒）
MAX_NET_HISTORY = 100  # 网络历史记录最大长度，减少内存占用

# 网络模块全局变量（使用deque优化内存）
g_net_last_update = 0   # 最后网络更新时间戳
g_net_send = 0.0        # 网络发送速率（MB/s）
g_net_recv = 0.0        # 网络接收速率（MB/s）
g_net_last_io = None    # 最后网络IO统计
g_net_history = deque(maxlen=MAX_NET_HISTORY)  # 网络历史数据队列

# 进程模块配置
PROCESS_UPDATE_INTERVAL = 3.0  # 进程信息更新间隔（秒）
PROCESS_CPU_THRESHOLD = 0.2  # 进程CPU使用率最小阈值（%），过滤低占用进程
PROCESS_SORT_LIMIT = 5  # 进程排序前N个限制，减少排序开销

# =============================================================================
# 天气页面配置 - 特定于天气页面的设置
# =============================================================================

# 天气API配置
SENIVERSE_API_KEY = "SWcgQfk4sHr8uPDYc"  # 思知天气API Key
WEATHER_UPDATE_INTERVAL = 28800.0  # 天气页面天气更新间隔（秒，8小时）

# 天气图标尺寸配置
ICON_SIZE_1X = 51
ICON_SIZE_2X = 90

# 星期映射
WEEKDAY_MAP = {
    0: "周一", 1: "周二", 2: "周三", 3: "周四",
    4: "周五", 5: "周六", 6: "周日"
}

# 默认天气数据
DEFAULT_CURRENT_WEATHER = {
    "temp": "--", "condition": "未知", "humidity": "--",
    "wind": "--", "city": "未知", "code": 0
}

DEFAULT_WEATHER_INFO = {
    "current": DEFAULT_CURRENT_WEATHER.copy(),
    "forecast": []
}

# 时间日期模块配置
DASHBOARD_TIME_HEIGHT = 200  # 时间日期模块高度

# 当天天气模块配置
DASHBOARD_CURRENT_WEATHER_HEIGHT = 220  # 当天天气模块高度

# 预报天气模块配置
DASHBOARD_FORECAST_HEIGHT = 180  # 预报天气模块高度

# 内网IP模块配置
DASHBOARD_IP_HEIGHT = 80  # 内网IP模块高度

# 磁盘IO指示灯模块配置
DISK_IO_THRESHOLD = 0.1  # 磁盘IO活动阈值（MB/s）
WEATHER_DISK_IO_UPDATE_INTERVAL = 0.5  # 天气页面磁盘IO更新间隔（秒，每0.5秒更新一次）
DASHBOARD_DISK_IO_HEIGHT = 220  # 磁盘读写指示灯模块高度

# 磁盘布局配置
DISK_LAYOUT_ROWS = 2
DISK_LAYOUT_COLS = 3
DISK_DEVICES_TOTAL = 6
SSD_DEVICES_COUNT = 2
HDD_DEVICES_COUNT = 4

# 磁盘位置配置（2行3列布局）
DISK_POSITIONS = [
    ("SSD1", 0, 0),
    ("HDD1", 0, 1),
    ("HDD2", 0, 2),
    ("SSD2", 1, 0),
    ("HDD3", 1, 1),
    ("HDD4", 1, 2),
]

# 天气页面专用字体（在模块导入时初始化）
FONT_TIME = None        # 时间字体（140px）
FONT_TEMP = None        # 温度字体（42px）
FONT_IP = None         # IP字体（24px）
FONT_TEMP_RANGE = None  # 温度范围字体（26px）
FONT_LABEL = None       # 标签字体（10px）

# =============================================================================
# 通用辅助设置 - 辅助函数和通用工具
# =============================================================================

# Surface缓存管理
surface_cache = {}  # Surface缓存字典
card_templates = {}  # 卡片模板缓存字典
background_surface = None  # 背景Surface缓存

def init_fonts():
    """初始化字体"""
    global FONT_TITLE, FONT_LARGE, FONT_MEDIUM, FONT_SMALL, FONT_TINY
    global FONT_TIME, FONT_TEMP, FONT_IP, FONT_TEMP_RANGE, FONT_LABEL
    FONT_TITLE = pygame.font.SysFont(DASHBOARD_FONT_NAME, 20)  # 标题字体
    FONT_LARGE = pygame.font.SysFont(DASHBOARD_FONT_NAME, 28)  # 大号字体
    FONT_MEDIUM = pygame.font.SysFont(DASHBOARD_FONT_NAME, 22)  # 中号字体
    FONT_SMALL = pygame.font.SysFont(DASHBOARD_FONT_NAME, 16)  # 小号字体
    FONT_TINY = pygame.font.SysFont(DASHBOARD_FONT_NAME, 14)  # 极小字体
    FONT_TIME = pygame.font.SysFont(DASHBOARD_FONT_NAME, 140)  # 时间字体
    FONT_TEMP = pygame.font.SysFont(DASHBOARD_FONT_NAME, 42)  # 温度字体
    FONT_IP = pygame.font.SysFont(DASHBOARD_FONT_NAME, 24)  # IP字体
    FONT_TEMP_RANGE = pygame.font.SysFont(DASHBOARD_FONT_NAME, 26)  # 温度范围字体
    FONT_LABEL = pygame.font.SysFont(DASHBOARD_FONT_NAME, 10)  # 标签字体
    logger.info(f"字体初始化成功，使用字体: {DASHBOARD_FONT_NAME}")

# 模块导入时自动初始化字体（延迟初始化，避免Pygame初始化问题）
def _init_fonts_on_demand():
    """按需初始化字体"""
    global FONT_TITLE, FONT_LARGE, FONT_MEDIUM, FONT_SMALL, FONT_TINY
    global FONT_TIME, FONT_TEMP, FONT_IP, FONT_TEMP_RANGE, FONT_LABEL
    if FONT_TITLE is None:
        init_fonts()

# 创建字体访问包装器，确保字体在使用前被初始化
def get_font_title():
    _init_fonts_on_demand()
    return FONT_TITLE

def get_font_large():
    _init_fonts_on_demand()
    return FONT_LARGE

def get_font_medium():
    _init_fonts_on_demand()
    return FONT_MEDIUM

def get_font_small():
    _init_fonts_on_demand()
    return FONT_SMALL

def get_font_tiny():
    _init_fonts_on_demand()
    return FONT_TINY

def get_font_time():
    _init_fonts_on_demand()
    return FONT_TIME

def get_font_temp():
    _init_fonts_on_demand()
    return FONT_TEMP

def get_font_ip():
    _init_fonts_on_demand()
    return FONT_IP

def get_font_temp_range():
    _init_fonts_on_demand()
    return FONT_TEMP_RANGE

def get_font_label():
    _init_fonts_on_demand()
    return FONT_LABEL
