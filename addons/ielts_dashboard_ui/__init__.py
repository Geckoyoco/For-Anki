import html
from html.parser import HTMLParser
import json
import re
import os
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass

from aqt import gui_hooks, mw
from aqt.deckbrowser import DeckBrowser
from aqt.overview import Overview, OverviewBottomBar, OverviewContent
from aqt.reviewer import ReviewerBottomBar
from aqt.qt import (
    QAction,
    QAbstractItemView,
    QDialog,
    QComboBox,
    QColor,
    QFileDialog,
    QGridLayout,
    QStandardPaths,
    QHeaderView,
    QKeySequence,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
)
from aqt.utils import tooltip, showWarning


ADDON_PACKAGE = mw.addonManager.addonFromModule(__name__)
mw.addonManager.setWebExports(__name__, r"web/.*")
today_dialog = None
today_added_dialog = None
memory_curve_dialog = None
learning_overview_dialog = None
study_time_dialog = None


@dataclass(frozen=True)
class Bucket:
    label: str
    min_days: int
    max_days: int | None


MEMORY_CURVE_BUCKETS = [
    Bucket("不足 1 天", 0, 1),
    Bucket("1 至不足 4 天", 1, 4),
    Bucket("4 至不足 8 天", 4, 8),
    Bucket("8 至不足 15 天", 8, 15),
    Bucket("15 至不足 31 天", 15, 31),
    Bucket("31 至不足 91 天", 31, 91),
    Bucket("91 天及以上", 91, None),
]


def add_dashboard_assets(web_content, context):
    base = f"/_addons/{ADDON_PACKAGE}/web"
    if isinstance(context, DeckBrowser):
        web_content.css.append(f"{base}/dashboard.css")
        web_content.js.append(f"{base}/dashboard.js")
    elif isinstance(context, Overview):
        web_content.css.append(f"{base}/overview.css?v=20261025-leech")
        web_content.js.append(f"{base}/overview.js?v=20261025-leech")
    elif isinstance(context, OverviewBottomBar):
        web_content.css.append(f"{base}/overview-bottom.css")
    elif isinstance(context, ReviewerBottomBar):
        web_content.css.append(f"{base}/reviewer-bottom.css")


def overview_word_groups():
    deck_name = mw.col.decks.current()["name"].replace('"', '\\"')
    all_cards = [
        mw.col.get_card(card_id)
        for card_id in mw.col.find_cards(f'deck:"{deck_name}"')
    ]
    all_note_ids = {card.nid for card in all_cards}
    learned_note_ids = {card.nid for card in all_cards if card.reps > 0}
    cards_by_note = {}
    for card in all_cards:
        cards_by_note.setdefault(card.nid, []).append(card)
    mastered_note_ids = {
        note_id
        for note_id, cards in cards_by_note.items()
        if cards and all(card.reps > 0 and card.ivl >= 21 for card in cards)
    }
    learning_note_ids = {
        note_id
        for note_id, cards in cards_by_note.items()
        if note_id not in mastered_note_ids
        and any(card.reps > 0 and card.type in (1, 3) for card in cards)
    }
    consolidating_note_ids = (
        learned_note_ids - mastered_note_ids - learning_note_ids
    )
    unseen_note_ids = all_note_ids - learned_note_ids
    # Leech is a note tag; include suspended cards and count each note once.
    leech_note_ids = all_note_ids & set(
        mw.col.find_notes(f'deck:"{deck_name}" tag:leech')
    )
    today_note_ids = {
        mw.col.get_card(card_id).nid
        for card_id in mw.col.find_cards(f'deck:"{deck_name}" rated:1')
    }
    # The scheduler applies deck limits, ordering and sibling burying.
    # Reading this queue does not answer cards or advance their scheduling.
    queued = mw.col.sched.get_queued_cards(fetch_limit=max(1, len(all_cards)))
    scheduled_note_ids = {
        item.card.note_id for item in queued.cards
        if item.card.note_id in unseen_note_ids and item.card.reps == 0
    }
    groups = {
        "unseen": unseen_note_ids,
        "today-unseen": scheduled_note_ids - today_note_ids,
        "learning": learning_note_ids,
        "consolidating": consolidating_note_ids,
        "mastered": mastered_note_ids,
        "leech": leech_note_ids,
    }
    return cards_by_note, groups, learned_note_ids, today_note_ids


def add_overview_progress(overview, content):
    cards_by_note, groups, learned_note_ids, today_note_ids = overview_word_groups()
    stats = {
        "ielts-total-words": len(cards_by_note),
        "ielts-learned-words": len(learned_note_ids),
        "ielts-unseen-words": len(groups["unseen"]),
        "ielts-today-unseen-words": len(groups["today-unseen"]),
        "ielts-learning-words": len(groups["learning"]),
        "ielts-consolidating-words": len(groups["consolidating"]),
        "ielts-mastered-words": len(groups["mastered"]),
        "ielts-leech-words": len(groups["leech"]),
        "ielts-today-done": len(today_note_ids),
    }
    content.table += "".join(
        f'<span id="{element_id}" hidden>{value}</span>'
        for element_id, value in stats.items()
    )


def render_completed_overview(overview):
    # Anki's Svelte completion page bypasses overview_will_render_content.
    deck = overview.mw.col.decks.current()
    content = OverviewContent(
        deck=deck["name"],
        shareLink="",
        desc=overview._desc(deck),
        table=(
            '<p>今日计划内学习已完成。仍有未学习卡片时，可能已达今日学习上限。</p>'
            '<p><a href="studymore">自定义学习</a></p>'
        ),
    )
    gui_hooks.overview_will_render_content(overview, content)
    content.deck = html.escape(content.deck)
    overview.web.stdHtml(
        overview._body % content.__dict__,
        css=["css/overview.css"],
        js=["js/vendor/jquery.min.js"],
        context=overview,
    )


