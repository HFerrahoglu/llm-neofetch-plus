"""UI Rendering Module.

Handles all visual output, formatting, and display for terminal.
"""

import json
import math
import re
from typing import Dict, Optional, Union

import yaml


class Colors:
    """Terminal ANSI color codes for styled output."""

    def __init__(self, config: Optional[Dict] = None):
        if config and "colors" in config:
            c = config["colors"]
            self.primary = c.get("primary", "\033[1;34m")
            self.secondary = c.get("secondary", "\033[1;36m")
            self.success = c.get("success", "\033[1;32m")
            self.warning = c.get("warning", "\033[1;33m")
            self.danger = c.get("danger", "\033[1;31m")
            self.info = c.get("info", "\033[1;35m")
            self.reset = c.get("reset", "\033[0m")
            self.bold = c.get("bold", "\033[1m")
            self.dim = c.get("dim", "\033[2m")
        else:
            self.primary = "\033[1;34m"
            self.secondary = "\033[1;36m"
            self.success = "\033[1;32m"
            self.warning = "\033[1;33m"
            self.danger = "\033[1;31m"
            self.info = "\033[1;35m"
            self.reset = "\033[0m"
            self.bold = "\033[1m"
            self.dim = "\033[2m"


class UIRenderer:
    """Main UI rendering class for terminal output.

    Handles all visual display including headers, sections,
    progress bars, GPU info, disk info, and recommendations.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.colors = Colors(config)
        self.width = self.config.get("ui", {}).get("box_width", 76)
        self.use_emoji = self.config.get("ui", {}).get("use_emoji", True)
        self.show_progress = self.config.get("ui", {}).get("show_progress_bars", True)

    def format_size(self, bytes_val: Union[int, float], suffix: str = "B") -> str:
        """Format bytes into human-readable size with unit suffix.

        Args:
            bytes_val: Number of bytes.
            suffix: Unit suffix (default 'B' for bytes).

        Returns:
            Formatted string like "1.5 GiB" or "500 MiB".
        """
        if bytes_val == 0:
            return "0 B"

        units = ["", "Ki", "Mi", "Gi", "Ti", "Pi"]
        i = int(math.log(bytes_val, 1024))
        i = min(i, len(units) - 1)
        p = 1024**i

        return f"{bytes_val / p:.1f} {units[i]}{suffix}"

    def progress_bar(
        self,
        value: float,
        max_value: float,
        width: int = 20,
        label: str = "",
        show_percent: bool = True,
    ) -> str:
        """Generate a visual progress bar with optional label.

        Args:
            value: Current value.
            max_value: Maximum value.
            width: Bar character width.
            label: Optional label text.
            show_percent: Show percentage on the right.

        Returns:
            Formatted progress bar string.
        """
        if max_value == 0:
            percent = 0
        else:
            percent = min(100, (value / max_value) * 100)

        filled = int(width * percent / 100)
        bar = "█" * filled + "░" * (width - filled)

        if percent < 50:
            color = self.colors.success
        elif percent < 75:
            color = self.colors.warning
        else:
            color = self.colors.danger

        result = f"{label:<15}" if label else ""
        result += f"[{color}{bar}{self.colors.reset}]"

        if show_percent:
            result += f" {percent:5.1f}%"

        return result

    def print_header(self):
        """Print the main application header with logo."""
        c = self.colors

        logo = f"""
{c.secondary}╔{'═' * (self.width - 2)}╗{c.reset}
{c.secondary}║{c.reset}{c.warning}{self.center_text('🗲 LLM • NEOFETCH ++ 🗲', self.width - 2)}{c.secondary}║{c.reset}
{c.secondary}║{c.reset}{self.center_text('Advanced System Info for Local LLM Usage', self.width - 2)}{c.secondary}║{c.reset}
{c.secondary}║{c.reset}{self.center_text('2026 Edition', self.width - 2)}{c.secondary}║{c.reset}
{c.secondary}╚{'═' * (self.width - 2)}╝{c.reset}
"""
        print(logo)

    def print_section_header(self, title: str):
        """Print a section header with icon and divider.

        Args:
            title: Section title text.
        """
        c = self.colors
        icon = self._get_section_icon(title)
        print(f"\n{c.primary}{'─' * self.width}{c.reset}")
        print(f"{c.bold}{c.secondary}{icon} {title}{c.reset}")
        print(f"{c.primary}{'─' * self.width}{c.reset}")

    def _get_section_icon(self, title: str) -> str:
        """Get emoji icon for a section based on title keywords.

        Args:
            title: Section title.

        Returns:
            Emoji icon string.
        """
        if not self.use_emoji:
            return "▶"

        icons = {
            "System": "💻",
            "CPU": "🔧",
            "GPU": "🎮",
            "Memory": "🧠",
            "Storage": "💾",
            "Battery": "🔋",
            "Performance": "📊",
            "Recommendations": "🎯",
            "Benchmarks": "⚡",
            "LLM Backends": "🚀",
            "Quick Start": "🏁",
        }

        for key, icon in icons.items():
            if key.lower() in title.lower():
                return icon

        return "▶"

    def print_kv(self, key: str, value: str, indent: int = 2):
        """Print a key-value pair with consistent formatting.

        Args:
            key: Label text.
            value: Value text.
            indent: Number of leading spaces.
        """
        c = self.colors
        padding = " " * indent
        print(f"{padding}{c.success}{key:<14}{c.reset} {value}")

    def print_gpu_info(self, gpu: Dict):
        """Print detailed GPU information with VRAM bar and stats.

        Args:
            gpu: Dictionary containing GPU details.
        """
        c = self.colors

        name = gpu["name"]
        vendor = gpu["vendor"]
        vram_total = gpu["vram_total_gb"]
        vram_used = gpu["vram_used_gb"]
        util = gpu["utilization_percent"]
        temp = gpu["temperature_c"]

        vendor_icon = {
            "NVIDIA": "🟢",
            "AMD": "🔴",
            "Intel": "🔵",
        }.get(vendor, "⚪") if self.use_emoji else ""

        print(f"    {vendor_icon} {c.bold}{name}{c.reset}")

        if vram_total > 0:
            print(f"      VRAM: {vram_total:.1f} GB total")
            if vram_used > 0:
                vram_bar = self.progress_bar(
                    vram_used, vram_total, width=25, label="", show_percent=False
                )
                print(f"            {vram_bar} {vram_used:.1f}/{vram_total:.1f} GB")

        if util > 0:
            util_bar = self.progress_bar(util, 100, width=25, label="Usage")
            print(f"      {util_bar}")

        if temp:
            temp_color = (
                c.success if temp < 60 else c.warning if temp < 80 else c.danger
            )
            print(f"      Temp: {temp_color}{temp:.0f}°C{c.reset}")

    def print_disk_info(self, disk: Dict):
        """Print disk information with type badge and usage bar.

        Args:
            disk: Dictionary containing disk details.
        """
        c = self.colors

        mountpoint = disk["mountpoint"]
        total = disk["total_bytes"]
        free = disk["free_bytes"]
        used = disk["used_bytes"]
        disk_type = disk["type"]

        type_badges = {
            "NVMe": f"{c.success}[NVMe]{c.reset}",
            "SSD": f"{c.info}[SSD]{c.reset}",
            "HDD": f"{c.dim}[HDD]{c.reset}",
        }
        badge = type_badges.get(disk_type, f"[{disk_type}]")

        print(f"    {c.bold}{mountpoint}{c.reset} {badge}")
        print(f"      Total: {self.format_size(total)}  •  Free: {self.format_size(free)}")

        if self.show_progress:
            usage_bar = self.progress_bar(used, total, width=30, label="Usage")
            print(f"      {usage_bar}")

    def print_model_recommendations(
        self, vram_gb: float, ram_gb: float, disk_type: str, config: Dict
    ):
        """Print personalized LLM model recommendations based on hardware.

        Args:
            vram_gb: Available GPU VRAM in GB.
            ram_gb: Available RAM in GB.
            disk_type: Primary disk type.
            config: Configuration dictionary with model recommendations.
        """
        c = self.colors

        print(f"\n{c.warning}{'─' * self.width}{c.reset}")
        print(f"{c.bold}{c.warning}🎯 Personalized Model Recommendations{c.reset}")
        print(f"{c.warning}{'─' * self.width}{c.reset}\n")

        models = config.get("models", {})

        suitable_models = []

        for category, info in models.items():
            vram_min = info.get("vram_min", 0)
            ram_min = info.get("ram_min", 0)

            if vram_gb >= vram_min and ram_gb >= ram_min:
                suitable_models.append((category, info))

        if not suitable_models:
            print(
                f"  {c.dim}Your system can run basic models with CPU inference.{c.reset}"
            )
            return

        for category, info in suitable_models:
            size_range = info.get("size_range", "")
            examples = info.get("examples", [])

            category_names = {
                "tiny": "Tiny Models (Lightning Fast)",
                "small": "Small Models (Excellent Balance)",
                "medium": "Medium Models (High Quality)",
                "large": "Large Models (Superior Performance)",
                "xlarge": "Extra Large Models (Maximum Capability)",
            }

            name = category_names.get(category, category.capitalize())

            print(f"  {c.success}▸{c.reset} {c.bold}{name}{c.reset} ({size_range})")

            for example in examples[:3]:
                print(f"    • {example}")

            print()

    def print_quantization_guide(self, config: Dict):
        """Print GGUF quantization format guide.

        Args:
            config: Configuration dictionary with quantization info.
        """
        c = self.colors

        print(f"\n{c.info}📊 Quantization Guide (GGUF){c.reset}")
        print(f"{c.dim}{'─' * 60}{c.reset}\n")

        quants = config.get("quantization", {}).get("gguf", {})

        for quant_name, info in quants.items():
            quality = info.get("quality", "")
            use_case = info.get("use_case", "")

            print(
                f"  {c.bold}{quant_name:8}{c.reset}  {quality:15}  {c.dim}{use_case}{c.reset}"
            )

    def print_backend_comparison(self, config: Dict):
        """Print comparison of LLM inference backends.

        Args:
            config: Configuration dictionary with backend info.
        """
        c = self.colors

        backends = config.get("backends", {})

        print(f"  {'Backend':<15} {'Ease':<6} {'Speed':<6} {'Features':<8} {'Platforms'}")
        print(f"  {c.dim}{'-' * 70}{c.reset}")

        for name, info in backends.items():
            ease = "⭐" * info.get("ease_of_use", 0)
            speed = "⭐" * info.get("performance", 0)
            features = "⭐" * info.get("features", 0)
            platforms = ", ".join(info.get("platforms", []))[:20]

            display_name = name.replace("_", " ").title()

            print(
                f"  {c.bold}{display_name:<15}{c.reset} {ease:<6} {speed:<6} {features:<8} {c.dim}{platforms}{c.reset}"
            )

    def print_quick_start(self):
        """Print quick start command suggestions for running local LLMs."""
        c = self.colors

        commands = [
            ("Test with tiny model", "ollama run llama3.2:1b"),
            ("Run popular 7B model", "ollama run qwen2.5:7b"),
            ("Try coding assistant", "ollama run deepseek-coder:6.7b"),
            ("Best quality 9B", "ollama run gemma2:9b"),
        ]

        print(f"\n  {c.dim}Try these commands:{c.reset}\n")

        for desc, cmd in commands:
            print(
                f"  {c.success}▸{c.reset} {desc:<25} {c.dim}${c.reset} {c.bold}{cmd}{c.reset}"
            )

    def print_tips(
        self,
        vram_gb: float,
        ram_gb: float,
        swap_gb: float,
        disk_type: str,
    ):
        """Print optimization tips based on system configuration.

        Args:
            vram_gb: Available GPU VRAM.
            ram_gb: Available RAM.
            swap_gb: Available swap space.
            disk_type: Primary disk type.
        """
        c = self.colors

        tips = []

        if vram_gb < 8:
            tips.append(
                f"{c.warning}⚠{c.reset}  Low VRAM - Use CPU inference or smaller quantized models"
            )
        elif vram_gb >= 24:
            tips.append(
                f"{c.success}✓{c.reset}  Excellent VRAM - Can run 70B models with Q4 quantization"
            )

        if ram_gb >= 32:
            tips.append(
                f"{c.success}✓{c.reset}  Good RAM - CPU-only inference viable for 13-30B models"
            )

        if swap_gb < 16 and ram_gb < 64:
            tips.append(
                f"{c.warning}⚠{c.reset}  Consider increasing swap/pagefile to 16-32 GB for large models"
            )

        if disk_type in ["NVMe", "SSD"]:
            tips.append(
                f"{c.success}✓{c.reset}  Fast storage - Quick model loading and context management"
            )
        else:
            tips.append(
                f"{c.info}ℹ{c.reset}  Consider SSD/NVMe for faster model loading"
            )

        if tips:
            print(f"\n{c.primary}💡 Optimization Tips:{c.reset}\n")
            for tip in tips:
                print(f"  {tip}")

    def center_text(self, text: str, width: int) -> str:
        """Center text within specified width, ignoring ANSI codes.

        Args:
            text: Text to center.
            width: Total width.

        Returns:
            Centered text string.
        """
        clean_text = re.sub(r"\033\[[0-9;]+m", "", text)
        padding = max(0, width - len(clean_text))
        left_pad = padding // 2
        right_pad = padding - left_pad
        return " " * left_pad + text + " " * right_pad

    def print_benchmark_results(self, results: Dict):
        """Print disk benchmark results with speed classification.

        Args:
            results: Dictionary with read/write speeds.
        """
        c = self.colors

        if not results:
            return

        read_speed = results.get("read_mb_s", 0)
        write_speed = results.get("write_mb_s", 0)

        def classify_speed(speed: float) -> str:
            if speed >= 2000:
                return c.success + "Excellent (NVMe)" + c.reset
            if speed >= 500:
                return c.info + "Good (SATA SSD)" + c.reset
            if speed >= 100:
                return c.warning + "Moderate" + c.reset
            return c.danger + "Slow (HDD)" + c.reset

        print(f"    Read:  {read_speed:7.1f} MB/s  {classify_speed(read_speed)}")
        print(f"    Write: {write_speed:7.1f} MB/s  {classify_speed(write_speed)}")


class ExportFormatter:
    """Formats system information for export to various file formats."""

    @staticmethod
    def to_json(data: Dict) -> str:
        """Convert system info to formatted JSON.

        Args:
            data: System information dictionary.

        Returns:
            JSON string with indentation.
        """
        return json.dumps(data, indent=2)

    @staticmethod
    def to_yaml(data: Dict) -> str:
        """Convert system info to YAML format.

        Args:
            data: System information dictionary.

        Returns:
            YAML string.
        """
        return yaml.dump(data, default_flow_style=False)

    @staticmethod
    def to_markdown(data: Dict, ui: UIRenderer) -> str:
        """Convert system info to Markdown format.

        Args:
            data: System information dictionary.
            ui: UIRenderer instance for formatting.

        Returns:
            Markdown formatted string.
        """
        md = "# LLM-Neofetch++ System Report\n\n"
        md += f"Generated: {data.get('timestamp', 'N/A')}\n\n"

        md += "## System Information\n\n"
        os_info = data.get("os", {})
        md += f"- **OS**: {os_info.get('platform', 'N/A')}\n"
        md += f"- **Kernel**: {os_info.get('release', 'N/A')}\n"
        md += f"- **Architecture**: {os_info.get('machine', 'N/A')}\n\n"

        md += "## CPU\n\n"
        cpu = data.get("cpu", {})
        md += f"- **Model**: {cpu.get('name', 'N/A')}\n"
        md += f"- **Cores**: {cpu.get('cores_physical', 0)} physical / {cpu.get('cores_logical', 0)} logical\n"
        md += f"- **Frequency**: {cpu.get('current_freq_mhz', 0):.0f} MHz\n\n"

        md += "## GPU\n\n"
        gpus = data.get("gpus", [])
        for i, gpu in enumerate(gpus, 1):
            md += f"### GPU {i}: {gpu['name']}\n"
            md += f"- **Vendor**: {gpu['vendor']}\n"
            if gpu["vram_total_gb"] > 0:
                md += f"- **VRAM**: {gpu['vram_total_gb']:.1f} GB\n"
            md += "\n"

        md += "## Memory\n\n"
        mem = data.get("memory", {})
        ram_gb = mem.get("ram_total_bytes", 0) / (1024**3)
        md += f"- **RAM**: {ram_gb:.1f} GB\n"
        md += f"- **Usage**: {mem.get('ram_percent', 0):.1f}%\n\n"

        return md
