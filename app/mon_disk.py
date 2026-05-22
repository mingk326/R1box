#!/usr/bin/env python3

import logging
import time
import os
import re
import psutil
import pygame
import subprocess
from typing import Dict, List, Optional, Tuple, Any

import mon_config
from mon_config import (
    DISK_DISPLAY_COUNT, ALLOWED_MOUNT_PREFIXES,
    COLORS, BAR_RADIUS
)
from mon_utils import (
    draw_rounded_rect, 
    draw_text_centered_with_shadow,
    draw_vertical_title,
    draw_card,
    run_command_with_timeout,
    cache_result
)

logger = logging.getLogger('mon_disk')


@cache_result(mon_config.DISK_UPDATE_INTERVAL)
def get_all_volumes() -> List[Dict[str, Any]]:
    """
    获取所有vol卷信息
    
    功能：获取所有挂载点的基本信息（使用率、容量等）
    返回值：
        List[Dict]: vol卷信息列表
    """
    
    volumes = []
    
    try:
        logger.debug("开始获取所有vol卷基本信息...")
        partitions = psutil.disk_partitions()
        logger.debug(f"psutil检测到 {len(partitions)} 个分区")
        
        for partition in partitions:
            # 过滤挂载点
            if not any(partition.mountpoint.startswith(prefix) for prefix in ALLOWED_MOUNT_PREFIXES):
                logger.debug(f"跳过挂载点: {partition.mountpoint}")
                continue
            
            try:
                # 获取磁盘使用情况
                usage = psutil.disk_usage(partition.mountpoint)
                
                # 计算使用率
                percent = round(usage.percent, 1)
                
                # 格式化大小
                total_gb = round(usage.total / (1024**3), 1)
                used_gb = round(usage.used / (1024**3), 1)
                unit = "GB"
                
                # 大容量自动转换为TB
                if total_gb >= 1024:
                    total_gb = round(total_gb / 1024, 1)
                    used_gb = round(used_gb / 1024, 1)
                    unit = "TB"
                
                volume_info = {
                    "mountpoint": partition.mountpoint,
                    "device": partition.device,
                    "percent": percent,
                    "used": used_gb,
                    "total": total_gb,
                    "unit": unit,
                    "vol_name": partition.mountpoint.split("/")[-1] if "/" in partition.mountpoint else partition.mountpoint
                }
                
                volumes.append(volume_info)
                logger.debug(f"检测到vol卷: {volume_info}")
                
            except (PermissionError, OSError):
                logger.warning(f"无法访问挂载点: {partition.mountpoint}")
                continue
        
        # 按vol_name排序
        volumes.sort(key=lambda x: x["vol_name"])
        volumes = volumes[:DISK_DISPLAY_COUNT]
        logger.debug(f"总共检测到 {len(volumes)} 个vol卷")
        
    except Exception as e:
        logger.error(f"获取vol卷信息失败: {e}")
        
    return volumes


def get_physical_devices() -> Dict[str, Dict[str, Any]]:
    """
    获取所有物理磁盘的详细信息
    
    功能：获取所有sd*, nvme*等物理磁盘的温度、类型、状态等信息
    返回值：
        Dict: 物理磁盘信息字典，key为设备名（如sda, nvme0n1）
    """
    
    devices_info = {}
    
    try:
        logger.debug("开始获取所有物理磁盘详细信息...")
        
        # 获取所有块设备
        result = subprocess.run(["lsblk", "-d", "-o", "NAME,TYPE"], 
                               capture_output=True, text=True, timeout=2)
        
        if result.returncode != 0:
            logger.error("lsblk命令执行失败")
            return {}
        
        logger.debug(f"lsblk命令输出:\n{result.stdout}")
        
        # 解析物理设备（disk类型）
        disk_devices = []
        for line in result.stdout.split('\n'):
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "disk":
                device_name = parts[0]
                
                # 过滤掉loop和mmcblk设备
                if device_name.startswith('loop') or device_name.startswith('mmcblk'):
                    logger.debug(f"过滤设备: {device_name}")
                    continue
                
                disk_devices.append(device_name)
        
        # 关键修复：串行获取温度，避免并发问题
        for idx, device_name in enumerate(disk_devices):
            device_path = f"/dev/{device_name}"
            logger.debug(f"开始检测设备: {device_name}")
            
            # 添加小延迟，避免硬件访问冲突
            if idx > 0:
                time.sleep(0.1)
            
            # 获取设备详细信息
            temp = read_single_temp(device_path)
            device_type = get_device_type_from_smartctl(device_path)
            
            device_info = {
                "path": device_path,
                "temp": temp,
                "device_type": device_type,
                "is_raid_member": False,
                "raid_group": None
            }
            
            devices_info[device_name] = device_info
            logger.debug(f"检测到物理设备: {device_name} - 温度: {temp}, 类型: {device_type}")
        
        logger.debug(f"总共检测到 {len(devices_info)} 个物理设备")
        
        # 记录RAID成员信息
        raid_members = [name for name, info in devices_info.items() if info["is_raid_member"]]
        logger.debug(f"检测到 {len(raid_members)} 个RAID成员设备: {raid_members}")
        
    except Exception as e:
        logger.error(f"获取物理磁盘信息失败: {e}")
    
    return devices_info


