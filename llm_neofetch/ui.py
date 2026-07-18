"""UI Rendering Module.

Rich-based terminal rendering: panels, rules, tables, and bars.
Colors are configured as Rich style strings (e.g. "green", "bold blue"),
never as raw ANSI escape codes.
"""

import json
import math
from typing import Dict, Optional, Union

import yaml
from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text

from llm_neofetch.version import __version__

DEFAULT_STYLES: Dict[str, str] = {
    "primary": "blue",
    "secondary": "cyan",
    "success": "green",
    "warning": "yellow",
    "danger": "red",
    "info": "magenta",
    "dim": "dim",
}

THEMES: Dict[str, Dict[str, str]] = {
    "default": DEFAULT_STYLES,
    "dracula": {
        "primary": "#bd93f9",
        "secondary": "#8be9fd",
        "success": "#50fa7b",
        "warning": "#f1fa8c",
        "danger": "#ff5555",
        "info": "#ff79c6",
        "dim": "#6272a4",
    },
    "nord": {
        "primary": "#81a1c1",
        "secondary": "#88c0d0",
        "success": "#a3be8c",
        "warning": "#ebcb8b",
        "danger": "#bf616a",
        "info": "#b48ead",
        "dim": "#4c566a",
    },
    "solarized": {
        "primary": "#268bd2",
        "secondary": "#2aa198",
        "success": "#859900",
        "warning": "#b58900",
        "danger": "#dc322f",
        "info": "#d33682",
        "dim": "#586e75",
    },
    "mono": {
        "primary": "white",
        "secondary": "bold white",
        "success": "white",
        "warning": "bold",
        "danger": "bold underline",
        "info": "white",
        "dim": "dim",
    },
}


