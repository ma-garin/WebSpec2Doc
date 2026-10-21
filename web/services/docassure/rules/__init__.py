"""Document Assurance の決定論ルール。公開 API は load_pack / run_rules。"""
from .engine import load_pack, run_rules

__all__ = ["load_pack", "run_rules"]