WORD_GROUP_LABELS = {
    "unseen": "未学习",
    "today-unseen": "今日未学习",
    "learning": "学习中",
    "consolidating": "巩固中",
    "mastered": "已掌握",
    "leech": "顽固词汇",
}


def open_word_group(group):
    label = WORD_GROUP_LABELS[group]
    deck_name = mw.col.decks.current()["name"]
    cards_by_note, groups, _, _ = overview_word_groups()
    entries = []
    # One row per note, matching the overview's existing word counts.
    for note_id in sorted(groups[group]):
        note = cards_by_note[note_id][0].note()
        english = plain_field(note.fields[0] if note.fields else "")
        chinese = chinese_translation(note.fields[1] if len(note.fields) > 1 else "")
        deck_names, repetitions, today_repetitions = note_learning_details(note_id)
        entries.append([english, chinese, today_repetitions, deck_names, repetitions])
    open_today_words(deck_name, entries_override=entries, group_label=label)


def add_tomorrow_review_counts(deck_browser, content):
    counts = {}
    for deck in mw.col.decks.all():
        deck_name = deck["name"].replace('"', '\\"')
        counts[str(deck["id"])] = len(
            mw.col.find_cards(f'deck:"{deck_name}" prop:due=1')
        )

    content.stats += (
        '<script id="ielts-tomorrow-counts" type="application/json">'
        f"{json.dumps(counts, separators=(',', ':'))}"
        "</script>"
        f'<span id="ielts-today-added-count" hidden>{len(mw.col.find_cards("added:1"))}</span>'
    )


def dashboard_word_groups():
    cards_by_note = {}
    for note_id, reps, card_type, interval in mw.col.db.all(
        "select nid, reps, type, ivl from cards"
    ):
        cards_by_note.setdefault(note_id, []).append((reps, card_type, interval))
    learned = {
        nid for nid, cards in cards_by_note.items() if any(reps > 0 for reps, _, _ in cards)
    }
    mastered = {
        nid for nid, cards in cards_by_note.items()
        if all(reps > 0 and interval >= 21 for reps, _, interval in cards)
    }
    learning = {
        nid for nid, cards in cards_by_note.items()
        if nid not in mastered and any(reps > 0 and kind in (1, 3) for reps, kind, _ in cards)
    }
    unseen = set(cards_by_note) - learned
    today = set(mw.col.find_notes("rated:1"))
    scheduled = set()
    selected_deck = mw.col.decks.current()["id"]
    # Read each root's scheduler queue, preserving the user's selected deck.
    try:
        for deck in mw.col.decks.all():
            if "::" in deck["name"]:
                continue
            mw.col.decks.select(deck["id"])
            queued = mw.col.sched.get_queued_cards(fetch_limit=max(1, len(cards_by_note)))
            scheduled.update(
                item.card.note_id for item in queued.cards
                if item.card.note_id in unseen and item.card.reps == 0
            )
    finally:
        mw.col.decks.select(selected_deck)
    return {
        "unseen": unseen,
        "today-unseen": scheduled - today,
        "learning": learning,
        "consolidating": learned - mastered - learning,
        "mastered": mastered,
    }, today


def note_learning_details(note_id):
    names = set()
    repetitions = 0
    for deck_id, original_deck_id, reps in mw.col.db.all(
        "select did, odid, reps from cards where nid = ?", note_id
    ):
        deck = mw.col.decks.get(original_deck_id or deck_id)
        if deck:
            names.add(deck["name"])
        repetitions += reps
    cutoff = mw.col.sched.day_cutoff
    if callable(cutoff):
        cutoff = cutoff()
    start = (datetime.fromtimestamp(cutoff) - timedelta(days=1)).timestamp()
    today_repetitions = mw.col.db.scalar(
        "select count(*) from revlog where cid in (select id from cards where nid = ?) "
        "and id >= ? and id < ? and ease between 1 and 4 and type in (0, 1, 2)",
        note_id, int(start * 1000), int(cutoff * 1000),
    )
    return "；".join(sorted(names)), repetitions, today_repetitions


def open_dashboard_word_group(group):
    groups, _ = dashboard_word_groups()
    entries = []
    for note_id in sorted(groups[group]):
        note = mw.col.get_note(note_id)
        english = plain_field(note.fields[0] if note.fields else "")
        chinese = chinese_translation(note.fields[1] if len(note.fields) > 1 else "")
        deck_names, repetitions, today_repetitions = note_learning_details(note_id)
        entries.append([english, chinese, today_repetitions, deck_names, repetitions])
    open_today_words("全部牌组", entries_override=entries, group_label=WORD_GROUP_LABELS[group])


