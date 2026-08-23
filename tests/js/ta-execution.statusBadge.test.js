// static/js/ta-execution.js statusBadge。
// 契約: 既知ステータスはラベルとクラスを対応させ、未知ステータスは「実行中」に寄せる。
import { describe, expect, it } from 'vitest';
import { loadDeclarations } from './helpers/load-source.js';

const { statusBadge } = loadDeclarations(
  'static/js/ta-execution.js',
  ['TA_STATUS_LABELS', 'esc', 'statusBadge'],
);

describe('statusBadge / 既知ステータス', () => {
  it.each([
    ['complete', '完了'],
    ['failed', '失敗'],
    ['cancelled', '中断'],
    ['running', '実行中'],
  ])('%p は %p ラベルと対応するクラスを出す', (status, label) => {
    expect(statusBadge(status))
      .toBe(`<span class="rh-status-badge rh-status-${status}">${label}</span>`);
  });
});

describe('statusBadge / 未知ステータスは実行中へ寄せる', () => {
  it.each([
    ['queued'],
    ['COMPLETE'],
    [''],
    [undefined],
    [null],
  ])('%p は running 扱いにする', (status) => {
    expect(statusBadge(status))
      .toBe('<span class="rh-status-badge rh-status-running">実行中</span>');
  });

  it('ステータス由来の文字列を HTML へ素通ししない', () => {
    const html = statusBadge('<img src=x onerror=alert(1)>');
    expect(html).toBe('<span class="rh-status-badge rh-status-running">実行中</span>');
    expect(html).not.toContain('onerror');
  });
});

describe('statusBadge / 既知の穴（現状の挙動を固定する）', () => {
  // ラベル表は素のオブジェクトリテラルのため、Object.prototype のキーが真値として
  // 拾われる。実装変更は本タスクの範囲外なので、現状を固定して報告する。
  it('__proto__ は未知ステータスとして扱われず、クラスへ混入する', () => {
    const html = statusBadge('__proto__');
    expect(html).toContain('rh-status-__proto__');
    expect(html).not.toContain('実行中');
  });
});
