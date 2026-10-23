"use strict";

const video = document.getElementById("video");
const listEl = document.getElementById("tvList");
const searchEl = document.getElementById("search");
const catChipsEl = document.getElementById("catChips");
const nowName = document.getElementById("nowName");
const nowStatus = document.getElementById("nowStatus");
const testBtn = document.getElementById("testBtn");
const refreshBtn = document.getElementById("refreshBtn");
const probeBar = document.getElementById("probeBar");
const probeFill = document.getElementById("probeFill");
const probeText = document.getElementById("probeText");

let channels = [];        // 仅可播放的频道
let allCount = 0;         // 探测前总数
let currentCat = "全部";
let currentChannel = null;
let currentHls = null;
let urlIndex = 0;
let loading = false;

function setStatus(t) { nowStatus.textContent = t; }

function showProbe(txt, pct) {
  probeBar.style.display = "flex";
  probeText.textContent = txt;
  probeFill.style.width = (pct == null ? 15 : Math.max(0, Math.min(100, pct))) + "%";
}
function hideProbe() { probeBar.style.display = "none"; }

// ---------- 加载：拉列表 → 探测存活 → 只渲染可用频道 ----------
function load(opts) {
  opts = opts || {};
  if (loading) return;
  loading = true;
  refreshBtn.disabled = true;
  showProbe("正在加载频道列表…", 5);

  const url = "/api/tv/channels/stream" + (opts.refresh ? "?refresh=1" : "");
  let buffer = "";

  fetch(url)
    .then(async (resp) => {
      if (!resp.ok || !resp.body) throw new Error("HTTP " + resp.status);
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const raw = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 2);
          if (!raw.startsWith("data:")) continue;
          let d;
          try { d = JSON.parse(raw.slice(5).trim()); } catch (e) { continue; }
          handleEvent(d);
        }
      }
    })
    .catch((e) => {
      if (!channels.length) {
        listEl.innerHTML = '<div class="empty">加载失败：' + e + "</div>";
        setStatus("加载失败");
        hideProbe();
      }
    })
    .finally(() => {
      loading = false;
      refreshBtn.disabled = false;
    });
}

function handleEvent(d) {
  if (d.phase === "loading") {
    showProbe("正在加载频道列表…", 5);
    return;
  }
  if (d.phase === "loaded") {
    allCount = d.count;
    showProbe("共 " + allCount + " 个频道，正在测试能否连接…", 10);
    return;
  }
  if (d.phase === "probing") {
    const pct = 10 + 85 * (d.done / Math.max(1, d.total));
    showProbe("正在测试频道连接 " + d.done + "/" + d.total + " …", pct);
    return;
  }
  if (d.phase === "error") {
    listEl.innerHTML = '<div class="empty">加载失败：' + (d.error || "未知错误") + "</div>";
    setStatus("加载失败");
    hideProbe();
    return;
  }
  if (d.phase === "done") {
    channels = (d.channels || []).filter((c) => c.live);
    const dead = (d.channels || []).length - channels.length;
    currentCat = "全部";
    renderChips();
    renderList();
    hideProbe();
    if (dead > 0) {
      setStatus("可用 " + channels.length + " 个 · 已过滤 " + dead + " 个无法连接的频道");
    } else {
      setStatus("共 " + channels.length + " 个可用频道");
    }
    if (d.errors && d.errors.length) console.warn("部分源不可用:", d.errors);
  }
}

// ---------- 分类 chips ----------
function renderChips() {
  const cset = new Set();
  channels.forEach((c) => (c.cats || []).forEach((x) => cset.add(x)));
  const cats = ["全部", ...[...cset].sort()];
  catChipsEl.innerHTML = "";
  cats.forEach((c) => {
    const el = document.createElement("div");
    el.className = "chip" + (c === currentCat ? " active" : "");
    el.textContent = c;
    el.onclick = () => { currentCat = c; renderChips(); renderList(); };
    catChipsEl.appendChild(el);
  });
}

function getFiltered() {
  const kw = searchEl.value.trim().toLowerCase();
  return channels.filter((c) => {
    if (currentCat !== "全部" && !(c.cats || []).includes(currentCat)) return false;
    if (kw) {
      const hay = ((c.name || "") + " " + (c.raw_name || "")).toLowerCase();
      if (!hay.includes(kw)) return false;
    }
    return true;
  });
}

