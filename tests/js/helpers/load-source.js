// static/js の classic script（IIFE）から、単一の宣言だけを抜き出して評価するローダ。
//
// 前提: static/js/*.js は `(function () { ... })()` で閉じており、内部の関数を
// export していない。実装を ESM 化する改変は禁止されているため、テスト側で
// 「ソースを読む → 対象の宣言をテキストとして切り出す → new Function で評価する」
// という経路を取る。切り出しは文字列・テンプレートリテラル・正規表現リテラル・
// コメントを飛ばしながら括弧の深さを数える簡易スキャナで行う。
//
// 既知の限界（対象関数はいずれも該当しない）:
//   - テンプレートリテラル内にネストしたテンプレートリテラル
//   - 同名の宣言が同一ファイルに複数ある場合は最初の 1 件のみ
//
// new Function について: 評価するのは「このリポジトリ内の static/js から読んだソース」
// と「テストが明示した宣言名」だけで、外部入力は一切通さない。テスト専用であり、
// 本番コード（static/js・Python 側）はこのファイルを読み込まない。
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

const OPEN = '([{';
const CLOSE = ')]}';
const REGEX_PREV_CHARS = '(,=:[!&|?{};+-*%^~<>';
const REGEX_PREV_WORDS = ['return', 'typeof', 'case', 'in', 'of', 'new', 'delete', 'void', 'instanceof'];

export function readSource(relPath) {
  return readFileSync(path.join(REPO_ROOT, relPath), 'utf8');
}

function skipString(src, start) {
  const quote = src[start];
  let i = start + 1;
  while (i < src.length) {
    const ch = src[i];
    if (ch === '\\') {
      i += 2;
      continue;
    }
    if (ch === quote) return i + 1;
    i += 1;
  }
  throw new Error(`文字列リテラルが閉じていません（位置 ${start}）`);
}

function skipComment(src, start) {
  if (src[start] !== '/') return -1;
  if (src[start + 1] === '/') {
    const nl = src.indexOf('\n', start);
    return nl === -1 ? src.length : nl;
  }
  if (src[start + 1] === '*') {
    const end = src.indexOf('*/', start);
    if (end === -1) throw new Error(`ブロックコメントが閉じていません（位置 ${start}）`);
    return end + 2;
  }
  return -1;
}

// `/` が除算ではなく正規表現リテラルの開始かを、直前の非空白文字から判定する。
function isRegexStart(src, start) {
  let j = start - 1;
  while (j >= 0 && /\s/.test(src[j])) j -= 1;
  if (j < 0) return true;
  if (REGEX_PREV_CHARS.includes(src[j])) return true;
  const word = src.slice(Math.max(0, j - 11), j + 1).match(/[A-Za-z$_]+$/);
  return word ? REGEX_PREV_WORDS.includes(word[0]) : false;
}

function skipRegex(src, start) {
  let i = start + 1;
  let inClass = false;
  while (i < src.length) {
    const ch = src[i];
    if (ch === '\\') {
      i += 2;
      continue;
    }
    if (ch === '[') inClass = true;
    else if (ch === ']') inClass = false;
    else if (ch === '/' && !inClass) {
      i += 1;
      while (i < src.length && /[a-z]/.test(src[i])) i += 1;
      return i;
    }
    i += 1;
  }
  throw new Error(`正規表現リテラルが閉じていません（位置 ${start}）`);
}

// start から走査し、stop(ch, depth) が真になった文字の「次」の位置を返す。
function walk(src, start, stop) {
  let depth = 0;
  let i = start;
  while (i < src.length) {
    const ch = src[i];
    if (ch === '"' || ch === "'" || ch === '`') {
      i = skipString(src, i);
      continue;
    }
    if (ch === '/') {
      const afterComment = skipComment(src, i);
      if (afterComment !== -1) {
        i = afterComment;
        continue;
      }
      if (isRegexStart(src, i)) {
        i = skipRegex(src, i);
        continue;
      }
    }
    if (OPEN.includes(ch)) depth += 1;
    else if (CLOSE.includes(ch)) depth -= 1;
    if (stop(ch, depth)) return i + 1;
    i += 1;
  }
  throw new Error('宣言の終端を検出できませんでした');
}

function extractFunction(src, name) {
  const re = new RegExp(`(?:^|\\n)[ \\t]*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = re.exec(src);
  if (!m) return null;
  const start = src.indexOf('function', m.index);
  const parenStart = src.indexOf('(', start);
  const afterParams = walk(src, parenStart, (ch, depth) => CLOSE.includes(ch) && depth === 0);
  const braceStart = src.indexOf('{', afterParams);
  const end = walk(src, braceStart, (ch, depth) => ch === '}' && depth === 0);
  return src.slice(start, end);
}

function extractBinding(src, name) {
  const re = new RegExp(`(?:^|\\n)[ \\t]*(?:const|let|var)\\s+${name}\\s*=`);
  const m = re.exec(src);
  if (!m) return null;
  const trimmed = m[0].replace(/^\n?[ \t]*/, '');
  const start = m.index + (m[0].length - trimmed.length);
  const end = walk(src, start, (ch, depth) => ch === ';' && depth === 0);
  return src.slice(start, end);
}

/**
 * 指定ファイルから複数の宣言を、与えた順序どおりに連結して評価する。
 * 依存する宣言（定数など）を先に並べること。
 *
 * @param {string} relPath リポジトリルートからの相対パス
 * @param {string[]} names 抜き出す宣言名
 * @param {Record<string, unknown>} globals 評価スコープへ注入する値（実装内の同名グローバルを差し替える）
 */
export function loadDeclarations(relPath, names, globals = {}) {
  const src = readSource(relPath);
  const parts = names.map((name) => {
    const snippet = extractFunction(src, name) ?? extractBinding(src, name);
    if (!snippet) throw new Error(`${relPath} に宣言 ${name} が見つかりません`);
    return snippet;
  });
  const keys = Object.keys(globals);
  // 実装側の IIFE は 'use strict' 配下にあるため、評価環境も strict に揃える。
  const body = `'use strict';\n${parts.join('\n')}\nreturn { ${names.join(', ')} };`;
  const factory = new Function(...keys, body);
  return factory(...keys.map((key) => globals[key]));
}

export function loadFunction(relPath, name, globals = {}) {
  return loadDeclarations(relPath, [name], globals)[name];
}
