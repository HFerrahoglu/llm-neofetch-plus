#!/usr/bin/env python3
"""
LLM-Neofetch++ v1.0
Advanced system information tool for local LLM usage.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

sys.path.insert(0, str(Path(__file__).parent / "src"))

from detectors import (
    AppleSiliconDetector,
    BatteryDetector,
    CPUDetector,
    DiskDetector,
    GPUDetector,
    MemoryDetector,
    MotherboardDetector,
    OSDetector,
)
from ui import ExportFormatter, UIRenderer


class LLMNeofetch:
    """Main application class for LLM-Neofetch++.

    Coordinates configuration loading, system information gathering,
    and UI rendering for displaying hardware specifications optimized
    for local LLM usage.

    Attributes:
        config: Configuration dictionary loaded from YAML.
        ui: UIRenderer instance for terminal output.
        verbose: Enable detailed logging when True.
    """

    def __init__(self, config_path: str = None, verbose: bool = False):
        self.config = self._load_config(config_path)
        self.ui = UIRenderer(self.config)
        self.verbose = verbose
        self._setup_logging()

    def _load_config(self, config_path: str = None) -> Dict:
        """Load configuration from YAML file.

        Args:
            config_path: Explicit path to config file. If None, searches
                default locations.

        Returns:
            Configuration dictionary.
        """
        if config_path is None:
            possible_paths = [
                Path(__file__).parent / "config" / "config.yaml",
                Path.home() / ".config" / "llm-neofetch" / "config.yaml",
                Path("/etc/llm-neofetch/config.yaml"),
            ]

            for path in possible_paths:
                if path.exists():
                    config_path = str(path)
                    break

        if config_path and Path(config_path).exists():
            try:
                with open(config_path) as f:
                    return yaml.safe_load(f)
            except Exception as e:
                print(f"Warning: Could not load config: {e}")

        return self._default_config()

    def _default_config(self) -> Dict:
        """Return default configuration dictionary."""
        return {
            "ui": {
                "box_width": 76,
                "use_emoji": True,
                "show_progress_bars": True,
                "compact_mode": False,
            },
            "colors": {
                "primary": "\033[1;34m",
                "secondary": "\033[1;36m",
                "success": "\033[1;32m",
                "warning": "\033[1;33m",
                "danger": "\033[1;31m",
                "info": "\033[1;35m",
                "reset": "\033[0m",
                "bold": "\033[1m",
                "dim": "\033[2m",
            },
        }

    def _setup_logging(self):
        """Configure logging based on verbosity level."""
        level = logging.DEBUG if self.verbose else logging.WARNING
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler() if self.verbose else logging.NullHandler()
            ],
        )

    def collect_system_info(self, benchmark: bool = False) -> Dict[str, Any]:
        """Collect all system information from detectors.

        Args:
            benchmark: Run disk speed benchmark if True.

        Returns:
            Dictionary containing all detected system information.
        """
        info = {
            "timestamp": datetime.now().isoformat(),
            "os": OSDetector.detect(),
            "uptime": OSDetector.get_uptime(),
            "cpu": CPUDetector.detect(),
            "gpus": GPUDetector.detect(),
            "memory": MemoryDetector.detect(),
            "disks": DiskDetector.detect(),
            "battery": BatteryDetector.detect(),
            "motherboard": MotherboardDetector.detect(),
        }

        apple_silicon = AppleSiliconDetector.detect()
        if apple_silicon:
            info["apple_silicon"] = apple_silicon

        if benchmark and info["disks"]:
            print(
                f"\n{self.ui.colors.info}Running disk benchmark...{self.ui.colors.reset}"
            )
            main_disk = info["disks"][0]
            mountpoint = main_disk["mountpoint"]
            bench_result = DiskDetector.benchmark_speed(mountpoint, size_mb=100)
            if bench_result:
                main_disk["benchmark"] = bench_result

        return info

    def display_system_info(self, info: Dict, detail_level: int = 2):
        """Display collected system information to terminal.

        Args:
            info: Dictionary of system information.
            detail_level: 1=minimal, 2=normal, 3=detailed.
        """
        c = self.ui.colors

        self.ui.print_header()

        self.ui.print_section_header("System Information")

        os_info = info["os"]
        uptime = info["uptime"]

        self.ui.print_kv("OS", os_info["platform"])
        self.ui.print_kv("Kernel", f"{os_info['release']} ({os_info['machine']})")
        self.ui.print_kv(
            "Uptime", f"{uptime['days']}d {uptime['hours']}h {uptime['minutes']}m"
        )
        self.ui.print_kv("Python", os_info["python_version"])

        if info["motherboard"] != "N/A":
            self.ui.print_kv("Motherboard", info["motherboard"])

        self.ui.print_section_header("CPU")

        cpu = info["cpu"]
        self.ui.print_kv("Model", cpu["name"])
        self.ui.print_kv(
            "Cores",
            f"{cpu['cores_physical']} physical / {cpu['cores_logical']} threads",
        )
        self.ui.print_kv("Frequency", f"{cpu['current_freq_mhz']:.0f} MHz")

        if detail_level >= 2:
            if cpu["usage_percent"] > 0:
                usage_bar = self.ui.progress_bar(
                    cpu["usage_percent"], 100, width=30, label="Usage"
                )
                print(f"  {usage_bar}")

            if cpu["temperature_c"]:
                temp_color = (
                    c.success
                    if cpu["temperature_c"] < 60
                    else c.warning
                    if cpu["temperature_c"] < 80
                    else c.danger
                )
                print(
                    f"  Temperature:    {temp_color}{cpu['temperature_c']:.1f}°C{c.reset}"
                )

        self.ui.print_section_header("GPU")

        gpus = info["gpus"]
        for gpu in gpus:
            self.ui.print_gpu_info(gpu)
            print()

        self.ui.print_section_header("Memory")

        mem = info["memory"]
        ram_total = mem["ram_total_bytes"]
        ram_available = mem["ram_available_bytes"]
        ram_used = mem["ram_used_bytes"]

        ram_gb = ram_total / (1024**3)

        self.ui.print_kv("Total RAM", f"{self.ui.format_size(ram_total)} ({ram_gb:.1f} GB)")

        if detail_level >= 2:
            ram_bar = self.ui.progress_bar(ram_used, ram_total, width=30, label="Usage")
            print(f"  {ram_bar}")
            print(f"  Available:      {self.ui.format_size(ram_available)}")

        swap_total = mem["swap_total_bytes"]
        swap_gb = swap_total / (1024**3)

        if swap_total > 0:
            swap_status = f"{self.ui.format_size(swap_total)} ({mem['swap_percent']:.0f}% used)"
        else:
            swap_status = f"{c.warning}None / Disabled{c.reset}"

        self.ui.print_kv("Swap", swap_status)

        self.ui.print_section_header("Storage")

        disks = info["disks"]
        for disk in disks:
            self.ui.print_disk_info(disk)

            if detail_level >= 3 and "benchmark" in disk:
                print(f"    {c.dim}Benchmark Results:{c.reset}")
                self.ui.print_benchmark_results(disk["benchmark"])

            print()

        battery = info.get("battery")
        if battery:
            self.ui.print_section_header("Battery")

            status = (
                "⚡ Plugged In"
                if battery["plugged"]
                else f"🔋 On Battery ({battery['time_left']})"
            )
            self.ui.print_kv("Status", status)

            if detail_level >= 2:
                batt_bar = self.ui.progress_bar(
                    battery["percent"], 100, width=30, label="Charge"
                )
                print(f"  {batt_bar}")

        apple_silicon = info.get("apple_silicon")
        if apple_silicon:
            self.ui.print_section_header("🍎 Apple Silicon")

            self.ui.print_kv("Chip", apple_silicon["chip"])
            self.ui.print_kv(
                "Unified Memory", f"{apple_silicon['unified_memory_gb']:.1f} GB"
            )
            self.ui.print_kv(
                "MLX Support", "✓ Yes" if apple_silicon["supports_mlx"] else "✗ No"
            )

        if detail_level >= 2:
            max_vram = max([g["vram_total_gb"] for g in gpus], default=0)

            self.ui.print_model_recommendations(
                vram_gb=max_vram,
                ram_gb=ram_gb,
                disk_type=disks[0]["type"] if disks else "Unknown",
                config=self.config,
            )

        if detail_level >= 3:
            self.ui.print_quantization_guide(self.config)

        if detail_level >= 3:
            self.ui.print_section_header("LLM Backends Comparison")
            self.ui.print_backend_comparison(self.config)

        if detail_level >= 2:
            self.ui.print_tips(
                vram_gb=max_vram,
                ram_gb=ram_gb,
                swap_gb=swap_gb,
                disk_type=disks[0]["type"] if disks else "Unknown",
            )

        if detail_level >= 2:
            self.ui.print_section_header("Quick Start Commands")
            self.ui.print_quick_start()

        print(f"\n{c.dim}{'─' * self.ui.width}{c.reset}")
        print(f"{c.dim}Tip: Use 'llm-neofetch --help' for more options{c.reset}\n")

    def export(self, info: Dict, format: str, output_file: str):
        """Export system info to file.

        Args:
            info: System information dictionary.
            format: Export format (json, yaml, markdown).
            output_file: Path to output file.
        """
        formatter = ExportFormatter()

        if format == "json":
            content = formatter.to_json(info)
        elif format == "yaml":
            content = formatter.to_yaml(info)
        elif format == "markdown":
            content = formatter.to_markdown(info, self.ui)
        else:
            print(f"Error: Unknown format '{format}'")
            return

        with open(output_file, "w") as f:
            f.write(content)

        print(
            f"{self.ui.colors.success}✓{self.ui.colors.reset} Exported to {output_file}"
        )

    def interactive_mode(self) -> int:
        """Prompt user to select detail level interactively.

        Returns:
            Selected detail level (1, 2, or 3).
        """
        c = self.ui.colors

        print(f"{c.bold}Select detail level:{c.reset}")
        print(f"  {c.success}[1]{c.reset} Minimal  - Quick overview")
        print(f"  {c.info}[2]{c.reset} Normal   - Balanced (default)")
        print(f"  {c.warning}[3]{c.reset} Detailed - Full information")
        print()

        try:
            choice = input(f"{c.bold}Choice [1-3]:{c.reset} ").strip()
            if choice in ["1", "2", "3"]:
                return int(choice)
        except (KeyboardInterrupt, EOFError):
            print()
            return 2

        return 2


def main() -> int:
    """Main entry point for CLI execution.

    Returns:
        Exit code (0=success, non-zero=error).
    """
    parser = argparse.ArgumentParser(
        description="LLM-Neofetch++ - Advanced system info for local LLM usage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  llm-neofetch                          # Normal output
  llm-neofetch -d 3                     # Detailed output
  llm-neofetch -b                       # With disk benchmark
  llm-neofetch --export report.json     # Export to JSON
  llm-neofetch -i                       # Interactive mode
        """,
    )

    parser.add_argument(
        "-d",
        "--detail",
        type=int,
        choices=[1, 2, 3],
        default=2,
        help="Detail level: 1=minimal, 2=normal, 3=detailed",
    )
    parser.add_argument(
        "-b",
        "--benchmark",
        action="store_true",
        help="Run disk benchmark (takes ~10 seconds)",
    )
    parser.add_argument(
        "-i", "--interactive", action="store_true", help="Interactive mode"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging"
    )
    parser.add_argument(
        "--export",
        type=str,
        metavar="FILE",
        help="Export to file (supports .json, .yaml, .md)",
    )
    parser.add_argument(
        "--config", type=str, metavar="FILE", help="Custom config file path"
    )
    parser.add_argument(
        "--version", action="version", version="LLM-Neofetch++ v1.0.0"
    )

    args = parser.parse_args()

    try:
        app = LLMNeofetch(config_path=args.config, verbose=args.verbose)

        detail_level = args.detail
        if args.interactive:
            detail_level = app.interactive_mode()

        info = app.collect_system_info(benchmark=args.benchmark)

        app.display_system_info(info, detail_level=detail_level)

        if args.export:
            ext = Path(args.export).suffix.lower()
            format_map = {
                ".json": "json",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".md": "markdown",
                ".markdown": "markdown",
            }

            export_format = format_map.get(ext, "json")
            app.export(info, export_format, args.export)

        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
