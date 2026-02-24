"""Hardware Detection Module.

Detects CPU, GPU, RAM, Disk, and other system components
for displaying system information optimized for local LLM usage.
"""

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import psutil

try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

logger = logging.getLogger(__name__)


class BaseDetector:
    """Base class for hardware detectors with common utilities."""

    @staticmethod
    def run_command(cmd: str, timeout: int = 5) -> str:
        """Execute shell command safely with timeout.

        Args:
            cmd: Shell command to execute.
            timeout: Maximum execution time in seconds.

        Returns:
            Command output as string, or empty string on failure.
        """
        try:
            result = subprocess.check_output(
                cmd,
                shell=True,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
            return result.strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return ""
        except Exception as e:
            logger.debug(f"Command failed: {cmd} - {str(e)}")
            return ""


class OSDetector(BaseDetector):
    """Detects operating system and basic system information."""

    @staticmethod
    def detect() -> Dict[str, str]:
        """Detect OS information including platform, kernel, and Python version.

        Returns:
            Dictionary containing OS details.
        """
        uname = platform.uname()

        return {
            "system": platform.system(),
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "platform": platform.platform(terse=True),
            "python_version": platform.python_version(),
        }

    @staticmethod
    def get_uptime() -> Dict[str, int]:
        """Get system uptime since last boot.

        Returns:
            Dictionary with days, hours, minutes, and total seconds.
        """
        uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
        return {
            "days": uptime.days,
            "hours": uptime.seconds // 3600,
            "minutes": (uptime.seconds % 3600) // 60,
            "total_seconds": int(uptime.total_seconds()),
        }


class CPUDetector(BaseDetector):
    """Detects CPU information including cores, frequency, and temperature."""

    @staticmethod
    def detect() -> Dict[str, Union[str, int, float]]:
        """Detect CPU model, cores, frequency, usage, and temperature.

        Returns:
            Dictionary containing CPU specifications and current state.
        """
        uname = platform.uname()
        cpu_name = platform.processor() or uname.processor

        if not cpu_name and sys.platform.startswith("win"):
            cpu_name = CPUDetector.run_command("wmic cpu get name")
            if cpu_name:
                lines = cpu_name.splitlines()
                cpu_name = lines[-1].strip() if len(lines) > 1 else "Unknown"

        if sys.platform == "darwin" and not cpu_name:
            cpu_name = CPUDetector.run_command("sysctl -n machdep.cpu.brand_string")

        if not cpu_name and sys.platform.startswith("linux"):
            cpu_name = CPUDetector.run_command(
                "cat /proc/cpuinfo | grep 'model name' | head -1 | cut -d':' -f2"
            )

        cores_physical = psutil.cpu_count(logical=False) or 0
        cores_logical = psutil.cpu_count(logical=True) or 0

        freq = psutil.cpu_freq()
        current_freq = freq.current if freq else 0
        max_freq = freq.max if freq else 0

        cpu_percent = psutil.cpu_percent(interval=1)

        temperature = CPUDetector._get_temperature()

        return {
            "name": cpu_name.strip() or "Unknown CPU",
            "cores_physical": cores_physical,
            "cores_logical": cores_logical,
            "current_freq_mhz": current_freq,
            "max_freq_mhz": max_freq,
            "usage_percent": cpu_percent,
            "temperature_c": temperature,
        }

    @staticmethod
    def _get_temperature() -> Optional[float]:
        """Get CPU temperature from available sensors.

        Returns:
            Temperature in Celsius, or None if unavailable.
        """
        try:
            temps: Any = psutil.sensors_temperatures()
            if not temps:
                return None

            for name in ["coretemp", "cpu_thermal", "k10temp", "zenpower"]:
                if name in temps and temps[name]:
                    return temps[name][0].current

            for sensor_temps in temps.values():
                if sensor_temps:
                    return sensor_temps[0].current
        except (AttributeError, KeyError):
            pass

        return None


class GPUDetector(BaseDetector):
    """Detects GPU information including VRAM, utilization, and temperature."""

    @staticmethod
    def detect() -> List[Dict[str, Union[str, int, float]]]:
        """Detect all available GPUs from NVIDIA, AMD, Intel, or WMI.

        Returns:
            List of dictionaries containing GPU details.
        """
        gpus: List[Dict[str, Union[str, int, float]]] = []

        gpus.extend(GPUDetector._detect_nvidia())
        gpus.extend(GPUDetector._detect_amd())
        gpus.extend(GPUDetector._detect_intel())

        if not gpus and WMI_AVAILABLE and sys.platform.startswith("win"):
            gpus.extend(GPUDetector._detect_wmi())

        if not gpus:
            gpus.append(
                {
                    "vendor": "Unknown",
                    "name": "No dedicated GPU detected",
                    "vram_total_gb": 0,
                    "vram_used_gb": 0,
                    "utilization_percent": 0,
                    "temperature_c": 0.0,
                }
            )

        return gpus

    @staticmethod
    def _detect_nvidia() -> List[Dict]:
        """Detect NVIDIA GPUs using nvidia-smi.

        Returns:
            List of NVIDIA GPU information dictionaries.
        """
        gpus: List[Dict] = []

        if not shutil.which("nvidia-smi"):
            return gpus

        query = "name,memory.total,memory.used,utilization.gpu,temperature.gpu"
        cmd = f"nvidia-smi --query-gpu={query} --format=csv,noheader,nounits"
        output = GPUDetector.run_command(cmd)

        if not output:
            return gpus

        for line in output.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                try:
                    gpus.append(
                        {
                            "vendor": "NVIDIA",
                            "name": parts[0],
                            "vram_total_gb": float(parts[1]) / 1024,
                            "vram_used_gb": float(parts[2]) / 1024,
                            "utilization_percent": float(parts[3]),
                            "temperature_c": float(parts[4])
                            if parts[4] != "[N/A]"
                            else None,
                        }
                    )
                except ValueError:
                    continue

        return gpus

    @staticmethod
    def _detect_amd() -> List[Dict]:
        """Detect AMD GPUs using rocm-smi.

        Returns:
            List of AMD GPU information dictionaries.
        """
        gpus: List[Dict] = []

        if not shutil.which("rocm-smi"):
            return gpus

        name_output = GPUDetector.run_command("rocm-smi --showproductname")
        GPUDetector.run_command("rocm-smi --showmeminfo vram")
        GPUDetector.run_command("rocm-smi --showtemp")
        GPUDetector.run_command("rocm-smi --showuse")

        if name_output:
            gpu_name = "AMD GPU"
            for line in name_output.splitlines():
                if "GPU" in line or "Card" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        gpu_name = parts[1].strip()
                        break

            gpus.append(
                {
                    "vendor": "AMD",
                    "name": gpu_name,
                    "vram_total_gb": 0,
                    "vram_used_gb": 0,
                    "utilization_percent": 0,
                    "temperature_c": None,
                }
            )

        return gpus

    @staticmethod
    def _detect_intel() -> List[Dict]:
        """Detect Intel GPUs including Arc/Xe series.

        Returns:
            List of Intel GPU information dictionaries.
        """
        gpus: List[Dict] = []

        if shutil.which("sycl-ls"):
            output = GPUDetector.run_command("sycl-ls")
            if "Intel" in output:
                gpus.append(
                    {
                        "vendor": "Intel",
                        "name": "Intel GPU (Arc/Xe)",
                        "vram_total_gb": 0,
                        "vram_used_gb": 0,
                        "utilization_percent": 0,
                        "temperature_c": None,
                    }
                )

        return gpus

    @staticmethod
    def _detect_wmi() -> List[Dict]:
        """Detect GPUs using WMI on Windows.

        Returns:
            List of GPU information dictionaries from WMI.
        """
        gpus: List[Dict] = []

        try:
            c = wmi.WMI()
            for video in c.Win32_VideoController():
                name = video.Name.strip()
                if any(
                    vendor in name
                    for vendor in ["NVIDIA", "AMD", "Intel", "Radeon", "GeForce"]
                ):
                    vram_bytes = video.AdapterRAM or 0
                    vram_gb = vram_bytes / (1024**3) if vram_bytes else 0

                    gpus.append(
                        {
                            "vendor": "Integrated/Discrete",
                            "name": name,
                            "vram_total_gb": vram_gb,
                            "vram_used_gb": 0,
                            "utilization_percent": 0,
                            "temperature_c": None,
                        }
                    )
        except Exception as e:
            logger.debug(f"WMI GPU detection failed: {e}")

        return gpus


class MemoryDetector(BaseDetector):
    """Detects RAM and swap memory information."""

    @staticmethod
    def detect() -> Dict[str, Union[int, float]]:
        """Detect physical RAM and swap memory usage.

        Returns:
            Dictionary containing memory statistics in bytes and percentage.
        """
        vmem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return {
            "ram_total_bytes": vmem.total,
            "ram_available_bytes": vmem.available,
            "ram_used_bytes": vmem.used,
            "ram_percent": vmem.percent,
            "swap_total_bytes": swap.total,
            "swap_used_bytes": swap.used,
            "swap_percent": swap.percent,
        }


class DiskDetector(BaseDetector):
    """Detects disk storage information including type (SSD/NVMe/HDD)."""

    @staticmethod
    def detect() -> List[Dict[str, Union[str, int, float]]]:
        """Detect all mounted disks with capacity and type information.

        Returns:
            List of disk information dictionaries, sorted by system drives first.
        """
        disks: List[Dict[str, Union[str, int, float]]] = []
        partitions = psutil.disk_partitions(all=False)

        for partition in partitions:
            if partition.fstype == "" or "loop" in partition.device:
                continue

            is_system = partition.mountpoint in [
                "/",
                "C:\\",
            ] or "Windows" in partition.opts

            try:
                usage = psutil.disk_usage(partition.mountpoint)

                disk_type = DiskDetector._detect_disk_type(partition.device)

                disk_info = {
                    "mountpoint": partition.mountpoint,
                    "device": partition.device,
                    "fstype": partition.fstype,
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "percent": usage.percent,
                    "type": disk_type,
                    "is_system": is_system,
                }

                disks.append(disk_info)

            except PermissionError:
                continue

        disks.sort(key=lambda x: (not x["is_system"], x["mountpoint"]))

        return disks[:3]

    @staticmethod
    def _detect_disk_type(device: str) -> str:
        """Detect disk storage type (NVMe, SSD, or HDD).

        Args:
            device: Device path (e.g., /dev/sda1 or /dev/nvme0n1p1).

        Returns:
            String indicating disk type: 'NVMe', 'SSD', 'HDD', or 'Unknown'.
        """
        device_lower = device.lower()

        if "nvme" in device_lower:
            return "NVMe"

        if sys.platform.startswith("linux"):
            match = re.search(r"/dev/([a-z]+)", device_lower)
            if match:
                dev_name = match.group(1)
                try:
                    with open(f"/sys/block/{dev_name}/queue/rotational") as f:
                        if f.read().strip() == "0":
                            return "SSD"
                        return "HDD"
                except Exception:
                    pass

        if "ssd" in device_lower:
            return "SSD"

        return "Unknown"

    @staticmethod
    def benchmark_speed(
        path: str = None, size_mb: int = 100, timeout: int = 30
    ) -> Optional[Dict[str, float]]:
        """Benchmark disk read and write speeds.

        Args:
            path: Directory path for benchmark file. Defaults to home directory.
            size_mb: Size of test file in megabytes.
            timeout: Maximum benchmark duration in seconds.

        Returns:
            Dictionary with read/write speeds in MB/s, or None on failure.
        """
        if path is None:
            path = os.path.expanduser("~")

        test_file = os.path.join(path, ".llm_neofetch_benchmark.tmp")

        try:
            start = time.time()
            data = b"0" * (size_mb * 1024 * 1024)
            with open(test_file, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            write_time = time.time() - start

            if write_time > timeout:
                return None

            start = time.time()
            with open(test_file, "rb") as f:
                _ = f.read()
            read_time = time.time() - start

            os.remove(test_file)

            return {
                "read_mb_s": size_mb / read_time if read_time > 0 else 0,
                "write_mb_s": size_mb / write_time if write_time > 0 else 0,
            }

        except Exception as e:
            logger.debug(f"Disk benchmark failed: {e}")
            if os.path.exists(test_file):
                try:
                    os.remove(test_file)
                except Exception:
                    pass
            return None


class BatteryDetector(BaseDetector):
    """Detects battery information on laptops."""

    @staticmethod
    def detect() -> Optional[Dict[str, Union[bool, float, str]]]:
        """Detect battery charge level, power status, and time remaining.

        Returns:
            Dictionary containing battery details, or None if not available.
        """
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return None

            if battery.power_plugged:
                time_left = "Charging"
            elif battery.secsleft == psutil.POWER_TIME_UNLIMITED:
                time_left = "Unlimited"
            elif battery.secsleft == psutil.POWER_TIME_UNKNOWN:
                time_left = "Unknown"
            else:
                hours = battery.secsleft // 3600
                minutes = (battery.secsleft % 3600) // 60
                time_left = f"{hours}h {minutes}m"

            return {
                "percent": battery.percent,
                "plugged": battery.power_plugged,
                "time_left": time_left,
                "time_left_seconds": battery.secsleft if battery.secsleft >= 0 else 0,
            }
        except Exception as e:
            logger.debug(f"Battery detection failed: {e}")
            return None


class MotherboardDetector(BaseDetector):
    """Detects motherboard/board information."""

    @staticmethod
    def detect() -> str:
        """Detect motherboard manufacturer and product name.

        Returns:
            String with manufacturer and product, or "N/A" if unavailable.
        """
        if WMI_AVAILABLE and sys.platform.startswith("win"):
            try:
                c = wmi.WMI()
                for board in c.Win32_BaseBoard():
                    manufacturer = board.Manufacturer.strip()
                    product = board.Product.strip()
                    return f"{manufacturer} {product}"
            except Exception:
                pass

        if sys.platform.startswith("linux"):
            manufacturer = MotherboardDetector.run_command(
                "cat /sys/class/dmi/id/board_vendor 2>/dev/null"
            )
            product = MotherboardDetector.run_command(
                "cat /sys/class/dmi/id/board_name 2>/dev/null"
            )
            if manufacturer and product:
                return f"{manufacturer} {product}"

        return "N/A"


class AppleSiliconDetector(BaseDetector):
    """Detects Apple Silicon (M-series) chip information."""

    @staticmethod
    def detect() -> Optional[Dict[str, Union[str, int, bool]]]:
        """Detect Apple Silicon chip variant and unified memory.

        Returns:
            Dictionary with chip details, or None if not Apple Silicon.
        """
        if sys.platform != "darwin":
            return None

        chip = AppleSiliconDetector.run_command("sysctl -n machdep.cpu.brand_string")

        if not chip or "Apple" not in chip:
            return None

        mem_bytes = AppleSiliconDetector.run_command("sysctl -n hw.memsize")
        mem_gb = int(mem_bytes) / (1024**3) if mem_bytes.isdigit() else 0

        chip_variant = "Unknown"
        for variant in ["M1", "M2", "M3", "M4"]:
            if variant in chip:
                chip_variant = variant
                break

        return {
            "chip": chip,
            "variant": chip_variant,
            "unified_memory_gb": mem_gb,
            "supports_mlx": True,
        }
