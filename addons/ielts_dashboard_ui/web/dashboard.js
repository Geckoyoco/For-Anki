(() => {
  let headerTimeTimer = null;

  function numberFrom(element) {
    if (!element) return 0;
    return Number(element.textContent.replace(/[^\d]/g, "")) || 0;
  }

  function updateHeaderTime(dashboard) {
    const dateElement = dashboard.querySelector(".ielts-time-block__date");
    const timeElement = dashboard.querySelector(".ielts-time-block__time");
    if (!dateElement || !timeElement) return;

    const now = new Date();
    const monthDay = new Intl.DateTimeFormat("zh-CN", {
      month: "long",
      day: "numeric",
    }).format(now);
    const weekday = new Intl.DateTimeFormat("zh-CN", {
      weekday: "long",
    }).format(now);
    dateElement.textContent = `${monthDay} ${weekday}`;
    timeElement.textContent = new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(now);
  }

  function startHeaderClock(dashboard) {
    if (headerTimeTimer) {
      clearInterval(headerTimeTimer);
    }
    updateHeaderTime(dashboard);
    headerTimeTimer = setInterval(() => updateHeaderTime(dashboard), 60000);
  }

  function isTopLevelRow(row) {
    const deckCell = row.querySelector(".decktd");
    if (!deckCell) return false;
    return !deckCell.innerHTML.trimStart().startsWith("&nbsp;");
  }

  function metric(label, value, tone, action = "") {
    const interactive = action
      ? ` role="button" tabindex="0" data-action="${action}" title="查看今天学习的中英文"`
      : "";
    return `
      <div class="ielts-metric ielts-metric--${tone}"${interactive}>
        <span class="ielts-metric__label">${label}</span>
        <strong class="ielts-metric__value">${value}</strong>
      </div>
    `;
  }

  function enhanceDeckBrowser() {
    const table = document.querySelector("center > table");
    const host = table?.parentElement;

    if (!table || !host || document.querySelector(".ielts-dashboard")) {
      return;
    }

    document.body.classList.add("ielts-dashboard-home");
    table.classList.add("ielts-deck-table");

    const rows = [...table.querySelectorAll("tr.deck")];
    const tomorrowData = document.querySelector("#ielts-tomorrow-counts");
    let tomorrowCounts = {};
    try {
      tomorrowCounts = JSON.parse(tomorrowData?.textContent || "{}");
    } catch (_error) {
      tomorrowCounts = {};
    }

    const headerRow = [...table.querySelectorAll("tr")].find(
      (row) => !row.classList.contains("deck"),
    );
    if (headerRow && !headerRow.querySelector(".tomorrow-header")) {
      const tomorrowHeader = document.createElement("th");
      tomorrowHeader.className = "count tomorrow-header";
      tomorrowHeader.textContent = "明日复习";
      headerRow.insertBefore(tomorrowHeader, headerRow.lastElementChild);
    }

    rows.forEach((row) => {
      const optionsCell = row.querySelector("td.opts");
      if (!row.querySelector(".tomorrow-count")) {
        const tomorrowCell = document.createElement("td");
        tomorrowCell.className = "count tomorrow-count";
        tomorrowCell.setAttribute("align", "end");
        tomorrowCell.textContent = String(tomorrowCounts[row.id] || 0);
        row.insertBefore(tomorrowCell, optionsCell || null);
      }
    });
    const topLevelRows = rows.filter(isTopLevelRow);
    const summaryRows = topLevelRows.length ? topLevelRows : rows;

    const totals = summaryRows.reduce(
      (result, row) => {
        result.newCards += numberFrom(row.querySelector(".new-count"));
        result.learning += numberFrom(row.querySelector(".learn-count"));
        result.review += numberFrom(row.querySelector(".review-count"));
        return result;
      },
      { newCards: 0, learning: 0, review: 0 },
    );

    rows.forEach((row) => {
      const deckName = row.querySelector("a.deck")?.textContent.trim() || "";
      if (/^[【[]/.test(deckName)) {
        row.classList.add("ielts-primary-deck");
      }
    });

    const studiedToday = document.querySelector("#studiedToday");
    const todayAdded = numberFrom(
      document.querySelector("#ielts-today-added-count"),
    );
    const studiedText = (
      studiedToday?.textContent.trim() || "今天尚未开始学习"
    ).replace(/[\u200e\u200f\u2066-\u2069]/g, "");
    const completedMatch = studiedText.match(/学习了\s*(\d+)\s*张/);
    const minutesMatch = studiedText.match(/([\d.]+)\s*分(?:钟)?内/);
    const completed = completedMatch ? completedMatch[1] : "0";
    const minutes = minutesMatch ? `${minutesMatch[1]} 分钟` : "0 分钟";

    const dashboard = document.createElement("section");
    dashboard.className = "ielts-dashboard";
    dashboard.innerHTML = `
      <div class="ielts-dashboard__heading">
        <div class="ielts-dashboard__title">
          <h1>Memory Hub</h1>
        </div>
        <div class="ielts-time-block" aria-live="polite">
          <span class="ielts-time-block__date"></span>
          <strong class="ielts-time-block__time"></strong>
        </div>
      </div>
      <div class="ielts-dashboard__metrics">
        ${metric("今日完成", `${completed} 张`, "done", "open-today")}
        ${metric("学习时间", minutes, "time")}
        ${metric("新卡", totals.newCards, "new")}
        ${metric("待复习", totals.review, "review")}
        ${metric("今日新增", todayAdded, "added", "open-today-added")}
      </div>
    `;

    host.insertBefore(dashboard, table);
    startHeaderClock(dashboard);

    const openToday = () => pycmd("ielts:open-today");
    dashboard.querySelectorAll('[data-action="open-today"]').forEach((element) => {
      element.addEventListener("click", openToday);
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openToday();
        }
      });
    });

    const todayAddedMetric = dashboard.querySelector(
      '[data-action="open-today-added"]',
    );
    const openTodayAdded = () => pycmd("ielts:open-today-added");
    todayAddedMetric?.addEventListener("click", openTodayAdded);
    todayAddedMetric?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openTodayAdded();
      }
    });

    if (studiedToday) {
      studiedToday.classList.add("ielts-original-stats");
      studiedToday.setAttribute("title", studiedText);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      enhanceDeckBrowser();
    });
  } else {
    enhanceDeckBrowser();
  }
})();
