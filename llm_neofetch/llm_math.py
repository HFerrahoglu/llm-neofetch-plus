"""LLM memory and performance estimation math.

All figures are planning heuristics, not exact measurements. Weight
memory scales with parameter count and quantization bits; KV cache
scales with context length and the model's attention architecture
(approximated from a table of common open-weight models, most of which
use grouped-query attention).
"""

import re
from typing import Dict, Optional, Tuple

# Approximate attention architecture by parameter count (billions):
# (n_layers, n_kv_heads, head_dim). Values follow common open models
# (Llama 3.x, Qwen 2.5); used to estimate KV cache size per token.
_ARCHITECTURES: Tuple[Tuple[float, int, int, int], ...] = (
    (0.5, 24, 2, 64),
    (1.0, 16, 8, 64),
    (3.0, 28, 8, 128),
    (7.0, 28, 4, 128),
    (8.0, 32, 8, 128),
    (13.0, 40, 40, 128),
    (14.0, 48, 8, 128),
    (32.0, 64, 8, 128),
    (34.0, 48, 8, 128),
    (70.0, 80, 8, 128),
    (72.0, 80, 8, 128),
)

# Fallback bits-per-weight when a quant name is unknown
DEFAULT_QUANT_BITS: Dict[str, float] = {
    "Q2_K": 2.5,
    "Q3_K_M": 3.5,
    "Q4_0": 4.5,
    "Q4_K_M": 4.5,
    "Q5_K_M": 5.5,
    "Q6_K": 6.5,
    "Q8_0": 8.0,
    "F16": 16.0,
    "FP16": 16.0,
}

GIB = 1024**3


def nearest_architecture(params_b: float) -> Tuple[int, int, int]:
    """Return (layers, kv_heads, head_dim) for the closest known size.

    Args:
        params_b: Model size in billions of parameters.

    Returns:
        Tuple of (n_layers, n_kv_heads, head_dim).
    """
    best = min(_ARCHITECTURES, key=lambda a: abs(a[0] - params_b))
    return best[1], best[2], best[3]


def weights_gb(params_b: float, bits_per_weight: float) -> float:
    """Estimate model weight memory in GiB.

    Args:
        params_b: Model size in billions of parameters.
        bits_per_weight: Effective bits per weight (e.g. 4.5 for Q4_K_M).

    Returns:
        Weight memory in GiB.
    """
    return params_b * 1e9 * bits_per_weight / 8 / GIB


def kv_cache_gb(params_b: float, context_tokens: int) -> float:
    """Estimate KV cache memory (f16) for a context length in GiB.

    Args:
        params_b: Model size in billions of parameters.
        context_tokens: Context window length in tokens.

    Returns:
        KV cache memory in GiB.
    """
    layers, kv_heads, head_dim = nearest_architecture(params_b)
    bytes_per_token = 2 * layers * kv_heads * head_dim * 2  # K+V, f16
    return bytes_per_token * context_tokens / GIB


def total_memory_gb(
    params_b: float, bits_per_weight: float, context_tokens: int
) -> float:
    """Estimate total inference memory (weights + KV cache + overhead).

    Args:
        params_b: Model size in billions of parameters.
        bits_per_weight: Effective bits per weight.
        context_tokens: Context window length in tokens.

    Returns:
        Total memory requirement in GiB.
    """
    weights = weights_gb(params_b, bits_per_weight)
    kv = kv_cache_gb(params_b, context_tokens)
    overhead = 0.6 + 0.05 * weights  # runtime + compute buffers
    return weights + kv + overhead


def max_context_tokens(
    params_b: float, bits_per_weight: float, budget_gb: float
) -> int:
    """Estimate the largest context that fits in a memory budget.

    Args:
        params_b: Model size in billions of parameters.
        bits_per_weight: Effective bits per weight.
        budget_gb: Available memory in GiB.

    Returns:
        Maximum context length in tokens (0 if the weights don't fit).
    """
    weights = weights_gb(params_b, bits_per_weight)
    overhead = 0.6 + 0.05 * weights
    remaining = budget_gb - weights - overhead
    if remaining <= 0:
        return 0

    layers, kv_heads, head_dim = nearest_architecture(params_b)
    bytes_per_token = 2 * layers * kv_heads * head_dim * 2
    return int(remaining * GIB / bytes_per_token)


