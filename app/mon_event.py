#!/usr/bin/env python3

import os
import time
import pygame
import logging
import mon_config as config

# 配置日志
logger = logging.getLogger('mon_event')

class MouseEventHandler:
    def __init__(self):
        # 屏幕状态
        self.screen_enabled = True
        # 页面状态
        self.current_page = 1  # 0: 监控页面, 1: 天气页面
        self.total_pages = 2   # 总页面数
        # 亮度控制相关
        self.brightness_path = "/sys/devices/pci0000:00/0000:00:02.0/drm/card0/card0-DSI-1/intel_backlight/brightness"
        self.brightness_min = 0  # 最小亮度写死为0
        self.brightness_max = 96000  # 最大亮度写死为96000
        self.brightness_step = config.BRIGHTNESS_STEP
        # 屏幕空白控制路径
        self.screen_blank_path = "/sys/class/graphics/fb0/blank"
        # 读取当前亮度
        self.current_brightness = self.get_current_brightness()
        self.last_brightness = self.current_brightness  # 保存关闭前的亮度
        # 读取配置的初始屏幕模式
        self.config_screen_mode = os.environ.get('config_screen_mode', 'weather').lower()
        # 根据配置设置初始屏幕状态和页面
        if self.config_screen_mode == 'off':
            self.screen_enabled = False
            self.current_page = 1  # 默认天气页面
        elif self.config_screen_mode == 'monitor':
            self.screen_enabled = True
            self.current_page = 0  # 监控页面
        else:  # weather
            self.screen_enabled = True
            self.current_page = 1  # 天气页面
        # 亮屏临时状态
        self.temp_bright_screen = False
        self.temp_bright_end_time = 0
    
    def get_current_brightness(self):
        """
        获取当前屏幕亮度
        """
        try:
            if os.path.exists(self.brightness_path):
                with open(self.brightness_path, 'r') as f:
                    return int(f.read().strip())
        except Exception as e:
            logger.error(f"获取亮度失败: {e}")
        return 50000  # 默认亮度
    
    def set_brightness(self, brightness):
        """
        设置屏幕亮度
        """
        try:
            # 确保亮度在阈值范围内
            brightness = max(self.brightness_min, min(self.brightness_max, brightness))
            if os.path.exists(self.brightness_path):
                with open(self.brightness_path, 'w') as f:
                    f.write(str(brightness))
            # 无论文件是否存在，都更新内部状态
            self.current_brightness = brightness
            logger.info(f"屏幕亮度已设置为: {brightness}")
        except Exception as e:
            logger.error(f"设置亮度失败: {e}")
    
    def set_screen_enabled(self, enabled):
        """
        设置屏幕开启/关闭状态
        """
        try:
            if os.path.exists(self.screen_blank_path):
                with open(self.screen_blank_path, 'w') as f:
                    f.write('0' if enabled else '1')
            
            # 关闭屏幕时记录当前亮度并设置为0
            if not enabled:
                # 只有在当前亮度不为0时才保存，避免重复关屏覆盖有效亮度
                if self.current_brightness != 0:
                    self.last_brightness = self.current_brightness
                self.set_brightness(0)  # 关闭时亮度设为0
            # 开启屏幕时恢复之前的亮度
            elif enabled and self.current_brightness == 0:
                self.set_brightness(self.last_brightness)
            
            self.screen_enabled = enabled
            logger.info(f"屏幕状态已{'开启' if enabled else '关闭'}")
        except Exception as e:
            logger.error(f"设置屏幕状态失败: {e}")
    
    def get_screen_status(self):
        """
        获取当前屏幕状态
        """
        current_time = time.time()
        
        # 检查临时亮屏状态
        if self.temp_bright_screen:
            if current_time > self.temp_bright_end_time:
                self.temp_bright_screen = False
                # 恢复配置的屏幕状态
                current_config = os.environ.get('config_screen_mode', 'weather').lower()
                self.config_screen_mode = current_config
                # 根据配置恢复屏幕状态
                if current_config == 'off':
                    self.set_screen_enabled(False)
                else:
                    self.set_screen_enabled(True)
            else:
                # 临时亮屏期间，确保屏幕是开启的
                if not self.screen_enabled:
                    self.set_screen_enabled(True)
                return True
        
        return self.screen_enabled
    
    def get_current_page(self):
        """
        获取当前页面
        """
        return self.current_page
    
    def switch_page(self):
        """
        切换页面
        """
        self.current_page = (self.current_page + 1) % self.total_pages
        logger.info(f"切换到页面: {'监控页面' if self.current_page == 0 else '天气页面'}")
        return self.current_page
    
    def handle_mouse_event(self, event):
        """
        处理鼠标事件
        """
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # 左键：切换页面
                logger.info("收到鼠标左键点击，切换页面")
                self.switch_page()
            elif event.button == 2:
                # 中键：开启屏幕（如果关闭）并保持亮度调整
                logger.info("收到鼠标中键点击")
                current_screen_enabled = self.get_screen_status()
                if not current_screen_enabled:
                    self.config_screen_power = True
                    os.environ['config_screen_power'] = 'true'
                    self.set_screen_enabled(True)
                    self.temp_bright_screen = False
            elif event.button == 3:
                # 右键：切换屏幕开关
                current_screen_enabled = self.get_screen_status()
                if current_screen_enabled:
                    logger.info("收到鼠标右键点击，关闭屏幕")
                    self.config_screen_power = False
                    os.environ['config_screen_power'] = 'false'
                    self.set_screen_enabled(False)
                    self.temp_bright_screen = False
                else:
                    logger.info("收到鼠标右键点击，开启屏幕")
                    self.config_screen_power = True
                    os.environ['config_screen_power'] = 'true'
                    self.set_screen_enabled(True)
                    self.temp_bright_screen = False
        
        elif event.type == pygame.MOUSEWHEEL:
            logger.info(f"收到鼠标滚轮滚动，方向: {event.y}")
            
            # 立即处理滚轮事件，不管屏幕当前状态
            
            # 检查当前屏幕状态
            current_screen_enabled = self.get_screen_status()
            
            if not current_screen_enabled:
                # 如果屏幕当前是关闭的，临时亮屏15秒
                self.temp_bright_screen = True
                self.temp_bright_end_time = time.time() + config.MOUSE_WHEEL_BRIGHT_TIME
                
                # 设置屏幕为开启状态
                self.set_screen_enabled(True)
                # 恢复上一次关屏前的亮度
                self.set_brightness(self.last_brightness)
                logger.info(f"屏幕已关闭，临时亮屏{config.MOUSE_WHEEL_BRIGHT_TIME}秒")
            
            # 调整亮度
            new_brightness = self.current_brightness + (self.brightness_step if event.y > 0 else -self.brightness_step)
            logger.info(f"{'向上' if event.y > 0 else '向下'}滚动，{'提高' if event.y > 0 else '降低'}亮度")
            self.set_brightness(new_brightness)
