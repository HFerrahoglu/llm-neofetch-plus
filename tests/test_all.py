"""
Unit tests for LLM-Neofetch++
"""

import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from detectors import (
    CPUDetector,
    DiskDetector,
    GPUDetector,
    MemoryDetector,
    MotherboardDetector,
    OSDetector,
)
from ui import UIRenderer


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

    def test_progress_bar(self):
        """Test progress bar generation"""
        bar = self.ui.progress_bar(50, 100, width=10, label="Test")
        self.assertIn("Test", bar)
        self.assertIn("50.0%", bar)

    def test_center_text(self):
        """Test text centering"""
        centered = self.ui.center_text("Test", 20)
        self.assertEqual(len(centered), 20)
        self.assertTrue("Test" in centered)


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
        self.ui = UIRenderer()

    def test_color_initialization(self):
        """Test color codes initialization"""
        self.assertIsNotNone(self.ui.colors.primary)
        self.assertIsNotNone(self.ui.colors.success)
        self.assertIsNotNone(self.ui.colors.reset)

    def test_gpu_info_display(self):
        """Test GPU info display doesn't crash"""
        gpu = {
            'vendor': 'NVIDIA',
            'name': 'Test GPU',
            'vram_total_gb': 8,
            'vram_used_gb': 2,
            'utilization_percent': 50,
            'temperature_c': 60
        }

        # Should not raise exception
        try:
            import io
            import sys
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

            self.ui.print_gpu_info(gpu)

            sys.stdout = old_stdout
        except Exception as e:
            self.fail(f"print_gpu_info raised exception: {e}")


class TestCommandRunner(unittest.TestCase):
    """Test command execution"""

    def test_run_command_success(self):
        """Test running a simple command"""
        from detectors import BaseDetector

        result = BaseDetector.run_command("echo test")
        self.assertEqual(result, "test")

    def test_run_command_failure(self):
        """Test running a non-existent command"""
        from detectors import BaseDetector

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