def tokens_per_second(model_weights_gb: float, bandwidth_gb_s: float) -> float:
    """Estimate generation speed from memory bandwidth.

    Token generation is memory-bandwidth bound: every token reads all
    weights once. Real-world speed is typically 60-80% of this bound.

    Args:
        model_weights_gb: Weight memory in GiB.
        bandwidth_gb_s: Memory bandwidth in GB/s.

    Returns:
        Estimated tokens per second.
    """
    if model_weights_gb <= 0:
        return 0.0
    return 0.7 * bandwidth_gb_s / model_weights_gb


def gpu_bandwidth_estimate(vram_gb: float) -> float:
    """Rough GPU memory bandwidth estimate from VRAM class.

    Args:
        vram_gb: GPU VRAM in GB.

    Returns:
        Estimated bandwidth in GB/s.
    """
    if vram_gb >= 24:
        return 900.0
    if vram_gb >= 16:
        return 600.0
    if vram_gb >= 12:
        return 500.0
    if vram_gb >= 8:
        return 400.0
    if vram_gb >= 6:
        return 300.0
    # Small VRAM usually means an iGPU sharing system memory bandwidth
    return 80.0


def ram_bandwidth_estimate(
    channels: int = 2, speed_mts: float = 3200.0
) -> float:
    """Estimate system RAM bandwidth.

    Args:
        channels: Number of populated memory channels.
        speed_mts: Memory speed in MT/s.

    Returns:
        Estimated bandwidth in GB/s.
    """
    channels = max(1, channels)
    return channels * speed_mts * 8 / 1000


def finetune_vram_gb(params_b: float, method: str = "qlora") -> float:
    """Estimate minimum VRAM for fine-tuning.

    Heuristics: QLoRA holds 4-bit weights plus optimizer state for
    adapters and activations; LoRA holds fp16 weights plus the same.
    Full fine-tuning needs weights + gradients + optimizer (~16 bytes
    per parameter with Adam).

    Args:
        params_b: Model size in billions of parameters.
        method: 'qlora', 'lora', or 'full'.

    Returns:
        Estimated VRAM requirement in GiB.
    """
    method = method.lower()
    if method == "qlora":
        return weights_gb(params_b, 4.5) + 0.15 * params_b + 1.5
    if method == "lora":
        return weights_gb(params_b, 16.0) + 0.15 * params_b + 1.5
    return params_b * 16e9 / GIB  # full fine-tune with Adam


def parse_model_size(name: str) -> Optional[float]:
    """Parse parameter count in billions from a model name.

    Handles names like "llama3.1:70b", "Qwen2.5 0.5B", "7b-instruct",
    "gemma2:9b-instruct-q4_K_M".

    Args:
        name: Model name string.

    Returns:
        Size in billions of parameters, or None if not found.
    """
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z0-9])", name)
    if not matches:
        return None
    # The size token is usually the last plausible one (e.g. "llama3.1:70b")
    sizes = [float(m) for m in matches if 0.1 <= float(m) <= 1000]
    return sizes[-1] if sizes else None


def parse_quant(name: str) -> Optional[str]:
    """Parse a quantization tag from a model name, if present.

    Args:
        name: Model name string (e.g. "llama3.1:8b-instruct-q4_K_M").

    Returns:
        Normalized quant name (e.g. "Q4_K_M"), or None.
    """
    match = re.search(r"[qQ](\d)_(k_m|k_s|k_l|k|0|1)", name, re.IGNORECASE)
    if not match:
        if re.search(r"\bf(p)?16\b", name, re.IGNORECASE):
            return "F16"
        return None
    return f"Q{match.group(1)}_{match.group(2).upper()}"


def quant_bits(quant: str, config_quants: Optional[Dict] = None) -> float:
    """Look up effective bits-per-weight for a quant name.

    Args:
        quant: Quantization name (e.g. "Q4_K_M").
        config_quants: Optional 'quantization.gguf' config section.

    Returns:
        Bits per weight (defaults to 4.5 when unknown).
    """
    quant = quant.upper()
    if config_quants:
        info = config_quants.get(quant)
        if isinstance(info, dict) and "bits" in info:
            return float(info["bits"])
    return DEFAULT_QUANT_BITS.get(quant, 4.5)