class UIRenderer:
    """Main UI rendering class for terminal output.

    Handles all visual display including headers, sections,
    bars, GPU info, disk info, and recommendations.
    """

    def __init__(self, config: Optional[Dict] = None, console: Optional[Console] = None):
        self.config = config or {}
        ui_cfg = self.config.get("ui", {})
        self.use_emoji = ui_cfg.get("use_emoji", True)
        self.show_progress = ui_cfg.get("show_progress_bars", True)
        self.compact = ui_cfg.get("compact_mode", False)
        self.console = console or Console(highlight=False)
        self.width = min(self.console.size.width, ui_cfg.get("box_width", 76))
        theme = str(ui_cfg.get("theme", "default")).lower()
        self.styles = self._load_styles(self.config.get("colors", {}), theme)

    @staticmethod
    def _load_styles(colors_cfg: Dict, theme: str = "default") -> Dict[str, str]:
        """Build the style map from a theme, validating user overrides.

        Invalid values (including raw ANSI codes from legacy configs)
        are silently replaced with the theme defaults.

        Args:
            colors_cfg: The 'colors' section of the config.
            theme: Theme name from THEMES (falls back to default).

        Returns:
            Mapping of semantic names to Rich style strings.
        """
        styles = dict(THEMES.get(theme, DEFAULT_STYLES))
        for key, value in colors_cfg.items():
            if key not in styles or not isinstance(value, str):
                continue
            try:
                Style.parse(value)
            except Exception:
                continue
            styles[key] = value
        return styles

    def format_size(self, bytes_val: Union[int, float], suffix: str = "B") -> str:
        """Format bytes into human-readable size with unit suffix.

        Args:
            bytes_val: Number of bytes.
            suffix: Unit suffix (default 'B' for bytes).

        Returns:
            Formatted string like "1.5 GiB" or "500 MiB".
        """
        if bytes_val < 1:
            return "0 B"

        units = ["", "Ki", "Mi", "Gi", "Ti", "Pi"]
        i = int(math.log(bytes_val, 1024))
        i = min(i, len(units) - 1)
        p = 1024**i

        return f"{bytes_val / p:.1f} {units[i]}{suffix}"

    def level_style(self, level: float, invert: bool = False) -> str:
        """Pick a severity style for a 0-100 level.

        Args:
            level: Value between 0 and 100.
            invert: Treat high values as good (e.g. battery charge).

        Returns:
            Rich style string.
        """
        if invert:
            level = 100 - level
        if level < 50:
            return self.styles["success"]
        if level < 75:
            return self.styles["warning"]
        return self.styles["danger"]

    def temp_style(self, temp_c: float) -> str:
        """Pick a severity style for a temperature in Celsius.

        Args:
            temp_c: Temperature in Celsius.

        Returns:
            Rich style string.
        """
        if temp_c < 60:
            return self.styles["success"]
        if temp_c < 80:
            return self.styles["warning"]
        return self.styles["danger"]

    def bar(
        self,
        value: float,
        max_value: float,
        width: int = 30,
        invert: bool = False,
        show_percent: bool = True,
    ) -> Text:
        """Build a colored usage bar.

        Args:
            value: Current value.
            max_value: Maximum value.
            width: Bar character width.
            invert: Treat high values as good (colored green).
            show_percent: Append the percentage after the bar.

        Returns:
            Rich Text renderable.
        """
        if max_value == 0:
            percent = 0.0
        else:
            percent = min(100.0, (value / max_value) * 100)

        filled = int(width * percent / 100)
        style = self.level_style(percent, invert=invert)

        text = Text()
        text.append("█" * filled, style=style)
        text.append("░" * (width - filled), style=self.styles["dim"])
        if show_percent:
            text.append(f" {percent:5.1f}%", style=self.styles["dim"])
        return text

    def print_bar(
        self,
        label: str,
        value: float,
        max_value: float,
        indent: int = 2,
        invert: bool = False,
    ):
        """Print a labeled usage bar aligned with key-value rows.

        Args:
            label: Row label.
            value: Current value.
            max_value: Maximum value.
            indent: Number of leading spaces.
            invert: Treat high values as good.
        """
        text = Text(" " * indent)
        text.append(f"{label:<15}", style=self.styles["success"])
        text.append_text(self.bar(value, max_value, invert=invert))
        self.console.print(text)

    def print_header(self):
        """Print the main application header panel."""
        bolt = "⚡ " if self.use_emoji else ""
        title = Text()
        title.append(f"{bolt}LLM-Neofetch++ ", style=f"bold {self.styles['warning']}")
        title.append(f"v{__version__}", style=self.styles["dim"])

        if self.compact:
            self.console.print(title)
            return

        panel = Panel(
            Text("Advanced system info for local LLM usage", style=self.styles["dim"]),
            title=title,
            title_align="left",
            width=self.width,
            border_style=self.styles["secondary"],
            padding=(0, 2),
        )
        self.console.print()
        self.console.print(panel)

    def print_section_header(self, title: str):
        """Print a section header rule with icon.

        Args:
            title: Section title text.
        """
        icon = self._get_section_icon(title)
        line = Text("── ", style=self.styles["primary"])
        line.append(f"{icon} {title} ", style=f"bold {self.styles['secondary']}")
        remaining = self.width - line.cell_len
        line.append("─" * max(remaining, 3), style=self.styles["primary"])
        if not self.compact:
            self.console.print()
        self.console.print(line)

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
            "Apple": "🍎",
            "Recommendations": "🎯",
            "Quantization": "📊",
            "Backends": "🚀",
            "Models": "📦",
            "Process": "⚙",
            "Runtimes": "🧩",
            "Benchmark": "⚡",
            "Fine-Tuning": "🎓",
            "Optimization": "💡",
            "Quick Start": "🏁",
        }

        for key, icon in icons.items():
            if key.lower() in title.lower():
                return icon

        return "▶"

    def print_kv(self, key: str, value, indent: int = 2, value_style: str = ""):
        """Print a key-value pair with consistent formatting.

        Args:
            key: Label text.
            value: Value text or Rich Text.
            indent: Number of leading spaces.
            value_style: Optional Rich style for the value.
        """
        text = Text(" " * indent)
        text.append(f"{key:<15}", style=self.styles["success"])
        if isinstance(value, Text):
            text.append_text(value)
        else:
            text.append(str(value), style=value_style)
        self.console.print(text)

    def print_info(self, message: str):
        """Print an informational message."""
        self.console.print(Text(message, style=self.styles["info"]))

    def print_success(self, message: str):
        """Print a success message with checkmark."""
        text = Text("✓ ", style=self.styles["success"])
        text.append(message)
        self.console.print(text)

    def print_gpu_info(self, gpu: Dict):
        """Print detailed GPU information with VRAM bar and stats.

        Args:
            gpu: Dictionary containing GPU details.
        """
        vendor = gpu["vendor"]
        vram_total = gpu["vram_total_gb"]
        vram_used = gpu["vram_used_gb"]
        util = gpu["utilization_percent"]
        temp = gpu["temperature_c"]

        vendor_icons = {"NVIDIA": "🟢", "AMD": "🔴", "Intel": "🔵"}
        icon = vendor_icons.get(vendor, "⚪") if self.use_emoji else "▸"

        line = Text(f"  {icon} ")
        line.append(str(gpu["name"]), style="bold")
        self.console.print(line)

        pad = " " * 5
        if vram_total > 0:
            row = Text(pad)
            row.append(f"{'VRAM':<8}", style=self.styles["success"])
            if vram_used > 0:
                row.append_text(
                    self.bar(vram_used, vram_total, width=25, show_percent=False)
                )
                row.append(
                    f" {vram_used:.1f}/{vram_total:.1f} GB", style=self.styles["dim"]
                )
            else:
                row.append(f"{vram_total:.1f} GB")
            self.console.print(row)

        if util > 0:
            row = Text(pad)
            row.append(f"{'Usage':<8}", style=self.styles["success"])
            row.append_text(self.bar(util, 100, width=25))
            self.console.print(row)

        if temp:
            row = Text(pad)
            row.append(f"{'Temp':<8}", style=self.styles["success"])
            row.append(f"{temp:.0f}°C", style=self.temp_style(temp))
            self.console.print(row)

    def print_disk_info(self, disk: Dict):
        """Print disk information with type badge and usage bar.

        Args:
            disk: Dictionary containing disk details.
        """
        disk_type = disk["type"]
        badge_styles = {
            "NVMe": self.styles["success"],
            "SSD": self.styles["info"],
            "HDD": self.styles["dim"],
        }

        line = Text("  ")
        line.append(str(disk["mountpoint"]), style="bold")
        line.append(" ")
        line.append(f"[{disk_type}]", style=badge_styles.get(disk_type, ""))
        self.console.print(line)

        pad = " " * 5
        row = Text(pad)
        row.append(f"{'Size':<8}", style=self.styles["success"])
        row.append(
            f"{self.format_size(disk['free_bytes'])} free of "
            f"{self.format_size(disk['total_bytes'])}"
        )
        self.console.print(row)

        if self.show_progress:
            row = Text(pad)
            row.append(f"{'Usage':<8}", style=self.styles["success"])
            row.append_text(self.bar(disk["used_bytes"], disk["total_bytes"], width=25))
            self.console.print(row)

    def print_model_recommendations(
        self,
        vram_gb: float,
        ram_gb: float,
        disk_type: str,
        config: Dict,
        gpu_bandwidth: float = 0.0,
        ram_bandwidth: float = 0.0,
    ):
        """Print context-aware LLM model recommendations.

        For each runnable tier, shows the estimated max context length
        and generation speed on this hardware (Q4_K_M assumed).

        Args:
            vram_gb: Available GPU VRAM in GB.
            ram_gb: Available RAM in GB.
            disk_type: Primary disk type.
            config: Configuration dictionary with model recommendations.
            gpu_bandwidth: GPU memory bandwidth estimate in GB/s.
            ram_bandwidth: System RAM bandwidth estimate in GB/s.
        """
        from llm_neofetch import llm_math

        models = config.get("models", {})

        suitable_models = []
        for category, info in models.items():
            vram_min = info.get("vram_min", 0)
            ram_min = info.get("ram_min", 0)
            if vram_gb >= vram_min and ram_gb >= ram_min:
                suitable_models.append((category, info))

        if not suitable_models:
            self.console.print(
                Text(
                    "  Your system can run basic models with CPU inference.",
                    style=self.styles["dim"],
                )
            )
            return

        category_names = {
            "tiny": "Tiny (1-3B)",
            "small": "Small (7-8B)",
            "medium": "Medium (13-14B)",
            "large": "Large (30-34B)",
            "xlarge": "Extra Large (70-72B)",
        }

        if not gpu_bandwidth:
            gpu_bandwidth = llm_math.gpu_bandwidth_estimate(vram_gb)
        if not ram_bandwidth:
            ram_bandwidth = llm_math.ram_bandwidth_estimate()

        bits = 4.5  # Q4_K_M

        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Model Tier", header_style=self.styles["dim"])
        table.add_column("Examples", header_style=self.styles["dim"])
        table.add_column("Max ctx", header_style=self.styles["dim"])
        table.add_column("~Speed", header_style=self.styles["dim"])

        # Largest runnable tier first
        for category, info in reversed(suitable_models):
            name = category_names.get(
                category, f"{category.capitalize()} ({info.get('size_range', '')})"
            )
            examples = ", ".join(info.get("examples", [])[:3])

            params = llm_math.parse_model_size(str(info.get("size_range", ""))) or 0
            max_ctx_text = "—"
            speed_text = Text("—", style=self.styles["dim"])

            if params:
                weights = llm_math.weights_gb(params, bits)
                on_gpu = vram_gb > 0 and weights + 1.0 <= vram_gb
                budget = vram_gb if on_gpu else ram_gb * 0.8
                bandwidth = gpu_bandwidth if on_gpu else ram_bandwidth

                max_ctx = llm_math.max_context_tokens(params, bits, budget)
                if max_ctx >= 1024:
                    max_ctx_text = f"{max_ctx // 1024}K"
                elif max_ctx > 0:
                    max_ctx_text = str(max_ctx)

                tps = llm_math.tokens_per_second(weights, bandwidth)
                device = "GPU" if on_gpu else "CPU"
                speed_text = Text(f"{tps:.0f} tok/s ", style="")
                speed_text.append(f"({device})", style=self.styles["dim"])

            table.add_row(
                Text(name, style=f"bold {self.styles['success']}"),
                examples,
                max_ctx_text,
                speed_text,
            )

        self.console.print(Padding(table, (0, 0, 0, 2)))
        self.console.print(
            Text(
                "  Estimates assume Q4_K_M quantization; speed is a "
                "bandwidth-based upper bound.",
                style=self.styles["dim"],
            )
        )

    def print_can_run(self, report: Dict):
        """Print a can-run verdict panel and per-quant breakdown.

        Args:
            report: Report dictionary produced by the can-run command.
        """
        model = report["model"]
        params = report["params_b"]
        context = report["context"]

        fits_any = any(row["fits"] != "no" for row in report["rows"])
        if fits_any:
            headline = Text("✓ ", style=f"bold {self.styles['success']}")
            headline.append(f"{model} ", style="bold")
            headline.append(f"({params:g}B) can run on this system")
        else:
            headline = Text("✗ ", style=f"bold {self.styles['danger']}")
            headline.append(f"{model} ", style="bold")
            headline.append(f"({params:g}B) does not fit on this system")

        panel = Panel(
            headline,
            width=self.width,
            border_style=self.styles["secondary"],
            padding=(0, 2),
        )
        self.console.print()
        self.console.print(panel)

        subtitle = f"  Context: {context:,} tokens • VRAM: {report['vram_gb']:.1f} GB"
        if "vram_free_gb" in report and report["vram_gb"] > 0:
            subtitle += f" ({report['vram_free_gb']:.1f} free)"
        subtitle += f" • RAM: {report['ram_gb']:.1f} GB"
        if "ram_free_gb" in report:
            subtitle += f" ({report['ram_free_gb']:.1f} free)"
        self.console.print(Text(subtitle, style=self.styles["dim"]))
        self.console.print()

        has_now = any("fits_now" in row for row in report["rows"])

        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Quant", header_style=self.styles["dim"], style="bold")
        table.add_column("Memory", header_style=self.styles["dim"])
        table.add_column("Capacity", header_style=self.styles["dim"])
        if has_now:
            table.add_column("Right now", header_style=self.styles["dim"])
        table.add_column("~Speed", header_style=self.styles["dim"])
        table.add_column("Max ctx", header_style=self.styles["dim"])

        def verdict_text(fits: str, now: bool = False) -> Text:
            if fits == "gpu":
                return Text("✓ GPU", style=self.styles["success"])
            if fits == "cpu":
                return Text("✓ CPU", style=self.styles["warning"])
            label = "✗ not now" if now else "✗ no"
            return Text(label, style=self.styles["danger"])

        for row in report["rows"]:
            speed = f"{row['tps']:.0f} tok/s" if row["tps"] else "—"
            max_ctx = row["max_ctx"]
            if max_ctx >= 1024:
                ctx_text = f"{max_ctx // 1024}K"
            elif max_ctx > 0:
                ctx_text = str(max_ctx)
            else:
                ctx_text = "—"

            cells = [
                row["quant"],
                f"{row['total_gb']:.1f} GB",
                verdict_text(row["fits"]),
            ]
            if has_now:
                cells.append(verdict_text(row.get("fits_now", "no"), now=True))
            cells.extend([speed, ctx_text])
            table.add_row(*cells)

        self.console.print(Padding(table, (0, 0, 0, 2)))
        self.console.print(
            Text(
                "  Capacity uses hardware totals; 'Right now' uses memory "
                "that is actually free at this moment.",
                style=self.styles["dim"],
            )
        )
        self.console.print()

    def print_diff(self, report_a: Dict, report_b: Dict, name_a: str, name_b: str):
        """Print a comparison of two exported system reports.

        Args:
            report_a: First system info dictionary.
            report_b: Second system info dictionary.
            name_a: Label for the first system.
            name_b: Label for the second system.
        """

        def metrics(data: Dict) -> Dict[str, str]:
            cpu = data.get("cpu", {})
            mem = data.get("memory", {})
            gpus = data.get("gpus", [])
            disks = data.get("disks", [])
            max_vram = max((g.get("vram_total_gb", 0) for g in gpus), default=0)
            total_vram = sum(g.get("vram_total_gb", 0) for g in gpus)
            return {
                "CPU": str(cpu.get("name", "?")),
                "Cores": f"{cpu.get('cores_physical', 0)}c / {cpu.get('cores_logical', 0)}t",
                "RAM": f"{mem.get('ram_total_bytes', 0) / (1024**3):.1f} GB",
                "Max GPU VRAM": f"{max_vram:.1f} GB",
                "Total VRAM": f"{total_vram:.1f} GB",
                "Disk": str(disks[0].get("type", "?")) if disks else "?",
            }

        a = metrics(report_a)
        b = metrics(report_b)

        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Metric", header_style=self.styles["dim"], style="bold")
        table.add_column(name_a, header_style=self.styles["dim"])
        table.add_column(name_b, header_style=self.styles["dim"])

        for key in a:
            table.add_row(key, a[key], b[key])

        self.console.print()
        self.console.print(Padding(table, (0, 0, 0, 2)))

        def score(data: Dict) -> float:
            mem = data.get("memory", {})
            gpus = data.get("gpus", [])
            vram = max((g.get("vram_total_gb", 0) for g in gpus), default=0)
            ram = mem.get("ram_total_bytes", 0) / (1024**3)
            return vram * 3 + ram

        verdict = Text("  ")
        if abs(score(report_a) - score(report_b)) < 1:
            verdict.append("Both systems are comparable for LLM inference.")
        else:
            winner = name_a if score(report_a) > score(report_b) else name_b
            verdict.append("→ ", style=self.styles["success"])
            verdict.append(f"{winner}", style=f"bold {self.styles['success']}")
            verdict.append(" is better suited for LLM inference.")
        self.console.print(verdict)
        self.console.print()

    def print_quantization_guide(self, config: Dict):
        """Print GGUF quantization format guide.

        Args:
            config: Configuration dictionary with quantization info.
        """
        quants = config.get("quantization", {}).get("gguf", {})

        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Format", header_style=self.styles["dim"], style="bold")
        table.add_column("Quality", header_style=self.styles["dim"])
        table.add_column("Best for", header_style=self.styles["dim"])

        for quant_name, info in quants.items():
            table.add_row(
                quant_name,
                str(info.get("quality", "")),
                Text(str(info.get("use_case", "")), style=self.styles["dim"]),
            )

        self.console.print(Padding(table, (0, 0, 0, 2)))

    def print_backend_comparison(self, config: Dict):
        """Print comparison of LLM inference backends.

        Args:
            config: Configuration dictionary with backend info.
        """
        backends = config.get("backends", {})
        star = "⭐" if self.use_emoji else "*"
        display_names = {
            "ollama": "Ollama",
            "llama_cpp": "llama.cpp",
            "vllm": "vLLM",
            "exllamav2": "ExLlamaV2",
            "lm_studio": "LM Studio",
        }

        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Backend", header_style=self.styles["dim"], style="bold")
        table.add_column("Ease", header_style=self.styles["dim"])
        table.add_column("Speed", header_style=self.styles["dim"])
        table.add_column("Features", header_style=self.styles["dim"])
        table.add_column("Platforms", header_style=self.styles["dim"])

        for name, info in backends.items():
            table.add_row(
                display_names.get(name, name.replace("_", " ").title()),
                star * info.get("ease_of_use", 0),
                star * info.get("performance", 0),
                star * info.get("features", 0),
                Text(", ".join(info.get("platforms", [])), style=self.styles["dim"]),
            )

        self.console.print(Padding(table, (0, 0, 0, 2)))

    def print_quick_start(self):
        """Print quick start command suggestions for running local LLMs."""
        commands = [
            ("Test with tiny model", "ollama run llama3.2:1b"),
            ("Run popular 7B model", "ollama run qwen2.5:7b"),
            ("Try coding assistant", "ollama run deepseek-coder:6.7b"),
            ("Best quality 9B", "ollama run gemma2:9b"),
        ]

        for desc, cmd in commands:
            line = Text("  ")
            line.append("▸ ", style=self.styles["success"])
            line.append(f"{desc:<25}", style=self.styles["dim"])
            line.append("$ ", style=self.styles["dim"])
            line.append(cmd, style="bold")
            self.console.print(line)

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
        tips = []

        if vram_gb < 8:
            tips.append(
                ("⚠", "warning", "Low VRAM - Use CPU inference or smaller quantized models")
            )
        elif vram_gb >= 24:
            tips.append(
                ("✓", "success", "Excellent VRAM - Can run 70B models with Q4 quantization")
            )

        if ram_gb >= 32:
            tips.append(
                ("✓", "success", "Good RAM - CPU-only inference viable for 13-30B models")
            )

        if swap_gb < 16 and ram_gb < 64:
            tips.append(
                ("⚠", "warning", "Consider increasing swap/pagefile to 16-32 GB for large models")
            )

        if disk_type in ["NVMe", "SSD"]:
            tips.append(
                ("✓", "success", "Fast storage - Quick model loading and context management")
            )
        else:
            tips.append(("ℹ", "info", "Consider SSD/NVMe for faster model loading"))

        for symbol, style_key, tip in tips:
            line = Text("  ")
            line.append(symbol, style=self.styles[style_key])
            line.append(f"  {tip}")
            self.console.print(line)

    def print_benchmark_results(self, results: Dict):
        """Print disk benchmark results with speed classification.

        Args:
            results: Dictionary with read/write speeds.
        """
        if not results:
            return

        def classify(speed: float) -> Text:
            if speed >= 2000:
                return Text("Excellent (NVMe)", style=self.styles["success"])
            if speed >= 500:
                return Text("Good (SATA SSD)", style=self.styles["info"])
            if speed >= 100:
                return Text("Moderate", style=self.styles["warning"])
            return Text("Slow (HDD)", style=self.styles["danger"])

        pad = " " * 5
        self.console.print(
            Text(f"{pad}Benchmark Results", style=f"bold {self.styles['secondary']}")
        )
        for label, key in (("Read", "read_mb_s"), ("Write", "write_mb_s")):
            speed = results.get(key, 0)
            row = Text(pad)
            row.append(f"{label:<8}", style=self.styles["success"])
            row.append(f"{speed:7.1f} MB/s  ")
            row.append_text(classify(speed))
            self.console.print(row)
        if results.get("read_cached", True):
            self.console.print(
                Text(
                    f"{pad}Note: read speed may include OS page cache",
                    style=self.styles["dim"],
                )
            )

    def print_footer(self):
        """Print the closing divider and help tip."""
        if self.compact:
            return
        self.console.print()
        self.console.print(Text("─" * self.width, style=self.styles["dim"]))
        self.console.print(
            Text(
                "Tip: use 'llm-neofetch --help' for more options",
                style=self.styles["dim"],
            )
        )
        self.console.print()

    def print_multi_gpu_summary(self, gpus: list):
        """Print a total-VRAM summary when multiple GPUs are present.

        Args:
            gpus: List of GPU dictionaries.
        """
        with_vram = [g for g in gpus if g.get("vram_total_gb", 0) > 0]
        if len(with_vram) < 2:
            return
        total = sum(g["vram_total_gb"] for g in with_vram)
        line = Text("  ")
        line.append(f"{'Total VRAM':<15}", style=self.styles["success"])
        line.append(f"{total:.1f} GB across {len(with_vram)} GPUs ")
        line.append(
            "(tensor parallelism: vLLM, ExLlamaV2)", style=self.styles["dim"]
        )
        self.console.print(line)

    def print_npus(self, npus: list):
        """Print detected NPU / AI accelerator devices.

        Args:
            npus: List of NPU name strings.
        """
        for npu in npus:
            icon = "🧿 " if self.use_emoji else "▸ "
            line = Text(f"  {icon}")
            line.append(str(npu), style="bold")
            line.append("  (NPU)", style=self.styles["dim"])
            self.console.print(line)

    def print_runtimes(self, runtimes: Dict):
        """Print AI runtime/driver availability.

        Args:
            runtimes: Mapping of runtime name to version or None.
        """
        for name, version in runtimes.items():
            row = Text("  ")
            row.append(f"{name:<15}", style=self.styles["success"])
            if version:
                row.append("✓ ", style=self.styles["success"])
                row.append(str(version))
            else:
                row.append("✗ not detected", style=self.styles["dim"])
            self.console.print(row)

    def print_backends_status(self, backends: list):
        """Print installed backend status table.

        Args:
            backends: List of backend info dictionaries.
        """
        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Backend", header_style=self.styles["dim"], style="bold")
        table.add_column("Version", header_style=self.styles["dim"])
        table.add_column("Status", header_style=self.styles["dim"])
        table.add_column("Models", header_style=self.styles["dim"])

        for backend in backends:
            if backend.get("running"):
                status = Text("● running", style=self.styles["success"])
            else:
                status = Text("○ installed", style=self.styles["dim"])
            models = str(backend.get("models_count") or "—")
            table.add_row(
                backend["name"],
                backend.get("version") or "—",
                status,
                models,
            )

        self.console.print(Padding(table, (0, 0, 0, 2)))

    def print_processes(self, processes: list):
        """Print running LLM process table.

        Args:
            processes: List of process info dictionaries.
        """
        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Process", header_style=self.styles["dim"], style="bold")
        table.add_column("PID", header_style=self.styles["dim"])
        table.add_column("RAM", header_style=self.styles["dim"])
        table.add_column("VRAM", header_style=self.styles["dim"])

        for proc in processes:
            vram_mb = proc.get("vram_mb", 0)
            vram = f"{vram_mb / 1024:.1f} GB" if vram_mb else "—"
            table.add_row(
                proc["name"],
                str(proc["pid"]),
                f"{proc['ram_gb']:.1f} GB",
                vram,
            )

        self.console.print(Padding(table, (0, 0, 0, 2)))

    def print_installed_models(
        self, models: list, vram_gb: float, ram_gb: float, limit: int = 10
    ):
        """Print locally downloaded models with a fits-verdict per model.

        Args:
            models: List of model dictionaries (name, size_gb, source).
            vram_gb: Available VRAM budget.
            ram_gb: Total system RAM.
            limit: Maximum rows to display.
        """
        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Model", header_style=self.styles["dim"], style="bold")
        table.add_column("Size", header_style=self.styles["dim"])
        table.add_column("Source", header_style=self.styles["dim"])
        table.add_column("Fits", header_style=self.styles["dim"])

        for model in models[:limit]:
            need = model["size_gb"] + 1.5  # rough KV/overhead margin
            if need <= vram_gb:
                fits = Text("✓ GPU", style=self.styles["success"])
            elif need <= ram_gb * 0.8:
                fits = Text("✓ CPU (RAM)", style=self.styles["warning"])
            else:
                fits = Text("✗ too big", style=self.styles["danger"])
            table.add_row(
                model["name"], f"{model['size_gb']:.1f} GB", model["source"], fits
            )

        self.console.print(Padding(table, (0, 0, 0, 2)))
        if len(models) > limit:
            self.console.print(
                Text(
                    f"  … and {len(models) - limit} more",
                    style=self.styles["dim"],
                )
            )

    def print_finetune_guide(self, vram_gb: float):
        """Print fine-tuning VRAM requirements with fit verdicts.

        Args:
            vram_gb: Available VRAM budget.
        """
        from llm_neofetch import llm_math

        table = Table(box=None, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column("Model", header_style=self.styles["dim"], style="bold")
        table.add_column("QLoRA", header_style=self.styles["dim"])
        table.add_column("LoRA (fp16)", header_style=self.styles["dim"])

        def verdict(need: float) -> Text:
            mark = "✓" if need <= vram_gb else "✗"
            style = self.styles["success"] if need <= vram_gb else self.styles["dim"]
            return Text(f"{need:.0f} GB {mark}", style=style)

        for params in (1, 3, 8, 14, 32, 70):
            table.add_row(
                f"{params}B",
                verdict(llm_math.finetune_vram_gb(params, "qlora")),
                verdict(llm_math.finetune_vram_gb(params, "lora")),
            )

        self.console.print(Padding(table, (0, 0, 0, 2)))
        self.console.print(
            Text(
                "  Estimates assume short sequences and small batches.",
                style=self.styles["dim"],
            )
        )

    def print_llm_benchmark(self, result: Dict):
        """Print real generation benchmark results from Ollama.

        Args:
            result: Benchmark result dictionary.
        """
        self.print_kv("Model", result.get("model", "?"))
        tps = result.get("tokens_per_second", 0)
        self.print_kv(
            "Generation",
            f"{tps:.1f} tokens/s",
            value_style=f"bold {self.styles['success']}",
        )
        prompt_tps = result.get("prompt_tokens_per_second")
        if prompt_tps:
            self.print_kv("Prompt eval", f"{prompt_tps:.0f} tokens/s")


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
        if os_info.get("system") == "Windows":
            kernel = os_info.get("version", "N/A")
        else:
            kernel = os_info.get("release", "N/A")
        md += f"- **OS**: {os_info.get('platform', 'N/A')}\n"
        md += f"- **Kernel**: {kernel}\n"
        md += f"- **Architecture**: {os_info.get('machine', 'N/A')}\n\n"

        md += "## CPU\n\n"
        cpu = data.get("cpu", {})
        freq = f"{cpu.get('current_freq_mhz', 0):.0f} MHz"
        if cpu.get("max_freq_mhz", 0) > cpu.get("current_freq_mhz", 0):
            freq += f" (max {cpu.get('max_freq_mhz', 0):.0f} MHz)"
        md += f"- **Model**: {cpu.get('name', 'N/A')}\n"
        md += f"- **Cores**: {cpu.get('cores_physical', 0)} physical / {cpu.get('cores_logical', 0)} logical\n"
        md += f"- **Frequency**: {freq}\n\n"

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
