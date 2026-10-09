"""Headless end-to-end check: drop the 260903 files on the window and read the grid.

    python misc/smoke_test.py [data_dir]

Asserts the same numbers as `python -m biodist.study --self-check`, but through the UI —
so it also covers the drop classifier, the auto-assignment of runs to animals, and the
results table.
"""

import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from PySide6.QtCore import QEvent, QItemSelectionModel, QModelIndex, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QComboBox, QLabel, QLineEdit, QMenu, QPushButton, QTableWidget, QToolButton,
)

from biodist import report  # noqa: E402
from biodist.app import PREFS, TC, MainWindow, Sheet  # noqa: E402
from biodist.study import Manual  # noqa: E402

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Code\BioDist\data_260903")
FILES = ["260903_tissue_list_indiv.xlsx", "260903_injected_activity.xlsx",
         "Tare-001-20260902-161122-AutoExport.xlsx",
         "Tare-001-20260903-153146-AutoExport.xlsx",
         "Tc-99m-002-20260903-185456-AutoExport.xlsx",
         "Tc-99m-002-20260904-040117-AutoExport.xlsx"]

import biodist.app as _app  # noqa: E402
_app.OPTIONS_FILE = Path(os.environ.get("TEMP", ".")) / "_biodist_smoke_options.json"
_app.OPTIONS_FILE.unlink(missing_ok=True)           # the shipped defaults, not the user's file
app = QApplication.instance() or QApplication([])
w = MainWindow()
w.add_files([DATA / f for f in FILES])
assert w.study.date == "2026-09-03", f"the date must come off the counting files: {w.study.date}"
w.study.window = "112-168"

assert len(w.study.tissues) == 25, len(w.study.tissues)
assert [a.id for a in w.study.animals][:3] == ["107", "108", "109"]
assert w.study.tissue("Tail").role == "tail", "the tail must be auto-flagged as the injection site"
assert w.study.tissue("ctrl").role == "blank"

# four runs, all landing on animal 107: empty and filled tubes, a count and its recount
assert len(w.study.sources) == 4, w.study.sources
assert [s.animals for s in w.study.sources] == [["107"]] * 4, [s.animals for s in w.study.sources]
assert [s.kind for s in w.study.sources] == ["empty", "filled", "count", "count"]

w.study.manual += [
    Manual("107", "Bone marrow", mass_g=0.00113, note="weighed on paraffin"),
    Manual("107", "Thyr", mass_g=0.00261, note="weighed on paraffin"),
    Manual("107", "Kidneys", mbq=10.85, time="16:46"),
    Manual("107", "caecum", mbq=0.048, time="16:44"),
    Manual("107", "int small", mbq=0.255, time="16:45"),
    Manual("107", "int large", mbq=0.033, time="16:45"),
]
w._sync()

s, res = w._eff, w.res
# the lab sheet's 121 empty syringe was corrected 14:44 -> 15:44 by the user: nothing to flag
# but 107's tail, read on the dose calibrator — its vial counts background
assert [n[:22] for n in res.notes if "control tubes" not in n] == ["107: the tail vial rea"], res.notes
assert abs(res.injected_bq["107"] / 1e6 - 31.384) < 0.01, res.injected_bq["107"] / 1e6
assert abs(res.cell("107", "Liver").mass_g - 0.9223) < 1e-4
assert res.cell("107", "Kidneys").bq_src == "dose calibrator"
for tissue, want in (("Kidneys", 143.2), ("Blood", 0.28), ("Thyr", 2.55), ("Liver", 0.470)):
    got = res.value(s, "107", tissue, "pid_g")
    assert got is not None and abs(got - want) / want < 0.02, f"{tissue}: {got} vs {want}"

# the check panel must have noticed the liver disagreeing between the two counts; the kept
# count's dead time (1.22) is under 1.5, so no flag; what happened is in the log
html = w.check.toHtml()
# 1.22 and 1.61: neither in the default target range (≤ 1.1); 1.22 is valid (≤ 1.5): used,
# not flagged
assert "counts differ" not in html and "dead time" not in html, html
assert "a recount of" in html and "4 counter file(s)" in html, html

# the results grid: tissues down, animals across, and copyable as TSV
r = w.results
r.show_result(s, res)
grid = r._grid()
assert grid[0][:2] == ["tissue", "107 (C1)"], grid[0][:2]
assert len(grid) == 23 + 1, len(grid)              # the tissues only, by default
for a in r.show_rows.values():
    a.setChecked(True)
assert len(r._grid()) == 25 + 1 + 5 + 1, len(r._grid())   # + tail, blank, a gap, 5 summaries
assert r._grid()[-1][0] == "sum of tissues (%IA)"
kidneys = next(row for row in grid if row[0] == "Kidneys")
assert kidneys[1].startswith("143."), kidneys
r.set_unit("suv")
assert next(row for row in r._grid() if row[0] == "Kidneys")[1].startswith("28."), "SUV"
r.set_unit("act")                                    # as the tissue table: its own digits
assert r.s_digits.text() == "–" and not r.s_digits.isEnabled(), r.s_digits.text()
assert next(row for row in r._grid() if row[0] == "Kidneys")[1].endswith(" MBq")
r.set_unit("kbq")
kid = next(row for row in r._grid() if row[0] == "Kidneys")[1]
assert r.s_digits.isEnabled() and "." in kid and float(kid.replace(",", "")) > 1000, kid
PREFS["result_show_menu"] = ["sum"]                  # Options › Results window: the menus
r._apply_prefs()
assert r.show_rows["sum"].isVisible() and not r.show_rows["inj"].isVisible()
PREFS["result_show_menu"] = [k for k, _ in _app.RESULT_ROWS]
r.set_unit("suv")

# '+' after the cards: next ID in the series, isotope and molecule carried over; Ctrl+Z/Y
n = len(w.study.animals)
w.study.animals[-1].molecule = "24E8"
w.recompute()                                       # what a card edit ends in
w.study.animals[-1].extra.update(strain="C57BL/6", sex="F", comment="limp")
w.add_animal()
new = w.study.animals[-1]
assert new.extra.get("strain") == "C57BL/6" and "comment" not in new.extra, new.extra
assert (new.id, new.isotope, new.molecule) == ("122", "99mTc", "24E8"), new
w.undo()
assert len(w.study.animals) == n and w.study.animals[-1].molecule == "24E8", "undo"
w.redo()
assert w.study.animals[-1].id == "122", "redo"
w.undo()

# a stray time on the clipboard is not a tissue list
QApplication.clipboard().setText("14:46")
w.paste()
assert not w.study.tissue("14:46"), "a pasted time must not become a tissue"

