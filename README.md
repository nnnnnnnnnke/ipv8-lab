<p align="center">
  <img src="assets/logo.png" alt="IPv8 Lab" width="240">
</p>

<p align="center">
  A hands-on playground for <a href="https://www.ietf.org/archive/id/draft-thain-ipv8-00.html"><code>draft-thain-ipv8-00</code></a><br>
  <sub>packet library · 2-tier router sim · Cisco-style CLI · IPv4 compat via XLATE8</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue"> <img src="https://img.shields.io/badge/license-MIT-informational">
</p>

---

## What is IPv8?

**IPv8** (version number `8` in the IP header) is a proposed successor to IPv4 described in the Internet Draft [`draft-thain-ipv8-00`](https://www.ietf.org/archive/id/draft-thain-ipv8-00.html). Its defining property is a **64-bit address** split into two 32-bit halves:

```
 r . r . r . r . n . n . n . n
 └─────┬─────┘   └─────┬─────┘
     ASN prefix       Host address
    (32 bits)         (32 bits, IPv4-shaped)
```

The routing prefix `r.r.r.r` is the AS number encoded directly in network byte order. The host portion `n.n.n.n` keeps IPv4 semantics, so existing IPv4 routing tables still apply inside an AS. Example: `ASN 64496` encodes as `0.0.251.240`.

Key specs from the draft:

| item            | value                                  |
|-----------------|----------------------------------------|
| IP version      | `8`                                    |
| Address size    | 64 bits                                |
| Header size     | 40 bytes                               |
| IPv4 compat     | yes (`r.r.r.r == 0` → IPv4-only)       |
| Broadcast       | `255.255.255.255.255.255.255.255`      |
| Multicast       | `255.255.xx.xx.xx.xx.xx.xx`            |
| Internal zone   | `127.x.x.x.*`                          |
| DMZ             | `127.127.0.0.*`                        |
| RINE peering    | `100.x.x.x.*`                          |
| Documentation   | `0.0.255.253.*` (ASN 65533)            |

Routing is two-tier: **Tier 1** is an exact lookup on `r.r.r.r`, **Tier 2** is a standard longest-prefix match on `n.n.n.n`. Addresses with `r.r.r.r == 0.0.0.0` bypass Tier 1 entirely — that's how IPv4 co-exists.

The draft also defines companion protocols (OSPF8, BGP8, IS-IS8, DHCP8, ICMPv8, ARP8, DNS8 `A8` records, XLATE8, NetLog8, etc.). This lab implements the on-the-wire data-plane pieces (IPv8, ICMPv8, XLATE8, two-tier routing) and ships a Cisco-style CLI for configuring them.

---

## Do I need an AS number?

**Short answer**: on paper yes — but `ASN = 0` gives you an escape hatch for pure-IPv4 setups.

An IPv8 address is 64 bits: `r.r.r.r` (32-bit **ASN**) + `n.n.n.n` (32-bit host). The ASN half is the Tier-1 routing key, and that's exactly where IPv8 earns its keep over IPv4 — global tables can aggregate at the AS boundary instead of listing every prefix. No ASN ⇒ no Tier-1 key ⇒ you give up that property.

Three practical options:

| option                           | ASN field                     | when to use                                                    |
|----------------------------------|-------------------------------|----------------------------------------------------------------|
| **Public ASN**                   | IANA-assigned (`0.0.251.240` for AS 64496, etc.) | production                                                      |
| **Private ASN**                  | `65001`–`65534`, or `4.2B`–`4.3B` | internal deployments and labs — this repo uses `65001`–`65005` |
| **`ASN = 0`** (IPv4-compat)      | `0.0.0.0`                     | when you have no ASN, or for raw IPv4 interop                  |

### How `ASN = 0` behaves

- Tier 1 lookup is skipped entirely.
- Routing reduces to standard IPv4 longest-prefix match.
- In the IOS shell: `ipv8 address 0.0.0.0.192.168.1.1` turns an interface into plain IPv4.
- This is the path used by the XLATE8 translator.

### ASN values this lab uses

```
65001  → 0.0.253.233   R1
65002  → 0.0.253.234   R2
65003  → 0.0.253.235   R3
65004  → 0.0.253.236   R4
65005  → 0.0.253.237   R5
65533  → 0.0.255.253   documentation ASN (reserved by the draft)
65534  → 0.0.255.254   private-BGP ASN (reserved by the draft)
0      → 0.0.0.0       IPv4-compat
```

> **Bottom line** — `ASN = 0` keeps IPv8 usable for organisations without their own AS. But to get IPv8's actual benefit (AS-aggregated routing) you need *some* ASN, even a private one.

---

## What this repo gives you

- **`ipv8/`** — pure-Python reference implementation (no third-party deps)
  - `address.py` — 64-bit address, parse/format, reserved-range classification
  - `packet.py`  — 40-byte header encode/decode, one's-complement checksum over the full header
  - `routing.py` — two-tier routing table with longest-prefix match at Tier 2
  - `icmp.py`    — ICMPv8 echo request/reply
  - `xlate.py`   — XLATE8 translator (IPv4 ⇄ IPv8) preserving ToS / flags / frag-offset / identification so round-trips are byte-exact
  - `simulator.py` — userspace multi-AS simulator (Hosts, Routers, Links, Network) with a full tcpdump-style trace
  - `ios.py`     — Cisco-IOS-flavoured CLI (user / priv / config / config-if modes)
  - `socket_api.py` — `sockaddr_in8` struct
  - `constants.py` — `IP_VERSION = 8`, well-known multicast groups, ASN reservations
- **`demos/`** — runnable demo scripts
- **`ios_shell.py`** — interactive Cisco-style shell on top of a pre-built 5-router topology
- **`cli.py`** — light interactive shell (non-Cisco style, good for quick experiments)

### Features at a glance

- 64-bit address roundtrip, classification, boundary checks
- 40-byte IPv8 header with checksum that covers the full header including reserved bytes
- Two-tier routing (Tier 1 ASN, Tier 2 longest-prefix)
- ICMPv8 echo, TTL decrement, no-route / ttl-exceeded drop handling
- Cisco IOS-flavoured CLI: `enable`, `configure terminal`, `interface`, `ipv8 address`, `ipv8 route`, `no ipv8 route`, `show running-config`, `show ipv8 interface`, `show ipv8 route`, `ping8`, `hostname`, `no shutdown` / `shutdown`, `description`, `end`, `exit`, `write memory`
- Topologies ready to explore: linear 5-router chain, 4-router ring, full 4-mesh, hub-and-spoke
- IPv4 compatibility via `ASN = 0` + `XLATE8` translator

---

## Quick start

### Requirements
- Python 3.9+ (no third-party packages)
- macOS or Linux

### 30-second tour
```sh
git clone https://github.com/nnnnnnnnnke/ipv8-lab.git
cd ipv8-lab
python3 demos/01_encode_packet.py
python3 ios_shell.py              # interactive Cisco-style shell
```

### Demos
```sh
python3 demos/01_encode_packet.py     # build & hex-dump a single IPv8 packet
python3 demos/02_two_as_ping.py       # 2-AS ping with full tcpdump-style trace
python3 demos/03_xlate_demo.py        # IPv4 → IPv8 → IPv4 round-trip
python3 demos/04_address_zoo.py       # classify every reserved address family
python3 demos/05_five_routers_cli.py  # 5 routers configured via Cisco CLI, host-to-host ping8
```

---

## Configuring a router in Cisco style

Every router is an `ipv8.Router` driven by an `ipv8.IOSCLI` instance. The CLI supports the familiar EXEC / configuration hierarchy:

```
R1> enable
R1# configure terminal
R1(config)# hostname R1
R1(config)# interface Gig0/0
R1(config-if)# ipv8 address 0.0.253.233.10.1.1.1
R1(config-if)# no shutdown
R1(config-if)# exit
R1(config)# interface Gig0/1
R1(config-if)# ipv8 address 0.0.253.233.10.12.0.1
R1(config-if)# no shutdown
R1(config-if)# exit
R1(config)# ipv8 route 0.0.253.233.10.1.1.0/24 interface Gig0/0
R1(config)# ipv8 route 0.0.253.237.0.0.0.0/0 0.0.253.233.10.12.0.2
R1(config)# end
R1# show ipv8 route
Codes: C - connected, S - static
Two-tier IPv8 routing table (draft-thain-ipv8-00)
  C  ASN 65001 10.1.1.1/32 direct  dev Gig0/0
  C  ASN 65001 10.12.0.1/32 direct  dev Gig0/0
  S  ASN 65005 0.0.0.0/0 via 0.0.253.233.10.12.0.2 dev Gig0/1
R1# ping8 0.0.253.237.10.5.1.1
Type escape sequence to abort.
Sending 5, 0-byte IPv8 Echos to 0.0.253.237.10.5.1.1, timeout is 2 seconds:
!!!!!
Success rate is 100 percent (5/5)
```

### Command reference

| mode              | command                                              | purpose                                    |
|-------------------|------------------------------------------------------|--------------------------------------------|
| user EXEC         | `enable`                                             | enter priv EXEC                            |
| user / priv       | `ping8 <addr>`                                       | send 5 ICMPv8 echoes                       |
| user / priv       | `show ipv8 interface [brief]`                        | list interfaces + state                    |
| user / priv       | `show ipv8 route`                                    | print the two-tier routing table           |
| priv              | `show running-config`                                | dump CLI-reconstructible config            |
| priv              | `configure terminal`                                 | enter global config                        |
| global config     | `hostname NAME`                                      | rename device                              |
| global config     | `interface NAME`                                     | enter interface config                     |
| global config     | `ipv8 route PFX/LEN NEXT_HOP`                        | static route via next-hop                  |
| global config     | `ipv8 route PFX/LEN interface IFACE`                 | directly-connected static route            |
| global config     | `no ipv8 route PFX/LEN`                              | remove a route                             |
| global config     | `end` / `exit`                                       | return to priv EXEC                        |
| interface config  | `ipv8 address ADDR`                                  | assign IPv8 address                        |
| interface config  | `no shutdown` / `shutdown`                           | enable / disable interface                 |
| interface config  | `description TEXT`                                   | free-form label                            |
| interface config  | `exit`                                               | leave interface config                     |

---

## Interactive IOS shell

`ios_shell.py` is a Cisco-IOS-flavoured REPL attached to a **pre-built 5-router topology**, so you can experiment without writing any Python.

### Starting it

```sh
python3 ios_shell.py          # start on R1
python3 ios_shell.py R3       # start already attached to R3
```

Or drop these aliases into your `~/.zshrc` / `~/.bashrc` for one-word access:

```sh
export IPV8_LAB_HOME="$HOME/ipv8-lab"
alias ipv8lab='python3 "$IPV8_LAB_HOME/ios_shell.py"'
alias ipv8lab-demo='python3 "$IPV8_LAB_HOME/demos/05_five_routers_cli.py"'
```

### Pre-built topology

```
hostA ─ linkA ─ R1 ─ link12 ─ R2 ─ link23 ─ R3 ─ link34 ─ R4 ─ link45 ─ R5 ─ linkB ─ hostB
10.1.1.10      (AS 65001)   (AS 65002)   (AS 65003)   (AS 65004)   (AS 65005)    10.5.1.20
              0.0.253.233  0.0.253.234  0.0.253.235  0.0.253.236  0.0.253.237
```

- **Hosts**: `hostA` (`0.0.253.233.10.1.1.10`), `hostB` (`0.0.253.237.10.5.1.20`)
- **Routers**: R1…R5, each with two `GigabitEthernet` interfaces (`Gig0/0` upstream, `Gig0/1` downstream)
- **Routing**: every router ships with four static routes — one per remote ASN — and connected routes for its own /24s

### Meta commands (shell-only, not real IOS)

| command                                    | effect                                                      |
|--------------------------------------------|-------------------------------------------------------------|
| `attach R1` … `attach R5`                  | switch console to another router                            |
| `routers`                                  | list routers + interface addresses                          |
| `hosts`                                    | list hostA / hostB addresses                                |
| `show trace`                               | tcpdump-style log of every packet sent in the sim so far    |
| `clear trace`                              | reset the trace buffer                                      |
| `ping from hostA to <ADDR>`                | ping from a *host*, not a router                            |
| `ping from hostA to <ADDR> <id> <seq>`     | same with explicit ICMP id / sequence                       |
| `quit` / `:q`                              | leave the shell (works from any IOS mode)                   |

Everything else is forwarded to the Cisco CLI documented above.

### Mode transitions (standard IOS)

```
user EXEC  ─ enable            →  priv EXEC
priv EXEC  ─ configure terminal→  global config
config     ─ interface Gig0/0  →  interface config
config-if  ─ exit              →  global config
config     ─ end               →  priv EXEC
priv EXEC  ─ disable           →  user EXEC
```

### Quick tour — copy-paste session

```
routers
hosts
enable
show ipv8 route
ping8 0.0.253.237.10.5.1.1                ! router-to-router, 5 hops
clear trace
ping from hostA to 0.0.253.237.10.5.1.20  ! edge-to-edge ping
show trace                                 ! TTL 64→59 round-trip visible

attach R3
enable
configure terminal
interface Gig0/0
 description link-toward-R2
 exit
ipv8 route 0.0.253.240.0.0.0.0/0 0.0.253.235.10.23.0.1
end
show running-config
no ipv8 route 0.0.253.240.0.0.0.0/0
end

attach R5
enable
configure terminal
hostname EdgeRouter5                      ! prompt updates immediately
end
ping from hostB to 0.0.253.233.10.1.1.10  ! reverse end-to-end
quit
```

### Break-and-recover pattern

```
attach R3
enable
configure terminal
interface Gig0/1
 shutdown                                  ! rip the R3—R4 link
 end
clear trace
ping from hostA to 0.0.253.237.10.5.1.20  ! dropped with "no-route"
configure terminal
interface Gig0/1
 no shutdown
 end
ping from hostA to 0.0.253.237.10.5.1.20  ! reachable again
```

### Adding IPv4-compat (ASN=0) routing

```
attach R1
enable
configure terminal
interface Gig0/0
 ipv8 address 0.0.0.0.192.168.1.1          ! re-address under ASN=0
 exit
ipv8 route 0.0.0.0.0.0.0.0/0 interface Gig0/0
end
show ipv8 route                             ! an ASN-0 bucket now appears
```

> When in doubt, `routers`, `hosts`, and `show trace` together always tell you where you are and what's happening.

---

## Architecture at a glance

```
            ┌────────────────── cli.py ───────────────────┐
            │                                             │
            ▼                                             │
        IOSCLI (ios.py)                                   │
            │                                             │
        ┌───┴───┐                                         │
        ▼       ▼                                         │
      Host   Router ─────── rtable ─── TwoTierRoutingTable (routing.py)
        │       │                                         │
        └───┬───┘                                         │
            ▼                                             │
       Network / Link (simulator.py)                      │
            │                                             │
            ▼                                             │
        IPv8Packet (packet.py)   ── checksum16 ──         │
            │            ▲                                │
            │            │                                │
        IPv8Address (address.py)                          │
            │                                             │
            ▼                                             │
        ICMPv8 (icmp.py) · XLATE8 (xlate.py)
```

---

## License

MIT — see [LICENSE](LICENSE).

---
---

<p align="center">
  <img src="assets/logo.png" alt="IPv8 Lab" width="200">
</p>

<h1 align="center">日本語版</h1>

## IPv8 とは

**IPv8** は、IETF インターネットドラフト [`draft-thain-ipv8-00`](https://www.ietf.org/archive/id/draft-thain-ipv8-00.html) で提案されている IPv4 の後継プロトコルです。IP ヘッダのバージョン番号は `8` で、最大の特徴は **64-bit アドレス** を 32-bit ずつの 2 つに分けた構造にあります。

```
 r . r . r . r . n . n . n . n
 └─────┬─────┘   └─────┬─────┘
    ASN プレフィックス  ホスト部
      (32 bit)        (32 bit、IPv4 と同形)
```

`r.r.r.r` は AS 番号をネットワークバイトオーダーでそのまま符号化したもの、`n.n.n.n` は従来の IPv4 のセマンティクスをそのまま残しています。例えば `ASN 64496` は `0.0.251.240` と符号化されます。

ドラフトが定める主要な値：

| 項目              | 値                                    |
|-------------------|---------------------------------------|
| バージョン        | `8`                                   |
| アドレス長        | 64 bit                                |
| ヘッダ長          | 40 byte                               |
| IPv4 互換         | あり（`r.r.r.r == 0` → 純 IPv4）      |
| ブロードキャスト  | `255.255.255.255.255.255.255.255`     |
| マルチキャスト    | `255.255.xx.xx.xx.xx.xx.xx`           |
| 内部ゾーン        | `127.x.x.x.*`                         |
| DMZ               | `127.127.0.0.*`                       |
| RINE ピアリング   | `100.x.x.x.*`                         |
| ドキュメント用    | `0.0.255.253.*`（ASN 65533）          |

ルーティングは **二階層構造** で、Tier 1 は `r.r.r.r` による厳密一致、Tier 2 は `n.n.n.n` に対する最長一致です。`r.r.r.r == 0.0.0.0` のときは Tier 1 をスキップし、既存の IPv4 ルーティング表がそのまま適用されるため、IPv4 と共存できます。

ドラフトには OSPF8、BGP8、IS-IS8、DHCP8、ICMPv8、ARP8、DNS8（`A8` レコード）、XLATE8、NetLog8 などの補助プロトコルも含まれます。本リポジトリは **データプレーン部分（IPv8 / ICMPv8 / XLATE8 / 二階層ルーティング）を実装**し、Cisco 風 CLI で設定できる形にしています。

---

## AS 番号は必要？

**結論**: 仕様上は必要。ただし `ASN = 0` が用意されており、純 IPv4 用途では逃げられます。

IPv8 アドレス 64 bit は `r.r.r.r`（32 bit **ASN**）+ `n.n.n.n`（32 bit ホスト）で構成されます。ASN 部は **Tier 1 ルーティングの鍵** であり、IPv8 が IPv4 に対して持つ最大の優位（AS 境界でルート集約できる）のための情報そのものです。ASN を与えない＝ Tier 1 鍵を持たない＝ IPv8 のメリットを捨てる、ということになります。

3 つの実用的な選択肢：

| 方式                              | ASN 値                                | 使いどころ                                                   |
|-----------------------------------|---------------------------------------|--------------------------------------------------------------|
| **公式 ASN**                      | IANA 割当（例: AS 64496 → `0.0.251.240`） | 本番運用                                                      |
| **プライベート ASN**              | `65001`〜`65534` / `4.2B`〜`4.3B`     | 社内・検証・本ラボ（`65001`〜`65005` を使用）                |
| **`ASN = 0`**（IPv4-compat）      | `0.0.0.0`                             | AS を持たない／持ちたくないケース、純 IPv4 との混在           |

### `ASN = 0` の動作

- Tier 1 ルックアップをスキップ
- ルーティングは IPv4 と同等（最長一致のみ）
- IOS シェルで `ipv8 address 0.0.0.0.192.168.1.1` とすれば IPv4-only インターフェースに
- XLATE8 が利用する経路

### 本ラボで使っている ASN 値

```
65001  → 0.0.253.233   R1
65002  → 0.0.253.234   R2
65003  → 0.0.253.235   R3
65004  → 0.0.253.236   R4
65005  → 0.0.253.237   R5
65533  → 0.0.255.253   ドキュメント用 ASN（draft の予約）
65534  → 0.0.255.254   プライベート BGP 用 ASN（draft の予約）
0      → 0.0.0.0       IPv4-compat
```

> **要点** — `ASN = 0` のおかげで「AS を持たない組織が IPv8 を使えない」という事態は避けられます。ただし IPv8 本来の恩恵（AS 単位の集約ルーティング）を得るには何らかの ASN（プライベートでも可）が必要です。

---

## 本リポジトリで出来ること

- **`ipv8/`** — 依存ゼロの純 Python 実装
  - `address.py` — 64-bit アドレスの生成・パース・分類
  - `packet.py`  — 40 byte ヘッダの encode/decode、全ヘッダを対象とするチェックサム
  - `routing.py` — 二階層ルーティング表（Tier 2 は最長一致）
  - `icmp.py`    — ICMPv8 echo request/reply
  - `xlate.py`   — XLATE8 変換（IPv4 ⇄ IPv8）、ToS / flags / フラグメントオフセット / 識別子を保持しバイト単位で往復一致
  - `simulator.py` — Host / Router / Link / Network を備えたユーザランド複数 AS シミュレータ、tcpdump 風トレース付き
  - `ios.py`     — Cisco IOS 風 CLI（user / priv / config / config-if モード）
  - `socket_api.py` — `sockaddr_in8` 相当の構造体
  - `constants.py` — `IP_VERSION = 8`、既知マルチキャスト、予約 ASN
- **`demos/`** — すぐ実行できるデモ
- **`ios_shell.py`** — 事前構築済み 5 台構成に接続する Cisco 風対話シェル
- **`cli.py`** — 簡易対話シェル

### 機能の概要

- 64-bit アドレスの往復・分類・境界チェック
- 40 byte ヘッダのチェックサムは予約領域も含む全 40 byte をカバー
- 二階層ルーティング（Tier 1 ASN、Tier 2 最長一致）
- ICMPv8 echo、TTL 減算、`no-route` / `ttl-exceeded` のドロップ処理
- Cisco IOS 風 CLI：`enable` / `configure terminal` / `interface` / `ipv8 address` / `ipv8 route` / `no ipv8 route` / `show running-config` / `show ipv8 interface` / `show ipv8 route` / `ping8` / `hostname` / `no shutdown` / `shutdown` / `description` / `end` / `exit` / `write memory`
- 用意済みトポロジ：直列 5 台、リング 4 台、フルメッシュ 4 台、ハブ＆スポーク
- IPv4 下位互換：`ASN = 0` + `XLATE8` 変換

---

## クイックスタート

### 必要環境
- Python 3.9 以上（サードパーティ依存なし）
- macOS / Linux

### 30 秒で触ってみる
```sh
git clone https://github.com/nnnnnnnnnke/ipv8-lab.git
cd ipv8-lab
python3 demos/01_encode_packet.py
python3 ios_shell.py              # Cisco 風対話シェル起動
```

### デモ
```sh
python3 demos/01_encode_packet.py     # 単一 IPv8 パケットの生成と hex ダンプ
python3 demos/02_two_as_ping.py       # 2 AS 跨ぎ ping と tcpdump 風トレース
python3 demos/03_xlate_demo.py        # IPv4 → IPv8 → IPv4 の往復
python3 demos/04_address_zoo.py       # 予約アドレス全種の分類
python3 demos/05_five_routers_cli.py  # 5 台を Cisco CLI で設定、host 間 ping8
```

---

## Cisco 風 CLI でルータを設定する

各ルータは `ipv8.Router` と `ipv8.IOSCLI` をペアで使います。IOS と同じ EXEC / config 階層が利用できます。

```
R1> enable
R1# configure terminal
R1(config)# hostname R1
R1(config)# interface Gig0/0
R1(config-if)# ipv8 address 0.0.253.233.10.1.1.1
R1(config-if)# no shutdown
R1(config-if)# exit
R1(config)# interface Gig0/1
R1(config-if)# ipv8 address 0.0.253.233.10.12.0.1
R1(config-if)# no shutdown
R1(config-if)# exit
R1(config)# ipv8 route 0.0.253.233.10.1.1.0/24 interface Gig0/0
R1(config)# ipv8 route 0.0.253.237.0.0.0.0/0 0.0.253.233.10.12.0.2
R1(config)# end
R1# show ipv8 route
Codes: C - connected, S - static
Two-tier IPv8 routing table (draft-thain-ipv8-00)
  C  ASN 65001 10.1.1.1/32 direct  dev Gig0/0
  C  ASN 65001 10.12.0.1/32 direct  dev Gig0/0
  S  ASN 65005 0.0.0.0/0 via 0.0.253.233.10.12.0.2 dev Gig0/1
R1# ping8 0.0.253.237.10.5.1.1
Type escape sequence to abort.
Sending 5, 0-byte IPv8 Echos to 0.0.253.237.10.5.1.1, timeout is 2 seconds:
!!!!!
Success rate is 100 percent (5/5)
```

### コマンドリファレンス

| モード            | コマンド                                             | 用途                                     |
|-------------------|------------------------------------------------------|------------------------------------------|
| user EXEC         | `enable`                                             | priv EXEC へ移行                         |
| user / priv       | `ping8 <addr>`                                       | ICMPv8 echo を 5 回送出                  |
| user / priv       | `show ipv8 interface [brief]`                        | インターフェース一覧                     |
| user / priv       | `show ipv8 route`                                    | 二階層ルーティング表を表示               |
| priv              | `show running-config`                                | 現在の設定を CLI 形式で出力              |
| priv              | `configure terminal`                                 | グローバル config へ                     |
| global config     | `hostname NAME`                                      | ホスト名変更                             |
| global config     | `interface NAME`                                     | インターフェース config へ               |
| global config     | `ipv8 route PFX/LEN NEXT_HOP`                        | ネクストホップ経由の static route        |
| global config     | `ipv8 route PFX/LEN interface IFACE`                 | 直接接続の static route                  |
| global config     | `no ipv8 route PFX/LEN`                              | ルート削除                               |
| global config     | `end` / `exit`                                       | priv EXEC へ戻る                         |
| interface config  | `ipv8 address ADDR`                                  | IPv8 アドレス設定                        |
| interface config  | `no shutdown` / `shutdown`                           | インターフェース有効/無効                |
| interface config  | `description TEXT`                                   | 任意ラベル                               |
| interface config  | `exit`                                               | interface config を抜ける                |

---

## 対話型 IOS シェル

`ios_shell.py` は Cisco IOS 風の対話シェルで、**5 台構成のトポロジが起動時点で既に組み上がっている** ため Python を書かずにそのまま実験できます。

### 起動

```sh
python3 ios_shell.py          # R1 に接続して起動
python3 ios_shell.py R3       # 起動時から R3 に attach
```

`~/.zshrc` / `~/.bashrc` に以下のエイリアスを入れると一語で叩けます：

```sh
export IPV8_LAB_HOME="$HOME/ipv8-lab"
alias ipv8lab='python3 "$IPV8_LAB_HOME/ios_shell.py"'
alias ipv8lab-demo='python3 "$IPV8_LAB_HOME/demos/05_five_routers_cli.py"'
```

### プリビルト構成

```
hostA ─ linkA ─ R1 ─ link12 ─ R2 ─ link23 ─ R3 ─ link34 ─ R4 ─ link45 ─ R5 ─ linkB ─ hostB
10.1.1.10      (AS 65001)   (AS 65002)   (AS 65003)   (AS 65004)   (AS 65005)    10.5.1.20
              0.0.253.233  0.0.253.234  0.0.253.235  0.0.253.236  0.0.253.237
```

- **ホスト**: `hostA` (`0.0.253.233.10.1.1.10`)、`hostB` (`0.0.253.237.10.5.1.20`)
- **ルータ**: R1〜R5、各 `GigabitEthernet` 2 口（`Gig0/0` 上流、`Gig0/1` 下流）
- **経路**: 各ルータに他 4 AS 向けの static route と自 /24 の接続経路が事前設定済

### 対話版限定コマンド（IOS には無い）

| コマンド                                    | 動作                                                  |
|---------------------------------------------|-------------------------------------------------------|
| `attach R1` 〜 `attach R5`                  | コンソールを他ルータへ切替                            |
| `routers`                                   | 全ルータとインターフェースアドレスを一覧              |
| `hosts`                                     | hostA / hostB のアドレス表示                          |
| `show trace`                                | これまでの全パケットを tcpdump 風に表示                |
| `clear trace`                               | トレースをクリア                                      |
| `ping from hostA to <ADDR>`                 | **ルータでなくホスト発** の ping                      |
| `ping from hostA to <ADDR> <id> <seq>`      | 識別子・シーケンス番号も指定                          |
| `quit` / `:q`                               | シェル終了（どのモードでも）                          |

その他は全て Cisco CLI へ素通し（上の Command Reference を参照）。

### モード遷移（本家 IOS と同じ）

```
user EXEC  ─ enable            →  priv EXEC
priv EXEC  ─ configure terminal→  global config
config     ─ interface Gig0/0  →  interface config
config-if  ─ exit              →  global config
config     ─ end               →  priv EXEC
priv EXEC  ─ disable           →  user EXEC
```

### コピペで試せるセッション

```
routers
hosts
enable
show ipv8 route
ping8 0.0.253.237.10.5.1.1                ! ルータ間 ping、5 ホップ
clear trace
ping from hostA to 0.0.253.237.10.5.1.20  ! エッジ→エッジ ping
show trace                                 ! TTL 64→59 の往復が見える

attach R3
enable
configure terminal
interface Gig0/0
 description link-toward-R2
 exit
ipv8 route 0.0.253.240.0.0.0.0/0 0.0.253.235.10.23.0.1
end
show running-config
no ipv8 route 0.0.253.240.0.0.0.0/0
end

attach R5
enable
configure terminal
hostname EdgeRouter5                      ! プロンプトが即座に反映
end
ping from hostB to 0.0.253.233.10.1.1.10  ! 逆方向の end-to-end
quit
```

### 壊して直すパターン

```
attach R3
enable
configure terminal
interface Gig0/1
 shutdown                                  ! R3—R4 間リンクを落とす
 end
clear trace
ping from hostA to 0.0.253.237.10.5.1.20  ! "no-route" で落ちる
configure terminal
interface Gig0/1
 no shutdown
 end
ping from hostA to 0.0.253.237.10.5.1.20  ! 復旧
```

### IPv4 下位互換（ASN=0）経路を追加

```
attach R1
enable
configure terminal
interface Gig0/0
 ipv8 address 0.0.0.0.192.168.1.1          ! ASN=0 に付け替え
 exit
ipv8 route 0.0.0.0.0.0.0.0/0 interface Gig0/0
end
show ipv8 route                             ! ASN 0 のバケットが現れる
```

> 迷ったら `routers` / `hosts` / `show trace` の 3 つで現状を確認できます。

---

## アーキテクチャ俯瞰

```
            ┌────────────────── cli.py ───────────────────┐
            │                                             │
            ▼                                             │
        IOSCLI (ios.py)                                   │
            │                                             │
        ┌───┴───┐                                         │
        ▼       ▼                                         │
      Host   Router ─────── rtable ─── TwoTierRoutingTable (routing.py)
        │       │                                         │
        └───┬───┘                                         │
            ▼                                             │
       Network / Link (simulator.py)                      │
            │                                             │
            ▼                                             │
        IPv8Packet (packet.py)   ── checksum16 ──         │
            │            ▲                                │
            │            │                                │
        IPv8Address (address.py)                          │
            │                                             │
            ▼                                             │
        ICMPv8 (icmp.py) · XLATE8 (xlate.py)
```

---

## ライセンス

MIT — [LICENSE](LICENSE) を参照。
