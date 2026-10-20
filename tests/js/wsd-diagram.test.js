// 自前の図描画器（static/js/wsd-diagram.js）と吹き出し配置（wsd-tour.js）の単体テスト。
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const D = require('../../static/js/wsd-diagram.js');
const T = require('../../static/js/wsd-tour.js');

describe('WsdDiagram.render', () => {
  it('ラベルを HTML エスケープする', () => {
    const svg = D.render({ kind: 'flowchart', nodes: [{ id: 'a', label: '<script>alert(1)</script>' }], edges: [] });
    expect(svg).not.toContain('<script>');
    expect(svg).toContain('&lt;script&gt;');
  });

  it('循環を含んでも例外なく全ノードを描く', () => {
    const nodes = ['a', 'b', 'c'].map(id => ({ id, label: id }));
    const edges = [{ from: 'a', to: 'b' }, { from: 'b', to: 'c' }, { from: 'c', to: 'a' }, { from: 'a', to: 'a' }];
    const svg = D.render({ kind: 'flowchart', direction: 'LR', nodes, edges });
    expect((svg.match(/<text class="wd-text"/g) || []).length).toBe(3);
    expect(svg).toContain('class="wsd-diagram"');
  });

  it('ノード 0 件はプレースホルダ、シーケンスも描ける', () => {
    expect(D.render({ kind: 'flowchart', nodes: [] })).toContain('表示する項目がありません');
    const svg = D.render({
      kind: 'sequence',
      nodes: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }],
      edges: [{ from: 'a', to: 'b', label: '1 click', style: 'dashed' }],
    });
    expect(svg).toContain('1 click');
    expect(svg).toContain('wd-life');
  });

  it('200 ノードを 1 秒以内に描く', () => {
    const nodes = [], edges = [];
    for (let i = 0; i < 200; i++) { nodes.push({ id: `n${i}`, label: `N${i}` }); if (i) edges.push({ from: `n${i >> 1}`, to: `n${i}` }); }
    const t = Date.now();
    D.render({ kind: 'flowchart', nodes, edges });
    expect(Date.now() - t).toBeLessThan(1000);
  });
});

describe('WsdTour._place', () => {
  it('吹き出しを画面内にクランプする', () => {
    const pos = T._place({ left: 100, top: 100, right: 200, bottom: 130, width: 100, height: 30 }, 360, 150, 1000, 800, 'bottom', 'end');
    expect(pos.left).toBeGreaterThanOrEqual(8);
    expect(pos.top).toBe(142);
  });
});
