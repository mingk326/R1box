#!/usr/bin/env python3

import sys
import os
import pygame
import logging
import time

# 导入自定义模块
import mon_config as config
import mon_permission as permission
import mon_cpu as cpu
import mon_memory as memory
import mon_disk as disk
import mon_network as network
import mon_process as process
import mon_event
import mon_weather

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('screen_mon')


def init_env():
    """
    初始化Pygame和SDL环境变量
    """
    # 必要的环境变量设置
    env_vars = {
        # SDL相关环境变量
        'XDG_RUNTIME_DIR': '/tmp',
        'SDL_FBDEV': config.FB_DEV,
        'SDL_DISPLAY': ':0',
        'SDL_AUDIODRIVER': 'dummy',
        
        # Pygame相关环境变量
        'PYGAME_HIDE_SUPPORT_PROMPT': '1'
    }
    
    # 批量设置环境变量
    for key, value in env_vars.items():
        os.environ.setdefault(key, value)


def init_pygame():
    """
    初始化Pygame库和屏幕设置
    
    Returns:
        pygame.Surface: 初始化后的屏幕对象
    """
    pygame.init()
    
    # 设置屏幕模式
    try:
        screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.FULLSCREEN | pygame.NOFRAME)
    except Exception:
        screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    
    # 隐藏鼠标光标
    pygame.mouse.set_visible(False)
    
    # 初始化字体
    config.init_fonts()
    
    return screen


def check_and_update_background():
    """
    检查并更新背景图像
    
    Returns:
        pygame.Surface: 背景图像Surface对象
    """
    try:
        # 创建动态背景
        background_surface = permission.create_dynamic_background()
    except Exception as e:
        logger.error(f"创建背景失败: {e}")
        # 创建默认黑色背景
        background_surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        background_surface.fill((0, 0, 0))
    
    return background_surface


def main():
    """主程序入口"""
    logger.info("启动海康R1设备监控程序（优化版本）")
    
    # 1. 初始化系统环境
    init_env()
    
    # 2. 初始化权限目录
    permission.init_permission_dirs()
    logger.info("权限目录初始化完成")
    
    # 3. 初始化Pygame
    screen = init_pygame()
    logger.info("Pygame和字体系统初始化完成")
    
    # 5. 初始化背景
    background_surface = check_and_update_background()
    logger.info("背景初始化完成")
    
    # 性能优化：初始化数据缓存
    last_process_update = 0
    last_background_update = 0
    cached_procs = []
    
    # 初始化鼠标事件处理器
    event_handler = mon_event.MouseEventHandler()
    logger.info(f"屏幕默认显示模式: {event_handler.config_screen_mode}")
    
    # 主循环
    running = True
    clock = pygame.time.Clock()
    
    logger.info("进入主循环（优化模式）")
    
    while running:
        current_time = time.time()
        
        # 处理事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                logger.info("收到退出事件")
                running = False
            else:
                # 处理鼠标事件（左键切换页面，右键开关屏幕，中键和滚轮调节亮度）
                event_handler.handle_mouse_event(event)
        
        # 屏幕关闭处理：跳过绘制，降低CPU占用
        if not event_handler.get_screen_status():
            screen.fill((0, 0, 0))
            pygame.display.flip()
            # 减少睡眠时间，确保事件能及时处理
            time.sleep(0.1)
            continue
        
        # 更新背景（仅在需要时更新）
        if current_time - last_background_update >= config.BG_CHANGE_INTERVAL:
            background_surface = check_and_update_background()
            last_background_update = current_time
        
        # 清屏
        screen.blit(background_surface, (0, 0))
        
        # 根据当前页面绘制不同内容
        current_page = event_handler.get_current_page()
        if current_page == 0:
            # 资源监控页面：绘制各监控模块
            # 获取进程信息（使用缓存机制）
            if current_time - last_process_update >= config.PROCESS_UPDATE_INTERVAL:
                procs = process.get_top_processes()
                cached_procs = procs
                last_process_update = current_time
            else:
                procs = cached_procs
            
            # 绘制各监控模块
            y_offset = config.GAP
            
            # CPU模块（使用缓存机制）
            cpu_rect = pygame.Rect(config.GAP, y_offset, config.CARD_WIDTH, config.CPU_HEIGHT)
            cpu.draw_cpu(screen, cpu_rect)
            y_offset += config.CPU_HEIGHT + config.GAP
            
            # 内存模块（使用缓存机制）
            mem_rect = pygame.Rect(config.GAP, y_offset, config.CARD_WIDTH, config.MEM_HEIGHT)
            memory.draw_memory(screen, mem_rect)
            y_offset += config.MEM_HEIGHT + config.GAP
            
            # 磁盘模块（使用缓存机制）
            disk_rect = pygame.Rect(config.GAP, y_offset, config.CARD_WIDTH, config.DISK_HEIGHT)
            disk.draw_disk(screen, disk_rect)
            y_offset += config.DISK_HEIGHT + config.GAP
            
            # 网络模块（使用缓存机制）
            net_rect = pygame.Rect(config.GAP, y_offset, config.CARD_WIDTH, config.NET_HEIGHT)
            network.draw_network(screen, net_rect)
            y_offset += config.NET_HEIGHT + config.GAP
            
            # 进程模块（使用缓存机制）
            proc_rect = pygame.Rect(config.GAP, y_offset, config.CARD_WIDTH, config.PROC_HEIGHT)
            process.draw_processes(screen, procs, proc_rect)
        else:
            # 天气页面：绘制时间、日期、天气、硬盘读写状态
            info_rect = pygame.Rect(config.GAP, config.GAP, config.CARD_WIDTH, config.SCREEN_HEIGHT - 2 * config.GAP)
            mon_weather.draw_weather_page(screen, info_rect)
        
        # 更新显示
        pygame.display.flip()
        
        # 控制帧率
        clock.tick(config.FRAME_RATE)
    
    # 清理资源
    logger.info("开始清理资源")
    pygame.quit()
    logger.info("程序正常退出")
    sys.exit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        pygame.quit()
        sys.exit(1)