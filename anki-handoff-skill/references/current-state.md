# Anki 当前交接（2026-10-29 核查）

## 范围与来源

旧交接见 `/Users/gecko/Documents/ChatGPT/Engineer/任务交接.md`（2026-10-06），本文件只记录此后已核对的增量和关键约束。原文中的历史计数、旧迁移包和未验收项仍需按时间解读。当前 Anki 实际版本由应用命令返回 `26.09.2`。

## 当前路径

- 集合：`/Users/gecko/Library/Application Support/Anki2/账户 1/collection.anki2`
- 仪表盘插件：`/Users/gecko/Library/Application Support/Anki2/addons21/ielts_dashboard_ui/`
- Contanki：`/Users/gecko/Library/Application Support/Anki2/addons21/1898790263/`
- 迁移脚本：`/Users/gecko/Documents/ChatGPT/Engineer/package_anki_mac.py`；仍硬编码 2026-10-04 输出，并依赖旧 `/tmp/anki-dedupe-20261002/export_decks.py`，不可直接运行。
- 旧迁移包：`/Users/gecko/Documents/ChatGPT/Engineer/Anki_Mac迁移包_2026-10-04.zip`，不含之后更新。

## 已核对的当前实现

- 仪表盘 `__init__.py` 仍有学习日修正 `anki_study_day`、年度学习时长图 `show_study_time`、完成页 `Overview._show_finished_screen` 覆盖、单词分组明细及 `leech` 顽固词汇。
- `web/overview.js` 的学习进度数字有点击与键盘导出入口；Python 消息 `ielts:export-learned-words` 从当前牌组（含子牌组）取 `reps>0` 的笔记，导出英文、中文、累计学习次数。此路径代码已安装，未做真实 UI 点击验收。
- 明细窗口的“导出 Excel”在 2026-10-29 修为纵向单词行；有“学习次数”的表取英文、中文、累计学习次数三列。此前多组横排导出是另一入口。用户随后确认问题均已解决。
- Contanki 当前 `dualsense` 文件：答案态叉 Good、圆 Good、方 Again、三角 Easy、上/下 Hard、左 Again、右 Good；可用键盘/手柄修改并保存是否可靠，尚未真实复验。不要据旧文档覆盖当前映射。
- 2026-10-18 备份显示有卡片模板改动，包括中英模板恢复和字体/换行调整。当前集合模型/字段/例句是否已应用未核实，不能照旧 HTML 盲写。

## 仍有效的用户要求

导航：牌组、添加、浏览、学习总览、学习时长、遗忘曲线、同步，隐藏统计入口。学习总览独立、淡色指标，完成或达限额后仍可查看牌组统计。明细：英文、中文、累计学习次数、今日学习次数、所属牌组。学习时长只要深色蓝格的年度每日热力图，悬停日期、H:MM:SS、作答次数，跟随 Anki 学习日，超过一小时单独色阶。遗忘曲线是历史真实作答间隔回忆率。背面中文下例句空值隐藏，先核实实际字段与模板。手柄映射先读当前配置，保留用户修改和保存能力。

## 核查记录

- 用户于 2026-10-29 明确确认此前问题均已解决。真实 Anki UI 核查确认当前 PTE 完成页仍显示自定义统计、导航顺序正确、学习进度数字显示导出入口；页面显示 933/6533。这是观察时的值，不作长期固定计数。
- 集合只读连接曾遇到 `database is locked`；Anki 当时运行中，尊重集合锁，不把它记为未完成的产品功能。历史 PTE ID 为 `1790868297127`，实际操作时仍应重新核实。
- 不得公开上传集合、学习记录、手柄配置、凭据、迁移包；公开交接只含必要路径与行为说明。
