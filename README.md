# FM 网络电台 / FM Web Radio

📻 一个基于 Web 的 FM 网络电台播放器。电台数据来自开源的 [Radio Browser](https://www.radio-browser.info/) 索引，支持按国家/地区、区域（中央台 / 省份）、类别（新闻 / 交通 / 音乐 …）筛选，并在浏览器中直连播放。

A web-based FM radio player. Station data comes from the open-source [Radio Browser](https://www.radio-browser.info/) index. Filter by country, region (central / province) and category (news / traffic / music …), and play directly in the browser.

![Version](https://img.shields.io/badge/version-v1.0-blue.svg)

![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

---

## ✨ 功能特性 / Features

三个板块，顶部导航一键切换：

| 板块 | 内容 |
| --- | --- |
| 📻 电台 | 多国家在线 FM 电台（Radio Browser 索引），区域 + 类别筛选 |
| 📺 电视频道 | 多源聚合的公开 TV 直播（569 个频道），打开即自动测活、只显示可播放的，分类标签 + 台标预览 + 按名称排序 |
| 🎬 视频节目 | 《新闻联播》（近 30 天，每日完整版 + 当日分条）、《北京新闻》（近 20 期），左侧播放器 + 右侧列表，均可页内播放 |

- 🌍 **多国家/地区**：中国、全球、美国、日本、英国、韩国
- 🏷️ **自动分类标签**：区域（中央台 / 北京 / 江苏 / 山东 …）+ 类别（新闻 / 交通 / 音乐 / 财经 / 体育 …）
- 🔍 **搜索 + 筛选**：关键词搜索，区域与类别可叠加筛选
- ▶️ **浏览器直连播放**：HLS(.m3u8) 用 hls.js，普通音频(MP3/AAC) 用原生 `<audio>`
- 🧹 **自动去重**：按 url / stationuuid / 归一化名称三级去重，消除“同一个台出现多次”
- 🖥️ **跨平台部署**：Windows 与 Ubuntu 均可；支持通过 frp 从公网访问（可选，本地使用无需配置）
- 🔧 **后台守护 + 开机自启**：一条命令后台启动/停止/重启/查状态/看日志；Linux 支持 `./run.sh enable` 一键注册 systemd 开机自启
- 📱 **响应式布局**：自适应桌面与手机浏览器（平板/手机/小屏手机三档断点）；分类标签在手机上为单行横向滚动
- 🛡️ **直播源容错**：多源聚合 + 服务侧死链检测 + 播放端自动切换备用源

## 🚀 快速开始 / Quick Start

默认端口 **6123**。首次运行会自动安装依赖 `flask` / `requests`。

### Windows

双击 `run.bat` 即以**后台方式**启动（命令行窗口可以直接关闭），浏览器打开 <http://localhost:6123/>。

```bat
run.bat          :: 后台启动（默认）
run.bat stop     :: 停止
run.bat restart  :: 重启
run.bat status   :: 查看状态
run.bat logs     :: 实时日志（Ctrl+C 只退出查看）
run.bat run      :: 前台运行（调试）
./run.sh enable  :: 开机自启
```

Windows 开机自启：用「任务计划程序」创建基本任务，触发器选「计算机启动时」，操作为
`cmd /c "cd /d <项目目录> && run.bat"`，并勾选「不管用户是否登录都要运行」。

### Ubuntu / Linux

```bash
chmod +x run.sh
./run.sh              # 后台启动（默认，可关闭终端）
```

**不创建任何虚拟环境**，直接使用已存在的 Python 环境。默认使用 `run.sh` 顶部的 `DEFAULT_PY`：

```bash
DEFAULT_PY="/home/japp/miniconda3/envs/pyServer/bin/python"
```

切换方式（优先级：显式指定 > 默认环境 > `python3` > `python`）：

```bash
./run.sh                                                 # 用默认环境
PYTHON=/opt/conda/envs/other/bin/python ./run.sh         # 临时覆盖
conda activate myenv && PYTHON="$(command -v python)" ./run.sh   # 跟随已激活的 conda 环境
PORT=9000 ./run.sh                                       # 改端口
```

脚本会打印实际使用的解释器与版本，依赖 `flask` / `requests` 缺失时才安装到该环境。
默认路径不存在时会打印警告并自动回退到 `python3` / `python`。

#### 后台运行与开机自启（Linux）

```bash
./run.sh              # 后台启动（默认，可关闭终端）
./run.sh stop         # 停止
./run.sh restart      # 重启
./run.sh status       # 查看运行状态
./run.sh logs         # 实时日志（Ctrl+C 只退出查看，不停服务）
./run.sh run          # 前台运行（调试用）
./run.sh enable       # 设置开机自启（systemd）
./run.sh disable      # 取消开机自启
```

- 后台进程用 `nohup` 启动，PID 记录在 `.fmradio.pid`，日志追加到 `fmradio.log`。
- `./run.sh enable` 会自动生成 systemd 单元（写入当前 `WorkingDirectory`、`PORT` 与解释器路径）、
  执行 `systemctl enable` 并立即启动，无需手动改 `fmradio.service`。
- 无 systemd 的环境改用 cron：`@reboot cd <项目目录> && ./run.sh`。

### 通过 frp 公网访问（可选，本地不部署也可以正常使用）/ Public access via frp (optional)

> **可选项。** 只在本地使用时，直接访问 <http://localhost:6123/> 即可，无需做任何公网配置，功能完全一致。  
> 本节仅在需要让局域网以外的设备（如手机流量、异地电脑）访问时才需要。

如果希望从外网访问，把本机 `6123` 端口通过 frp（或其他内网穿透工具）映射到你自己的服务器公网端口，之后通过  
`http://<公网IP>:<映射端口>/` 访问。frpc 侧示例：

```toml
[[proxies]]
name = "fmradio"
type = "tcp"
localIP = "127.0.0.1"
localPort = 6123
remotePort = 6123
```

注意：

- 播放采用浏览器直连电台源站，音频流量不经过 frp，对服务器带宽压力很小。
- 若公网打开页面空白但本地正常，通常是没有映射端口或防火墙未放行 `remotePort`。

> **Optional.** For local use just open <http://localhost:6123/> — no public-network setup needed and all features work.  
> This section only applies if you want to reach the service from outside your LAN.

### 开机自启（systemd，Ubuntu）— 手动方式

推荐直接用 `./run.sh enable`（见上节）。也可以手动安装模板：

```bash
sudo cp fmradio.service /etc/systemd/system/fmradio.service
# 编辑 User、WorkingDirectory，以及 ExecStart 里的 Python 解释器路径：
sudo systemctl daemon-reload && sudo systemctl enable --now fmradio
```

> ⚠️ **生产环境建议换 WSGI 服务器**：`app.py` 默认用 Flask 自带的 `app.run()` 启动，控制台会打印
> *"This is a development server. Do not use it in a production deployment."*。
> 自省用没问题，但公网长期运行建议改用 `waitress`（纯 Windows/Linux 通用、无需编译）：
>
> ```bash
> pip install waitress
> waitress-serve --host 0.0.0.0 --port 6123 --threads 16 app:app
> ```
>
> 此时把 `fmradio.service` 的 `ExecStart` 指向 `waitress-serve` 即可，其余不变。
> 本项目不依赖 Flask 的开发期特性（无 debug、无 reload），替换后行为一致。

## ⚙️ 配置 / Configuration

| 项       | 说明                                                                                                                                  |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 端口      | 环境变量 `PORT`，默认 `6123`                                                                                                               |
| 数据源     | Radio Browser API（多镜像自动回退：de1 / de2 / at1 / all）                                                                                    |
| 播放模式    | 直连（浏览器直接连接电台源站）                                                                                                                     |
| 出网方式    | **纯直连（默认）**：`RB_PROXY_MODE=direct`，完全忽略系统代理与 `HTTP(S)_PROXY` 环境变量，不使用 Clash Verge 等任何代理。仅在特殊网络下才改为 `system`（只走代理）或 `auto`（直连失败回退代理） |
| 超时 / 缓存 | `RB_TIMEOUT`（默认 8s）、`RB_DEADLINE`（每通道时限 30s）、`RB_CACHE_TTL`（结果缓存 300s） |
| TV 频道源 | `TV_SOURCES`，逗号分隔，默认 6 个源（Collect-IPTV 每 4 小时自动测活优选 + gh-proxy 镜像、vbskycn 6 小时拨测、peterhchina 两个、iptv-org）。同一频道跨源合并为多个备用源，不可达的源自动跳过 |
| TV/节目缓存 | `TV_TIMEOUT`（默认 15s）、`TV_CACHE_TTL`（默认 1800s）、`TV_SOURCES_DEADLINE`（拉取全部源的总时限，默认 45s） |
| 死链检测 | `TV_PROBE_TTL`（600s）、`TV_PROBE_WORKERS`（48）、`TV_PROBE_TIMEOUT`（4s）、`TV_MAX_URLS`（每频道最多备用源 6）；打开页面自动全量探测，`↻ 刷新可用频道` 按钮强制重测 |
| 联播往期天数 | `XWLB_DAYS`（默认 30） |

### 电视频道：打开即测活，只显示可播放的

公开直播源失效是常态，本项目从五个层面解决：

1. **多源聚合**：默认 6 个公开列表，同一频道按归一化名合并，最多保留 `TV_MAX_URLS`（6）个备用地址
2. **打开即自动测活**：进入 `/tv` 时通过 SSE 流式接口并发探测每个频道的所有备用源，**列表只渲染可连接的频道**，进度条实时显示「正在测试频道连接 x/y」
3. **结果缓存 + 单飞**：探测结果缓存 `TV_PROBE_TTL`（默认 10 分钟），期间刷新页面 **0.5 秒**出列表；多人同时打开时后来者直接命中缓存，不会把探测线程按用户数翻倍
4. **播放端自动切换**：某个源播放失败时自动切到下一个备用源，状态栏显示「主源失效，切换到备用源 n/m」；浏览器拦截自动播放时不会误判为源失效
5. **总时限保护**：所有源都不可达时，`TV_SOURCES_DEADLINE` 保证 SSE 在 45 秒内给出明确错误，不会无限挂住

实测：842 个频道中 **718 个可播放**，124 个连不上的被自动过滤。

> 部署提示：默认源里 `raw.githubusercontent.com` 在国内服务器经常读取超时，已配 gh-proxy 镜像兜底（实测超时后仍能拿到全部频道）。若部署机访问 GitHub 系列全部不通，可用 `TV_SOURCES` 换成国内可达的 m3u 地址。

### 数据源 / Data sources

- 电台索引：[Radio Browser](https://api.radio-browser.info)（社区维护，无 API key）
- 电视频道：[vbskycn/iptv](https://github.com/vbskycn/iptv)（6 小时自动拨测）、[peterhchina/iptv](https://github.com/peterhchina/iptv)（每日更新）、[iptv-org](https://github.com/iptv-org/iptv)（全球）
- 《新闻联播》：央视网 <https://tv.cctv.com/lm/xwlb/index.shtml>，往期页 `tv.cctv.com/lm/xwlb/day/YYYYMMDD.shtml`，播放地址经 `vdn.apps.cntv.cn` 解析
- 《北京新闻》：北京时间 <https://www.btime.com/btv/btvxw_bjxm>，播放地址经 `app.api.btime.com/video/play` 解析

本项目仅做聚合与界面呈现，不存储、不分发任何音视频内容，播放全部走浏览器直连原始来源。
源失效时可通过 `TV_SOURCES` 或上述官方页面自行增删。

### API 一览 / Endpoints

| 端点 | 说明 |
| --- | --- |
| `GET /` `GET /tv` `GET /programs` | 三个页面 |
| `GET /api/radiobrowser?country=CN&limit=300` | 电台列表（去重 + 自动标签） |
| `GET /api/probe?url=<流地址>` | 服务器侧检测流是否存活 |
| `GET /api/tv/channels` | 电视频道列表（含台标、分类、多备用源） |
| `GET /api/tv/channels?probe=1` | 同上，附带死链检测结果与延迟 |
| `GET /api/tv/programs?src=xwlb\|bjxw` | 节目列表；`xwlb` 支持 `&date=YYYY-MM-DD` 取往期 |
| `GET /api/tv/play?url=<节目详情页>[&gid=]` | 解析节目可直接播放的媒体地址 |
| `GET /healthz` | 健康检查 |

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
├── app.py               # Flask 后端：页面 + 电台/TV/节目 API
├── tv.py                # TV 频道(m3u) 与节目(央视/北京时间) 聚合解析
├── tagging.py           # 电台区域/类别标签推导 + 名称归一化（去重）
├── proxy_utils.py       # URL 校验与 SSRF 防护
├── requirements.txt     # Python 依赖（Flask, requests）
├── static/
│   ├── index.html       # 📻 电台页
│   ├── tv.html          # 📺 电视频道页（分类标签 + 台标预览）
│   ├── programs.html    # 🎬 视频节目页（新闻联播 / 北京新闻）
│   ├── style.css        # 全部样式（含响应式断点）
│   ├── app.js           # 电台页逻辑
│   ├── tv.js            # 电视频道页逻辑
│   └── programs.js      # 视频节目页逻辑
├── run.bat              # Windows 启动脚本（默认后台；start/stop/restart/status/logs/run）
├── run.sh               # Ubuntu/Linux 启动脚本（默认后台 + stop/restart/status/logs/run/enable/disable）
├── fmradio.service      # systemd 服务模板（手动安装用；推荐 ./run.sh enable）
├── LICENSE              # Apache License 2.0
└── README.md
```

## 🛠️ 技术栈 / Tech Stack

Python · Flask · requests · hls.js · Radio Browser API · iptv-org

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
