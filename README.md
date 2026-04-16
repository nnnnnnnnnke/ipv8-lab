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

<p align="center">
  <b><a href="#english">🇬🇧 English</a></b> · <b><a href="#日本語版">🇯🇵 日本語</a></b>
</p>

---

<a id="english"></a>

## Table of contents

- [What is IPv8?](#what-is-ipv8)
- [Do I need an AS number?](#do-i-need-an-as-number)
- [What this repo gives you](#what-this-repo-gives-you)
- [Quick start](#quick-start)
- [Configuring a router in Cisco style](#configuring-a-router-in-cisco-style)
- [Interactive IOS shell](#interactive-ios-shell)
- [Architecture at a glance](#architecture-at-a-glance)
- [License](#license)
- [日本語版 ↓](#日本語版)

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
| user / priv       | `ping8 <ADDR>` / `ping <X.X.X.X>`                    | send 5 ICMP(v8) echoes                     |
| user / priv       | `show ipv8 interface [brief]`                        | list IPv8 interfaces + state               |
| user / priv       | `show ipv8 route`                                    | print the two-tier routing table           |
| user / priv       | `show ip interface [brief]`                          | list *IPv4-compat* interfaces (ASN=0)      |
| user / priv       | `show ip route`                                      | IPv4-only view of the routing table        |
| priv              | `show running-config`                                | dump CLI-reconstructible config            |
| priv              | `configure terminal`                                 | enter global config                        |
| global config     | `hostname NAME`                                      | rename device                              |
| global config     | `interface NAME`                                     | enter interface config                     |
| global config     | `ipv8 route PFX/LEN NEXT_HOP`                        | IPv8 static route via next-hop             |
| global config     | `ipv8 route PFX/LEN interface IFACE`                 | IPv8 directly-connected static route       |
| global config     | `ip route X.X.X.X/LEN Y.Y.Y.Y`                       | IPv4 static route (stored under ASN=0)     |
| global config     | `ip route X.X.X.X/LEN interface IFACE`               | IPv4 directly-connected route              |
| global config     | `no ipv8 route PFX/LEN`                              | remove a route                             |
| global config     | `end` / `exit`                                       | return to priv EXEC                        |
| interface config  | `ipv8 address R.R.R.R.N.N.N.N`                       | assign a native IPv8 address               |
| interface config  | `ip address X.X.X.X`                                 | assign an IPv4 address (ASN=0 shortcut)    |
| interface config  | `no shutdown` / `shutdown`                           | enable / disable interface                 |
| interface config  | `description TEXT`                                   | free-form label                            |
| interface config  | `exit`                                               | leave interface config                     |

> The `ip …` forms are **exact shortcuts** for `ipv8 … 0.0.0.0.…`.  `ip address 10.0.0.1` and `ipv8 address 0.0.0.0.10.0.0.1` produce byte-identical `Interface` state; `ping 10.0.0.1` and `ping8 0.0.0.0.10.0.0.1` generate byte-identical frames. The library layer has a single code path — the two surfaces are just parser-level aliases.

---

## Interactive IOS shell

`ios_shell.py` drops you into a Cisco-IOS-flavoured REPL over an **empty, router-only network**. You add routers, connect them with links, assign any IPv8 address you like, install static routes, and ping — entirely at the prompt.

### Starting it

```sh
python3 ios_shell.py
```

Or add this alias to your `~/.zshrc` / `~/.bashrc`:

```sh
export IPV8_LAB_HOME="$HOME/ipv8-lab"
alias ipv8lab='python3 "$IPV8_LAB_HOME/ios_shell.py"'
```

### Meta commands (shell-only, not real IOS)

| command                                          | effect                                                                |
|--------------------------------------------------|-----------------------------------------------------------------------|
| `router add <NAME>`                              | create a router (auto-attach)                                         |
| `router remove <NAME>`                           | delete a router and detach its links                                  |
| `link add <LINK> <Ra>:<Ifa> <Rb>:<Ifb>`          | create a link and interfaces on both routers                          |
| `link remove <LINK>`                             | tear down a link and remove the attached interfaces                   |
| `attach <NAME>`                                  | switch console to another router (starts in user EXEC each time)      |
| `routers`                                        | list routers + each interface's address and admin state               |
| `links`                                          | list links + their endpoints                                          |
| `show trace`                                     | tcpdump-style log of every packet in the sim                          |
| `clear trace`                                    | reset the trace buffer                                                |
| `help-meta` / `?`                                | print the meta-command reference                                      |
| `quit` / `:q`                                    | leave the shell                                                       |

Everything else is forwarded to the Cisco CLI (see *Command Reference* above).

### Mode transitions (standard IOS)

```
user EXEC  ─ enable            →  priv EXEC
priv EXEC  ─ configure terminal→  global config
config     ─ interface <IFACE> →  interface config
config-if  ─ exit              →  global config
config     ─ end               →  priv EXEC
priv EXEC  ─ disable           →  user EXEC
```

### Quick tour — build a 3-router chain from scratch

```
router add R1
router add R2
router add R3

link add L12 R1:Gig0/0 R2:Gig0/0
link add L23 R2:Gig0/1 R3:Gig0/0

attach R1
enable
configure terminal
interface Gig0/0
 ipv8 address 0.0.253.233.10.12.0.1        ! R1 side of L12
 no shutdown
 exit
ipv8 route 0.0.253.234.0.0.0.0/0 0.0.253.233.10.12.0.2
ipv8 route 0.0.253.235.0.0.0.0/0 0.0.253.233.10.12.0.2
end

attach R2
enable
configure terminal
interface Gig0/0
 ipv8 address 0.0.253.234.10.12.0.2
 no shutdown
 exit
interface Gig0/1
 ipv8 address 0.0.253.234.10.23.0.1
 no shutdown
 exit
ipv8 route 0.0.253.233.0.0.0.0/0 0.0.253.234.10.12.0.1
ipv8 route 0.0.253.235.0.0.0.0/0 0.0.253.234.10.23.0.2
end

attach R3
enable
configure terminal
interface Gig0/0
 ipv8 address 0.0.253.235.10.23.0.2
 no shutdown
 exit
ipv8 route 0.0.253.233.0.0.0.0/0 0.0.253.235.10.23.0.1
ipv8 route 0.0.253.234.0.0.0.0/0 0.0.253.235.10.23.0.1
end

attach R1
enable
ping8 0.0.253.235.10.23.0.2                ! R1 → R3, 2 hops
show trace
```

**What this confirms**

| block | what you observe |
|---|---|
| *router add / link add* | `routers` and `links` show the new objects and the placeholder `0.0.0.0.0.0.0.0` address assigned on each freshly-created interface |
| *interface config* | `ipv8 address` accepts any 64-bit address you type — use any private ASN (e.g. `0.0.253.233` = 65001) or `0.0.0.0` for IPv4-compat |
| *static routes* | after config you get `!!!!!` 100 % from `ping8` and `show trace` prints the full R1 → R2 → R3 round-trip with per-hop TTL decrement |

### Break-and-recover pattern

```
attach R2
enable
configure terminal
interface Gig0/1
 shutdown
 end
clear trace
ping8 0.0.253.235.10.23.0.2                ! now drops at R2

configure terminal
interface Gig0/1
 no shutdown
 end
ping8 0.0.253.235.10.23.0.2                ! reachable again
```

**What this confirms**

- `shutdown` sets `Interface.admin_down=True` and the simulator's forwarder drops the next packet with `egress-admin-down (Gig0/1)` in the trace
- `no shutdown` restores reachability without touching the routing table — static routes remained installed throughout
- The failure trace stops at the router that owns the dead interface, making blackholes easy to spot

### Adding IPv4-compat (ASN = 0) alongside native IPv8

Re-attach to R1 (still configured from the Quick tour) and graft a second, IPv4-compat interface:

```
router add R4
link add L14 R1:Gig0/1 R4:Gig0/0

attach R1
enable
configure terminal
interface Gig0/1
 ipv8 address 0.0.0.0.192.168.1.1          ! ASN=0 edge
 no shutdown
 exit
ipv8 route 0.0.0.0.0.0.0.0/0 0.0.0.0.192.168.1.2
end
show ipv8 route                             ! ASN 0 bucket alongside ASN 65001
```

**What this confirms**

- A single router can carry **native IPv8 interfaces and `ASN = 0` IPv4-compat interfaces at the same time**
- `show ipv8 route` lists two ASN buckets — `0` and `65001` — demonstrating that Tier 1 lookup works for the real ASN and is bypassed (IPv4 semantics) for `ASN = 0`
- Reconfiguration is live; no reload needed

> When in doubt, `routers`, `links`, and `show trace` together always tell you what's going on.

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

<p align="center">
  <b><a href="#english">🇬🇧 English</a></b> · <b><a href="#日本語版">🇯🇵 日本語</a></b>
</p>

---

## 目次

- [IPv8 とは](#ipv8-とは)
- [AS 番号は必要？](#as-番号は必要)
- [本リポジトリで出来ること](#本リポジトリで出来ること)
- [クイックスタート](#クイックスタート)
- [Cisco 風 CLI でルータを設定する](#cisco-風-cli-でルータを設定する)
- [対話型 IOS シェル](#対話型-ios-シェル)
- [アーキテクチャ俯瞰](#アーキテクチャ俯瞰)
- [ライセンス](#ライセンス)
- [English ↑](#english)

---

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

| モード            | コマンド                                             | 用途                                         |
|-------------------|------------------------------------------------------|----------------------------------------------|
| user EXEC         | `enable`                                             | priv EXEC へ移行                             |
| user / priv       | `ping8 <ADDR>` / `ping <X.X.X.X>`                    | ICMP(v8) echo を 5 回送出                    |
| user / priv       | `show ipv8 interface [brief]`                        | IPv8 インターフェース一覧                    |
| user / priv       | `show ipv8 route`                                    | 二階層ルーティング表を表示                   |
| user / priv       | `show ip interface [brief]`                          | **IPv4 互換 (ASN=0) のみ**を抽出表示         |
| user / priv       | `show ip route`                                      | ルーティング表を IPv4 形式で表示             |
| priv              | `show running-config`                                | 現在の設定を CLI 形式で出力                  |
| priv              | `configure terminal`                                 | グローバル config へ                         |
| global config     | `hostname NAME`                                      | ホスト名変更                                 |
| global config     | `interface NAME`                                     | インターフェース config へ                   |
| global config     | `ipv8 route PFX/LEN NEXT_HOP`                        | IPv8 static route（next-hop 経由）            |
| global config     | `ipv8 route PFX/LEN interface IFACE`                 | IPv8 static route（直接接続）                 |
| global config     | `ip route X.X.X.X/LEN Y.Y.Y.Y`                       | IPv4 static route（ASN=0 として記録）         |
| global config     | `ip route X.X.X.X/LEN interface IFACE`               | IPv4 直接接続 route                          |
| global config     | `no ipv8 route PFX/LEN`                              | ルート削除                                   |
| global config     | `end` / `exit`                                       | priv EXEC へ戻る                             |
| interface config  | `ipv8 address R.R.R.R.N.N.N.N`                       | ネイティブ IPv8 アドレスを割当               |
| interface config  | `ip address X.X.X.X`                                 | IPv4 アドレス割当（ASN=0 のショートカット）   |
| interface config  | `no shutdown` / `shutdown`                           | インターフェース有効/無効                    |
| interface config  | `description TEXT`                                   | 任意ラベル                                   |
| interface config  | `exit`                                               | interface config を抜ける                    |

> `ip …` 系は `ipv8 … 0.0.0.0.…` への **完全なショートカット**。`ip address 10.0.0.1` と `ipv8 address 0.0.0.0.10.0.0.1` は内部表現が完全一致し、`ping 10.0.0.1` と `ping8 0.0.0.0.10.0.0.1` が生成するフレームもバイト単位で同一。ライブラリ層のコードパスは一本で、2 つの構文は純粋にパーサーレベルのエイリアス。

---

## 対話型 IOS シェル

`ios_shell.py` は Cisco IOS 風の対話シェルで、**空（router ゼロ台）の状態から始まり**、ルータを足す・リンクを張る・任意の IPv8 アドレスを割り当てる・ping を打つ、までプロンプト上で完結します。

### 起動

```sh
python3 ios_shell.py
```

`~/.zshrc` / `~/.bashrc` に以下のエイリアスを入れると一語で叩けます：

```sh
export IPV8_LAB_HOME="$HOME/ipv8-lab"
alias ipv8lab='python3 "$IPV8_LAB_HOME/ios_shell.py"'
```

### 対話版限定コマンド（IOS には無い）

| コマンド                                          | 動作                                                                 |
|---------------------------------------------------|----------------------------------------------------------------------|
| `router add <NAME>`                               | ルータ新規作成（自動 attach）                                         |
| `router remove <NAME>`                            | ルータ削除（紐付く IF も切断）                                        |
| `link add <LINK> <Ra>:<Ifa> <Rb>:<Ifb>`           | リンク作成、両端に IF も自動生成                                      |
| `link remove <LINK>`                              | リンク撤去（両端の IF も削除）                                        |
| `attach <NAME>`                                   | コンソールを他ルータへ切替（毎回 user EXEC から）                     |
| `routers`                                         | ルータと各 IF の アドレス／admin 状態を一覧                            |
| `links`                                           | リンクと両端エンドポイントを一覧                                      |
| `show trace`                                      | これまでの全パケットを tcpdump 風に表示                               |
| `clear trace`                                     | トレースをクリア                                                      |
| `help-meta` / `?`                                 | メタコマンド早見表                                                    |
| `quit` / `:q`                                     | シェル終了                                                            |

その他は全て Cisco CLI へ素通し（上の Command Reference を参照）。

### モード遷移（本家 IOS と同じ）

```
user EXEC  ─ enable            →  priv EXEC
priv EXEC  ─ configure terminal→  global config
config     ─ interface <IFACE> →  interface config
config-if  ─ exit              →  global config
config     ─ end               →  priv EXEC
priv EXEC  ─ disable           →  user EXEC
```

### コピペで試せるセッション（3 台直列を一から組む）

```
router add R1
router add R2
router add R3

link add L12 R1:Gig0/0 R2:Gig0/0
link add L23 R2:Gig0/1 R3:Gig0/0

attach R1
enable
configure terminal
interface Gig0/0
 ipv8 address 0.0.253.233.10.12.0.1        ! R1 側の L12
 no shutdown
 exit
ipv8 route 0.0.253.234.0.0.0.0/0 0.0.253.233.10.12.0.2
ipv8 route 0.0.253.235.0.0.0.0/0 0.0.253.233.10.12.0.2
end

attach R2
enable
configure terminal
interface Gig0/0
 ipv8 address 0.0.253.234.10.12.0.2
 no shutdown
 exit
interface Gig0/1
 ipv8 address 0.0.253.234.10.23.0.1
 no shutdown
 exit
ipv8 route 0.0.253.233.0.0.0.0/0 0.0.253.234.10.12.0.1
ipv8 route 0.0.253.235.0.0.0.0/0 0.0.253.234.10.23.0.2
end

attach R3
enable
configure terminal
interface Gig0/0
 ipv8 address 0.0.253.235.10.23.0.2
 no shutdown
 exit
ipv8 route 0.0.253.233.0.0.0.0/0 0.0.253.235.10.23.0.1
ipv8 route 0.0.253.234.0.0.0.0/0 0.0.253.235.10.23.0.1
end

attach R1
enable
ping8 0.0.253.235.10.23.0.2                ! R1 → R3、2 ホップ
show trace
```

**このツアーで確認できること**

| ブロック | 観察できる内容 |
|---|---|
| *router add / link add* | `routers` / `links` で作成物を確認。新しい IF には仮アドレス `0.0.0.0.0.0.0.0` が入る |
| *interface 設定* | `ipv8 address` は **任意の 64-bit アドレス** を受け付ける（private ASN、IPv4-compat の ASN=0 など自由） |
| *static route* | 設定完了後 `ping8` が `!!!!!` (100%)、`show trace` で R1 → R2 → R3 の往復が per-hop TTL 減算付きで確認できる |

### 壊して直すパターン

```
attach R2
enable
configure terminal
interface Gig0/1
 shutdown
 end
clear trace
ping8 0.0.253.235.10.23.0.2                ! R2 で drop される

configure terminal
interface Gig0/1
 no shutdown
 end
ping8 0.0.253.235.10.23.0.2                ! 復旧
```

**確認できること**

- `shutdown` で `Interface.admin_down = True` になり、次のパケットはトレース上 `egress-admin-down (Gig0/1)` で drop
- `no shutdown` で即復旧。ルート表は触っていないのに到達性が戻る
- 失敗トレースが **該当ルータで止まる** ので、どこで詰まったか一目でわかる

### IPv4 下位互換（ASN=0）を同居させる

上の 3 台構成に 4 台目を加えて、R1 に IPv4-compat インターフェースを足します：

```
router add R4
link add L14 R1:Gig0/1 R4:Gig0/0

attach R1
enable
configure terminal
interface Gig0/1
 ipv8 address 0.0.0.0.192.168.1.1          ! ASN=0 側のエッジ
 no shutdown
 exit
ipv8 route 0.0.0.0.0.0.0.0/0 0.0.0.0.192.168.1.2
end
show ipv8 route                             ! ASN 0 と ASN 65001 のバケットが並ぶ
```

**確認できること**

- 1 台のルータが **ネイティブ IPv8 と `ASN = 0` の IPv4-compat を同居** できる
- `show ipv8 route` に ASN バケットが 2 つ（`0` と `65001`）並び、Tier 1 が機能したまま `ASN = 0` だけ IPv4 短絡を取る
- 再起動・リロード不要、実機 IOS と同じ挙動で **設定が即時反映**

> 迷ったら `routers` / `links` / `show trace` の 3 つで現状を確認できます。

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
