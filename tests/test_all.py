"""
Unit tests for LLM-Neofetch++
"""

import sys
import unittest
from pathlib import Path

# Allow running tests from a source checkout without installation
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_neofetch.detectors import (
    CPUDetector,
    DiskDetector,
    GPUDetector,
    MemoryDetector,
    MotherboardDetector,
    OSDetector,
)
from llm_neofetch.ui import UIRenderer


class TestFormatting(unittest.TestCase):
    """Test formatting functions"""

    def setUp(self):
        self.ui = UIRenderer()

    def test_format_size(self):
        """Test size formatting"""
        self.assertEqual(self.ui.format_size(0), "0 B")
        self.assertEqual(self.ui.format_size(1024), "1.0 KiB")
        self.assertEqual(self.ui.format_size(1024**2), "1.0 MiB")
        self.assertEqual(self.ui.format_size(1024**3), "1.0 GiB")
        self.assertEqual(self.ui.format_size(1024**4), "1.0 TiB")

    def test_bar(self):
        """Test usage bar generation"""
        bar = self.ui.bar(50, 100, width=10)
        plain = bar.plain
        self.assertIn("█", plain)
        self.assertIn("░", plain)
        self.assertIn("50.0%", plain)

    def test_bar_invert(self):
        """Test inverted semantics: high value is good (green)"""
        bar = self.ui.bar(96, 100, width=10, invert=True)
        first_span_style = str(bar.spans[0].style)
        self.assertEqual(first_span_style, self.ui.styles["success"])

        bar = self.ui.bar(96, 100, width=10)
        first_span_style = str(bar.spans[0].style)
        self.assertEqual(first_span_style, self.ui.styles["danger"])

    def test_level_style(self):
        """Test severity style thresholds"""
        self.assertEqual(self.ui.level_style(30), self.ui.styles["success"])
        self.assertEqual(self.ui.level_style(60), self.ui.styles["warning"])
        self.assertEqual(self.ui.level_style(90), self.ui.styles["danger"])


class TestDetectors(unittest.TestCase):
    """Test hardware detectors"""

    def test_os_detector(self):
        """Test OS detection"""
        os_info = OSDetector.detect()
        self.assertIsInstance(os_info, dict)
        self.assertIn('system', os_info)
        self.assertIn('platform', os_info)

    def test_cpu_detector(self):
        """Test CPU detection"""
        cpu_info = CPUDetector.detect()
        self.assertIsInstance(cpu_info, dict)
        self.assertIn('name', cpu_info)
        self.assertIn('cores_physical', cpu_info)
        self.assertIn('cores_logical', cpu_info)

    def test_gpu_detector(self):
        """Test GPU detection"""
        gpus = GPUDetector.detect()
        self.assertIsInstance(gpus, list)
        self.assertGreater(len(gpus), 0)

        # Check first GPU structure
        gpu = gpus[0]
        self.assertIn('vendor', gpu)
        self.assertIn('name', gpu)
        self.assertIn('vram_total_gb', gpu)

    def test_memory_detector(self):
        """Test memory detection"""
        mem_info = MemoryDetector.detect()
        self.assertIsInstance(mem_info, dict)
        self.assertIn('ram_total_bytes', mem_info)
        self.assertGreater(mem_info['ram_total_bytes'], 0)

    def test_disk_detector(self):
        """Test disk detection"""
        disks = DiskDetector.detect()
        self.assertIsInstance(disks, list)

        if len(disks) > 0:
            disk = disks[0]
            self.assertIn('mountpoint', disk)
            self.assertIn('total_bytes', disk)
            self.assertIn('type', disk)

    def test_motherboard_detector(self):
        """Test motherboard detection"""
        mb_info = MotherboardDetector.detect()
        self.assertIsInstance(mb_info, str)


