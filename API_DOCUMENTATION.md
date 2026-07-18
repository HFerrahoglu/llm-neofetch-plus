# LLM-Neofetch++ API Documentation

This document provides comprehensive information on using LLM-Neofetch++ as a Python library
for system hardware detection and display.

## Installation

```bash
pip install llm-neofetch-plus
```

```python
from llm_neofetch import LLMNeofetch
```

## Quick Start

```python
from llm_neofetch import LLMNeofetch

app = LLMNeofetch()
info = app.collect_system_info()
app.display_system_info(info, detail_level=2)
```

## Core Classes

### LLMNeofetch

Main application class that coordinates configuration loading, system information gathering,
and UI rendering.

**Attributes:**
- `config` (dict): Configuration dictionary loaded from YAML.
- `ui` (UIRenderer): Terminal UI renderer instance.
- `verbose` (bool): Enable detailed logging.

**Methods:**

#### `__init__(config_path: str = None, verbose: bool = False)`

Initialize the application.

**Args:**
- `config_path`: Optional path to custom config file.
- `verbose`: Enable debug logging.

#### `collect_system_info(benchmark: bool = False) -> dict`

Collect all system information from detectors.

**Args:**
- `benchmark`: Run disk speed benchmark if True.

**Returns:**
- Dictionary containing all system information.

#### `display_system_info(info: dict, detail_level: int = 2)`

Display system information to terminal.

**Args:**
- `info`: System information dictionary.
- `detail_level`: 1=minimal, 2=normal, 3=detailed.

#### `export(info: dict, format: str, output_file: str)`

Export system info to file.

**Args:**
- `info`: System information dictionary.
- `format`: Export format (json, yaml, markdown).
- `output_file`: Path to output file.

## Detector Modules

### OSDetector

Detects operating system and basic system information.

```python
from llm_neofetch.detectors import OSDetector

os_info = OSDetector.detect()
print(os_info["platform"])  # "Linux-6.5.0-x86_64..."
print(os_info["system"])    # "Linux"

uptime = OSDetector.get_uptime()
print(f"{uptime['days']}d {uptime['hours']}h")
```

**Returns:**
- `dict`: OS details including system, release, version, machine, platform, python_version.

### CPUDetector

Detects CPU information including cores, frequency, and temperature.

```python
from llm_neofetch.detectors import CPUDetector

cpu_info = CPUDetector.detect()

print(cpu_info["name"])              # "AMD Ryzen 9 7950X"
print(cpu_info["cores_physical"])    # 16
print(cpu_info["cores_logical"])      # 32
print(cpu_info["current_freq_mhz"])  # 4200.0
print(cpu_info["usage_percent"])     # 35.2
print(cpu_info["temperature_c"])      # 58.5 or None
```

**Returns:**
- `dict`: CPU specifications and current state (name, cores_physical, cores_logical, current_freq_mhz, max_freq_mhz, usage_percent, temperature_c).

### GPUDetector

Detects GPU information from NVIDIA, AMD, Intel, or WMI.

```python
from llm_neofetch.detectors import GPUDetector

gpus = GPUDetector.detect()

for gpu in gpus:
    print(f"GPU: {gpu['name']}")
    print(f"  Vendor: {gpu['vendor']}")
    print(f"  VRAM: {gpu['vram_total_gb']:.1f} GB")
    print(f"  Used: {gpu['vram_used_gb']:.1f} GB")
    print(f"  Utilization: {gpu['utilization_percent']}%")
    print(f"  Temperature: {gpu['temperature_c']}°C")
```

**Returns:**
- `list[dict]`: List of GPU information dictionaries.

### MemoryDetector

Detects RAM and swap memory information.

```python
from llm_neofetch.detectors import MemoryDetector

mem_info = MemoryDetector.detect()

ram_gb = mem_info["ram_total_bytes"] / (1024**3)
available_gb = mem_info["ram_available_bytes"] / (1024**3)
swap_gb = mem_info["swap_total_bytes"] / (1024**3)

print(f"Total RAM: {ram_gb:.1f} GB")
print(f"Available: {available_gb:.1f} GB")
print(f"Usage: {mem_info['ram_percent']}%")
print(f"Swap: {swap_gb:.1f} GB ({mem_info['swap_percent']}% used)")
```