def plain_field(value):
    value = re.sub(r"<br\s*/?>", " ", value or "", flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def chinese_translation(value):
    value = plain_field(value)
    english_definition = re.search(
        r"(?<=[\u3400-\u9fff；，。)])\s*"
        r"(?:n|v|vi|vt|adj|adv|prep|pron|conj|num|abbr)\.\s*(?=[A-Za-z])",
        value,
        flags=re.IGNORECASE,
    )
    if english_definition:
        value = value[: english_definition.start()]
    return value


def today_unique_entries(deck_name=None):
    unique_entries = {}
    day_cutoff = mw.col.sched.day_cutoff
    if callable(day_cutoff):
        day_cutoff = day_cutoff()
    day_start_ms = (day_cutoff - 86400) * 1000
    day_end_ms = day_cutoff * 1000
    search = "rated:1"
    if deck_name:
        escaped_deck_name = deck_name.replace('"', '\\"')
        search = f'deck:"{escaped_deck_name}" rated:1'

    for card_id in mw.col.find_cards(search):
        card = mw.col.get_card(card_id)
        note = card.note()
        english = plain_field(note.fields[0] if note.fields else "")
        chinese = chinese_translation(note.fields[1] if len(note.fields) > 1 else "")
        key = (english.casefold(), chinese.casefold())
        review_count = mw.col.db.scalar(
            "select count() from revlog where cid = ? and id >= ? and id < ?",
            card_id,
            day_start_ms,
            day_end_ms,
        )
        if english or chinese:
            if key in unique_entries:
                unique_entries[key][2] += review_count
            else:
                unique_entries[key] = [english, chinese, review_count]

    return list(unique_entries.values())


def today_added_entries():
    entries = []
    for card_id in mw.col.find_cards("added:1"):
        card = mw.col.get_card(card_id)
        note = card.note()
        deck = mw.col.decks.get(card.did)
        english = plain_field(note.fields[0] if note.fields else "")
        chinese = chinese_translation(note.fields[1] if len(note.fields) > 1 else "")
        if english or chinese:
            entries.append([deck["name"] if deck else "", english, chinese])
    return entries


def table_export_data(table):
    columns = [column for column in range(table.columnCount())
               if not table.isColumnHidden(column)]
    headers = [table.horizontalHeaderItem(column).text() for column in columns]
    rows = [
        [table.item(row, column).data(Qt.ItemDataRole.DisplayRole)
         if table.item(row, column) else "" for column in columns]
        for row in range(table.rowCount()) if not table.isRowHidden(row)
    ]
    return headers, rows


def printable_word_rows(headers, rows):
    """Four column pairs; read down each pair, then across, page by page."""
    if "英文单词" not in headers or "中文翻译" not in headers:
        return headers, rows, []
    english = headers.index("英文单词")
    chinese = headers.index("中文翻译")
    packed = []
    breaks = []
    # 13 rows x four pairs = 52 words per landscape A4 page.
    for start in range(0, len(rows), 52):
        page = rows[start:start + 52]
        height = (len(page) + 3) // 4
        for row_index in range(height):
            values = []
            for group in range(4):
                index = group * height + row_index
                values.extend([page[index][english], page[index][chinese]]
                              if index < len(page) else ["", ""])
            packed.append(values)
        if start + 52 < len(rows):
            breaks.append(len(packed) + 1)  # includes header row
    return ["英文单词", "中文翻译"] * 4, packed, breaks


def write_list_xlsx(path, headers, rows, *, vertical=False):
    """Write a real XLSX using only the standard library bundled with Anki."""
    headers, rows, print_breaks = (headers, rows, []) if vertical else printable_word_rows(headers, rows)
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    def tag(name):
        return "{" + ns + "}" + name
    def column_name(index):
        name = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            name = chr(65 + remainder) + name
        return name
    def xml(element):
        return ET.tostring(element, encoding="utf-8", xml_declaration=True)
    def clean_text(value):
        value = str(value if value is not None else "")
        return "".join(c for c in value if c in "\t\n\r" or
                       0x20 <= ord(c) <= 0xD7FF or
                       0xE000 <= ord(c) <= 0xFFFD or
                       0x10000 <= ord(c) <= 0x10FFFF)[:32767]

    sheet = ET.Element(tag("worksheet"))
    properties = ET.SubElement(sheet, tag("sheetPr"))
    ET.SubElement(properties, tag("pageSetUpPr"), fitToPage="1")
    last_cell = f"{column_name(len(headers))}{len(rows) + 1}"
    ET.SubElement(sheet, tag("dimension"), ref=f"A1:{last_cell}")
    views = ET.SubElement(sheet, tag("sheetViews"))
    view = ET.SubElement(views, tag("sheetView"), workbookViewId="0")
    ET.SubElement(view, tag("pane"), ySplit="1", topLeftCell="A2",
                  activePane="bottomLeft", state="frozen")
    cols = ET.SubElement(sheet, tag("cols"))
    for index, header in enumerate(headers, 1):
        width = 23 if "中文" in header else 18
        ET.SubElement(cols, tag("col"), min=str(index), max=str(index),
                      width=str(width), customWidth="1")
    data = ET.SubElement(sheet, tag("sheetData"))
    for row_number, values in enumerate([headers] + rows, 1):
        row = ET.SubElement(data, tag("row"), r=str(row_number),
                            ht="28" if row_number == 1 else "36", customHeight="1")
        for index, value in enumerate(values, 1):
            cell = ET.SubElement(row, tag("c"),
                                 r=f"{column_name(index)}{row_number}",
                                 s="1" if row_number == 1 else "0")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                ET.SubElement(cell, tag("v")).text = str(value)
            else:
                cell.set("t", "inlineStr")
                text = ET.SubElement(ET.SubElement(cell, tag("is")), tag("t"))
                text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                text.text = clean_text(value)
    ET.SubElement(sheet, tag("printOptions"), horizontalCentered="1")
    ET.SubElement(sheet, tag("pageMargins"), left="0.25", right="0.25",
                  top="0.3", bottom="0.3", header="0.15", footer="0.15")
    ET.SubElement(sheet, tag("pageSetup"), paperSize="9", orientation="landscape",
                  fitToWidth="1", fitToHeight="0", pageOrder="downThenOver")
    footer = ET.SubElement(sheet, tag("headerFooter"))
    ET.SubElement(footer, tag("oddFooter")).text = "&C第 &P 页 / 共 &N 页"
    if print_breaks:
        breaks = ET.SubElement(sheet, tag("rowBreaks"), count=str(len(print_breaks)),
                               manualBreakCount=str(len(print_breaks)))
        for row_id in print_breaks:
            ET.SubElement(breaks, tag("brk"), id=str(row_id), min="0", max="16383", man="1")
    workbook = ET.Element(tag("workbook"))
    sheets = ET.SubElement(workbook, tag("sheets"))
    ET.SubElement(sheets, tag("sheet"), name="单词列表", sheetId="1",
                  attrib={"{" + office_rel + "}id": "rId1"})
    names = ET.SubElement(workbook, tag("definedNames"))
    ET.SubElement(names, tag("definedName"), name="_xlnm.Print_Area", localSheetId="0").text = f"'单词列表'!$A$1:${column_name(len(headers))}${len(rows) + 1}"
    ET.SubElement(names, tag("definedName"), name="_xlnm.Print_Titles", localSheetId="0").text = "'单词列表'!$1:$1"
    relationships = ET.Element("Relationships", xmlns=rel_ns)
    ET.SubElement(relationships, "Relationship", Id="rId1",
                  Type=office_rel + "/worksheet", Target="worksheets/sheet1.xml")
    ET.SubElement(relationships, "Relationship", Id="rId2",
                  Type=office_rel + "/styles", Target="styles.xml")
    root_relationships = ET.Element("Relationships", xmlns=rel_ns)
    ET.SubElement(root_relationships, "Relationship", Id="rId1",
                  Type=office_rel + "/officeDocument", Target="xl/workbook.xml")
    types = ET.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
    ET.SubElement(types, "Default", Extension="rels",
                  ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(types, "Default", Extension="xml", ContentType="application/xml")
    for name, kind in [("workbook", "sheet.main"), ("worksheets/sheet1", "worksheet"), ("styles", "styles")]:
        ET.SubElement(types, "Override", PartName=f"/xl/{name}.xml",
                      ContentType=f"application/vnd.openxmlformats-officedocument.spreadsheetml.{kind}+xml")
    styles = f'''<styleSheet xmlns="{ns}">
      <fonts count="2"><font><sz val="12"/><name val="Calibri"/></font><font><b/><sz val="12"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>
      <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF172033"/><bgColor indexed="64"/></patternFill></fill></fills>
      <borders count="1"><border><left style="hair"><color rgb="FFB8BEC8"/></left><right style="hair"><color rgb="FFB8BEC8"/></right><top style="hair"><color rgb="FFB8BEC8"/></top><bottom style="hair"><color rgb="FFB8BEC8"/></bottom><diagonal/></border></borders>
      <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
      <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center"/></xf></cellXfs>
      <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
    </styleSheet>'''
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".xlsx", delete=False) as handle:
            temporary = handle.name
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in {
                "[Content_Types].xml": xml(types),
                "_rels/.rels": xml(root_relationships),
                "xl/workbook.xml": xml(workbook),
                "xl/_rels/workbook.xml.rels": xml(relationships),
                "xl/worksheets/sheet1.xml": xml(sheet),
                "xl/styles.xml": styles,
            }.items():
                archive.writestr(name, content)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def export_word_table(dialog, table, label):
    safe_label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", label).strip(" .")[:150]
    folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    filename = f"{safe_label}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    path, _ = QFileDialog.getSaveFileName(dialog, "导出 Excel", str(Path(folder) / filename), "Excel 工作簿 (*.xlsx)")
    if not path:
        return
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"
    try:
        headers, rows = table_export_data(table)
        if "英文单词" in headers and "中文翻译" in headers and "学习次数" in headers:
            columns = [headers.index(name) for name in ("英文单词", "中文翻译", "学习次数")]
            rows = [[row[index] for index in columns] for row in rows]
            headers = ["英文单词", "中文翻译", "累计学习次数"]
        write_list_xlsx(path, headers, rows, vertical=True)
    except Exception as error:
        showWarning(f"导出失败：{error}", parent=dialog)
        return
    tooltip(f"已导出 {len(rows)} 行到：{path}", parent=dialog)


def add_excel_export_button(layout, dialog, table, label):
    button = QPushButton("导出 Excel", dialog)
    button.setStyleSheet("QPushButton { padding: 8px 18px; border: 1px solid #2f6fed; border-radius: 6px; background: #2f6fed; color: white; font-weight: 600; }")
    button.clicked.connect(lambda: export_word_table(dialog, table, label))
    layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignRight)


