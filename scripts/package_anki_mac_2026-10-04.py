import hashlib
import json
import sqlite3
import tempfile
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

ROOT = Path('/Users/gecko/Documents/ChatGPT/Engineer')
DEST = ROOT / 'Anki_Mac迁移包_2026-10-04'
ADDONS = Path.home() / 'Library/Application Support/Anki2/addons21'

for _ in range(60):
    if subprocess.run(['pgrep', '-x', 'Anki'], capture_output=True).returncode != 0:
        break
    time.sleep(1)
else:
    raise RuntimeError('Anki is still running; no export performed')

DEST.mkdir(exist_ok=False)
source = Path('/tmp/anki-dedupe-20261002/export_decks.py').read_text()
source = source.replace("DEST = Path('/Users/gecko/Documents/ChatGPT/Engineer/Anki牌组导出_2026-10-02')", 'DEST = Path(' + repr(str(DEST)) + ')')
start = source.index('TARGETS = [')
end = source.index('\n\nif subprocess', start)
source = source[:start] + "TARGETS = [(1790868297127, '🌸 00｜PTE_词汇')]" + source[end:]
exec(compile(source, 'verified_deck_export', 'exec'), {})

from anki.collection import Collection
col = Collection(str(Path.home() / 'Library/Application Support/Anki2/账户 1/collection.anki2'))
try:
    package = next(DEST.glob('*.apkg'))
    with zipfile.ZipFile(package) as archive, tempfile.TemporaryDirectory() as folder:
        database = 'collection.anki21' if 'collection.anki21' in archive.namelist() else 'collection.anki2'
        archive.extract(database, folder)
        db = sqlite3.connect(str(Path(folder) / database))
        models = json.loads(db.execute('select models from col').fetchone()[0])
        template_report = []
        for model_id, model in models.items():
            original = col.models.get(int(model_id))
            assert original is not None
            assert model['css'] == original['css']
            assert [(t['name'], t['qfmt'], t['afmt']) for t in model['tmpls']] == [(t['name'], t['qfmt'], t['afmt']) for t in original['tmpls']]
            template_report.append({'name': model['name'], 'templates': len(model['tmpls']), 'verified': True})
        db.close()
        (DEST / '模板核查.json').write_text(json.dumps(template_report, ensure_ascii=False, indent=2), encoding='utf-8')
finally:
    col.close()

for name in ['1898790263', 'ielts_dashboard_ui']:
    shutil.copytree(ADDONS / name, DEST / '插件' / name,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))

guide = '''# Mac Anki 迁移

包含当前两个插件及配置、PTE 词汇牌组（学习记录、调度、模板、牌组设置和媒体）。不包含其他牌组、AnkiWeb 登录信息或整机偏好。源电脑 Anki 版本为 26.9.2；目标电脑建议使用同版本。

1. 在另一台 Mac 安装并打开 Anki 一次，然后完全退出 Anki。若已有重要内容，先导出备份；建议新建独立用户配置导入，避免与已有同名牌组混合。
2. Finder 按 Command+Shift+G，输入 ~/Library/Application Support/Anki2/addons21/ 。把本包“插件”文件夹内的 1898790263 和 ielts_dashboard_ui 两个文件夹放进去。若有同名插件，先把旧文件夹移到别处备份，再放入本包版本；不要合并文件夹。
3. 打开 Anki，双击本包 PTE .apkg 文件，或使用“文件 → 导入”。若出现“导入学习进度/学习记录/调度信息”选项，请保留开启。此文件只包含 PTE 牌组，模板和媒体随包导入。
4. 连接 DualSense 手柄，检查“工具 → Contanki”中的配置；本包保留当前手柄按键绑定。回答页三角为 Easy、圆圈为 Good。首次连接可能需要按一下手柄按键。已修复同名备份导致 Save 覆盖按键的问题。
5. 首页应出现 Memory Hub；顶部顺序为牌组、添加、浏览、学习总览、学习时长、遗忘曲线、同步，统计入口隐藏。学习总览为低饱和度配色；单词列表列顺序为英文、中文、学习次数、所属牌组。学习时长为粉色年度热力图，超过一小时使用最深色，悬停显示时:分:秒；下方不再显示列表。牌组完成今日学习后仍显示统计及可点击的单词列表。

插件不能随 .apkg 自动安装，需要完成第 2 步。在目标 Mac 上尚未实机验证，不承诺不同 Anki/macOS 版本完全一致。本包是迁移时点的快照，不会自动同步两台电脑后续的学习记录。
'''
(DEST / '安装说明.md').write_text(guide, encoding='utf-8')
prompt = '''请直接在这台 Mac 上完成 Anki 迁移安装，不要只给教程。
找到并解压 Anki_Mac迁移包_2026-10-04.zip，先阅读安装说明.md、导出核查.json、模板核查.json，并核对 SHA256.json。
检查 Anki 版本，源版本为26.9.2。先备份目标电脑已有重要数据；遇到已有同名牌组或插件冲突，问我，不擅自覆盖。
完全退出 Anki，把插件目录内的1898790263和ielts_dashboard_ui安装至 ~/Library/Application Support/Anki2/addons21/，包含user_files和当前配置；已有同名插件先备份移出，不合并目录。
启动Anki，导入包内PTE .apkg，保留学习记录、调度和牌组设置。导入数量以导出核查.json为准，不使用旧包的数量。
核查模板样式和媒体正常；核查顶部入口顺序、学习总览、粉色学习时长热力图，以及完成学习后仍能查看牌组统计。
连接DualSense后检查按键，回答页三角Easy、圆圈Good，其余按包内配置，不自行重置。验证自己修改按键并Save后能保留，测试结束恢复原绑定。
不要更改AnkiWeb账户或同步设置，不上传数据；遇到全量同步或覆盖提示先问我。卡住时先检查，不直接强制退出。
最后简洁报告安装内容、导入数量、核查结果及未完成项。不能验证的明确说明。
'''
(DEST / '给另一台电脑AI的Prompt.txt').write_text(prompt, encoding='utf-8')
hashes = {str(p.relative_to(DEST)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in DEST.rglob('*') if p.is_file()}
(DEST / 'SHA256.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2), encoding='utf-8')
output = ROOT / (DEST.name + '.zip')
with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
    for path in DEST.rglob('*'):
        if path.is_file():
            archive.write(path, str(path.relative_to(ROOT)))
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    for name, digest in hashes.items():
        assert hashlib.sha256(archive.read(DEST.name + '/' + name)).hexdigest() == digest
print(json.dumps({'zip': str(output), 'bytes': output.stat().st_size,
                  'files': len(hashes), 'verified': True}, ensure_ascii=False))