**Returns:**
- `dict`: Memory statistics (ram_total_bytes, ram_available_bytes, ram_used_bytes, ram_percent, swap_total_bytes, swap_used_bytes, swap_percent).

### DiskDetector

Detects disk storage information including type (SSD/NVMe/HDD).

```python
from llm_neofetch.detectors import DiskDetector

disks = DiskDetector.detect()

for disk in disks:
    print(f"Mount: {disk['mountpoint']}")
    print(f"  Type: {disk['type']}")  # NVMe, SSD, HDD
    print(f"  Total: {disk['total_bytes'] / (1024**3):.1f} GB")
    print(f"  Free: {disk['free_bytes'] / (1024**3):.1f} GB")
    print(f"  Usage: {disk['percent']}%")
```

**Returns:**
- `list[dict]`: List of disk information dictionaries sorted by system drives first.

#### `benchmark_speed(path: str = None, size_mb: int = 100, timeout: int = 30) -> dict | None`

Benchmark disk read and write speeds.

**Args:**
- `path`: Directory path for benchmark file. Defaults to the system temp
  directory. Falls back to a writable directory on the same drive if the
  requested path is not writable.
- `size_mb`: Size of test file in megabytes.
- `timeout`: Maximum benchmark duration in seconds.

**Returns:**
- Dictionary with read/write speeds in MB/s and the directory used
  (`path`), or None on failure. Note: read speed may include the OS page
  cache.

### BatteryDetector

Detects battery information on laptops.

```python
from llm_neofetch.detectors import BatteryDetector

battery = BatteryDetector.detect()

if battery:
    print(f"Battery: {battery['percent']}%")
    print(f"Plugged: {battery['plugged']}")
    print(f"Time Left: {battery['time_left']}")
```

**Returns:**
- `dict | None`: Battery details (percent, plugged, time_left, time_left_seconds) or None if unavailable.

### MotherboardDetector

Detects motherboard information.

```python
from llm_neofetch.detectors import MotherboardDetector

board = MotherboardDetector.detect()
print(board)  # "ASUS ROG Strix X670E-E Gaming WiFi"
```

**Returns:**
- `str`: Manufacturer and product name, or "N/A" if unavailable.

### AppleSiliconDetector

Detects Apple Silicon (M-series) chip information.

```python
from llm_neofetch.detectors import AppleSiliconDetector

apple = AppleSiliconDetector.detect()

if apple:
    print(f"Chip: {apple['chip']}")
    print(f"Variant: {apple['variant']}")  # M1, M2, M3, M4
    print(f"Unified Memory: {apple['unified_memory_gb']:.1f} GB")
    print(f"MLX Support: {apple['supports_mlx']}")
```

**Returns:**
- `dict | None`: Chip details or None if not Apple Silicon.

## LLM Math (`llm_neofetch.llm_math`)

Planning heuristics for model memory and speed. All functions are pure.

```python
from llm_neofetch import llm_math

llm_math.weights_gb(8, 4.5)                  # ~4.2 GiB for 8B @ Q4_K_M
llm_math.kv_cache_gb(8, 65536)               # KV cache at 64K context
llm_math.total_memory_gb(8, 4.5, 8192)       # weights + KV + overhead
llm_math.max_context_tokens(8, 4.5, 12.0)    # max context in a 12 GB budget
llm_math.tokens_per_second(4.2, 400)         # bandwidth-bound speed estimate
llm_math.finetune_vram_gb(8, "qlora")        # fine-tuning VRAM estimate
llm_math.parse_model_size("llama3.1:70b")    # 70.0
llm_math.parse_quant("8b-instruct-q4_K_M")   # "Q4_K_M"
```

## Environment Detection (`llm_neofetch.environment`)

