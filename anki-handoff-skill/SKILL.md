---
name: anki-handoff
description: Maintain this user's macOS Anki customization, verify current state, update the handoff, and prepare migration only when requested.
---

# Anki 定制与交接

先读 [当前交接](references/current-state.md)，再检查本机实际版本、集合、插件源码、模板和配置。交接文档是上次核查结果，不是当前真值；保留用户后来修改的内容。

仅执行本次用户授权的范围。修改集合、模板或删除前备份；Anki 运行时不以裸 SQL 写集合，不默认强制退出；不恢复全库英文自动去重。区分已修改、静态检查、模拟测试、真实 Anki UI 验证。迁移时先读 `package_anki_mac.py`，换新输出目录，正常退出 Anki 后通过 Anki API 导出并核查；目标电脑不覆盖其他数据、不复制凭据、不自动确认全量同步。

每次完成 Anki 相关变更后，同步更新本 skill 的 `references/current-state.md`，记录日期、改动文件、具体行为、验证等级、未确认事项。若 GitHub 仓库已经确定且本次授权包含发布，再将更新提交到该仓库；不要猜测仓库。
