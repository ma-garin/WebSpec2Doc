# axe-core vendored asset

- Version: 4.10.2
- Source: `https://registry.npmjs.org/axe-core/-/axe-core-4.10.2.tgz`（`package/axe.min.js` を無改変で同梱）
- SHA-256: `b511cd9dec01c76f4b2ad1723b66b6db37d4c2eb4ed199076e1829d9ee7b75e3`
- License: MPL-2.0（`LICENSE` に全文同梱。docs/11 §1-4 の「MIT」記載は誤りで、本タスクで訂正した）
- Runtime policy: この同梱ファイルのみが許可された axe-core 実行元。CDN フォールバックは行わない（オフライン完結・AC-2）。
- 配置理由: 注入元が Python（`src/ux/axe_runner.py`）であり、層分離（src から web/static へ依存しない）を守るため `static/vendor/` ではなく `src/ux/assets/` に置く。

## 更新手順

1. `npm pack axe-core@<新バージョン>` で tarball を取得する（CDN からの直接取得は避け、npm registry からのみ取得する）。
2. tarball を展開し `package/axe.min.js` と `package/LICENSE` をそのまま（無改変で）本ディレクトリへコピーする。
3. `sha256sum axe.min.js` を実行し、本ファイルの Version / SHA-256 を更新する。
4. `tests/test_axe_runner.py::test_axe_asset_sha256_matches_manifest` を実行し一致を確認する。
5. `LICENSE` の内容が MPL-2.0 のままであることを確認する（ライセンス変更があれば別途対応を検討する）。