```python
from llm_neofetch.environment import (
    BackendDetector,     # installed Ollama/LM Studio/llama.cpp/vLLM
    EnvironmentDetector, # "Bare metal", "WSL2", "Docker", "AWS EC2", ...
    ModelScanner,        # locally downloaded models (name, size_gb, source)
    OllamaBenchmark,     # real tokens/s via the Ollama API
    ProcessDetector,     # running LLM processes with RAM/VRAM usage
    RuntimeDetector,     # CUDA/ROCm/Vulkan/DirectML/Metal versions
)

backends = BackendDetector.detect()
models = ModelScanner.scan()
result = OllamaBenchmark.run()   # None if Ollama isn't reachable
```

All detection is best-effort: on systems without the relevant tools these
return empty lists / None values instead of raising.

## UI Renderer

### UIRenderer

Handles all visual output, formatting, and display for terminal.

```python
from llm_neofetch.ui import UIRenderer
import yaml

with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

ui = UIRenderer(config)

ui.print_header()
ui.print_section_header("My Section")
ui.print_kv("CPU", "AMD Ryzen 9")
ui.print_kv("RAM", "64 GB")
```

**Methods:**

#### `format_size(bytes_val: int | float, suffix: str = "B") -> str`

Format bytes into human-readable size.

**Args:**
- `bytes_val`: Number of bytes.
- `suffix`: Unit suffix (default 'B').

**Returns:**
- Formatted string like "1.5 GiB" or "500 MiB".

#### `bar(value: float, max_value: float, width: int = 30, invert: bool = False, show_percent: bool = True) -> rich.text.Text`

Build a colored usage bar.

**Args:**
- `value`: Current value.
- `max_value`: Maximum value.
- `width`: Bar character width.
- `invert`: Treat high values as good (colored green, e.g. battery charge).
- `show_percent`: Append the percentage after the bar.

**Returns:**
- Rich `Text` renderable.

#### `print_bar(label: str, value: float, max_value: float, indent: int = 2, invert: bool = False)`

Print a labeled usage bar aligned with key-value rows.

#### `print_gpu_info(gpu: dict)`

Print detailed GPU information with VRAM bar and stats.

#### `print_disk_info(disk: dict)`

Print disk information with type badge and usage bar.

#### `print_model_recommendations(vram_gb: float, ram_gb: float, disk_type: str, config: dict)`

Print personalized LLM model recommendations based on hardware.

#### `print_quantization_guide(config: dict)`

Print GGUF quantization format guide.

#### `print_backend_comparison(config: dict)`

Print comparison of LLM inference backends.

#### `print_tips(vram_gb: float, ram_gb: float, swap_gb: float, disk_type: str)`

Print optimization tips based on system configuration.

#### `print_benchmark_results(results: dict)`

Print disk benchmark results with speed classification.

### ExportFormatter

Formats system information for export to various file formats.

```python
from llm_neofetch.ui import ExportFormatter, UIRenderer

formatter = ExportFormatter()
ui = UIRenderer()

system_data = {
    "cpu": CPUDetector.detect(),
    "gpus": GPUDetector.detect(),
    "memory": MemoryDetector.detect(),
}

json_output = formatter.to_json(system_data)
yaml_output = formatter.to_yaml(system_data)
md_output = formatter.to_markdown(system_data, ui)

with open("report.json", "w", encoding="utf-8") as f:
    f.write(json_output)
```

**Methods:**

#### `to_json(data: dict) -> str`

Convert system info to formatted JSON.

#### `to_yaml(data: dict) -> str`

Convert system info to YAML format.

#### `to_markdown(data: dict, ui: UIRenderer) -> str`

Convert system info to Markdown format.

## Complete Examples

### Example 1: Basic System Check

```python
from llm_neofetch import LLMNeofetch

app = LLMNeofetch()
info = app.collect_system_info()
app.display_system_info(info, detail_level=2)
```

### Example 2: Hardware-Based Model Recommendation