def copy_selected_word_cells(dialog, table):
    indexes = table.selectedIndexes()
    if not indexes:
        tooltip("请先选中要复制的单元格", parent=dialog)
        return
    selected = {(index.row(), index.column()) for index in indexes}
    rows = sorted({row for row, _ in selected})
    columns = sorted({column for _, column in selected})
    lines = []
    for row in rows:
        values = []
        for column in columns:
            item = table.item(row, column)
            values.append(item.text() if (row, column) in selected and item else "")
        lines.append("\t".join(values))
    mw.app.clipboard().setText("\n".join(lines))
    tooltip("已复制", parent=dialog)


def add_word_copy_controls(layout, dialog, table):
    action = QAction("复制", table)
    action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Copy))
    action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    action.triggered.connect(lambda: copy_selected_word_cells(dialog, table))
    table.addAction(action)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)


def open_today_words(deck_name=None, *, entries_override=None, group_label=None):
    global today_dialog

    entries = (today_unique_entries(deck_name)
               if entries_override is None else entries_override)
    if not entries:
        if group_label:
            tooltip(f"这个牌组没有{group_label}的单词")
        elif deck_name:
            tooltip("这个牌组今天还没有学习记录")
        else:
            tooltip("今天还没有学习记录")
        return

    if today_dialog:
        today_dialog.close()
        today_dialog = None

    dialog = QDialog(mw)
    window_label = group_label or "今日单词"
    dialog.setWindowTitle(f"{window_label} · {deck_name}" if deck_name else window_label)
    dialog.resize(1100 if group_label else 760, 620)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setStyleSheet(
        """
        QDialog {
            background: #f4f6f9;
        }
        QLabel {
            color: #172033;
        }
        QTableWidget {
            background: #ffffff;
            alternate-background-color: #f8fafc;
            border: 1px solid #dfe4eb;
            border-radius: 8px;
            color: #202938;
            font-size: 14px;
            gridline-color: #edf0f4;
            selection-background-color: #e6efff;
            selection-color: #172033;
        }
        QTableWidget::item {
            padding: 5px 10px;
        }
        QHeaderView::section {
            height: 34px;
            padding: 0 10px;
            border: 0;
            border-bottom: 1px solid #dfe4eb;
            background: #eef2f7;
            color: #5d6675;
            font-size: 12px;
            font-weight: 700;
        }
        """
    )

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(10)
    title_prefix = deck_name if deck_name else "全部牌组"
    title_text = (f"{title_prefix} · {group_label} {len(entries)} 个单词"
                  if group_label else
                  f"{title_prefix} · 今日学习 {len(entries)} 个不重复单词")
    title = QLabel(title_text)
    title.setStyleSheet("font-size: 18px; font-weight: 700; padding: 2px 1px;")
    layout.addWidget(title)

    table = QTableWidget(len(entries), 5 if group_label else 3, dialog)
    table.setHorizontalHeaderLabels(
        ["英文单词", "中文翻译", "学习次数", "今日学习次数", "所属牌组"]
        if group_label else ["英文单词", "中文翻译", "次数"]
    )
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setWordWrap(False)
    table.verticalHeader().setDefaultSectionSize(44)
    table.verticalHeader().setMinimumSectionSize(44)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        0, QHeaderView.ResizeMode.Fixed
    )
    table.setColumnWidth(0, 180)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(
        2, QHeaderView.ResizeMode.Fixed
    )
    table.setColumnWidth(2, 62)
    if group_label:
        table.setColumnWidth(2, 90)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(3, 110)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(4, 280)

    for row, entry in enumerate(entries):
        english, chinese, review_count = entry[:3]
        english_item = QTableWidgetItem(english)
        english_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        chinese_item = QTableWidgetItem(chinese)
        count_item = QTableWidgetItem()
        count_item.setData(Qt.ItemDataRole.DisplayRole, review_count)
        count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 0, english_item)
        table.setItem(row, 1, chinese_item)
        table.setItem(row, 3 if group_label else 2, count_item)
        if group_label:
            deck_item = QTableWidgetItem(entry[3])
            deck_item.setToolTip(entry[3])
            repetitions_item = QTableWidgetItem()
            repetitions_item.setData(Qt.ItemDataRole.DisplayRole, entry[4])
            repetitions_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, repetitions_item)
            table.setItem(row, 4, deck_item)

    table.setSortingEnabled(True)
    table.horizontalHeader().setSortIndicatorShown(True)
    layout.addWidget(table)

    add_word_copy_controls(layout, dialog, table)
    add_excel_export_button(layout, dialog, table, dialog.windowTitle())

    today_dialog = dialog
    dialog.destroyed.connect(clear_today_dialog)
    dialog.show()


