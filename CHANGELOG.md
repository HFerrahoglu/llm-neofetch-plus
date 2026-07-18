# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-07-18

### Added
- **Context-aware recommendations**: model tiers now show the estimated
  max context length and generation speed on your hardware, computed from
  weights + KV cache (GQA-aware) + overhead.
- **`can-run` command**: `llm-neofetch can-run llama3.1:70b [--quant Q4_K_M]
  [--context 16384]` prints a fits/doesn't-fit verdict per quantization with
  memory needs, estimated speed, and max context. Exit code 2 when nothing fits.
- **`diff` command**: compare two exported JSON reports side by side.
- **`--watch` live monitor**: CPU/RAM/GPU/LLM-process dashboard that
  refreshes in place (`--interval` to tune).
- **`--json`**: machine-readable system report on stdout.
- **HTML export**: `--export report.html` renders the full colored report.
- **Themes**: `--theme dracula|nord|solarized|mono` or `ui.theme` in config.
- **`--compact`** and **`--no-emoji`** output modes (compact_mode config
  key now actually works).
- **Real LLM benchmark**: `--bench-llm [MODEL]` measures actual tokens/s
  through the Ollama API.
- **Memory bandwidth benchmark**: `--bench-mem` measures single-thread copy
  throughput; RAM speed/module info and a bandwidth estimate are shown in
  the Memory section.
- **Installed backend detection**: Ollama (version, running state, model
  count), LM Studio, llama.cpp, vLLM.
- **Installed model scan**: lists downloaded Ollama/LM Studio models with a
  fits-on-GPU/CPU verdict per model.
- **Running LLM process detection** with RAM and per-process GPU memory.
- **AI runtime detection**: CUDA, ROCm, Vulkan, DirectML, Metal versions.
- **Environment detection**: WSL, Docker, cloud vendors (AWS/GCP/Azure),
  VM hypervisors — shown in System Information.
- **NPU detection**: Intel AI Boost, AMD XDNA, Apple Neural Engine.
- **amd-smi support** (tried before rocm-smi) and **pynvml fallback** when
  nvidia-smi is not on PATH (optional `gpu` extra).
- **Fine-tuning guide**: QLoRA/LoRA VRAM needs with fit verdicts (detail 3).
- **Multi-GPU summary**: total VRAM line with tensor-parallelism note.
- **Apple Silicon detail**: GPU core count and memory bandwidth per chip
  variant, used to power recommendations on Macs.
- Linux disk benchmark now uses O_DIRECT to bypass the page cache (the
  cached-read note only appears when the fallback path was used).

## [1.1.0] - 2026-07-18

### Fixed
- **Escape codes printed as literal text**: color codes written as
  `"\033[...]"` in config.yaml were parsed by YAML as a NUL byte plus the
  literal text `33[...`, garbling the entire output once the config loaded.
  Colors are now Rich style names (e.g. `"green"`, `"bold blue"`); raw ANSI
  values from legacy user configs are ignored gracefully.
- **Packaging**: pip-installed package was broken (`ModuleNotFoundError`) —
  the main module and bundled config were missing from the wheel. The project
  is now a proper `llm_neofetch` package; `python -m llm_neofetch` also works.
- **Windows config loading**: config files are now read as UTF-8; previously
  the bundled config failed to load on non-UTF-8 locales, leaving model
  recommendations, the quantization guide, and backend comparison empty.
- **Windows disk type detection**: NVMe/SSD/HDD is now detected via
  PowerShell `Get-PhysicalDisk` (previously always "Unknown" on Windows).
- **Windows CPU name**: the real marketing name is read from the registry
  (previously the raw family string, e.g. "Intel64 Family 6 Model 186");
  the deprecated `wmic` fallback was removed.
- **AMD GPU detection**: rocm-smi output (VRAM, utilization, temperature) is
  now actually parsed via `--json`; previously the results were discarded and
  AMD GPUs always reported 0 VRAM.
- **Intel GPU detection**: real device names are parsed from `sycl-ls`.
- **Windows GPU VRAM**: read from the registry (64-bit), avoiding WMI's
  4 GB `AdapterRAM` cap; GPU vendor is now derived from the adapter name.
- **Battery bar colors**: high charge is now green (was red).
- **Disk benchmark on Windows**: falls back to a writable directory on the
  same drive instead of silently failing on the drive root; benchmark
  results are now shown at every detail level when `-b` is used.
- Export files are written as UTF-8.
- Header box alignment with emoji; version number shown in the banner.
- Windows kernel line now shows the build number instead of "11".

### Changed
- **The terminal UI was rewritten on top of [Rich](https://github.com/Textualize/rich)**:
  automatic terminal-width handling, correct emoji alignment, proper color
  support on all Windows consoles, tables for recommendations/quantization/
  backends, and graceful no-color output when piped. Adds `rich` as a
  dependency.
- User config files are now deep-merged over complete built-in defaults, so
  partial configs no longer disable whole sections.
- Config search order: explicit `--config`, then user config
  (`~/.config/llm-neofetch/`), then `/etc/llm-neofetch/`, then the bundled
  package config (previously the bundled config shadowed user config).
- Disk benchmark writes incompressible random data and reports the directory
  used; read speed is labeled as potentially cached.
- Library imports moved from `src.detectors` / `src.ui` to
  `llm_neofetch.detectors` / `llm_neofetch.ui`.
- Maximum CPU frequency is shown alongside the current frequency.

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
