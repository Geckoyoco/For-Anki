# For Anki

本仓库保存 Anki 定制插件源码、交接文档和可复用的交接 skill，供 fork 和后续修改。当前本机 Anki 版本为 26.09.2。

- [`任务交接.md`](任务交接.md)：历史背景与 2026-10-29 增量。
- [`anki-handoff-skill/SKILL.md`](anki-handoff-skill/SKILL.md)：接手和迭代流程；最新核查在 `references/current-state.md`。
- [`addons/ielts_dashboard_ui`](addons/ielts_dashboard_ui)：本机仪表盘插件当前源码。
- [`addons/1898790263`](addons/1898790263)：Contanki 1.0.2 的本机源码副本，原项目 [roxgib/anki-contanki](https://github.com/roxgib/anki-contanki)，遵循目录内 AGPL-3.0 许可证。本机修改以当前文件为准。
- [`scripts/package_anki_mac_2026-10-04.py`](scripts/package_anki_mac_2026-10-04.py)：旧迁移脚本留档，硬编码旧日期和本机路径，并依赖旧临时文件；**不可直接运行**。

本仓库不含 Anki 集合、学习记录、媒体、登录凭据、迁移包及 Contanki 的 `user_files` 个人配置。Contanki 的 `buttons/` 图片资源也未上传；如需独立安装 Contanki，请从上游项目获取对应版本资源。任何新电脑安装或迁移都必须先核对目标环境，不能把本仓库当成完整迁移包。