```python
from llm_neofetch.detectors import GPUDetector, MemoryDetector

def recommend_model():
    """Recommend models based on hardware capabilities."""
    gpus = GPUDetector.detect()
    mem = MemoryDetector.detect()

    vram = max([g["vram_total_gb"] for g in gpus], default=0)
    ram_gb = mem["ram_total_bytes"] / (1024**3)

    recommendations = []

    if vram >= 24:
        recommendations.append({
            "size": "70B",
            "quant": "Q4_K_M",
            "models": ["Llama 3.1 70B", "Qwen2.5 72B"],
            "tokens_per_sec": "35-45"
        })
    elif vram >= 12:
        recommendations.append({
            "size": "32B",
            "quant": "Q4_K_M",
            "models": ["Llama 3.1 33B", "Qwen2.5 32B"],
            "tokens_per_sec": "50-70"
        })

    if ram_gb >= 32:
        recommendations.append({
            "size": "13-14B",
            "quant": "Q5_K_M",
            "models": ["Llama 2 13B", "Qwen2.5 14B"],
            "tokens_per_sec": "10-25 (CPU)",
            "backend": "llama.cpp with CPU"
        })

    return recommendations

for rec in recommend_model():
    print(f"Model Size: {rec['size']}")
    print(f"Quantization: {rec['quant']}")
    print(f"Examples: {', '.join(rec['models'])}")
    print(f"Speed: {rec['tokens_per_sec']} tok/s\n")
```

### Example 3: System Monitoring

```python
import time
from llm_neofetch.detectors import CPUDetector, GPUDetector

def monitor_system(duration_seconds: int = 60, interval: int = 5):
    """Monitor system resources."""
    print("Monitoring started...")
    start = time.time()

    while time.time() - start < duration_seconds:
        cpu = CPUDetector.detect()
        print(f"\n[{time.strftime('%H:%M:%S')}]")
        print(f"  CPU: {cpu['usage_percent']:.1f}%", end="")
        if cpu["temperature_c"]:
            print(f" @ {cpu['temperature_c']:.0f}°C")
        else:
            print()

        gpus = GPUDetector.detect()
        for i, gpu in enumerate(gpus):
            if gpu["utilization_percent"] > 0:
                print(f"  GPU {i}: {gpu['utilization_percent']}%", end="")
                if gpu["temperature_c"]:
                    print(f" @ {gpu['temperature_c']:.0f}°C")
                else:
                    print()

        time.sleep(interval)

monitor_system(duration_seconds=60, interval=5)
```

### Example 4: Export System Report

```python
from llm_neofetch import LLMNeofetch

app = LLMNeofetch()
info = app.collect_system_info(benchmark=True)

app.export(info, "json", "system_report.json")
app.export(info, "yaml", "system_report.yaml")
app.export(info, "markdown", "system_report.md")
```

### Example 5: Compare Two Systems

```python
import json

def compare_systems(system1_file: str, system2_file: str):
    """Compare two systems from exported JSON files."""
    with open(system1_file) as f:
        sys1 = json.load(f)

    with open(system2_file) as f:
        sys2 = json.load(f)

    print("CPU Comparison:")
    print(f"  System 1: {sys1['cpu']['cores_logical']} threads")
    print(f"  System 2: {sys2['cpu']['cores_logical']} threads")

    vram1 = max([g["vram_total_gb"] for g in sys1["gpus"]], default=0)
    vram2 = max([g["vram_total_gb"] for g in sys2["gpus"]], default=0)

    print(f"\nVRAM Comparison:")
    print(f"  System 1: {vram1:.1f} GB")
    print(f"  System 2: {vram2:.1f} GB")

    if vram1 > vram2:
        print("\nSystem 1 is better for LLM inference")
    else:
        print("\nSystem 2 is better for LLM inference")

compare_systems("workstation.json", "laptop.json")
```

## Contributing

To contribute to the API:

1. Create a new detector class inheriting from `BaseDetector`
2. Implement the `detect()` method
3. Add unit tests
4. Submit a pull request

For more information, see the Contributing section in the README.
