# FM 网络电台 / FM Web Radio

📻 一个基于 Web 的 FM 网络电台播放器。电台数据来自开源的 [Radio Browser](https://www.radio-browser.info/) 索引，支持按国家/地区、区域（中央台 / 省份）、类别（新闻 / 交通 / 音乐 …）筛选，并在浏览器中直连播放。

A web-based FM radio player. Station data comes from the open-source [Radio Browser](https://www.radio-browser.info/) index. Filter by country, region (central / province) and category (news / traffic / music …), and play directly in the browser.

![Version](https://img.shields.io/badge/version-v1.0-blue.svg)

![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

---

## ✨ 功能特性 / Features

- 🌍 **多国家/地区**：中国、全球、美国、日本、英国、韩国
- 🏷️ **自动分类标签**：区域（中央台 / 北京 / 江苏 / 山东 …）+ 类别（新闻 / 交通 / 音乐 / 财经 / 体育 …）
- 🔍 **搜索 + 筛选**：关键词搜索，区域与类别可叠加筛选
- ▶️ **浏览器直连播放**：HLS(.m3u8) 用 hls.js，普通音频(MP3/AAC) 用原生 `<audio>`
- 🧹 **自动去重**：按 url / stationuuid / 归一化名称三级去重，消除“同一个台出现多次”
- 🖥️ **跨平台部署**：Windows 与 Ubuntu 均可；支持通过 frp 从公网访问（可选，本地使用无需配置）
- 📱 **响应式布局**：自适应桌面与手机浏览器（平板/手机/小屏手机三档断点）

## 🚀 快速开始 / Quick Start

### Windows

双击 `run.bat`（首次运行会自动安装 Flask / requests），浏览器打开 <http://localhost:8000/>。

### Ubuntu / Linux

```bash
chmod +x run.sh
./run.sh
```

首次运行会自动创建 `.venv` 并安装依赖；`PORT=9000 ./run.sh` 可改端口。

### 通过 frp 公网访问（可选，本地不部署也可以正常使用）/ Public access via frp (optional)

> **可选项。** 只在本地使用时，直接访问 <http://localhost:8000/> 即可，无需做任何公网配置，功能完全一致。  
> 本节仅在需要让局域网以外的设备（如手机流量、异地电脑）访问时才需要。

如果希望从外网访问，把本机 `8000` 端口通过 frp（或其他内网穿透工具）映射到你自己的服务器公网端口，之后通过  
`http://<公网IP>:<映射端口>/` 访问。frpc 侧示例：

```toml
[[proxies]]
name = "fmradio"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8000
remotePort = 8000
```

注意：

- 播放采用浏览器直连电台源站，音频流量不经过 frp，对服务器带宽压力很小。
- 若公网打开页面空白但本地正常，通常是没有映射端口或防火墙未放行 `remotePort`。

> **Optional.** For local use just open <http://localhost:8000/> — no public-network setup needed and all features work.  
> This section only applies if you want to reach the service from outside your LAN.

### 开机自启（systemd，Ubuntu）

```bash
sudo cp fmradio.service /etc/systemd/system/fmradio.service
# 编辑其中的 User 与 WorkingDirectory 为实际值后：
sudo systemctl daemon-reload && sudo systemctl enable --now fmradio
```

## ⚙️ 配置 / Configuration

| 项       | 说明                                                                                                                                  |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 端口      | 环境变量 `PORT`，默认 `8000`                                                                                                               |
| 数据源     | Radio Browser API（多镜像自动回退：de1 / de2 / at1 / all）                                                                                    |
| 播放模式    | 直连（浏览器直接连接电台源站）                                                                                                                     |
| 出网方式    | **纯直连（默认）**：`RB_PROXY_MODE=direct`，完全忽略系统代理与 `HTTP(S)_PROXY` 环境变量，不使用 Clash Verge 等任何代理。仅在特殊网络下才改为 `system`（只走代理）或 `auto`（直连失败回退代理） |
| 超时 / 缓存 | `RB_TIMEOUT`（默认 8s）、`RB_DEADLINE`（每通道时限 30s）、`RB_CACHE_TTL`（结果缓存 300s）                                                              |

### 直连说明 / Direct-connection policy

本项目**不使用任何代理**。`app.py` 在直连模式下会：

1. 使用 `trust_env=False` 的专属 Session，忽略环境变量与 Windows 系统代理；
2. 启动时直接清除 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 等环境变量；
3. 启动时打印日志确认当前为直连模式（若检测到代理配置会提示「已强制绕过」）。

因此即使本机装有 Clash Verge 并开启了系统代理，也不会影响本服务。

### 排查：启动后「加载失败 … ProxyError / WinError 10061」

`requests` 默认会读取环境变量或 Windows 系统代理。若机器上配了 Clash / Verge 等本地代理但代理软件未运行，  
所有出站请求都会因连不上 `127.0.0.1:xxxx` 而失败，表现为「刚启动加载失败，刷新几次又正常」。  
现已默认纯直连并清除代理环境变量，该问题不再出现。若本机**必须**走代理才能出网，启动时设 `RB_PROXY_MODE=system`。

### Troubleshooting: "Load failed … ProxyError / WinError 10061"

`requests` picks up `HTTP(S)_PROXY` env vars / the Windows system proxy by default. If a local proxy  
(Clash, Verge, …) is configured but not running, every outbound call fails with `127.0.0.1:xxxx refused`,  
which looks like "fails at startup, works after a few refreshes". The app now runs in **direct mode by default**:  
it uses a `trust_env=False` session and strips proxy env vars at startup, so a local Clash Verge install  
has no effect. Set `RB_PROXY_MODE=system` only if the host can reach the internet exclusively via a proxy.

## 📁 项目结构 / Project Structure

单一代码源，Windows 与 Ubuntu 共用；仅启动脚本不同（`run.bat` / `run.sh`）。

```
.
├── app.py               # Flask 后端：页面 + /api/radiobrowser + /api/probe
├── tagging.py           # 电台区域/类别标签推导 + 名称归一化（去重）
├── proxy_utils.py       # URL 校验与 SSRF 防护
├── requirements.txt     # Python 依赖（Flask, requests）
├── static/              # 前端页面（index.html / style.css / app.js）
├── run.bat              # Windows 一键启动
├── run.sh               # Ubuntu/Linux 一键启动（自动建 venv）
├── fmradio.service      # systemd 服务模板（Ubuntu 开机自启）
├── LICENSE              # Apache License 2.0
└── README.md
```

## 🛠️ 技术栈 / Tech Stack

Python · Flask · requests · hls.js · Radio Browser API

## 📄 License / 协议

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.  
本项目采用 Apache License 2.0 协议，完整文本见 [LICENSE](LICENSE)。

## 🤖 AI 协助声明 / AI Assistance

本项目在开发过程中使用 *Codex&#x20;*/ 豆包 App / Workbuddy 协助编写与调试，所用账号为：  
This project was developed with assistance from Codex / Doubao App, using the following accounts:

```
findaxh@outlook.com
wangxuehao2024@163.com
```

## 👤 Author / 作者

王雪豪  
Email: <findaxh@outlook.com>  
Version: v1.0  
Updated: 2026-10-08
