// static/js/ta-design.js readConditions。
// 契約（実装コメント由来）: キー ta.conditions.v1 /
// 値 {"domain", "items": [{id,title,url,condition,category,priority,note}]}。
// 壊れた JSON・形不一致はデータ無しとして扱い、例外を画面へ出さない。
import { beforeEach, describe, expect, it } from 'vitest';
import { loadFunction } from './helpers/load-source.js';

const KEY = 'ta.conditions.v1';
const readConditions = loadFunction('static/js/ta-design.js', 'readConditions');

const validPayload = {
  domain: 'example.com',
  items: [{
    id: 'C-001',
    title: 'ログイン画面',
    url: 'https://example.com/login',
    condition: 'ID 未入力で送信',
    category: '入力検証',
    priority: 'High',
    note: '',
  }],
};

describe('readConditions / 正常系', () => {
  beforeEach(() => sessionStorage.clear());

  it('保存済みの引き継ぎデータをそのまま返す', () => {
    sessionStorage.setItem(KEY, JSON.stringify(validPayload));
    expect(readConditions()).toEqual(validPayload);
  });

  it('items が複数でも全件返す', () => {
    const many = { domain: 'a.example', items: [validPayload.items[0], { ...validPayload.items[0], id: 'C-002' }] };
    sessionStorage.setItem(KEY, JSON.stringify(many));
    expect(readConditions().items).toHaveLength(2);
  });

  it('domain が無くても items があれば読める（domain は表示注記にしか使わない）', () => {
    sessionStorage.setItem(KEY, JSON.stringify({ items: validPayload.items }));
    expect(readConditions().domain).toBeUndefined();
  });

  it('契約外のキーは読まない', () => {
    sessionStorage.setItem('ta.conditions.v0', JSON.stringify(validPayload));
    expect(readConditions()).toBeNull();
  });
});

describe('readConditions / 異常系はすべて null（例外を出さない）', () => {
  beforeEach(() => sessionStorage.clear());

  it('キー未保存', () => {
    expect(readConditions()).toBeNull();
  });

  it.each([
    ['空文字', ''],
    ['壊れた JSON', '{"domain": "example.com", "items": ['],
    ['JSON ですらない文字列', 'undefined'],
    ['null リテラル', 'null'],
    ['数値', '123'],
    ['配列（トップレベルの形不一致）', '[{"id":"C-001"}]'],
    ['items が無い', '{"domain":"example.com"}'],
    ['items が配列でない', '{"domain":"example.com","items":{"id":"C-001"}}'],
    ['items が空配列', '{"domain":"example.com","items":[]}'],
    ['items が文字列', '{"domain":"example.com","items":"C-001"}'],
  ])('%s は null を返す', (_label, raw) => {
    sessionStorage.setItem(KEY, raw);
    expect(readConditions()).toBeNull();
  });
});

describe('readConditions / ストレージ自体が使えない環境', () => {
  it('getItem が例外を投げても null を返す（プライベートモード等）', () => {
    const fn = loadFunction('static/js/ta-design.js', 'readConditions', {
      sessionStorage: {
        getItem() {
          throw new DOMException('The operation is insecure.', 'SecurityError');
        },
      },
    });
    expect(fn()).toBeNull();
  });
});