def clear_today_dialog():
    global today_dialog
    today_dialog = None


def open_today_added():
    global today_added_dialog

    entries = today_added_entries()
    if not entries:
        tooltip("今天还没有新增卡片")
        return

    if today_added_dialog:
        today_added_dialog.close()
        today_added_dialog = None

    dialog = QDialog(mw)
    dialog.setWindowTitle("今日新增")
    dialog.resize(820, 620)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setStyleSheet(
        """
        QDialog { background: #f4f6f9; }
        QLabel { color: #172033; }
        QTableWidget {
            background: #ffffff;
            alternate-background-color: #f8fafc;
            border: 1px solid #dfe4eb;
            border-radius: 8px;
            color: #202938;
            font-size: 14px;
            gridline-color: #edf0f4;
            selection-background-color: #e6efff;
            selection-color: #172033;
        }
        QTableWidget::item { padding: 5px 10px; }
        QHeaderView::section {
            height: 34px;
            padding: 0 10px;
            border: 0;
            border-bottom: 1px solid #dfe4eb;
            background: #eef2f7;
            color: #5d6675;
            font-size: 12px;
            font-weight: 700;
        }
        """
    )

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(10)
    title = QLabel(f"今日新增 {len(entries)} 张卡片")
    title.setStyleSheet("font-size: 18px; font-weight: 700; padding: 2px 1px;")
    layout.addWidget(title)

    table = QTableWidget(len(entries), 3, dialog)
    table.setHorizontalHeaderLabels(["牌组", "英文单词", "中文翻译"])
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setWordWrap(False)
    table.verticalHeader().setDefaultSectionSize(44)
    table.verticalHeader().setMinimumSectionSize(44)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(0, 220)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(1, 180)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    for row, (deck, english, chinese) in enumerate(entries):
        for column, value in enumerate((deck, english, chinese)):
            item = QTableWidgetItem(value)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, column, item)

    table.setSortingEnabled(True)
    table.horizontalHeader().setSortIndicatorShown(True)
    layout.addWidget(table)

    add_excel_export_button(layout, dialog, table, "今日新增")

    today_added_dialog = dialog
    dialog.destroyed.connect(clear_today_added_dialog)
    dialog.show()


def clear_today_added_dialog():
    global today_added_dialog
    today_added_dialog = None


def memory_curve_bucket_for_interval(days):
    for bucket in MEMORY_CURVE_BUCKETS:
        if days < bucket.min_days:
            continue
        if bucket.max_days is None or days < bucket.max_days:
            return bucket
    return None


