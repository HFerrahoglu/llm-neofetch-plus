"""Environment Detection Module.

Detects the LLM runtime environment around the hardware: installed
inference backends, running LLM processes, AI runtimes/drivers,
virtualization (WSL/Docker/cloud), and locally downloaded models.
All detection is best-effort and degrades gracefully.
"""

import glob
import json
import logging
import os
import platform
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from llm_neofetch.detectors import BaseDetector

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://127.0.0.1:11434"


def _http_get_json(url: str, timeout: float = 1.5) -> Optional[Any]:
    """Fetch JSON from a local HTTP endpoint.

    Args:
        url: URL to fetch.
        timeout: Timeout in seconds.

    Returns:
        Parsed JSON, or None on any failure.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.debug(f"HTTP GET {url} failed: {e}")
        return None


class RuntimeDetector(BaseDetector):
    """Detects AI compute runtimes and driver stacks."""

    @staticmethod
    def detect() -> Dict[str, Optional[str]]:
        """Detect CUDA, ROCm, Vulkan, DirectML, and Metal availability.

        Returns:
            Mapping of runtime name to version string (or None if absent).
        """
        runtimes: Dict[str, Optional[str]] = {
            "CUDA": RuntimeDetector._cuda_version(),
            "ROCm": RuntimeDetector._rocm_version(),
            "Vulkan": RuntimeDetector._vulkan_version(),
        }

        if sys.platform.startswith("win"):
            runtimes["DirectML"] = RuntimeDetector._directml_version()
        if sys.platform == "darwin":
            runtimes["Metal"] = "available"

        return runtimes

    @staticmethod
    def _cuda_version() -> Optional[str]:
        if shutil.which("nvidia-smi"):
            output = RuntimeDetector.run_command("nvidia-smi")
            match = re.search(r"CUDA Version:\s*([\d.]+)", output)
            if match:
                return match.group(1)
        if shutil.which("nvcc"):
            output = RuntimeDetector.run_command("nvcc --version")
            match = re.search(r"release\s*([\d.]+)", output)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _rocm_version() -> Optional[str]:
        version_file = Path("/opt/rocm/.info/version")
        try:
            if version_file.exists():
                return version_file.read_text(encoding="utf-8").strip().split("-")[0]
        except OSError:
            pass
        if shutil.which("rocm-smi") or shutil.which("amd-smi"):
            return "installed"
        return None

    @staticmethod
    def _vulkan_version() -> Optional[str]:
        if not shutil.which("vulkaninfo"):
            return None
        output = RuntimeDetector.run_command("vulkaninfo --summary", timeout=10)
        match = re.search(r"apiVersion\s*=\s*([\d.]+)", output)
        if match:
            return match.group(1)
        return "installed" if output else None

    @staticmethod
    def _directml_version() -> Optional[str]:
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        if (system32 / "DirectML.dll").exists():
            return "available"
        return None


class BackendDetector(BaseDetector):
    """Detects installed LLM inference backends."""

    @staticmethod
    def detect() -> List[Dict[str, Any]]:
        """Detect installed backends with version and running state.

        Returns:
            List of dictionaries: name, installed, version, running,
            models_count (where applicable).
        """
        backends = [
            BackendDetector._detect_ollama(),
            BackendDetector._detect_lm_studio(),
            BackendDetector._detect_llama_cpp(),
            BackendDetector._detect_vllm(),
        ]
        return [b for b in backends if b is not None]

    @staticmethod
    def _detect_ollama() -> Optional[Dict[str, Any]]:
        installed = shutil.which("ollama") is not None
        info: Dict[str, Any] = {
            "name": "Ollama",
            "installed": installed,
            "version": None,
            "running": False,
            "models_count": 0,
        }

        if installed:
            output = BackendDetector.run_command("ollama --version")
            match = re.search(r"([\d]+\.[\d]+\.[\d]+)", output)
            if match:
                info["version"] = match.group(1)

        tags = _http_get_json(f"{OLLAMA_URL}/api/tags")
        if tags is not None:
            info["running"] = True
            info["installed"] = True
            info["models_count"] = len(tags.get("models", []))

        return info if info["installed"] else None

    @staticmethod
    def _detect_lm_studio() -> Optional[Dict[str, Any]]:
        candidates = []
        if sys.platform.startswith("win"):
            local = os.environ.get("LOCALAPPDATA", "")
            if local:
                candidates.append(Path(local) / "Programs" / "lm-studio")
                candidates.append(Path(local) / "LM-Studio")
        elif sys.platform == "darwin":
            candidates.append(Path("/Applications/LM Studio.app"))
        else:
            candidates.append(Path.home() / ".lmstudio")

        installed = shutil.which("lms") is not None or any(
            p.exists() for p in candidates
        )
        if not installed:
            return None

        running = any(
            "lm studio" in (proc.info.get("name") or "").lower()
            or "lmstudio" in (proc.info.get("name") or "").lower()
            for proc in psutil.process_iter(["name"])
        )

        return {
            "name": "LM Studio",
            "installed": True,
            "version": None,
            "running": running,
            "models_count": len(ModelScanner.scan_lm_studio()),
        }

    @staticmethod
    def _detect_llama_cpp() -> Optional[Dict[str, Any]]:
        binary = None
        for name in ("llama-server", "llama-cli", "llama.cpp"):
            if shutil.which(name):
                binary = name
                break
        if binary is None:
            return None

        version = None
        output = BackendDetector.run_command(f"{binary} --version")
        match = re.search(r"version:\s*(\S+)", output)
        if match:
            version = match.group(1)

        return {
            "name": "llama.cpp",
            "installed": True,
            "version": version,
            "running": False,
            "models_count": 0,
        }

    @staticmethod
    def _detect_vllm() -> Optional[Dict[str, Any]]:
        if not shutil.which("vllm"):
            return None
        return {
            "name": "vLLM",
            "installed": True,
            "version": None,
            "running": False,
            "models_count": 0,
        }


class ProcessDetector(BaseDetector):
    """Detects running LLM-related processes."""

    _NAME_PATTERNS = re.compile(
        r"ollama|llama-server|llama-cli|lm.?studio|koboldcpp|text-generation|vllm",
        re.IGNORECASE,
    )

    @staticmethod
    def detect() -> List[Dict[str, Any]]:
        """Find running LLM processes with their memory usage.

        Returns:
            List of dictionaries: name, pid, ram_gb, vram_mb (if known).
        """
        processes: List[Dict[str, Any]] = []
        gpu_mem = ProcessDetector._nvidia_process_memory()

        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                name = proc.info.get("name") or ""
                if not ProcessDetector._NAME_PATTERNS.search(name):
                    continue
                mem = proc.info.get("memory_info")
                ram_gb = (mem.rss / (1024**3)) if mem else 0.0
                processes.append(
                    {
                        "name": name,
                        "pid": proc.info["pid"],
                        "ram_gb": ram_gb,
                        "vram_mb": gpu_mem.get(proc.info["pid"], 0),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return processes

    @staticmethod
    def _nvidia_process_memory() -> Dict[int, float]:
        """Get per-process GPU memory usage from nvidia-smi.

        Returns:
            Mapping of PID to VRAM usage in MB.
        """
        result: Dict[int, float] = {}
        if not shutil.which("nvidia-smi"):
            return result

        output = ProcessDetector.run_command(
            "nvidia-smi --query-compute-apps=pid,used_memory "
            "--format=csv,noheader,nounits"
        )
        for line in output.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    result[int(parts[0])] = float(parts[1])
                except ValueError:
                    continue
        return result


class EnvironmentDetector(BaseDetector):
    """Detects the execution environment (WSL, Docker, cloud, bare metal)."""

    @staticmethod
    def detect() -> str:
        """Identify the execution environment.

        Returns:
            Environment description, e.g. "WSL2", "Docker",
            "AWS EC2", or "Bare metal".
        """
        env = []

        if sys.platform.startswith("linux"):
            release = platform.uname().release.lower()
            if "microsoft" in release:
                env.append("WSL2" if "wsl2" in release else "WSL")
            if os.path.exists("/.dockerenv"):
                env.append("Docker")
            else:
                try:
                    with open("/proc/1/cgroup", encoding="utf-8") as f:
                        content = f.read()
                    if "docker" in content or "containerd" in content:
                        env.append("Docker")
                except OSError:
                    pass

        cloud = EnvironmentDetector._cloud_vendor()
        if cloud:
            env.append(cloud)

        return " / ".join(env) if env else "Bare metal"

    @staticmethod
    def _cloud_vendor() -> Optional[str]:
        """Detect a cloud provider from DMI vendor strings.

        Returns:
            Cloud provider name, or None.
        """
        vendor = ""
        if sys.platform.startswith("linux"):
            for path in (
                "/sys/class/dmi/id/sys_vendor",
                "/sys/class/dmi/id/product_name",
            ):
                try:
                    with open(path, encoding="utf-8") as f:
                        vendor += f.read().strip() + " "
                except OSError:
                    continue
        elif sys.platform.startswith("win"):
            vendor = EnvironmentDetector.run_powershell(
                "(Get-CimInstance Win32_ComputerSystem).Manufacturer + ' ' + "
                "(Get-CimInstance Win32_ComputerSystem).Model"
            )

        vendor_lower = vendor.lower()
        if "amazon" in vendor_lower or "ec2" in vendor_lower:
            return "AWS EC2"
        if "google" in vendor_lower:
            return "Google Cloud"
        if "microsoft corporation" in vendor_lower and "virtual" in vendor_lower:
            return "Azure"
        if "openstack" in vendor_lower:
            return "OpenStack"
        if "vmware" in vendor_lower:
            return "VMware VM"
        if "virtualbox" in vendor_lower:
            return "VirtualBox VM"
        if "qemu" in vendor_lower or "kvm" in vendor_lower:
            return "QEMU/KVM VM"
        return None


class ModelScanner(BaseDetector):
    """Scans for locally downloaded LLM models."""

    @staticmethod
    def scan() -> List[Dict[str, Any]]:
        """Scan Ollama and LM Studio for downloaded models.

        Returns:
            List of dictionaries: name, size_gb, source.
        """
        models = ModelScanner.scan_ollama() + ModelScanner.scan_lm_studio()
        models.sort(key=lambda m: m["size_gb"], reverse=True)
        return models

    @staticmethod
    def scan_ollama() -> List[Dict[str, Any]]:
        """List models from a running Ollama instance.

        Returns:
            List of model dictionaries (empty if Ollama isn't running).
        """
        models: List[Dict[str, Any]] = []
        tags = _http_get_json(f"{OLLAMA_URL}/api/tags")
        if not tags:
            return models

        for model in tags.get("models", []):
            name = model.get("name", "?")
            size_gb = model.get("size", 0) / (1024**3)
            models.append({"name": name, "size_gb": size_gb, "source": "Ollama"})

        return models

    @staticmethod
    def scan_lm_studio() -> List[Dict[str, Any]]:
        """Scan LM Studio model directories for GGUF files.

        Returns:
            List of model dictionaries.
        """
        models: List[Dict[str, Any]] = []
        candidates = [
            Path.home() / ".lmstudio" / "models",
            Path.home() / ".cache" / "lm-studio" / "models",
        ]

        for base in candidates:
            if not base.exists():
                continue
            for gguf in glob.glob(str(base / "**" / "*.gguf"), recursive=True):
                try:
                    size_gb = os.path.getsize(gguf) / (1024**3)
                except OSError:
                    continue
                models.append(
                    {
                        "name": Path(gguf).stem,
                        "size_gb": size_gb,
                        "source": "LM Studio",
                    }
                )
            break

        return models


class OllamaBenchmark(BaseDetector):
    """Benchmarks real generation speed via the Ollama API."""

    @staticmethod
    def run(
        model: Optional[str] = None, timeout: float = 120.0
    ) -> Optional[Dict[str, Any]]:
        """Run a short generation and measure real tokens/second.

        Uses Ollama's reported eval_count/eval_duration for accuracy.

        Args:
            model: Model name; defaults to the smallest installed model.
            timeout: Request timeout in seconds (model load can be slow).

        Returns:
            Dictionary with model, tokens_per_second, prompt_tokens_per_second,
            or None if Ollama is unavailable.
        """
        if model is None:
            installed = ModelScanner.scan_ollama()
            if not installed:
                return None
            model = min(installed, key=lambda m: m["size_gb"])["name"]

        payload = json.dumps(
            {
                "model": model,
                "prompt": "Write one short sentence about local LLMs.",
                "stream": False,
                "options": {"num_predict": 64},
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as e:
            logger.debug(f"Ollama benchmark failed: {e}")
            return None

        result: Dict[str, Any] = {"model": model}

        eval_count = data.get("eval_count", 0)
        eval_duration = data.get("eval_duration", 0)  # nanoseconds
        if eval_count and eval_duration:
            result["tokens_per_second"] = eval_count / (eval_duration / 1e9)

        prompt_count = data.get("prompt_eval_count", 0)
        prompt_duration = data.get("prompt_eval_duration", 0)
        if prompt_count and prompt_duration:
            result["prompt_tokens_per_second"] = prompt_count / (
                prompt_duration / 1e9
            )

        return result if "tokens_per_second" in result else None
