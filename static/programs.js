"use strict";

const video = document.getElementById("video");
const listEl = document.getElementById("progList");
const srcChipsEl = document.getElementById("srcChips");
const dateChipsEl = document.getElementById("dateChips");
const itemLabel = document.getElementById("itemLabel");
const nowTitle = document.getElementById("nowTitle");
const nowMeta = document.getElementById("nowMeta");
const nowStatus = document.getElementById("nowStatus");

const SOURCES = [
  { key: "xwlb", label: "📺 新闻联播", desc: "CCTV《新闻联播》每日更新完整视频与当日分条" },
  { key: "bjxw", label: "📡 北京新闻", desc: "BRTV《北京新闻》每日更新完整视频" },
];

let currentSrc = "xwlb";
let dates = [];
let currentDate = "";
let items = [];
let currentItem = null;
let currentHls = null;

function setStatus(t) { nowStatus.textContent = t; }

// ---------- 来源切换 ----------
function renderSrcChips() {
  srcChipsEl.innerHTML = "";
  SOURCES.forEach((s) => {
    const el = document.createElement("button");
    el.className = "nav-btn" + (s.key === currentSrc ? " active" : "");
    el.textContent = s.label;
    el.onclick = () => {
      if (s.key === currentSrc) return;
      currentSrc = s.key;
      currentDate = "";
      renderSrcChips();
      load();
    };
    srcChipsEl.appendChild(el);
  });
}

// ---------- 日期 chips ----------
function renderDateChips() {
  dateChipsEl.innerHTML = "";
  if (!dates.length) {
    dateChipsEl.innerHTML = '<span class="side-hint">该来源按节目聚合，无需选日期</span>';
    return;
  }
  dates.forEach((d) => {
    const el = document.createElement("div");
    el.className = "chip" + (d === currentDate ? " active" : "");
    el.textContent = d.slice(5);            // 10-21
    el.title = d;
    el.onclick = () => {
      if (d === currentDate) return;
      currentDate = d;
      renderDateChips();
      load();
    };
    dateChipsEl.appendChild(el);
  });
}

// ---------- 加载 ----------
let loadToken = 0;
function load(retryLeft) {
  const myToken = ++loadToken;
  if (typeof retryLeft !== "number") retryLeft = 2;
  setStatus(retryLeft === 2 ? "正在加载…" : "正在重试…");
  listEl.innerHTML = '<div class="side-hint">正在加载…</div>';

  let q = "/api/tv/programs?src=" + encodeURIComponent(currentSrc);
  if (currentDate) q += "&date=" + encodeURIComponent(currentDate);

  fetch(q)
    .then((r) => r.json())
    .then((d) => {
      if (myToken !== loadToken) return;
      if (d.ok) {
        items = d.items || [];
        dates = d.dates || [];
        if (d.date) currentDate = d.date;          // 以服务端返回的实际日期为准
        if (!currentDate && dates.length) currentDate = dates[0];
        renderDateChips();
        renderList();
        const meta = d.meta || {};
        itemLabel.textContent = (meta.name || "") + (d.date ? " · " + d.date : "");
        setStatus("共 " + (d.count || items.length) + " 期节目");
        return;
      }
      if (retryLeft > 0) {
        setTimeout(() => { if (myToken === loadToken) load(retryLeft - 1); }, 1200);
        return;
      }
      listEl.innerHTML = '<div class="side-hint">加载失败：' + (d.error || "未知错误") + "</div>";
      setStatus("加载失败");
    })
    .catch((e) => {
      if (myToken !== loadToken) return;
      if (retryLeft > 0) {
        setTimeout(() => { if (myToken === loadToken) load(retryLeft - 1); }, 1200);
        return;
      }
      listEl.innerHTML = '<div class="side-hint">加载失败：' + e + "</div>";
      setStatus("加载失败");
    });
}

// ---------- 节目列表 ----------
function renderList() {
  listEl.innerHTML = "";
  if (!items.length) {
    listEl.innerHTML = '<div class="side-hint">暂无节目</div>';
    return;
  }
  items.forEach((it) => {
    const el = document.createElement("div");
    el.className = "side-item" + (currentItem && currentItem.url === it.url ? " active" : "");

    const thumb = document.createElement("div");
    thumb.className = "side-thumb";
    if (it.cover) {
      const img = document.createElement("img");
      img.src = it.cover;
      img.alt = "";
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      img.onerror = () => { thumb.textContent = "🎬"; };
      thumb.appendChild(img);
    } else {
      thumb.textContent = "🎬";
    }

    const body = document.createElement("div");
    body.className = "side-body";
    const t = document.createElement("div");
    t.className = "side-title";
    t.textContent = it.title;
    const m = document.createElement("div");
    m.className = "side-meta";
    m.textContent = (it.duration ? it.duration + " · " : "") + (it.tag || it.source || "");
    body.appendChild(t);
    body.appendChild(m);

    el.appendChild(thumb);
    el.appendChild(body);
    el.onclick = () => playItem(it);
    listEl.appendChild(el);
  });
}

// ---------- 播放 ----------
function destroyHls() {
  if (currentHls) {
    try { currentHls.destroy(); } catch (e) {}
    currentHls = null;
  }
}

function playItem(it) {
  currentItem = it;
  nowTitle.textContent = it.title;
  nowMeta.textContent =
    (it.date || "") +
    (it.duration ? " · " + it.duration : "") +
    (it.source ? " · " + it.source : "");
  setStatus("正在解析播放地址…");
  renderList();
  destroyHls();

  let q = "/api/tv/play?url=" + encodeURIComponent(it.url);
  if (it.gid) q += "&gid=" + encodeURIComponent(it.gid);

  fetch(q)
    .then((r) => r.json())
    .then((d) => {
      if (!d.ok) {
        setStatus((d.error || "无法解析播放地址") + "，正在打开原页面…");
        window.open(it.url, "_blank", "noopener");
        return;
      }
      video.src = d.url;
      video.play().catch(() => setStatus("请点击播放器中的播放按钮"));
      setStatus(
        "● 已就绪" +
          (d.duration ? " · " + d.duration : "") +
          (d.rate ? " · " + d.rate + "kbps" : "")
      );
    })
    .catch((e) => setStatus("解析失败：" + e));
}

video.addEventListener("playing", () => setStatus("● 播放中"));
video.addEventListener("waiting", () => setStatus("缓冲中…"));
video.addEventListener("pause", () => setStatus("已暂停"));
video.addEventListener("error", () => setStatus("播放出错，请重试或换一期"));

// ---------- 键盘：上下期切换 ----------
document.addEventListener("keydown", (e) => {
  if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  if (!items.length) return;
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  let i = currentItem ? items.findIndex((x) => x.url === currentItem.url) : -1;
  i = e.key === "ArrowDown" ? Math.min(i + 1, items.length - 1) : Math.max(i - 1, 0);
  playItem(items[i]);
});

renderSrcChips();
load();
