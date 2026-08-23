// ローダ自体の検証。ここが壊れると全 JS テストが「通っているのに何も検証していない」
// 状態になるため、抽出の成功と失敗の双方を確かめる。
import { describe, expect, it } from 'vitest';
import { loadDeclarations, loadFunction, readSource } from './helpers/load-source.js';

describe('load-source ローダ', () => {
  it('関数宣言を抜き出して評価できる', () => {
    const fn = loadFunction('static/js/ta-execution.js', 'fmtDuration');
    expect(typeof fn).toBe('function');
  });

  it('const 束縛（アロー関数）を抜き出して評価できる', () => {
    const fn = loadFunction('static/js/ta-design.js', 'esc');
    expect(typeof fn).toBe('function');
  });

  it('存在しない宣言名は例外にする（黙って undefined を返さない）', () => {
    expect(() => loadFunction('static/js/ta-execution.js', 'noSuchFunction'))
      .toThrow(/宣言 noSuchFunction が見つかりません/);
  });

  it('依存する宣言を順に並べて同一スコープで評価できる', () => {
    const mod = loadDeclarations('static/js/ta-execution.js', ['TA_STATUS_LABELS', 'esc', 'statusBadge']);
    expect(mod.TA_STATUS_LABELS.complete).toBe('完了');
    expect(typeof mod.statusBadge).toBe('function');
  });

  it('注入した値が実装内の同名グローバルを差し替える', () => {
    const esc = loadFunction('static/js/ta-execution.js', 'esc', { escHtml: () => 'INJECTED' });
    expect(esc('<b>')).toBe('INJECTED');
  });

  it('読み取り対象は実ファイルであること（空ファイルを掴んでいない）', () => {
    expect(readSource('static/js/ta-execution.js').length).toBeGreaterThan(1000);
  });
});
