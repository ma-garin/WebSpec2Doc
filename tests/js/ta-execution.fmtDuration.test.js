// static/js/ta-execution.js fmtDuration の境界。
// 契約: 秒数 → 「N秒」/「N分M秒」、算出不能・非正値は「—」（0 を「0秒」と出さない）。
import { describe, expect, it } from 'vitest';
import { loadFunction } from './helpers/load-source.js';

const fmtDuration = loadFunction('static/js/ta-execution.js', 'fmtDuration');

describe('fmtDuration / 正常系', () => {
  it.each([
    [1, '1秒'],
    [30, '30秒'],
    [59, '59秒'],
    [60, '1分0秒'],
    [61, '1分1秒'],
    [90, '1分30秒'],
    [599, '9分59秒'],
    [3599, '59分59秒'],
    [3600, '60分0秒'],
  ])('fmtDuration(%p) は %p', (input, expected) => {
    expect(fmtDuration(input)).toBe(expected);
  });

  it('小数秒は四捨五入して整数表示にする', () => {
    expect(fmtDuration(12.4)).toBe('12秒');
    expect(fmtDuration(12.5)).toBe('13秒');
  });

  it('数値文字列も受け付ける（API 由来の値が文字列でも壊れない）', () => {
    expect(fmtDuration('90')).toBe('1分30秒');
  });

  it('1 時間を超えても分に繰り上げたまま表示する（時間の単位は持たない）', () => {
    expect(fmtDuration(7325)).toBe('122分5秒');
  });
});

describe('fmtDuration / 非正値・非数は「—」', () => {
  it.each([
    [0, '0 は測定なしとして扱う'],
    [-1, '負値'],
    [-3600, '大きな負値'],
    [NaN, 'NaN'],
    [Infinity, 'Infinity'],
    [-Infinity, '-Infinity'],
    [undefined, 'undefined'],
    [null, 'null（Number(null) は 0）'],
    ['', '空文字（Number("") は 0）'],
    ['abc', '数値化できない文字列'],
    [{}, 'オブジェクト'],
  ])('fmtDuration(%p) は「—」: %s', (input) => {
    expect(fmtDuration(input)).toBe('—');
  });
});

describe('fmtDuration / 既知の表示ゆれ（現状の挙動を固定する）', () => {
  // 秒側を Math.round、分側を Math.floor で別々に丸めているため、
  // 60 秒に繰り上がる境界で「60秒」「N分60秒」が出る。実装は本タスクの範囲外のため
  // 現状を明示的に固定し、R-09 の検出結果として報告する。
  it('59.6 秒は繰り上がらず「60秒」になる', () => {
    expect(fmtDuration(59.6)).toBe('60秒');
  });

  it('119.6 秒は「2分0秒」ではなく「1分60秒」になる', () => {
    expect(fmtDuration(119.6)).toBe('1分60秒');
  });
});
