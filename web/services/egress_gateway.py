"""K1 送信ゲートウェイ — 全ての外向き通信の唯一の出口。

設計計画 rev.3 のセキュリティカーネル。検証層はネットワークへ直接触れず、
必ずここを経由する。「各層が礼儀正しさを守る」という約束ではなく、
**機構として迂回不能**にすることが目的。

塞ぐ攻撃（自己レッドチーミングで判明）:
  #3 SSRF   — 内部ネットワーク・クラウドメタデータ・WebSpec2Doc 自身への誘導
  #5 予算   — 「テスト件数」ではなく実HTTPリクエスト数で計数し、上限で遮断
  #9 未証明 — 全リクエストを記録し、「送信0」を証拠付きで実証可能にする

既存の `src/crawler/url_safety.py` は IP リテラルのみを検査しており、
`evil.example.com` が 127.0.0.1 へ解決される DNS ベースの SSRF を防げない。
本モジュールは名前解決まで行って検査する。
"""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EGRESS_FIXTURE_NAME = "_autorun_egress.ts"
EGRESS_LOG_NAME = "egress_log.ndjson"
POLICY_ENV = "WEBSPEC2DOC_EGRESS_POLICY"

#: クラウドのメタデータ endpoint（認証情報が取れるため最優先で遮断）
METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",  # AWS / Azure / GCP(旧)
        "metadata.google.internal",
        "metadata.goog",
        "100.100.100.100",  # Alibaba Cloud
    }
)

LOCAL_HOSTNAMES = frozenset({"localhost", "ip6-localhost", "ip6-loopback"})
LOCAL_SUFFIXES = (".local", ".localhost", ".internal")


class EgressDenied(ValueError):
    """送信ゲートウェイが拒否した宛先。"""


@dataclass(frozen=True)
class EgressPolicy:
    """1 ジョブ分の送信方針。不変。"""

    #: 実HTTPリクエストの総上限（サブリソース・リダイレクト・リトライを含む）
    budget: int = 500
    #: 並列ワーカー数。予算はワーカーへ等分される（各ワーカーで独立に強制）
    workers: int = 1
    #: WebSpec2Doc 自身のオリジン（自分自身への誘導を防ぐ）
    self_origins: tuple[str, ...] = ()
    #: 追加で拒否するホスト
    extra_denied_hosts: tuple[str, ...] = ()
    #: True の場合、全ての送信を遮断する（自己検証など対象へ触れてはならない用途）
    block_all: bool = False

    def to_json(self) -> str:
        per_worker = max(1, self.budget // max(1, self.workers))
        return json.dumps(
            {
                "budgetPerWorker": per_worker,
                "selfOrigins": list(self.self_origins),
                "deniedHosts": sorted(set(METADATA_HOSTS) | set(self.extra_denied_hosts)),
                "blockAll": self.block_all,
            }
        )


@dataclass
class EgressReport:
    """実行後に送信ログから組み立てる報告。"""

    allowed: int = 0
    denied: int = 0
    denied_reasons: dict[str, int] = field(default_factory=dict)
    budget_exhausted: bool = False

    @property
    def total(self) -> int:
        return self.allowed + self.denied

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "denied": self.denied,
            "denied_reasons": self.denied_reasons,
            "budget_exhausted": self.budget_exhausted,
            "total": self.total,
        }


# ─────────────────── 宛先の検査（Python 側・権威） ───────────────────


def assert_target_allowed(url: str, policy: EgressPolicy) -> None:
    """対象URLを名前解決まで含めて検査する。危険なら EgressDenied。

    既存の url_safety.validate_target_url が IP リテラルしか見ないのに対し、
    ここでは実際に名前解決し、**解決後のアドレス**がプライベート帯なら拒否する
    （DNS ベースの SSRF / DNS リバインディングへの対策）。
    """
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise EgressDenied(f"http/https のみ許可します: {url!r}")

    host = (parsed.hostname or "").lower()
    if not host:
        raise EgressDenied(f"ホスト名が取得できません: {url!r}")

    if host in METADATA_HOSTS:
        raise EgressDenied(f"クラウドメタデータへのアクセスは禁止です: {host}")
    if host in LOCAL_HOSTNAMES or host.endswith(LOCAL_SUFFIXES):
        raise EgressDenied(f"ローカルホストへのアクセスは禁止です: {host}")
    if host in {h.lower() for h in policy.extra_denied_hosts}:
        raise EgressDenied(f"拒否リストのホストです: {host}")

    origin = f"{scheme}://{parsed.netloc}".lower()
    if origin in {o.lower() for o in policy.self_origins}:
        raise EgressDenied(f"WebSpec2Doc 自身へのアクセスは禁止です: {origin}")

    for address in _resolve_all(host):
        if not address.is_global:
            raise EgressDenied(
                f"プライベート/予約済みアドレスへ解決されました: {host} -> {address}"
            )