def collect_memory_curve_rows():
    stats = {
        bucket.label: {"reviews": 0, "remembered": 0, "again": 0}
        for bucket in MEMORY_CURVE_BUCKETS
    }
    rows = mw.col.db.all(
        """
        select (id - previous_id) / 86400000.0, ease
        from (
            select id, ease, type,
                   lag(id) over (partition by cid order by id) as previous_id
            from revlog where ease between 1 and 4 and type in (0, 1, 2)
                and cid in (select id from cards)
        )
        where previous_id is not null and type in (1, 2)
        """
    )
    for last_interval, ease in rows:
        bucket = memory_curve_bucket_for_interval(float(last_interval or 0))
        if not bucket:
            continue
        item = stats[bucket.label]
        item["reviews"] += 1
        if int(ease or 0) == 1:
            item["again"] += 1
        else:
            item["remembered"] += 1

    result = []
    for bucket in MEMORY_CURVE_BUCKETS:
        item = stats[bucket.label]
        reviews = item["reviews"]
        remembered = item["remembered"]
        again = item["again"]
        retention = remembered / reviews * 100 if reviews else 0
        result.append((bucket.label, reviews, remembered, again, retention))
    return result


def make_table_item(value, align=Qt.AlignmentFlag.AlignCenter):
    item = QTableWidgetItem(str(value))
    item.setTextAlignment(align)
    return item


def show_memory_curve():
    global memory_curve_dialog

    if not mw.col:
        tooltip("请先打开一个 Anki 资料库")
        return

    if memory_curve_dialog:
        memory_curve_dialog.close()
        memory_curve_dialog = None

    curve_rows = collect_memory_curve_rows()
    total_reviews = sum(row[1] for row in curve_rows)
    total_remembered = sum(row[2] for row in curve_rows)
    overall = total_remembered / total_reviews * 100 if total_reviews else 0

    dialog = QDialog(mw)
    dialog.setWindowTitle("历史回忆率分析 · 全部牌组")
    dialog.resize(680, 480)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setStyleSheet(
        """
        QDialog { background: #f4f6f9; color: #172033; }
        QLabel { color: #172033; }
        QTableWidget {
            background: #ffffff;
            alternate-background-color: #f8fafc;
            border: 1px solid #dfe4eb;
            border-radius: 8px;
            color: #202938;
            font-size: 14px;
            gridline-color: #edf0f4;
            selection-background-color: #e6efff;
            selection-color: #172033;
        }
        QTableWidget::item { padding: 6px 10px; }
        QHeaderView::section {
            height: 34px;
            padding: 0 10px;
            border: 0;
            border-bottom: 1px solid #dfe4eb;
            background: #eef2f7;
            color: #5d6675;
            font-size: 12px;
            font-weight: 700;
        }
        QPushButton {
            min-height: 30px;
            padding: 4px 14px;
            border: 1px solid #cfd6df;
            border-radius: 6px;
            background: #ffffff;
        }
        QPushButton:hover { background: #f0f4fa; }
        """
    )

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(10)

    title = QLabel(
        f"历史回忆率：{overall:.1f}% · 统计 {total_reviews} 次复习记录"
    )
    title.setStyleSheet("font-size: 18px; font-weight: 700; padding: 2px 1px;")
    layout.addWidget(title)

    hint = QLabel("范围：全部现存卡片的历史记录，按实际两次作答间隔分组；Again 记为忘记，其余评分记为记住。\n不含已删除卡片；这是历史统计，不是当前记忆预测。")
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #6b7280; font-size: 12px;")
    layout.addWidget(hint)

    table = QTableWidget(len(curve_rows), 5, dialog)
    table.setHorizontalHeaderLabels(["间隔", "复习次数", "记住", "忘记", "回忆率"])
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(38)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for column in range(1, 5):
        table.horizontalHeader().setSectionResizeMode(
            column, QHeaderView.ResizeMode.Fixed
        )
    table.setColumnWidth(1, 92)
    table.setColumnWidth(2, 82)
    table.setColumnWidth(3, 82)
    table.setColumnWidth(4, 92)

    for row_index, (label, reviews, remembered, again, retention) in enumerate(
        curve_rows
    ):
        table.setItem(
            row_index,
            0,
            make_table_item(
                label, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            ),
        )
        table.setItem(row_index, 1, make_table_item(reviews))
        table.setItem(row_index, 2, make_table_item(remembered))
        table.setItem(row_index, 3, make_table_item(again))
        table.setItem(row_index, 4, make_table_item(f"{retention:.1f}%" if reviews else "—"))

    layout.addWidget(table)

    close_button = QPushButton("关闭", dialog)
    close_button.clicked.connect(dialog.close)
    layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

    memory_curve_dialog = dialog
    dialog.destroyed.connect(clear_memory_curve_dialog)
    dialog.show()


def clear_memory_curve_dialog():
    global memory_curve_dialog
    memory_curve_dialog = None


def add_memory_curve_toolbar_link(links, toolbar):
    class LinkIdentity(HTMLParser):
        identifier = None

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.identifier = dict(attrs).get("id")

    sync_links = []
    visible_links = []
    for link in links:
        identity = LinkIdentity()
        identity.feed(link)
        if identity.identifier == "sync":
            sync_links.append(link)
        elif identity.identifier != "stats":
            visible_links.append(link)
    links[:] = visible_links
    links.append(
        toolbar.create_link(
            "learningOverview", "学习总览", show_learning_overview,
            tip="查看全部牌组学习进度", id="learning-overview",
        )
    )
    links.append(toolbar.create_link(
        "studyTime", "学习时长", show_study_time,
        tip="按日、周、月查看作答耗时", id="study-time",
    ))
    links.append(
        toolbar.create_link(
            "memoryCurveStats",
            "遗忘曲线",
            show_memory_curve,
            tip="查看历史回忆率分析",
            id="memory-curve-stats",
        )
    )
    links.extend(sync_links)


