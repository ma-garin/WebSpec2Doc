"""Native reverse analysis（外部 CLI 無しの JS 静的解析）。

契約は facts.py、差し替え点は parser.py、組立は evidence.py。
service は ``run_static_analysis`` を呼ぶ。
"""

from reverse_analysis.native.evidence import ENGINE_VERSION, NATIVE_VERSION, NativeResult, run_static_analysis

__all__ = ["ENGINE_VERSION", "NATIVE_VERSION", "NativeResult", "run_static_analysis"]