# 107's Adrenal and BAT tubes swapped by hand in the empty-tube weighing: the filled tubes
# follow by rack match, the two countings are offered the same order, and take it
emp = next(x for x in w.study.sources if x.kind == "empty")
emp.slotmap.update({"1:2": ["107", "BAT"], "1:3": ["107", "Adrenal"]})
emp.auto = False
w.recompute()
asked = []
w._offer_fixes(ask=lambda lines: asked.extend(lines) or [True] * len(lines))
assert len(asked) == 2 and all("animal 107, 2 vial(s)" in x for x in asked), asked
cnt = [x for x in w.study.sources if x.kind == "count"]
assert all(x.mapping(w.runs[x.path])["1:2"] == ("107", "BAT") for x in cnt)
w._offer_fixes(ask=lambda lines: 1 / 0)             # nothing left to offer: never asks
w.undo()
w.undo()
assert not w.study.sources[0].slotmap, "undone"

# Tab along a card's row, then on to the next card; Enter down the card
w.show()
w.activateWindow()
app.processEvents()
c0, c1 = w.cards[0], w.cards[1]
c0.focus("syringe full", 1)
app.processEvents()
c0.eventFilter(c0.e_full_t, QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier))
app.processEvents()
assert c1.where(app.focusWidget()) == (c1.where(c1.e_full)), "Tab past a row's end: next card"
c1.eventFilter(c1.e_full, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
app.processEvents()
assert app.focusWidget() is c1.e_empty, "Enter: the next row, same column"

# the report: sections ticked, reordered, a table copied into another unit; every format
import biodist.app as _app  # noqa: E402
_real_save, _app._save_prefs = _app._save_prefs, lambda *a: True   # Options file untouched
rw = w.report
tree = rw.tree
assert tree.topLevelItemCount() == len(rw.specs) + 1, "the copy / remove / add bar, last"
for r in range(len(rw.specs)):
    tree.topLevelItem(r).setCheckState(0, Qt.Checked)
app.processEvents()
assert all(x["on"] for x in rw.specs)
arr = next(r for r, x in enumerate(rw.specs) if x["key"] == "arrive")
n = len(rw.specs)
tree._remove(arr)                                    # the only one: kept hidden, not shown
assert rw.specs[arr]["gone"] and not rw.specs[arr]["on"] and len(rw.specs) == n, rw.specs[arr]
assert report.clean(rw.specs)[arr].get("gone"), "the shipped list does not bring it back"
tree.setCurrentItem(tree.topLevelItem(0))
tree._add(report._one({"key": "arrive", "on": True}))   # + add: below the selected, as it starts
assert [x["key"] for x in rw.specs].count("arrive") == 1 and rw.specs[1]["key"] == "arrive"
assert rw.specs[1]["on"] and not rw.specs[1].get("gone")
app.processEvents()
assert tree.topLevelItemCount() == len(rw.specs) + 1
gen = next(r for r, x in enumerate(rw.specs) if x["key"] == "general")
sec = tree.topLevelItem(gen)                         # unfolded: its parts, ticked
parts = [sec.child(k).text(0) for k in range(sec.childCount())]
assert any(p.startswith("the rules") for p in parts) and "processing" not in \
    rw.specs[gen]["parts"], (parts, rw.specs[gen]["parts"])
first = rw.specs[0]["key"]
rw.specs.append(rw.specs.pop(0))                     # moved last (a drag does this)
tree._done()
app.processEvents()
assert rw.specs[-1]["key"] == first == "general"
row = next(r for r, x in enumerate(rw.specs) if x.get("unit") == "pid_g")
tree._copy(row)
tree._set(row + 1, "unit", "suv")
tree._set(row + 1, "layout", "list")
app.processEvents()
assert report.title(rw.specs[row + 1]) == "Tissue uptake, SUV (g/g)"
titles = [t for t, _ in rw._sections()]
assert titles.index("Tissue uptake, %IA/g") + 1 == titles.index("Tissue uptake, SUV (g/g)"), titles
assert titles[-1] == "General", titles
suv = rw._sections()[titles.index("Tissue uptake, %IA/g") + 1][1]
assert suv[0][0] == "p" and any(b[1].startswith("Kidneys: ") for b in suv), suv[:3]
gen_rows = dict(next(b for t, b in rw._sections() if t == "General")[0][2])
assert "counting efficiency (counts per decay)" in gen_rows and "vial counted more than once" \
    not in gen_rows, list(gen_rows)                # the facts, not the rules, by default
eff = gen_rows["counting efficiency (counts per decay)"]
assert "112-168 keV: 0.758 (the file)" in eff and "15-2047 keV: 0.856" in eff, eff
rw.show()
rw.refresh()
app.processEvents()
rw._goto(len(rw.specs) - 1)
assert rw.view.verticalScrollBar().value() > 0, "a click on a section scrolls the preview there"
rw.hide()
# Tissues ⤢: the results and the report list the chosen tissues, in the chosen order
ow = w.output_win
ow.open()
n0 = len(w.results._rows())
ow._apply(["Blood"])
ow.src.setCurrentRow([t.name for t in w.study.tissues].index("Liver"))
ow._add()
app.processEvents()
assert w.study.output == ["Blood", "Liver"], w.study.output
assert [t.name for t in w.results._rows()][:2] == ["Blood", "Liver"]
assert [r[0] for r in report._grid(w._eff, w.res, lambda a, t: 0, False)[1]] == ["Blood", "Liver"]
ow._apply([])
app.processEvents()
assert not w.study.output and len(w.results._rows()) == n0
# renamed for the results and the report only; ↺ gives the name back
it = next(ow.out.item(i) for i in range(ow.out.count()) if ow.out.item(i).text() == "Liver")
it.setText("Liver (whole)")
app.processEvents()
app.processEvents()
assert w.study.tissue_labels == {"Liver": "Liver (whole)"} and w.study.tissue("Liver")
assert "Liver (whole)" in [r[0] for r in w.results._grid()]
assert "Liver (whole)" in [r[0] for r in report._grid(w._eff, w.res, lambda a, t: 0)[1]]
it = next(ow.out.item(i) for i in range(ow.out.count()) if ow.out.item(i).text() == "Liver (whole)")
assert it.data(Qt.UserRole + 1), "a renamed one shows its ↺"
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from biodist.app import _Revert  # noqa: E402
ow.eventFilter(ow.out.viewport(), QMouseEvent(
    QEvent.MouseButtonRelease, QPointF(_Revert.spot(ow.out, it).center()), QPointF(),
    Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
app.processEvents()
app.processEvents()
assert not w.study.tissue_labels, w.study.tissue_labels
ow.close()
# Animals ▤: grouped by molecule in the results and the report; the cards' order dragged
ao = w.animal_order
ao.open()
mols = {a.id: a.molecule for a in w.study.animals}
for a in w.study.animals:
    a.molecule = "B" if a.id == "108" else "A"
ao.group.setChecked(True)
app.processEvents()
heads = w.results._grid()[0][1:]
assert heads[0] == "107 (C1)\nA" and heads[-1] == "108 (C2)\nB", heads
ao.src.model().moveRow(QModelIndex(), 0, QModelIndex(), ao.src.count())
app.processEvents()
app.processEvents()
assert w.study.animals[-1].id == "107", [a.id for a in w.study.animals]
w.undo()
w.undo()
w.undo()
assert w.study.animals[0].id == "107" and not w.study.group_by, "undone"
for a in w.study.animals:
    a.molecule = mols[a.id]
ao.close()
for ext in (".odt", ".pdf", ".xlsx", ".md", ".html"):
    out = Path(os.environ.get("TEMP", ".")) / f"_biodist_report{ext}"
    w.report.write(out)
    assert out.stat().st_size > 2000, (ext, out.stat().st_size)
    out.unlink()
_app._save_prefs = _real_save

tmp = Path(os.environ.get("TEMP", ".")) / "_biodist_smoke.json"
w.study.save(tmp)
w._load_study(tmp)
assert abs(w.res.value(w._eff, "107", "Kidneys", "pid_g") - 143.2) < 3, "round trip"
tmp.unlink(missing_ok=True)

# the typed rows of the tissue grid: + mass opens a row, a cell typed there is a manual mass
PREFS["typed_mass"] = "g"                            # mg by default; g typed here
w._hand(w.study.tissue("Adrenal"), "mass", True)
r0 = w._trows.index((w.study.tissues.index(w.study.tissue("Adrenal")), "mass_g"))
w.t_tissues.item(r0, TC).setText("0.004")
assert w.res.cell("107", "Adrenal").mass_src == "manual", "typed mass wins"
w.t_tissues.item(w._trows.index((1, ""), ), 0).setText("Adrenals")
assert any(m.tissue == "Adrenals" and m.mass_g == 0.004 for m in w.study.manual), "rename follows"

# a dose-calibrator read the next day, typed with its date
w._hand(w.study.tissue("Liver"), "activity", True)
rt = w._trows.index((w.study.tissues.index(w.study.tissue("Liver")), "time"))
w.t_tissues.item(rt - 1, TC).setText("0.5")
w.t_tissues.item(rt, TC).setText("4/9/26 9:00")
assert w.res.cell("107", "Liver").bq_src == "dose calibrator", w.res.notes
# a wide cell keeps its values together in the middle; the typed activity and its time sit
# in the activity's share of the cell, under the activity in use
rt = w._trows.index((w.study.tissues.index(w.study.tissue("Liver")), "time"))
d, ix = w.t_tissues.itemDelegate(), w.t_tissues.model().index(rt, TC)
opt = _app.QStyleOptionViewItem()
opt.initFrom(w.t_tissues)
opt.rect = _app.QRect(0, 0, 600, 30)
blk = d._block(opt, ix)
assert blk.width() < 600 and abs(blk.center().x() - 300) <= 1, blk
assert ix.data(_app._SHARE) == (1, 2) and ix.siblingAtRow(rt - 1).data(_app._SHARE) == (1, 2)

# a click under an animal opens a typed row for every animal: a note here
w._open_typed(w.study.tissue("Heart"), "note", "note", TC)
rn = w._trows.index((w.study.tissues.index(w.study.tissue("Heart")), "note"))
w.t_tissues.item(rn, TC).setText("clot")
assert any(m.tissue == "Heart" and m.note == "clot" for m in w.study.manual), "typed note"
# a mass typed in mg (Options) is stored in g; × closes the row, Ctrl+Z opens it again
PREFS["typed_mass"] = "mg"
w._sync()
r0 = w._trows.index((w.study.tissues.index(w.study.tissue("Adrenals")), "mass_g"))
assert w.t_tissues.cellWidget(r0, 0).findChild(QLabel).text().endswith("mass (mg)")
# ▸ / ▾ before a tissue with typed rows folds them away and back
n_rows = w.t_tissues.rowCount()
w._tissue_open["Adrenals"] = False
w._sync()
assert w.t_tissues.rowCount() == n_rows - 1, "folded"
w._tissue_open["Adrenals"] = True
w._sync()
r0 = w._trows.index((w.study.tissues.index(w.study.tissue("Adrenals")), "mass_g"))
assert w.t_tissues.item(r0, TC).text() == "4", w.t_tissues.item(r0, TC).text()
w.t_tissues.item(r0, TC).setText("5.5")
assert next(m for m in w.study.manual if m.tissue == "Adrenals").mass_g == 0.0055
PREFS["typed_mass"] = "g"
w._sync()
ra = w._trows.index((w.study.tissues.index(w.study.tissue("Adrenals")), "mass_g"))
w.t_tissues.cellWidget(ra, 0).findChild(QToolButton).click()
app.processEvents()
assert "mass" not in w.study.tissue("Adrenals").hand, "× closes the typed row"
assert not any(m.tissue == "Adrenals" and m.mass_g for m in w.study.manual), "… and deletes"
w.undo()
app.processEvents()
assert "mass" in w.study.tissue("Adrenals").hand, "Ctrl+Z opens it again"
# a tissue cell: mass in mg and the activity at the injection time, units under each other
rl = w._trows.index((w.study.tissues.index(w.study.tissue("Liver")), ""))
cell = w.t_tissues.item(rl - 0, TC).text()
assert re.fullmatch(r"\d+\.\d mg\t\d+\.\d+ (MBq|kBq)", cell), cell
assert "injection time" in w.l_tissue_note.text()
from biodist.app import _act  # noqa: E402
assert [_act(x) for x in (12.34e6, 0.5e6, 0.0123e6, 1500, 150)] == \
    ["12.3 MBq", "0.50 MBq", "0.012 MBq", "1.50 kBq", "0.150 kBq"]

# numbers show as read: 1.30 stays 1.30, .577 gets its 0
from biodist.app import _num  # noqa: E402
assert (_num(1.3, "1.30"), _num(0.577, ".577"), _num(2.0, "")) == ("1.30", "0.577", "2"),     _num(1.3, "1.30")

# a source's animals and tissues sum up its vials; its run shows when it was measured
assert w.t_sources.cellWidget(2, 5) is None and w.t_sources.item(2, 5).text(), \
    w.t_sources.item(2, 5).text()
assert re.fullmatch(r"round 1 · \d\d \w+ \d\d:\d\d–\d\d:\d\d  ⤢", w.t_sources.item(2, 1).text()), \
    w.t_sources.item(2, 1).text()

# 260923: the user's study, then its 18 Hidex files dropped at once — the post-collection
# weighing put two small racks in the run before their own; the guess must place them
D2 = DATA.parent / "data"
if (D2 / "260923.json").exists():
    w2 = MainWindow()
    w2._load_study(D2 / "260923.json")
    w2.add_files(sorted(D2.glob("*AutoExport.xlsx")))
    assert w2.study.date == "2026-09-23", w2.study.date
    w2.study.sources = []                           # the saved study may hold them already
    w2.add_files(sorted(D2.glob("*AutoExport.xlsx")))
    w2.add_files(sorted(D2.glob("*AutoExport.xlsx")))   # a second drop adds nothing
    kinds = [x.kind for x in w2.study.sources]
    assert kinds[:18] == ["empty"] * 6 + ["filled"] * 6 + ["count"] * 6, kinds
    assert [x.animals for x in w2.study.sources[12:18]] == [[a.id] for a in w2.study.animals]
    assert [x.animals for x in w2.study.sources[18:]] in ([], [[a.id] for a in w2.study.animals])
    html = w2.check.toHtml()
    assert html.count("rack slip") == 2, html
    assert "Study date" not in html, "the filled tubes set the day, not the next-day counts"
    assert all(c.mass_g > -0.005 for c in w2.res.cells.values() if c.mass_g is not None)
    hand = {(x[0], x[1]) for x in w2.study.chosen if x[2] == "mass"}   # the user's own picks
    assert all(c.mass_src.startswith("Tare-") for k, c in w2.res.cells.items()
               if c.mass_src and k not in hand),         "the day's filled tubes weigh, not the next-day recount"
    w2._keep_or_save = lambda: True

# Options: a typed time shows tidied but keeps its seconds; a field goes on every card;
# a capped table scrolls
from biodist.app import PREFS, AnimalCard  # noqa: E402
PREFS.update(tidy_times=True, time_format="HH:MM d+n", field_all=True, table_rows=5)
w._sync()
card = w.cards_row.itemAt(0).widget()
card.e_inj.setText("d+1 8:48:21")
card.e_inj.editingFinished.emit()
a0 = w.study.animals[0]
assert (a0.inj_time, card.e_inj.text()) == ("d+1 8:48:21", "08:48 d+1"), a0.inj_time
card.e_inj.editingFinished.emit()                 # left untouched: the seconds stay
assert a0.inj_time == "d+1 8:48:21", a0.inj_time
w._show_field(a0, "tumour model", True)            # the animal window's "on card" tick
app.processEvents()
assert all("tumour model" in x.extra for x in w.study.animals)
assert w.t_tissues.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOn
assert isinstance(card, AnimalCard)
# 16.png: a short ID and alias stay on one line with the age and the dose; the Animals
# section is as tall as its tallest card (no scrolling)
a0.aliases = ["V7"]
w._sync()
app.processEvents()
app.processEvents()
c0 = w.cards[0]
assert c0.e_id.width() < 60 and (app.platformName() == "offscreen"   # no fonts there:
                                  or c0.head.indexOf(c0.alias_w) >= 0), c0.e_id.width()  # no width
assert w.cards_scroll.verticalScrollBar().maximum() == 0

# a card's × hides a field on every card, and keeps what it holds
a0.extra["sex"] = "F"
w._show_field(a0, "sex", False)
app.processEvents()
card = w.cards_row.itemAt(0).widget()
card = card if isinstance(card, AnimalCard) else card.widget()
assert "sex" not in card.fields and a0.extra["sex"] == "F", card.fields
w._show_field(a0, "sex", True)
app.processEvents()

# the animal window: every field, copied to the others
before_loss = w.res.injected_bq["107"]
w.animal_win.show_animal(0)
a0.molecule = "R3B23"
w.animal_win._copy("molecule", w.study.animals[1:])
assert {x.molecule for x in w.study.animals} == {"R3B23"}
w.animal_win.show_animal(len(w.study.animals))            # past the end: the last one
assert w.animal_win.i == len(w.study.animals) - 1
w.animal_win._add_event("imaging")                   # a procedure brings its own fields
app.processEvents()
labels = [x.text().strip() for x in w.animal_win.scroll.widget().findChildren(QLabel)]
assert "modality" in labels and "route" not in labels, labels
plus = next(b for b in w.animal_win.scroll.widget().findChildren(QToolButton)
            if b.text() == "+ field")                # a procedure's: the only one left
plus.click()                                       # a click: the name box shows
more = plus.parent().findChild(QLineEdit)
assert not more.isHidden() and plus.isHidden()
more.setText("kV")
more.editingFinished.emit()
app.processEvents()
app.processEvents()
assert "kV" in w.study.animals[-1].events[0], w.study.animals[-1].events
x = next(b for b in w.animal_win.scroll.widget().findChildren(QToolButton)
         if b.text() == "×" and "kV" in b.toolTip())
x.click()                                          # an added field has its ×
app.processEvents()
app.processEvents()
assert "kV" not in w.study.animals[-1].events[0], "removed"
w.study.animals[-1].events[0]["kV"] = ""
# an imaging session brings its anaesthesia, a procedure of its own; SPECT/CT is two sessions
al = w.study.animals[-1]
assert [e["kind"] for e in al.events] == ["imaging", "anaesthesia"], al.events
combo = next(c for c in w.animal_win.scroll.widget().findChildren(QComboBox)
             if "SPECT" in [c.itemText(i) for i in range(c.count())])
root = w.animal_win.scroll.widget()
combo.lineEdit().editingFinished.emit()               # what its list opening says: no change,
app.processEvents()                                   # no redraw (it took the open list away)
app.processEvents()
assert w.animal_win.scroll.widget() is root, "the modality list stays open"
combo.setCurrentText("SPECT/CT")
combo.lineEdit().editingFinished.emit()
app.processEvents()
app.processEvents()
assert [e.get("modality") for e in al.events if e["kind"] == "imaging"] == ["SPECT", "CT"]
# removed by mistake: Ctrl+Z in the animal window brings it back
n = len(al.events)
al.events.pop(0)
w.animal_win._redraw()
app.processEvents()
w.animal_win._step(True)
app.processEvents()
assert len(w.study.animals[-1].events) == n, "undone in the animal window"
# the every-animal table holds the procedures, and the other losses
w.study.animals[0].losses.append({"mbq": "0.3", "time": "12:30", "what": "cotton"})
w.animal_win.show_all()
app.processEvents()
heads = [w.animal_win.sheet.item(r, 0).text() for r in range(w.animal_win.sheet.rowCount())]
assert "imaging 1 · modality" in heads and "other loss 1 (MBq)" in heads, heads
r = heads.index("imaging 2 · start")
w.animal_win.sheet.setCurrentCell(r, len(w.study.animals) + w.animal_win.SC - 1)
w.animal_win.sheet.item(r, len(w.study.animals) + w.animal_win.SC - 1).setText("13:30")
app.processEvents()
assert [e for e in w.study.animals[-1].events if e["kind"] == "imaging"][1]["start"] == "13:30"
assert w.res.injected_bq["107"] < before_loss, "the loss comes off"
# the table view: on card and copy per field; copy lists every animal, the source greyed
sh = w.animal_win.sheet
rw = next(r for r in range(sh.rowCount()) if sh.item(r, 0).text() == "body weight (g)")
assert sh.cellWidget(rw, 1).findChild(_app.QCheckBox) is not None
if len(w.study.animals) > 1:
    sh.setCurrentCell(rw, w.animal_win.SC + 1)      # the second animal's cell: copied from it
    menu = sh.cellWidget(rw, 2).menu()
    menu.aboutToShow.emit()
    ticks = [x for x in menu.actions() if x.isCheckable()]
    assert len(ticks) == len(w.study.animals) and not ticks[1].isEnabled() and \
        ticks[0].isEnabled(), [x.text() for x in ticks]
w.study.animals[-1].events.clear()
w.study.animals[0].losses.clear()
w.animal_win.close()

# Options: a window of its own, exported and imported as JSON
from biodist.app import _load_prefs, _save_prefs  # noqa: E402
w.show_options()
assert w.options_win.pages.count() == w.options_win.topics.count() == 12
tmp = Path(os.environ.get("TEMP", ".")) / "_biodist_options.json"
keep = dict(PREFS)
assert _save_prefs(tmp)
PREFS["card_rows"], PREFS["strains"] = 99, "junk"
_load_prefs(tmp)
assert PREFS == keep, "options round trip"
tmp.unlink()
# Ctrl+Z in the Options: the options as they were (written to a scratch file here)
real_file = _app.OPTIONS_FILE
_app.OPTIONS_FILE = tmp
_app._PREFS_UNDO["now"] = [json.dumps(PREFS, sort_keys=True)]
w.options_win._set("strip_racks", 5)
assert PREFS["strip_racks"] == 5
w._prefs_undo(True)
assert PREFS["strip_racks"] == 3, "Ctrl+Z in the Options"
w._prefs_undo(False)
assert PREFS["strip_racks"] == 5, "Ctrl+Y"
w._prefs_undo(True)
_app.OPTIONS_FILE = real_file
tmp.unlink(missing_ok=True)
# Options › Results: the study's rules (Ctrl+Z there is the study's), its expected ranges
ow = w.options_win
ow.topics.setCurrentRow([ow.topics.item(i).text() for i in range(ow.topics.count())]
                        .index("Rules"))
page = ow.pages.currentWidget().widget()            # each page in its scroll area
assert not w.study.ranges, "no expected range until one is set"
plus = next(b for b in page.findChildren(QPushButton) if b.text() == "+")
plus.menu().aboutToShow.emit()
thyr = next(x for x in plus.menu().actions() if x.text() == "Thyr")
thyr.trigger()
app.processEvents()
app.processEvents()
assert w.study.ranges == [["Thyr", 0.0, 0.0, 0.0, 0.0]], w.study.ranges
rng = page.findChild(QTableWidget)
rng.item(0, 2).setText("2")                          # 2.61 mg: over
app.processEvents()
app.processEvents()
assert any(f.startswith("out of range") for f in w.res.cell("107", "Thyr").flags)
ow._undo(True)                                       # the study's step, on this page
app.processEvents()
assert w.study.ranges == [["Thyr", 0.0, 0.0, 0.0, 0.0]], w.study.ranges
combo = next(c for c in page.findChildren(QComboBox)
             if c.currentText() == "weighted by their counts")
combo.activated.emit(1)                              # their mean
app.processEvents()
app.processEvents()
assert w.study.combine == "mean" and PREFS["combine"] == "weighted", "the study's, not Options'"
w.study.combine, w.study.ranges = "weighted", []
w._sync()
ow.close()

# 260903 whole: tumour and muscle weighed and counted straight after euthanasia (their own
# list, empty tubes and weigh+count run), the rest later — the second list is its own run
w3 = MainWindow()
w3.add_files([DATA / f for f in FILES + ["260903_tissue_direct.xlsx",
                                         "Tare-001-20260902-165551-AutoExport.xlsx",
                                         "Tc-99m_weights-010-20260903-141827-AutoExport.xlsx"]])
assert w3.study.batch_tissues("direct") == ["tumor", "muscle"], w3.study.batch_tissues("direct")
assert not w3.h_tissues.isVisibleTo(w3) and not w3.h_sources.isVisibleTo(w3), "hints hide"
assert w3.batch_bar.isVisibleTo(w3), "two runs: each one's vial order shows"
direct = [x for x in w3.study.sources if x.batch == "direct"]
assert [x.kind for x in direct] == ["empty", "weigh_count"], [(x.path, x.kind) for x in direct]
assert abs(w3.res.cell("107", "tumor").mass_g - 0.2767) < 1e-4
assert abs(w3.res.cell("109", "muscle").mass_g - 0.1150) < 1e-4
assert abs(w3.res.cell("107", "Liver").mass_g - 0.9223) < 1e-4, "the main run is untouched"
# the Results' side panel: the rule for every cell, and one cell's counting picked by hand
from PySide6.QtWidgets import QTableWidgetSelectionRange  # noqa: E402
res3 = w3.results
w3.show_results()
res3.data_changed.emit({"pick_count": "first", "dt_max": 2.0, "valid_dt": 2.0})   # both in
assert w3.res.cell("107", "Liver").bq_src.startswith("Tc-99m-002-20260903"), "rule"
res3.data_changed.emit({"pick_count": "first", "dt_max": 1.1, "valid_dt": 1.5})
liver = [t.name for t in res3._rows()].index("Liver")
res3.table.setCurrentCell(liver, 1)
res3.table.setRangeSelected(QTableWidgetSelectionRange(liver - 1, 1, liver, 2), True)
app.processEvents()
late = w3.res.round_of("Tc-99m-002-20260904-040117-AutoExport.xlsx")
there = sorted([a, t, "count", x[0]] for (a, t) in [(a.id, t.name) for a, t in res3._selected()]
               for x in w3.res.cell(a, t).alts if w3.res.round_of(x[0]) == late)
assert len(there) >= 2, there
tab, rks, _ = res3._ticks["count"]           # a row per round, its window picked in the row
assert tab.columnCount() == 8 and "of 4 cells" in tab.item(0, 3).text(), tab.item(0, 3).text()
assert isinstance(tab.cellWidget(0, 1), QComboBox) and \
    tab.cellWidget(0, 1).currentText() == "15-2047", "the window, in the row"
assert not res3._b_apply.isEnabled(), "nothing to apply before a click"
on_late = {k for k in [(a.id, t.name) for a, t in res3._selected()]
           if w3.res.round_of(w3.res.cell(*k).bq_src) == late}
there = [x for x in there if tuple(x[:2]) not in on_late]   # using it already: no pick
res3._src_click("count", next(r for r, rk in enumerate(rks) if rk[1] == late), add=False)
app.processEvents()
app.processEvents()
assert res3._pending and not w3.study.chosen, "shown in the table, not applied"
assert res3._b_apply.isEnabled()
res3._b_apply.click()
app.processEvents()
app.processEvents()
assert sorted(w3.study.chosen) == there, w3.study.chosen     # not on a vial that round missed
assert all(w3.res.round_of(w3.res.cell(a, t).bq_src) == late for a, t, *_ in there), "picked"
assert not there or res3.table.item(liver, 1).font().italic() or ("107", "Liver") in on_late, \
    "a picked cell is italic"
assert len(res3._selected()) == 4, "the selection survives the recompute"


def spin():
    app.processEvents()
    app.processEvents()


def rounds_clicked():
    """The liver of 107 alone: every round, the first a plain click, the others Ctrl+click."""
    res3._fill_panel()
    tab, rks, _ = res3._ticks["count"]
    assert tab.item(0, 3).text() and tab.item(0, 5).text(), "counts, kBq of the counting"
    for r, rk in enumerate(rks):
        if rk[0] == 0:
            res3._src_click("count", r, add=r > 0)
            spin()
    return sum(1 for rk in rks if rk[0] == 0)


# one cell: both countings — weighted by their counts; another cell drops unapplied ticks,
# and says so
res3.table.clearSelection()
res3.table.setCurrentCell(liver, 1)
app.processEvents()
n_rounds = rounds_clicked()
assert res3.res.cell("107", "Liver").bq_src == f"weighted of {n_rounds}", "previewed"
res3.set_unit("bq")                          # 0.47 either way
assert res3.table.item(liver, 1).font().bold() and "not applied" in \
    res3.table.item(liver, 1).toolTip(), "what the ticks give, in the table"
res3.set_unit("pid_g")
res3.table.setCurrentCell(liver - 1, 1)               # elsewhere, not applied: dropped
spin()
assert not res3._pending and res3.res is w3.res and "Not applied" in \
    res3.statusBar().currentMessage(), res3.statusBar().currentMessage()
res3.table.setCurrentCell(liver, 1)
app.processEvents()
rounds_clicked()
res3._b_apply.click()
spin()
assert w3.res.cell("107", "Liver").bq_src == f"weighted of {n_rounds}", w3.res.cell("107", "Liver")
assert w3.res.source_label("107", "Liver", "activity").startswith("weighted r1+r2")
# Ctrl+click on a ticked row takes it out; round 1 in the photopeak window, from its list
res3._fill_panel()
tab, rks, _ = res3._ticks["count"]
res3._src_click("count", next(r for r, rk in enumerate(rks) if rk[:2] == (0, 1)), add=True)
spin()
assert res3.res.round_of(res3.res.cell("107", "Liver").bq_src) == 0, res3.res.cell("107", "Liver")
tab, rks, _ = res3._ticks["count"]
cb = tab.cellWidget(next(r for r, rk in enumerate(rks) if rk[:2] == (0, 0)), 1)
cb.setCurrentIndex(cb.findText("112-168"))
cb.activated.emit(cb.findText("112-168"))
spin()
res3._b_apply.click()
spin()
assert w3.res.source_label("107", "Liver", "activity") == "round 1 · 112-168", \
    w3.res.source_label("107", "Liver", "activity")
res3.set_unit("src_mass")
assert res3._grid()[liver + 1][1] == "weight − tare", res3._grid()[liver + 1]
res3.set_unit("pid_g")
app.processEvents()
res3._fill_panel()
back = next(b for b in res3.panel.widget().findChildren(QPushButton)
            if b.text() == "Back to the rules")
back.click()
spin()
assert not any(x[:2] == ["107", "Liver"] for x in w3.study.chosen), w3.study.chosen
# several cells, round 1 in the other window: the cells using it take it there, the kidneys
# keep their dose-calibrator reading, the others what they had — and get no pick
w3.study.manual.append(Manual("107", "Kidneys", mbq=10.85, time="16:46"))
kept = w3.study.chosen
res3.data_changed.emit({"chosen": []})
spin()
names = [t.name for t in res3._rows()]
res3.table.clearSelection()
for tn in ("Kidneys", "Liver", "Blood", "Lungs"):
    res3.table.setRangeSelected(QTableWidgetSelectionRange(names.index(tn), 1,
                                                           names.index(tn), 1), True)
app.processEvents()
res3._fill_panel()
was = {tn: list(w3.res.cell("107", tn).bq_used) for tn in ("Kidneys", "Liver", "Blood", "Lungs")}
r1 = w3.res.rounds[0]
assert was["Kidneys"] == ["dose calibrator"] and any(set(u) & set(r1) for u in was.values()), \
    (was, r1, w3.study.pick_count, w3.study.chosen)
tab, rks, _ = res3._ticks["count"]
cb = tab.cellWidget(next(r for r, rk in enumerate(rks) if rk[:2] == (0, 0)), 1)
cb.activated.emit(cb.findText("112-168"))
spin()
for tn, u in was.items():
    now = res3.res.cell("107", tn).bq_used
    assert now == ([f"{u[0]}@112-168"] if u[0] in r1 else u), (tn, u, now)
assert sorted(x[1] for x in res3._pending[0] if x[0] == "107") == sorted(
    tn for tn, u in was.items() if u[0] in r1), res3._pending[0]
res3._unpreview()
w3.study.manual.pop()
res3.data_changed.emit({"chosen": kept})
spin()
res3.table.setRangeSelected(QTableWidgetSelectionRange(liver - 1, 1, liver, 2), True)
app.processEvents()
res3.data_changed.emit({"pick_count": "last"})
app.processEvents()
assert w3.study.chosen, "a rule leaves the cells' own picks alone"
res3.data_changed.emit({"pick_count": "first", "chosen": []})
res3.show_rows["tail"].setChecked(True)
assert res3.table.item(res3.table.rowCount() - 1, 1) is not None
res3.close()
w3._move_tissue(w3.study.tissues.index(w3.study.tissue("muscle")), "1")
app.processEvents()
assert w3.study.batch_tissues("direct") == ["muscle", "tumor"], "# reorders within the run"
# the sources' vial strips: a row per file in the sources table, unfolded under it to type
# animal / tissue vial by vial
assert all(x.auto for x in w3.study.sources if x.batch == "direct"), "drawing is no edit"
i = next(k for k, x in enumerate(w3.study.sources) if x.kind == "weigh_count")
t = w3.t_sources
r = w3._srows.index(i)
assert "muscle: 107" in t.item(r, 4).toolTip() and i not in w3._strip_sheets, \
    t.item(r, 4).toolTip()
assert t.item(r, 4).text() == "107, 108, 109" and t.item(r, 5).text() == "direct: all", \
    (t.item(r, 4).text(), t.item(r, 5).text())
assert re.fullmatch(r"\d+ \(\d+\)", t.item(r, 3).text()), t.item(r, 3).text()
w3._source_clicked(r, 0)
app.processEvents()
sh = w3._strip_sheets[i]


def cell(sh, f, k):
    """A strip's cell: field f (0 animal, 1 tissue, 2… read off the file) of vial k."""
    return sh.item(*sh.cells[(f, k)])


assert t.cellWidget(r + 1, 0).findChild(Sheet) is sh and w3._srows[r + 1] is None, \
    "unfolds under its file"
assert t.rowHeight(r + 1) == sh.height() and cell(sh, 1, 0).text() == "muscle"
# three animals' vials: in columns, vial / animal / tissue, a tissue's animals down each
assert sh.columnCount() == 6 and sh.rowCount() == 3, (sh.columnCount(), sh.rowCount())
assert sh.width() <= t.width() and sh.maximumWidth() < 2000
sh.setCurrentCell(*sh.cells[(1, 0)])
cell(sh, 1, 0).setText("TUMOR")                       # case follows the tissue list
app.processEvents()
src = w3.study.sources[i]
assert not src.auto and src.slotmap[sh.vials[0]] == ["107", "tumor"], src.slotmap
# vial 1 placed: the vials after it proposed in grey, the file's order; Tab places them
def key(w, k):
    w.keyPressEvent(QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier))


sh = w3._strip_sheets[i]
keys = sh.vials
prop = w3._proposal[1]
assert w3._proposal[0] == src.uid and prop[keys[1]] == ["108", "tumor"], w3._proposal
assert cell(sh, 1, 1).font().italic() and cell(sh, 0, 1).text() == "108"
assert "Tab" in w3.statusBar().currentMessage()
key(sh, Qt.Key_Tab)          # a hidden table gives Tab to the focus chain: sent as a key
app.processEvents()
assert w3._proposal is None and all(src.slotmap[k] == v for k, v in prop.items())
assert not cell(w3._strip_sheets[i], 1, 1).font().italic()
sh = w3._strip_sheets[i]
sh.setCurrentCell(*sh.cells[(0, 0)])
cell(sh, 0, 0).setText("108")                          # a proposal again, dropped by Esc
app.processEvents()
assert w3._proposal
key(w3._strip_sheets[i], Qt.Key_Escape)
app.processEvents()
assert w3._proposal is None and src.slotmap[keys[1]] == ["108", "tumor"], "Esc places none"
cell(w3._strip_sheets[i], 0, 0).setText("zz")         # not an animal: refused
app.processEvents()
assert src.slotmap[keys[0]][0] == "108"
# a click on a vial drops its list down: the tissues under the animals
sh = w3._strip_sheets[i]
sh.setCurrentCell(*sh.cells[(1, 2)])
sh.itemDelegate().popup = False
sh.editItem(cell(sh, 1, 2))
cb = sh.findChild(QComboBox)
assert cb and cb.count() == len(w3.study.tissues) and cb.currentText() == "tumor", \
    (cb and cb.currentText())
sh.closePersistentEditor(cell(sh, 1, 2))
# Options can add the file's own weight and activity under the vials, read-only
PREFS["strip_rows"] = ["weight", "activity"]           # set here: _set would save them
w3._sync_strips()
app.processEvents()
sh = w3._strip_sheets[i]
assert sh.columnCount() == 10 and re.fullmatch(r"\d+\.\d{4}", cell(sh, 2, 0).text()) and \
    cell(sh, 3, 0).text() and not cell(sh, 3, 0).flags() & Qt.ItemIsEditable, \
    [sh.item(0, c).text() for c in range(sh.columnCount())]
assert sh.horizontalHeaderItem(sh.cells[(3, 0)][1]).text() == "activity (counts)"
PREFS["strip_layout"] = "rows"                         # across: one line, vials side by side
w3._sync_strips()
sh = w3._strip_sheets[i]
assert sh.rowCount() == 5 and sh.verticalHeaderItem(1).text() == "animal", sh.rowCount()
PREFS["strip_layout"] = "auto"
PREFS["strip_rows"] = []
w3._sync_strips()
# the tables take the window's width, the room going to the summaries
w3.resize(1366, 768)
app.processEvents()
assert t.width() > t.minimumWidth() or t.columnWidth(3) > 70, t.width()
tt = w3.t_tissues                                     # the animals' columns stop at 150 px
assert all(tt.columnWidth(c) <= max(150, tt._base[c]) for c in tt._free())
# two columns selected: dragging one sizes both, and the table widens with them
wide = tt.minimumWidth()
tt.clearSelection()
for c in (TC, TC + 1):
    tt.selectionModel().select(tt.model().index(0, c),
                               QItemSelectionModel.Select | QItemSelectionModel.Columns)
tt._set_user({c: 260 for c in tt._cols(TC)})
app.processEvents()
assert [tt.columnWidth(c) for c in (TC, TC + 1)] == [260, 260] and tt.minimumWidth() > wide
w3._sync()                                            # kept through a redraw
assert tt.columnWidth(TC + 1) == 260
for c in (TC, TC + 1):
    tt.selectionModel().select(tt.model().index(0, c),
                               QItemSelectionModel.Select | QItemSelectionModel.Columns)
tt._fit_cols(TC)                                    # a double-click fits both to content
assert tt.columnWidth(TC) < 260 and tt.columnWidth(TC + 1) < 260
tt._user.clear()
# several tissues selected: one batch for all of them
rows = [r for r, (k, f) in enumerate(w3._trows) if not f][:2]
tt.clearSelection()
for r in rows:
    tt.item(r, 0).setSelected(True)
w3._set_batch(w3._trows[rows[0]][0], "pair")
app.processEvents()
assert [w3.study.tissues[w3._trows[r][0]].batch for r in rows] == ["pair", "pair"]
w3.undo()
app.processEvents()
# a file's animals or tissues typed: the whole file goes to them
j = next(k for k, x in enumerate(w3.study.sources) if x.kind == "count")
w3._src_names(t.model().index(w3._srows.index(j), 4), "108")
app.processEvents()
assert (w3.study.sources[j].animals, w3.study.sources[j].auto) == (["108"], False)
assert t.item(w3._srows.index(j), 4).text() == "108"
w3._src_names(t.model().index(w3._srows.index(j), 4), "nobody")      # refused
app.processEvents()
assert w3.study.sources[j].animals == ["108"]
k = next(k for k, x in enumerate(w3.study.sources) if x.kind == "weigh_count")
assert "direct: all" in w3._src_choices(t.model().index(w3._srows.index(k), 5))
w3._src_names(t.model().index(w3._srows.index(k), 5), "direct: tum")   # part of one name
app.processEvents()
assert (w3.study.sources[k].batch, w3.study.sources[k].tissues) == ("direct", ["tumor"])
# (ignored): still listed, greyed, out of the numbers
name = Path(w3.study.sources[j].path).name
assert name in w3.res.spans
w3._src_set(j, "kind", "ignored")
w3._resync_sources()
app.processEvents()
assert name not in w3.res.spans
assert t.item(w3._srows.index(j), 0).foreground().color().name() == "#9a8672"
for _ in range(4):
    w3.undo()
app.processEvents()
assert w3.study.sources[j].kind == "count", w3.study.sources[j].kind
n = len(w3.study.sources)
w3.del_sources([w3._srows.index(n - 1)])             # table rows, strips in between
assert len(w3.study.sources) == n - 1

# the check is a log, oldest first, the newest at the bottom
log = w3.check.toPlainText().splitlines()
assert log == [x[:8] + "  " + x[10:] for x in w3._log], (log[:3], w3._log[:3])
gone = next(k for k, x in enumerate(log) if x.endswith("AutoExport.xlsx removed"))
assert all(x[:8] >= log[gone][:8] for x in log[gone:]), "what the removal changed comes after"
sb = w3.check.verticalScrollBar()
assert sb.value() == sb.maximum()

# a tail left empty on the card but counted: in grey, back at injection time
card = w3.cards[0]
assert w3.study.animals[0].tail_mbq is None and card.e_tail.placeholderText() != "MBq", \
    card.e_tail.placeholderText()
assert card.e_tail_t.placeholderText() == card.e_inj.text(), card.e_tail_t.placeholderText()

# every animal side by side: no rebuild storm, the selector greyed; a pasted column lands
syncs = []
w3._sync = lambda f=w3._sync: (syncs.append(1), f())[1]
aw = w3.animal_win
aw.show_all()
app.processEvents()
assert aw.stack.currentIndex() == 1 and not aw.c_animal.isEnabled() and not syncs, syncs
row = [x[1] for x in aw._rows()].index("injection")
aw.sheet.setCurrentCell(row, aw.SC)
QApplication.clipboard().setText("10:01\t10:02")
aw.sheet.paste()
app.processEvents()
assert [x.inj_time for x in w3.study.animals[:2]] == ["10:01", "10:02"], \
    [x.inj_time for x in w3.study.animals[:2]]
aw.show_animal(0)                                     # a card's ⤢: back to one animal
assert aw.stack.currentIndex() == 0 and aw.c_animal.isEnabled()
aw.close()
w3._keep_or_save = lambda: True

# an animal's ID changed on its card: its files, typed values and picks follow, every view
# names it anew; an ID another animal has is refused
st3 = w3.study
before = w3.res.value(w3._eff, "107", "Liver", "pid_g")
st3.chosen.append(["107", "Liver", "count", st3.sources[-1].path])
c107 = next(c for c in w3.cards if c.a.id == "107")
c107.e_id.setText("A107")
c107.e_id.editingFinished.emit()
app.processEvents()
app.processEvents()
assert st3.animal("A107") and not st3.animal("107"), [a.id for a in st3.animals]
assert all("107" not in s.animals for s in st3.sources), "the files follow"
assert any(x[0] == "A107" for x in st3.chosen), "the picks follow"
assert abs(w3.res.value(w3._eff, "A107", "Liver", "pid_g") - before) < 0.05, "values kept"
heads = [w3.t_tissues.horizontalHeaderItem(c).text() for c in range(w3.t_tissues.columnCount())]
assert any(h.startswith("A107") for h in heads), heads
c108 = next(c for c in w3.cards if c.a.id == "108")
c108.e_id.setText("A107")                                 # taken
c108.e_id.editingFinished.emit()
app.processEvents()
assert st3.animal("108") and [a.id for a in st3.animals].count("A107") == 1

# an empty study: no tables, a + and a line; a recorded tissue list opens from the +
w5 = MainWindow()
assert w5.h_tissues.isVisibleTo(w5) and not w5.t_tissues.isVisibleTo(w5), "no empty table"
assert w5.h_sources.isVisibleTo(w5) and not w5.t_sources.isVisibleTo(w5)
PREFS["tissue_lists"] = {"mine": ["Blood", "Liver", "(empty)"]}
m = QMenu()
w5._tissue_menu(m)
next(a for a in m.actions() if a.text().startswith("mine")).trigger()
assert [x.name for x in w5.study.tissues] == ["Blood", "Liver", "(empty)"]
assert w5.study.tissue("(empty)").role == "blank" and w5.t_tissues.isVisibleTo(w5)
PREFS["tissue_lists"] = {}
w5._keep_or_save = lambda: True

# a Wizard2 file holds no efficiency: CPM in the tissue table until it is typed in Data sources
WZ = DATA.parent / "data_misc" / "wizard2" / "000567.csv"
if WZ.exists():
    from biodist.study import Animal, Tissue  # noqa: E402
    w4 = MainWindow()
    w4.study.animals = [Animal(id=i, full_mbq=10.0, full_time="09:00", inj_time="09:05")
                        for i in ("1", "2")]
    w4.study.tissues = [Tissue(f"t{i}") for i in range(1, 11)]
    w4.add_files([WZ])
    assert w4.res.no_eff == ["Wizard2|Tc-99m"] and w4.t_eff.isVisibleTo(w4), w4.res.no_eff
    r2 = w4._trows.index((1, ""))
    assert w4.t_tissues.item(r2, TC).text().endswith(" CPM"), w4.t_tissues.item(r2, TC).text()
    w4.t_eff.item(0, 3).setText("75 %")
    app.processEvents()
    app.processEvents()
    assert w4.study.efficiency["Wizard2|Tc-99m"][2] == 0.75 and not w4.res.no_eff
    assert w4.t_tissues.item(r2, TC).text().endswith("Bq"), w4.t_tissues.item(r2, TC).text()
    w4._keep_or_save = lambda: True

print("smoke test ok — 260903 read off the results grid, 260923 rack slip placed, Wizard2")