def anki_study_day(timestamp=None):
    cutoff = mw.col.sched.day_cutoff
    if callable(cutoff):
        cutoff = cutoff()
    boundary = datetime.fromtimestamp(cutoff)
    value = datetime.fromtimestamp(timestamp) if timestamp is not None else datetime.now()
    return (value - timedelta(hours=boundary.hour, minutes=boundary.minute,
                              seconds=boundary.second)).date()


def collect_study_time_rows(mode):
    today = anki_study_day()
    def period(day):
        if mode == "每周":
            return day - timedelta(days=day.weekday())
        if mode == "每月":
            return day.replace(day=1)
        return day
    totals = {}
    for timestamp, milliseconds in mw.col.db.all(
        "select id, time from revlog where ease between 1 and 4 and type in (0, 1, 2)"
    ):
        day = anki_study_day(timestamp / 1000)
        key = period(day)
        item = totals.setdefault(key, [0, 0])
        item[0] += max(0, milliseconds or 0)
        item[1] += 1
    first = min(totals, default=period(today))
    key = period(today)
    rows = []
    while key >= first:
        milliseconds, count = totals.get(key, [0, 0])
        label = key.isoformat()
        if mode == "每周":
            label += " ~ " + (key + timedelta(days=6)).isoformat()
        elif mode == "每月":
            label = key.strftime("%Y-%m")
        rows.append((label, milliseconds, count))
        if mode == "每月":
            key = (key - timedelta(days=1)).replace(day=1)
        else:
            key -= timedelta(days=7 if mode == "每周" else 1)
    return rows


