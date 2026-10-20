// System02「実行と結果」と System03「静的候補の探索」の判定（純関数）。
// 契約: 一部失敗・一部のみ実行を成功にしない／実行対象と実行済みを混ぜない／認証状態が無いときの 0 を「未実施」と分ける。
import { describe, expect, it } from 'vitest';
import { loadDeclarations, loadFunction } from './helpers/load-source.js';

const runVerdict = loadDeclarations('static/js/ta2/panels.js', ['runVerdict']).runVerdict;
const evKey = loadFunction('static/js/ta2/ws-rea-viewpoints.js', 'evKey');
const { flowModel } = loadDeclarations('static/js/autorun-static-routes.js', ['UNCONFIRMED', 'flowModel']);

describe('runVerdict（System02 の実行判定）', () => {
  const at = '2026-10-20 12:00:00';
  it('実行中は running', () => {
    expect(runVerdict({ running: true, done: 1, total: 3 }, null, 0, 10).code).toBe('running');
  });
  it('記録が無ければ未実行', () => {
    expect(runVerdict({}, null, 0, 10).code).toBe('not_started');
  });
  it('成功と失敗が混在すれば一部失敗（成功にしない）', () => {
    const v = runVerdict({}, { at, total: 8, passed: 7, failed: 1 }, 0, 116);
    expect(v.code).toBe('partial');
    expect(v.label).toBe('一部失敗');
    expect(v.reason).toContain('範囲外の 108 件は前回までの結果のまま');
  });
  it('全件失敗は失敗', () => {
    expect(runVerdict({}, { at, total: 1, passed: 0, failed: 1 }, 0, 116).code).toBe('failed');
  });
  it('結果の無いテストや実行できなかったテストがあれば一部のみ実行', () => {
    expect(runVerdict({}, { at, total: 4, passed: 3, failed: 0 }, 0, 4).label).toBe('一部のみ実行');
    expect(runVerdict({}, { at, total: 3, passed: 3, failed: 0 }, 1, 4).code).toBe('partial');
  });
  it('一部の範囲だけ成功したときは件数付きの成功にする', () => {
    const v = runVerdict({}, { at, total: 2, passed: 2, failed: 0 }, 0, 116);
    expect(v.code).toBe('done');
    expect(v.label).toBe('成功（2 件）');
  });
});

describe('evKey（System02 の由来と根拠）', () => {
  it.each([
    [{ is_new: false, origin: 'existing_candidate', ev_code: 'observed' }, 'base'],
    [{ is_new: true, origin: 'observed', ev_code: 'observed' }, 'observed'],
    [{ is_new: true, origin: 'observed_auth', ev_code: 'observed_auth' }, 'observed_auth'],
    [{ is_new: true, origin: 'static', ev_code: 'static' }, 'static'],
    [{ is_new: true, origin: 'rea_added', ev_code: 'inferred' }, 'inferred'],
    [{ is_new: true, origin: 'rea_added', ev_code: 'ambiguous' }, 'ambiguous'],
    [{ is_new: true, origin: 'unverified', ev_code: 'unverified' }, 'unverified'],
    [{ is_new: true, origin: 'unverified', ev_code: 'unavailable' }, 'unavailable'],
  ])('%o → %s', (v, key) => {
    expect(evKey(v)).toBe(key);
  });
});

describe('flowModel（System03 の流れ図）', () => {
  const items = [
    { status: 'observed', authenticated: false },
    { status: 'observed', authenticated: true },
    { status: 'ambiguous' }, { status: 'unreached' }, { status: 'auth_required' }, { status: 'failed' },
  ];
  it('段ごとの数を分け、未確認・曖昧に 4 状態をまとめる', () => {
    const m = flowModel({ items, before: { static_routes: 8 }, after: { system02_runnable: 2, auth_state_available: true } });
    expect(m).toMatchObject({ before: 8, probed: 6, notProbed: 2, unauth: 1, auth: 1, unconfirmed: 4, runnable: 2 });
  });
  it('認証状態が無く認証済み実測も無ければ 0 ではなく未実施（null）', () => {
    const m = flowModel({ items: items.slice(0, 1), after: { auth_state_available: false } });
    expect(m.auth).toBeNull();
  });
  it('実行対象が不明なら null（0 にしない）', () => {
    expect(flowModel({ items: [], after: {} }).runnable).toBeNull();
  });
});