def map_volumes_to_devices(volumes: List[Dict[str, Any]], 
                          devices_info: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将vol卷映射到物理磁盘
    
    功能：确定每个vol卷对应的物理磁盘信息
    参数：
        volumes: vol卷信息列表
        devices_info: 物理磁盘信息字典
    返回值：
        List[Dict]: 包含完整磁盘信息的vol卷列表
    """
    import platform
    
    if platform.system() != "Linux":
        logger.debug("非Linux系统，跳过vol卷映射")
        return volumes
    
    enhanced_volumes = []
    
    try:
        logger.debug("开始将vol卷映射到物理磁盘...")
        logger.debug(f"需要映射的vol卷数量: {len(volumes)}")
        logger.debug(f"可用的物理设备数量: {len(devices_info)}")
        
        for volume in volumes:
            mountpoint = volume["mountpoint"]
            vol_name = volume["vol_name"]
            
            logger.debug(f"处理vol卷: {vol_name} (挂载点: {mountpoint})")
            
            # 获取挂载点对应的设备
            result = subprocess.run(["findmnt", "-n", "-o", "SOURCE", mountpoint], 
                                   capture_output=True, text=True, timeout=2)
            
            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"无法获取挂载点 {mountpoint} 对应的设备信息")
                volume.update(get_default_volume_info())
                enhanced_volumes.append(volume)
                continue
            
            source_device = result.stdout.strip()
            logger.debug(f"挂载点 {mountpoint} 对应的设备: {source_device}")
            
            # 解析设备名
            device_match = re.search(r'/dev/(\S+)', source_device)
            if not device_match:
                logger.warning(f"无法解析设备名: {source_device}")
                volume.update(get_default_volume_info())
                enhanced_volumes.append(volume)
                continue
            
            device_name = device_match.group(1)
            logger.debug(f"解析出的设备名: {device_name}")
            
            # 检查是否为RAID设备
            if device_name.startswith('md'):
                logger.debug(f"检测到RAID设备: {device_name}")
                # RAID设备
                raid_info = analyze_raid_volume(device_name, devices_info)
                volume.update(raid_info)
                logger.debug(f"RAID卷分析结果: {raid_info}")
            elif device_name.startswith('mapper/'):
                logger.debug(f"检测到LVM逻辑卷: {device_name}")
                # LVM逻辑卷，需要特殊处理
                lvm_info = analyze_lvm_volume(device_name, devices_info)
                volume.update(lvm_info)
                logger.debug(f"LVM卷分析结果: {lvm_info}")
            else:
                logger.debug(f"检测到单盘设备: {device_name}")
                # 单盘设备
                single_info = analyze_single_volume(device_name, devices_info)
                volume.update(single_info)
                logger.debug(f"单盘卷分析结果: {single_info}")
            
            enhanced_volumes.append(volume)
            logger.debug(f"vol卷 {vol_name} 映射完成，最终信息: {volume}")
        
        logger.debug(f"vol卷映射完成，总共处理 {len(enhanced_volumes)} 个vol卷")
        
    except Exception as e:
        logger.error(f"映射vol卷到设备失败: {e}")
        # 出错时返回原始volumes
        enhanced_volumes = volumes
    
    return enhanced_volumes


def analyze_raid_volume(raid_device: str, devices_info: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """分析RAID卷信息
    
    功能：获取RAID卷的详细信息，包括成员设备、温度、类型等
    参数：
        raid_device: RAID设备名（如md0）
        devices_info: 物理磁盘信息字典
    返回值：
        Dict: RAID卷的详细信息
    """
    try:
        logger.debug(f"开始分析RAID卷: {raid_device}")
        
        # 获取RAID组成员
        result = subprocess.run(["mdadm", "--detail", f"/dev/{raid_device}"], 
                               capture_output=True, text=True, timeout=5)
        
        if result.returncode != 0:
            logger.warning(f"无法获取RAID卷 {raid_device} 的详细信息")
            return get_default_volume_info()
        
        raid_members = []
        sleeping_count = 0
        max_temp = None
        device_types = set()
        
        logger.debug(f"RAID卷 {raid_device} 的详细信息:\n{result.stdout}")
        
        # 解析RAID组成员
        for line in result.stdout.split('\n'):
            if 'active sync' in line or 'spare' in line:
                # 提取设备名
                member_match = re.search(r'/dev/(\S+)', line)
                if member_match:
                    member_with_partition = member_match.group(1)
                    
                    # 提取基础设备名（去掉分区号）
                    base_device = re.sub(r'(p\d+)?$', '', member_with_partition)
                    
                    logger.debug(f"找到RAID成员设备: {member_with_partition} -> 基础设备名: {base_device}")
                    
                    # 匹配物理设备
                    member_found = False
                    for device_name, device_info in devices_info.items():
                        if device_name == base_device:
                            raid_members.append(device_info)
                            member_found = True
                            
                            # 统计休眠设备
                            if device_info.get('is_sleeping', False):
                                sleeping_count += 1
                            
                            # 获取最高温度
                            temp = device_info.get('temp')
                            if temp is not None:
                                if max_temp is None or temp > max_temp:
                                    max_temp = temp
                            
                            # 收集设备类型
                            device_type = device_info.get('device_type', '未知')
                            device_types.add(device_type)
                            
                            logger.debug(f"匹配到物理设备: {device_name}, 类型: {device_type}, 温度: {temp}, 休眠: {device_info.get('is_sleeping', False)}")
                            break
                    
                    if not member_found:
                        logger.warning(f"未找到RAID成员设备 {base_device} 对应的物理设备信息")
        
        logger.debug(f"RAID卷 {raid_device} 分析结果:")
        logger.debug(f"- 成员设备数量: {len(raid_members)}")
        logger.debug(f"- 休眠设备数量: {sleeping_count}")
        logger.debug(f"- 最高温度: {max_temp}")
        logger.debug(f"- 设备类型集合: {device_types}")
        
        # 确定设备类型
        if len(device_types) == 1:
            device_type = list(device_types)[0]
            logger.debug(f"单一设备类型: {device_type}")
        else:
            device_type = "混合RAID"
            logger.debug(f"混合设备类型: {device_types} -> 显示为 '混合RAID'")
        
        all_members_sleeping = (sleeping_count == len(raid_members)) and len(raid_members) > 0
        logger.debug(f"所有成员休眠: {all_members_sleeping}")
        
        raid_info = {
            "temp": max_temp,
            "device_type": device_type,
            "is_raid": True,
            "raid_members": raid_members,
            "all_members_sleeping": all_members_sleeping
        }
        
        logger.debug(f"RAID卷 {raid_device} 最终信息: {raid_info}")
        
        return raid_info
        
    except Exception as e:
        logger.error(f"分析RAID卷 {raid_device} 失败: {e}")
        return get_default_volume_info()


def analyze_lvm_volume(lvm_device: str, devices_info: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    分析LVM逻辑卷信息 - 简化版本
    
    功能：使用简单的lsblk命令直接获取LVM卷的底层设备信息
    参数：
        lvm_device: LVM设备名（如mapper/trim_...）
        devices_info: 物理磁盘信息字典
    返回值：
        Dict: LVM卷的详细信息
    """
    try:
        logger.debug(f"开始分析LVM逻辑卷: {lvm_device}")
        
        # 提取LVM卷名（去掉mapper/前缀）
        lvm_volume_name = lvm_device.replace('mapper/', '')
        logger.debug(f"提取LVM卷名: {lvm_volume_name}")
        
        # 简化方法：直接使用lsblk获取设备层次结构
        result = subprocess.run(["lsblk", "-s", "-o", "NAME,TYPE", 
                               f"/dev/mapper/{lvm_volume_name}"], capture_output=True, text=True, timeout=3)
        
        if result.returncode != 0:
            logger.warning(f"lsblk -s 命令失败，使用直接分析方法")
            return analyze_lvm_directly(lvm_device, devices_info)
        
        logger.debug(f"lsblk -s 命令输出:\n{result.stdout}")
        
        # 解析lsblk -s输出，提取底层物理设备
        physical_devices = []
        
        # lsblk -s输出是树形结构，需要处理Unicode缩进字符
        for line in result.stdout.strip().split('\n'):
            if not line.strip() or 'TYPE' in line:
                continue  # 跳过空行和标题行
            
            # 移除树形结构的Unicode字符（└─, ├─等）
            cleaned_line = line.replace('└─', '').replace('├─', '').replace('│', '').strip()
            
            # 解析设备名和类型
            parts = cleaned_line.split()
            if len(parts) >= 2:
                device_name = parts[0]
                device_type = parts[1]
                
                # 只关注disk类型的设备（物理磁盘）
                if device_type == 'disk':
                    # 过滤掉不需要的设备类型
                    if (device_name.startswith(('sd', 'nvme', 'hd')) and 
                        not device_name.startswith(('loop', 'mmcblk'))):
                        physical_devices.append(device_name)
        
        # 去重
        physical_devices = list(set(physical_devices))
        
        if not physical_devices:
            logger.warning(f"无法解析LVM卷的底层物理设备，使用直接分析方法")
            return analyze_lvm_directly(lvm_device, devices_info)
        
        logger.debug(f"LVM卷 {lvm_device} 对应的物理设备: {physical_devices}")
        
        # 分析物理设备信息
        lvm_members = []
        sleeping_count = 0
        max_temp = None
        device_types = set()
        
        for device_name in physical_devices:
            if device_name in devices_info:
                device_info = devices_info[device_name]
                lvm_members.append(device_info)
                
                # 统计休眠设备
                if device_info.get('is_sleeping', False):
                    sleeping_count += 1
                
                # 获取最高温度
                temp = device_info.get('temp')
                if temp is not None:
                    if max_temp is None or temp > max_temp:
                        max_temp = temp
                
                # 收集设备类型
                device_type = device_info.get('device_type', '未知')
                device_types.add(device_type)
                
                logger.debug(f"匹配到物理设备: {device_name}, 类型: {device_type}, 温度: {temp}")
            else:
                logger.warning(f"未找到物理设备 {device_name} 对应的设备信息")
        
        # 确定设备类型
        if len(device_types) == 0:
            device_type = "未知"
        elif len(device_types) == 1:
            device_type = list(device_types)[0]
        else:
            device_type = "混合LVM"
        
        all_members_sleeping = (sleeping_count == len(lvm_members)) and len(lvm_members) > 0
        
        lvm_info = {
            "temp": max_temp,
            "device_type": device_type,
            "is_raid": False,
            "is_lvm": True,
            "raid_members": lvm_members,
            "all_members_sleeping": all_members_sleeping
        }
        
        logger.debug(f"LVM卷 {lvm_device} 分析完成: {lvm_info}")
        
        return lvm_info
        
    except Exception as e:
        logger.error(f"分析LVM卷 {lvm_device} 失败: {e}")
        return analyze_lvm_directly(lvm_device, devices_info)


def analyze_lvm_directly(lvm_device: str, devices_info: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    直接分析LVM逻辑卷的底层设备信息
    
    功能：当LVM分析命令失败时，直接分析所有可用设备信息
    参数：
        lvm_device: LVM设备名
        devices_info: 物理磁盘信息字典
    返回值：
        Dict: LVM卷的详细信息
    """
    logger.debug(f"直接分析LVM卷 {lvm_device} 的底层设备信息")
    
    # 分析所有可用设备的类型和温度
    device_types = set()
    max_temp = None
    sleeping_count = 0
    total_devices = 0
    
    for device_name, device_info in devices_info.items():
        # 跳过RAID成员设备（它们已经在RAID组中）
        if device_info.get('is_raid_member', False):
            continue
            
        device_types.add(device_info.get('device_type', '未知'))
        
        temp = device_info.get('temp')
        if temp is not None:
            if max_temp is None or temp > max_temp:
                max_temp = temp
        
        if device_info.get('is_sleeping', False):
            sleeping_count += 1
        
        total_devices += 1
    
    logger.debug(f"直接分析结果: 设备类型集合: {device_types}, 最高温度: {max_temp}, 设备数量: {total_devices}")
    
    # 确定设备类型
    if len(device_types) == 0:
        device_type = "未知"
    elif len(device_types) == 1:
        device_type = list(device_types)[0]
        logger.debug(f"单一设备类型: {device_type}")
    else:
        device_type = "混合LVM"
        logger.debug(f"混合设备类型: {device_types} -> 显示为 '混合LVM'")
    
    all_members_sleeping = (sleeping_count == total_devices) and total_devices > 0
    logger.debug(f"所有成员休眠: {all_members_sleeping}")
    
    return {
        "temp": max_temp,
        "device_type": device_type,
        "is_raid": False,
        "is_lvm": True,
        "raid_members": [],
        "all_members_sleeping": all_members_sleeping
    }


def analyze_single_volume(device_name: str, devices_info: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    分析单盘卷信息
    
    功能：获取单盘卷的详细信息
    参数：
        device_name: 设备名（如sda）
        devices_info: 物理磁盘信息字典
    返回值：
        Dict: 单盘卷的详细信息
    """
    logger.debug(f"开始分析单盘卷: {device_name}")
    
    # 提取基础设备名（去掉分区号）
    base_device = re.sub(r'\d+$', '', device_name)
    logger.debug(f"提取基础设备名: {device_name} -> {base_device}")
    
    if base_device in devices_info:
        device_info = devices_info[base_device]
        
        logger.debug(f"找到物理设备信息: {base_device}")
        logger.debug(f"设备温度: {device_info.get('temp')}")
        logger.debug(f"设备类型: {device_info.get('device_type', '未知')}")
        logger.debug(f"设备休眠状态: {device_info.get('is_sleeping', False)}")
        
        single_info = {
            "temp": device_info.get("temp"),
            "device_type": device_info.get("device_type", "未知"),
            "is_raid": False,
            "raid_members": [],
            "all_members_sleeping": device_info.get("is_sleeping", False)
        }
        
        logger.debug(f"单盘卷 {device_name} 最终信息: {single_info}")
        
        return single_info
    else:
        logger.warning(f"未找到设备 {base_device} 对应的物理设备信息")
        return get_default_volume_info()


def get_default_volume_info() -> Dict[str, Any]:
    """获取默认的vol卷信息"""
    return {
        "temp": None,
        "device_type": "未知",
        "is_raid": False,
        "raid_members": [],
        "all_members_sleeping": False
    }


@cache_result(mon_config.DISK_UPDATE_INTERVAL)
def get_disk_info() -> List[Dict[str, Any]]:
    """
    获取磁盘信息（带缓存机制）
    
    功能：按新数据流设计组织磁盘信息，支持缓存机制降低CPU占用
    返回值：
        List[Dict]: 包含完整磁盘信息的vol卷列表
    """
    import platform
    
    if platform.system() != "Linux":
        logger.debug("非Linux系统，返回空列表")
        return []
    
    try:
        logger.debug("开始获取磁盘信息...")
        
        # 获取所有vol卷
        volumes = get_all_volumes()
        logger.debug(f"获取到 {len(volumes)} 个vol卷")
        
        # 获取物理磁盘信息
        devices_info = get_physical_devices()
        logger.debug(f"获取到 {len(devices_info)} 个物理设备")
        
        # 将vol卷映射到物理磁盘
        enhanced_volumes = map_volumes_to_devices(volumes, devices_info)
        logger.debug(f"映射完成，得到 {len(enhanced_volumes)} 个增强的vol卷")
        
        # 输出最终结果摘要
        for i, volume in enumerate(enhanced_volumes):
            logger.debug(f"vol卷 {i+1}: {volume['vol_name']} -> 类型: {volume.get('device_type', '未知')}, "
                       f"温度: {volume.get('temp', 'N/A')}, RAID: {volume.get('is_raid', False)}")
        
        logger.debug("磁盘信息获取完成")
        
        return enhanced_volumes
        
    except Exception as e:
        logger.error(f"获取磁盘信息失败: {e}")
        return []


def read_single_temp(device_path: str) -> Optional[float]:
    """
    读取单个设备的温度（支持休眠状态检测）
    """
    import platform
    
    if platform.system() != "Linux":
        return None
    
    try:
        # 关键修复：使用更可靠的休眠检测逻辑
        if 'nvme' in device_path:
            # NVMe设备 - 简化休眠检测逻辑
            result = run_command_with_timeout(["smartctl", "-a",  "-n", "standby",device_path], 
                                            timeout=5, use_sudo=True)
            
            # 检查命令是否成功执行（不仅仅是返回码）
            if result and hasattr(result, 'stdout') and result.stdout:
                # 更保守的休眠检测：只检查明确的休眠状态
                output_lower = result.stdout.lower()
                if 'standby' in output_lower and 'power state' in output_lower:
                    # 只有在明确提到power state为standby时才认为是休眠
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if 'power state' in line.lower() and 'standby' in line.lower():
                            logger.debug(f"NVMe设备 {device_path} 处于休眠状态")
                            return None
                
                match = re.search(r'Temperature:\s*(\d+)\s*Celsius', result.stdout, re.IGNORECASE)
                if match:
                    temp = float(match.group(1))
                    if 0 < temp < 100:
                        logger.debug(f"NVMe设备 {device_path} 温度: {temp}°C")
                        return temp
        else:
            # SATA/SCSI设备 - 使用更可靠的检测方法
            # 首先检查设备是否真的存在并可访问
            if not os.path.exists(device_path):
                logger.debug(f"设备路径不存在: {device_path}")
                return None
            
            # 尝试直接读取温度，不依赖休眠检测
            result = run_command_with_timeout(["smartctl", "-A",  "-n", "standby",device_path], 
                                            timeout=5, use_sudo=True)
            
            if result and hasattr(result, 'stdout') and result.stdout:
                # 检查是否真的休眠：查看特定属性
                output = result.stdout
                
                # 方法1：Temperature_Celsius属性 (ID 194)
                for line in output.split('\n'):
                    if '194 Temperature_Celsius' in line:
                        parts = line.split()
                        if len(parts) >= 10:
                            try:
                                temp = float(parts[9])
                                if 10 < temp < 120:
                                    logger.debug(f"SATA设备 {device_path} 温度(194): {temp}°C")
                                    return temp
                            except (ValueError, IndexError):
                                pass
                
                # 方法2：其他温度属性
                temp_attributes = [
                    ('190 Airflow_Temperature_Cel', "Airflow_Temperature_Cel"),
                    ('231 Temperature_Celsius_x2', "Temperature_Celsius_x2"),
                ]
                
                for attr_pattern, attr_name in temp_attributes:
                    for line in output.split('\n'):
                        if attr_pattern in line:
                            parts = line.split()
                            if len(parts) >= 10:
                                try:
                                    temp = float(parts[9])
                                    if 10 < temp < 120:
                                        logger.debug(f"SATA设备 {device_path} 温度({attr_name}): {temp}°C")
                                        return temp
                                except (ValueError, IndexError):
                                    continue
                
                # 如果找不到温度属性，尝试检查设备是否响应
                # 发送一个简单的IDENTIFY命令
                identify_result = run_command_with_timeout(["smartctl", "-i",  "-n", "standby",device_path], 
                                                         timeout=3, use_sudo=True)
                if identify_result and identify_result.returncode == 0:
                    # 设备响应但没有温度信息，可能不支持温度监控
                    logger.debug(f"设备 {device_path} 响应但没有温度信息")
                    return None
                else:
                    # 设备不响应，可能休眠或离线
                    logger.debug(f"设备 {device_path} 无响应，可能休眠")
                    return None
        
        # 尝试从sysfs读取温度（备选方案）
        device_name = os.path.basename(device_path)
        import glob
        sysfs_paths = [
            f"/sys/class/block/{device_name}/device/hwmon/hwmon*/temp1_input",
            f"/sys/class/block/{device_name}/device/hwmon/hwmon*/temp2_input",
        ]
        
        for sysfs_path in sysfs_paths:
            for actual_path in glob.glob(sysfs_path):
                try:
                    with open(actual_path, 'r') as f:
                        temp = int(f.read().strip()) / 1000
                        if 0 < temp < 100:
                            logger.debug(f"Sysfs设备 {device_path} 温度: {temp}°C")
                            return temp
                except (FileNotFoundError, PermissionError, ValueError):
                    continue
        
    except Exception as e:
        logger.debug(f"读取设备 {device_path} 温度时出错: {e}")
    
    return None

def get_device_type_from_smartctl(device_path: str) -> str:
    """通过smartctl获取设备类型"""
    try:
        # 首先检查是否为NVMe设备
        if "/dev/nvme" in device_path:
            return "SSD"
        
        result = run_command_with_timeout(["smartctl", "-i", "-n", "standby", device_path], 
                                         timeout=3, use_sudo=True)
        if not result or result.returncode != 0:
            # 如果smartctl失败，根据设备路径判断
            if "/dev/nvme" in device_path:
                return "SSD"
            elif "/dev/sd" in device_path:
                # 对于SATA设备，默认返回HDD，但需要进一步检测
                return "HDD"
            else:
                return "HDD"
        
        output = result.stdout
        
        # 检查SSD相关关键词
        if "Solid State Device" in output or "SSD" in output:
            return "SSD"
        
        rotation_match = re.search(r'Rotation Rate:\s*(\S+)', output)
        if rotation_match:
            rotation_rate = rotation_match.group(1)
            if rotation_rate == "Solid State Device" or rotation_rate == "SSD":
                return "SSD"
            elif rotation_rate == "rpm" or rotation_rate.isdigit():
                return "HDD"
        
        device_type_match = re.search(r'Device type:\s*(\S+)', output)
        if device_type_match:
            device_type = device_type_match.group(1).lower()
            if "ssd" in device_type or "solid" in device_type:
                return "SSD"
            elif "hdd" in device_type or "disk" in device_type:
                return "HDD"
        
        protocol_match = re.search(r'Transport protocol:\s*(\S+)', output)
        if protocol_match:
            protocol = protocol_match.group(1).lower()
            if "nvme" in protocol:
                return "SSD"
        
        model_match = re.search(r'Model Family:\s*(.+)', output)
        if model_match:
            model_family = model_match.group(1).lower()
            if "ssd" in model_family or "solid" in model_family:
                return "SSD"
            elif "hdd" in model_family or "disk" in model_family:
                return "HDD"
        
        # 检查设备型号
        model_match = re.search(r'Device Model:\s*(.+)', output)
        if model_match:
            model = model_match.group(1).lower()
            if "ssd" in model or "solid" in model:
                return "SSD"
        
    except Exception:
        # 异常时根据设备路径判断
        if "/dev/nvme" in device_path:
            return "SSD"
        elif "/dev/sd" in device_path:
            return "HDD"
    
    # 默认返回HDD
    return "HDD"




def get_temperature_color(temp: float) -> Tuple[int, int, int]:
    """根据温度获取颜色"""
    if temp is None:
        return COLORS["text_gray"]
    elif temp < 40:
        return COLORS["disk_temp_normal"]
    elif temp < 50:
        return COLORS["disk_temp_warm"]
    else:
        return COLORS["disk_temp_hot"]


# 以下是原有的绘图函数（保持不变）

def draw_disk(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """绘制磁盘模块"""
    # 绘制卡片背景
    draw_card(surface, rect)
    
    # 绘制垂直标题"存储"
    draw_vertical_title(surface, rect, "存储")
    
    disks = get_disk_info()
    draw_disk_partitions(surface, rect, disks)


def draw_disk_partitions(surface: pygame.Surface, rect: pygame.Rect, disks: List[Dict[str, Any]]) -> None:
    """绘制磁盘分区信息"""
    if not disks:
        no_disk_surf = mon_config.FONT_MEDIUM.render("未检测到存储分区", True, COLORS["text_gray"])
        surface.blit(no_disk_surf, (rect.centerx - no_disk_surf.get_width()//2, rect.centery))
        return
    
    disk_count = len(disks)
    
    if disk_count == 1:
        bar_width = 120
        bar_spacing = 0
        start_x = rect.centerx - bar_width // 2
    elif disk_count == 2:
        bar_width = 80
        bar_spacing = 40
        total_width = 2 * bar_width + bar_spacing
        start_x = rect.centerx - total_width // 2
    elif disk_count == 3:
        bar_width = 60
        bar_spacing = 30
        total_width = 3 * bar_width + 2 * bar_spacing
        start_x = rect.centerx - total_width // 2
    elif disk_count == 4:
        bar_width = 50
        bar_spacing = 25
        total_width = 4 * bar_width + 3 * bar_spacing
        start_x = rect.centerx - total_width // 2
    else:
        bar_width = 40
        bar_spacing = 20
        total_width = disk_count * bar_width + (disk_count - 1) * bar_spacing
        start_x = rect.centerx - total_width // 2
    
    for i, disk_info in enumerate(disks):
        bar_x = start_x + i * (bar_width + bar_spacing)
        bar_y = rect.y + 5
        draw_disk_bar(surface, bar_x, bar_y, bar_width, rect.height - 10, disk_info)


def draw_disk_bar(surface: pygame.Surface, x: int, y: int, width: int, height: int, disk_info: Dict[str, Any]) -> None:
    """绘制单个磁盘柱状图"""
    vol_name = disk_info["vol_name"]
    pct = disk_info["percent"]
    used = disk_info["used"]
    total = disk_info["total"]
    unit = disk_info["unit"]
    temp = disk_info["temp"]
    device_type = disk_info["device_type"]
    is_raid = disk_info["is_raid"]
    
    bar_height = height - 45
    bar_y = y + 35
    
    # 绘制vol名称
    vol_rect = (x, y + 5, width, 20)
    draw_text_centered_with_shadow(surface, mon_config.FONT_SMALL, vol_name, COLORS["text_white"], vol_rect)
    
    # 绘制柱状图背景
    bar_rect = pygame.Rect(x, bar_y, width - 4, bar_height)
    draw_rounded_rect(surface, COLORS["bg_dark"], bar_rect, BAR_RADIUS//2)
    
    # 计算填充高度
    bar_fill_height = int(bar_height * (pct / 100))
    
    # 绘制填充部分
    if bar_fill_height > 0:
        fill_rect = pygame.Rect(x, bar_y + bar_height - bar_fill_height, width - 4, bar_fill_height)
        draw_rounded_rect(surface, COLORS["disk_used"], fill_rect, BAR_RADIUS//2)
    
    # 绘制边框
    draw_rounded_rect(surface, COLORS["border"], bar_rect, BAR_RADIUS//2, 1)
    
    # 显示温度或休眠状态
    temp_rect = (x, bar_y + 5, width, 20)
    if temp is not None:
        temp_color = get_temperature_color(temp)
        temp_text = f"{temp:.0f}°C"
        draw_text_centered_with_shadow(surface, mon_config.FONT_SMALL, temp_text, temp_color, temp_rect)
    else:
        # 所有设备在休眠状态时都显示"眠"符号
        draw_text_centered_with_shadow(surface, mon_config.FONT_SMALL, "眠", COLORS["text_gray"], temp_rect)
    
    # 底部信息显示
    bottom_y = bar_y + bar_height - 55

    # 第1行：使用率
    pct_rect = (x, bottom_y, width, 20)
    draw_text_centered_with_shadow(surface, mon_config.FONT_SMALL, f"{pct}%", COLORS["disk_text"], pct_rect)

    # 第2行：总容量
    total_rect = (x, bottom_y + 17, width, 15)
    draw_text_centered_with_shadow(surface, mon_config.FONT_TINY, f"{total}{unit}", COLORS["text_gray"], total_rect)
    
    # 第3行：设备类型（如果是RAID且混合类型显示RAID）
    type_rect = (x, bottom_y + 34, width, 15)
    display_type = device_type
    if is_raid and device_type == "混合RAID":
        display_type = "RAID"
    draw_text_centered_with_shadow(surface, mon_config.FONT_TINY, f"{display_type}", COLORS["text_gray"], type_rect)