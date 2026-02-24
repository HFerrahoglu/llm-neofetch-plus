#!/usr/bin/env python3
"""Example: Using LLM-Neofetch++ as a Python library."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_neofetch import LLMNeofetch


def main():
    """Demonstrate various ways to use LLM-Neofetch++."""
    print("=== Example 1: Basic Usage ===\n")

    app = LLMNeofetch()
    info = app.collect_system_info(benchmark=False)
    app.display_system_info(info, detail_level=2)

    print("\n\n=== Example 2: Accessing Raw Data ===\n")

    cpu = info["cpu"]
    print(f"CPU: {cpu['name']}")
    print(f"Cores: {cpu['cores_physical']} physical / {cpu['cores_logical']} logical")

    gpus = info["gpus"]
    for i, gpu in enumerate(gpus, 1):
        print(f"\nGPU {i}: {gpu['name']}")
        print(f"  VRAM: {gpu['vram_total_gb']:.1f} GB")

    memory = info["memory"]
    ram_gb = memory["ram_total_bytes"] / (1024**3)
    print(f"\nRAM: {ram_gb:.1f} GB")

    print("\n\n=== Example 3: Export to JSON ===\n")

    output_file = "/tmp/system_info.json"
    app.export(info, format="json", output_file=output_file)
    print(f"Exported to: {output_file}")

    print("\n\n=== Example 4: Conditional Logic Based on Hardware ===\n")

    max_vram = max([g["vram_total_gb"] for g in gpus], default=0)

    if max_vram >= 24:
        print("Your system can run 70B models!")
        print("  Recommended: Llama 3.1 70B Q4_K_M")
    elif max_vram >= 12:
        print("Your system can run 30B models!")
        print("  Recommended: Qwen2.5 32B Q4_K_M")
    elif max_vram >= 8:
        print("Your system can run 13-14B models!")
        print("  Recommended: Llama 2 13B Q5_K_M")
    else:
        print("Your system is best suited for CPU inference")
        print("  Recommended: Llama 3.2 3B Q4_K_M")


if __name__ == "__main__":
    main()