class TestUIRenderer(unittest.TestCase):
    """Test UI rendering"""

    def setUp(self):
        import io

        from rich.console import Console

        self.output = io.StringIO()
        self.ui = UIRenderer(console=Console(file=self.output, width=80))

    def test_styles_initialization(self):
        """Test default styles are present"""
        for key in ("primary", "secondary", "success", "warning", "danger", "info"):
            self.assertIn(key, self.ui.styles)

    def test_legacy_ansi_config_ignored(self):
        """Raw ANSI codes from legacy configs must fall back to defaults"""
        ui = UIRenderer({"colors": {"primary": "\x0033[1;34m", "success": "green"}})
        self.assertEqual(ui.styles["primary"], "blue")
        self.assertEqual(ui.styles["success"], "green")

    def test_gpu_info_display(self):
        """Test GPU info display renders name without escape garbage"""
        gpu = {
            'vendor': 'NVIDIA',
            'name': 'Test GPU',
            'vram_total_gb': 8,
            'vram_used_gb': 2,
            'utilization_percent': 50,
            'temperature_c': 60
        }

        self.ui.print_gpu_info(gpu)
        rendered = self.output.getvalue()
        self.assertIn("Test GPU", rendered)
        self.assertNotIn("33[", rendered)


class TestConfig(unittest.TestCase):
    """Test configuration loading and merging"""

    def test_deep_merge(self):
        """Test recursive config merge"""
        from llm_neofetch.app import _deep_merge

        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 9}, "c": 4}
        merged = _deep_merge(base, override)

        self.assertEqual(merged["a"]["x"], 1)
        self.assertEqual(merged["a"]["y"], 9)
        self.assertEqual(merged["b"], 3)
        self.assertEqual(merged["c"], 4)

    def test_config_always_complete(self):
        """Config must contain all sections even without a config file"""
        from llm_neofetch.app import LLMNeofetch

        app = LLMNeofetch(config_path="/nonexistent/config.yaml")
        for section in ("ui", "colors", "models", "quantization", "backends"):
            self.assertIn(section, app.config)
        self.assertGreater(len(app.config["models"]), 0)


class TestLLMMath(unittest.TestCase):
    """Test LLM memory/performance estimation math"""

    def test_weights_gb(self):
        """8B model at Q4_K_M is roughly 4-5 GB"""
        from llm_neofetch import llm_math

        weights = llm_math.weights_gb(8, 4.5)
        self.assertGreater(weights, 3.5)
        self.assertLess(weights, 5.5)

    def test_kv_cache_scales_with_context(self):
        """KV cache must grow linearly with context length"""
        from llm_neofetch import llm_math

        kv_4k = llm_math.kv_cache_gb(8, 4096)
        kv_64k = llm_math.kv_cache_gb(8, 65536)
        self.assertAlmostEqual(kv_64k / kv_4k, 16.0, places=3)
        # 8B (GQA): ~0.5 GB at 4K context
        self.assertGreater(kv_4k, 0.2)
        self.assertLess(kv_4k, 1.0)

    def test_max_context_roundtrip(self):
        """A model must fit at its own computed max context"""
        from llm_neofetch import llm_math

        budget = 8.0
        max_ctx = llm_math.max_context_tokens(8, 4.5, budget)
        self.assertGreater(max_ctx, 0)
        total = llm_math.total_memory_gb(8, 4.5, max_ctx)
        self.assertLessEqual(total, budget + 0.01)

    def test_max_context_zero_when_too_big(self):
        """70B does not fit in 8 GB at any context"""
        from llm_neofetch import llm_math

        self.assertEqual(llm_math.max_context_tokens(70, 4.5, 8.0), 0)

    def test_parse_model_size(self):
        """Parse parameter counts from model names"""
        from llm_neofetch import llm_math

        self.assertEqual(llm_math.parse_model_size("llama3.1:70b"), 70.0)
        self.assertEqual(llm_math.parse_model_size("Qwen2.5 0.5B"), 0.5)
        self.assertEqual(llm_math.parse_model_size("8b-instruct-q4_K_M"), 8.0)
        self.assertIsNone(llm_math.parse_model_size("mystery-model"))

    def test_parse_quant(self):
        """Parse quantization tags from model names"""
        from llm_neofetch import llm_math

        self.assertEqual(
            llm_math.parse_quant("llama3.1:8b-instruct-q4_K_M"), "Q4_K_M"
        )
        self.assertEqual(llm_math.parse_quant("model-q8_0"), "Q8_0")
        self.assertIsNone(llm_math.parse_quant("llama3.1:8b"))

    def test_tokens_per_second(self):
        """Speed estimate scales with bandwidth over weights"""
        from llm_neofetch import llm_math

        slow = llm_math.tokens_per_second(40, 50)
        fast = llm_math.tokens_per_second(5, 900)
        self.assertLess(slow, 2)
        self.assertGreater(fast, 100)

    def test_finetune_ordering(self):
        """QLoRA must need less VRAM than LoRA, LoRA less than full"""
        from llm_neofetch import llm_math

        qlora = llm_math.finetune_vram_gb(8, "qlora")
        lora = llm_math.finetune_vram_gb(8, "lora")
        full = llm_math.finetune_vram_gb(8, "full")
        self.assertLess(qlora, lora)
        self.assertLess(lora, full)