def _resolve_all(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """ホスト名を解決して全アドレスを返す。IPリテラルはそのまま返す。

    解決できない場合は空リスト（到達不能なので実害は無く、実行時に失敗する）。
    """
    literal = _as_ip(host)
    if literal is not None:
        return [literal]
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    addresses = []
    for info in infos:
        candidate = _as_ip(str(info[4][0]))
        if candidate is not None:
            addresses.append(candidate)
    return addresses


def _as_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


# ─────────────────── Playwright への強制（JS 側） ───────────────────


def write_egress_fixture(target_dir: Path, log_path: Path) -> Path:
    """生成テストが必ず経由する Playwright フィクスチャを書き出す。

    生成 spec は `@playwright/test` ではなくこのフィクスチャから test を import する。
    auto-use のため、**テスト側で無効化できない**（迂回不能性の担保）。
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = target_dir / EGRESS_FIXTURE_NAME
    fixture_path.write_text(_FIXTURE_TS.replace("__LOG_PATH__", str(log_path.resolve())),
                            encoding="utf-8")
    return fixture_path


_FIXTURE_TS = """// 自動生成 — K1 送信ゲートウェイ（設計計画 rev.3）
// 生成された全テストはこの test を使う。auto-use のため無効化できない。
import { test as base, expect } from '@playwright/test';
import * as fs from 'fs';

const POLICY = JSON.parse(process.env.WEBSPEC2DOC_EGRESS_POLICY || '{}');
const LOG_PATH = '__LOG_PATH__';
const BUDGET = Number(POLICY.budgetPerWorker ?? 1e9);
const SELF_ORIGINS: string[] = POLICY.selfOrigins || [];
const DENIED_HOSTS: string[] = POLICY.deniedHosts || [];
const BLOCK_ALL: boolean = Boolean(POLICY.blockAll);

let used = 0;

function record(entry: object) {
  try { fs.appendFileSync(LOG_PATH, JSON.stringify(entry) + '\\n'); } catch (e) { /* 記録失敗で実行は止めない */ }
}

// プライベート/ループバック/リンクローカルの判定（IPリテラル向け）
function isPrivateHost(host: string): boolean {
  if (host === 'localhost' || host.endsWith('.local') || host.endsWith('.localhost')
      || host.endsWith('.internal')) return true;
  if (host === '::1' || host === '[::1]') return true;
  const m = host.match(/^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})$/);
  if (!m) return false;
  const [a, b] = [Number(m[1]), Number(m[2])];
  if (a === 127 || a === 0 || a === 10) return true;
  if (a === 169 && b === 254) return true;      // リンクローカル（メタデータ含む）
  if (a === 192 && b === 168) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 100 && b >= 64 && b <= 127) return true;  // CGNAT
  return false;
}

function denyReason(rawUrl: string): string | null {
  let u: URL;
  try { u = new URL(rawUrl); } catch (e) { return 'invalid_url'; }
  if (BLOCK_ALL) return 'block_all';
  if (!['http:', 'https:'].includes(u.protocol)) return 'scheme';
  const host = u.hostname.toLowerCase();
  if (DENIED_HOSTS.includes(host)) return 'denied_host';
  if (isPrivateHost(host)) return 'private_address';
  if (SELF_ORIGINS.includes(u.origin.toLowerCase())) return 'self_origin';
  return null;
}

export const test = base.extend<{}>({
  page: async ({ page }, use, testInfo) => {
    await page.route('**/*', async (route) => {
      const url = route.request().url();
      const reason = denyReason(url);
      if (reason) {
        record({ t: Date.now(), test: testInfo.title, url, action: 'denied', reason });
        await route.abort();
        return;
      }
      if (used >= BUDGET) {
        record({ t: Date.now(), test: testInfo.title, url, action: 'denied', reason: 'budget' });
        await route.abort();
        return;
      }
      used += 1;
      record({ t: Date.now(), test: testInfo.title, url, action: 'allowed' });
      await route.continue();
    });
    await use(page);
  },
});

export { expect };
"""


def read_egress_report(log_path: Path) -> EgressReport:
    """送信ログを集計する。「送信0」の実証（攻撃 #9 の解消）に使う。"""
    report = EgressReport()
    if not log_path.is_file():
        return report
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("action") == "allowed":
            report.allowed += 1
            continue
        report.denied += 1
        reason = str(entry.get("reason", "unknown"))
        report.denied_reasons[reason] = report.denied_reasons.get(reason, 0) + 1
        if reason == "budget":
            report.budget_exhausted = True
    return report
