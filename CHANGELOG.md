# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-24

### Added
- CPU detection (model, cores, threads, frequency, temperature)
- GPU detection (NVIDIA, AMD, Intel Arc)
- VRAM detection and usage monitoring
- RAM and swap memory information
- Disk storage detection (NVMe/SSD/HDD)
- Battery information for laptops
- Apple Silicon (M-series) detection with unified memory
- Personalized LLM model recommendations based on hardware
- GGUF quantization format guide
- LLM backend comparison (Ollama, llama.cpp, vLLM, etc.)
- Disk speed benchmarking
- Export to JSON, YAML, and Markdown formats
- Interactive detail level selection
- Configurable UI (colors, emoji, progress bars)
- Comprehensive unit tests
- GitHub Actions CI/CD pipeline
- Pre-commit hooks with ruff

### Fixed
- Cross-platform compatibility (Windows, Linux, macOS)
- Proper error handling for missing hardware sensors
- Type annotations for mypy compatibility

## [0.0.1] - 2024-XX-XX

### Added
- Initial release
- Basic system information display
