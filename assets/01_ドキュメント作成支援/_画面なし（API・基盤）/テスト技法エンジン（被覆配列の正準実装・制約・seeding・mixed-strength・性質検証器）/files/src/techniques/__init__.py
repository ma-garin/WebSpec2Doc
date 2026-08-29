"""テスト技法エンジン — 各技法の正準実装を集約するパッケージ。

これまで境界値が7箇所・組合せが3箇所・状態遷移が2箇所に分散実装され、
うち1つ（analyzer/test_conditions.py の旧 generate_pairwise_cases）は
2-way 被覆を保証しない近似が「ペアワイズ」を名乗る欠陥を抱えていた。
本パッケージが唯一の正準実装であり、既存モジュールは委譲アダプタとして残す。

設計原則（リポジトリ共通）:
- evidence-only: 実測にない値を捏造しない
- 決定的純関数: 乱数・時刻を使わず、同一入力から必ず同一出力
- 各技法の docstring に一次出典（著者・年・タイトル）を記載する
- 生成結果は verify モジュールの機械検証器で被覆性質を検査できる
"""

from techniques.combinatorial import (
    CoverageRequirement,
    CoveringArrayResult,
    generate_covering_array,
)
from techniques.verify import verify_t_way_coverage

__all__ = [
    "CoverageRequirement",
    "CoveringArrayResult",
    "generate_covering_array",
    "verify_t_way_coverage",
]
