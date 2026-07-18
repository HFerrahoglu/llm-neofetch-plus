#!/usr/bin/env python3
"""
LLM-Neofetch++ v1.0
Advanced system information tool for local LLM usage.
"""

import argparse
import copy
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import psutil
import yaml
from rich.text import Text

from llm_neofetch import llm_math
from llm_neofetch.defaults import DEFAULT_CONFIG
from llm_neofetch.detectors import (
    AppleSiliconDetector,
    BatteryDetector,
    CPUDetector,
    DiskDetector,
    GPUDetector,
    MemoryBenchmark,
    MemoryDetector,
    MotherboardDetector,
    NPUDetector,
    OSDetector,
)
from llm_neofetch.environment import (
    BackendDetector,
    EnvironmentDetector,
    ModelScanner,
    OllamaBenchmark,
    ProcessDetector,
    RuntimeDetector,
)
from llm_neofetch.ui import ExportFormatter, UIRenderer
from llm_neofetch.version import __version__


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


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

    def __init__(
        self,
        config_path: str = None,
        verbose: bool = False,
        theme: Optional[str] = None,
        compact: bool = False,
        no_emoji: bool = False,
    ):
        self.config = self._load_config(config_path)

        ui_cfg = self.config.setdefault("ui", {})
        if theme:
            ui_cfg["theme"] = theme
        if compact:
            ui_cfg["compact_mode"] = True
        if no_emoji:
            ui_cfg["use_emoji"] = False

        self.ui = UIRenderer(self.config)
        self.verbose = verbose
        self._setup_logging()

    def _load_config(self, config_path: str = None) -> Dict:
        """Load configuration, merging any config file over built-in defaults.

        Search order (first existing file wins): explicit path, user config
        (~/.config/llm-neofetch/config.yaml), system config
        (/etc/llm-neofetch/config.yaml), bundled package config.

        Args:
            config_path: Explicit path to config file. If None, searches
                default locations.

        Returns:
            Configuration dictionary with all sections guaranteed present.
        """
        config = copy.deepcopy(DEFAULT_CONFIG)

        if config_path is None:
            possible_paths = [
                Path.home() / ".config" / "llm-neofetch" / "config.yaml",
                Path("/etc/llm-neofetch/config.yaml"),
                Path(__file__).parent / "config" / "config.yaml",
            ]

            for path in possible_paths:
                if path.exists():
                    config_path = str(path)
                    break

        if config_path and Path(config_path).exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                config = _deep_merge(config, loaded)
            except Exception as e:
                print(f"Warning: Could not load config: {e}")

        return config

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

    def collect_system_info(
        self,
        benchmark: bool = False,
        extended: bool = True,
        quiet: bool = False,
        bench_mem: bool = False,
        bench_llm: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Collect all system information from detectors.

        Args:
            benchmark: Run disk speed benchmark if True.
            extended: Also detect NPUs, runtimes, backends, processes,
                and installed models (slower).
            quiet: Suppress progress messages (for machine output).
            bench_mem: Run the memory bandwidth benchmark.
            bench_llm: Run a real generation benchmark via Ollama; pass a
                model name, or an empty string to auto-pick the smallest
                installed model. None skips the benchmark.

        Returns:
            Dictionary containing all detected system information.
        """
        info: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "os": OSDetector.detect(),
            "uptime": OSDetector.get_uptime(),
            "cpu": CPUDetector.detect(),
            "gpus": GPUDetector.detect(),
            "memory": MemoryDetector.detect(),
            "disks": DiskDetector.detect(),
            "battery": BatteryDetector.detect(),
            "motherboard": MotherboardDetector.detect(),
            "environment": EnvironmentDetector.detect(),
        }

        apple_silicon = AppleSiliconDetector.detect()
        if apple_silicon:
            info["apple_silicon"] = apple_silicon

        if extended:
            info["npus"] = NPUDetector.detect()
            info["runtimes"] = RuntimeDetector.detect()
            info["backends"] = BackendDetector.detect()
            info["processes"] = ProcessDetector.detect()
            info["installed_models"] = ModelScanner.scan()

        if benchmark and info["disks"]:
            if not quiet:
                self.ui.print_info("Running disk benchmark...")
            main_disk = info["disks"][0]
            mountpoint = main_disk["mountpoint"]
            bench_cfg = self.config.get("benchmark", {})
            bench_result = DiskDetector.benchmark_speed(
                mountpoint,
                size_mb=bench_cfg.get("test_file_size_mb", 100),
                timeout=bench_cfg.get("timeout_seconds", 30),
            )
            if bench_result:
                main_disk["benchmark"] = bench_result

        if bench_mem:
            if not quiet:
                self.ui.print_info("Running memory bandwidth benchmark...")
            mem_result = MemoryBenchmark.run()
            if mem_result:
                info["memory"]["bench_copy_gb_s"] = mem_result["copy_gb_s"]

        if bench_llm is not None:
            if not quiet:
                self.ui.print_info(
                    "Running LLM benchmark via Ollama (first load can be slow)..."
                )
            llm_result = OllamaBenchmark.run(bench_llm or None)
            if llm_result:
                info["llm_benchmark"] = llm_result
            elif not quiet:
                self.ui.print_info(
                    "LLM benchmark skipped: Ollama not reachable or no models."
                )

        return info

    def display_system_info(self, info: Dict, detail_level: int = 2):
        """Display collected system information to terminal.

        Args:
            info: Dictionary of system information.
            detail_level: 1=minimal, 2=normal, 3=detailed.
        """
        self.ui.print_header()

        self.ui.print_section_header("System Information")

        os_info = info["os"]
        uptime = info["uptime"]

        kernel = (
            os_info["version"] if os_info["system"] == "Windows" else os_info["release"]
        )

        self.ui.print_kv("OS", os_info["platform"])
        self.ui.print_kv("Kernel", f"{kernel} ({os_info['machine']})")
        self.ui.print_kv(
            "Uptime", f"{uptime['days']}d {uptime['hours']}h {uptime['minutes']}m"
        )
        self.ui.print_kv("Python", os_info["python_version"])

        if info["motherboard"] != "N/A":
            self.ui.print_kv("Motherboard", info["motherboard"])

        environment = info.get("environment")
        if environment and environment != "Bare metal":
            self.ui.print_kv("Environment", environment)

        self.ui.print_section_header("CPU")

        cpu = info["cpu"]
        self.ui.print_kv("Model", cpu["name"])
        self.ui.print_kv(
            "Cores",
            f"{cpu['cores_physical']} physical / {cpu['cores_logical']} threads",
        )
        freq_str = f"{cpu['current_freq_mhz']:.0f} MHz"
        if cpu["max_freq_mhz"] and cpu["max_freq_mhz"] > cpu["current_freq_mhz"]:
            freq_str += f" (max {cpu['max_freq_mhz']:.0f} MHz)"
        self.ui.print_kv("Frequency", freq_str)

        if detail_level >= 2:
            if cpu["usage_percent"] > 0:
                self.ui.print_bar("Usage", cpu["usage_percent"], 100)

            if cpu["temperature_c"]:
                self.ui.print_kv(
                    "Temperature",
                    f"{cpu['temperature_c']:.1f}°C",
                    value_style=self.ui.temp_style(cpu["temperature_c"]),
                )

        self.ui.print_section_header("GPU")

        gpus = info["gpus"]
        for gpu in gpus:
            self.ui.print_gpu_info(gpu)

        self.ui.print_multi_gpu_summary(gpus)

        npus = info.get("npus") or []
        if npus:
            self.ui.print_npus(npus)

        self.ui.print_section_header("Memory")

        mem = info["memory"]
        ram_total = mem["ram_total_bytes"]
        ram_available = mem["ram_available_bytes"]
        ram_used = mem["ram_used_bytes"]

        ram_gb = ram_total / (1024**3)

        self.ui.print_kv("Total RAM", f"{self.ui.format_size(ram_total)} ({ram_gb:.1f} GB)")

        if detail_level >= 2:
            self.ui.print_bar("Usage", ram_used, ram_total)
            self.ui.print_kv("Available", self.ui.format_size(ram_available))

        swap_total = mem["swap_total_bytes"]
        swap_gb = swap_total / (1024**3)

        if swap_total > 0:
            self.ui.print_kv(
                "Swap",
                f"{self.ui.format_size(swap_total)} ({mem['swap_percent']:.0f}% used)",
            )
        else:
            swap_warning = self.ui.styles["warning"]
            self.ui.print_kv("Swap", "None / Disabled", value_style=swap_warning)

        if detail_level >= 2 and mem.get("ram_speed_mts"):
            speed_str = f"{mem['ram_speed_mts']:.0f} MT/s"
            if mem.get("ram_sticks"):
                speed_str += f" ({mem['ram_sticks']} module(s))"
            self.ui.print_kv("Speed", speed_str)
            if mem.get("ram_bandwidth_est_gb_s"):
                self.ui.print_kv(
                    "Bandwidth",
                    f"~{mem['ram_bandwidth_est_gb_s']:.0f} GB/s (est. dual-channel)",
                )

        if mem.get("bench_copy_gb_s"):
            self.ui.print_kv(
                "Copy bench",
                f"{mem['bench_copy_gb_s']:.1f} GB/s (measured, single-thread)",
            )

        self.ui.print_section_header("Storage")

        disks = info["disks"]
        for disk in disks:
            self.ui.print_disk_info(disk)

            if "benchmark" in disk:
                self.ui.print_benchmark_results(disk["benchmark"])

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
                self.ui.print_bar("Charge", battery["percent"], 100, invert=True)

        apple_silicon = info.get("apple_silicon")
        if apple_silicon:
            self.ui.print_section_header("Apple Silicon")

            self.ui.print_kv("Chip", apple_silicon["chip"])
            self.ui.print_kv(
                "Unified Memory", f"{apple_silicon['unified_memory_gb']:.1f} GB"
            )
            self.ui.print_kv(
                "MLX Support", "✓ Yes" if apple_silicon["supports_mlx"] else "✗ No"
            )

        max_vram = max([g["vram_total_gb"] for g in gpus], default=0)

        # On Apple Silicon most unified memory is usable as GPU memory
        effective_vram = max_vram
        gpu_bandwidth = 0.0
        if apple_silicon:
            effective_vram = max(
                effective_vram, apple_silicon["unified_memory_gb"] * 0.75
            )
            gpu_bandwidth = float(apple_silicon.get("memory_bandwidth_gb_s", 0))

        ram_bandwidth = float(mem.get("ram_bandwidth_est_gb_s") or 0)

        if detail_level >= 2:
            backends = info.get("backends") or []
            if backends:
                self.ui.print_section_header("Installed Backends")
                self.ui.print_backends_status(backends)

            installed_models = info.get("installed_models") or []
            if installed_models:
                self.ui.print_section_header("Installed Models")
                self.ui.print_installed_models(
                    installed_models, vram_gb=effective_vram, ram_gb=ram_gb
                )

            processes = info.get("processes") or []
            if processes:
                self.ui.print_section_header("Running LLM Processes")
                self.ui.print_processes(processes)

        if info.get("llm_benchmark"):
            self.ui.print_section_header("LLM Benchmark (measured)")
            self.ui.print_llm_benchmark(info["llm_benchmark"])

        if detail_level >= 2:
            self.ui.print_section_header("Model Recommendations")
            self.ui.print_model_recommendations(
                vram_gb=effective_vram,
                ram_gb=ram_gb,
                disk_type=disks[0]["type"] if disks else "Unknown",
                config=self.config,
                gpu_bandwidth=gpu_bandwidth,
                ram_bandwidth=ram_bandwidth,
            )

        if detail_level >= 3:
            runtimes = info.get("runtimes") or {}
            if runtimes:
                self.ui.print_section_header("AI Runtimes")
                self.ui.print_runtimes(runtimes)

            self.ui.print_section_header("Quantization Guide (GGUF)")
            self.ui.print_quantization_guide(self.config)

            self.ui.print_section_header("LLM Backends Comparison")
            self.ui.print_backend_comparison(self.config)

            self.ui.print_section_header("Fine-Tuning Guide")
            self.ui.print_finetune_guide(vram_gb=effective_vram)

        if detail_level >= 2:
            self.ui.print_section_header("Optimization Tips")
            self.ui.print_tips(
                vram_gb=effective_vram,
                ram_gb=ram_gb,
                swap_gb=swap_gb,
                disk_type=disks[0]["type"] if disks else "Unknown",
            )

            self.ui.print_section_header("Quick Start Commands")
            self.ui.print_quick_start()

        self.ui.print_footer()

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
        elif format == "html":
            self._export_html(info, output_file)
            return
        else:
            print(f"Error: Unknown format '{format}'")
            return

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)

        self.ui.print_success(f"Exported to {output_file}")

    def _export_html(self, info: Dict, output_file: str):
        """Export a full-color HTML report by re-rendering the display.

        Args:
            info: System information dictionary.
            output_file: Path to the output HTML file.
        """
        from rich.console import Console

        record_console = Console(
            record=True, width=100, force_terminal=True, highlight=False
        )
        original_ui = self.ui
        self.ui = UIRenderer(self.config, console=record_console)
        try:
            self.display_system_info(info, detail_level=3)
        finally:
            self.ui = original_ui

        html = record_console.export_html(inline_styles=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

        self.ui.print_success(f"Exported to {output_file}")

    def can_run(self, model: str, quant: Optional[str], context: int) -> int:
        """Check whether a model fits on this system and report how.

        Args:
            model: Model name or size (e.g. "llama3.1:70b", "8b").
            quant: Specific quantization to check (default: all known).
            context: Context length in tokens.

        Returns:
            Exit code: 0 if the model fits somehow, 2 if it doesn't.
        """
        params = llm_math.parse_model_size(model)
        if params is None:
            self.ui.console.print(
                f"Could not parse a model size from '{model}'. "
                "Use names like 'llama3.1:70b' or plain sizes like '8b'.",
                style=self.ui.styles["danger"],
                markup=False,
            )
            return 2

        gpus = GPUDetector.detect()
        mem = MemoryDetector.detect()
        apple = AppleSiliconDetector.detect()

        ram_gb = mem["ram_total_bytes"] / (1024**3)
        vram_gb = max([float(g["vram_total_gb"]) for g in gpus], default=0.0)
        gpu_bandwidth = 0.0
        if apple:
            vram_gb = max(vram_gb, float(apple["unified_memory_gb"]) * 0.75)
            gpu_bandwidth = float(apple.get("memory_bandwidth_gb_s", 0))
        if not gpu_bandwidth:
            gpu_bandwidth = llm_math.gpu_bandwidth_estimate(vram_gb)
        ram_bandwidth = float(
            mem.get("ram_bandwidth_est_gb_s") or llm_math.ram_bandwidth_estimate()
        )

        config_quants = self.config.get("quantization", {}).get("gguf", {})
        selected = quant or llm_math.parse_quant(model)
        quant_names = [selected.upper()] if selected else list(config_quants)
        if not quant_names:
            quant_names = ["Q4_K_M"]

        rows = []
        for quant_name in quant_names:
            bits = llm_math.quant_bits(quant_name, config_quants)
            weights = llm_math.weights_gb(params, bits)
            total = llm_math.total_memory_gb(params, bits, context)

            if vram_gb > 0 and total <= vram_gb:
                fits, bandwidth, budget = "gpu", gpu_bandwidth, vram_gb
            elif total <= ram_gb * 0.8:
                fits, bandwidth, budget = "cpu", ram_bandwidth, ram_gb * 0.8
            else:
                fits, bandwidth = "no", 0.0
                budget = max(vram_gb, ram_gb * 0.8)

            rows.append(
                {
                    "quant": quant_name,
                    "total_gb": total,
                    "fits": fits,
                    "tps": llm_math.tokens_per_second(weights, bandwidth)
                    if fits != "no"
                    else 0.0,
                    "max_ctx": llm_math.max_context_tokens(params, bits, budget),
                }
            )

        report = {
            "model": model,
            "params_b": params,
            "context": context,
            "vram_gb": vram_gb,
            "ram_gb": ram_gb,
            "rows": rows,
        }
        self.ui.print_can_run(report)

        return 0 if any(r["fits"] != "no" for r in rows) else 2

    def diff(self, file_a: str, file_b: str) -> int:
        """Compare two exported JSON system reports.

        Args:
            file_a: Path to the first JSON report.
            file_b: Path to the second JSON report.

        Returns:
            Exit code (0 on success, 1 on error).
        """
        reports = []
        for path in (file_a, file_b):
            try:
                # utf-8-sig tolerates the BOM PowerShell adds on redirect
                with open(path, encoding="utf-8-sig") as f:
                    reports.append(json.load(f))
            except (OSError, ValueError) as e:
                self.ui.console.print(
                    f"Could not load '{path}': {e}",
                    style=self.ui.styles["danger"],
                    markup=False,
                )
                return 1

        self.ui.print_diff(
            reports[0], reports[1], Path(file_a).name, Path(file_b).name
        )
        return 0

    def interactive_mode(self) -> int:
        """Prompt user to select detail level interactively.

        Returns:
            Selected detail level (1, 2, or 3).
        """
        console = self.ui.console
        styles = self.ui.styles

        console.print("Select detail level:", style="bold")
        options = [
            ("1", "success", "Minimal  - Quick overview"),
            ("2", "info", "Normal   - Balanced (default)"),
            ("3", "warning", "Detailed - Full information"),
        ]
        for num, style_key, label in options:
            line = Text("  ")
            line.append(f"[{num}]", style=styles[style_key])
            line.append(f" {label}")
            console.print(line)
        console.print()

        try:
            console.print("Choice [1-3]: ", style="bold", end="", markup=False)
            choice = input().strip()
            if choice in ["1", "2", "3"]:
                return int(choice)
        except (KeyboardInterrupt, EOFError):
            console.print()
            return 2

        return 2


def watch_mode(app: LLMNeofetch, interval: float) -> int:
    """Live-updating system monitor (CPU, RAM, GPUs, LLM processes).

    Args:
        app: Application instance.
        interval: Refresh interval in seconds.

    Returns:
        Exit code (0 after Ctrl+C).
    """
    from rich.console import Group
    from rich.live import Live
    from rich.panel import Panel

    ui = app.ui
    psutil.cpu_percent(interval=None)  # prime the counter

    def build_view() -> Panel:
        rows = []

        cpu_pct = psutil.cpu_percent(interval=None)
        row = Text()
        row.append(f"{'CPU':<10}", style=ui.styles["success"])
        row.append_text(ui.bar(cpu_pct, 100, width=30))
        rows.append(row)

        vmem = psutil.virtual_memory()
        row = Text()
        row.append(f"{'RAM':<10}", style=ui.styles["success"])
        row.append_text(ui.bar(vmem.used, vmem.total, width=30))
        row.append(
            f"  {ui.format_size(vmem.used)} / {ui.format_size(vmem.total)}",
            style=ui.styles["dim"],
        )
        rows.append(row)

        for gpu in GPUDetector.detect():
            vram_total = float(gpu["vram_total_gb"])
            vram_used = float(gpu["vram_used_gb"])
            util = float(gpu["utilization_percent"])
            if vram_total <= 0 and util <= 0:
                continue
            label = str(gpu["name"])[:24]
            if util > 0:
                row = Text()
                row.append(f"{'GPU':<10}", style=ui.styles["success"])
                row.append_text(ui.bar(util, 100, width=30))
                row.append(f"  {label}", style=ui.styles["dim"])
                rows.append(row)
            if vram_total > 0:
                row = Text()
                row.append(f"{'VRAM':<10}", style=ui.styles["success"])
                row.append_text(ui.bar(vram_used, vram_total, width=30))
                row.append(
                    f"  {vram_used:.1f} / {vram_total:.1f} GB",
                    style=ui.styles["dim"],
                )
                rows.append(row)

        processes = ProcessDetector.detect()
        if processes:
            rows.append(Text())
            for proc in processes[:5]:
                row = Text()
                row.append(f"{proc['name'][:20]:<22}", style="bold")
                row.append(f"RAM {proc['ram_gb']:.1f} GB", style=ui.styles["dim"])
                if proc.get("vram_mb"):
                    row.append(
                        f"  VRAM {proc['vram_mb'] / 1024:.1f} GB",
                        style=ui.styles["dim"],
                    )
                rows.append(row)

        title = Text(f"⚡ LLM-Neofetch++ watch • {interval:g}s • Ctrl+C to exit")
        return Panel(
            Group(*rows),
            title=title,
            width=min(ui.width + 10, 90),
            border_style=ui.styles["secondary"],
            padding=(1, 2),
        )

    try:
        with Live(
            build_view(), console=ui.console, refresh_per_second=2
        ) as live:
            while True:
                time.sleep(interval)
                live.update(build_view())
    except KeyboardInterrupt:
        return 0


def main() -> int:
    """Main entry point for CLI execution.

    Returns:
        Exit code (0=success, non-zero=error).
    """
    parser = argparse.ArgumentParser(
        prog="llm-neofetch",
        description="LLM-Neofetch++ - Advanced system info for local LLM usage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  llm-neofetch                          # Normal output
  llm-neofetch -d 3                     # Detailed output
  llm-neofetch -b --bench-mem           # With disk + memory benchmarks
  llm-neofetch --bench-llm              # Real tokens/s via Ollama
  llm-neofetch --export report.html     # Full-color HTML report
  llm-neofetch --json                   # Machine-readable JSON to stdout
  llm-neofetch --watch                  # Live monitor (Ctrl+C to exit)
  llm-neofetch can-run llama3.1:70b     # Will it fit on this machine?
  llm-neofetch diff a.json b.json       # Compare two exported reports
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
        "--bench-mem",
        action="store_true",
        help="Run memory bandwidth benchmark",
    )
    parser.add_argument(
        "--bench-llm",
        nargs="?",
        const="",
        default=None,
        metavar="MODEL",
        help="Measure real tokens/s via Ollama (default: smallest installed model)",
    )
    parser.add_argument(
        "-i", "--interactive", action="store_true", help="Interactive mode"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout and exit",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Live system monitor (CPU/RAM/GPU/LLM processes)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="SEC",
        help="Refresh interval for --watch (default: 2)",
    )
    parser.add_argument(
        "--theme",
        type=str,
        choices=["default", "dracula", "nord", "solarized", "mono"],
        help="Color theme",
    )
    parser.add_argument(
        "--compact", action="store_true", help="Compact output (less whitespace)"
    )
    parser.add_argument(
        "--no-emoji", action="store_true", help="Disable emoji in output"
    )
    parser.add_argument(
        "--export",
        type=str,
        metavar="FILE",
        help="Export to file (.json, .yaml, .md, .html)",
    )
    parser.add_argument(
        "--config", type=str, metavar="FILE", help="Custom config file path"
    )
    parser.add_argument(
        "--version", action="version", version=f"LLM-Neofetch++ v{__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    can_run_parser = subparsers.add_parser(
        "can-run", help="Check whether a model fits on this system"
    )
    can_run_parser.add_argument(
        "model", help="Model name or size (e.g. llama3.1:70b, 8b)"
    )
    can_run_parser.add_argument(
        "--quant", type=str, help="Check one quantization only (e.g. Q4_K_M)"
    )
    can_run_parser.add_argument(
        "--context",
        type=int,
        default=8192,
        metavar="TOKENS",
        help="Context length in tokens (default: 8192)",
    )

    diff_parser = subparsers.add_parser(
        "diff", help="Compare two exported JSON reports"
    )
    diff_parser.add_argument("file_a", help="First JSON report")
    diff_parser.add_argument("file_b", help="Second JSON report")

    args = parser.parse_args()

    try:
        app = LLMNeofetch(
            config_path=args.config,
            verbose=args.verbose,
            theme=args.theme,
            compact=args.compact,
            no_emoji=args.no_emoji,
        )

        if args.command == "can-run":
            return app.can_run(args.model, args.quant, args.context)

        if args.command == "diff":
            return app.diff(args.file_a, args.file_b)

        if args.watch:
            return watch_mode(app, args.interval)

        if args.json:
            info = app.collect_system_info(
                benchmark=args.benchmark,
                quiet=True,
                bench_mem=args.bench_mem,
                bench_llm=args.bench_llm,
            )
            print(json.dumps(info, indent=2, default=str))
            return 0

        detail_level = args.detail
        if args.interactive:
            detail_level = app.interactive_mode()

        info = app.collect_system_info(
            benchmark=args.benchmark,
            extended=detail_level >= 2,
            bench_mem=args.bench_mem,
            bench_llm=args.bench_llm,
        )

        app.display_system_info(info, detail_level=detail_level)

        if args.export:
            ext = Path(args.export).suffix.lower()
            format_map = {
                ".json": "json",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".md": "markdown",
                ".markdown": "markdown",
                ".html": "html",
                ".htm": "html",
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