function renderList() {
  const list = getFiltered();
  listEl.innerHTML = "";
  // 探测进行中（已拿到总数但还没有可用频道）：给出明确提示，
  // 而不是显示「没有匹配的频道」让人以为源全挂了。
  if (allCount && !channels.length) {
    listEl.innerHTML = '<div class="empty">正在逐个测试频道能否连接，请稍候…</div>';
    return;
  }
  if (!allCount && !channels.length) {
    listEl.innerHTML = '<div class="empty">正在加载频道列表…</div>';
    return;
  }
  if (!list.length) {
    listEl.innerHTML = '<div class="empty">没有匹配的频道</div>';
    return;
  }
  list.forEach((ch) => {
    const el = document.createElement("div");
    el.className = "tv-card" + (currentChannel && currentChannel.name === ch.name ? " playing" : "");

    const box = document.createElement("div");
    box.className = "tv-logo";
    if (ch.logo) {
      const img = document.createElement("img");
      img.src = ch.logo;
      img.alt = ch.name;
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      img.onerror = () => {
        box.innerHTML = "";
        const fb = document.createElement("span");
        fb.className = "fallback";
        fb.textContent = ch.name.slice(0, 2);
        box.appendChild(fb);
      };
      box.appendChild(img);
    } else {
      const fb = document.createElement("span");
      fb.className = "fallback";
      fb.textContent = ch.name.slice(0, 2);
      box.appendChild(fb);
    }

    const nm = document.createElement("div");
    nm.className = "tname";
    nm.textContent = ch.name;

    const sub = document.createElement("div");
    sub.className = "tsub";
    let txt = (ch.cats || []).slice(0, 2).join(" / ");
    if (ch.backups > 0) txt += (txt ? " · " : "") + ch.backups + " 备源";
    if (ch.latency_ms != null) txt += (txt ? " · " : "") + ch.latency_ms + "ms";
    sub.textContent = txt;

    el.appendChild(box);
    el.appendChild(nm);
    el.appendChild(sub);
    el.onclick = () => playChannel(ch);
    listEl.appendChild(el);
  });
}

// ---------- 播放：多源自动切换 ----------
function destroyHls() {
  if (currentHls) {
    try { currentHls.destroy(); } catch (e) {}
    currentHls = null;
  }
}

function urlsOf(ch) {
  const all = (ch && ch.urls && ch.urls.length) ? ch.urls.slice() : [ch.url];
  if (ch && ch.best_url) {                       // 探测出的最快源放最前
    const i = all.indexOf(ch.best_url);
    if (i > 0) { all.splice(i, 1); all.unshift(ch.best_url); }
  }
  return all;
}

function playChannel(ch) {
  currentChannel = ch;
  urlIndex = 0;
  nowName.textContent = ch.name;
  setStatus("正在连接…");
  renderList();
  destroyHls();
  playUrl(ch, 0);
}

function playUrl(ch, idx) {
  const urls = urlsOf(ch);
  if (idx >= urls.length) {
    setStatus("所有 " + urls.length + " 个源均失效，请稍后再试");
    return;
  }
  urlIndex = idx;
  const url = urls[idx];
  if (idx > 0) setStatus("主源失效，切换到备用源 " + idx + "/" + (urls.length - 1) + "…");

  const isHls = ch.type === "hls" || /\.m3u8(\?|$)/i.test(url);
  if (isHls && window.Hls && Hls.isSupported()) {
    const hls = new Hls();
    currentHls = hls;
    hls.loadSource(url);
    hls.attachMedia(video);
    let switched = false;
    hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(autoplayFallback));
    hls.on(Hls.Events.ERROR, (evt, data) => {
      if (!data.fatal) return;
      if (!switched) {
        switched = true;
        try { hls.destroy(); } catch (e) {}
        currentHls = null;
        playUrl(ch, idx + 1);                     // 自动切换下一个源
        return;
      }
      setStatus("HLS 播放失败：源失效或被 CORS 拦截");
    });
  } else if (isHls && video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = url;
    video.play().catch(autoplayFallback);
  } else {
    video.src = url;
    video.play().catch(autoplayFallback);
  }
}

// 浏览器普遍禁止带声音的自动播放，play() 会以 NotAllowedError 拒绝。
// 这不是源失效，不能拿去切换备用源，否则会误判「主源失效」。
function autoplayFallback(err) {
  if (err && (err.name === "NotAllowedError" || err.name === "NotSupportedError")) {
    setStatus("已就绪 — 浏览器拦截了自动播放，请点播放器中的 ▶ 按钮");
    return;
  }
  if (currentChannel) playUrl(currentChannel, urlIndex + 1);
}

video.addEventListener("playing", () => {
  const n = urlsOf(currentChannel).length;
  setStatus("● 播放中" + (n > 1 ? " · 源 " + (urlIndex + 1) + "/" + n : ""));
  renderList();
});
video.addEventListener("waiting", () => setStatus("缓冲中…"));
video.addEventListener("pause", () => { setStatus("已暂停"); renderList(); });
video.addEventListener("error", () => {
  if (!currentChannel) return;
  const urls = urlsOf(currentChannel);
  if (urlIndex + 1 < urls.length) {
    playUrl(currentChannel, urlIndex + 1);
  } else {
    setStatus("播放出错：所有源均失效");
  }
});

// ---------- 检测源 ----------
testBtn.addEventListener("click", () => {
  const ch = currentChannel || channels[0];
  if (!ch) { setStatus("暂无频道"); return; }
  setStatus("正在检测该源…");
  fetch("/api/probe?url=" + encodeURIComponent(ch.url))
    .then((r) => r.json())
    .then((d) => {
      if (d.ok) setStatus("该源存活 ✓ (HTTP " + d.status + " · " + (d.content_type || "") + ")");
      else setStatus("该源不可用 ✗ " + (d.status ? ("HTTP " + d.status) : (d.error || "")));
    })
    .catch((e) => setStatus("检测失败：" + e));
});

// ---------- 事件 ----------
searchEl.addEventListener("input", renderList);
refreshBtn.addEventListener("click", () => load({ refresh: true }));

load();
