import { defineConfig } from 'vitest/config';

// static/js は classic script（IIFE・モジュールではない）ため、テストは
// tests/js/helpers/load-source.js 経由で「宣言を抜き出して評価する」方式を取る。
// 実装側を ESM 化する改変は行わない。
export default defineConfig({
  test: {
    // DOM API（document / sessionStorage）に触る関数があるため jsdom 固定。
    environment: 'jsdom',
    include: ['tests/js/**/*.test.js'],
    // Python 側のテスト・仮想環境・成果物ディレクトリは走査対象外。
    exclude: ['node_modules/**', 'venv/**', 'output/**', 'tests/e2e/**'],
    globals: false,
    reporters: 'default',
  },
});
