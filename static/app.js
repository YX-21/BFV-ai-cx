const state = {
    activeView: "player",
    lastServerSearch: null,
    lastServerMeta: null,
};

const platformLabels = {
    pc: "PC",
    xboxone: "Xbox One",
    ps4: "PS4",
};

const regionLabels = {
    all: "全部地区",
    Asia: "亚洲",
    EU: "欧洲",
    NAm: "北美",
    SAm: "南美",
    OC: "大洋洲",
    Afr: "非洲",
    AC: "南极",
};

const modeLabels = {
    Airborne: "空降兵",
    Breakthrough: "突破",
    BreakthroughLarge: "大型突破",
    Conquest: "征服",
    Firestorm: "火风暴",
    "Firestorm (solo)": "火风暴（单人）",
    DakarSolo: "火风暴（单人）",
    Domination: "抢攻",
    FinalStand: "最后一战",
    Frontlines: "前线",
    FrontlinesMedium: "小型前线",
    Outpost: "前哨",
    Rush: "突袭",
    SquadConquest: "小队征服",
    TeamDeathMatch: "团队死斗",
    Possession: "抢占",
    TugOfWar: "拔河",
};

const mapLabels = {
    Aerodrome: "机场",
    "Al Marj Encampment": "阿尔马吉营地",
    "Al Sundan": "艾尔桑丹",
    Arras: "阿拉斯",
    Devastation: "荒废之地",
    "Fjell 652": "菲耶尔 652",
    Hamada: "哈马达",
    "Iwo Jima": "硫磺岛",
    Marita: "马里塔",
    Mercury: "水星",
    Narvik: "纳尔维克",
    "Operation Underground": "地下行动",
    "Pacific Storm": "太平洋风暴",
    Panzerstorm: "装甲风暴",
    Provence: "普罗旺斯",
    Rotterdam: "鹿特丹",
    "Solomon Islands": "所罗门群岛",
    "Twisted Steel": "钢铁熔炉",
    "Wake Island": "威克岛",
    Halvoy: "哈沃伊",
    "Halvøy": "哈沃伊",
    DK_Norway: "哈沃伊",
};

const formatNumber = new Intl.NumberFormat("zh-CN");
const refs = {};

document.addEventListener("DOMContentLoaded", () => {
    refs.notice = document.getElementById("notice");
    refs.overviewGrid = document.getElementById("overview-grid");
    refs.topMaps = document.getElementById("top-maps");
    refs.topModes = document.getElementById("top-modes");
    refs.regions = document.getElementById("regions");
    refs.lastUpdated = document.getElementById("last-updated");
    refs.results = document.getElementById("results");
    refs.resultsTitle = document.getElementById("results-title");
    refs.resultsSubtitle = document.getElementById("results-subtitle");
    refs.loadingState = document.getElementById("loading-state");
    refs.loadingText = document.getElementById("loading-text");
    refs.playerForm = document.getElementById("player-form");
    refs.serverForm = document.getElementById("server-form");
    refs.viewButtons = [...document.querySelectorAll("[data-view]")];

    refs.viewButtons.forEach((button) => {
        button.addEventListener("click", () => switchView(button.dataset.view));
    });

    refs.playerForm.addEventListener("submit", handlePlayerSubmit);
    refs.serverForm.addEventListener("submit", handleServerSubmit);

    loadOverview();
});

function switchView(view) {
    state.activeView = view;
    refs.viewButtons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.view === view);
    });
    refs.playerForm.classList.toggle("search-form--active", view === "player");
    refs.serverForm.classList.toggle("search-form--active", view === "server");
    hideNotice();
}

