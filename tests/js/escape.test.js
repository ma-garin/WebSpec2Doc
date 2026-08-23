// HTML エスケープ関数群。innerHTML へ流し込む唯一の防御線なので、
// 5 文字それぞれ・組み合わせ・null 相当・多重適用を確かめる。
import { describe, expect, it } from 'vitest';
import { loadFunction } from './helpers/load-source.js';

const escHtml = loadFunction('static/js/core.js', 'escHtml');
const escExecution = loadFunction('static/js/ta-execution.js', 'esc');
const escDesign = loadFunction('static/js/ta-design.js', 'esc');
const escPreflight = loadFunction('static/js/autorun-preflight.js', 'esc');

describe('core.js escHtml', () => {
  it.each([
    ['&', '&amp;'],
    ['<', '&lt;'],
    ['>', '&gt;'],
    ['"', '&quot;'],
    ["'", '&#39;'],
  ])('%p を %p に変換する', (input, expected) => {
    expect(escHtml(input)).toBe(expected);
  });

  it('5 文字が混在しても全て変換する', () => {
    expect(escHtml(`&<>"'`)).toBe('&amp;&lt;&gt;&quot;&#39;');
  });

  it('script タグを無害化する', () => {
    expect(escHtml(`<script>alert('x')</script>`))
      .toBe('&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;');
  });

  it('属性を閉じさせない', () => {
    expect(escHtml('" onmouseover="alert(1)'))
      .toBe('&quot; onmouseover=&quot;alert(1)');
  });

  it('二重適用するとアンパサンドが再エスケープされる（多重適用は禁止）', () => {
    expect(escHtml(escHtml('<'))).toBe('&amp;lt;');
  });

  it('エスケープ対象を含まない文字列はそのまま返す', () => {
    expect(escHtml('ログイン画面 / login-page_01')).toBe('ログイン画面 / login-page_01');
  });

  it('非文字列も文字列化して扱う', () => {
    expect(escHtml(0)).toBe('0');
    expect(escHtml(null)).toBe('null');
  });
});

describe('ta-execution esc（escHtml へ委譲、不在時は自前で置換）', () => {
  it('escHtml が無い読込順でも 5 文字を変換する', () => {
    expect(escExecution(`&<>"'`)).toBe('&amp;&lt;&gt;&quot;&#39;');
  });

  it('escHtml があれば委譲する', () => {
    const calls = [];
    const esc = loadFunction('static/js/ta-execution.js', 'esc', {
      escHtml: (s) => {
        calls.push(s);
        return 'DELEGATED';
      },
    });
    expect(esc('<b>')).toBe('DELEGATED');
    expect(calls).toEqual(['<b>']);
  });

  it('null / undefined を空文字ではなく文字列化して返す（実装差の記録）', () => {
    expect(escExecution(null)).toBe('null');
    expect(escExecution(undefined)).toBe('undefined');
  });
});

describe('ta-design esc（自前実装・単一引用符は対象外）', () => {
  it.each([
    ['&', '&amp;'],
    ['<', '&lt;'],
    ['>', '&gt;'],
    ['"', '&quot;'],
  ])('%p を %p に変換する', (input, expected) => {
    expect(escDesign(input)).toBe(expected);
  });

  it('null / undefined は空文字にする', () => {
    expect(escDesign(null)).toBe('');
    expect(escDesign(undefined)).toBe('');
  });

  // 現状の挙動を固定する。ta-design.js は値を二重引用符の属性にしか埋めないため
  // 実害は出ていないが、単一引用符属性へ流用した瞬間に破れる。
  it("単一引用符は変換されない（他の関数との差分）", () => {
    expect(escDesign("it's")).toBe("it's");
    expect(escHtml("it's")).toBe('it&#39;s');
  });

  it('& を先に変換するため二重エスケープにならない', () => {
    expect(escDesign('&lt;')).toBe('&amp;lt;');
  });
});

describe('autorun-preflight esc', () => {
  it('5 文字すべてを変換する', () => {
    expect(escPreflight(`&<>"'`)).toBe('&amp;&lt;&gt;&quot;&#39;');
  });

  it('null / undefined は空文字にする', () => {
    expect(escPreflight(null)).toBe('');
    expect(escPreflight(undefined)).toBe('');
  });

  it('数値 0 を空文字に潰さない', () => {
    expect(escPreflight(0)).toBe('0');
  });
});
