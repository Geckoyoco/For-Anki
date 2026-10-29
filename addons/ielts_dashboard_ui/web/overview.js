(() => {
  function count(selector) {
    const element = document.querySelector(selector);
    return Number(element?.textContent.replace(/[^\d]/g, "")) || 0;
  }

  function metric(label, value, tone, action = "") {
    const interactive = action
      ? ` role="button" tabindex="0" data-action="${action}" title="查看${label}的中英文列表"`
      : "";
    return `
      <div class="ielts-overview-metric ielts-overview-metric--${tone}"${interactive}>
        <span>${label}</span>
        <strong>${value}</strong>
      </div>
    `;
  }

  function enhanceOverview() {
    const host = document.querySelector("body > center");
    const heading = host?.querySelector("h3");
    const studyButton = host?.querySelector("#study");

    if (!host || !heading || document.querySelector(".ielts-overview") ||
        !document.querySelector("#ielts-total-words")) {
      return;
    }

    const completed = !studyButton;
    let completionContent = "";
    if (completed) {
      const notice = host.cloneNode(true);
      notice.querySelectorAll("h3, .description, [id^='ielts-'], script, style")
        .forEach((element) => element.remove());
      completionContent = notice.innerHTML.trim();
    }

    const deckName = heading.textContent.trim();
    const newCards = count(".new-count");
    const learning = count(".learn-count");
    const review = count(".review-count");
    const totalWords = count("#ielts-total-words");
    const learnedWords = count("#ielts-learned-words");
    const unseenWords = count("#ielts-unseen-words");
    const todayUnseenWords = count("#ielts-today-unseen-words");
    const learningWords = count("#ielts-learning-words");
    const consolidatingWords = count("#ielts-consolidating-words");
    const masteredWords = count("#ielts-mastered-words");
    const leechWords = count("#ielts-leech-words");
    const todayDone = count("#ielts-today-done");
    const todayTasks = newCards + learning + review;
    const progress = totalWords
      ? Math.min(100, Math.round((learnedWords / totalWords) * 100))
      : 0;
    const description = host.querySelector(".description")?.innerHTML.trim() || "";

    document.body.classList.add("ielts-overview-home");

    const overview = document.createElement("main");
    overview.className = "ielts-overview";
    overview.innerHTML = `
      <header class="ielts-overview__heading">
        <div>
          <div class="ielts-overview__eyebrow">CURRENT DECK</div>
          <h1>${deckName}</h1>
          <p>${completed ? "今日学习已完成，查看这个牌组的学习情况。" : "查看今天的任务，然后开始学习。"}</p>
        </div>
        <button class="ielts-overview__back" type="button" title="返回牌组">返回牌组</button>
      </header>

      <section class="ielts-overview__metrics" aria-label="牌组进度">
        ${metric("总词数", totalWords, "total")}
        ${metric("未学习", unseenWords, "new", "unseen")}
        ${metric("今日未学习", todayUnseenWords, "new", "today-unseen")}
        ${metric("学习中", learningWords, "learning", "learning")}
        ${metric("巩固中", consolidatingWords, "consolidating", "consolidating")}
        ${metric("已掌握", masteredWords, "mastered", "mastered")}
        ${metric("顽固词汇", leechWords, "leech", "leech")}
        ${metric("今日完成", todayDone, "done", "open-today")}
      </section>

      <section class="ielts-overview__progress" aria-label="总体进度">
        <div class="ielts-overview__progress-copy">
          <span>学习进度</span>
          <strong id="export-learned-words" role="button" tabindex="0" title="导出已学单词与累计学习次数（Excel）">${learnedWords} / ${totalWords}</strong>
        </div>
        <div class="ielts-overview__progress-track">
          ${[
            ["mastered", "已掌握", masteredWords],
            ["consolidating", "巩固中", consolidatingWords],
            ["learning", "学习中", learningWords],
            ["unseen", "未学习", unseenWords],
          ].map(([state, label, value]) => `<span
            class="ielts-overview__progress-segment--${state}"
            style="width: ${totalWords ? (value / totalWords) * 100 : 0}%"
            title="${label}：${value}" aria-label="${label}：${value}"></span>`).join("")}
        </div>
        <b>${progress}%</b>
      </section>

      <section class="ielts-overview__action">
        <div>
          <span>今日任务</span>
          <strong>
            今日已学习 ${todayDone} 个单词
            <i aria-hidden="true"></i>
            ${completed ? "今日学习已完成" : todayTasks ? `当前待处理 ${todayTasks} 张卡片` : "当前任务已完成"}
          </strong>
        </div>
        ${completed ? "" : `<button id="study" class="ielts-overview__study" type="button">
          开始学习
        </button>`}
      </section>

      ${completionContent ? `<section class="ielts-overview__description">${completionContent}</section>` : ""}

      ${
        description
          ? `<section class="ielts-overview__description">${description}</section>`
          : ""
      }
    `;

    host.replaceChildren(overview);
    overview.querySelector("#study")?.addEventListener("click", () => pycmd("study"));
    const exportCount = overview.querySelector("#export-learned-words");
    exportCount?.addEventListener("click", () => pycmd("ielts:export-learned-words"));
    exportCount?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        pycmd("ielts:export-learned-words");
      }
    });
    overview
      .querySelector(".ielts-overview__back")
      ?.addEventListener("click", () => pycmd("decks"));

    overview.querySelectorAll("[data-action]").forEach((element) => {
      const openList = () => {
        const action = element.dataset.action;
        pycmd(action === "open-today"
          ? "ielts:open-current-deck-today"
          : `ielts:open-word-group:${action}`);
      };
      element.addEventListener("click", openList);
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openList();
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceOverview, { once: true });
  } else {
    enhanceOverview();
  }
})();