def show_study_time():
    global study_time_dialog
    if study_time_dialog is not None:
        study_time_dialog.close()
    dialog = QDialog(mw)
    dialog.setWindowTitle("学习时长 · 全部牌组")
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.resize(1000, 370)
    dialog.setStyleSheet(
        "QDialog { background: #fafafa; } QLabel { color: #4b4650; }"
        "QComboBox, QPushButton { background: #ffffff; color: #4b4650;"
        " border: 1px solid #ded9df; border-radius: 5px; padding: 5px 10px; }"
        "QComboBox QAbstractItemView { background: #ffffff; color: #4b4650;"
        " selection-background-color: #f8d5e5; selection-color: #4b4650; }"
    )
    layout = QVBoxLayout(dialog)
    daily = collect_study_time_rows("每日")
    daily_totals = {label: (milliseconds, count) for label, milliseconds, count in daily}
    year = QComboBox(dialog)
    years = sorted({int(label[:4]) for label, _, _ in daily}, reverse=True)
    year.addItems([str(value) for value in years])
    layout.addWidget(year)
    summary = QLabel(dialog)
    layout.addWidget(summary)
    heatmap = QTableWidget(7, 0, dialog)
    heatmap.setVerticalHeaderLabels(["一", "二", "三", "四", "五", "六", "日"])
    heatmap.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    heatmap.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    heatmap.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    heatmap.setShowGrid(True)
    heatmap.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    heatmap.horizontalHeader().setMinimumSectionSize(12)
    heatmap.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
    heatmap.verticalHeader().setDefaultSectionSize(23)
    heatmap.setFixedHeight(210)
    heatmap.setStyleSheet(
        "QTableWidget { background: #fafafa; border: 0; gridline-color: #fafafa; }"
        "QHeaderView::section { background: #fafafa; color: #8b818b; border: 0; }"
        "QTableCornerButton::section { background: #fafafa; border: 0; }"
    )
    def refresh_heatmap():
        selected = int(year.currentText())
        first = datetime(selected, 1, 1).date()
        last = datetime(selected, 12, 31).date()
        start = first - timedelta(days=first.weekday())
        columns = (last - start).days // 7 + 1
        heatmap.clearContents()
        heatmap.setColumnCount(columns)
        headers = [""] * columns
        for month in range(1, 13):
            headers[(datetime(selected, month, 1).date() - start).days // 7] = str(month)
        heatmap.setHorizontalHeaderLabels(headers)
        total = active = 0
        today = anki_study_day()
        for column in range(columns):
            for weekday in range(7):
                day = start + timedelta(days=column * 7 + weekday)
                item = QTableWidgetItem()
                color = "#fafafa"
                if first <= day <= last and day <= today:
                    milliseconds, count = daily_totals.get(day.isoformat(), (0, 0))
                    minutes = milliseconds / 60000
                    total += milliseconds
                    active += int(milliseconds > 0)
                    color = ("#ece9ed" if minutes == 0 else "#fce4ee" if minutes < 5
                             else "#f8c5dc" if minutes < 15 else "#f39bc3" if minutes < 30
                             else "#ed71ac" if minutes <= 60 else "#df458f")
                    seconds = milliseconds // 1000
                    item.setToolTip(f"{day.isoformat()}\n学习时长：{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}\n作答次数：{count}")
                item.setBackground(QColor(color))
                heatmap.setItem(weekday, column, item)
        summary.setText(f"{selected} 年 · 累计 {total / 3600000:.1f} 小时 · 学习 {active} 天")
    year.currentIndexChanged.connect(refresh_heatmap)
    refresh_heatmap()
    layout.addWidget(heatmap)
    legend = QLabel("时长 / 天：浅灰 0 · 浅粉 <5 分钟 · 淡粉 5至不足15 分钟 · 粉色 15至不足30 分钟 · 亮粉 30–60 分钟 · 浓粉 >1 小时")
    legend.setWordWrap(True)
    layout.addWidget(legend)
    cutoff = mw.col.sched.day_cutoff
    if callable(cutoff):
        cutoff = cutoff()
    change_time = datetime.fromtimestamp(cutoff).strftime("%H:%M")
    hint = QLabel(f"跟随 Anki 学习日，每日 {change_time} 换日，周一开始；仅累计作答耗时，不含空闲时间。")
    hint.setWordWrap(True)
    layout.addWidget(hint)
    close = QPushButton("关闭", dialog)
    close.clicked.connect(dialog.close)
    layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
    study_time_dialog = dialog
    dialog.destroyed.connect(clear_study_time_dialog)
    dialog.show()


def clear_study_time_dialog():
    global study_time_dialog
    study_time_dialog = None


def show_learning_overview():
    global learning_overview_dialog
    if learning_overview_dialog is not None:
        learning_overview_dialog.close()
    groups, today = dashboard_word_groups()
    total = sum(len(groups[key]) for key in ("unseen", "learning", "consolidating", "mastered"))
    dialog = QDialog(mw)
    dialog.setWindowTitle("学习总览 · 全部牌组")
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.resize(900, 210)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    grid = QGridLayout()
    grid.setSpacing(10)
    metrics = [
        ("总词数", total, "", "#f8fafc"),
        ("未学习", len(groups["unseen"]), "unseen", "#edf3ff"),
        ("今日未学习", len(groups["today-unseen"]), "today-unseen", "#fff1f5"),
        ("学习中", len(groups["learning"]), "learning", "#fff4e5"),
        ("巩固中", len(groups["consolidating"]), "consolidating", "#f3effc"),
        ("已掌握", len(groups["mastered"]), "mastered", "#eaf7ed"),
        ("今日完成", len(today), "today", "#edf9fa"),
    ]
    for column, (label, count, action, color) in enumerate(metrics):
        if action:
            tile = QPushButton(f"{label}\n{count}", dialog)
            tile.setAutoDefault(False)
            if action == "today":
                tile.clicked.connect(lambda _checked=False: open_today_words())
            else:
                tile.clicked.connect(lambda _checked=False, group=action: open_dashboard_word_group(group))
            tile.setToolTip(f"查看{label}的中英文列表")
        else:
            tile = QLabel(f"{label}\n{count}", dialog)
            tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setMinimumSize(108, 100)
        tile.setStyleSheet(
            f"background: {color}; color: #172033; border: 1px solid #dce3ed;"
            "border-radius: 8px; padding: 8px; font-size: 15px; font-weight: 600;"
        )
        grid.addWidget(tile, 0, column)
        grid.setColumnStretch(column, 1)
    layout.addLayout(grid)
    close_button = QPushButton("关闭", dialog)
    close_button.clicked.connect(dialog.close)
    layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
    learning_overview_dialog = dialog
    dialog.destroyed.connect(clear_learning_overview_dialog)
    dialog.show()


def clear_learning_overview_dialog():
    global learning_overview_dialog
    learning_overview_dialog = None


def install_memory_curve_menu_item():
    action = QAction("遗忘曲线分析", mw)
    action.triggered.connect(show_memory_curve)
    mw.form.menuTools.addAction(action)


def handle_dashboard_message(handled, message, context):
    if message == "ielts:export-learned-words" and isinstance(context, Overview):
        deck_name = mw.col.decks.current()["name"]
        note_reps = {}
        for card_id in mw.col.find_cards(f'deck:"{deck_name.replace(chr(34), chr(92) + chr(34))}"'):
            card = mw.col.get_card(card_id)
            note_reps[card.nid] = note_reps.get(card.nid, 0) + card.reps
        rows = []
        for note_id, reps in note_reps.items():
            if reps > 0:
                note = mw.col.get_note(note_id)
                rows.append([
                    plain_field(note.fields[0] if note.fields else ""),
                    chinese_translation(note.fields[1] if len(note.fields) > 1 else ""),
                    reps,
                ])
        rows.sort(key=lambda row: row[0].casefold())
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", deck_name).strip(" .")[:100]
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        filename = f"{safe_name}_已学单词与学习次数_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(mw, "导出已学单词", str(Path(folder) / filename), "Excel 工作簿 (*.xlsx)")
        if path:
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            try:
                write_list_xlsx(path, ["英文单词", "中文翻译", "累计学习次数"], rows, vertical=True)
                tooltip(f"已导出 {len(rows)} 个已学单词", parent=mw)
            except Exception as error:
                showWarning(f"导出失败：{error}", parent=mw)
        return (True, None)
    if message == "ielts:open-today" and isinstance(context, DeckBrowser):
        open_today_words()
        return (True, None)

    if message == "ielts:open-current-deck-today" and isinstance(context, Overview):
        open_today_words(mw.col.decks.current()["name"])
        return (True, None)

    if isinstance(context, Overview) and message.startswith("ielts:open-word-group:"):
        group = message.removeprefix("ielts:open-word-group:")
        if group in WORD_GROUP_LABELS:
            open_word_group(group)
            return (True, None)

    if message == "ielts:open-today-added" and isinstance(context, DeckBrowser):
        open_today_added()
        return (True, None)

    return handled


gui_hooks.webview_will_set_content.append(add_dashboard_assets)
gui_hooks.webview_did_receive_js_message.append(handle_dashboard_message)
gui_hooks.deck_browser_will_render_content.append(add_tomorrow_review_counts)
gui_hooks.overview_will_render_content.append(add_overview_progress)
Overview._show_finished_screen = render_completed_overview
gui_hooks.top_toolbar_did_init_links.append(add_memory_curve_toolbar_link)
install_memory_curve_menu_item()
