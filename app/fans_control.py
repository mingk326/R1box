#!/usr/bin/env python3
# =============================================================================
# 海康R1设备风扇控制脚本
# 功能：使用固定的hwmon3路径控制CPU和HDD风扇 (pwm2/HDD, pwm3/CPU)
# 版本：1.1.15
# 作者：山归山
# =============================================================================

import os
import sys
import time
import logging
import subprocess
import re
from pathlib import Path

# =============================================================================
# 日志配置
# =============================================================================
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# 风扇控制器类
# 功能：管理CPU和HDD风扇的自动/手动控制，支持温度监控和PWM调节
# =============================================================================
class R1FanController:
    """
    海康R1设备风扇控制器
    
    功能特性：
    - 支持自动温度控制模式
    - 支持5档手动控制模式
    - 兼容飞牛OS环境变量配置
    - 使用固定hwmon3硬件路径
    """
    
    def __init__(self):
        """
        初始化风扇控制器
        
        功能：设置硬件路径、风扇配置参数、初始化控制环境
        """
        # 硬件路径配置
        self.hwmon_path = Path('/sys/class/hwmon/hwmon3/')
        
        # 风扇控制路径映射
        self.fan_pwm_paths = {
            'hdd': self.hwmon_path / 'pwm2',      # HDD风扇 -> pwm2
            'cpu': self.hwmon_path / 'pwm3'       # CPU风扇 -> pwm3
        }
        
        # 风扇使能路径映射
        self.fan_enable_paths = {
            'hdd': self.hwmon_path / 'pwm2_enable',  # HDD风扇使能
            'cpu': self.hwmon_path / 'pwm3_enable'   # CPU风扇使能
        }
        
        # 风扇温度控制配置
        self.fan_configs = {
            'cpu': {
                'min_temp': 35,   # 最低温度阈值 (°C)
                'max_temp': 75,   # 最高温度阈值 (°C)
                'min_speed': 50,  # 最低PWM值
                'max_speed': 255  # 最高PWM值
            },
            'hdd': {
                'min_temp': 30,   # 最低温度阈值 (°C)
                'max_temp': 45,   # 最高温度阈值 (°C)
                'min_speed': 50,  # 最低PWM值
                'max_speed': 255, # 最高PWM值
                'cpu_full': 45    # 当CPU满速时，HDD风扇额外增加的转速百分比
            }
        }

        # 手动模式档位配置
        self.manual_fan_levels = {
            1: 25,   # 第1档 (~10% 速度)
            2: 64,   # 第2档 (~25% 速度)
            3: 128,  # 第3档 (~50% 速度)
            4: 192,  # 第4档 (~75% 速度)
            5: 255   # 第5档 (~100% 速度)
        }
        
        # 运行模式标识
        self.auto_mode_enabled = True
        
        # 手动档位设置
        self.cpu_manual_level = 2  # CPU风扇默认档位
        self.hdd_manual_level = 1  # HDD风扇默认档位
        
        # 初始化控制器
        self.initialize()

    def initialize(self):
        """
        初始化风扇控制器
        
        功能：检查硬件路径、设置风扇模式、准备控制环境
        返回：
            bool: 初始化是否成功
        """
        logger.info("开始初始化R1风扇控制器 (使用固定hwmon3路径)")
        
        # 检查硬件路径是否存在
        hdd_pwm_exists = self.fan_pwm_paths['hdd'].exists()
        cpu_pwm_exists = self.fan_pwm_paths['cpu'].exists()
        hdd_enable_exists = self.fan_enable_paths['hdd'].exists()
        cpu_enable_exists = self.fan_enable_paths['cpu'].exists()
        
        if not all([hdd_pwm_exists, cpu_pwm_exists, hdd_enable_exists, cpu_enable_exists]):
            logger.error("硬件路径不存在，请确认监控路径是否正确")
            logger.error(f"HDD PWM路径: {hdd_pwm_exists}, CPU PWM路径: {cpu_pwm_exists}")
            logger.error(f"HDD使能路径: {hdd_enable_exists}, CPU使能路径: {cpu_enable_exists}")
            return False
        else:
            logger.info("硬件监控路径检查通过")
        
        # 设置风扇为手动控制模式
        self.set_fan_manual_mode()
        
        logger.info("风扇控制器初始化完成")
        return True

    def set_fan_manual_mode(self):
        """
        设置风扇为手动模式 (enable = 1)
        功能：将HDD和CPU风扇控制权交给软件，启用PWM控制
        """
        logger.info("设置风扇为手动模式...")
        
        try:
            # 设置HDD风扇为手动模式 (pwm2_enable = 1)
            hdd_enable_path = self.fan_enable_paths['hdd']
            if hdd_enable_path.exists():
                with open(hdd_enable_path, 'w') as f:
                    f.write('1')  # 手动模式
                logger.info(f"成功设置HDD风扇为手动模式: {hdd_enable_path}")
            else:
                logger.warning(f"HDD风扇enable文件不存在: {hdd_enable_path}")
            
            # 设置CPU风扇为手动模式 (pwm3_enable = 1)  
            cpu_enable_path = self.fan_enable_paths['cpu']
            if cpu_enable_path.exists():
                with open(cpu_enable_path, 'w') as f:
                    f.write('1')  # 手动模式
                logger.info(f"成功设置CPU风扇为手动模式: {cpu_enable_path}")
            else:
                logger.warning(f"CPU风扇enable文件不存在: {cpu_enable_path}")
                
        except PermissionError:
            logger.error("权限不足，无法设置风扇enable模式，请确保以root权限运行")
        except Exception as e:
            logger.error(f"设置风扇enable模式时出错: {e}")

    def find_cpu_temperature(self):
        """
        查找CPU温度
        功能：扫描系统中可用的CPU温度传感器并返回当前温度值
        返回：float - CPU温度（摄氏度）
        """
        try:
            # 首选方法：直接从thermal zone获取CPU温度（参考提供的命令行代码）
            # 尝试常见CPU温度区域
            for zone_num in [0, 1, 2, 3, 4, 5]:  # 尝试多个可能的thermal zone
                temp_file = Path(f'/sys/class/thermal/thermal_zone{zone_num}/temp')
                if temp_file.exists():
                    type_file = Path(f'/sys/class/thermal/thermal_zone{zone_num}/type')
                    if type_file.exists():
                        with open(type_file, 'r') as f:
                            zone_type = f.read().strip().lower()
                            # 检查是否为CPU相关温度区域
                            if any(cpu_type in zone_type for cpu_type in ['cpu', 'core', 'package']):
                                with open(temp_file, 'r') as f:
                                    temp_raw = f.read().strip()
                                    temp = int(temp_raw) / 1000.0  # 转换为摄氏度
                                    logger.debug(f"CPU温度: {temp}°C from thermal_zone{zone_num} ({zone_type})")
                                    return temp
            
            # 备用方法：遍历hwmon目录查找CPU温度传感器
            hwmon_path = Path('/sys/class/hwmon/')
            cpu_temps = []
            
            for hwmon_dir in hwmon_path.glob('hwmon*'):
                if hwmon_dir.is_dir():
                    name_file = hwmon_dir / 'name'
                    if name_file.exists():
                        with open(name_file, 'r') as f:
                            name = f.read().strip()
                            # 查找CPU相关的温度传感器
                            if 'coretemp' in name or 'k10temp' in name or 'it86' in name or 'acpi' in name:
                                for temp_input in hwmon_dir.glob('temp*_input'):
                                    try:
                                        with open(temp_input, 'r') as f:
                                            temp = int(f.read().strip()) / 1000.0  # 转换为摄氏度
                                            logger.debug(f"CPU温度: {temp}°C from {temp_input}")
                                            cpu_temps.append(temp)
                                    except (ValueError, IOError):
                                        continue
                            
            # 如果找到了多个CPU温度传感器，返回平均值或第一个值
            if cpu_temps:
                avg_temp = sum(cpu_temps) / len(cpu_temps)
                logger.debug(f"CPU平均温度: {avg_temp}°C")
                return avg_temp
                                        
        except Exception as e:
            logger.error(f"查找CPU温度时出错: {e}")
        
        logger.warning("未能获取CPU温度，使用默认值")
        return 30.0  # 默认温度

    def find_hdd_temperature(self):
        """
        查找HDD温度 - 使用smartctl的-n参数避免唤醒休眠硬盘
        功能：扫描系统中可用的HDD温度传感器并返回当前温度值
        返回：float - HDD温度（摄氏度）
        """
        try:
            # 使用smartctl获取所有磁盘的温度，兼容单盘和RAID组合
            hdd_temps = []
            
            # 首先获取系统中所有磁盘设备，只考虑旋转磁盘（HDD）
            result = subprocess.run(['lsblk', '-r', '-o', 'NAME,TYPE,ROTA'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logger.debug(f"lsblk 输出: {result.stdout}")
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # 跳过标题行
                    parts = line.split()
                    if len(parts) >= 3:  # NAME, TYPE, ROTA
                        name, type_, rota = parts[0], parts[1], parts[2]
                        logger.debug(f"检测到设备: {name}, 类型: {type_}, ROTA: {rota}")
                        # 只检查磁盘类型且是旋转磁盘（HDD），排除SSD和NVMe
                        if type_.lower() in ['disk'] and rota.lower() == '1':  # ROTA为1表示是旋转磁盘(HDD)
                            device_path = f'/dev/{name}'
                            logger.info(f"检测HDD设备: {device_path}")
                            # 验证设备是否真实存在
                            if os.path.exists(device_path):
                                # 使用smartctl的-n参数避免唤醒休眠的硬盘
                                try:
                                    # 使用-n standby参数，如果硬盘在休眠状态则不唤醒
                                    smart_result = subprocess.run(
                                        ['smartctl', '-a', '-n', 'standby', device_path], 
                                        capture_output=True, text=True, timeout=5)
                                    if smart_result.returncode == 0:
                                        # 检查是否设备处于休眠状态
                                        if 'Device is in STANDBY mode' in smart_result.stdout or 'is sleeping' in smart_result.stdout:
                                            logger.debug(f"设备 {device_path} 处于休眠状态，跳过温度读取")
                                            continue
                                        
                                        logger.debug(f"smartctl输出({device_path}): {smart_result.stdout[:500]}...")  # 只记录前500字符
                                        # 查找温度信息，优先查找Temperature_Celsius
                                        temp_line = None
                                        for line in smart_result.stdout.split('\n'):
                                            if 'Temperature_Celsius' in line:
                                                temp_line = line
                                                break
                                        
                                        # 如果没找到Temperature_Celsius，尝试其他温度相关字段
                                        if not temp_line:
                                            for line in smart_result.stdout.split('\n'):
                                                if 'Temperature:' in line or '194 Temperature' in line:
                                                    temp_line = line
                                                    break
                                        
                                        if temp_line:
                                            logger.debug(f"找到温度行: {temp_line}")
                                            # 提取温度值
                                            temp_match = re.search(r'(\d+)\s*(?:°C|Celsius|C)', temp_line)
                                            if temp_match:
                                                temp = float(temp_match.group(1))
                                                logger.info(f"HDD温度: {temp}°C from {device_path}")
                                                hdd_temps.append(temp)
                                            else:
                                                # 如果正则表达式未匹配，直接按SMART数据行格式提取第10个字段
                                                parts = temp_line.split()
                                                if len(parts) >= 10:  # 确保有足够的部分
                                                    temp_field = parts[9]  # 第10个字段（索引为9）
                                                    # 提取字段中的数字
                                                    temp_numbers = re.findall(r'\d+', temp_field)
                                                    if temp_numbers:
                                                        temp = float(temp_numbers[0])
                                                        logger.info(f"HDD温度: {temp}°C from {device_path}")
                                                        hdd_temps.append(temp)
                                                
                                except subprocess.TimeoutExpired:
                                    logger.warning(f"获取 {device_path} 温度超时")
                                except Exception as e:
                                    logger.error(f"无法获取 {device_path} 温度: {e}")
            
            # 如果通过smartctl找到了温度，返回最高温度
            if hdd_temps:
                max_temp = max(hdd_temps)
                logger.info(f"最高HDD温度: {max_temp}°C (从 {len(hdd_temps)} 个磁盘中)")
                return max_temp
            else:
                logger.debug("未找到任何活动的HDD温度数据，使用默认值")
                
        except Exception as e:
            logger.error(f"查找HDD温度时出错: {e}")
        
        logger.debug("未能获取HDD温度，使用默认值")
        return 25.0  # 默认温度

    def load_fan_config(self):
        """
        从环境变量加载风扇设置
        功能：读取自动/手动模式设置、风扇档位、温度阈值等配置参数
        """
        try:
            # 从环境变量获取自动模式开关状态
            auto_mode = os.environ.get('config_fan_auto_mode', 'true').lower()
            self.auto_mode_enabled = auto_mode in ['true', '1', 'yes', 'on']
            logger.info(f"风扇自动模式: {'启用' if self.auto_mode_enabled else '禁用'}")
            
            if not self.auto_mode_enabled:
                # 手动模式：读取CPU和HDD风扇的手动档位
                cpu_level = os.environ.get('config_cpu_fan_level')
                hdd_level = os.environ.get('config_hdd_fan_level')
                
                if cpu_level is not None:
                    try:
                        level = int(cpu_level)
                        if 1 <= level <= 5:  # 1-5 表示5个档位
                            self.cpu_manual_level = level
                            logger.info(f"设置CPU风扇手动档位: {level}")
                        else:
                            logger.warning(f"CPU风扇档位超出范围: {level}, 使用默认值: {self.cpu_manual_level}")
                    except ValueError:
                        logger.warning(f"CPU风扇档位不是有效数字: {cpu_level}, 使用默认值: {self.cpu_manual_level}")
                
                if hdd_level is not None:
                    try:
                        level = int(hdd_level)
                        if 1 <= level <= 5:  # 1-5 表示5个档位
                            self.hdd_manual_level = level
                            logger.info(f"设置HDD风扇手动档位: {level}")
                        else:
                            logger.warning(f"HDD风扇档位超出范围: {level}, 使用默认值: {self.hdd_manual_level}")
                    except ValueError:
                        logger.warning(f"HDD风扇档位不是有效数字: {hdd_level}, 使用默认值: {self.hdd_manual_level}")
            else:
                # 自动模式：从环境变量获取CPU风扇配置
                cpu_min_temp = os.environ.get('config_cpu_fan_min_temp')
                cpu_max_temp = os.environ.get('config_cpu_fan_max_temp')
                cpu_min_speed = os.environ.get('config_cpu_fan_min_speed')
                cpu_max_speed = os.environ.get('config_cpu_fan_max_speed')
                
                if cpu_min_temp is not None:
                    self.fan_configs['cpu']['min_temp'] = int(cpu_min_temp)
                    logger.info(f"更新CPU风扇配置: min_temp = {cpu_min_temp}")
                if cpu_max_temp is not None:
                    self.fan_configs['cpu']['max_temp'] = int(cpu_max_temp)
                    logger.info(f"更新CPU风扇配置: max_temp = {cpu_max_temp}")
                if cpu_min_speed is not None:
                    self.fan_configs['cpu']['min_speed'] = int(cpu_min_speed)
                    logger.info(f"更新CPU风扇配置: min_speed = {cpu_min_speed}")
                if cpu_max_speed is not None:
                    self.fan_configs['cpu']['max_speed'] = int(cpu_max_speed)
                    logger.info(f"更新CPU风扇配置: max_speed = {cpu_max_speed}")
                    
                # 从环境变量获取HDD风扇配置
                hdd_min_temp = os.environ.get('config_hdd_fan_min_temp')
                hdd_max_temp = os.environ.get('config_hdd_fan_max_temp')
                hdd_min_speed = os.environ.get('config_hdd_fan_min_speed')
                hdd_max_speed = os.environ.get('config_hdd_fan_max_speed')
                
                if hdd_min_temp is not None:
                    self.fan_configs['hdd']['min_temp'] = int(hdd_min_temp)
                    logger.info(f"更新HDD风扇配置: min_temp = {hdd_min_temp}")
                if hdd_max_temp is not None:
                    self.fan_configs['hdd']['max_temp'] = int(hdd_max_temp)
                    logger.info(f"更新HDD风扇配置: max_temp = {hdd_max_temp}")
                if hdd_min_speed is not None:
                    self.fan_configs['hdd']['min_speed'] = int(hdd_min_speed)
                    logger.info(f"更新HDD风扇配置: min_speed = {hdd_min_speed}")
                if hdd_max_speed is not None:
                    self.fan_configs['hdd']['max_speed'] = int(hdd_max_speed)
                    logger.info(f"更新HDD风扇配置: max_speed = {hdd_max_speed}")
                
        except Exception as e:
            logger.error(f"加载风扇配置时出错: {e}")

    def calculate_fan_speed(self, temperature, fan_type='cpu'):
        """
        根据温度计算风扇速度
        功能：使用线性插值算法计算适合当前温度的风扇PWM值
        参数：
            temperature (float): 当前温度（摄氏度）
            fan_type (str): 风扇类型 ('cpu' 或 'hdd')
        返回：
            int: 计算得到的风扇PWM值 (25-255)
        """
        config = self.fan_configs[fan_type]
        min_temp = config['min_temp']
        max_temp = config['max_temp']
        min_speed = config['min_speed']
        max_speed = config['max_speed']
        
        if temperature <= min_temp:
            return max(min_speed, 25)  # 确保至少25的PWM值，避免风扇停转
        elif temperature >= max_temp:
            return max_speed
        else:
            # 线性插值计算风扇速度
            ratio = (temperature - min_temp) / (max_temp - min_temp)
            speed = int(min_speed + ratio * (max_speed - min_speed))
            # 确保速度在合理范围内，且不低于安全最小值
            return max(max(min_speed, 25), min(speed, max_speed))

    def set_cpu_fan_speed(self, speed):
        """
        设置CPU风扇速度 (使用固定路径: pwm3)
        功能：将计算得到的PWM值写入CPU风扇控制接口
        参数：
            speed (int): 风扇PWM值 (25-255)
        返回：
            bool: 设置是否成功
        """
        # 确保速度不低于最小安全值
        speed = max(speed, 25)
        logger.debug(f"尝试设置CPU风扇速度 (pwm3): {speed}")
        
        try:
            with open(self.fan_pwm_paths['cpu'], 'w') as f:
                f.write(str(speed))
            logger.info(f"成功设置CPU风扇速度 (pwm3): {speed}")
            return True
        except PermissionError:
            logger.error("权限不足，无法设置CPU风扇速度，请确保以root权限运行")
            return False
        except Exception as e:
            logger.error(f"设置CPU风扇速度时出错: {e}")
            return False

    def set_hdd_fan_speed(self, speed):
        """
        设置HDD风扇速度 (使用固定路径: pwm2)
        功能：将计算得到的PWM值写入HDD风扇控制接口
        参数：
            speed (int): 风扇PWM值 (25-255)
        返回：
            bool: 设置是否成功
        """
        # 确保速度不低于最小安全值
        speed = max(speed, 25)
        logger.debug(f"尝试设置HDD风扇速度 (pwm2): {speed}")
        
        try:
            with open(self.fan_pwm_paths['hdd'], 'w') as f:
                f.write(str(speed))
            logger.info(f"成功设置HDD风扇速度 (pwm2): {speed}")
            return True
        except PermissionError:
            logger.error("权限不足，无法设置HDD风扇速度，请确保以root权限运行")
            return False
        except Exception as e:
            logger.error(f"设置HDD风扇速度时出错: {e}")
            return False

    def set_initial_fan_speeds(self):
        """
        设置初始风扇速度
        功能：在程序启动时根据当前配置设置风扇的初始速度
        """
        logger.info("设置初始风扇速度...")
        
        # 加载配置
        self.load_fan_config()
        
        if self.auto_mode_enabled:
            # 自动模式：根据温度设置初始速度
            # 获取当前温度
            cpu_temp = self.find_cpu_temperature()
            hdd_temp = self.find_hdd_temperature()
            
            # 计算初始风扇速度
            cpu_speed = self.calculate_fan_speed(cpu_temp, fan_type='cpu')
            hdd_speed = self.calculate_fan_speed(hdd_temp, fan_type='hdd')
            
            logger.info(f"自动模式初始速度 - CPU温度: {cpu_temp:.1f}°C, 速度: {cpu_speed} | "
                       f"HDD温度: {hdd_temp:.1f}°C, 速度: {hdd_speed}")
        else:
            # 手动模式：使用预设的档位
            cpu_speed = self.manual_fan_levels[self.cpu_manual_level]
            hdd_speed = self.manual_fan_levels[self.hdd_manual_level]
            
            logger.info(f"手动模式初始速度 - CPU档位: {self.cpu_manual_level}, 速度: {cpu_speed} | "
                       f"HDD档位: {self.hdd_manual_level}, 速度: {hdd_speed}")
        
        # 设置风扇速度
        self.set_cpu_fan_speed(cpu_speed)
        self.set_hdd_fan_speed(hdd_speed)
        
        logger.info(f"初始风扇速度设置完成 - CPU: {cpu_speed}, HDD: {hdd_speed}")

    def run(self):
        """
        主循环 - 持续监控和调整风扇速度
        功能：实现风扇的持续监控和温度控制，每秒更新一次风扇速度
        """
        logger.info("启动风扇控制主循环")
        
        config_reload_counter = 0
        config_reload_interval = 300  # 每300次循环（约5分钟）重新加载配置
        
        while True:
            try:
                # 定期重新加载配置
                if config_reload_counter % config_reload_interval == 0:
                    logger.debug("重新加载风扇配置")
                    self.load_fan_config()
                    config_reload_counter = 0
                
                logger.debug(f"当前模式: {'自动' if self.auto_mode_enabled else '手动'}")
                
                if self.auto_mode_enabled:
                    # 自动模式：根据温度控制风扇
                    # 获取当前温度
                    logger.debug("获取当前温度...")
                    cpu_temp = self.find_cpu_temperature()
                    hdd_temp = self.find_hdd_temperature()
                    
                    logger.debug(f"获取到温度 - CPU: {cpu_temp:.1f}°C, HDD: {hdd_temp:.1f}°C")
                    
                    # 计算风扇速度
                    cpu_speed = self.calculate_fan_speed(cpu_temp, fan_type='cpu')
                    hdd_speed = self.calculate_fan_speed(hdd_temp, fan_type='hdd')
                    
                    # 检查CPU是否达到满速（温度达到或超过max_temp）
                    if cpu_temp >= self.fan_configs['cpu']['max_temp']:
                        # CPU满速时，为HDD风扇增加25%的转速补偿
                        hdd_compensation = int(hdd_speed * self.fan_configs['hdd']['cpu_full'] / 100)
                        hdd_speed_with_compensation = hdd_speed + hdd_compensation
                        # 确保不超过HDD风扇的最大速度
                        hdd_speed = min(hdd_speed_with_compensation, self.fan_configs['hdd']['max_speed'])
                        logger.debug(f"CPU满速，HDD风扇增加补偿 - 原速度: {hdd_speed - hdd_compensation}, 补偿: {hdd_compensation}, 最终速度: {hdd_speed}")
                    
                    logger.debug(f"计算得到速度 - CPU: {cpu_speed}, HDD: {hdd_speed}")
                    
                    # 记录日志
                    logger.info(f"自动模式 - CPU温度: {cpu_temp:.1f}°C, 速度: {cpu_speed} | "
                               f"HDD温度: {hdd_temp:.1f}°C, 速度: {hdd_speed}")
                else:
                    # 手动模式：使用预设的档位
                    cpu_speed = self.manual_fan_levels[self.cpu_manual_level]
                    hdd_speed = self.manual_fan_levels[self.hdd_manual_level]
                    
                    # 记录日志
                    logger.info(f"手动模式 - CPU档位: {self.cpu_manual_level}, 速度: {cpu_speed} | "
                               f"HDD档位: {self.hdd_manual_level}, 速度: {hdd_speed}")
                
                # 设置风扇速度
                logger.debug(f"尝试设置风扇速度 - CPU: {cpu_speed}, HDD: {hdd_speed}")
                cpu_success = self.set_cpu_fan_speed(cpu_speed)
                hdd_success = self.set_hdd_fan_speed(hdd_speed)
                
                # 记录设置状态
                logger.info(f"设置状态 - CPU: {'成功' if cpu_success else '失败'}, "
                           f"HDD: {'成功' if hdd_success else '失败'}")
                
                config_reload_counter += 1
                
                # 每隔1秒更新一次，以实现更及时的温度控制
                logger.debug("等待1秒后继续...")
                time.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("收到中断信号，退出风扇控制")
                break
            except Exception as e:
                logger.error(f"风扇控制主循环出错: {e}")
                time.sleep(5)  # 出错后稍作延迟再重试


def main():
    """
    主函数
    功能：初始化并启动R1风扇控制器
    """
    logger.info("R1风扇控制器启动")
    
    try:
        controller = R1FanController()
        controller.set_initial_fan_speeds()  # 设置初始风扇速度
        controller.run()
    except Exception as e:
        logger.error(f"风扇控制器启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()