class TestEnvironment(unittest.TestCase):
    """Test environment detection (offline-safe)"""

    def test_environment_detector(self):
        """Environment detection returns a non-empty string"""
        from llm_neofetch.environment import EnvironmentDetector

        env = EnvironmentDetector.detect()
        self.assertIsInstance(env, str)
        self.assertGreater(len(env), 0)

    def test_runtime_detector(self):
        """Runtime detection returns a dict of runtimes"""
        from llm_neofetch.environment import RuntimeDetector

        runtimes = RuntimeDetector.detect()
        self.assertIsInstance(runtimes, dict)
        self.assertIn("CUDA", runtimes)

    def test_backend_detector_offline(self):
        """Backend detection must not raise without backends"""
        from llm_neofetch.environment import BackendDetector

        backends = BackendDetector.detect()
        self.assertIsInstance(backends, list)

    def test_find_value_nested(self):
        """amd-smi style nested value extraction"""
        from llm_neofetch.detectors import GPUDetector

        data = {
            "asic": {"market_name": "RX 7900 XTX"},
            "vram": {"size": {"value": 24560, "unit": "MB"}},
        }
        self.assertEqual(
            GPUDetector._find_value(data, "market_name"), "RX 7900 XTX"
        )
        self.assertEqual(GPUDetector._find_number(data, "size"), 24560.0)


class TestThemes(unittest.TestCase):
    """Test theme support"""

    def test_all_themes_have_all_keys(self):
        """Every theme must define every semantic style"""
        from llm_neofetch.ui import DEFAULT_STYLES, THEMES

        for name, theme in THEMES.items():
            self.assertEqual(
                set(theme.keys()), set(DEFAULT_STYLES.keys()), f"theme: {name}"
            )

    def test_theme_selection(self):
        """UIRenderer must pick up the configured theme"""
        from llm_neofetch.ui import THEMES

        ui = UIRenderer({"ui": {"theme": "dracula"}})
        self.assertEqual(ui.styles["primary"], THEMES["dracula"]["primary"])

    def test_unknown_theme_falls_back(self):
        """Unknown theme names must fall back to defaults"""
        ui = UIRenderer({"ui": {"theme": "no-such-theme"}})
        self.assertEqual(ui.styles["primary"], "blue")


class TestCanRun(unittest.TestCase):
    """Test the can-run render path"""

    def test_print_can_run_renders(self):
        import io

        from rich.console import Console

        output = io.StringIO()
        ui = UIRenderer(console=Console(file=output, width=80))
        report = {
            "model": "llama3.1:8b",
            "params_b": 8.0,
            "context": 8192,
            "vram_gb": 24.0,
            "ram_gb": 64.0,
            "rows": [
                {
                    "quant": "Q4_K_M",
                    "total_gb": 6.2,
                    "fits": "gpu",
                    "tps": 120.0,
                    "max_ctx": 65536,
                }
            ],
        }
        ui.print_can_run(report)
        rendered = output.getvalue()
        self.assertIn("llama3.1:8b", rendered)
        self.assertIn("Q4_K_M", rendered)


class TestCommandRunner(unittest.TestCase):
    """Test command execution"""

    def test_run_command_success(self):
        """Test running a simple command"""
        from llm_neofetch.detectors import BaseDetector

        result = BaseDetector.run_command("echo test")
        self.assertEqual(result, "test")

    def test_run_command_failure(self):
        """Test running a non-existent command"""
        from llm_neofetch.detectors import BaseDetector

        result = BaseDetector.run_command("this_command_does_not_exist_12345")
        self.assertEqual(result, "")


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