function escapeHtml(value = "") {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function formatTimestamp(value) {
    if (!value) {
        return "刚刚";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return "刚刚";
    }

    return date.toLocaleString("zh-CN", {
        hour12: false,
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function formatValue(value) {
    if (typeof value === "number") {
        return Number.isInteger(value) ? formatNumber.format(value) : value.toFixed(2);
    }
    return value ?? "--";
}

function translateMode(value) {
    return modeLabels[value] || value || "未知模式";
}

function translateMap(value) {
    return mapLabels[value] || value || "未知地图";
}

function showNotice(message, type = "error") {
    refs.notice.hidden = false;
    refs.notice.textContent = message;
    refs.notice.classList.toggle("notice--info", type === "info");
}

function hideNotice() {
    refs.notice.hidden = true;
    refs.notice.textContent = "";
    refs.notice.classList.remove("notice--info");
}

function setLoading(active, text = "正在查询...") {
    refs.loadingState.hidden = !active;
    refs.loadingText.textContent = text;
}

function setResultHeader(title, subtitle) {
    refs.resultsTitle.textContent = title;
    refs.resultsSubtitle.textContent = subtitle;
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });

    const payload = await response.json();
    if (!response.ok || !payload.success) {
        throw new Error(payload.message || "请求失败");
    }

    return payload.data;
}

async function loadOverview() {
    try {
        const overview = await requestJson("/api/overview");
        renderOverview(overview);
    } catch (error) {
        refs.lastUpdated.textContent = "全局状态加载失败";
        showNotice(`首页概览加载失败：${error.message}`, "info");
    }
}

function renderOverview(data) {
    refs.lastUpdated.textContent = `全局状态更新于 ${formatTimestamp(data.updatedAt)}`;
    refs.overviewGrid.innerHTML = `
        ${metricCard("在线玩家", formatNumber.format(data.totals.players), "当前所有可见服务器中的玩家总数")}
        ${metricCard("活跃服务器", formatNumber.format(data.totals.servers), "当前已统计到的服务器数量")}
        ${metricCard("排队人数", formatNumber.format(data.totals.queue), "排队中玩家数")}
        ${metricCard("社区 / 官服", `${formatNumber.format(data.totals.communityServers)} / ${formatNumber.format(data.totals.officialServers)}`, "社区服与官服的实时对比")}
    `;

    refs.topMaps.innerHTML = renderRankList(data.topMaps, translateMap);
    refs.topModes.innerHTML = renderRankList(data.topModes, translateMode);
    refs.regions.innerHTML = renderRegionList(data.regions);
}

function metricCard(title, value, hint) {
    return `
        <article class="metric-card">
            <p>${escapeHtml(title)}</p>
            <strong>${escapeHtml(value)}</strong>
            <span>${escapeHtml(hint)}</span>
        </article>
    `;
}

function renderRankList(items, labelFormatter) {
    if (!items?.length) {
        return `<div class="rank-list__empty">暂无数据</div>`;
    }

    const maxValue = items[0].value || 1;
    return items
        .map((item) => {
            const width = Math.max(8, (item.value / maxValue) * 100);
            return `
                <div class="rank-item">
                    <div class="rank-item__row">
                        <span class="rank-item__label">${escapeHtml(labelFormatter(item.name))}</span>
                        <strong>${formatNumber.format(item.value)}</strong>
                    </div>
                    <div class="rank-bar"><span style="width:${width}%"></span></div>
                </div>
            `;
        })
        .join("");
}

function renderRegionList(items) {
    if (!items?.length) {
        return `<div class="rank-list__empty">暂无数据</div>`;
    }

    const maxValue = items[0].players || 1;
    return items
        .map((item) => {
            const width = Math.max(10, (item.players / maxValue) * 100);
            return `
                <div class="region-item">
                    <div class="region-item__row">
                        <span class="region-item__label">${escapeHtml(item.name)}</span>
                        <strong>${formatNumber.format(item.players)} / ${formatNumber.format(item.servers)}</strong>
                    </div>
                    <div class="region-bar"><span style="width:${width}%"></span></div>
                </div>
            `;
        })
        .join("");
}

async function handlePlayerSubmit(event) {
    event.preventDefault();
    const formData = new FormData(refs.playerForm);
    const query = String(formData.get("query") || "").trim();
    const platform = String(formData.get("platform") || "pc");

    if (!query) {
        showNotice("请输入玩家名或 personaId。");
        return;
    }

    hideNotice();
    setLoading(true, "正在拉取玩家战绩...");

    try {
        const payload = await requestJson("/api/player", {
            method: "POST",
            body: JSON.stringify({ query, platform }),
        });
        renderPlayerResult(payload);
    } catch (error) {
        showNotice(error.message);
    } finally {
        setLoading(false);
    }
}

async function handleServerSubmit(event) {
    event.preventDefault();
    const formData = new FormData(refs.serverForm);
    const query = String(formData.get("query") || "").trim();
    const platform = String(formData.get("platform") || "pc");
    const region = String(formData.get("region") || "all");
    const limit = Number(formData.get("limit") || 20);

    if (!query) {
        showNotice("请输入服务器名称。");
        return;
    }

    hideNotice();
    setLoading(true, "正在搜索服务器...");

    try {
        const payload = await requestJson("/api/servers", {
            method: "POST",
            body: JSON.stringify({ query, platform, region, limit }),
        });
        renderServerSearch(payload);
    } catch (error) {
        showNotice(error.message);
    } finally {
        setLoading(false);
    }
}

function bfbanPill(bfban) {
    const isDanger = Boolean(bfban?.hacker);
    const cssClass = isDanger ? "pill pill--danger" : "pill pill--ok";
    const label = bfban?.statusLabel || "无记录";
    const details = bfban?.cheatMethods ? ` · ${bfban.cheatMethods}` : "";
    const content = escapeHtml(`${label}${details}`);

    if (bfban?.url) {
        return `<a class="${cssClass} status-link" href="${escapeHtml(bfban.url)}" target="_blank" rel="noreferrer">${content}</a>`;
    }

    return `<span class="${cssClass}">${content}</span>`;
}

function renderPlayerResult(data) {
    const profile = data.profile;
    setResultHeader(
        `${profile.name} · ${platformLabels[data.platform] || data.platform}`,
        `更新于 ${formatTimestamp(data.updatedAt)} · 最佳兵种 ${profile.bestClass} · 游戏时长 ${profile.timePlayed}`,
    );

    refs.results.innerHTML = `
        <div class="stack">
            <article class="profile-card">
                <div class="profile-card__avatar">
                    ${profile.avatar ? `<img src="${escapeHtml(profile.avatar)}" alt="${escapeHtml(profile.name)}">` : ""}
                </div>
                <div>
                    <div class="profile-card__header">
                        <div>
                            <h3>${escapeHtml(profile.name)}</h3>
                            <div class="profile-meta">
                                <span class="pill">等级 ${formatValue(profile.rank)}</span>
                                <span class="pill">平台 ${escapeHtml(platformLabels[data.platform] || data.platform)}</span>
                                <span class="pill">personaId ${escapeHtml(profile.personaId || "--")}</span>
                                <span class="pill">userId ${escapeHtml(profile.userId || "--")}</span>
                            </div>
                        </div>
                        <div>${bfbanPill(data.bfban)}</div>
                    </div>
                    <div class="profile-meta">
                        <span class="pill">最长爆头 ${formatValue(profile.longestHeadShot)}m</span>
                        <span class="pill">最高连杀 ${formatValue(profile.highestKillStreak)}</span>
                        <span class="pill">总对局 ${formatValue(profile.roundsPlayed)}</span>
                        <span class="pill">救人 ${formatValue(profile.revives)}</span>
                        <span class="pill">助攻 ${formatValue(profile.killAssists)}</span>
                    </div>
                </div>
            </article>

            <div class="stats-grid">
                ${data.highlights
                    .map(
                        (item) => `
                            <article class="stats-card">
                                <p>${escapeHtml(item.label)}</p>
                                <strong>${escapeHtml(formatValue(item.value))}</strong>
                            </article>
                        `,
                    )
                    .join("")}
            </div>

            <div class="micro-grid">
                ${renderMiniSection("武器表现", data.topWeapons, (item) => `
                    <div class="mini-item__meta">${escapeHtml(item.type)} · 命中率 ${escapeHtml(item.accuracy)} · 使用 ${escapeHtml(formatValue(item.timeHours))} 小时</div>
                `)}
                ${renderMiniSection("载具表现", data.topVehicles, (item) => `
                    <div class="mini-item__meta">${escapeHtml(item.type)} · 摧毁 ${formatValue(item.destroyed)} · 使用 ${escapeHtml(formatValue(item.timeHours))} 小时</div>
                `)}
            </div>

            <article class="micro-card">
                <div class="micro-card__title">
                    <h3>兵种投入</h3>
                    <span>${data.classes.length} 个兵种</span>
                </div>
                <div class="class-grid">
                    ${data.topClasses
                        .map(
                            (item) => `
                                <article class="class-card">
                                    <div>${item.image ? `<img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}">` : ""}</div>
                                    <div>
                                        <h4>${escapeHtml(item.name)}</h4>
                                        <p>${escapeHtml(item.timePlayed)} · ${formatValue(item.kills)} 击杀</p>
                                    </div>
                                    <div class="class-card__stats">
                                        <span>得分 ${formatValue(item.score)}</span>
                                        <span>KPM ${formatValue(item.kpm)}</span>
                                    </div>
                                </article>
                            `,
                        )
                        .join("")}
                </div>
            </article>

            ${renderDetailsTable("完整武器列表", [
                "名称",
                "类型",
                "击杀",
                "KPM",
                "爆头率",
                "命中率",
                "使用时长",
            ], data.weapons.map((item) => [
                item.name,
                item.type,
                formatValue(item.kills),
                formatValue(item.kpm),
                item.headshotRate,
                item.accuracy,
                `${formatValue(item.timeHours)} 小时`,
            ]))}

            ${renderDetailsTable("完整载具列表", [
                "名称",
                "类型",
                "击杀",
                "KPM",
                "摧毁",
                "使用时长",
            ], data.vehicles.map((item) => [
                item.name,
                item.type,
                formatValue(item.kills),
                formatValue(item.kpm),
                formatValue(item.destroyed),
                `${formatValue(item.timeHours)} 小时`,
            ]))}

            ${renderDetailsTable("完整兵种列表", [
                "兵种",
                "得分",
                "击杀",
                "KPM",
                "时长",
            ], data.classes.map((item) => [
                item.name,
                formatValue(item.score),
                formatValue(item.kills),
                formatValue(item.kpm),
                item.timePlayed,
            ]))}
        </div>
    `;
}

function renderMiniSection(title, items, metaRenderer) {
    return `
        <article class="micro-card">
            <div class="micro-card__title">
                <h3>${title}</h3>
                <span>${items.length} 项亮点</span>
            </div>
            <div class="mini-list">
                ${items.length
                    ? items
                          .map(
                              (item) => `
                                <div class="mini-item">
                                    <div>
                                        <div class="mini-item__name">${escapeHtml(item.name)}</div>
                                        ${metaRenderer(item)}
                                    </div>
                                    <div class="mini-item__value">${formatValue(item.kills)}</div>
                                </div>
                            `,
                          )
                          .join("")
                    : `<div class="rank-list__empty">暂无有效数据</div>`}
            </div>
        </article>
    `;
}

function renderDetailsTable(title, headers, rows) {
    return `
        <details class="details-card">
            <summary>${title}</summary>
            <div class="details-card__body">
                <div class="table-wrap">
                    <table class="data-table">
                        <thead>
                            <tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr>
                        </thead>
                        <tbody>
                            ${rows.length
                                ? rows
                                      .map(
                                          (row) => `
                                        <tr>
                                            ${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}
                                        </tr>
                                    `,
                                      )
                                      .join("")
                                : `<tr><td colspan="${headers.length}">暂无数据</td></tr>`}
                        </tbody>
                    </table>
                </div>
            </div>
        </details>
    `;
}

function renderServerSearch(data) {
    state.lastServerSearch = data.servers;
    state.lastServerMeta = {
        title: `找到 ${data.servers.length} 个服务器`,
        subtitle: `${platformLabels[data.platform] || data.platform} · ${regionLabels[data.region] || data.region} · 更新于 ${formatTimestamp(data.updatedAt)}`,
    };

    setResultHeader(state.lastServerMeta.title, state.lastServerMeta.subtitle);

    if (!data.servers.length) {
        refs.results.innerHTML = `
            <div class="empty-state">
                <h3>没有匹配到服务器</h3>
                <p>可以换一个更短的关键字，或者切换平台与地区后重试。</p>
            </div>
        `;
        return;
    }

    refs.results.innerHTML = `
        <div class="server-grid">
            ${data.servers.map(renderServerCard).join("")}
        </div>
    `;
    bindResultActions();
}

function renderServerCard(server) {
    const background = server.image
        ? `style="background-image:url('${escapeHtml(server.image)}')"`
        : "";

    return `
        <article class="server-card" ${background}>
            <div>
                <div class="server-card__top">
                    <span class="pill">${server.official ? "官服" : server.custom ? "社区服" : "服务器"}</span>
                    <span class="pill">${escapeHtml(platformLabels[server.platform] || server.platform)}</span>
                </div>
                <h3 class="server-card__name">${escapeHtml(server.name)}</h3>
                <p class="server-card__desc">${escapeHtml(server.description || "未提供描述")}</p>

                <div class="server-card__meta">
                    <div><span>地图 / 模式</span><strong>${escapeHtml(translateMap(server.map))} / ${escapeHtml(translateMode(server.mode))}</strong></div>
                    <div><span>地区 / 国家</span><strong>${escapeHtml(server.region)} / ${escapeHtml(server.country)}</strong></div>
                    <div><span>玩家</span><strong>${escapeHtml(server.serverInfo)}</strong></div>
                    <div><span>排队 / 观战</span><strong>${formatValue(server.queue)} / ${formatValue(server.spectators)}</strong></div>
                </div>

                <div class="occupancy">
                    <div class="occupancy__row">
                        <span>上座率</span>
                        <strong>${formatValue(server.occupancy)}%</strong>
                    </div>
                    <div class="occupancy__bar"><span style="width:${Math.max(6, server.occupancy)}%"></span></div>
                </div>
            </div>

            <button
                class="primary-button"
                type="button"
                data-action="open-server"
                data-game-id="${escapeHtml(server.gameId)}"
                data-platform="${escapeHtml(server.platform)}"
                data-name="${escapeHtml(server.name)}"
                data-map="${escapeHtml(server.map)}"
                data-mode="${escapeHtml(server.mode)}"
                data-region="${escapeHtml(server.region)}"
                data-country="${escapeHtml(server.country)}"
                data-image="${escapeHtml(server.image || "")}"
            >
                查看玩家列表
            </button>
        </article>
    `;
}

async function openServerPlayers(button) {
    const gameId = button.dataset.gameId;
    const platform = button.dataset.platform;
    const context = {
        name: button.dataset.name,
        map: button.dataset.map,
        mode: button.dataset.mode,
        region: button.dataset.region,
        country: button.dataset.country,
        image: button.dataset.image,
    };

    setLoading(true, "正在拉取服务器玩家列表...");
    hideNotice();

    try {
        const payload = await requestJson(`/api/server-players?gameId=${encodeURIComponent(gameId)}&platform=${encodeURIComponent(platform)}`);
        renderServerPlayers(payload, context);
    } catch (error) {
        showNotice(error.message);
    } finally {
        setLoading(false);
    }
}

function renderServerPlayers(data, context) {
    setResultHeader(
        `${context.name} · 玩家列表`,
        `更新于 ${formatTimestamp(data.updatedAt)} · ${translateMap(context.map)} / ${translateMode(context.mode)} · ${context.region}`,
    );

    refs.results.innerHTML = `
        <div class="stack">
            <div class="server-toolbar">
                <button type="button" class="secondary-button" data-action="back-server-results">返回服务器列表</button>
            </div>

            <div class="server-summary">
                <article class="server-card" ${context.image ? `style="background-image:url('${escapeHtml(context.image)}')"` : ""}>
                    <div>
                        <div class="server-card__top">
                            <span class="pill">${escapeHtml(platformLabels[data.platform] || data.platform)}</span>
                            <span class="pill">${escapeHtml(data.server.serverType || "RANKED")}</span>
                        </div>
                        <h3 class="server-card__name">${escapeHtml(context.name || data.server.name)}</h3>
                        <p class="server-card__desc">${escapeHtml(data.server.description || "未提供描述")}</p>
                        <div class="server-card__meta">
                            <div><span>地图 / 模式</span><strong>${escapeHtml(translateMap(context.map || data.server.map))} / ${escapeHtml(translateMode(context.mode || data.server.mode))}</strong></div>
                            <div><span>地区 / 国家</span><strong>${escapeHtml(context.region || data.server.region)} / ${escapeHtml(context.country || data.server.country)}</strong></div>
                        </div>
                    </div>
                </article>

                <div class="stats-grid">
                    ${renderSummaryCard("在场玩家", data.summary.players)}
                    ${renderSummaryCard("排队人数", data.summary.queue)}
                    ${renderSummaryCard("加载中", data.summary.loading)}
                    ${renderSummaryCard("队伍数", data.summary.teams)}
                </div>
            </div>

            ${data.teams.map((team) => renderTeamTable(team, data.platform)).join("")}
            ${data.loading.length ? renderQueueTable("加载中", data.loading, data.platform) : ""}
            ${data.queue.length ? renderQueueTable("排队中", data.queue, data.platform) : ""}
        </div>
    `;
    bindResultActions();
}

function renderSummaryCard(label, value) {
    return `
        <article class="stats-card">
            <p>${escapeHtml(label)}</p>
            <strong>${formatValue(value)}</strong>
        </article>
    `;
}

function renderTeamTable(team, platform) {
    return `
        <details class="details-card" open>
            <summary>${escapeHtml(team.name)} · ${team.players.length} 人</summary>
            <div class="details-card__body">
                <div class="table-wrap">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>排名</th>
                                <th>玩家</th>
                                <th>BFBAN</th>
                                <th>延迟</th>
                                <th>小队</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${team.players
                                .map(
                                    (player) => `
                                        <tr>
                                            <td>${formatValue(player.rank)}</td>
                                            <td>
                                                <button
                                                    type="button"
                                                    class="player-link"
                                                    data-action="search-player"
                                                    data-query="${escapeHtml(player.name)}"
                                                    data-platform="${escapeHtml(platform)}"
                                                >
                                                    ${escapeHtml(player.name)}
                                                </button>
                                            </td>
                                            <td>${bfbanPill(player.bfban)}</td>
                                            <td>${formatValue(player.latency)} ms</td>
                                            <td>${escapeHtml(player.platoon || "-")}</td>
                                        </tr>
                                    `,
                                )
                                .join("")}
                        </tbody>
                    </table>
                </div>
            </div>
        </details>
    `;
}

function renderQueueTable(title, rows, platform) {
    return `
        <details class="details-card" open>
            <summary>${escapeHtml(title)} · ${rows.length} 人</summary>
            <div class="details-card__body">
                <div class="table-wrap">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>玩家</th>
                                <th>BFBAN</th>
                                <th>延迟</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows
                                .map(
                                    (player) => `
                                        <tr>
                                            <td>
                                                <button
                                                    type="button"
                                                    class="player-link"
                                                    data-action="search-player"
                                                    data-query="${escapeHtml(player.name)}"
                                                    data-platform="${escapeHtml(platform)}"
                                                >
                                                    ${escapeHtml(player.name)}
                                                </button>
                                            </td>
                                            <td>${bfbanPill(player.bfban)}</td>
                                            <td>${formatValue(player.latency)} ms</td>
                                        </tr>
                                    `,
                                )
                                .join("")}
                        </tbody>
                    </table>
                </div>
            </div>
        </details>
    `;
}

function bindResultActions() {
    document.querySelectorAll('[data-action="open-server"]').forEach((button) => {
        button.addEventListener("click", () => openServerPlayers(button));
    });

    document.querySelectorAll('[data-action="search-player"]').forEach((button) => {
        button.addEventListener("click", () => {
            const query = button.dataset.query;
            const platform = button.dataset.platform || "pc";
            switchView("player");
            refs.playerForm.querySelector('[name="query"]').value = query;
            refs.playerForm.querySelector('[name="platform"]').value = platform;
            refs.playerForm.requestSubmit();
        });
    });

    document.querySelectorAll('[data-action="back-server-results"]').forEach((button) => {
        button.addEventListener("click", () => {
            if (!state.lastServerSearch?.length) {
                return;
            }
            setResultHeader(state.lastServerMeta.title, state.lastServerMeta.subtitle);
            refs.results.innerHTML = `<div class="server-grid">${state.lastServerSearch.map(renderServerCard).join("")}</div>`;
            bindResultActions();
        });
    });
}
