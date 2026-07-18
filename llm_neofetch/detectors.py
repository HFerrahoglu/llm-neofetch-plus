"""Hardware Detection Module.

Detects CPU, GPU, RAM, Disk, and other system components
for displaying system information optimized for local LLM usage.
"""

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
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

    @staticmethod
    def run_powershell(script: str, timeout: int = 15) -> str:
        """Execute a PowerShell script safely on Windows.

        Runs without shell=True so no cmd.exe quoting is involved.

        Args:
            script: PowerShell script text.
            timeout: Maximum execution time in seconds.

        Returns:
            Script output as string, or empty string on failure.
        """
        try:
            result = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
            return result.strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return ""
        except Exception as e:
            logger.debug(f"PowerShell command failed: {str(e)}")
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
        cpu_name = ""

        if sys.platform.startswith("win"):
            cpu_name = CPUDetector._get_windows_cpu_name()

        if not cpu_name:
            cpu_name = platform.processor() or uname.processor

        if sys.platform == "darwin" and not cpu_name:
            cpu_name = CPUDetector.run_command("sysctl -n machdep.cpu.brand_string")

        if not cpu_name and sys.platform.startswith("linux"):
            cpu_name = CPUDetector.run_command(
                "cat /proc/cpuinfo | grep 'model name' | head -1 | cut -d':' -f2"
            )

        cores_physical = psutil.cpu_count(logical=False) or 0
        cores_logical = psutil.cpu_count(logical=True) or 0

        current_freq = 0
        max_freq = 0
        try:
            freq = psutil.cpu_freq()
            if freq:
                current_freq = freq.current
                max_freq = freq.max
        except AttributeError:
            pass

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
    def _get_windows_cpu_name() -> str:
        """Get the CPU marketing name from the Windows registry.

        platform.processor() only returns the CPU family string on Windows
        (e.g. "Intel64 Family 6 Model 186"), and wmic is removed from
        recent Windows 11 builds, so read the registry directly.

        Returns:
            CPU name string, or empty string on failure.
        """
        if sys.platform != "win32":
            return ""

        try:
            import winreg

            key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                name = winreg.QueryValueEx(key, "ProcessorNameString")[0]
                return str(name).strip()
        except OSError:
            return ""

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
        """Detect NVIDIA GPUs using nvidia-smi, falling back to NVML.

        Returns:
            List of NVIDIA GPU information dictionaries.
        """
        gpus: List[Dict] = []

        if not shutil.which("nvidia-smi"):
            return GPUDetector._detect_nvidia_nvml()

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
    def _detect_nvidia_nvml() -> List[Dict]:
        """Detect NVIDIA GPUs via NVML (pynvml) when nvidia-smi is absent.

        pynvml is an optional dependency; returns empty list if missing.

        Returns:
            List of NVIDIA GPU information dictionaries.
        """
        gpus: List[Dict] = []

        try:
            import pynvml
        except ImportError:
            return gpus

        try:
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                try:
                    util = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
                except Exception:
                    util = 0.0
                try:
                    temp = float(
                        pynvml.nvmlDeviceGetTemperature(
                            handle, pynvml.NVML_TEMPERATURE_GPU
                        )
                    )
                except Exception:
                    temp = None

                gpus.append(
                    {
                        "vendor": "NVIDIA",
                        "name": name,
                        "vram_total_gb": mem.total / (1024**3),
                        "vram_used_gb": mem.used / (1024**3),
                        "utilization_percent": util,
                        "temperature_c": temp,
                    }
                )
            pynvml.nvmlShutdown()
        except Exception as e:
            logger.debug(f"NVML detection failed: {e}")

        return gpus

    @staticmethod
    def _detect_amd() -> List[Dict]:
        """Detect AMD GPUs using amd-smi or rocm-smi.

        Tries amd-smi (the modern tool) first, then rocm-smi JSON,
        then legacy rocm-smi text parsing.

        Returns:
            List of AMD GPU information dictionaries.
        """
        gpus = GPUDetector._detect_amd_smi()
        if gpus:
            return gpus

        if not shutil.which("rocm-smi"):
            return gpus

        output = GPUDetector.run_command(
            "rocm-smi --showproductname --showmeminfo vram --showuse --showtemp --json"
        )
        if output:
            try:
                data = json.loads(output)
                for card_id in sorted(data):
                    card = data[card_id]
                    if isinstance(card, dict):
                        gpus.append(GPUDetector._parse_rocm_card(card))
            except (ValueError, TypeError) as e:
                logger.debug(f"rocm-smi JSON parsing failed: {e}")

        if gpus:
            return gpus

        name_output = GPUDetector.run_command("rocm-smi --showproductname")
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
    def _detect_amd_smi() -> List[Dict]:
        """Detect AMD GPUs using amd-smi (successor to rocm-smi).

        Returns:
            List of AMD GPU information dictionaries.
        """
        gpus: List[Dict] = []

        if not shutil.which("amd-smi"):
            return gpus

        static_out = GPUDetector.run_command("amd-smi static --json")
        metric_out = GPUDetector.run_command("amd-smi metric --json")

        try:
            static_data = json.loads(static_out) if static_out else []
            metric_data = json.loads(metric_out) if metric_out else []
        except (ValueError, TypeError) as e:
            logger.debug(f"amd-smi JSON parsing failed: {e}")
            return gpus

        if isinstance(static_data, dict):
            static_data = [static_data]
        if isinstance(metric_data, dict):
            metric_data = [metric_data]

        for i, entry in enumerate(static_data):
            if not isinstance(entry, dict):
                continue
            metrics = metric_data[i] if i < len(metric_data) else {}

            name = GPUDetector._find_value(entry, "market_name") or "AMD GPU"
            vram_mb = GPUDetector._find_number(entry, "size") or 0
            used_mb = GPUDetector._find_number(metrics, "used_vram") or 0
            util = GPUDetector._find_number(metrics, "gfx_activity") or 0
            temp = GPUDetector._find_number(metrics, "edge")

            gpus.append(
                {
                    "vendor": "AMD",
                    "name": str(name),
                    "vram_total_gb": float(vram_mb) / 1024,
                    "vram_used_gb": float(used_mb) / 1024,
                    "utilization_percent": float(util),
                    "temperature_c": float(temp) if temp is not None else None,
                }
            )

        return gpus

    @staticmethod
    def _find_value(data: Any, key_substring: str) -> Optional[Any]:
        """Recursively find the first value whose key contains a substring.

        Handles the nested {"value": x, "unit": "MB"} wrappers used by
        amd-smi JSON output.

        Args:
            data: Nested dict/list structure.
            key_substring: Substring to match against keys (lowercase).

        Returns:
            The found value, or None.
        """
        if isinstance(data, dict):
            for key, value in data.items():
                if key_substring in str(key).lower():
                    if isinstance(value, dict) and "value" in value:
                        return value["value"]
                    return value
            for value in data.values():
                found = GPUDetector._find_value(value, key_substring)
                if found is not None:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = GPUDetector._find_value(item, key_substring)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _find_number(data: Any, key_substring: str) -> Optional[float]:
        """Recursively find the first numeric value for a key substring.

        Args:
            data: Nested dict/list structure.
            key_substring: Substring to match against keys (lowercase).

        Returns:
            The numeric value, or None.
        """
        value = GPUDetector._find_value(data, key_substring)
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_rocm_card(card: Dict) -> Dict:
        """Extract GPU fields from one card's rocm-smi JSON entry.

        Key names vary between rocm-smi versions, so match substrings.

        Args:
            card: Dictionary of one card's rocm-smi JSON data.

        Returns:
            Normalized GPU information dictionary.
        """
        name = "AMD GPU"
        vram_total = 0.0
        vram_used = 0.0
        util = 0.0
        temp: Optional[float] = None

        for key, value in card.items():
            key_l = key.lower()
            try:
                if "card series" in key_l and value:
                    name = str(value).strip()
                elif ("card model" in key_l or "card sku" in key_l) and value and name == "AMD GPU":
                    name = str(value).strip()
                elif "vram total memory" in key_l:
                    vram_total = float(value) / (1024**3)
                elif "vram total used" in key_l:
                    vram_used = float(value) / (1024**3)
                elif "gpu use" in key_l:
                    util = float(value)
                elif "temperature" in key_l and ("edge" in key_l or temp is None):
                    temp = float(value)
            except (TypeError, ValueError):
                continue

        return {
            "vendor": "AMD",
            "name": name,
            "vram_total_gb": vram_total,
            "vram_used_gb": vram_used,
            "utilization_percent": util,
            "temperature_c": temp,
        }

    @staticmethod
    def _detect_intel() -> List[Dict]:
        """Detect Intel GPUs including Arc/Xe series.

        Returns:
            List of Intel GPU information dictionaries.
        """
        gpus: List[Dict] = []

        if not shutil.which("sycl-ls"):
            return gpus

        output = GPUDetector.run_command("sycl-ls")
        if not output:
            return gpus

        names: List[str] = []
        for line in output.splitlines():
            if ":gpu:" not in line.lower() or "Intel" not in line:
                continue
            match = re.search(r":gpu:\d+\]\s*[^,]+,\s*(.+?)(?:\s+\d+\.\d+)?\s*\[", line)
            if match:
                name = match.group(1).strip()
                if name and name not in names:
                    names.append(name)

        if not names and "Intel" in output:
            names.append("Intel GPU (Arc/Xe)")

        for name in names:
            gpus.append(
                {
                    "vendor": "Intel",
                    "name": name,
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
                name = (video.Name or "").strip()
                if not name:
                    continue
                if any(
                    vendor in name
                    for vendor in ["NVIDIA", "AMD", "Intel", "Radeon", "GeForce", "Arc"]
                ):
                    vram_gb = GPUDetector._get_windows_gpu_vram(name)
                    if not vram_gb:
                        # AdapterRAM is a 32-bit value capped at 4 GB
                        vram_bytes = video.AdapterRAM or 0
                        vram_gb = vram_bytes / (1024**3) if vram_bytes else 0

                    gpus.append(
                        {
                            "vendor": GPUDetector._vendor_from_name(name),
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

    @staticmethod
    def _vendor_from_name(name: str) -> str:
        """Derive GPU vendor from the adapter name.

        Args:
            name: GPU adapter name string.

        Returns:
            Vendor string: 'NVIDIA', 'AMD', 'Intel', or 'Unknown'.
        """
        upper = name.upper()
        if "NVIDIA" in upper or "GEFORCE" in upper or "QUADRO" in upper:
            return "NVIDIA"
        if "AMD" in upper or "RADEON" in upper:
            return "AMD"
        if "INTEL" in upper:
            return "Intel"
        return "Unknown"

    @staticmethod
    def _get_windows_gpu_vram(name: str) -> float:
        """Look up dedicated VRAM from the Windows registry.

        WMI's AdapterRAM is a 32-bit value capped at 4 GB; the display
        class registry key stores the real size as a 64-bit value.

        Args:
            name: GPU adapter name to match against DriverDesc.

        Returns:
            VRAM size in GB, or 0.0 if not found.
        """
        if sys.platform != "win32":
            return 0.0

        try:
            import winreg

            base = (
                r"SYSTEM\CurrentControlSet\Control\Class"
                r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
            )
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
                for i in range(64):
                    try:
                        sub = winreg.EnumKey(root, i)
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, sub) as key:
                            desc = winreg.QueryValueEx(key, "DriverDesc")[0]
                            if str(desc).strip() != name:
                                continue
                            qw = winreg.QueryValueEx(
                                key, "HardwareInformation.qwMemorySize"
                            )[0]
                            return int(qw) / (1024**3)
                    except OSError:
                        continue
        except OSError:
            pass

        return 0.0


class MemoryDetector(BaseDetector):
    """Detects RAM and swap memory information."""

    @staticmethod
    def detect() -> Dict[str, Any]:
        """Detect physical RAM and swap memory usage.

        Returns:
            Dictionary containing memory statistics in bytes and percentage,
            plus module details (speed, stick count, bandwidth estimate)
            when available.
        """
        vmem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        info: Dict[str, Any] = {
            "ram_total_bytes": vmem.total,
            "ram_available_bytes": vmem.available,
            "ram_used_bytes": vmem.used,
            "ram_percent": vmem.percent,
            "swap_total_bytes": swap.total,
            "swap_used_bytes": swap.used,
            "swap_percent": swap.percent,
        }
        info.update(MemoryDetector._detect_modules())
        return info

    @staticmethod
    def _detect_modules() -> Dict[str, Any]:
        """Detect RAM module speed and count.

        Memory bandwidth (channels x speed) is the key figure for CPU
        inference speed, so estimate it when module info is available.

        Returns:
            Dictionary with ram_speed_mts, ram_sticks and
            ram_bandwidth_est_gb_s (values may be None/0 if unknown).
        """
        speed = 0.0
        sticks = 0

        if sys.platform.startswith("win"):
            output = MemoryDetector.run_powershell(
                "Get-CimInstance Win32_PhysicalMemory | ForEach-Object { "
                '"$($_.ConfiguredClockSpeed)|$($_.Speed)" }'
            )
            for line in output.splitlines():
                configured, _, nominal = line.partition("|")
                sticks += 1
                for candidate in (configured.strip(), nominal.strip()):
                    if candidate.isdigit() and int(candidate) > 0:
                        speed = max(speed, float(candidate))
                        break
        elif sys.platform.startswith("linux"):
            output = MemoryDetector.run_command("dmidecode -t 17 2>/dev/null")
            if output:
                for block in output.split("Memory Device"):
                    if "No Module Installed" in block or "Size:" not in block:
                        continue
                    sticks += 1
                    match = re.search(r"Speed:\s*(\d+)\s*MT/s", block)
                    if match:
                        speed = max(speed, float(match.group(1)))

        result: Dict[str, Any] = {
            "ram_speed_mts": speed,
            "ram_sticks": sticks,
            "ram_bandwidth_est_gb_s": 0.0,
        }
        if speed > 0 and sticks > 0:
            # Soldered LPDDR often reports one module but runs dual-channel,
            # so assume at least 2 channels (labeled as an estimate in UI)
            channels = max(2, min(sticks, 2))
            result["ram_bandwidth_est_gb_s"] = channels * speed * 8 / 1000
        return result


class NPUDetector(BaseDetector):
    """Detects neural processing units (NPUs / AI accelerators)."""

    @staticmethod
    def detect() -> List[str]:
        """Detect NPUs such as Intel AI Boost, AMD XDNA, Apple ANE.

        Returns:
            List of NPU device names (empty if none found).
        """
        npus: List[str] = []

        if sys.platform.startswith("win"):
            output = NPUDetector.run_powershell(
                "Get-CimInstance Win32_PnPEntity | Where-Object { "
                "$_.Name -match '\\bNPU\\b|AI Boost|Neural|XDNA|Hexagon' } | "
                "Select-Object -ExpandProperty Name -Unique",
                timeout=20,
            )
            npus.extend(
                line.strip() for line in output.splitlines() if line.strip()
            )
        elif sys.platform.startswith("linux"):
            import glob as _glob

            if _glob.glob("/dev/accel/accel*") or _glob.glob("/dev/accel*"):
                name = "NPU (accel device)"
                if shutil.which("lspci"):
                    output = NPUDetector.run_command(
                        "lspci | grep -iE 'npu|vpu|neural'"
                    )
                    first = output.splitlines()[0].strip() if output else ""
                    if first:
                        name = first.split(": ", 1)[-1]
                npus.append(name)
        elif sys.platform == "darwin":
            chip = NPUDetector.run_command("sysctl -n machdep.cpu.brand_string")
            if "Apple" in chip:
                npus.append("Apple Neural Engine")

        return npus


class DiskDetector(BaseDetector):
    """Detects disk storage information including type (SSD/NVMe/HDD)."""

    _windows_disk_types: Optional[Dict[str, str]] = None

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

        if sys.platform.startswith("win"):
            letter = device_lower.strip()[:1]
            if letter.isalpha():
                win_type = DiskDetector._get_windows_disk_types().get(letter.upper())
                if win_type:
                    return win_type
            return "Unknown"

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

    @classmethod
    def _get_windows_disk_types(cls) -> Dict[str, str]:
        """Map Windows drive letters to disk types via PowerShell.

        Queries physical disk MediaType/BusType once and caches the
        result (drive letter -> 'NVMe' | 'SSD' | 'HDD').

        Returns:
            Dictionary mapping uppercase drive letters to disk types.
        """
        if cls._windows_disk_types is not None:
            return cls._windows_disk_types

        types: Dict[str, str] = {}
        script = (
            "$pd = @{}; Get-PhysicalDisk | ForEach-Object { "
            '$pd[[string]$_.DeviceId] = "$($_.MediaType)|$($_.BusType)" }; '
            "Get-Partition | Where-Object DriveLetter | ForEach-Object { "
            '"$($_.DriveLetter)=$($pd[[string]$_.DiskNumber])" }'
        )
        output = cls.run_powershell(script)

        for line in output.splitlines():
            if "=" not in line:
                continue
            letter, _, info = line.partition("=")
            media, _, bus = info.partition("|")
            media = media.strip().upper()
            if "NVME" in bus.strip().upper():
                disk_type = "NVMe"
            elif media == "SSD":
                disk_type = "SSD"
            elif media == "HDD":
                disk_type = "HDD"
            else:
                continue
            types[letter.strip().upper()] = disk_type

        cls._windows_disk_types = types
        return types

    @staticmethod
    def benchmark_speed(
        path: str = None, size_mb: int = 100, timeout: int = 30
    ) -> Optional[Dict[str, Union[str, float]]]:
        """Benchmark disk read and write speeds.

        Writes incompressible random data with fsync, then re-reads it in
        chunks. If the requested directory is not writable (e.g. a drive
        root on Windows), falls back to a writable directory on the same
        drive.

        Note:
            The read test re-reads the file that was just written, so the
            result is typically served from the OS page cache and reflects
            cached read throughput rather than raw disk speed.

        Args:
            path: Directory path for benchmark file. Defaults to the
                system temp directory.
            size_mb: Size of test file in megabytes.
            timeout: Maximum benchmark duration in seconds.

        Returns:
            Dictionary with read/write speeds in MB/s and the directory
            used ('path'), or None on failure.
        """
        target = DiskDetector._writable_benchmark_dir(path)
        if target is None:
            logger.debug(f"No writable benchmark directory found for {path!r}")
            return None

        test_file = os.path.join(target, ".llm_neofetch_benchmark.tmp")
        chunk = os.urandom(1024 * 1024)

        try:
            start = time.time()
            with open(test_file, "wb") as f:
                for _ in range(size_mb):
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
            write_time = time.time() - start

            if write_time > timeout:
                return None

            read_cached = True
            direct_time = DiskDetector._read_file_direct(test_file)
            if direct_time is not None:
                read_time = direct_time
                read_cached = False
            else:
                start = time.time()
                with open(test_file, "rb") as f:
                    while f.read(8 * 1024 * 1024):
                        pass
                read_time = time.time() - start

            return {
                "read_mb_s": size_mb / read_time if read_time > 0 else 0,
                "write_mb_s": size_mb / write_time if write_time > 0 else 0,
                "read_cached": read_cached,
                "path": target,
            }

        except Exception as e:
            logger.debug(f"Disk benchmark failed: {e}")
            return None
        finally:
            try:
                os.remove(test_file)
            except OSError:
                pass

    @staticmethod
    def _read_file_direct(path: str) -> Optional[float]:
        """Read a file bypassing the page cache via O_DIRECT (Linux only).

        Args:
            path: File to read.

        Returns:
            Elapsed seconds, or None if O_DIRECT is unavailable/failed.
        """
        if not sys.platform.startswith("linux") or not hasattr(os, "O_DIRECT"):
            return None

        import mmap

        try:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
        except OSError:
            return None

        try:
            buf = mmap.mmap(-1, 4 * 1024 * 1024)
            start = time.time()
            while True:
                n = os.readv(fd, [buf])
                if n <= 0:
                    break
            return time.time() - start
        except OSError:
            return None
        finally:
            os.close(fd)

    @staticmethod
    def _writable_benchmark_dir(path: Optional[str]) -> Optional[str]:
        """Find a writable directory for the benchmark file.

        Prefers the requested path; falls back to the temp or home
        directory only when they reside on the same drive/device, so the
        benchmark still measures the intended disk.

        Args:
            path: Requested directory, or None for the system temp dir.

        Returns:
            A writable directory path, or None if none is available.
        """
        candidates = []
        if path:
            candidates.append(path)
            for alt in (tempfile.gettempdir(), os.path.expanduser("~")):
                if DiskDetector._same_device(path, alt):
                    candidates.append(alt)
        else:
            candidates.append(tempfile.gettempdir())

        for candidate in candidates:
            try:
                with tempfile.NamedTemporaryFile(dir=candidate):
                    pass
                return candidate
            except OSError:
                continue

        return None

    @staticmethod
    def _same_device(a: str, b: str) -> bool:
        """Check whether two paths reside on the same drive/device.

        Args:
            a: First path.
            b: Second path.

        Returns:
            True if both paths are on the same drive/device.
        """
        try:
            if sys.platform.startswith("win"):
                drive_a = os.path.splitdrive(os.path.abspath(a))[0].lower()
                drive_b = os.path.splitdrive(os.path.abspath(b))[0].lower()
                return drive_a != "" and drive_a == drive_b
            return os.stat(a).st_dev == os.stat(b).st_dev
        except OSError:
            return False


class MemoryBenchmark(BaseDetector):
    """Benchmarks system memory copy bandwidth."""

    @staticmethod
    def run(size_mb: int = 256, rounds: int = 5) -> Optional[Dict[str, float]]:
        """Measure single-threaded memory copy bandwidth.

        Copies a large buffer repeatedly; each copy reads and writes the
        full buffer. Single-threaded memcpy underestimates the total
        multi-channel bandwidth but tracks CPU-inference throughput well.

        Args:
            size_mb: Buffer size in megabytes.
            rounds: Number of copy rounds to average over.

        Returns:
            Dictionary with copy_gb_s, or None on failure.
        """
        try:
            size = size_mb * 1024 * 1024
            src = memoryview(bytearray(size))
            dst = memoryview(bytearray(size))
            dst[:] = src  # warmup / page-fault both buffers

            start = time.perf_counter()
            for _ in range(rounds):
                dst[:] = src
            elapsed = time.perf_counter() - start

            if elapsed <= 0:
                return None
            return {"copy_gb_s": (2 * size * rounds) / elapsed / 1e9}
        except (MemoryError, OverflowError) as e:
            logger.debug(f"Memory benchmark failed: {e}")
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

    # Approximate unified memory bandwidth by chip variant (GB/s)
    _BANDWIDTH_GB_S = {
        "M1": 68, "M1 Pro": 200, "M1 Max": 400, "M1 Ultra": 800,
        "M2": 100, "M2 Pro": 200, "M2 Max": 400, "M2 Ultra": 800,
        "M3": 100, "M3 Pro": 150, "M3 Max": 400, "M3 Ultra": 800,
        "M4": 120, "M4 Pro": 273, "M4 Max": 546,
    }

    @staticmethod
    def detect() -> Optional[Dict[str, Union[str, int, float, bool]]]:
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
        for base in ["M4", "M3", "M2", "M1"]:
            if base in chip:
                chip_variant = base
                for tier in ["Ultra", "Max", "Pro"]:
                    if tier in chip:
                        chip_variant = f"{base} {tier}"
                        break
                break

        info: Dict[str, Union[str, int, float, bool]] = {
            "chip": chip,
            "variant": chip_variant,
            "unified_memory_gb": mem_gb,
            "supports_mlx": True,
        }

        bandwidth = AppleSiliconDetector._BANDWIDTH_GB_S.get(chip_variant, 0)
        if bandwidth:
            info["memory_bandwidth_gb_s"] = bandwidth

        gpu_cores = AppleSiliconDetector._get_gpu_cores()
        if gpu_cores:
            info["gpu_cores"] = gpu_cores

        return info

    @staticmethod
    def _get_gpu_cores() -> int:
        """Get the GPU core count from system_profiler.

        Returns:
            Number of GPU cores, or 0 if unavailable.
        """
        output = AppleSiliconDetector.run_command(
            "system_profiler SPDisplaysDataType 2>/dev/null", timeout=10
        )
        match = re.search(r"Total Number of Cores:\s*(\d+)", output)
        return int(match.group(1)) if match else 0
