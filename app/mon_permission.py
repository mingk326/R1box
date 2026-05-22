#!/usr/bin/env python3

import os
import logging
import time
import pygame

from mon_config import (
    PERMISSION_DIRS, BACKGROUND_IMAGES, CURRENT_BG_INDEX,
    LAST_BG_CHANGE_TIME, BG_CHANGE_INTERVAL, current_accessible_paths
)

logger = logging.getLogger(__name__)


def init_permission_dirs() -> None:
    """
    初始化飞牛应用开放平台权限目录（精简版）
    """
    global PERMISSION_DIRS, BACKGROUND_IMAGES
    
    # 清空权限目录列表
    PERMISSION_DIRS = []
    
    # 获取可访问路径配置
    accessible_paths_env = os.environ.get('config_accessible_paths', os.environ.get('TRIM_DATA_ACCESSIBLE_PATHS', ''))
    
    if accessible_paths_env:
        paths = [path.strip() for path in accessible_paths_env.split(':') if path.strip()]
        
        # 验证目录有效性
        for dir_path in paths:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                PERMISSION_DIRS.append(dir_path)
            else:
                logger.warning(f"无效目录: {dir_path}")
        
        # 扫描所有权限目录中的图片文件
        scan_background_images()
    else:
        logger.warning("可访问路径未设置，使用默认背景图片")


def check_accessible_paths() -> bool:
    """
    检查可访问路径是否发生变更
    
    Returns:
        bool: 路径是否发生变更
    """
    global current_accessible_paths
    
    # 获取当前配置变量值
    new_paths = os.environ.get('config_accessible_paths', '')
    if not new_paths:
        new_paths = os.environ.get('TRIM_DATA_ACCESSIBLE_PATHS', '')
    
    # 检查是否发生变化
    if new_paths != current_accessible_paths:
        logger.info(f"检测到路径变更: {new_paths}")
        current_accessible_paths = new_paths
        init_permission_dirs()  # 重新初始化权限目录
        return True
    
    return False


def scan_background_images() -> None:
    """
    扫描权限目录中的背景图片
    """
    global BACKGROUND_IMAGES
    
    BACKGROUND_IMAGES.clear()
    
    # 支持的图片格式
    supported_formats = ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp']
    
    image_count = 0
    for dir_path in PERMISSION_DIRS:
        try:
            # 扫描目录中的图片文件
            for filename in os.listdir(dir_path):
                file_path = os.path.join(dir_path, filename)
                
                # 检查是否为图片文件
                if os.path.isfile(file_path) and any(filename.lower().endswith(ext) for ext in supported_formats):
                    BACKGROUND_IMAGES.append(file_path)
                    image_count += 1
        except PermissionError:
            logger.warning(f"无权限访问目录: {dir_path}")
        except Exception as e:
            logger.warning(f"扫描目录失败 {dir_path}: {e}")
    
    # 按文件名排序图片列表
    BACKGROUND_IMAGES.sort()


def get_next_background() -> str:
    """
    获取下一张背景图片路径
    
    Returns:
        str: 背景图片路径
    """
    global CURRENT_BG_INDEX, LAST_BG_CHANGE_TIME
    
    current_time = time.time()
    
    # 检查是否需要切换背景
    if current_time - LAST_BG_CHANGE_TIME >= BG_CHANGE_INTERVAL:
        if BACKGROUND_IMAGES:
            CURRENT_BG_INDEX = (CURRENT_BG_INDEX + 1) % len(BACKGROUND_IMAGES)
        LAST_BG_CHANGE_TIME = current_time
    
    # 返回当前背景图片路径
    if BACKGROUND_IMAGES:
        return BACKGROUND_IMAGES[CURRENT_BG_INDEX]
    else:
        # 使用默认背景图片
        from mon_config import BACKGROUND_PATH
        return BACKGROUND_PATH


def create_dynamic_background() -> pygame.Surface:
    """
    创建动态背景Surface
    
    Returns:
        pygame.Surface: 背景Surface对象
    """
    from mon_config import SCREEN_WIDTH, SCREEN_HEIGHT, background_surface
    
    # 检查缓存
    if background_surface is not None:
        return background_surface
    
    try:
        # 获取当前背景图片路径
        bg_path = get_next_background()
        
        # 加载背景图片
        bg_image = pygame.image.load(bg_path).convert()
        
        # 缩放背景图片以适应屏幕
        bg_surface = pygame.transform.scale(bg_image, (SCREEN_WIDTH, SCREEN_HEIGHT))
        
        # 缓存背景Surface
        background_surface = bg_surface
        
        return bg_surface
        
    except Exception as e:
        logger.warning(f"加载背景图片失败: {e}")
        
        # 创建默认背景
        default_bg = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        default_bg.fill((45, 50, 60))  # 深灰色背景
        
        # 缓存默认背景
        background_surface = default_bg
        return default_bg