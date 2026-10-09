"""BioDist main window: the board, and the results grid it opens.

The board is a stack of areas, each with a `+`. Animals across the top, then the tissue
list, then the data sources (counter files, dropped anywhere on the window), then whatever
had to be typed by hand, then a running check of what looks wrong. `study.py` holds the
model and does the arithmetic; nothing here computes anything.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import dataclasses
import datetime as _dt
import functools
import html
import json
import math
import os
import re
import statistics
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import (
    QDate, QEvent, QEventLoop, QItemSelectionModel, QPointF, QRect, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QAction, QColor, QCursor, QIcon, QKeySequence, QPageLayout, QPageSize, QPainter, QPalette,
    QPdfWriter, QPixmap, QShortcut,
    QTextDocument, QTextDocumentWriter,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QCompleter, QDateEdit,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QStackedWidget, QStyle, QStyleOptionViewItem, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTextBrowser,
    QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from shiboken6 import isValid

from . import __version__, hidex, report
from . import study as _study
from .study import (
    NEEDS_ANAESTHESIA, split_modality,
    ANIMAL_MAJOR, ARRIVE_FIELDS, DATE_FORMATS, EVENT_FIELDS, EVENT_NEEDED, FIELD_TIP,
    HALF_LIFE_S, ISOTOPES, KIND_LABEL, KINDS, PRESET_LABEL, ROLE_HELP, STRAINS, TIME_FORMATS,
    TISSUE_MAJOR, TISSUE_ROLES, UNITS, DIGITS, DRIFT_MODES, BASES, TOPS, EMPTY_TUBE, one_top,
    DT_VALID, DT_WARN, Animal, Manual, Result, Source, Study, Tissue,
    age_weeks, at_imaging, at_injection, life_dates, when_views, imaging_label, auto_assign, compute, decay, format_date, format_time,
    guess_role, half_life_s, kind_of, names_summary, next_id, parse_time, propose,
    read_animals, read_column, read_weights, recovery_pct, set_half_lives, strip_summary, tail_pct,
    time_problems, unique_names, born, mid_date, colon_time, carry_fixes, unplaced, stamp,
    parse_age, parse_pi, FIELD_TYPES, fdef, clean_fdef, typed_procedures,
    default_procedures, ev_fields, SPECT_FIELDS, format_pi, time_views, event_time,
)

APP_NAME = "BioDist"
ALL = "(all)"          # what an empty animals/tissues field on a source means

_ACCENT = "#4a9782"
_IGNORED = "#9a8672"     # grey-orange: a file kept in the list, left out
_WARN = QColor("#5a4a22")
_BAD = QColor("#5a2b2b")
_OK_TEXT = "#8fbf8f"
_BLANK = "#b06a2c"          # dark orange: a blank tube's values
_SHARE = Qt.UserRole + 7    # a typed value in the tissue table: (part k, of n) of the cell
_YG = "#a8cb5a"            # yellow-green: worked out, not typed (counted tail, age from arrival)
_ARRIVE = "#d9b44a"         # amber: what ARRIVE asks for

_ALT_KEYS = {"DOB": ("dob", "date of birth"),   # older studies' spellings of a card field
             "injection volume": ("injection volume", "injection volume (ul)",
                                  "injection volume (µl)")}
TC = 5                # the tissue grid's first animal column
PANEL_W = 600              # the Results' side panel, as its count table needs
MIN_VIEW = 480        # the narrowest a results table, a report preview, an animal may get

# the card's fields, in the card's order; Options sets which a new card shows
CARD_KEYS = ["alias", "species", "strain", "genotype", "sex", "DOB", "weight", "isotope",
             "molecule", "injection", "injection volume", "syringe full", "syringe empty",
             "tail", "note"]
_ATTRS = {"alias": ("aliases",), "weight": ("weight_g",), "isotope": ("isotope",),
          "molecule": ("molecule",), "injection": ("inj_time",),
          "syringe full": ("full_mbq", "full_time"), "syringe empty": ("empty_mbq", "empty_time"),
          "tail": ("tail_mbq", "tail_time"), "note": ("note",),
          "procedures": ("events",)}   # the rest live in `extra`

RESULT_UNITS = UNITS + [("src_bq", "activity source"), ("src_mass", "mass source")]
WHOLE = {"bq", "counts"}                 # units shown without decimals, grouped: 26,100,000 Bq
RESULT_ROWS = [("other", "tail and standards"), ("blank", "blanks"),
               ("inj", "injected activity (MBq, at injection)"),
               ("img", "in the animal at SPECT / PET start (MBq)"),
               ("tail", "tail (%IA)"), ("weight", "body weight (g)"),
               ("sum", "sum of tissues (%IA)")]
RESULT_FLAGS = [("mass <= 0", True), ("no mass", True), ("at background", True),
                ("activity in a blank", False), ("under the valid range", False),
                ("over the valid range", False), ("counts differ", False),
                ("weighings differ", False), ("out of the expected range", False)]  # (flag, red?)
FLAG_TIP = {"mass <= 0": "the tube weighs no more than empty: no %IA/g",
            "no mass": "an activity, no mass: no %IA/g",
            "at background": "net counts under 3 σ (the detection limit), or none: nothing to "
                             "tell from the background",
            "activity in a blank": "a blank (control tube, empty vial) counting 1,000 or more: "
                                   "something in it",
            "under the valid range": "the counting in use is under the valid bottom (Options › "
                                     "Rules): no valid one for that vial",
            "over the valid range": "the counting in use is over the valid top — dead time, "
                                    "CPM or activity (Options › Rules): no valid one",
            "counts differ": "the counting in use disagrees with another of the vial, or is "
                             "out of the consensus",
            "weighings differ": "the weighing in use disagrees with another of the tube, or "
                                "is out of the consensus",
            "out of the expected range": "the mass or %IA/g outside what the study expects of "
                                         "the tissue (Options › Rules ▸ Expected per tissue)"}
_OLD_FLAGS = {"low counts": "under the valid range", "dead time": "over the valid range",
              "out of range": "out of the expected range"}     # named so until 2026.10.9

# Options. A JSON file beside BioDist.bat (no registry): read at start, written at every
# change; Options exports and imports the same file.
PREFS = {"isotopes": [list(x) for x in ISOTOPES],                     # name, h
         "strains": [list(x) for x in STRAINS],                          # species, strain, genotype
         "card_fields": [k for k in CARD_KEYS
                         if k not in ("alias", "genotype", "injection volume", "note")],
         "field_all": True, "card_rows": 0,
         "tidy_times": True, "time_format": "HH:MM d+n",
         "tidy_dates": True, "date_format": "DD/MM/YYYY", "tidy_numbers": False,
         "table_rows": 0,
         "strip_rows": [], "strip_activity": "counts", "strip_weight": "g",   # under the vials
         "strip_layout": "auto", "strip_racks": 3,       # ... laid out how, wrapped where
         "source_rounds": True,          # the counting round before a count file's times
         # the rules a new study starts with (a study keeps its own: Options › Results)
         **{k: copy.deepcopy(getattr(Study(), k)) for k in (
             "window_rule", "pick_count", "combine", "min_counts", "min_basis", "max_basis",
             "dt_max", "cpm_max", "valid_counts", "valid_max", "valid_dt", "count_agree",
             "count_tol_pct",
             "count_tol_sigma", "mass_rule",
             "mass_agree", "mass_tol_mg", "mass_tol_pct", "drift_fix", "ref_rule",
             "pick_mass", "pick_bq", "subtract_tail")},
         # the Results' side panel: a row per counting, its window picked in the row (or a
         # row per counting and window); a plain click takes that row alone (or adds it)
         "panel_windows": "pick", "panel_click": "one",
         # the Results window: the units its data list offers (one of each kind, the
         # rest one tick away), its decimals box, what show / highlight offer and tick
         "result_units": [k for k, _ in RESULT_UNITS
                          if k not in ("bq_g", "mbq_g", "bq", "mbq", "mass", "cpm")],
         "result_digits_box": True,
         "result_show": [], "result_show_menu": [k for k, _ in RESULT_ROWS],
         "result_flags": [k for k, _ in RESULT_FLAGS],
         "result_flags_menu": [k for k, _ in RESULT_FLAGS],
         # the fields: how each is typed (text, list, time, date), its list, its example
         "procedures": default_procedures(),   # kind -> its fields (Options › Procedures)
         "tissue_lists": {},             # recorded tissue lists: name -> tissues, in vial order
         "digits": dict(DIGITS), "details_all": False,
         "embed": True,                  # a saved study keeps its files' data (opens without them)
         # the log: what it records, and whether it is written to a file on exit
         "log": {"what": ["checks", "summaries", "files"], "autosave": "off", "folder": "",
                 "naming": "YYMMDD_BioDist"},
         # the tissue table: what a tissue × animal cell shows, the typed rows' units, the line
         # over the table
         "cell_mass": "mg", "cell_value": "bq", "typed_mass": "mg", "typed_activity": "MBq",
         "tissue_note": ["ref", "sources"],
         "report": report.DEFAULT, "report_format": ".xlsx"}
_DEFAULTS = copy.deepcopy(PREFS)
STRIP_ROWS = {"weight": "weight (g)", "activity": "activity"}
LOG_KINDS = {"checks": "checks — what looks wrong, and when it is resolved",
             "summaries": "summaries — each file's placement, each animal's injected activity "
                          "and sum of tissues, as they change",
             "files": "files — opened, saved, added, removed, exported, report written",
             "edits": "edits — every value typed or pasted, animals and tissues added or "
                      "removed, orders changed, guess again, undo / redo"}
LOG_NAMES = ["YYMMDD_BioDist", "YYYY-MM-DD_BioDist", "YYMMDD-hhmmss_BioDist",
             "BioDist_YYYYMMDD"]          # offered; any pattern can be typed
_TOKENS = [("YYYY", "%Y"), ("YY", "%y"), ("MM", "%m"), ("DD", "%d"), ("hh", "%H"),
           ("mm", "%M"), ("ss", "%S")]


def _log_name(folder: Path, start: _dt.datetime, pattern: str) -> str:
    """A session's log file from a pattern (YYYY YY MM DD hh mm ss, the session's start),
    never an earlier file's name: a second one gets .2, then .3 …"""
    fmt = re.sub("|".join(t for t, _ in _TOKENS), lambda m: dict(_TOKENS)[m[0]],
                 pattern.replace("%", "%%"))
    stem = re.sub(r'[\\/:*?"<>|]', "_", start.strftime(fmt)).strip() or "BioDist"
    stem = stem[:-4] if stem.lower().endswith(".log") else stem
    n = 1
    while (folder / (name := f"{stem}{'' if n == 1 else f'.{n}'}.log")).exists():
        n += 1
    return name


LOG_SAVE = {"off": "off — the log goes with the session (Study ▸ Log saves it)",
            "session": "a new file per session",
            "append": "one file, each session added at its end"}
CELL_MASS = {"mg": "mass in mg", "g": "mass in g", "": "no mass"}
CELL_VALUE = {"bq": "activity in MBq / kBq, at the reference time", "counts":
              "counts, as counted", "pid_g": "%IA/g", "pid": "%IA", "": "no activity"}
TISSUE_NOTE = {"ref": "the time the activities are given at",
               "sources": "where the masses and activities come from"}
ACTIVITY_UNITS = {"counts": "counts", "cpm": "CPM", "bq": "Bq"}
# the Results' units, then where each cell's values come from, in words
STRIP_LAYOUTS = {"auto": "auto — across for one animal's file, in columns for a file of "
                         "several animals",
                 "rows": "across: vials side by side, a new line every few racks",
                 "columns": "in columns: vial, animal, tissue, an animal's tissues down each"}


def _strip_cells(racks, extra, how, size) -> dict:
    """Where a file's vials go in its strip: {(field, vial #): (row, column)}, field -1 the
    vial's name, 0 its animal, 1 its tissue, 2… the rows read off the file. "rows": vials
    across, a band of `size` racks per line; "columns": sets of columns side by side,
    `size` vials down each."""
    out, fields = {}, range(-1, 2 + extra)
    if how == "rows":
        order = list(dict.fromkeys(racks))
        used: dict[int, int] = {}
        for i, rk in enumerate(racks):
            b = order.index(rk) // size
            c = used[b] = used.get(b, -1) + 1
            out.update({(f, i): (b * (3 + extra) + f + 1, c) for f in fields})
    else:
        for i in range(len(racks)):
            s, r = divmod(i, size)
            out.update({(f, i): (r, s * (3 + extra) + f + 1) for f in fields})
    return out
APP_DIR = Path(__file__).resolve().parents[2]      # where BioDist.bat is
OPTIONS_FILE = APP_DIR / "biodist_options.json"
OLD_OPTIONS = Path(sys.prefix) / "biodist_options.json"   # until 2026.10.6.1: in the runtime


PUBLIC = Path(os.environ.get("PUBLIC") or r"C:\Users\Public")   # any account writes there


def _here(main, name="") -> str:
    """Where a file dialog opens: the study's own folder, else its first data file's, else
    C:\\Users\\Public — `name` in it."""
    st = getattr(main, "study", None)
    for p in [main._path] + [Path(s.path) for s in st.sources] if st else []:
        if p and Path(p).parent.is_dir():
            return str(Path(p).parent / name)
    return str(PUBLIC / name)


def options_found() -> bool:
    """The options file is there — or one from before 2026.10.6.1 was, and is copied over."""
    if OPTIONS_FILE.exists():
        return True
    try:
        OPTIONS_FILE.write_bytes(OLD_OPTIONS.read_bytes())
        return True
    except OSError:
        return False


def _load_prefs(path: Path | None = None, got=None):
    """Options from a JSON file (or a dict); what is missing or malformed keeps its default."""
    path = path or OPTIONS_FILE
    if got is None:
        try:
            got = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            got = {}
    got = got if isinstance(got, dict) else {}
    num = (int, float)
    for k, v in _DEFAULTS.items():
        g = got.get(k)
        ok = type(g) is type(v) or type(v) in num and type(g) in num
        PREFS[k] = g if ok else copy.deepcopy(v)
    # ponytail: files from before 2026.9.28.1 carry a "listed" tick: the unticked ones go
    PREFS["isotopes"] = [r[:2] for r in PREFS["isotopes"]
                         if isinstance(r, list) and (len(r) == 2 or len(r) == 3 and r[2])]
    for k, n in (("isotopes", 2), ("strains", 3)):
        if not all(isinstance(r, list) and len(r) == n for r in PREFS[k]):
            PREFS[k] = copy.deepcopy(_DEFAULTS[k])
    PREFS["tissue_lists"] = {k: [str(x) for x in v] for k, v in PREFS["tissue_lists"].items()
                             if isinstance(v, list)}
    lists = got.get("lists") if isinstance(got.get("lists"), dict) else {}
    old = got.get("procedure_fields")
    if "procedures" not in got and isinstance(old, dict):     # before 2026.10.6.1: names
        order = [k for k in lists.get("procedure", []) if isinstance(k, str)] + list(old)
        PREFS["procedures"] = typed_procedures({k: [f for f in old.get(k, EVENT_FIELDS.get(
            k, [])) if isinstance(f, str)] for k in dict.fromkeys(order)}, lists)
        have = {f["name"] for f in PREFS["procedures"].get("imaging", [])}
        PREFS["procedures"].get("imaging", []).extend(
            dict(f) for f in SPECT_FIELDS if f["name"] not in have)
    PREFS["procedures"] = {str(k): [f for x in v if (f := clean_fdef(x))]
                           for k, v in PREFS["procedures"].items() if isinstance(v, list)} \
        or default_procedures()
    known = {(r[0], r[1]): r[2] for r in _DEFAULTS["strains"]}   # genotypes shipped since
    PREFS["strains"] = [[sp, st, g or known.get((sp, st), "")] for sp, st, g in PREFS["strains"]] \
        + [list(r) for r in _DEFAULTS["strains"]
           if (r[0], r[1]) not in {(x[0], x[1]) for x in PREFS["strains"]}]
    PREFS["digits"] = {k: int(v) for k, v in {**DIGITS, **PREFS["digits"]}.items()
                       if type(v) in num and k in DIGITS}
    lg = {**_DEFAULTS["log"], **PREFS["log"]}
    lg["what"] = [k for k in LOG_KINDS if k in lg["what"]] if isinstance(lg["what"], list) \
        else list(_DEFAULTS["log"]["what"])
    if PREFS["pick_count"] in ("mean", "median", "pooled"):   # 2026.10.6.1: "all", combined
        if "combine" not in got:
            PREFS["combine"] = "weighted" if PREFS["pick_count"] == "pooled" else "mean"
        PREFS["pick_count"] = "all"
    if "dt_max" not in got and type(got.get("dt_warn")) in num:   # a check until 2026.10.6.1
        PREFS["dt_max"] = got["dt_warn"]
    one_top(PREFS)                               # one top per range since 2026.10.9
    for k in ("result_flags", "result_flags_menu"):
        PREFS[k] = list(dict.fromkeys(_OLD_FLAGS.get(f, f) for f in PREFS[k]))
    PREFS["result_units"] = list(dict.fromkeys(   # "MBq or kBq (as the tissue table)" gone
        "kbq" if u == "act" else u for u in PREFS["result_units"]))
    if PREFS["combine"] not in COMBINE:
        PREFS["combine"] = "mean"
    if lg["autosave"] == "overwrite":            # ponytail: a mode until 2026.10.5.1
        lg["autosave"] = "session"
    if lg["autosave"] not in LOG_SAVE:
        lg["autosave"] = "off"
    lg["naming"] = {"date": LOG_NAMES[0], "time": LOG_NAMES[2]}.get(   # 2026.10.5.1 keys
        lg["naming"], lg["naming"] if isinstance(lg["naming"], str) and lg["naming"].strip()
        else LOG_NAMES[0])
    lg.pop("keep", None)
    for k, table in (("cell_mass", CELL_MASS), ("cell_value", CELL_VALUE),
                     ("typed_mass", {"g": 0, "mg": 0}), ("typed_activity", {"MBq": 0, "kBq": 0})):
        if PREFS[k] not in table:
            PREFS[k] = _DEFAULTS[k]
    PREFS["tissue_note"] = [k for k in TISSUE_NOTE if k in PREFS["tissue_note"]]
    lg["folder"] = str(lg["folder"] or "")
    PREFS["log"] = lg
    PREFS["report"] = report.clean(PREFS["report"])
    if PREFS["report_format"] not in (".odt", ".pdf", ".xlsx", ".md", ".html"):
        PREFS["report_format"] = ".xlsx"
    PREFS["strip_rows"] = [x for x in PREFS["strip_rows"] if x in STRIP_ROWS]
    if PREFS["strip_layout"] not in STRIP_LAYOUTS:
        PREFS["strip_layout"] = "auto"
    if PREFS["strip_activity"] not in ACTIVITY_UNITS:
        PREFS["strip_activity"] = _DEFAULTS["strip_activity"]
    if PREFS["table_rows"] < 5:                  # a table 1 row high hid the tissues
        PREFS["table_rows"] = 0
    for k, table in (("time_format", TIME_FORMATS), ("date_format", DATE_FORMATS)):
        if PREFS[k] not in table:
            PREFS[k] = _DEFAULTS[k]
    set_half_lives((k, h) for k, h in PREFS["isotopes"] if type(h) in num and h > 0)
    if got.get("average") in ("mean", "median"):   # one rule for both until 2026.10.5.3
        PREFS["mass_rule"] = got["average"]
    if PREFS["mass_rule"] not in MASS_RULES:
        PREFS["mass_rule"] = "first"
    if PREFS["pick_count"] not in COUNT_RULES:
        PREFS["pick_count"] = "auto"
    if got.get("drift_fix") is True:            # a tick before 2026.10.5.2
        PREFS["drift_fix"] = "scale"
    if PREFS["ref_rule"] not in ("injection", "time"):    # "study" until 2026.10.5.3
        PREFS["ref_rule"] = "time"
    if PREFS["drift_fix"] not in DRIFT_MODES:
        PREFS["drift_fix"] = ""
    for old, new in (("spread_warn", "count_tol_pct"), ("spread_sigma", "count_tol_sigma"),
                     ("mass_warn_mg", "mass_tol_mg"), ("mass_warn_pct", "mass_tol_pct")):
        if new not in got and type(got.get(old)) in num:      # a check until 2026.10.6.2
            PREFS[new] = got[old]


_PREFS_UNDO: dict[str, list] = {"back": [], "fwd": [], "now": []}


def _save_prefs(path: Path | None = None) -> bool:
    path = path or OPTIONS_FILE
    if path == OPTIONS_FILE:                     # every change saved is a step Ctrl+Z undoes
        now = json.dumps(PREFS, sort_keys=True)
        h = _PREFS_UNDO
        if h["now"] and h["now"][0] != now:
            h["back"].append(h["now"][0])
            h["fwd"].clear()
        h["now"] = [now]
    try:
        path.write_text(json.dumps(PREFS, indent=1, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False


def _prefs_step(back: bool) -> bool:
    """Ctrl+Z / Ctrl+Y in the Options and the Report: the options as they were."""
    h = _PREFS_UNDO
    src, dst = (h["back"], h["fwd"]) if back else (h["fwd"], h["back"])
    if not src:
        return False
    dst.append(h["now"][0])
    h["now"] = [src.pop()]
    _load_prefs(got=json.loads(h["now"][0]))
    try:
        OPTIONS_FILE.write_text(json.dumps(PREFS, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return True


def _new_study() -> Study:
    """A blank study, its data choices from Options: saved with it after, so it reproduces."""
    return Study(date=_dt.date.today().isoformat(), animals=[Animal(id="1")],
                 **{k: copy.deepcopy(PREFS[k]) for k in OptionsWindow.DEFAULTED})


def _shown(time_text, day) -> str:
    """A stored time as the fields show it: tidied if Options says so. The stored text,
    seconds and all, is what gets computed with and saved."""
    return format_time(time_text, day, PREFS["time_format"]) if PREFS["tidy_times"] else \
        str(time_text or "")


def _typed(old, text, day, shown=None) -> str:
    """What a time (or date) field holds after editing: the stored text, unless the text was
    changed from how that is shown."""
    text = colon_time(text).strip()               # 12h39 is stored as 12:39
    return old if text == (shown or _shown)(old, day) else text


def _date_shown(text, day) -> str:
    """A date of birth — one, a range or a list — tidied to the Options format, or as typed."""
    return format_date(text, day, PREFS["date_format"]) if PREFS["tidy_dates"] else \
        str(text or "")


def _num(v, typed="") -> str:
    """A number as it was read — 1.30 stays 1.30, .577 shows 0.577 (never 0.58) — unless
    Options tidies numbers."""
    if v is None:
        return ""
    t = str(typed or "").strip()
    if PREFS["tidy_numbers"] or _f(t) != v:
        return _g(v)
    return re.sub(r"^([-+]?)(?=[.,])", r"\g<1>0", t)


def _put_num(obj, attr, text):
    """A typed number into the model, and the text it was read as beside it."""
    v = _f(text)
    setattr(obj, attr, v)
    if v is None:
        obj.typed.pop(attr, None)
    elif _f(obj.typed.get(attr)) != v:
        obj.typed[attr] = text.strip()
    return v


def _xkey(a: Animal, name) -> str:
    """The key a field is stored under in `extra`: the study's own spelling if it has one."""
    alt = _ALT_KEYS.get(name, (name.lower(),))
    return next((k for k in a.extra if k.lower() in alt), name)


def _get(a: Animal, name) -> str:
    return str(a.extra.get(_xkey(a, name), ""))


def _put(a: Animal, name, value):
    if str(value).strip():
        a.extra[_xkey(a, name)] = str(value).strip()
    else:
        a.extra.pop(_xkey(a, name), None)


def _has(a: Animal, key) -> bool:
    if key in _ATTRS:
        return any(getattr(a, x) not in (None, "", []) for x in _ATTRS[key])
    return bool(_get(a, key).strip())


def _shows(a: Animal, key) -> bool:
    """Whether a card shows a field: as its × or the animal window's "on card" tick left
    it, else if Options lists it. An alias, a genotype or a note shows once it holds
    something; what is filled in the animal window stays off the card until ticked."""
    if key in a.show:
        return a.show[key]
    return key in PREFS["card_fields"] or key in ("alias", "genotype", "note") and _has(a, key)


def _species() -> list[str]:
    return list(dict.fromkeys(sp for sp, _, _ in PREFS["strains"]))


def _strains(species) -> list[str]:
    """The strains of a species; all of them for a species the table does not know."""
    sp = str(species or "").strip().lower()
    mine = [st for s, st, _ in PREFS["strains"] if s.lower() == sp]
    return mine or [st for _, st, _ in PREFS["strains"]]


def _strain_row(species, strain):
    sp, st = str(species or "").lower(), str(strain or "").strip().lower()
    rows = [r for r in PREFS["strains"] if r[1].lower() == st]
    return next((r for r in rows if r[0].lower() == sp), rows[0] if rows else None)


def _set_strain(a: Animal, strain):
    """A strain picked: its species and genotype come along when the table knows them, and
    a genotype typed by hand is not overwritten."""
    old = _strain_row(_get(a, "species"), _get(a, "strain"))
    _put(a, "strain", strain)
    row = _strain_row(_get(a, "species"), strain)
    if row:
        if not _get(a, "species"):
            _put(a, "species", row[0])
        if not _get(a, "genotype") or old and _get(a, "genotype") == old[2]:
            _put(a, "genotype", row[2])


def _set_species(a: Animal, species):
    """A species changed: a strain of another species goes."""
    _put(a, "species", species)
    row = _strain_row("", _get(a, "strain"))
    if row and species.strip() and _get(a, "strain") not in _strains(species):
        _put(a, "strain", "")
        if _get(a, "genotype") == row[2]:
            _put(a, "genotype", "")


def _put_event(ev: dict, key: str, text: str):
    """A procedure's field typed; emptied, a field of its own kind goes (an added one stays)."""
    ev[key] = text.strip()
    if not ev[key] and key in [f["name"] for f in PREFS["procedures"].get(
            ev.get("kind", ""), [])] + ["note"]:
        ev.pop(key)


def _aspec(name: str) -> dict:
    """How one of the animal's fields is typed (fixed: study.ANIMAL_SPECS); not listed: text,
    or a time when its name says so ('sacrifice time')."""
    got = _study.ANIMAL_SPECS.get(name) or next((f for k, f in _study.ANIMAL_SPECS.items()
                                                 if k.lower() == name.lower()), None)
    return got or fdef(name, "time" if _study.timed("", name.lower()) else "text")


def _copy_field(a: Animal, b: Animal, key):
    """One field of `a` onto `b`, the numbers with the text they were read as; a procedure's
    ("ev", kind, n, field) onto b's same procedure (added if b has none)."""
    if isinstance(key, tuple):
        return _list_put(b, key, _list_cell(a, key, None), None)
    for x in _ATTRS.get(key, ()):
        setattr(b, x, copy.deepcopy(getattr(a, x)))
        if x in a.typed:
            b.typed[x] = a.typed[x]
        else:
            b.typed.pop(x, None)
    if key not in _ATTRS:
        b.extra.pop(_xkey(b, key), None)
        if _get(a, key):
            b.extra[_xkey(a, key)] = _get(a, key)


_NUMS = {"weight_g", "full_mbq", "empty_mbq", "tail_mbq"}
_TYPED_UNIT = {"mass_g": ("typed_mass", "mg", "mass_mg"),      # a value typed in the tissue
               "mbq": ("typed_activity", "kBq", "kbq")}         # table, the smaller unit


def _typed_num(m, f) -> str:
    """A typed mass or activity in the unit Options says, as it was typed if it was."""
    if m is None or getattr(m, f) is None:
        return ""
    pref, small, key = _TYPED_UNIT[f]
    if PREFS[pref] == small:
        return _num(getattr(m, f) * 1000, m.typed.get(key))
    return _num(getattr(m, f), m.typed.get(f))


def _events_of(a: Animal, kind) -> list[dict]:
    return [e for e in a.events if e.get("kind") == kind]


_EV_SEP = " · "                          # a procedure's field as a card shows it


def _ev_key(kind, n, f) -> str:
    """A procedure's field under its name on the cards (Animal.show): 'imaging · start', the
    second imaging's 'imaging 2 · start'."""
    return f"{kind or 'other'}{f' {n + 1}' if n else ''}{_EV_SEP}{f}"


def _ev_shown(a: Animal) -> list[tuple[str, tuple, dict]]:
    """The procedures' fields this animal's card shows: (name, ("ev", kind, n, field), spec)."""
    out = []
    for kind in dict.fromkeys(e.get("kind", "") for e in a.events):
        for n, ev in enumerate(_events_of(a, kind)):
            out += [(k, ("ev", kind, n, sp["name"]), sp) for sp in ev_fields(ev, PREFS["procedures"])
                    if _shows(a, k := _ev_key(kind, n, sp["name"]))]
    return out


def _list_cell(a: Animal, key, day) -> str:
    """A cell of the every-animal table for what an animal may hold several of: an other
    loss ("loss", n, mbq | time | what), a note ("bnote", n), a procedure ("ev", kind, n,
    field)."""
    what, n = key[0], key[-2] if key[0] == "ev" else key[1]
    if what == "loss":
        lo = a.losses[n] if n < len(a.losses) else {}
        v = lo.get(key[2], "")
        return _shown(v, day) if key[2] == "time" else v
    if what == "bnote":
        return a.bio_notes[n] if n < len(a.bio_notes) else ""
    evs = _events_of(a, key[1])
    return str(evs[n].get(key[3], "")) if n < len(evs) else ""


def _list_put(a: Animal, key, text, day):
    if key[0] == "loss":
        n, f = key[1], key[2]
        while len(a.losses) <= n:
            a.losses.append({"mbq": "", "time": "", "what": ""})
        a.losses[n][f] = _typed(a.losses[n][f], text, day) if f == "time" else text
        while a.losses and not any(a.losses[-1].values()):
            a.losses.pop()
    elif key[0] == "bnote":
        while len(a.bio_notes) <= key[1]:
            a.bio_notes.append("")
        a.bio_notes[key[1]] = text
        while a.bio_notes and not a.bio_notes[-1]:
            a.bio_notes.pop()
    else:
        _, kind, n, f = key
        while len(_events_of(a, kind)) <= n:
            if not text:
                return
            a.events.append({"kind": kind})
        _put_event(_events_of(a, kind)[n], f, text)


def _cell_text(a: Animal, key, part, day) -> str:
    """One field of an animal as a table cell shows it; `part` 0/1 = a syringe's MBq / time."""
    if isinstance(key, tuple):
        return _list_cell(a, key, day)
    if key == "ID":
        return a.id
    if key == "alias":
        return ", ".join(a.aliases)
    if key in _ATTRS:
        x = _ATTRS[key][part or 0]
        v = getattr(a, x)
        return (_num(v, a.typed.get(x)) if x in _NUMS else _shown(v, day) if x.endswith("time")
                else str(v or ""))
    if key in ("DOB", "arrival"):
        return _date_shown(_get(a, key), day)
    v = _get(a, key)
    return _shown(v, day) if "time" in key.lower() else v


def _cell_put(a: Animal, key, part, text, day):
    """A typed or pasted cell back into the animal."""
    text = str(text or "").strip()
    if isinstance(key, tuple):
        _list_put(a, key, text, day)
    elif key == "ID":
        a.id = text or a.id
    elif key == "alias":
        a.aliases = _csv_list(text)
    elif key == "species":
        _set_species(a, text)
    elif key == "strain":
        _set_strain(a, text)
    elif key in _ATTRS:
        x = _ATTRS[key][part or 0]
        if x in _NUMS:
            _put_num(a, x, text)
        else:
            setattr(a, x, _typed(getattr(a, x), text, day) if x.endswith("time") else text)
    elif key == "DOB":
        _put(a, "DOB", _typed(_get(a, "DOB"), text, day, _date_shown))
    else:
        _put(a, key, _typed(_get(a, key), text, day) if "time" in key.lower() else text)


def _app_icon():
    """The window/taskbar icon, if the bundled .ico is present (made by misc/make_icon.py)."""
    p = Path(__file__).with_name("assets") / "biodist.ico"
    return QIcon(str(p)) if p.exists() else None


def _f(text) -> float | None:
    """A user-typed number, comma or point, blank meaning 'not given'."""
    s = str(text or "").strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _g(v, nd=4) -> str:
    return "" if v is None else f"{v:.{nd}g}"


def _edit(text="", placeholder="", width=0) -> QLineEdit:
    e = QLineEdit(str(text or ""))
    e.setPlaceholderText(placeholder)
    if width:
        e.setFixedWidth(width)
    return e


def _fit(e: QLineEdit, lo=34, hi=150) -> int:
    """A field as wide as what it holds (or its placeholder), within lo-hi px."""
    w = max(lo, min(hi, e.fontMetrics().horizontalAdvance(e.text() or e.placeholderText())
                    + 18))
    e.setFixedWidth(w)
    return w


def _ro(text, color="") -> QTableWidgetItem:
    """A table cell that is read, not typed into."""
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if color:
        it.setForeground(QColor(color))
    return it


class _Combo(QComboBox):
    """Takes the wheel only once clicked into: scrolling the board must not change a row."""

    def wheelEvent(self, ev):
        if self.hasFocus():
            super().wheelEvent(ev)
        else:
            ev.ignore()


class _Checklist(QMenu):
    """A menu of ticks that stays open while they are clicked."""

    def mouseReleaseEvent(self, ev):
        a = self.activeAction()
        if a and a.isCheckable():
            a.trigger()
            return
        super().mouseReleaseEvent(ev)


def _combo(items, current="", editable=False, width=0) -> QComboBox:
    c = _Combo()
    c.setFocusPolicy(Qt.StrongFocus)
    c.setEditable(editable)
    c.addItems(items)
    if current:
        c.setCurrentText(current)
    if width:
        c.setFixedWidth(width)
    return c


_BUSY = [0]


@contextlib.contextmanager
def _busy(win, text="Working…"):
    """While files are read, a study opened, a report written: the window greyed, the
    spinning cursor, a word in the status bar — even when it is quick."""
    _BUSY[0] += 1
    if _BUSY[0] == 1:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        if cw := win.centralWidget():
            cw.setEnabled(False)
        win.statusBar().showMessage(text)
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
    try:
        yield
    finally:
        _BUSY[0] -= 1
        if _BUSY[0] == 0:
            if cw := win.centralWidget():
                cw.setEnabled(True)
                for lay in cw.findChildren(QLayout):     # sized while disabled: stale, else
                    lay.invalidate()                     # the board squeezes, not scrolls
            QApplication.restoreOverrideCursor()


def busy(text):
    """The method runs as `_busy` says."""
    def wrap(fn):
        @functools.wraps(fn)
        def run(self, *a, **k):
            with _busy(self, text):
                return fn(self, *a, **k)
        return run
    return wrap


DRIFT_TIP = (
    "The control tubes (role blank) are weighed empty and then again with the others, with "
    "nothing put in them: they should not change. Every weighing after the tares — the filled "
    "tubes, a count + weight's — is checked by its own file's control tubes; if they read "
    "lighter or heavier (the balance, the tubes' temperature…), every tube of that file is "
    "corrected:\nscale — by the controls' ratio (an error in proportion to the weight, as a "
    "balance's calibration);\noffset — minus the controls' change in mg (the same error on "
    "every tube).\nThe tares are the reference. The median of the file's control tubes is "
    "used; the side panel's mass table shows each file's change (⚖ column), the log says it "
    "too. On tubes of the same size both give the same mass within 0.1 mg. A file without "
    "control tubes is used as weighed.")


COUNT_RULES = {"first": "the first in range", "last": "the last in range",
               "auto": "the one in range with the most counts",
               "all": "every one in range, combined"}
COUNT_TIP = ("Which counting of a vial makes its activity, among those in the target range "
             "(and in the consensus, below): the first (the day's counting), the last, the one "
             "with the most counts, every one combined, or one round. None in the target "
             "range: the same among the valid ones; none valid: the nearest to valid, flagged. "
             "A cell can take others: Results ▸ select it ▸ tick ▸ Apply")
DT_TIP = ("The rule prefers a counting with a dead-time factor up to this: the counter was "
          "busy that share of the time and its correction is less sure (1.1: a tenth; 260903 "
          "tumours at 1.4-2.2 read 4-10 % high)")
VALID_TIP = ("A counting with fewer counts, more than the top, or a higher dead time, is not "
             "valid: flagged, used only when none of the vial's is (then the nearest to "
             "valid), and never in the consensus — a thin late counting does not flag the good "
             "ones. 500 counts: ±8 % from counting alone in the wide window (its background "
             "~180 counts comes off), ±5 % in the photopeak — about the limit of "
             "quantification (misc/extra/261008_validity_threshold.md)")
RULES_SAID = ("The consensus: when more than half of a vial's valid countings (a tube's "
              "weighings) agree with each other — within the % or σ (mg or %) above. One out "
              "of it is flagged in the side panel, and left out before the rule picks when "
              "ticked here: 3 weighings, the day-of one 2 mg over two that agree — the first "
              "of those two is used. Not ticked, or no consensus: the rule picks among all, "
              "and the cell is flagged when the one used is out of it or disagrees. Every "
              "rule is the study's own, saved with it.")
COMBINE = {"weighted": "weighted by their counts", "mean": "their mean"}
PANEL_WINDOWS = {"pick": "a row each, its window picked in the row",
                 "rows": "a row each per energy window"}
PANEL_CLICK = {"one": "takes it alone — Ctrl+click adds or removes it",
               "toggle": "adds or removes it"}
COMBINE_TIP = ("Each counting is first decay-corrected to the same instant. Mean: each counts "
               "the same. Weighted: by its counts as counted — how sure it is (±1/√counts); "
               "decay correction scales the value, not that. 70,968 then 3,406 counts: the "
               "mean takes half of each, weighted 95 % and 5 %. Weighted is the better "
               "estimate when the countings differ in counts")
EFF_TIP = ("A counter turns CPM into Bq with its counting efficiency (counts per decay) — "
           "one per counter, isotope and energy window. A Hidex file carries its own; a "
           "Wizard2 file (or a Hidex one set to 1) none: type it in the table. Untick to type "
           "them for every file. Bq = CPM / 60 / efficiency")
BOTTOM_TIP = ("The bottom of both ranges. counts (the default): counted in the energy window "
              "in use — how sure the value is, ±1/√counts. counts (whole spectrum): in the "
              "file's widest window (15-2047 keV), the same as counts when that is the window "
              "in use. CPM: a rate, blind to the counting time (1,000 CPM is 500 counts in 30 s "
              "or 2,000 in 2 min). Bq, kBq, MBq: the activity in the vial as it was counted "
              "(CPM / 60 / efficiency). Changing it keeps the numbers: retype them")
TOP_TIP = ("The top of both ranges (0: none) — where the counter stops being linear. dead time "
           "(the default): the share of the time it was busy, what its correction rests on. "
           "CPM (whole spectrum): every pulse it had to handle, what makes that dead time. "
           "Bq, kBq, MBq: the activity in the vial (99mTc, 112-168 keV: its efficiency falls "
           "4.6 % from 0.4 to 70 kBq). counts: a longer counting gets more — little use as a "
           "top. One top: any but the dead time means no dead-time bound")
MIN_TIP = ("The rule prefers a counting with at least this many counts (dead time and CPM "
           "allowing): 10,000 counts is ±1 % from the counting statistics. A vial with none "
           "there takes a valid one — not flagged")
MASS_RULES = {"first": "the first (day-of) weighing", "last": "the last weighing",
              "median": "the median of the weighings", "mean": "the mean of the weighings"}
MASS_TIP = ("The same filled tube weighed more than once — on the day, then in a weigh + count "
            "file: which mass to use. The balance repeats within ±0.4 mg, but a weighing can be "
            "off by more (cold or wet tubes on the day): one weighing judged right, or the "
            "median of three or more (robust to one off), beats a mean. Flagged when they differ "
            "(Options › Checks)")


def _bring(win):
    """Shown, in front — and back from the taskbar if it was minimised."""
    win.setWindowState(win.windowState() & ~Qt.WindowMinimized)
    win.show()
    win.raise_()
    win.activateWindow()


def _centred(w) -> QWidget:
    """A widget in the middle of a table cell."""
    box = QWidget()
    h = QHBoxLayout(box)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(w, 0, Qt.AlignCenter)
    return box


def _undo_keys(win, undo, redo):
    """Ctrl+Z, Ctrl+Y and Ctrl+Shift+Z in a window of its own (a field being typed in keeps
    its own undo)."""
    for keys, fn in (("Ctrl+Z", undo), ("Ctrl+Y", redo), ("Ctrl+Shift+Z", redo)):
        QShortcut(QKeySequence(keys), win, fn)


def _csv_list(text: str) -> list[str]:
    """'107, 108' -> ['107','108']; '(all)' or blank -> []."""
    s = str(text or "").strip()
    if not s or s.lower() in (ALL, "all"):
        return []
    return [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]


# --------------------------------------------------------------------------- widgets
class Section(QWidget):
    """A titled area of the board, collapsible, with an optional '+' on the right."""

    add_clicked = Signal()

    def __init__(self, title, add_tip="", parent=None):
        super().__init__(parent)
        self._open = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 8)
        outer.setSpacing(0)

        bar = QWidget()
        bar.setStyleSheet("QWidget{background:#333;border-radius:4px;}")
        h = self.bar = QHBoxLayout(bar)
        h.setContentsMargins(6, 3, 6, 3)
        self._arrow = QToolButton()
        self._arrow.setText("▾")
        self._arrow.setStyleSheet("QToolButton{border:none;font-size:13px;}")
        self._arrow.clicked.connect(self.toggle)
        self._title = QLabel(title)
        self._title.setStyleSheet("font-weight:600;")
        self._note = QLabel("")
        self._note.setStyleSheet("color:#999;")
        h.addWidget(self._arrow)
        h.addWidget(self._title)
        h.addSpacing(8)
        h.addWidget(self._note)
        h.addStretch(1)
        if add_tip:
            b = QToolButton()
            b.setText("+")
            b.setToolTip(add_tip)
            b.setStyleSheet(
                f"QToolButton{{border:1px solid #555;border-radius:3px;padding:0 7px;"
                f"font-weight:bold;color:{_ACCENT};}} QToolButton:hover{{background:#3d3d3d;}}")
            b.clicked.connect(self.add_clicked)
            h.addWidget(b)
        outer.addWidget(bar)

        self.body = QWidget()
        self.inner = QVBoxLayout(self.body)
        self.inner.setContentsMargins(4, 6, 4, 0)
        outer.addWidget(self.body, 1)
        outer.addStretch(0)            # takes the body's share while it is folded away

    def toggle(self):
        self._open = not self._open
        self.body.setVisible(self._open)
        self._arrow.setText("▾" if self._open else "▸")

    def set_note(self, text):
        self._note.setText(text)


class _Field(QWidget):
    """A card field with a tiny × on its top-right corner: it hides the field, the data stay."""

    def __init__(self, w, tip, fn):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w)
        self.x = QToolButton(self)
        self.x.setText("×")
        self.x.setToolTip(tip)
        self.x.setFixedSize(11, 11)
        self.x.setCursor(Qt.PointingHandCursor)
        self.x.setStyleSheet("QToolButton{border:none;padding:0;margin:0;color:#8a8a8a;"
                             "font-size:10px;background:transparent;}"
                             "QToolButton:hover{color:#e08080;}")
        self.x.clicked.connect(fn)

    def resizeEvent(self, ev):
        self.x.move(self.width() - self.x.width(), -2)
        self.x.raise_()
        super().resizeEvent(ev)


def _plus(size=14, color=_ACCENT) -> QIcon:
    """A + drawn as two strokes: dead centre, whatever the font."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor(color))
    pen.setWidthF(max(1.6, size / 8))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    m = size / 2
    p.drawLine(QPointF(m, 2), QPointF(m, size - 2))
    p.drawLine(QPointF(2, m), QPointF(size - 2, m))
    p.end()
    return QIcon(pm)


def _glyph(text) -> QIcon:
    """A character as a small icon, for an action inside a line edit."""
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setPen(QColor(_ACCENT))
    p.drawText(pm.rect(), Qt.AlignCenter, text)
    p.end()
    return QIcon(pm)


class ArrivalPopup(QFrame):
    """What the supplier gives: who, the day the animals came in, their age then."""

    done = Signal()

    def __init__(self, a: Animal, day: _dt.date, parent=None):
        super().__init__(parent, Qt.Popup)
        self.a, self.day = a, day
        self.setFrameShape(QFrame.StyledPanel)
        f = QFormLayout(self)
        self.c_sup = _combo(_aspec("supplier")["items"], "", editable=True, width=170)
        self.c_sup.setCurrentText(_get(a, "supplier"))
        self.d_arr = QDateEdit()
        self.d_arr.setCalendarPopup(True)
        self.d_arr.setDisplayFormat("dd/MM/yyyy")
        got = mid_date(_get(a, "arrival"), day)
        self.d_arr.setDate(QDate(got or day))
        self._dated = got is not None            # untouched and unset: not stored
        self.d_arr.dateChanged.connect(self._update)
        self.e_age = _edit(_get(a, "age at arrival"), "6 wk, 42 d", 170)
        self.e_age.textChanged.connect(self._update)
        self.l_born = QLabel()
        self.l_born.setStyleSheet("color:#8d8d8d;")
        f.addRow("supplier", self.c_sup)
        f.addRow("arrival", self.d_arr)
        f.addRow("age at arrival", self.e_age)
        f.addRow(self.l_born)
        self._update(touched=False)

    def _update(self, *_, touched=True):
        self._dated = self._dated or touched and self.sender() is self.d_arr
        b = born({"arrival": self._arrival(), "age at arrival": self.e_age.text()}, self.day)
        self.l_born.setText(f"born ≈ {b:%d/%m/%Y}" if b else "")

    def _arrival(self) -> str:
        return self.d_arr.date().toPython().isoformat() if self._dated else ""

    def hideEvent(self, e):
        a, before = self.a, dict(self.a.extra)
        _put(a, "supplier", self.c_sup.currentText())
        _put(a, "arrival", self._arrival())
        _put(a, "age at arrival", self.e_age.text())
        if a.extra != before:
            self.done.emit()
        super().hideEvent(e)


class AnimalCard(QFrame):
    """One animal: the fields Options lists or that hold something, each hidden by its ×,
    in one order on every card; ⤢ opens them all in the animal window."""

    changed = Signal()
    rebuild = Signal()
    removed = Signal(object)
    shown = Signal(object, str, bool)      # a field hidden by its × (the note shown by + note)
    expand = Signal(object)
    hop = Signal(object, str, int)         # Tab past a row's end: (animal, row, +1 | -1)

    def __init__(self, animal: Animal, day: _dt.date, parent=None):
        super().__init__(parent)
        self.a, self.day = animal, day
        self.tail_ia = None            # MBq at injection from a counted tail vial, if any
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("AnimalCard{background:#303030;border:1px solid #454545;"
                           "border-radius:5px;}")
        self.setFixedWidth(280)
        self._build()

    @staticmethod
    def _link(text, tip, fn) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setStyleSheet(f"QToolButton{{border:none;color:{_ACCENT};}}")
        b.clicked.connect(fn)
        return b

    def _field(self, key, w, tip="") -> _Field:
        if tip:
            w.setToolTip(tip)
        f = _Field(w, f"Hide {key} — what it holds is kept; the animal window (⤢) shows it "
                      "again: its “on card” tick",
                   lambda: self.shown.emit(self.a, key, False))
        self.fields[key] = f
        return f

    def _build(self):
        a, day = self.a, self.day
        g = QGridLayout(self)
        g.setContentsMargins(8, 6, 8, 8)
        g.setVerticalSpacing(3)
        g.setColumnStretch(1, 1)
        self.fields: dict[str, _Field] = {}
        self.rows: list[tuple[str, list[QWidget]]] = []   # (row, its editors): Tab / Enter
        r = 0

        head = QHBoxLayout()
        self.e_id = _edit(a.id, "ID")
        self.e_id.setStyleSheet("font-weight:600;")
        _fit(self.e_id)                    # as wide as the ID: the alias, age, dose fit beside
        self.e_id.textChanged.connect(lambda _: (_fit(self.e_id), self._place_alias()))
        rm = self.rm = QToolButton()
        rm.setText("×")
        rm.setToolTip("Remove this animal (Ctrl+Z brings it back)")
        rm.setStyleSheet("QToolButton{border:none;color:#c06060;font-weight:bold;}")
        rm.clicked.connect(lambda: self.removed.emit(self.a))
        head.addWidget(self.e_id)
        self.head = head
        self._gap = QWidget()          # the age and the dose to the right, the alias or not
        self._gap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        head.addWidget(self._gap)
        self.l_age = QLabel()
        self.l_age.setStyleSheet("color:#7fc97f;")
        head.addWidget(self.l_age)
        head.addSpacing(4)
        self.l_dose = QLabel()
        head.addWidget(self.l_dose)
        head.addWidget(rm)
        g.addLayout(head, r, 0, 1, 2)
        self.rows.append(("ID", [self.e_id]))
        r += 1

        self.alias_box = QVBoxLayout()
        self.alias_box.setSpacing(3)
        self.e_aliases: list[QLineEdit] = []
        if _shows(a, "alias"):
            self._add_alias(", ".join(a.aliases), focus=False)
        g.addLayout(self.alias_box, r, 0, 1, 2)
        r += 1

        def row(*items):
            """One line of the card: (key, label, widget) side by side, the hidden ones out."""
            nonlocal r
            vis = [(k, lab, w) for k, lab, w in items if _shows(a, k)]
            if not vis:
                return
            lab = QLabel(", ".join(dict.fromkeys(lab for _, lab, _ in vis)))
            lab.setStyleSheet("color:#a0a0a0;")
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            eds = []
            for k, _, w in vis:
                h.addWidget(self._field(k, w))
                eds += [w] if isinstance(w, (QLineEdit, QComboBox)) else w.findChildren(QLineEdit)
            self.rows.append((vis[0][0], eds))
            if all(w.maximumWidth() < 1000 for _, _, w in vis):
                h.addStretch(1)
            g.addWidget(lab, r, 0)
            g.addWidget(box, r, 1)
            r += 1

        def pick(items, key, hint, width=0):
            c = _combo(items, "", editable=True, width=width)
            c.setCurrentText(_get(a, key))
            c.lineEdit().setPlaceholderText(hint)
            return c

        self.c_species = pick(_species(), "species", "species", 76)
        self.c_strain = pick(_strains(_get(a, "species")), "strain", "strain")
        self.c_strain.setToolTip("The strains of this species (Options edits the list); picking "
                                 "one fills in its genotype")
        row(("species", "animal", self.c_species), ("strain", "animal", self.c_strain))
        self.e_geno = _edit(_get(a, "genotype"), "genotype, e.g. Foxn1 nu/nu")
        row(("genotype", "genotype", self.e_geno))
        self.c_sex = pick(["F", "M"], "sex", "sex", 40)
        self.e_dob = _edit(_date_shown(_get(a, "DOB"), day), "DOB or age")
        self.e_dob.setToolTip("Date of birth — gives the age on the study date. A cage born over "
                              "several days: a range (7-26/02/26, 07/02-03/03/26) or a list "
                              "(7/2, 13/2, 26/2/26); the median date gives the age.\n"
                              "Or the age itself: 12 wk, 2.5 mo, 10-12 wk, 84 d")
        self.e_weight = _edit(_num(a.weight_g, a.typed.get("weight_g")), "20.0", 44)
        self.e_weight.setToolTip("Body weight (g) — needed for SUV")
        self.e_dob.addAction(_glyph("▾"), QLineEdit.TrailingPosition).triggered.connect(
            self._arrival)
        self.e_dob.setToolTip(self.e_dob.toolTip() + "\n▾: supplier, arrival date and age "
                              "at arrival — the date of birth follows, in grey")
        row(("sex", "sex", self.c_sex), ("DOB", "DOB", self.e_dob), ("weight", "g", self.e_weight))
        self.c_iso = _combo([k for k, _ in PREFS["isotopes"]], a.isotope,
                            editable=True, width=76)
        self.c_iso.setToolTip("Any isotope can be typed; Options edits the list and the half-lives")
        self.e_mol = _edit(a.molecule, "molecule, e.g. R3B23")
        self.e_mol.setToolTip("Reported as isotope-molecule, e.g. 99mTc-R3B23")
        row(("isotope", "tracer", self.c_iso), ("molecule", "tracer", self.e_mol))

        ex = TIME_FORMATS[PREFS["time_format"]] if PREFS["tidy_times"] else "08:48"
        tw = min(80, max(52, self.fontMetrics().horizontalAdvance(ex) + 12))

        def pair(n, t):
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            e1 = _edit(_num(getattr(a, n), a.typed.get(n)), "MBq")
            e2 = _edit(_shown(getattr(a, t), day), "HH:MM", tw)
            h.addWidget(e1)
            h.addWidget(e2)
            return w, e1, e2

        self.e_inj = _edit(_shown(a.inj_time, day), "HH:MM")
        self.e_vol = _edit(_get(a, "injection volume"), "µL", 54)
        self.e_vol.setToolTip("Injection volume (µL)")
        row(("injection", "injection", self.e_inj), ("injection volume", "injection", self.e_vol))
        w_full, self.e_full, self.e_full_t = pair("full_mbq", "full_time")
        row(("syringe full", "syringe full", w_full))
        w_empty, self.e_empty, self.e_empty_t = pair("empty_mbq", "empty_time")
        row(("syringe empty", "syringe empty", w_empty))
        for i, lo in enumerate(a.losses):
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            e1, e2 = _edit(lo.get("mbq", ""), "MBq"), _edit(_shown(lo.get("time", ""), day),
                                                         "HH:MM", tw)
            h.addWidget(e1)
            h.addWidget(e2)
            w.setToolTip((lo.get("what") or "Other activity that did not go in") + " — read "
                         "by hand, taken off the injected activity")
            e1.editingFinished.connect(lambda i=i, e=e1: self._set_loss(i, "mbq", e.text()))
            e2.editingFinished.connect(lambda i=i, e=e2: self._set_loss(i, "time", e.text(), e))
            lab = QLabel(lo.get("what") or "other loss")
            lab.setStyleSheet("color:#a0a0a0;")
            f = _Field(w, "Remove this loss (Ctrl+Z brings it back)",
                       lambda i=i: (self.a.losses.pop(i), self.changed.emit(),
                                    self.rebuild.emit()))
            g.addWidget(lab, r, 0)
            g.addWidget(f, r, 1)
            self.rows.append((f"loss{i}", [e1, e2]))
            r += 1
        w_tail, self.e_tail, self.e_tail_t = pair("tail_mbq", "tail_time")
        w_tail.setToolTip("Injection-site activity read on the dose calibrator, subtracted from "
                          "the injected activity.\nTyped here it replaces a counted tail vial; "
                          "leave it empty to use the vial.")
        row(("tail", "tail (inj. site)", w_tail))

        # the other fields in one order on every card: related ones together, unlisted last
        rank = {f.lower(): i for i, f in enumerate(ARRIVE_FIELDS)}
        core = {_xkey(a, f).lower() for f in CARD_KEYS}
        for k in sorted((k for k in a.extra if k.lower() not in core),
                        key=lambda k: rank.get(k.lower(), len(rank))):
            v = a.extra.get(k, "")
            sp = _aspec(k)
            e = _edit(_shown(v, day) if sp["type"] == "time" else v, sp["example"])
            e.setToolTip(FIELD_TIP.get(k.lower(), ""))
            e.editingFinished.connect(lambda key=k, ed=e: self._set_extra(key, ed))
            row((k, k, e))
        for k, ek, sp in _ev_shown(a):           # a procedure's field ticked "on card"
            v = _list_cell(a, ek, day)
            e = _edit(_shown(v, day) if sp["type"] == "time" else v, sp["example"])
            e.editingFinished.connect(lambda ek=ek, ed=e, ty=sp["type"]: self._set_ev(ek, ed, ty))
            row((k, k, e))

        # the note spans the card and has no label: it is whatever the user wants it to be
        self.e_note = QPlainTextEdit(a.note)
        self.e_note.setPlaceholderText("note")
        self.e_note.setFixedHeight(54)
        self.e_note.textChanged.connect(
            lambda: setattr(self.a, "note", self.e_note.toPlainText()))
        if _shows(a, "note"):
            g.addWidget(self._field("note", self.e_note), r, 0, 1, 2)
            r += 1

        foot = QHBoxLayout()
        if not _shows(a, "note"):
            foot.addWidget(self._link("+ note", "A free note on this animal", self._open_note))
        foot.addWidget(self._link("+ alias", "Another name for this animal (ear tag, cage "
                                  "code…): the aliases field, comma-separated", self._more_alias))
        foot.addStretch(1)
        foot.addWidget(self._link("⤢", "Open this animal in its own window: every field, "
                                  "what the biodistribution needs first, then ARRIVE; copy a "
                                  "value to the other animals", lambda: self.expand.emit(self.a)))
        g.addLayout(foot, r, 0, 1, 2)
        g.setRowStretch(r + 1, 1)     # spare height goes below the card, not between rows

        for e in (self.e_id, self.e_weight, self.e_dob, self.e_mol, self.e_full, self.e_full_t,
                  self.e_empty, self.e_empty_t, self.e_inj, self.e_tail, self.e_tail_t,
                  self.e_geno, self.e_vol):
            e.editingFinished.connect(self._pull)
        for c in (self.c_iso, self.c_sex):
            c.currentTextChanged.connect(self._pull)
        for c, fn in ((self.c_species, _set_species), (self.c_strain, _set_strain)):
            c.activated.connect(lambda _=0, c=c, fn=fn: self._picked(c, fn))
            c.lineEdit().editingFinished.connect(lambda c=c, fn=fn: self._picked(c, fn))
        for _, eds in self.rows:
            for e in eds:
                e.installEventFilter(self)
                if isinstance(e, QComboBox):
                    e.lineEdit().installEventFilter(self)
        self._show_dose()

    def where(self, w) -> tuple[int, int] | None:
        """(row, column) of an editor on this card."""
        for r, (_, eds) in enumerate(self.rows):
            for c, e in enumerate(eds):
                if w is e or isinstance(e, QComboBox) and w is e.lineEdit():
                    return r, c
        return None

    def focus(self, row: str, col: int) -> bool:
        """Focus a row's editor (col -1: its last); False if the card has no such row."""
        eds = next((eds for k, eds in self.rows if k == row), None)
        if not eds:
            return False
        e = eds[max(-len(eds), min(col, len(eds) - 1))]
        e.setFocus(Qt.TabFocusReason)
        (e.lineEdit() if isinstance(e, QComboBox) else e).selectAll()
        return True

    def eventFilter(self, obj, ev):
        """Tab: the next field of the row, past its end the same row of the next card
        (Shift+Tab back). Enter: the next row down, same column."""
        if ev.type() != QEvent.KeyPress or ev.modifiers() & ~Qt.ShiftModifier:
            return super().eventFilter(obj, ev)
        k, at = ev.key(), self.where(obj)
        if not at or k not in (Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Return, Qt.Key_Enter):
            return super().eventFilter(obj, ev)
        (r, c), (key, eds) = at, self.rows[at[0]]
        if k in (Qt.Key_Return, Qt.Key_Enter):
            if isinstance(obj, QComboBox) or isinstance(obj.parent(), QComboBox):
                combo = obj if isinstance(obj, QComboBox) else obj.parent()
                if combo.view().isVisible():     # the list is open: Enter picks from it
                    return super().eventFilter(obj, ev)
            if r + 1 < len(self.rows):
                (obj.parent() if isinstance(obj.parent(), QComboBox) else obj).clearFocus()
                self.focus(self.rows[r + 1][0], c)
            return True
        step = -1 if k == Qt.Key_Backtab or ev.modifiers() & Qt.ShiftModifier else 1
        if 0 <= c + step < len(eds):
            self.focus(key, c + step)
        else:
            self.hop.emit(self.a, key, step)
        return True

    def _picked(self, combo, fn):
        """Species or strain set: the strain list, the genotype follow — the card redraws."""
        before = dict(self.a.extra)
        fn(self.a, combo.currentText())
        if self.a.extra != before:
            self.changed.emit()
            self.rebuild.emit()

    def _show_dose(self):
        """Yellow once the syringes and the injection time give a dose, green once the
        injection site has been read too."""
        a, day = self.a, self.day
        wk, b = age_weeks(_get(a, "DOB"), day), born(a.extra, day)
        est = wk is None and b is not None
        if est:
            wk = (day - b).days / 7
        self.l_age.setText("" if wk is None else f"{wk:.1f} wk")
        self.l_age.setStyleSheet(f"color:{_YG if est else '#7fc97f'};")
        self.l_age.setToolTip(f"Age on {day:%d %b %Y}, the study date" + (
            " — from the age at arrival" if est else ""))
        self.e_dob.setPlaceholderText(f"{b:%d/%m/%y}" if b else "DOB or age")
        bad = time_problems(a, day)
        for f, e in (("full_time", self.e_full_t), ("empty_time", self.e_empty_t),
                     ("inj_time", self.e_inj), ("tail_time", self.e_tail_t)):
            e.setStyleSheet("border:1px solid #c06060;" if f in bad else "")
            e.setToolTip(bad.get(f, "HH:MM on the study date; another day: 8:47 d1, "
                                    "d+1 08:47, or with its date: 24/9 8:47"))
        tf, te, ti = (parse_time(x, day) for x in (a.full_time, a.empty_time, a.inj_time))
        if a.full_mbq is None or a.empty_mbq is None or not (tf and te and ti):
            self.l_dose.setText("")
            self._place_alias()
            return
        hl = half_life_s(a.isotope) or HALF_LIFE_S["99mTc"]
        mbq = decay(a.full_mbq, tf, ti, hl) - decay(a.empty_mbq, te, ti, hl)
        for lo in a.losses:
            if (x := _f(lo.get("mbq"))) is not None and (tl := parse_time(lo.get("time"), day)):
                mbq -= decay(x, tl, ti, hl)
        tt = parse_time(a.tail_time, day)
        tail = a.tail_mbq is not None and tt is not None
        if tail:
            mbq -= decay(a.tail_mbq, tt, ti, hl)
        elif self.tail_ia is not None:
            mbq -= self.tail_ia
        self.l_dose.setText(f"● {mbq:.3g} MBq")
        self._place_alias()
        self.l_dose.setStyleSheet("color:" + ("#7fc97f" if tail else _YG
                                              if self.tail_ia is not None else "#d9b44a") + ";")
        self.l_dose.setToolTip(f"Injected {mbq:.4g} MBq at {_shown(a.inj_time, day)}" + (
            ", injection site taken off" if tail else
            ", the counted tail vial taken off" if self.tail_ia is not None else
            " — the injection site (tail) is not typed yet"))

    def _place_alias(self):
        """The aliases sit on the ID line, as wide as they are, while the age and the dose
        leave them room (16.png: ID, alias, age, dose on one line); else on a line below,
        the card's width."""
        if not self.e_aliases or not hasattr(self, "rm"):
            return
        e, ed = self.alias_w, self.e_aliases[0]
        sp = h if (h := self.head.spacing()) >= 0 else 6     # -1: the style's, Fusion's 6
        used = (self.e_id.width() + self.l_age.sizeHint().width() + self.l_dose.sizeHint().width()
                + self.rm.sizeHint().width() + 4 + 5 * sp)
        free = self.width() - 16 - used - 4
        need = max(40, ed.fontMetrics().horizontalAdvance(ed.text() or ed.placeholderText())
                   + 18)
        inline = free >= need                # never squeezed out of sight (260903 animal 6)
        if inline:
            ed.setFixedWidth(need)
        else:
            ed.setMinimumWidth(0)
            ed.setMaximumWidth(16777215)
        if (self.head.indexOf(e) >= 0) != inline:
            self.head.removeWidget(e)
            self.alias_box.removeWidget(e)
            if inline:
                self.head.insertWidget(1, e)
            else:
                self.alias_box.insertWidget(0, e)
        self.layout().invalidate()          # the row of cards is sized off this card's hint

    def _set_loss(self, i, f, text, ed=None):
        lo = self.a.losses[i]
        v = _typed(lo.get(f, ""), text, self.day) if f == "time" else text.strip()
        if ed:
            ed.setText(_shown(v, self.day))
        if v != lo.get(f, ""):
            lo[f] = v
            self._show_dose()
            self.changed.emit()

    def _set_extra(self, key, ed):
        text = ed.text()
        if "time" in key.lower():
            text = _typed(self.a.extra.get(key, ""), text, self.day)
            ed.setText(_shown(text, self.day))
        if self.a.extra.get(key, "") != text.strip():
            self.a.extra[key] = text.strip()
        self._show_dose()
        self.changed.emit()

    def _set_ev(self, ek, ed, kind):
        """A procedure's field typed on the card."""
        old = _list_cell(self.a, ek, self.day)
        text = _typed(old, ed.text(), self.day) if kind == "time" else ed.text().strip()
        if kind == "time":
            ed.setText(_shown(text, self.day))
        if text != old:
            _list_put(self.a, ek, text, self.day)
            self.changed.emit()

    def _add_alias(self, text, focus=True):
        """The aliases, comma-separated, in one field; its × hides them (they are kept)."""
        e = _edit(text, "aliases")
        e.setToolTip("Other names for this animal (ear tag, cage code…), comma-separated")
        self.e_aliases = [e]
        self.alias_w = self._field("alias", e)
        self.alias_box.addWidget(self.alias_w)   # _place_alias may move it up
        e.editingFinished.connect(self._pull)
        e.textChanged.connect(lambda _: self._place_alias())
        if focus:
            e.setFocus()

    def _more_alias(self):
        if not self.e_aliases:
            self.shown.emit(self.a, "alias", True)
            return
        e = self.e_aliases[0]
        if e.text().strip():
            e.setText(e.text().strip().rstrip(",") + ", ")
        e.setFocus()
        e.end(False)

    def _open_note(self):
        self.shown.emit(self.a, "note", True)

    def _arrival(self):
        """Supplier, arrival date, age at arrival: the grey date of birth follows."""
        pop = ArrivalPopup(self.a, self.day, self)
        pop.move(self.e_dob.mapToGlobal(self.e_dob.rect().bottomLeft()))
        pop.done.connect(lambda: (self._show_dose(), self.changed.emit()))
        pop.show()

    def _pull(self):
        a, day = self.a, self.day
        a.id = self.e_id.text().strip()
        if self.e_aliases:
            a.aliases = _csv_list(self.e_aliases[0].text())
        a.isotope, a.molecule = self.c_iso.currentText().strip(), self.e_mol.text().strip()
        for f, v in (("sex", self.c_sex.currentText()), ("genotype", self.e_geno.text()),
                     ("injection volume", self.e_vol.text())):
            _put(a, f, v)
        dob = _typed(_get(a, "DOB"), self.e_dob.text(), day, _date_shown)
        _put(a, "DOB", dob)
        self.e_dob.setText(_date_shown(dob, day))
        for f, e in (("weight_g", self.e_weight), ("full_mbq", self.e_full),
                     ("empty_mbq", self.e_empty), ("tail_mbq", self.e_tail)):
            e.setText(_num(_put_num(a, f, e.text()), a.typed.get(f)))
        for f, e in (("full_time", self.e_full_t), ("empty_time", self.e_empty_t),
                     ("inj_time", self.e_inj), ("tail_time", self.e_tail_t)):
            setattr(a, f, _typed(getattr(a, f), e.text(), day))
            e.setText(_shown(getattr(a, f), day))
        self._show_dose()
        self.changed.emit()


class Table(QTableWidget):
    """A plain table that deletes selected rows on Del and copies as TSV on Ctrl+C."""

    delete_rows = Signal(list)
    labelled = False      # a copy takes the header row and column 0 with it
    stretch = ()          # columns that share the room left when the window is wider
    cap = 16777215        # ... up to this wide

    def __init__(self, headers, parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)
        self.setStyleSheet("QTableWidget{gridline-color:#3d3d3d;}")
        self._base: list[int] = []
        self._user: dict[str, int] = {}      # dragged by hand, by header text: kept on refits
        self._sizing = False
        h = self.horizontalHeader()
        h.sectionResized.connect(self._dragged)
        h.sectionHandleDoubleClicked.connect(self._fit_cols)

    def _head(self, c) -> str:
        return self.horizontalHeaderItem(c).text() if self.horizontalHeaderItem(c) else str(c)

    def _cols(self, c) -> list[int]:
        """The column dragged, or every selected column when it is one of them."""
        sel = {i.column() for i in self.selectionModel().selectedColumns()}
        return sorted(sel) if c in sel and self.selectionBehavior() != QAbstractItemView.SelectRows else [c]

    def _dragged(self, c, _old, new):
        if self._sizing or not QApplication.mouseButtons() & Qt.LeftButton \
                or self.horizontalHeader().sectionResizeMode(c) != QHeaderView.Interactive:
            return                              # a drag by hand only, not a refresh
        self._set_user({x: new for x in self._cols(c)})

    def _fit_cols(self, c):
        self._sizing = True                     # Qt already fitted `c`; fit its companions
        for x in self._cols(c):
            self.resizeColumnToContents(x)
        self._sizing = False
        self._set_user({x: self.columnWidth(x) + 12 for x in self._cols(c)})

    def _set_user(self, widths):
        self._sizing = True
        for x, w in widths.items():
            self.setColumnWidth(x, w)
            self._user[self._head(x)] = w
            if x < len(self._base):
                self._base[x] = w
        self._sizing = False
        self._width()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Delete:
            rows = sorted({i.row() for i in self.selectedIndexes()}, reverse=True)
            if rows:
                self.delete_rows.emit(rows)
                return
        if ev.matches(QKeySequence.Copy):
            QApplication.clipboard().setText(self._tsv())
            return
        super().keyPressEvent(ev)

    def _tsv(self) -> str:
        idx = self.selectedIndexes()
        if not idx:
            return ""
        rows = sorted({i.row() for i in idx})
        cols = sorted({i.column() for i in idx})
        if self.labelled and 0 not in cols:
            cols.insert(0, 0)
        out = ["\t".join((self.item(r, c).text() if self.item(r, c) else "") for c in cols)
               for r in rows]
        if self.labelled or self.selectionModel().selectedColumns():   # with the headers
            out.insert(0, "\t".join(self.horizontalHeaderItem(c).text()
                                    if self.horizontalHeaderItem(c) else "" for c in cols))
        return "\n".join(out)

    def fit(self, max_rows=0):
        """As wide and as tall as the content: the page scrolls, not each table on its own —
        unless `max_rows` caps it, then the table scrolls past that many rows."""
        rows = min(max_rows, self.rowCount()) if max_rows else self.rowCount()
        self._cut = rows < self.rowCount()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn if self._cut
                                        else Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sizing = True
        self.resizeColumnsToContents()
        for c in range(self.columnCount()):          # room to type into an empty column
            self.setColumnWidth(c, self._user.get(self._head(c),
                                                  max(self.columnWidth(c) + 12, 70)))
        self._sizing = False
        self._base = [self.columnWidth(c) for c in range(self.columnCount())]
        self._width()
        self.setFixedHeight(max(40, 2 * self.frameWidth() + self.horizontalHeader().height()
                                + sum(self.rowHeight(r) for r in range(rows))))

    def _width(self):
        """Wide enough for every column; a dragged column widens the table with it."""
        if len(self._base) != self.columnCount():
            return                                   # not fitted yet
        w = 2 * self.frameWidth() + sum(self._base) + \
            (self.verticalScrollBar().sizeHint().width() if self._cut else 0)
        if not self.stretch:
            self.setFixedWidth(w)
            return
        free = self._free()
        self.setMinimumWidth(w)
        self.setMaximumWidth(min(16777215, w + sum(max(0, self.cap - self._base[c])
                                                   for c in free)))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._spread()

    def _free(self) -> list[int]:
        return [c for c in self.stretch if c < len(self._base) and self._head(c) not in self._user]

    def _spread(self):
        cols = self._free()
        if len(self._base) != self.columnCount() or not cols:
            return
        extra = max(0, self.viewport().width() - sum(self._base)) // len(cols)
        self._sizing = True
        for c in cols:
            self.setColumnWidth(c, max(self._base[c], min(self._base[c] + extra, self.cap)))
        self._sizing = False

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._spread()


class Sheet(Table):
    """Typed into like a spreadsheet: a value typed with several cells selected goes into
    all of them — a comma list is dealt out along them (107, 108, 109 over six cells:
    107 108 109 107 108 109) —, Ctrl+V pastes a block copied from Excel from the current
    cell on (one value: into every selected cell), Del empties the selected cells.
    `edited` carries every (row, column, text) the user changed; the owner stores them."""

    edited = Signal(list)
    key = None            # the owner's say on a key first: key -> True when it took it

    def __init__(self, headers, parent=None):
        super().__init__(headers, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._busy = False
        self.itemChanged.connect(self._typed)

    def put(self, r, c, text, editable=True, tip="", color=""):
        """A cell set from the model: no `edited` (colouring it would fire one too)."""
        self._busy = True
        it = self.item(r, c) or QTableWidgetItem()
        it.setText(str(text or ""))
        it.setFlags(it.flags() | Qt.ItemIsEditable if editable else
                    it.flags() & ~Qt.ItemIsEditable)
        if tip:
            it.setToolTip(tip)
        if color:
            it.setForeground(QColor(color))
        self.setItem(r, c, it)
        self._busy = False
        return it

    def _cells(self):
        return sorted({(i.row(), i.column()) for i in self.selectedIndexes()
                       if self.item(i.row(), i.column()) is None
                       or self.item(i.row(), i.column()).flags() & Qt.ItemIsEditable})

    def _apply(self, out):
        self._busy = True
        for r, c, v in out:
            (self.item(r, c) or self.put(r, c, "")).setText(v)
        self._busy = False
        if out:
            self.edited.emit(out)

    def _typed(self, it):
        if self._busy:
            return
        cells = self._cells()
        if (it.row(), it.column()) not in cells or len(cells) == 1:
            return self._apply([(it.row(), it.column(), it.text().strip())])
        parts = [p.strip() for p in it.text().split(",")] if "," in it.text() else [it.text()]
        self._apply([(r, c, parts[k % len(parts)].strip()) for k, (r, c) in enumerate(cells)])

    def paste(self):
        text = QApplication.clipboard().text().rstrip("\r\n")
        rows = [line.split("\t") for line in text.splitlines()]
        cells = self._cells()
        if not rows or self.currentRow() < 0:
            return
        if len(rows) == 1 and len(rows[0]) == 1 and len(cells) > 1:
            return self._apply([(r, c, rows[0][0].strip()) for r, c in cells])
        r0, c0 = self.currentRow(), self.currentColumn()
        out = [(r0 + i, c0 + j, v.strip()) for i, row in enumerate(rows)
               for j, v in enumerate(row)
               if r0 + i < self.rowCount() and c0 + j < self.columnCount()]
        self._apply([(r, c, v) for r, c, v in out if not self.item(r, c)
                     or self.item(r, c).flags() & Qt.ItemIsEditable])

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.state() != \
                QAbstractItemView.EditingState:
            return self._apply([(r, c, "") for r, c in self._cells()])
        if ev.matches(QKeySequence.Paste):
            return self.paste()
        if self.key and self.state() != QAbstractItemView.EditingState and self.key(ev.key()):
            return
        super().keyPressEvent(ev)

    def mouseReleaseEvent(self, ev):
        """With a list of names behind it: one plain click on a cell opens the list."""
        super().mouseReleaseEvent(ev)
        d = self.itemDelegate()
        if isinstance(d, _NameDelegate) and ev.button() == Qt.LeftButton and \
                not ev.modifiers() and len(self.selectedIndexes()) == 1 and \
                (it := self.itemAt(ev.position().toPoint())) and it.flags() & Qt.ItemIsEditable:
            d.popup = True
            self.editItem(it)
            d.popup = False


class _Middle(QStyledItemDelegate):
    """A column wider than its widest value (stretched to the window, a long header, dragged)
    keeps its values together in the middle: each drawn as aligned (numbers right, names
    left) in a block as wide as the column's widest, the block centred in the cell — at the
    content's width nothing moves, and the background still fills the cell. `middle(col)`:
    which columns."""

    def __init__(self, view, middle=None):
        super().__init__(view)
        self.middle, self._w = middle, {}
        m = view.model()
        for sig in (m.dataChanged, m.modelReset, m.rowsInserted, m.rowsRemoved,
                    m.columnsInserted, m.columnsRemoved, m.layoutChanged):
            sig.connect(lambda *_: self._w.clear())    # measured again at the next paint

    def _block(self, opt, idx) -> QRect:
        v, c = self.parent(), idx.column()
        if c not in self._w:
            self._w[c] = max((self.sizeHint(QStyleOptionViewItem(opt), idx.siblingAtRow(r))
                              .width() for r in range(v.model().rowCount())
                              if v.columnSpan(r, c) == 1 and v.rowSpan(r, c) == 1), default=0)
        pad = max(0, opt.rect.width() - self._w[c]) // 2
        return opt.rect.adjusted(pad, 0, -pad, 0)

    def _bare(self, p, opt, idx) -> QStyleOptionViewItem:
        """The cell drawn without its text (background, selection); its style option back."""
        o = QStyleOptionViewItem(opt)
        self.initStyleOption(o, idx)
        text, o.text = o.text, ""
        (o.widget.style() if o.widget else QApplication.style()).drawControl(
            QStyle.CE_ItemViewItem, o, p, o.widget)
        o.text = text
        p.save()
        p.setPen(o.palette.color(QPalette.Normal if o.state & QStyle.State_Enabled
                                 else QPalette.Disabled,
                                 QPalette.HighlightedText if o.state & QStyle.State_Selected
                                 else QPalette.Text))
        p.setFont(o.font)
        return o

    def paint(self, p, opt, idx):
        if not (self.middle and self.middle(idx.column())) or not idx.data():
            return super().paint(p, opt, idx)
        o = self._bare(p, opt, idx)
        m = QApplication.style().pixelMetric(QStyle.PM_FocusFrameHMargin, None, o.widget) + 1
        r = self._block(opt, idx).adjusted(m, 0, -m, 0)     # the margins Qt's own text has
        p.drawText(r, o.displayAlignment, o.fontMetrics.elidedText(o.text, Qt.ElideRight,
                                                                   r.width()))
        p.restore()


class _NameDelegate(_Middle):
    """A cell typed from a list, names(index), completed as it is typed (any part of a
    name), the list dropped down when the cell was clicked. With `commit` the text goes to
    commit(index, text) rather than into the cell."""

    def __init__(self, parent, names, commit=None, middle=None):
        super().__init__(parent, middle)
        self.names, self.commit, self.popup = names, commit, False

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.setEditable(True)
        cb.setInsertPolicy(QComboBox.NoInsert)
        cb.addItems(self.names(index))
        cb.completer().setCompletionMode(QCompleter.PopupCompletion)
        cb.completer().setFilterMode(Qt.MatchContains)
        cb.completer().setCaseSensitivity(Qt.CaseInsensitive)
        cb.activated.connect(lambda _: (self.commitData.emit(cb), self.closeEditor.emit(cb)))
        if self.popup:
            QTimer.singleShot(0, cb.showPopup)
        return cb

    def setEditorData(self, cb, index):
        cb.setEditText(index.data() or "")
        cb.lineEdit().selectAll()

    def setModelData(self, cb, model, index):
        if self.commit:
            self.commit(index, cb.currentText().strip())
        else:
            model.setData(index, cb.currentText().strip())


def _run_details(parent, src, run):
    """Everything a file holds, vial by vial: times, weights, and per window the counts."""
    if run is None:
        return
    d = QDialog(parent)
    d.setWindowTitle(Path(src.path).name)
    lay = QVBoxLayout(d)
    info = QLabel(f"{src.path}<br>{html.escape(run.run_type)} · {run.template}"
                  + (f" · started {run.started:%d %b %Y %H:%M}" if run.started else "")
                  + (f" · normalized to {run.normalized_to:%d %b %H:%M}"
                     if run.normalized_to else ""))
    info.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lay.addWidget(info)
    wins = run.windows
    heads = ["vial", "time", "tare (g)", "total (g)", "sample (g)", "dead time"] + \
        [f"{w} {u}" for w in wins for u in ("counts", "CPM", "Bq")]
    rows = [[x.key, f"{x.time:%H:%M:%S}" if x.time else "", x.tare_g, x.total_g, x.sample_g,
             x.dead_time] + [m.get(w) for w in wins for m in (x.counts, x.cpm, x.bq)]
            for x in run.slots]
    # only what the file holds: a tare run is vials and weights, a count run has no masses;
    # a weighing the counter did not tare itself is just "weight"
    keep = [c for c in range(len(heads)) if c == 0 or any(r[c] not in (None, "") for r in rows)]
    if PREFS["details_all"]:
        keep = list(range(len(heads)))
    elif src.kind != "empty" and not any(r[4] is not None for r in rows):
        heads[2 if src.kind == "filled" else 3] = "weight (g)"
    t = Table([heads[c] for c in keep])
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectItems)   # a header click takes a column
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, k in enumerate(keep):
            v = row[k]
            t.setItem(r, c, _ro(v if isinstance(v, str) else "" if v is None else f"{v:.6g}"))
    t.resizeColumnsToContents()
    lay.addWidget(t)
    foot = QHBoxLayout()
    foot.addWidget(QLabel("Click a header for its column, drag across headers for several — "
                          "Ctrl+C copies them with their headers."))
    foot.addStretch(1)
    b = QPushButton("Copy all")
    b.clicked.connect(lambda: (t.selectAll(), QApplication.clipboard().setText(t._tsv())))
    foot.addWidget(b)
    lay.addLayout(foot)
    d.resize(min(1400, max(520, 40 + sum(t.columnWidth(c) for c in range(t.columnCount())))),
             700)
    d.show()


def _sheet_for(w) -> Sheet | None:
    """The Sheet a focused widget belongs to (its viewport, an open editor)."""
    while w is not None and not isinstance(w, Sheet):
        w = w.parentWidget()
    return w


def _short(src) -> str:
    """A source as the side panel names it: the file without its export suffix."""
    return "typed by hand" if src == "manual" else \
        re.sub(r"(-AutoExport)?\.(xlsx|csv)$", "", str(src))


def _act(bq) -> str:
    """An activity as the tissue table shows it: MBq from 0.002 MBq up, kBq below; one
    decimal over 2, two over 0.2, three under."""
    x, unit = (bq / 1e6, "MBq") if abs(bq) >= 2000 else (bq / 1e3, "kBq")
    return f"{x:.{1 if abs(x) > 2 else 2 if abs(x) > 0.2 else 3}f} {unit}"


class _Parts(_Middle):
    """A cell holding "12.3 mg\t1.23 MBq": each part right-aligned in its own share of the
    block (`_Middle`), so the units of a column stand under each other. A value typed by
    hand (`_SHARE`: part k of n) sits in its share, under the value it stands for."""

    def paint(self, p, opt, idx):
        text = idx.data() or ""
        share = idx.data(_SHARE)
        if "\t" not in text and not (share and text):
            return super().paint(p, opt, idx)
        self._bare(p, opt, idx)
        parts = text.split("\t") if "\t" in text else \
            ["" if k != share[0] else text for k in range(share[1])]
        r = (self._block(opt, idx) if self.middle and self.middle(idx.column())
             else opt.rect).adjusted(4, 0, -6, 0)
        w = r.width() // len(parts)
        for k, part in enumerate(parts):
            p.drawText(QRect(r.left() + k * w, r.top(), w if k < len(parts) - 1
                             else r.right() - r.left() - k * w, r.height()),
                       Qt.AlignRight | Qt.AlignVCenter, part)
        p.restore()

    def sizeHint(self, opt, idx):
        size = super().sizeHint(opt, idx)
        parts = (idx.data() or "").split("\t")
        if len(parts) > 1:
            size.setWidth(len(parts) * max(opt.fontMetrics.horizontalAdvance(x) for x in parts)
                          + 8 * len(parts) + 10)
        return size


def _kbq(v) -> str:
    """An activity in kBq, the side panel's: 3-4 figures, no exponent."""
    if v is None:
        return ""
    k = v / 1e3
    return f"{k:,.0f}" if abs(k) >= 1000 else f"{k:,.1f}" if abs(k) >= 10 \
        else f"{k:,.3f}"


def _bq(v) -> str:
    return (f"{v / 1e6:.4g} MBq" if abs(v) >= 1e6 else f"{v / 1e3:.4g} kBq" if abs(v) >= 1e3
            else f"{v:.4g} Bq")


# ------------------------------------------------------------------- results window
class ResultsWindow(QMainWindow):
    """Tissues down, animals across — the array to paste into Excel."""

    ROWS = RESULT_ROWS
    FLAGS = RESULT_FLAGS
    data_changed = Signal(dict)      # study fields the sources panel set
    SUM_TIP = ("The injected activity found in all the collected tissues together. Well under "
               "100 is normal (carcass, excreta, what was not collected);\nfar over 100 means "
               "a file landed on the wrong animal or tissue.")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — results")
        self.resize(1100, 720)
        self.study: Study | None = None
        self.res: Result | None = None

        self.tb = tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addWidget(QLabel("  data  "))
        self.c_unit = _combo([])
        self.c_unit.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._units: list[str] = []              # the keys the data list offers
        self.c_unit.currentIndexChanged.connect(self._unit_set)
        tb.addWidget(self.c_unit)
        self._a_digits = [tb.addWidget(QLabel("  decimals "))]
        self.s_digits = QSpinBox()
        self.s_digits.setKeyboardTracking(False)
        self.s_digits.setRange(0, 8)
        self.s_digits.setSpecialValueText("–")  # at -1: a unit whose format decides
        self.s_digits.setValue(PREFS["digits"]["pid_g"])
        self.s_digits.setToolTip("Decimals shown for this unit — kept for next time, and the "
                                 "report's default")
        self.s_digits.valueChanged.connect(self._digits_set)
        self._a_digits.append(tb.addWidget(self.s_digits))
        tb.addSeparator()
        self.show_rows = self._checklist("show", "Rows under the tissues", self.ROWS,
                                         set(PREFS["result_show"]))
        self._img_seen = False
        self.show_rows["sum"].setToolTip(self.SUM_TIP)
        self.flags = self._checklist("highlight", "Which problems tint a cell (red: no "
                                     "usable value, amber: worth a look)",
                                     [(f, f) for f, _ in self.FLAGS],
                                     set(PREFS["result_flags"]))
        tb.addWidget(_sheet_link("Which animals and tissues show, in which order, under "
                                 "which name", lambda: parent and parent.names_win.open()))
        tb.addSeparator()
        self.a_panel = QAction("sources", self)
        self.a_panel.setCheckable(True)
        self.a_panel.setChecked(True)
        self.a_panel.setToolTip("Show / hide the side panel: where the values come from, for "
                                "every cell and for the one clicked")
        tb.addAction(self.a_panel)
        gap = QWidget()
        gap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(gap)
        for text, tip, fn in (("⧉", "Copy the whole table, animals and tissues included "
                                    "(Ctrl+C copies the selection, with its animals and tissues)",
                               self.copy_all),
                              ("Export…", "Write the table to .xlsx or .csv (Ctrl+E)",
                               self.export)):
            a = QAction(text, self)
            a.setToolTip(tip)
            a.triggered.connect(fn)
            tb.addAction(a)

        self.table = Table([])
        self.table.labelled = True
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)   # header = a column
        self._widths: dict[str, int] = {}       # dragged by the user, kept across refreshes
        self._sizing = False
        self.table.horizontalHeader().sectionResized.connect(self._resized)
        empty = QLabel("Nothing to show yet — drop the counter files, the tissue list and the "
                       "animals on the main window.\nValues appear here as soon as a counting "
                       "lands on an animal.")
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet("color:#8d8d8d;")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(empty)
        self.stack.setMinimumWidth(MIN_VIEW)
        self.stack.setCurrentIndex(1)
        self.panel = QScrollArea()
        self.panel.setWidgetResizable(True)
        self.panel.setFrameShape(QFrame.NoFrame)
        self.panel.setMinimumWidth(330)
        self.panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   # sized to fit
        self.a_panel.toggled.connect(self.panel.setVisible)
        split = QSplitter()
        split.addWidget(self.stack)
        split.addWidget(self.panel)
        split.setStretchFactor(0, 1)
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        self.setCentralWidget(split)
        self._panel_later = QTimer(self)
        self._panel_later.setSingleShot(True)
        self._panel_later.timeout.connect(self._fill_panel)
        self.table.itemSelectionChanged.connect(self._sel_changed)
        self._pending = None          # (picks, cells): ticks shown in the table, not applied
        self._saved = None            # (study, res) as applied, while a preview shows
        self._dropped = ""            # said once, in red: ticks dropped unapplied
        self._said = ""               # … and on the status line
        QShortcut(QKeySequence("Ctrl+E"), self, self.export)
        if parent:
            _undo_keys(self, parent.undo, parent.redo)
        self.statusBar()
        self._apply_prefs()

    def _apply_prefs(self):
        """What Options › Results window says: the units offered (the one shown kept if it
        still is), the decimals box, the show / highlight items in their menus — an item
        not in its menu keeps its tick."""
        units = [k for k, _ in RESULT_UNITS if k in PREFS["result_units"]] or ["pid_g"]
        if units != self._units:
            now = self.unit if self._units else "pid_g"
            self._units = units
            self.c_unit.blockSignals(True)
            self.c_unit.clear()
            self.c_unit.addItems([dict(RESULT_UNITS)[k] for k in units])
            self.c_unit.setCurrentIndex(units.index(now) if now in units else 0)
            self.c_unit.blockSignals(False)
            self._unit_set(redraw=False)
        for a in self._a_digits:
            a.setVisible(PREFS["result_digits_box"])
        for menu, key in ((self.show_rows, "result_show_menu"), (self.flags, "result_flags_menu")):
            for k, a in menu.items():
                a.setVisible(k in PREFS[key])

    def set_unit(self, key):
        """Show `key` — offered from now on if it was not."""
        if key not in self._units:
            PREFS["result_units"] = PREFS["result_units"] + [key]
            self._apply_prefs()
        self.c_unit.setCurrentIndex(self._units.index(key))

    def _checklist(self, text, tip, items, on) -> dict[str, QAction]:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setPopupMode(QToolButton.InstantPopup)
        m = _Checklist(b)
        acts = {}
        for key, label in items:
            a = m.addAction(label)
            a.setToolTip(FLAG_TIP.get(key, ""))
            a.setCheckable(True)
            a.setChecked(key in on)
            a.toggled.connect(self.refresh)
            acts[key] = a
        m.setToolTipsVisible(True)
        b.setMenu(m)
        self.tb.addWidget(b)
        return acts

    def _set(self, say="", **fields):
        """A choice made in the panel, applied once the click that made it is over."""
        QTimer.singleShot(0, lambda: (self.data_changed.emit(fields),
                                      say and self.statusBar().showMessage(say, 8000)))

    def _selected(self) -> list[tuple[Animal, Tissue]]:
        """The tissue cells selected, else the current one."""
        tissues, animals = self._rows(), self.study.output_animals()
        idx = {(i.row(), i.column()) for i in self.table.selectedIndexes()} or \
            {(self.table.currentRow(), self.table.currentColumn())}
        return [(animals[c - 1], tissues[r]) for r, c in sorted(idx, key=lambda x: (x[1], x[0]))
                if 0 <= r < len(tissues) and 1 <= c <= len(animals)]

    def _fill_panel(self):
        """Where the selected cells' values come from: their countings (a row per round and
        window), tares and weighings side by side, ticked where in use, each row's flags
        beside it. A tick shows its result in the table at once; Apply keeps it, another cell
        drops it. Every other cell follows the rules: Options › Results."""
        if self._sizing:
            return
        s, res = self.study, self.res
        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(10, 6, 10, 10)
        top = self.panel.verticalScrollBar().value()
        old = self.panel.takeWidget()
        if old:
            old.deleteLater()
        self.panel.setWidget(root)
        if not s or not res:
            return

        def title(text):
            lab = QLabel(text)
            lab.setStyleSheet(f"font-weight:600;color:{_ACCENT};padding-top:6px;")
            v.addWidget(lab)

        def grey(text):
            lab = QLabel(text)
            lab.setWordWrap(True)
            lab.setStyleSheet("color:#8d8d8d;")
            v.addWidget(lab)
        if self._dropped:                        # said once, where the eye is
            lab = QLabel(self._dropped)
            lab.setWordWrap(True)
            lab.setStyleSheet("color:#e08080;font-weight:600;")
            v.addWidget(lab)
            self._dropped = ""
        cells = self._selected()
        self._ticks = {}
        rules = AnimalCard._link("see the rules", "Options › Results: how every cell's values "
                                 "are made, for this study", self._see_rules)
        if not cells:
            title("Sources")
            grey("Click a value — or select several — to see where it comes from: every counting "
                 "and weighing of it side by side, each one's flags beside it. A click on a row "
                 f"{PANEL_CLICK[PREFS['panel_click']]}: the table shows the result at once, "
                 "Apply keeps it. A cell with its own pick shows in italics; the others follow "
                 "the rules.")
            v.addWidget(rules, 0, Qt.AlignLeft)
            v.addStretch(1)
            self._panel_width()
            return
        one = len(cells) == 1
        keys = [(a.id, t.name) for a, t in cells]
        cs = [res.cell(*k) for k in keys]
        title(f"{cells[0][0].label} / {cells[0][1].name}" if one else
              f"{len(cells)} cells selected")
        if not any(c.alts or c.fulls or c.calib is not None for c in cs):
            grey("No counting or weighing here.")
        for what, head, tip in (
                ("count", "Activity — the countings",
                 "A round: one pass of the counter over the vials (count+weight: weighed in the "
                 "same pass), " + ("a row per energy window" if PREFS["panel_windows"] == "rows"
                                   else "its energy window picked in the row")
                 + ". A click on a row " + PANEL_CLICK[PREFS["panel_click"]] + ". Several: "
                 + COMBINE[s.combine] + " (Options › Results). kBq: decay-corrected to "
                 + ("each animal's injection" if res.refs else f"{res.ref:%d %b %H:%M}")),
                ("empty", "Empty tube — the tare", "What the full tube's weight is taken off; "
                 "several ticked: their median"),
                ("mass", "Mass — the full tube", "Each weighing of the filled tube, and the "
                 "tissue mass it gives (− the tare ticked above). Several ticked: their mean")):
            rows = self._src_rows(what, keys, cs)
            if rows:
                lab = QLabel(f"<b>{head}</b>")
                lab.setToolTip(tip)
                v.addWidget(lab)
                v.addWidget(self._src_table(what, rows, one, keys))
        marked = [k in {tuple(x[:2]) for x in s.empty} for k in keys]
        e = QCheckBox("empty tube — nothing was collected in it")
        e.setCheckState(Qt.Checked if all(marked) else Qt.PartiallyChecked if any(marked)
                        else Qt.Unchecked)
        e.setToolTip("Ticked: no value for these cells, no flag — the tube held nothing (a "
                     "tissue not found or lost). Said in the log and the report's checks. "
                     "BioDist offers it for a tissue weighing about nothing that counts "
                     "background")
        e.clicked.connect(lambda on: (self._unpreview(), self._set(
            empty=[x for x in self.study.empty if tuple(x[:2]) not in keys]
            + ([list(k) for k in keys] if on else []),
            say=("Marked empty" if on else "No longer marked empty") + " — Ctrl+Z in the "
            "main window undoes")))
        v.addWidget(e)
        if not self._ticks:
            v.addStretch(1)
            self._panel_width()
            return
        if self._pending:
            lab = QLabel("In the table, not applied yet — Apply keeps it; another cell, or "
                         "closing the window, drops it.")
            lab.setWordWrap(True)
            lab.setStyleSheet("color:#d9b44a;")
            v.addWidget(lab)
        h = QHBoxLayout()
        self._b_apply = QPushButton("Apply")
        self._b_apply.setEnabled(bool(self._pending))
        self._b_apply.setStyleSheet(f"QPushButton:enabled{{background:{_ACCENT};color:white;"
                                    f"font-weight:600;padding:3px 16px;}}")
        self._b_apply.setToolTip("Keep the ticked countings / weighings for the selected cells "
                                 "(Ctrl+Z in the main window undoes)")
        self._b_apply.clicked.connect(self._apply)
        saved = self._saved[0] if self._saved else s
        own = any(tuple(x[:2]) in keys for x in saved.chosen)
        b_rules = QPushButton("Back to the rules" if own or self._pending else
                              "follow the rules ✓")
        b_rules.setToolTip("Drop the selected cells' own picks (and any ticks not applied): "
                           "the rules decide again" if own else
                           "Drop the ticks not applied: the rules' pick again" if self._pending
                           else "These cells take what the rules pick (Options › Rules) — "
                           "nothing of their own to drop")
        b_rules.setEnabled(own or bool(self._pending))
        b_rules.clicked.connect(lambda: self._to_rules(keys))
        h.addWidget(self._b_apply)
        h.addWidget(b_rules)
        h.addWidget(rules)
        h.addStretch(1)
        v.addLayout(h)
        v.addStretch(1)
        self._panel_width()
        QTimer.singleShot(0, lambda: self.panel.verticalScrollBar().setValue(top))

    def _src_rows(self, what, keys, cs) -> dict:
        """The rows of one source table: row key -> {"label", "wins": {window: {"files": {cell:
        [file]}, "x": {cell: what the row holds for it}}}, "on": {cell: in use}, "w": the
        window shown} — "files" and "x" are the shown window's. A counting row is a round (its
        window picked in the row; Options › Results: a row per window too) or the dose
        calibrator, a weighing row is what it was (tare, weight, count+weight r2, typed) — so
        several cells line up."""
        res, rows = self.res, {}
        apart = PREFS["panel_windows"] == "rows"

        def put(rk, label, k, f, x, on, w="", rule=False):
            r = rows.setdefault(rk, {"label": label, "wins": {}, "on": {}})
            d = r["wins"].setdefault(w, {"files": {}, "x": {}})
            d["files"].setdefault(k, []).append(f)
            d["x"].setdefault(k, x)
            r["on"][k] = r["on"].get(k, False) or on
            if on:
                r.setdefault("used", w)
            if rule:
                r.setdefault("rule", w)
        for k, c in zip(keys, cs):
            if what == "count":
                for y in sorted(c.every, key=lambda y: (y[4] or _dt.datetime.min, y[5])):
                    i = res.round_of(y[0])
                    kind = res.files.get(y[0], ("",))[0]
                    src = y[0] if y[7] else f"{y[0]}@{y[5]}"
                    put((0, i if i is not None else 99, y[0] if i is None else "",
                         apart and not y[7], y[5] if apart else ""),
                        (f"round {i + 1}" if i is not None else _short(y[0]))
                        + (" · count+weight" if kind == "weigh_count" else ""),
                        k, src, (src, *y[1:5], y[6], y[8], y[9], y[10]), src in c.bq_used,
                        y[5], y[7])
                if c.calib is not None:
                    put((1, 0, "", False, ""), "dose calibrator", k, "dose calibrator", (
                        "dose calibrator", c.calib, *[None] * 7),
                        "dose calibrator" in c.bq_used)
            elif what == "empty":
                for j, (n, g) in enumerate(c.empties):
                    put((0, j, ""), "tare" + (f" {j + 1}" if len(c.empties) > 1 else ""),
                        k, n, (n, g), n in c.mass_empty.split(" + "))
            else:
                for n, g, kind in c.fulls:
                    lab = res.weighing_label(n, kind)
                    i = res.round_of(n)
                    put((0 if kind == "filled" else 2 if n == "manual" else 1,
                         i if i is not None else 0, lab), lab, k, n, (n, g, kind),
                        n in c.mass_used)
        for r in rows.values():                  # the window in use, else the rule's
            r["w"] = next(w for w in (r.get("used"), r.get("rule"), *r["wins"]) if w in r["wins"])
            r["files"], r["x"] = r["wins"][r["w"]]["files"], r["wins"][r["w"]]["x"]
        return dict(sorted(rows.items(), key=lambda kv: kv[0]))

    def _src_flag(self, what, k, x) -> tuple[str, int, str]:
        """(level, how many, why) for one counting / weighing of cell k, whether in use or
        not: 'bad' a weighing that cannot be used; 'warn' a counting that is not valid, or a
        measure out of the consensus of its vial's, or that disagrees with another when there
        is none (each says which). A counting out of the target range is no flag: the rule
        takes another if it can."""
        s, res = self.study, self.res
        c = res.cell(*k)
        why = []
        if what == "mass":
            net = self._net(c, x)
            if net is not None and net < -0.005:
                return "bad", 1, "lighter than its empty tube: no tube in that vial — not usable"
            pk = ("mass", x[0])
        elif what == "empty":
            pk = ("tare", x[0])
        else:
            if x[0] == "dose calibrator":
                return "", 0, ""
            if x[2] and s.valid_dt and x[2] > s.valid_dt:
                why.append(f"dead time {x[2]:.2f}: not valid (≤ {s.valid_dt:g}) — the counter "
                           "missed counts, the correction is less sure")
            if x[3] is not None and x[3] < s.valid_counts:
                why.append(f"{x[3]:,.4g} {BASES.get(s.min_basis)}: not valid (≥ "
                           f"{s.valid_counts:,.4g})" + (f" — ±{100 * x[7]:.0f} % from counting "
                                                        "alone" if x[7] and x[7] != math.inf
                                                        else ""))
            if s.valid_max and (x[8] or 0) > s.valid_max:
                why.append(f"{x[8]:,.4g} {TOPS.get(s.max_basis)}: not valid (≤ "
                           f"{s.valid_max:,.4g}) — past where the counter is linear")
            f, w = x[0].rsplit("@", 1) if "@" in x[0] else (x[0], c.rule_w.get(x[0], ""))
            pk = ("count", f, w)
        why += c.pairs.get(pk, [])
        return ("warn" if why else "", len(why), "\n".join(why))

    def _net(self, c, x, tare=None) -> float | None:
        """A weighing's tissue mass: the full tube − the tare (or as it is: typed, self-tared)."""
        if x[2] == "direct":
            return x[1]
        if tare is None:
            ts = [g for n, g in c.empties if n in c.mass_empty.split(" + ")]
            tare = statistics.median(ts) if ts else None
        return None if tare is None else x[1] - tare

    def _src_table(self, what, rows, one, keys) -> QTableWidget:
        """One source table, a tick per row: in use ticked (several cells: half-ticked where
        only some use it), each row's flags in the last column — on hover, why. A click on a
        row picks it (`_src_click`); a counting in several windows has its window in a list."""
        res, s = self.res, self.study
        k0 = keys[0]
        ref = "at injection" if res.refs else f"at {res.ref:%H:%M}"
        wins = what == "count" and len({w for x in rows.values() for w in x["wins"] if w}) > 1
        ctrl = what == "mass" and any(f in res.drift for x in rows.values()
                                      for fs in x["files"].values() for f in fs)
        heads = {"count": ["counting"] + ["keV"] * wins + ["when", "counts", "CPM",
                                                           f"kBq {ref}", "dt"],
                 "empty": ["weighing", "when", "g"],
                 "mass": ["weighing", "when", "g", "− tare (mg)"] + ["⚖ mg"] * ctrl}[what] \
            + ["⚑"]
        t = QTableWidget(len(rows), len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        t.setStyleSheet("QTableWidget{gridline-color:#3d3d3d;}")
        t.viewport().setCursor(Qt.PointingHandCursor)

        def when(f):
            tm = (res.spans.get(f.rsplit("@", 1)[0]) or (None,))[0] if what == "count" else \
                res.files.get(f, ("", None))[1]
            return f"{tm:%d %b %H:%M}" if tm else ""
        for r, (rk, row) in enumerate(rows.items()):
            if one:
                x, f = row["x"][k0], row["files"][k0][0]
                if what == "count":
                    m = next((m for m in s.manual if (m.animal, m.tissue) == k0
                              and m.mbq is not None), None)
                    vals = [(m.time + " · typed") if m and f == "dose calibrator" else
                            f"{x[4]:%d %b %H:%M}" if x[4] else when(f),
                            "" if x[6] is None else f"{x[6]:,.0f}",
                            "" if x[5] is None else f"{x[5]:,.0f}",
                            _kbq(res.at_ref(k0[0], x[1])), "" if not x[2] else f"{x[2]:.3f}"]
                elif what == "empty":
                    vals = [when(f), f"{x[1]:.4f}"]
                else:
                    net = self._net(res.cell(*k0), x)
                    vals = ["typed" if f == "manual" else when(f),
                            "" if x[2] == "direct" else f"{x[1]:.4f}",
                            "" if net is None else f"{net * 1000:,.1f}"] + \
                        [f"{res.drift[f][0]:+.1f}" if f in res.drift else ""] * ctrl
                lvl, n, why = self._src_flag(what, k0, x)
            else:
                n = len(row["files"])
                vals = [res.round_label(rk[1]).split(" · ")[1] if what == "count" and rk[0] == 0
                        and rk[1] != 99 else "", f"{n} of {len(keys)} cells"] + \
                    [""] * (len(heads) - 4 - wins)
                flags = [(k, self._src_flag(what, k, x)) for k, x in row["x"].items()]
                bad = [(k, f) for k, f in flags if f[0]]
                lvl = "bad" if any(f[0] == "bad" for _, f in bad) else "warn" if bad else ""
                n = len(bad)
                why = "\n".join(f"{k[0]} / {k[1]}: {f[2]}".replace("\n", "; ")
                                for k, f in bad[:8])
            if wins:
                vals.insert(0, row["w"])
            it = QTableWidgetItem(row["label"])
            it.setFlags(Qt.ItemIsEnabled)            # the click decides the tick, not Qt
            if lvl != "bad":
                ons = [row["on"].get(k, False) for k in keys if k in row["files"]]
                it.setCheckState(Qt.Checked if ons and all(ons) else
                                 Qt.PartiallyChecked if any(ons) else Qt.Unchecked)
            t.setItem(r, 0, it)
            mark = "✗" if lvl == "bad" else ("⚠" + (f" {n}" if n > 1 else "")) if lvl else ""
            for c, text in enumerate(vals + [mark], start=1):
                x = QTableWidgetItem(text)
                x.setTextAlignment((Qt.AlignRight if 2 + wins <= c < len(heads) - 1
                                    else Qt.AlignLeft) | Qt.AlignVCenter)
                t.setItem(r, c, x)
            files = sorted({f for fs in row["files"].values() for f in fs})
            for c in range(len(heads)):
                t.item(r, c).setToolTip("\n".join(
                    ([why] if why else []) + [_short(f) for f in files[:6]]
                    + (["…"] if len(files) > 6 else [])))
                if lvl:
                    t.item(r, c).setBackground(_BAD if lvl == "bad" else _WARN)
            if ctrl and (f0 := next((f for f in files if f in res.drift), None)):
                mg, pct, on = res.drift[f0]
                it2 = t.item(r, len(heads) - 2)
                it2.setToolTip(f"the control tubes of {_short(f0)}: {mg:+.1f} mg ({pct:+.3f} %) "
                               "against their tares — " + (
                                   "this weighing is corrected by them" if on else
                                   "not corrected (Options › Results ▸ Weighing correction)"))
                if not on:
                    it2.setForeground(QColor("#8d8d8d"))
            if wins and len(row["wins"]) > 1:
                ws = list(row["wins"])
                cb = _combo(ws, row["w"])
                cb.setToolTip("This counting's energy window: another one, and the cells using "
                              "it take it in that window")
                cb.activated.connect(lambda i, r=r, ws=ws, row=row: ws[i] != row["w"] and
                                     self._src_click(what, r, win=ws[i]))
                t.setCellWidget(r, 1, cb)
        t.resizeColumnsToContents()
        if wins:
            t.setColumnWidth(1, max(t.columnWidth(1), max(
                (w.sizeHint().width() for w in t.findChildren(QComboBox)), default=0)))
        t.setFixedHeight(t.horizontalHeader().height() + sum(t.rowHeight(r) for r in
                                                              range(t.rowCount())) + 4)
        t.setMinimumWidth(sum(t.columnWidth(c) for c in range(t.columnCount())) + 4)
        self._ticks[what] = (t, list(rows), rows)
        t.cellClicked.connect(lambda r, c: self._src_click(what, r))
        return t

    def _src_click(self, what, r, add=None, win=None):
        """Row r of a source table clicked, or its window changed to `win`. Each selected
        cell that has the row takes it alone — or, `add` (Ctrl held; or every click, Options
        › Results), with the others it uses, or without it if ticked. A window changed: the
        cells using the row take it in that window, the others keep theirs (none using it:
        a click). Cells without the row, or that would not change, keep what they had. The
        table shows the result at once; Apply keeps it."""
        t, rks, rows = self._ticks[what]
        row, it = rows[rks[r]], t.item(r, 0)
        if it is None or it.data(Qt.CheckStateRole) is None:
            return                                   # a weighing that cannot be used
        if add is None:
            add = PREFS["panel_click"] == "toggle" or bool(
                QApplication.keyboardModifiers() & Qt.ControlModifier)
        files = row["wins"][win]["files"] if win else row["files"]
        off = win is None and add and it.checkState() == Qt.Checked
        used = {"count": lambda c: list(c.bq_used),
                "empty": lambda c: [n for n in c.mass_empty.split(" + ") if n],
                "mass": lambda c: list(c.mass_used)}[what]
        keys = [(a.id, tis.name) for a, tis in self._selected()]
        chosen = list(self.study.chosen)
        swap = win and any(row["on"].get(k) for k in keys)   # only the cells using the row
        for k in keys:
            if k not in files or swap and not row["on"].get(k):
                continue
            now = used(self.res.cell(*k))
            mine = {f for d in row["wins"].values() for f in d["files"].get(k, [])}
            rest = [f for f in now if f not in mine]
            new = (rest + files[k] if swap or add and not off else
                   rest if off else files[k])
            if set(new) == set(now):
                continue
            chosen = [x for x in chosen if not (tuple(x[:2]) == k and x[2] == what)]
            if new:
                chosen.append([*k, what, *new])
        QTimer.singleShot(0, lambda: self._preview(chosen, keys))   # not inside the click

    def _preview(self, chosen, keys):
        """The Results as they would be with these picks — the study untouched until Apply."""
        saved = self._saved[0] if self._saved else self.study
        if chosen == saved.chosen:
            self._unpreview()
        elif self.parent():
            if self._saved is None:
                self._saved = (self.study, self.res)
            self.study, self.res = self.parent().preview(chosen)
            self._pending = (chosen, keys)
        self.refresh()

    def _unpreview(self, say=""):
        """Back to the Results as applied; `say`, in red, why ticks were dropped."""
        if self._saved:
            self.study, self.res = self._saved
        if self._pending and say:
            self._dropped = self._said = say
        self._saved = self._pending = None

    def _sel_changed(self):
        """Another cell selected with ticks not applied: they go, and it is said."""
        if self._sizing:
            return
        keys = [(a.id, t.name) for a, t in self._selected()] if self.study else []
        if self._pending and sorted(keys) != sorted(self._pending[1]):
            names = ", ".join(f"{a} / {t}" for a, t in self._pending[1][:3]) + (
                " …" if len(self._pending[1]) > 3 else "")
            self._unpreview(f"Not applied — the ticks for {names} were dropped (Apply keeps "
                            "them)")
            QTimer.singleShot(0, self.refresh)
            return
        self._panel_later.start()

    def _apply(self):
        if not self._pending:
            return
        chosen, keys = self._pending
        self._unpreview()
        self._set(chosen=chosen, say=f"Applied to {len(keys)} cell(s) — italics in the table; "
                  "Ctrl+Z in the main window undoes")

    def _to_rules(self, keys):
        """The selected cells' own picks go — now, it is a button, not a tick."""
        self._unpreview()
        if not any(tuple(x[:2]) in keys for x in self.study.chosen):
            return self.refresh()                # only ticks not applied: dropped
        self._set(chosen=[x for x in self.study.chosen if tuple(x[:2]) not in keys],
                  say="Back to the rules — Ctrl+Z in the main window undoes")

    def hideEvent(self, ev):
        self._unpreview()                        # closed: nothing half-done stays
        super().hideEvent(ev)

    def _see_rules(self):
        if self.parent():
            self.parent().show_options("Rules")

    def _panel_width(self):
        """The panel never narrower than what it holds: nothing is cut, no sideways scroll —
        the table beside it gives up the room."""
        if w := self.panel.widget():
            # built just now, not shown: its layout counts nothing yet — the tables do
            need = max(330, w.minimumSizeHint().width(), max(
                (x.minimumWidth() for x in w.findChildren(QTableWidget)), default=0) + 20)                 + self.panel.verticalScrollBar().sizeHint().width() + 4
            self.panel.setMinimumWidth(need)
            sp = self.panel.parentWidget()
            if isinstance(sp, QSplitter) and self.panel.width() < need:
                a, b = sp.sizes()
                add = 0
                if self.isVisible() and not self.isMaximized() and self.screen():
                    room = self.screen().availableGeometry().right() - \
                        self.frameGeometry().right()
                    add = max(0, min(need - b, room))     # to the right, the table kept
                    self.resize(self.width() + add, self.height())
                sp.setSizes([max(MIN_VIEW, a + b + add - need), need])

    def _resized(self, c, _old, new):
        if not self._sizing and self.table.horizontalHeaderItem(c):
            self._widths[self.table.horizontalHeaderItem(c).text()] = new

    def show_result(self, study: Study, res: Result):
        self._saved = None                       # what was previewed is no longer the study
        if self._pending:
            self._dropped = "Not applied — the study changed, the ticks were dropped"
        self._pending = None
        self.study, self.res = study, res
        self.refresh()

    @property
    def unit(self) -> str:
        return self._units[max(0, self.c_unit.currentIndex())]

    def _unit_set(self, *_, redraw=True):
        own = self.unit.startswith("src_")       # words
        self.s_digits.blockSignals(True)
        self.s_digits.setMinimum(-1 if own else 0)
        self.s_digits.setValue(-1 if own else 0 if self.unit in WHOLE else
                               PREFS["digits"].get(self.unit, 2))
        self.s_digits.setEnabled(not own and self.unit not in WHOLE)
        self.s_digits.blockSignals(False)
        if redraw:
            self.refresh()

    def _digits_set(self, n):
        if n < 0:
            return
        PREFS["digits"][self.unit] = n
        _save_prefs()
        self.refresh()

    def _rows(self):
        """The output list (Tissues ⤢), then the other roles `show` ticks."""
        keep = ((("tail", "standard") if self.show_rows["other"].isChecked() else ())
                + (("blank",) if self.show_rows["blank"].isChecked() else ()))
        out = self.study.output_tissues()
        return out + [t for t in self.study.tissues if t.role in keep and t not in out]

    @staticmethod
    def _text(s, res, aid, tissue, unit, nd) -> str:
        """A cell as the table shows it."""
        if unit.startswith("src_") or res.cell(aid, tissue).bq_src == EMPTY_TUBE:
            return res.source_label(aid, tissue, "activity" if unit == "src_bq" else "mass")
        v = res.value(s, aid, tissue, unit)
        return "" if v is None else f"{v:,.{nd}f}"

    def refresh(self):
        s, res = self.study, self.res
        if not s or not res:
            return
        self._apply_prefs()
        here = (self.table.currentRow(), self.table.currentColumn())
        ranges = self.table.selectedRanges()
        self.stack.setCurrentIndex(0 if res.cells else 1)
        unit = self.unit
        nd = 0 if unit in WHOLE else PREFS["digits"].get(unit, 2)
        tissues, animals = self._rows(), s.output_animals()
        if not self._img_seen and any(at_imaging(s, res, a.id) for a in s.animals):
            self._img_seen = True                # a first SPECT / PET session: the row shows
            self.show_rows["img"].blockSignals(True)
            self.show_rows["img"].setChecked(True)
            self.show_rows["img"].blockSignals(False)
        img = f"activity in the animal at {imaging_label(s, res)} start (MBq)"
        self.show_rows["img"].setText(img)
        extra = [(k, img if k == "img" else lab) for k, lab in self.ROWS[2:]
                 if self.show_rows[k].isChecked()]
        lit = {f for f, a in self.flags.items() if a.isChecked()}
        red = {f for f, bad in self.FLAGS if bad}
        picked = {tuple(x[:2]) for x in s.chosen}
        self._sizing = True
        self.table.clear()
        self.table.setColumnCount(1 + len(animals))
        self.table.setRowCount(len(tissues) + (len(extra) + 1 if extra else 0))
        self.table.setHorizontalHeaderLabels(
            ["tissue"] + [s.column_label(a) or "?" for a in animals])

        for r, t in enumerate(tissues):
            head = QTableWidgetItem(s.tissue_label(t.name)
                                    + ("  (tail)" if t.role == "tail" else ""))
            head.setToolTip(t.role)
            if t.role != "tissue":
                head.setForeground(QColor("#999"))
            self.table.setItem(r, 0, head)
            for c, a in enumerate(animals, start=1):
                cell = res.cell(a.id, t.name)
                it = QTableWidgetItem(self._text(s, res, a.id, t.name, unit, nd))
                if not unit.startswith("src_"):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if cell.bq_src == EMPTY_TUBE:            # marked so: no value, said in grey
                    it.setForeground(QColor("#777"))
                if self._saved and it.text() != self._text(*self._saved, a.id, t.name, unit, nd):
                    it.setForeground(QColor(_OK_TEXT))     # what the ticks give, not applied
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                src_m = res.source_label(a.id, t.name, "mass") or "none"
                src_a = res.source_label(a.id, t.name, "activity") or "none"
                tip = [f"{a.label} / {t.name}",
                       f"mass {_g(cell.mass_g)} g  ({src_m})",
                       f"activity {_g(res.at_ref(a.id, cell.bq))} Bq at "
                       f"{res.ref_of(a.id):%d %b %H:%M}  ({src_a})"]
                if cell.dead_time:
                    tip.append(f"dead time factor {cell.dead_time:.3f}")
                for src, bq, dt, n, *_ in cell.alts:
                    tip.append(f"    {src}: {bq:,.0f} Bq"
                               + (f", dt {dt:.3f}" if dt else "")
                               + (f", {n:,.4g} {BASES.get(s.min_basis)}" if n is not None else ""))
                if len(cell.mass_alts) > 1:
                    tip += [f"    {src}: {g:.4g} g" for src, g in cell.mass_alts]
                if cell.flags:
                    tip.append("⚠ " + "; ".join(cell.flags))
                if self._saved and it.font().bold():
                    tip.append(f"was {self._text(*self._saved, a.id, t.name, unit, nd)} — "
                               "not applied (side panel ▸ Apply)")
                if (a.id, t.name) in picked:
                    tip.append("source picked by hand (side panel)")
                    font = it.font()
                    font.setItalic(True)
                    it.setFont(font)
                it.setToolTip("\n".join(tip))
                shown = {k for k in lit for f in cell.flags if f.startswith(k)}
                if shown:
                    it.setBackground(_BAD if shown & red else _WARN)
                self.table.setItem(r, c, it)

        for r, (key, label) in enumerate(extra, start=len(tissues) + 1):
            it = QTableWidgetItem(label)
            it.setForeground(QColor("#9fb8c8"))
            if key == "sum":
                it.setToolTip(self.SUM_TIP)
            self.table.setItem(r, 0, it)
            for c, a in enumerate(animals, start=1):
                tip = ""
                if key == "inj":
                    v = at_injection(s, res, a.id, res.injected_bq.get(a.id))
                    txt = "" if v is None else f"{v / 1e6:,.2f}"
                elif key == "img":
                    got = at_imaging(s, res, a.id)
                    txt = " / ".join(f"{bq / 1e6:,.2f}" for _, _, bq in got)
                    tip = "\n".join(f"{m} at {t:%d %b %H:%M}: {bq / 1e6:.4g} MBq"
                                    for m, t, bq in got) or \
                        "No SPECT / PET session with a start time — animal window, Procedures"
                elif key == "tail":
                    v = tail_pct(s, res, a.id)
                    txt = "" if v is None else f"{v:,.2f}"
                    mbq = at_injection(s, res, a.id, res.tail_bq.get(a.id))
                    tip = "" if mbq is None else f"{mbq / 1e6:.3g} MBq at injection"
                elif key == "weight":
                    txt = _g(a.weight_g)
                else:
                    v = recovery_pct(s, res, a.id)
                    txt = "" if v is None else f"{v:,.1f}"
                cell = QTableWidgetItem(txt)
                cell.setToolTip(tip)
                cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                cell.setForeground(QColor("#9fb8c8"))
                self.table.setItem(r, c, cell)

        self.table.resizeColumnsToContents()
        for c in range(self.table.columnCount()):
            hd = self.table.horizontalHeaderItem(c).text()
            self.table.setColumnWidth(c, self._widths.get(
                hd, max(90 if c else 0, self.table.columnWidth(c) + 32)))
        if here[0] >= 0:
            self.table.setCurrentCell(*here, QItemSelectionModel.NoUpdate)
        for rg in ranges:                        # a selection survives a recompute
            self.table.setRangeSelected(rg, True)
        self._sizing = False
        self._fill_panel()
        lab = dict(RESULT_UNITS)[unit]
        # only Bq depends on the instant: %IA, SUV take dose and tissue to the same one
        self.statusBar().showMessage(
            f"{len(tissues)} tissues × {len(animals)} animals in {lab}"
            + ((" — at each animal's injection time" if res.refs else
                f" — at {res.ref:%d %b %Y %H:%M}"
                + ("" if s.ref_time else ", the first counting's reference"))
               if unit in ("bq", "bq_g") else ""))
        if self._said:                           # ticks dropped: that, not the counts
            self.statusBar().showMessage(self._said, 10000)
            self._said = ""

    def fit_window(self):
        """As big as the table, within the screen — no empty acres, no cut columns."""
        t = self.table
        w = (2 * t.frameWidth() + t.verticalScrollBar().sizeHint().width() + 60
             + sum(t.columnWidth(c) for c in range(t.columnCount())))
        h = (2 * t.frameWidth() + t.horizontalHeader().height() + 60
             + sum(t.rowHeight(r) for r in range(t.rowCount()))
             + self.tb.sizeHint().height() + self.statusBar().sizeHint().height())
        scr = self.screen().availableGeometry()
        w += max(self.panel.minimumWidth(), PANEL_W) + 8 if self.panel.isVisible() or \
            self.a_panel.isChecked() else 0
        self.resize(min(max(w, self.tb.sizeHint().width()), scr.width() - 40),
                    min(h, scr.height() - 60))

    def _grid(self) -> list[list[str]]:
        out = [[self.table.horizontalHeaderItem(c).text()
                for c in range(self.table.columnCount())]]
        for r in range(self.table.rowCount()):
            out.append([(self.table.item(r, c).text() if self.table.item(r, c) else "")
                        for c in range(self.table.columnCount())])
        return out

    def copy_all(self):
        QApplication.clipboard().setText("\n".join("\t".join(r) for r in self._grid()))
        self.statusBar().showMessage("Copied — paste straight into Excel", 4000)

    def export(self):
        if not self.res:
            return
        name = f"{self.study.name or 'biodist'}_{self.unit}"
        path, _ = QFileDialog.getSaveFileName(self, "Export results", _here(self.parent(), name),
                                              "Excel (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        grid = self._grid()
        try:
            if path.lower().endswith(".csv"):
                with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                    csv.writer(fh).writerows(grid)
            else:
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = dict(RESULT_UNITS)[self.unit].replace("/", " per ")
                for row in grid:
                    ws.append([_f(v) if i and _f(v) is not None else v
                               for i, v in enumerate(row)])
                wb.save(path)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not write the file:\n{e}")
            return
        self.statusBar().showMessage(f"Written to {path}", 6000)
        self.parent().log(f"results exported: {Path(path).name} ({self.unit})")


# -------------------------------------------------------------------- animal window
class AnimalWindow(QMainWindow):
    """One animal, every field: what the biodistribution needs, then what ARRIVE asks for,
    then the rest, in the card's order; its procedures (injections before or with the
    tracer, imaging, tumour cells, diet…) as a table. Any field can be copied to the other
    animals. ▦ shows every animal side by side, a table typed and pasted into like Excel."""

    GROUPS = [
        ("Biodistribution info", "#e08080",
         ["weight", "isotope", "molecule", "injection", "injection route", "injection volume",
          "syringe full", "syringe empty", "tail"]),
        ("ARRIVE 2.0 — reported with the study", "#d9b44a",
         ["species", "strain", "genotype", "sex", "DOB", "supplier", "arrival",
          "protocol", "housing", "health status", "euthanasia", "euthanasia time"]),
    ]
    SC = 1                                   # the table view: field, animals, copy, on card
    COL_W = 150                              # an animal's column in it
    OPTIONAL = {"injection volume",          # in the first group, not needed for the values
                "arrival", "health status"}  # the other way to a date of birth; nice to have
    PAIRED = {"age", "age at arrival"}       # on the DOB's and the arrival's line
    LABEL = {"weight": "body weight (g)", "syringe full": "syringe full (MBq, at)",
             "syringe empty": "syringe empty (MBq, at)", "tail": "tail (MBq, at)",

             "injection": "injection time", "alias": "aliases", "DOB": "date of birth · age",
             "arrival": "arrival · age at arrival", "injection volume": "injection volume (µL)",
             "euthanasia time": "euthanasia time · p.i."}

    def __init__(self, main):
        super().__init__(main)
        self.main, self.i = main, 0
        self.setWindowTitle(f"{APP_NAME} — animal")
        self.resize(760, 820)
        self.setMinimumWidth(MIN_VIEW)          # as narrow as the Results' table may get
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        self.a_prev = tb.addAction("◀", lambda: self.show_animal(self.i - 1))
        self.a_prev.setToolTip("Previous animal")
        self.c_animal = _combo([], width=180)
        self.c_animal.activated.connect(self.show_animal)
        self.a_combo = tb.addWidget(self.c_animal)
        self.a_next = tb.addAction("▶", lambda: self.show_animal(self.i + 1))
        self.a_next.setToolTip("Next animal")
        tb.addSeparator()
        self.a_table = tb.addAction("▦ every animal")
        self.a_table.setCheckable(True)
        self.a_table.toggled.connect(self._toggle_table)
        self.a_table.setToolTip("Every animal side by side: type with several cells selected "
                                "to fill them all, paste a row copied from Excel (injection "
                                "times, aliases…)")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.sheet = Sheet([])
        self.sheet.edited.connect(self._sheet_edited)
        self._drawn = []
        self.stack = QStackedWidget()
        self.stack.addWidget(self.scroll)
        self.stack.addWidget(self.sheet)
        self.setCentralWidget(self.stack)
        _undo_keys(self, lambda: self._step(True), lambda: self._step(False))
        self.statusBar()

    @property
    def a(self) -> Animal:
        return self.main.study.animals[self.i]

    def show_animal(self, i):
        if not self.main.study.animals:
            return self.close()
        self.i = max(0, min(i, len(self.main.study.animals) - 1))
        if self.a_table.isChecked():             # a card's ⤢: that animal on its own
            self.a_table.setChecked(False)       # toggled: redrawn
        else:
            self.refresh(force=True)
        self.show()
        self.raise_()
        self.activateWindow()

    def _groups(self, a: Animal):
        """[(title, colour, keys)]: the two groups, then the rest in the card's order."""
        listed = {k.lower() for _, _, keys in self.GROUPS for k in keys} | self.PAIRED
        rest = ["alias", "group"] + [f for f in ARRIVE_FIELDS if f.lower() not in listed
                                     and f != "group"]
        seen = listed | {x.lower() for x in rest} | {_xkey(a, k).lower() for k in CARD_KEYS}
        for b in self.main.study.animals:        # a field filled on any animal is a row
            for k in b.extra:
                if k.lower() not in seen:
                    rest.append(k)
                    seen.add(k.lower())
        rest.append("note")
        return self.GROUPS + [("Other", "#9a9a9a", rest)]

    def show_all(self):
        """Every animal side by side, the table view."""
        if not self.main.study.animals:
            return
        if self.a_table.isChecked():
            self.refresh(force=True)
        self.a_table.setChecked(True)            # toggled: the table view
        self.show()
        self.raise_()
        self.activateWindow()

    def _toggle_table(self, on):
        for x in (self.a_prev, self.a_combo, self.a_next):
            x.setEnabled(not on)
        self.stack.setCurrentIndex(int(on))
        self.refresh(force=True)
        if on:                                   # every column in view, within the screen
            scr = self.screen().availableGeometry()
            self.resize(min(max(self.width(), self._table_width()), scr.width() - 40),
                        self.height())

    def refresh(self, force=False):
        """Redrawn from the model — not while it is being typed in: its own edits are there."""
        st = self.main.study
        if not force and (not self.isVisible() or self.isActiveWindow()):
            return
        if not st.animals:
            return self.close()
        self.i = min(self.i, len(st.animals) - 1)
        self.c_animal.blockSignals(True)
        self.c_animal.clear()
        self.c_animal.addItems([x.label or "?" for x in st.animals])
        self.c_animal.setCurrentIndex(self.i)
        self.c_animal.blockSignals(False)
        if self.a_table.isChecked():
            return self._fill_sheet()
        a = self.a

        root = QWidget()
        g = QGridLayout(root)
        g.setColumnStretch(1, 1)
        g.setVerticalSpacing(4)
        r = 0
        head = QLabel("on card")
        head.setStyleSheet("color:#8d8d8d;")
        head.setToolTip("Whether the animal's card shows the field (the data are kept either "
                        "way). Off until ticked, but for what Options puts on every card")
        g.addWidget(head, r, 3)
        r += 1
        e = _edit(a.id, "ID", 120)
        e.setStyleSheet("font-weight:600;")
        e.editingFinished.connect(self._commit(lambda: setattr(a, "id", e.text().strip())))
        g.addWidget(QLabel("ID"), r, 0)
        g.addWidget(e, r, 1)
        r += 1
        for name, color, keys in self._groups(a):
            t = QLabel(name)
            t.setStyleSheet(f"font-weight:600;color:{color};padding-top:10px;")
            g.addWidget(t, r, 0, 1, 4)
            r += 1
            for key in keys:
                lab = QLabel(self.LABEL.get(key, key))
                need = name != "Other" and key not in self.OPTIONAL and not _has(a, key) \
                    and not (key == "DOB" and life_dates(a.extra, self.main.study.day)["age"])
                tint = _ARRIVE if key in ("weight", "injection route") else color  # ARRIVE
                lab.setStyleSheet(f"color:{tint};" if need else "color:#b0b0b0;")
                lab.setToolTip(FIELD_TIP.get(key.lower(), "") + ("\nEmpty — " + (
                    "the values need it" if tint == "#e08080" else "ARRIVE asks for it")
                    if need else ""))
                box = QWidget()
                h = QHBoxLayout(box)
                h.setContentsMargins(0, 0, 0, 0)
                for w in self._editors(a, key):
                    h.addWidget(w)
                g.addWidget(lab, r, 0)
                g.addWidget(box, r, 1)
                g.addWidget(self._copy_button(key), r, 2)
                on = QCheckBox()
                on.setChecked(_shows(a, key))
                on.toggled.connect(lambda v, key=key: self.main._show_field(self.a, key, v))
                g.addWidget(on, r, 3, Qt.AlignCenter)
                r += 1
            if name == self.GROUPS[0][0]:
                r = self._bio_more(g, r)
        r = self._procedures(g, r)
        g.setRowStretch(r, 1)
        top = self.scroll.verticalScrollBar().value()
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        for c in root.findChildren(QComboBox):   # a long list item must not widen the window
            c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(12)
        self.scroll.setWidget(root)
        self.scroll.verticalScrollBar().setValue(top)
        gaps = sum(1 for _, c, keys in self.GROUPS for k in keys
                   if k not in self.OPTIONAL and not _has(a, k))
        self.statusBar().showMessage(f"{a.label}: {gaps} of the highlighted fields still empty"
                                     if gaps else f"{a.label}: every highlighted field filled")

    def _bio_more(self, g, r) -> int:
        """Under the biodistribution info: the other losses of the dose and the notes, as
        many as needed, each with its ×; + loss / note adds one."""
        a, day = self.a, self.main.study.day

        def x_button(fn, tip):
            x = QToolButton()
            x.setText("×")
            x.setToolTip(tip + " (Ctrl+Z brings it back)")
            x.setStyleSheet("QToolButton{border:none;color:#8d8d8d;}")
            x.clicked.connect(lambda: (fn(), self._redraw()))
            return x
        for i, lo in enumerate(a.losses):
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            eds = [_edit(lo.get("mbq", ""), "MBq", 110), _edit(_shown(lo.get("time", ""), day),
                                                               "HH:MM", 130),
                   _edit(lo.get("what", ""), "what: cotton on the tail…")]
            for f, e in zip(("mbq", "time", "what"), eds):
                e.editingFinished.connect(self._commit(
                    lambda i=i, f=f, e=e: _list_put(a, ("loss", i, f), e.text(), day)))
                h.addWidget(e)
            lab = QLabel("other loss (MBq, at)")
            lab.setStyleSheet("color:#b0b0b0;")
            lab.setToolTip("Activity that did not go in, read by hand — taken off the "
                           "injected activity, like the empty syringe")
            g.addWidget(lab, r, 0)
            g.addWidget(box, r, 1)
            g.addWidget(x_button(lambda i=i: a.losses.pop(i), "Remove this loss"), r, 2)
            r += 1
        for i, text in enumerate(a.bio_notes):
            e = _edit(text, "a note on this animal's biodistribution")
            e.editingFinished.connect(self._commit(
                lambda i=i, e=e: _list_put(a, ("bnote", i), e.text(), day)))
            lab = QLabel("note")
            lab.setStyleSheet("color:#b0b0b0;")
            g.addWidget(lab, r, 0)
            g.addWidget(e, r, 1)
            g.addWidget(x_button(lambda i=i: a.bio_notes.pop(i), "Remove this note"), r, 2)
            r += 1
        add = QToolButton()
        add.setText("+ loss / note")
        add.setPopupMode(QToolButton.InstantPopup)
        add.setStyleSheet(f"QToolButton{{border:none;color:{_ACCENT};}} QToolButton::menu-indicator{{image:none;}}")
        m = QMenu(add)
        m.setToolTipsVisible(True)
        m.addAction("other loss (MBq, at)", lambda: (a.losses.append(
            {"mbq": "", "time": "", "what": ""}), self._redraw())).setToolTip(
            "Activity that did not go in, read by hand (a cotton held on the tail…): on the "
            "card under the empty syringe, taken off the injected activity")
        m.addAction("note", lambda: (a.bio_notes.append(" "), self._redraw()))
        add.setMenu(m)
        g.addWidget(add, r, 1, Qt.AlignLeft)
        return r + 1

    def _procedures(self, g, r) -> int:
        """ARRIVE item 9 beyond the tracer: one block per procedure — an injection before or
        with it (blocking, Gelofusine…), an imaging session, tumour cells, surgery… — each
        with its kind's fields (Options, Procedures) and any added to it."""
        a = self.a
        t = QLabel("Procedures")
        t.setStyleSheet("font-weight:600;color:#d9b44a;padding-top:10px;")
        t.setToolTip("Reported under ARRIVE item 9, one line per procedure")
        g.addWidget(t, r, 0)
        add = QToolButton()
        add.setText("+ procedure")
        add.setPopupMode(QToolButton.InstantPopup)
        add.setStyleSheet(f"QToolButton{{border:none;color:{_ACCENT};}} QToolButton::menu-indicator{{image:none;}}")
        m = QMenu(add)
        for k in list(PREFS["procedures"]) + ["other…"]:
            m.addAction(k, lambda k=k: self._add_event("" if k == "other…" else k))

        add.setMenu(m)
        g.addWidget(add, r, 1, Qt.AlignLeft)
        g.addWidget(self._copy_button("procedures"), r, 2)
        r += 1
        for ev in a.events:
            head = QWidget()
            h = QHBoxLayout(head)
            h.setContentsMargins(0, 6, 0, 0)
            if ev.get("kind"):
                k = QLabel(ev["kind"])
                k.setStyleSheet("font-weight:600;padding-top:6px;")
            else:                                    # "other…": the kind is typed
                k = _edit("", "kind: minipump, blocking…", 200)
                k.editingFinished.connect(lambda ev=ev, k=k: k.text().strip() and (
                    ev.update(kind=k.text().strip()), self._redraw()))
            h.addStretch(1)
            x = QToolButton()
            x.setText("×")
            x.setToolTip("Remove this procedure (Ctrl+Z in the main window brings it back)")
            x.setStyleSheet("QToolButton{border:none;color:#8d8d8d;}")
            x.clicked.connect(lambda _=0, ev=ev: (a.events.remove(ev), self._redraw()))
            h.addWidget(x)
            g.addWidget(k, r, 0)
            g.addWidget(head, r, 1)
            r += 1
            res = self.main.res
            start = event_time(a, ev.get("start") or ev.get("when", ""), self.main.study.day)
            for m, t, bq in (at_imaging(self.main.study, res, a.id) if res else []):
                if ev.get("kind") == "imaging" and t == start:
                    h.insertWidget(1, QLabel(f"<span style='color:{_YG}'>{bq / 1e6:.3g} MBq "
                                             f"in the animal at {t:%H:%M}</span>"))
                    break
            kind = ev.get("kind", "")
            nth = [e is ev for e in _events_of(a, kind)].index(True)   # its kind's nth
            own = {f["name"] for f in PREFS["procedures"].get(kind, [])}
            watched = {f["when"].split("=")[0].strip() for f in PREFS["procedures"].get(
                kind, []) if "=" in f["when"]}           # fields others show by
            rows: list[tuple[str, list[dict]]] = []      # fields sharing a line: one row
            for sp in ev_fields(ev, PREFS["procedures"]):
                if sp["line"] and rows and rows[-1][0] == sp["line"]:
                    rows[-1][1].append(sp)
                else:
                    rows.append((sp["line"] or sp["name"], [sp]))
            for label, group in rows:
                need = [sp["name"] for sp in group if sp["name"] in EVENT_NEEDED.get(kind, [])
                        and not ev.get(sp["name"])]
                lab = QLabel("   " + label)
                lab.setStyleSheet("color:#d9b44a;" if need else "color:#b0b0b0;")
                if need:
                    lab.setToolTip(f"Empty — ARRIVE asks for it: {', '.join(need)}")
                box = QWidget()
                hl = QHBoxLayout(box)
                hl.setContentsMargins(0, 0, 0, 0)
                for sp in group:
                    if len(group) > 1:
                        n = QLabel(sp["name"])
                        n.setStyleSheet("color:#8d8d8d;")
                        hl.addWidget(n)
                    for x in self._field_widgets(a, sp, lambda ev=ev, f=sp["name"]: ev.get(
                            f, ""), lambda v, ev=ev, f=sp["name"]: _put_event(ev, f, v),
                            redraw=sp["name"] in watched):
                        hl.addWidget(x, 1)
                g.addWidget(lab, r, 0)
                g.addWidget(box, r, 1)
                f = group[0]["name"]
                if len(group) == 1 and f not in own and f != "note":
                    x = QToolButton()                    # a field added to this one alone
                    x.setText("×")
                    x.setToolTip(f"Remove {f} from this procedure (Ctrl+Z brings it back)")
                    x.setStyleSheet("QToolButton{border:none;color:#c06060;}")
                    x.clicked.connect(lambda _=0, ev=ev, f=f: (ev.pop(f, None), self._redraw()))
                    hl.addWidget(x)
                eks = [("ev", kind, nth, sp["name"]) for sp in group]   # copied, shown together
                g.addWidget(self._copy_button(eks, label=f"{kind or 'other'} {label}"), r, 2)
                on = QCheckBox()
                on.setChecked(all(_shows(a, _ev_key(*k[1:])) for k in eks))
                on.toggled.connect(lambda v, eks=eks: [self.main._show_field(
                    self.a, _ev_key(*k[1:]), v) for k in eks])
                g.addWidget(on, r, 3, Qt.AlignCenter)
                r += 1
            g.addWidget(self._more_field(ev), r, 1, Qt.AlignLeft)
            r += 1
        return r

    def _more_field(self, ev) -> QWidget:
        """+ field under a procedure: a click opens a box for the new field's name, Enter
        adds it, Esc or leaving it empty puts the + field back."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        b = AnimalCard._link("+ field", "A field for this procedure only — Options › "
                             "Procedures sets the fields every procedure of a kind opens "
                             "with", lambda: None)
        e = _edit("", "name of the field, Enter", 200)
        e.hide()
        h.addWidget(b)
        h.addWidget(e)
        b.clicked.connect(lambda: (b.hide(), e.show(), e.setFocus()))

        def done():
            name = e.text().strip()
            e.hide()
            b.show()
            if name and name not in ev:
                ev[name] = ""
                self._redraw()
        e.editingFinished.connect(done)
        return w

    def _field_widgets(self, a, sp, get, put, redraw=False) -> list[QWidget]:
        """A field's editors by its type (Options): a date with the age and D-n, a time with
        the time p.i., a list, or text — the example in grey while empty. `redraw`: another
        field shows or not by this one's value."""
        if sp["type"] == "date":
            return [self._when(a, get, put)]
        if sp["type"] == "time":
            return self._clock(a, get, put)
        if sp["type"] == "list":
            c = _combo(sp["items"], "", editable=True)
            c.setCurrentText(get())
            c.lineEdit().setPlaceholderText(sp["example"])
            c.setToolTip("Options lists these; anything can be typed")
            # its line edit says "finished" as its own list opens: a redraw then (a field
            # others show by) took the combo, and the list with it — only on a change
            done = self._commit(lambda: c.currentText() != get() and (
                put(c.currentText()), self._split(a),
                redraw and QTimer.singleShot(0, self._redraw)))
            c.activated.connect(done)
            c.lineEdit().editingFinished.connect(done)
            return [c]
        e = _edit(get(), sp["example"])
        e.editingFinished.connect(self._commit(lambda: put(e.text())))
        return [e]

    def _clock(self, a, get, put) -> list[QLineEdit]:
        """A time on the study day two ways — the clock time, the time after this animal's
        injection ('2 h p.i.') — one typed, the other worked out (grey)."""
        day = self.main.study.day
        e, e2 = _edit("", "", 0), _edit("", "", 0)
        e.setToolTip("The clock time: 13:10 (another day: 13:10 d+1) — or type the time after "
                     "the injection beside it; one gives the other (grey)")
        e2.setToolTip("After the injection: 2 h p.i., 45 min, 1h30 — or type the clock time")

        def show():
            text = get()
            inj = parse_time(a.inj_time, day) if a.inj_time else None
            v = time_views(text, inj, day)
            pi = parse_pi(text) is not None
            e.setText("" if pi else _shown(text, day))
            e2.setText(text if pi else "")
            e.setPlaceholderText(f"{v['time']:%H:%M}" if pi and v["time"] else "HH:MM")
            e2.setPlaceholderText(format_pi(v["pi"]) if not pi and v["pi"] is not None else
                                  "2 h p.i." if inj or not text.strip() else "no injection time")

        def typed_pi():
            t = e2.text().strip()
            if t and parse_pi(t) is None:
                self.statusBar().showMessage(f"{t!r}: not a time after the injection — 2 h, "
                                             "45 min, 1h30", 6000)
                return
            put(t if not t or re.search(r"(?i)p\.?\s*i\.?|before", t) else f"{t} p.i.")
        show()
        e.editingFinished.connect(self._commit(lambda: e.text().strip() != _shown(get(), day) and (
            put(_typed(get(), e.text(), day)), show())))
        e2.editingFinished.connect(self._commit(lambda: e2.text().strip() != (
            get() if parse_pi(get()) is not None else "") and (typed_pi(), show())))
        return [e, e2]

    def _when(self, a, get, put) -> QWidget:
        """A procedure's day three ways — date, the animal's age, days from the study day —
        one typed, the other two worked out (grey)."""
        day = self.main.study.day
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        eds = [_edit("", "", 0) for _ in range(3)]
        for e, tip in zip(eds, ("The date", "The animal's age that day (needs its date of "
                                "birth or age)", "Days from the study day: D-14, D+2")):
            e.setToolTip(tip + " — type any one of the three, the others follow (grey)")
            h.addWidget(e)

        def show():
            text = get()
            v = when_views(text, life_dates(a.extra, day)["DOB"], day)
            mine = (2 if re.fullmatch(r"(?i)d\s*[+-−]?\s*\d+", text.strip()) else
                    1 if parse_age(text) is not None else 0 if text.strip() else -1)
            grey = [f"{v['date']:%d/%m/%Y}" if v["date"] else "date",
                    f"{v['age']:.1f} wk" if v["age"] is not None else "age",
                    f"D{v['day']:+d}" if v["day"] is not None else "D-14"]
            for i, e in enumerate(eds):
                e.setText(text if i == mine else "")
                e.setPlaceholderText(grey[i])
        show()
        for e in eds:
            e.editingFinished.connect(self._commit(lambda e=e: e.text().strip() != get()
                                                   and (put(e.text()), show())))
        return w

    def _step(self, back):
        """Ctrl+Z here undoes the study's last edit, and the window follows."""
        self.main._step(back)
        QTimer.singleShot(0, lambda: self.refresh(force=True))

    def _add_event(self, kind):
        again = bool(_events_of(self.a, kind))  # a CT after a SPECT: the same anaesthesia
        self.a.events.append({"kind": kind})
        if kind in NEEDS_ANAESTHESIA and not again:
            self.a.events.append({"kind": "anaesthesia"})
            self.statusBar().showMessage(f"{kind} added, and its anaesthesia as a procedure of "
                                         "its own — × removes it if there was none", 8000)
        elif kind in NEEDS_ANAESTHESIA:
            self.statusBar().showMessage(f"{kind} added, under the anaesthesia already there — "
                                         "+ procedure ▸ anaesthesia if it had its own", 8000)
        self._redraw()

    def _split(self, a):
        """SPECT/CT typed as one modality: two imaging procedures."""
        new = split_modality(a.events)
        if len(new) != len(a.events):
            a.events[:] = new
            self.statusBar().showMessage("A dual-modality session is two imaging procedures, "
                                         "one per modality", 8000)
            QTimer.singleShot(0, lambda: self.refresh(force=True))

    def _redraw(self):
        self.main._later(self.main._sync)()
        QTimer.singleShot(0, lambda: self.refresh(force=True))

    # ------------------------------------------------------------ every animal at once
    def _rows(self):
        """The table view's rows: (label, key, part, colour); a syringe is two rows."""
        st = self.main.study
        out = [("ID", "ID", None, "#b0b0b0")]
        for name, color, keys in self._groups(st.animals[0]):
            for k in keys:
                if k in ("syringe full", "syringe empty", "tail"):
                    out += [(f"{k} (MBq)", k, 0, color), (f"{k} at", k, 1, color)]
                elif k in ("DOB", "arrival"):
                    out += [("date of birth" if k == "DOB" else k, k, None, color),
                            *[(x, x, None, color) for x in
                              (("age",) if k == "DOB" else ("age at arrival",))]]
                else:
                    out.append((self.LABEL.get(k, k), k, None, color))
            if name == self.GROUPS[0][0]:          # as many as the animal with the most
                for n in range(max(len(a.losses) for a in st.animals)):
                    out += [(f"other loss {n + 1} {lab}", ("loss", n, f), None, color)
                            for f, lab in (("mbq", "(MBq)"), ("time", "at"), ("what", "what"))]
                out += [(f"note {n + 1}", ("bnote", n), None, color)
                        for n in range(max(len(a.bio_notes) for a in st.animals))]
        kinds = list(dict.fromkeys(e.get("kind", "") for a in st.animals for e in a.events))
        for kind in kinds:                        # the procedures: imaging 2 · start …
            most = max(len(_events_of(a, kind)) for a in st.animals)
            for n in range(most):
                evs = [e for a in st.animals for e in _events_of(a, kind)[n:n + 1]]
                fields = list(dict.fromkeys(f["name"] for e in evs for f in ev_fields(
                    e, PREFS["procedures"])))
                out += [(f"{kind or 'other'}{f' {n + 1}' if most > 1 else ''} · {f}",
                         ("ev", kind, n, f), None, _ARRIVE) for f in fields]
        return out

    def _fill_sheet(self):
        st, sh = self.main.study, self.sheet
        rows = self._drawn = self._rows()   # an edit before the next redraw goes by these
        n = len(st.animals)
        cp, oc = self.SC + n, self.SC + n + 1   # copy ▾, on card: after the animals, as the
        sh.clear()                              # one-animal view has them
        sh.setColumnCount(oc + 1)
        sh.setHorizontalHeaderLabels(["field"] + [a.label or "?" for a in st.animals]
                                     + ["", "on card"])
        sh.horizontalHeaderItem(oc).setToolTip("Whether the cards show the field (the data are "
                                               "kept either way): ticked on every card, half "
                                               "on some")
        sh.setRowCount(len(rows))
        fields = {k for _, _, keys in self._groups(st.animals[0]) for k in keys}
        for r, (lab, key, part, color) in enumerate(rows):
            sh.put(r, 0, lab, editable=False, color=color)
            sh.put(r, cp, "", editable=False)
            sh.put(r, oc, "", editable=False)
            ev = isinstance(key, tuple) and key[0] == "ev"     # a procedure's field
            if ev or isinstance(key, str) and key in fields and part in (None, 0):
                shown = _ev_key(*key[1:]) if ev else key
                on = [_shows(a, shown) for a in st.animals]
                c = QCheckBox()
                c.setTristate(False)
                c.setCheckState(Qt.Checked if all(on) else Qt.PartiallyChecked if any(on)
                                else Qt.Unchecked)
                c.clicked.connect(lambda v, shown=shown: self.main._show_field(
                    self.main.study.animals[0], shown, v, every=True))
                sh.setCellWidget(r, cp, self._copy_button(key, lambda: self._sheet_animal(),
                                                          label=lab))
                sh.setCellWidget(r, oc, _centred(c))
            for c, a in enumerate(st.animals, self.SC):
                text = _cell_text(a, key, part, st.day)
                life = life_dates(a.extra, st.day) if key in ("DOB", "age", "age at arrival") \
                    and not text else {}
                if v := life.get(key):                   # worked out from the others: grey
                    sh.put(r, c, f"{v:%d/%m/%Y}" if key == "DOB" else f"{v:.1f} wk",
                           tip="worked out from the other dates — type to set it", color="#777")
                    continue
                sh.put(r, c, text, tip=text if len(text) > 20 else "")   # 150 px: cut short
        sh.resizeColumnToContents(0)
        for c in range(self.SC, cp):
            sh.setColumnWidth(c, self.COL_W)
        sh.setColumnWidth(cp, 62)
        sh.setColumnWidth(oc, 56)
        self.statusBar().showMessage("Select several cells and type to fill them all (a comma "
                                     "list is dealt out); Ctrl+V pastes a row or a block "
                                     "copied from Excel from the current cell on")

    def _table_width(self) -> int:
        """The window as wide as the table view whole, its vertical bar in."""
        sh = self.sheet
        return (sum(sh.columnWidth(c) for c in range(sh.columnCount())) + 2 * sh.frameWidth()
                + sh.verticalScrollBar().sizeHint().width()
                + (sh.verticalHeader().width() if sh.verticalHeader().isVisible() else 0)
                + self.width() - self.stack.width())

    def _sheet_animal(self) -> Animal:
        """The table view's animal to copy from: the current cell's, else the first."""
        c = self.sheet.currentColumn() - self.SC
        st = self.main.study
        return st.animals[c] if 0 <= c < len(st.animals) else st.animals[0]

    def _sheet_edited(self, out):
        st, rows = self.main.study, self._drawn
        for r, c, text in out:
            if self.SC <= c < self.SC + len(st.animals):
                a = st.animals[c - self.SC]
                _cell_put(a, rows[r][1], rows[r][2], text, st.day)
                if rows[r][1] == "alias" and text.strip() and a.show.get("alias") is False:
                    del a.show["alias"]          # an alias typed here shows on its card
        for r, c, _ in out:                      # tidied as the model reads it
            if self.SC <= c < self.SC + len(st.animals):
                self.sheet.put(r, c, _cell_text(st.animals[c - self.SC], rows[r][1],
                                                rows[r][2], st.day))
        self.main._later(self.main._sync)()

    def _commit(self, fn):
        """An edit applied to the model; the board follows if it changed anything."""
        def go(*_):
            before = repr(self.a)
            fn()
            if repr(self.a) != before:
                for i, x in enumerate(self.main.study.animals[:self.c_animal.count()]):
                    self.c_animal.setItemText(i, x.label or "?")   # an ID, an alias typed here
                self.main._later(self.main._sync)()
        return go

    def _editors(self, a: Animal, key) -> list[QWidget]:
        day = self.main.study.day
        if key in ("syringe full", "syringe empty", "tail"):
            n, t = _ATTRS[key]
            e1 = _edit(_num(getattr(a, n), a.typed.get(n)), "MBq", 110)
            e2 = _edit(_shown(getattr(a, t), day), "HH:MM", 130)
            e1.editingFinished.connect(self._commit(
                lambda: e1.setText(_num(_put_num(a, n, e1.text()), a.typed.get(n)))))
            e2.editingFinished.connect(self._commit(lambda: (
                setattr(a, t, _typed(getattr(a, t), e2.text(), day)),
                e2.setText(_shown(getattr(a, t), day)))))
            return [e1, e2, QWidget()]
        if key == "weight":
            e = _edit(_num(a.weight_g, a.typed.get("weight_g")), "g", 110)
            e.editingFinished.connect(self._commit(
                lambda: e.setText(_num(_put_num(a, "weight_g", e.text()), a.typed.get("weight_g")))))
            return [e, QWidget()]
        if key == "injection":
            e = _edit(_shown(a.inj_time, day), "HH:MM", 130)
            e.editingFinished.connect(self._commit(lambda: (
                setattr(a, "inj_time", _typed(a.inj_time, e.text(), day)),
                e.setText(_shown(a.inj_time, day)))))
            return [e, QWidget()]
        if key == "note":
            e = QPlainTextEdit(a.note)
            e.setFixedHeight(70)
            e.textChanged.connect(lambda: setattr(a, "note", e.toPlainText()))
            return [e]
        if key in ("isotope", "species", "strain", "sex"):
            items = {"isotope": [k for k, _ in PREFS["isotopes"]],
                     "species": _species(), "strain": _strains(_get(a, "species")),
                     "sex": ["F", "M"]}[key]
            now = a.isotope if key == "isotope" else _get(a, key)
            c = _combo(items, "", editable=True, width=220)
            c.setCurrentText(now)
            set_ = {"isotope": lambda v: setattr(a, "isotope", v.strip()),
                    "species": lambda v: _set_species(a, v),
                    "strain": lambda v: _set_strain(a, v),
                    "sex": lambda v: _put(a, "sex", v)}[key]

            def done(*_, c=c, set_=set_):
                before = repr(a)
                set_(c.currentText())
                if repr(a) != before:
                    self.main._later(self.main._sync)()
                    if key in ("species", "strain"):     # the strain list and genotype follow
                        QTimer.singleShot(0, lambda: self.refresh(force=True))
            c.activated.connect(done)
            c.lineEdit().editingFinished.connect(done)
            return [c, QWidget()]
        if key == "alias":
            e = _edit(", ".join(a.aliases), "ear tag, cage code… — commas between")
            e.editingFinished.connect(self._commit(
                lambda: setattr(a, "aliases", _csv_list(e.text()))))
            return [e]
        if key == "molecule":
            e = _edit(a.molecule, "e.g. R3B23")
            e.editingFinished.connect(self._commit(
                lambda: setattr(a, "molecule", e.text().strip())))
            return [e]
        v = _get(a, key)
        if key in ("DOB", "arrival"):            # with the age that goes with it
            other = "age" if key == "DOB" else "age at arrival"
            e = _edit(_date_shown(v, day), "" if key == "DOB" else "22/09/2026")
            e.setToolTip("A cage born over several days: a range or a list — the median date "
                         "gives the age. Any one of date of birth, age, or arrival with the "
                         "age at arrival gives the others (grey)" if key == "DOB" else
                         "The day the animals came in; with the age at arrival it gives the "
                         "date of birth")
            e2 = _edit(_get(a, other), "", 110)
            e2.setToolTip("On the study day" if other == "age" else "The supplier's age, "
                          "on the arrival day")

            def grey():                          # what the others give, in the empty one
                life = life_dates(a.extra, day)
                d, wk = life["DOB"], life[other]
                if key == "DOB":
                    e.setPlaceholderText(f"{d:%d/%m/%Y}" if d else
                                         "07/02/2026, a range 7-26/02/26, a list")
                e2.setPlaceholderText(f"{wk:.1f} wk" if wk is not None else "12 wk, 2.5 mo")
            grey()
            e.editingFinished.connect(self._commit(lambda: (
                _put(a, key, _typed(_get(a, key), e.text(), day, _date_shown)),
                e.setText(_date_shown(_get(a, key), day)), grey())))
            e2.editingFinished.connect(self._commit(lambda: (_put(a, other, e2.text()), grey())))
            return [e, e2]
        return self._field_widgets(a, _aspec(key), lambda: _get(a, key),
                                   lambda x: _put(a, key, x))

    def _copy_button(self, key, source=None, label=None) -> QToolButton:
        """copy ▾: this animal's `key` (a list: those fields) to every other, or to the
        ticked ones — every animal listed in the study's order, the one copied from greyed.
        `source()`: the animal to copy from when the menu opens (the table view: the current
        cell's), else this one. `label`: the field as said, if not its key."""
        label = label or key
        b = QToolButton()
        b.setText("copy ▾")
        b.setToolTip(f"Copy this animal's {label} to the other animals" if source is None else
                     f"Copy the {label} of the animal whose cell is selected (else the first) "
                     "to the others")
        b.setPopupMode(QToolButton.InstantPopup)
        b.setStyleSheet(f"QToolButton{{border:none;color:{_ACCENT};}} QToolButton::menu-indicator{{image:none;}}")
        m = _Checklist(b)

        def build():
            m.clear()
            src = source() if source else self.a
            others = [x for x in self.main.study.animals if x is not src]
            m.addAction(f"{src.label or '?'} to every other animal",
                        lambda: self._copy(key, others, src, label))
            m.addSection("or tick some")
            ticks = []
            for x in self.main.study.animals:
                act = m.addAction(x.label or "?")
                act.setCheckable(True)
                if x is src:
                    act.setText(f"{x.label or '?'}  (copied from)")
                    act.setEnabled(False)
                else:
                    ticks.append((x, act))
            m.addAction("copy to the ticked ones",
                        lambda: self._copy(key, [x for x, act in ticks if act.isChecked()], src,
                                           label))
        m.aboutToShow.connect(build)
        b.setMenu(m)
        b.setEnabled(len(self.main.study.animals) > 1)
        return b

    def _copy(self, key, targets, src=None, label=None):
        src = src or self.a
        for b in targets:
            for k in key if isinstance(key, list) else [key]:
                _copy_field(src, b, k)
        self.main._later(self.main._sync)()
        self.statusBar().showMessage(f"{label or key} copied to {len(targets)} animal(s) — "
                                     "Ctrl+Z in the main window undoes it", 6000)
        if isinstance(key, (list, tuple)):       # a procedure added to some: shown here too
            QTimer.singleShot(0, lambda: self.refresh(force=True))


# ------------------------------------------------------------------- options window
class OptionsWindow(QMainWindow):
    """The settings, by topic on the left. Saved as they change; one JSON file, which can be
    exported to another computer and imported there."""

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle(f"{APP_NAME} — options")
        self.setMinimumSize(820, 520)
        scr = QApplication.primaryScreen().availableGeometry()   # the Results page whole
        self.resize(min(1150, scr.width() - 40), min(900, scr.height() - 60))   # Procedures'
        #                                          field table whole
        self.topics = QListWidget()
        self.topics.setFixedWidth(190)
        self.pages = QStackedWidget()
        self.topics.currentRowChanged.connect(self.pages.setCurrentIndex)
        foot = QHBoxLayout()
        for text, tip, fn in (
                ("Export…", "Write every option to a JSON file", self._export),
                ("Import…", "Read the options from a JSON file", self._import),
                ("Reset to defaults", "Every option back to how BioDist ships", self._reset)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            foot.addWidget(b)
        foot.addStretch(1)
        self.where = QLabel(f"saved as they change, in {OPTIONS_FILE}")
        self.where.setStyleSheet("color:#8d8d8d;")
        foot.addWidget(self.where)
        root = QWidget()
        v = QVBoxLayout(root)
        h = QHBoxLayout()
        h.addWidget(self.topics)
        h.addWidget(self.pages, 1)
        v.addLayout(h, 1)
        v.addLayout(foot)
        self.setCentralWidget(root)
        _undo_keys(self, lambda: self._undo(True), lambda: self._undo(False))
        self._build()

    def _undo(self, back):
        """Ctrl+Z / Ctrl+Y: on the Results page the study's last change, else the options'."""
        if self.topics.currentItem() and self.topics.currentItem().text() == "Rules":
            self.main._step(back)
        else:
            self.main._prefs_undo(back)

    def _set(self, key, value):
        if PREFS[key] != value:
            PREFS[key] = value
            if key == "isotopes":
                set_half_lives((k, h) for k, h in value if h)
            _save_prefs()
            self.main._later(self.main._sync)()

    def _build(self):
        at = max(0, self.topics.currentRow())
        self.topics.clear()
        while self.pages.count():
            w = self.pages.widget(0)
            self.pages.removeWidget(w)
            w.deleteLater()
        for name, page in (("Animal cards", self._cards()), ("Formats", self._formats()),
                           ("Isotopes", self._isotopes()),
                           ("Species and strains", self._strains()),
                           ("Procedures", self._proc_fields()),
                           ("Tissue table", self._tissue_page()),
                           ("Data sources", self._sources()),
                           ("Rules", self._data()), ("Results window", self._results_page()),
                           ("Report", self._report_page()),
                           ("Study file", self._study_page()),
                           ("Log", self._log_page())):
            self.topics.addItem(name)
            sc = QScrollArea()                   # a page taller than the window scrolls —
            sc.setWidgetResizable(True)          # squeezed, its rows overlapped (Results)
            sc.setFrameShape(QFrame.NoFrame)
            sc.setWidget(page)
            self.pages.addWidget(sc)
        self.topics.setCurrentRow(at)
        for sb in self.pages.findChildren(QAbstractSpinBox):
            sb.setKeyboardTracking(False)        # applied on Enter or leaving, not per key

    @staticmethod
    def _page(title, text):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 4, 8, 4)
        t = QLabel(f"<b>{title}</b>")
        t.setStyleSheet("font-size:14px;")
        v.addWidget(t)
        g = QLabel(text)
        g.setWordWrap(True)
        g.setStyleSheet("color:#8d8d8d;")
        v.addWidget(g)
        return w, v

    def _check(self, v, key, text, tip=""):
        c = QCheckBox(text)
        c.setChecked(PREFS[key])
        c.setToolTip(tip)
        c.toggled.connect(lambda on: self._set(key, on))
        v.addWidget(c)
        return c

    def _choice(self, key, items: dict, tip=""):
        c = _combo(list(items.values()), items.get(PREFS[key], ""))
        c.setToolTip(tip)
        c.activated.connect(lambda i: self._set(key, list(items)[i]))
        return c

    def _cards(self):
        w, v = self._page("Animal cards", "The fields a card shows until its × hides one or "
                          "the animal window's “on card” tick shows one. A field holding "
                          "something shows anyway, until hidden; hiding never deletes what it "
                          "holds.")
        grid = QGridLayout()
        for i, k in enumerate(CARD_KEYS):
            c = QCheckBox(k)
            c.setChecked(k in PREFS["card_fields"])
            c.toggled.connect(lambda on, k=k: self._set("card_fields", [
                x for x in CARD_KEYS if (x == k and on) or (x != k and x in PREFS["card_fields"])]))
            grid.addWidget(c, i % 7, i // 7)
        v.addLayout(grid)
        v.addSpacing(10)
        self._check(v, "field_all", "× and “on card” apply to every animal",
                    "Off: only to the card they were clicked on (a note is always one card's)")
        f = QFormLayout()
        n = QSpinBox()
        n.setRange(0, 60)
        n.setSpecialValueText("off — show it all")
        n.setSuffix(" lines")
        n.setValue(PREFS["card_rows"])
        n.valueChanged.connect(lambda x: self._set("card_rows", x))
        f.addRow("Scroll a card taller than", n)
        v.addLayout(f)
        v.addStretch(1)
        return w

    def _formats(self):
        w, v = self._page("Formats", "How typed values are shown. What was typed is what is "
                          "saved and computed with — tidying only changes the display.")
        f = QFormLayout()
        f.addRow(self._check(QVBoxLayout(), "tidy_times", "Tidy times",
                             "8:48:21 d1 · d+1 08:48 · 25/9 8:48 · 2026-09-25 08:48 are all "
                             "read; seconds are kept"),
                 self._choice("time_format", {k: f"{k}    {ex}" for k, ex in TIME_FORMATS.items()}))
        f.addRow(self._check(QVBoxLayout(), "tidy_dates", "Tidy dates",
                             "Dates of birth in any order; a range 7-26/02/26 shows as "
                             "07–26/02/2026"),
                 self._choice("date_format", {k: k for k in DATE_FORMATS}))
        f.addRow(self._check(QVBoxLayout(), "tidy_numbers", "Tidy numbers",
                             "Off: numbers show as read — 1.30 stays 1.30, the digits say what "
                             "the instrument gave; .577 always shows 0.577"), QLabel(""))
        v.addLayout(f)
        g = QLabel("Where: <b>times</b> — the animal cards and window (syringes, injection, "
                   "tail, losses, procedures), the every-animal table, the tissue table's "
                   "“read at”. <b>Dates</b> — date of birth and arrival (cards, animal window, "
                   "table). <b>Numbers</b> — MBq and body weight on the cards and in the animal "
                   "window, masses and activities typed in the tissue table.<br>Not: the "
                   "files' own times (Data sources, side panel: day month hh:mm), the Results "
                   "(decimals: Options › Results window) and the report (its own decimals).")
        g.setWordWrap(True)
        g.setStyleSheet("color:#8d8d8d;")
        v.addWidget(g)
        v.addStretch(1)
        return w

    def _table(self, v, key, heads, tip):
        """An editable list of rows: typing saves it; + adds a row, − removes the selected."""
        t = QTableWidget(0, len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setToolTip(tip)
        rows = PREFS[key]
        t.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, x in enumerate(row):
                it = QTableWidgetItem()
                if isinstance(x, bool):
                    it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setCheckState(Qt.Checked if x else Qt.Unchecked)
                else:
                    it.setText(f"{x:g}" if isinstance(x, float) else str(x))
                t.setItem(r, c, it)

        def read(*_):
            out = []
            for r in range(t.rowCount()):
                row = []
                for c, x0 in enumerate(rows[0] if rows else [""] * len(heads)):
                    it = t.item(r, c)
                    if isinstance(x0, bool):
                        row.append(bool(it) and it.checkState() == Qt.Checked)
                    elif isinstance(x0, (int, float)):
                        row.append(_f(it.text() if it else "") or 0.0)
                    else:
                        row.append(it.text().strip() if it else "")
                if row[0] if isinstance(row[0], str) else row[1]:
                    out.append(row)
            self._set(key, out)
        t.itemChanged.connect(read)
        v.addWidget(t, 1)
        h = QHBoxLayout()
        for text, fn in (("+", lambda: (t.insertRow(t.rowCount()),
                                        t.scrollToBottom())),
                         ("−", lambda: ([t.removeRow(r) for r in sorted(
                             {i.row() for i in t.selectedIndexes()}, reverse=True)], read()))):
            b = QPushButton(text)
            b.setFixedWidth(34)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        return t

    def _isotopes(self):
        w, v = self._page("Isotopes", "The isotopes the card's list offers and the half-lives "
                          "decay correction uses (another can be typed on the card, but has no "
                          "half-life until it is added here). Edit a cell, + adds a row.")
        self._table(v, "isotopes", ["isotope", "half-life (h)"], "Half-life in hours")
        return w

    def _strains(self):
        w, v = self._page("Species and strains", "The card offers a species' own strains; "
                          "picking one fills in its genotype. Edit a cell, + adds a row.")
        self._table(v, "strains", ["species", "strain", "genotype"],
                    "Genotype left empty: nothing is filled in")
        return w

    def _field_table(self, v, cols, save):
        """A table of fields: name, type, list, example (and for a procedure: the line it
        shares, when it shows). + adds a row, − removes the selected, ↑ ↓ move one. Saved
        as edited. Returns (table, fill)."""
        heads = ["field", "type", "list (commas)", "example (grey while empty)", "line",
                 "shown when"][:cols]
        t = QTableWidget(0, len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        t.horizontalHeader().setStretchLastSection(True)
        for c, wd in enumerate((130, 115, 170, 125, 90)[:cols - 1]):
            t.setColumnWidth(c, wd)
        tips = ["The name the animal window shows", "text; list — the list below, anything "
                "can still be typed; time · p.i. — HH:MM or after the injection (2 h p.i.), the "
                "other worked out; date · age · D-n — a day as a date, the animal's age (8 wk) "
                "or days from the study day (D-14), the others worked out",
                "For a list: its items, commas between (one in brackets stays in its item: "
                "APT62 (mouse, HS))", "Shown in grey while the field is "
                "empty", "Fields with the same line name sit side by side on one line, under "
                "that name (hardware: system, collimator)",
                "Shown only when another field holds a value: modality = SPECT (or SPECT, PET)"]
        for c in range(len(heads)):
            t.horizontalHeaderItem(c).setToolTip(tips[c])
        keys = list(FIELD_TYPES)

        def fill(fields):
            t.blockSignals(True)
            t.setRowCount(len(fields))
            for r, f in enumerate(fields):
                for c, x in enumerate([f["name"], "", ", ".join(f["items"]), f["example"],
                                       f["line"], f["when"]][:cols]):
                    t.setItem(r, c, QTableWidgetItem(x))
                cb = _combo(list(FIELD_TYPES.values()), FIELD_TYPES[f["type"]])
                cb.activated.connect(lambda *_: read())
                t.setCellWidget(r, 1, cb)
            t.blockSignals(False)

        def rows():
            def cell(r, c):
                return (t.item(r, c).text().strip() if t.item(r, c) else "") if c < cols else ""
            return [fdef(cell(r, 0), keys[t.cellWidget(r, 1).currentIndex()],
                         [x.strip() for x in re.split(r",(?![^()]*\))", cell(r, 2))   # not
                          if x.strip()], cell(r, 3),               # in brackets: (mouse, HS)
                         cell(r, 4), cell(r, 5))
                    for r in range(t.rowCount()) if cell(r, 0)]

        def read(*_):
            save(rows())
        t.itemChanged.connect(read)
        v.addWidget(t, 1)
        h = QHBoxLayout()

        def add():
            t.blockSignals(True)
            r = t.rowCount()
            t.insertRow(r)
            for c in range(cols):
                t.setItem(r, c, QTableWidgetItem(""))
            cb = _combo(list(FIELD_TYPES.values()), FIELD_TYPES["text"])
            cb.activated.connect(lambda *_: read())
            t.setCellWidget(r, 1, cb)
            t.blockSignals(False)
            t.setCurrentCell(r, 0)
            t.editItem(t.item(r, 0))

        def move(d):
            r = t.currentRow()
            fs = rows()
            if 0 <= r < len(fs) and 0 <= r + d < len(fs):
                fs[r], fs[r + d] = fs[r + d], fs[r]
                save(fs)
                fill(fs)
                t.setCurrentCell(r + d, 0)
        for text, tip, fn in (("+", "A field", add),
                              ("−", "Remove the selected fields", lambda: (
                                  [t.removeRow(r) for r in sorted(
                                      {i.row() for i in t.selectedIndexes()}, reverse=True)],
                                  read())),
                              ("↑", "Move it up", lambda: move(-1)),
                              ("↓", "Move it down", lambda: move(1))):
            b = QPushButton(text)
            b.setFixedWidth(34)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        return t, fill

    def _tissue_page(self):
        w, v = self._page("Tissue table", "The tissue table on the board: what each tissue × "
                          "animal cell shows, the units of the rows typed by hand, and the "
                          "line over the table.")
        f = QFormLayout()
        f.addRow("Cells show", self._choice("cell_mass", CELL_MASS))
        f.addRow("and", self._choice("cell_value", CELL_VALUE,
                                     "The reference time: each animal's injection time, or "
                                     "one instant for all (the Results' side panel)"))
        f.addRow("A mass typed in", self._choice("typed_mass", {"mg": "mg", "g": "g"}))
        f.addRow("An activity typed in", self._choice("typed_activity",
                                                      {"MBq": "MBq", "kBq": "kBq"}))
        v.addLayout(f)
        v.addSpacing(8)
        v.addWidget(QLabel("The line over the table says"))
        for k, text in TISSUE_NOTE.items():
            c = QCheckBox(text)
            c.setChecked(k in PREFS["tissue_note"])
            c.toggled.connect(lambda on, k=k: self._set("tissue_note", [
                x for x in TISSUE_NOTE if (x == k and on) or (x != k and x in PREFS["tissue_note"])]))
            v.addWidget(c)
        v.addSpacing(8)
        g = QLabel("<b>Recorded tissue lists</b> — the Tissues' + opens one into a study. A "
                   "name, then the tissues in vial order, commas between; “(empty)” for a bare "
                   "vial, “ctrl” a control tube.")
        g.setWordWrap(True)
        v.addWidget(g)
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["name", "tissues"])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        t.setMinimumHeight(120)

        def fill():
            t.blockSignals(True)
            t.setRowCount(len(PREFS["tissue_lists"]))
            for r, (name, tissues) in enumerate(PREFS["tissue_lists"].items()):
                t.setItem(r, 0, QTableWidgetItem(name))
                t.setItem(r, 1, QTableWidgetItem(", ".join(tissues)))
            t.blockSignals(False)

        def read(*_):
            rows = [((t.item(r, 0).text() if t.item(r, 0) else "").strip(),
                     _csv_list(t.item(r, 1).text() if t.item(r, 1) else ""))
                    for r in range(t.rowCount())]
            self._set("tissue_lists", {n: x for n, x in rows if n})
        t.itemChanged.connect(read)
        fill()
        v.addWidget(t, 1)

        def add(name="", tissues=()):
            t.blockSignals(True)
            t.insertRow(t.rowCount())
            t.setItem(t.rowCount() - 1, 0, QTableWidgetItem(name))
            t.setItem(t.rowCount() - 1, 1, QTableWidgetItem(", ".join(tissues)))
            t.blockSignals(False)
            if name:
                read()
            else:
                t.editItem(t.item(t.rowCount() - 1, 0))
        self._plus_minus(v, lambda: add(), lambda: (
            [t.removeRow(r) for r in sorted({i.row() for i in t.selectedIndexes()},
                                            reverse=True)], read()))
        st = self.main.study
        b = QPushButton("+ this study's list")
        b.setToolTip("Record the tissues of the study open, in their order")
        b.setEnabled(bool(st.tissues))
        b.clicked.connect(lambda: add(st.name or "this study", [x.name for x in st.tissues]))
        v.itemAt(v.count() - 1).layout().insertWidget(2, b)     # by the + and −
        v.addStretch(1)
        return w

    def _proc_fields(self):
        w, v = self._page("Procedures", "The kinds “+ procedure” offers (left: double-click to "
                          "rename, drag to reorder) and the fields each opens with (right) — "
                          "how each is typed: text, a list (anything can still be typed), a "
                          "time (HH:MM or after the injection, 2 h p.i.), a day (a date, the "
                          "animal's age then, or D-14) — the other ways are worked out, in "
                          "grey. Fields with the same “line” sit side by side; “shown when” "
                          "keeps a field for one case (modality = SPECT). A note always "
                          "follows; “+ field” in the animal window adds one to one procedure. "
                          "Procedures already entered keep what they hold. Hover the headers.")
        h = QHBoxLayout()
        v.addLayout(h, 1)
        left = QVBoxLayout()
        kinds = QListWidget()
        kinds.setFixedWidth(170)
        kinds.setDragDropMode(QAbstractItemView.InternalMove)
        kinds.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        left.addWidget(kinds, 1)
        right = QVBoxLayout()
        h.addLayout(left)
        h.addLayout(right, 1)
        names: list[str] = []                    # the kinds as listed, to tell a rename

        def listed():
            return [kinds.item(i).text().strip() for i in range(kinds.count())]

        def save_kinds(*_):
            """A kind renamed or moved: its fields go with it."""
            now, procs = listed(), PREFS["procedures"]
            same = len(now) == len(names)
            new = {}
            for i, n in enumerate(now):
                if n and n not in new:
                    new[n] = procs.get(names[i] if same and names[i] not in now else n, [])
            names[:] = now
            self._set("procedures", new)

        def save_fields(fs):
            i = kinds.currentRow()
            if 0 <= i < len(names):
                self._set("procedures", {**PREFS["procedures"], names[i]: fs})

        table, fill = self._field_table(right, 6, save_fields)

        def show(i):
            fill(PREFS["procedures"].get(names[i], []) if 0 <= i < len(names) else [])
            table.setEnabled(0 <= i < len(names))

        def load():
            kinds.blockSignals(True)
            kinds.clear()
            for k in PREFS["procedures"]:
                it = QListWidgetItem(k)
                it.setFlags(it.flags() | Qt.ItemIsEditable)
                kinds.addItem(it)
            names[:] = list(PREFS["procedures"])
            kinds.blockSignals(False)
        load()
        kinds.currentRowChanged.connect(show)
        kinds.itemChanged.connect(save_kinds)
        kinds.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, save_kinds))
        kinds.setCurrentRow(0)
        hb = QHBoxLayout()

        def add_kind():
            n, k = 1, "new kind"
            while k in names:
                n += 1
                k = f"new kind {n}"
            self._set("procedures", {**PREFS["procedures"], k: []})
            load()
            kinds.setCurrentRow(kinds.count() - 1)
            kinds.editItem(kinds.item(kinds.count() - 1))

        def drop_kind():
            i = kinds.currentRow()
            if 0 <= i < len(names):
                self._set("procedures", {k: f for k, f in PREFS["procedures"].items()
                                         if k != names[i]})
                load()
                kinds.setCurrentRow(min(i, kinds.count() - 1))
        for text, tip, fn in (("+", "A kind of procedure", add_kind),
                              ("−", "Remove the kind selected (procedures entered keep it)",
                               drop_kind)):
            b = QPushButton(text)
            b.setFixedWidth(34)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            hb.addWidget(b)
        hb.addStretch(1)
        left.addLayout(hb)
        return w

    @staticmethod
    def _plus_minus(v, add, remove):
        h = QHBoxLayout()
        for text, fn in (("+", add), ("−", remove)):
            b = QPushButton(text)
            b.setFixedWidth(34)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        return h.itemAt(0).widget()

    def _sources(self):
        w, v = self._page("Data sources", "What a file's vials show when it is unfolded "
                          "(▸) in the data-source table, under the animal and the tissue.")
        f = QFormLayout()
        for k, label, menu in (
                ("weight", "weight", self._choice("strip_weight", {
                    "g": "g — the vial and its tube, as weighed"})),
                ("activity", "activity", self._choice("strip_activity", {
                    "counts": "counts, as counted", "cpm": "CPM, as counted",
                    "bq": "Bq, as the counter normalized it"}))):
            c = QCheckBox(label)                 # a row under the vials, and in what
            c.setChecked(k in PREFS["strip_rows"])
            c.toggled.connect(lambda on, k=k: self._set("strip_rows", [
                x for x in STRIP_ROWS if (x == k and on) or (x != k and x in PREFS["strip_rows"])]))
            f.addRow(c, menu)
        f.addRow("Vials laid out", self._choice("strip_layout", STRIP_LAYOUTS))
        n = QSpinBox()
        n.setRange(1, 50)
        n.setValue(PREFS["strip_racks"])
        n.setSuffix(" racks")
        n.valueChanged.connect(lambda x: self._set("strip_racks", x))
        f.addRow("Across: a new line every", n)
        f.addRow(self._check(QVBoxLayout(), "source_rounds", "The counting round of each "
                             "count file, before its times", "round 1, round 2…: one pass of "
                             "the counter over the vials, as the Results' side panel names "
                             "them; each round tinted"))
        f.addRow(self._check(QVBoxLayout(), "details_all", "A file's details (⤢) show every "
                             "column, the empty ones too", "Off: only what the file holds — a "
                             "tare run is vials and weights, a count run has no masses"))
        g = QLabel(
            "<b>The guess</b>, for every file not placed by hand (the log says why, file by "
            "file): a weighing whose tubes match an earlier one (each tube within 5 mg, "
            "heavier) is that rack filled — the racks are matched one by one, so a rack weighed "
            "in the wrong run still lands on its animal; a counting that matches an earlier one "
            "vial by vial is a recount; the rest are dealt to the animals in card order, the "
            "tissues in the batch's vial order. A file of masses typed by hand (tissues down, "
            "animals across) is read as such — see the README.")
        g.setWordWrap(True)
        g.setStyleSheet("color:#8d8d8d;")
        f.addRow(g)
        v.addLayout(f)
        v.addStretch(1)
        return w

    def _report_page(self):
        w, v = self._page("Report", "What a new report holds and is saved as — the report "
                          "window shows and edits the same: tick the sections, drag them, "
                          "unfold one (▸) for what it shows. Its value tables take the Results' "
                          "decimals unless set on the table.")
        f = QFormLayout()
        self._fmt = self._choice("report_format", dict(ReportWindow.FORMATS))
        self._fmt.activated.connect(lambda i: (
            self.main.report.c_format.setCurrentIndex(i), self.main.report._head()))
        f.addRow("Saved as", self._fmt)
        v.addLayout(f)
        tree = ReportTree()
        tree.changed.connect(lambda: self.main.report.isVisible() and self.main.report.refresh())
        v.addWidget(tree, 1)
        return w
    def _study_page(self):
        w, v = self._page("Study file", "What a saved study (.json) holds besides the animals, "
                          "the tissues and how the files were placed.")
        self._check(v, "embed", "Keep the files' data in the study",
                    "Every Hidex file's values, compact, a line per file at the end of the "
                    ".json: the study opens and computes the same if the files are moved or "
                    "gone. Off: only their paths")
        g = QLabel("Always kept: each file's path, size, dates and SHA-256 fingerprint — a file "
                   "changed since is said when the study opens — and the study's own "
                   "fingerprint, to tell an edit made outside BioDist.")
        g.setWordWrap(True)
        g.setStyleSheet("color:#8d8d8d;")
        v.addWidget(g)
        v.addStretch(1)
        return w

    RULES = ("window", "window_rule", "pick_count", "combine", "min_counts", "min_basis",
             "max_basis", "dt_max", "cpm_max", "valid_counts", "valid_max", "valid_dt",
             "count_agree", "count_tol_pct",
             "count_tol_sigma", "ref_rule", "ref_time", "mass_rule", "mass_agree", "mass_tol_mg", "mass_tol_pct",
             "pick_mass", "pick_bq", "drift_fix", "subtract_tail", "half_lives")
    DEFAULTED = [k for k in RULES if k not in ("window", "ref_time", "half_lives")]   # PREFS
    #                                              keeps these (half-lives: Options › Isotopes)

    def _data(self):
        w, v = self._page("Rules", "How the values of the study open are made, and what each "
                          "tissue is expected to be — saved with the study, so it reproduces. "
                          "A new study starts with the defaults. Ctrl+Z on this page undoes "
                          "the study's last change.")
        self._rules_box = QVBoxLayout()
        v.addLayout(self._rules_box)
        self._rules_sig = None
        self.refresh_rules()
        v.addSpacing(8)
        g = QLabel("<b>Expected per tissue</b> (this study) — the mass (mg) and uptake (%IA/g) "
                   "a tissue should have; 0 = no bound. Outside: flagged “out of the "
                   "expected range”. "
                   "+ offers the study's tissues.")
        g.setWordWrap(True)
        v.addWidget(g)
        self._ranges(v)
        return w

    def _results_page(self):
        w, v = self._page("Results window", "How the Results window shows the values — every "
                          "study. How the values are made: Options › Rules.")
        v.addWidget(QLabel("<b>data</b> — the units its list offers"))
        g = QGridLayout()
        for i, (k, lab) in enumerate(RESULT_UNITS):
            c = QCheckBox(lab)
            c.setChecked(k in PREFS["result_units"])
            c.toggled.connect(lambda on, k=k: self._set("result_units", [
                x for x, _ in RESULT_UNITS if (x == k and on) or (x != k and
                                                               x in PREFS["result_units"])]))
            g.addWidget(c, i // 4, i % 4)
        v.addLayout(g)
        self._check(v, "result_digits_box", "the decimals box beside it",
                    "Off: the decimals set below only")
        v.addSpacing(8)
        v.addWidget(QLabel("<b>show</b> and <b>highlight</b> — in the menu, and ticked when "
                           "the window opens"))
        g = QGridLayout()
        g.addWidget(QLabel("in the menu"), 0, 1)
        g.addWidget(QLabel("ticked"), 0, 2)
        r = 1
        for title, items, menu, on in (
                ("show — rows under the tissues", RESULT_ROWS, "result_show_menu",
                 "result_show"),
                ("highlight — what tints a cell", [(f, f) for f, _ in RESULT_FLAGS],
                 "result_flags_menu", "result_flags")):
            lab = QLabel(title)
            lab.setStyleSheet("color:#8d8d8d;")
            g.addWidget(lab, r, 0)
            r += 1
            for k, text in items:
                g.addWidget(QLabel("    " + text), r, 0)
                for col, key in ((1, menu), (2, on)):
                    c = QCheckBox()
                    c.setChecked(k in PREFS[key])
                    c.toggled.connect(lambda x, k=k, key=key, items=items: self._set(key, [
                        y for y, _ in items if (y == k and x) or (y != k and y in PREFS[key])]))
                    g.addWidget(c, r, col, Qt.AlignHCenter)
                r += 1
        g.setColumnStretch(3, 1)
        v.addLayout(g)
        note = QLabel("“ticked” takes effect when BioDist starts; an item out of its menu keeps "
                      "its tick. activity in the animal at SPECT / PET start ticks itself once a "
                      "study has such a session.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8d8d8d;")
        v.addWidget(note)
        v.addSpacing(8)
        v.addWidget(QLabel("<b>Side panel</b> (sources)"))
        f = QFormLayout()
        f.addRow("Countings", self._choice("panel_windows", PANEL_WINDOWS,
                                           "One row per counting, its energy window picked in "
                                           "the row (the one in use shown) — or a row for each "
                                           "counting in each window"))
        f.addRow("A click on a row", self._choice("panel_click", PANEL_CLICK,
                                                  "Which of a cell's countings / weighings make "
                                                  "its value: the row clicked alone (Ctrl+click "
                                                  "adds or removes one), or each click adds or "
                                                  "removes"))
        v.addLayout(f)
        v.addSpacing(8)
        v.addWidget(QLabel("<b>Decimals</b> shown, per unit (the decimals box sets them "
                           "too; Bq and counts are whole)"))
        g = QGridLayout()
        for i, (k, lab) in enumerate(UNITS):
            n = QSpinBox()
            n.setRange(0, 0 if k in WHOLE else 8)
            n.setFixedWidth(52)
            n.setEnabled(k not in WHOLE)
            n.setValue(PREFS["digits"].get(k, 2))
            n.valueChanged.connect(lambda x, k=k: self._set("digits", {**PREFS["digits"], k: x}))
            unit = QLabel(lab)
            unit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)   # the unit right by its box
            g.addWidget(unit, i // 3, 3 * (i % 3))
            g.addWidget(n, i // 3, 3 * (i % 3) + 1)
        for c in range(3):
            g.setColumnMinimumWidth(3 * c + 2, 24)            # a gap between the pairs
        g.setColumnStretch(9, 1)
        v.addLayout(g)
        v.addStretch(1)
        return w

    def _tick(self, s, field, text) -> QCheckBox:
        c = QCheckBox(text)
        c.setChecked(bool(getattr(s, field)))
        c.setToolTip(RULES_SAID)
        c.toggled.connect(lambda on: self._rule(**{field: on}))
        return c

    def _rule(self, **fields):
        """A rule of the study changed, applied once the click that changed it is over."""
        QTimer.singleShot(0, lambda: self.main._data_changed(fields))

    def refresh_rules(self):
        """The rules as the study open has them — rebuilt when the study changed them."""
        main = self.main
        s, res = main.study, main.res
        rounds = [res.round_label(i) for i in range(len(res.rounds))] if res else []
        windows = s.windows_available(main.runs)
        sig = (repr([getattr(s, k) for k in self.RULES]), len(s.chosen), tuple(rounds),
               tuple(a.isotope for a in s.animals),
               tuple(windows), s.name, tuple(PREFS[k] for k in self.DEFAULTED))
        if hasattr(self, "_fill_ranges"):
            self._fill_ranges()
        if sig == self._rules_sig or not hasattr(self, "_rules_box"):
            return
        self._rules_sig = sig
        box = self._rules_box
        while box.count():
            it = box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        host = QWidget()
        box.addWidget(host)
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        differ = [k for k in self.DEFAULTED if getattr(s, k) != PREFS[k]]
        head = QLabel(f"<b>How the values are made</b> — this study: "
                      f"{html.escape(s.name or '(not named yet)')}. A change applies at once"
                      + (f"; <span style='color:{_ARRIVE}'>●</span> not the defaults" if differ
                         else ""))
        head.setToolTip("Every value follows the rules as soon as one changes — nothing to "
                        "apply. Ctrl+Z on this page undoes the last change")
        head.setWordWrap(True)                   # not in a form row: it may wrap
        v.addWidget(head)
        f = QFormLayout()

        def row(label, fields, w):
            """A rule's row: ● before its name when the study's differs from the defaults."""
            off = [k for k in fields if k in differ]
            lab = QLabel(label + (f" <span style='color:{_ARRIVE}'>●</span>" if off else ""))
            if off:
                lab.setToolTip("Not the defaults — they are " + ", ".join(
                    f"{k} {PREFS[k]!r}" for k in off) + ". Back to the defaults (below) takes "
                    "them all")
            f.addRow(lab, w)

        def combo(items, now, tip, fn):
            c = _combo([lab for _, lab in items], dict(items).get(now, now))
            c.setToolTip(tip)
            c.activated.connect(lambda i: fn(items[i][0]))
            return c
        used = main._windows_used(main._eff) if hasattr(main, "_eff") else {}
        kev = {k: ", ".join(x) + " keV" for k, x in used.items() if x}
        cw = combo([("wide", "auto — widest" + (f" · {kev['wide']}" if kev.get("wide") else "")),
                    ("peak", "auto — photopeak" + (f" · {kev['peak']}" if kev.get("peak")
                                                   else ""))]
                   + [(x, x + " keV") for x in windows], s.window or s.window_rule,
                   "auto — widest: one isotope takes its widest window (all the counts), several "
                   "each take their photopeak; or one window by name, in every file. A cell can "
                   "take another window: Results ▸ side panel",
                   lambda x: self._rule(window="", window_rule=x) if x in ("wide", "peak")
                   else self._rule(window=x))
        now = s.pick_count
        if now.startswith("round:") and res and (i := res.round_of(now[6:])) is not None:
            now = f"round:{res.rounds[i][0]}"

        def num(field, lo, hi, step, decimals, tip, width=80):
            """A number of the study, applied when left (Enter, Tab)."""
            n = QDoubleSpinBox()
            n.setKeyboardTracking(False)
            n.setRange(lo, hi)
            n.setDecimals(decimals)
            n.setSingleStep(step)
            n.setValue(float(getattr(s, field)))
            n.setFixedWidth(width)
            n.setToolTip(tip)
            n.editingFinished.connect(lambda: abs(n.value() - getattr(s, field)) > 1e-9
                                      and self._rule(**{field: n.value()}))
            return n

        def line(*parts):
            w_ = QWidget()
            h_ = QHBoxLayout(w_)
            h_.setContentsMargins(0, 0, 0, 0)
            for p in parts:
                h_.addWidget(QLabel(p) if isinstance(p, str) else p)
            h_.addStretch(1)
            return w_

        def unit(k):                             # the same text on both rows: aligned
            return QLabel("" if k == "dt" else TOPS.get(k, k))

        def amount(field, k, step, tip):
            """A range bound in its unit: whole counts / CPM, Bq to 3 decimals, a dead time
            to 2 (1.00: none of the time lost)."""
            if k == "dt":
                return num(field, 0, 10.0, 0.05, 2, tip + " — a dead-time factor (0: none)", 100)
            whole = k.split("_")[0] in ("counts", "cpm")
            return num(field, 0, 1e9, step if whole else {"bq": 100, "kbq": 0.1, "mbq": 0.001}[k],
                       0 if whole or k == "bq" else 3, tip, 100)

        def top_in(k):
            """The tops' unit changed: the dead time (its defaults) or a CPM / Bq one (none
            until typed) — one top a range, never both."""
            dt = k == "dt"
            if k == s.max_basis:
                return
            self._rule(max_basis=k, valid_max=0, cpm_max=0,
                       valid_dt=(s.valid_dt or DT_VALID) if dt else 0,
                       dt_max=(s.dt_max or DT_WARN) if dt else 0)
        lo, hi = s.min_basis, s.max_basis
        vtop, ttop = ("valid_dt", "dt_max") if hi == "dt" else ("valid_max", "cpm_max")
        f.addRow(QLabel("<b>Countings</b>"))
        row("Counting window", ("window_rule",), cw)
        row("Typed by hand", ("pick_bq",), combo(
            [("auto", "wins over the counter"), ("files", "not used — the counter only")],
            s.pick_bq, "An activity typed in the tissue table (+ ▸ activity: read on the dose "
            "calibrator) replaces what the counter gives that vial — or not. Not used, it is "
            "still in the side panel, to pick for a cell", lambda x: self._rule(pick_bq=x)))
        row("Ranges in", ("min_basis", "max_basis"), line(
            "≥", combo(list(BASES.items()), lo, BOTTOM_TIP, lambda x: self._rule(min_basis=x)),
            "· ≤", combo(list(TOPS.items()), hi, TOP_TIP, top_in)))
        row("Valid", ("valid_counts", "valid_max", "valid_dt"), line(
            "≥", amount("valid_counts", lo, 100, VALID_TIP), unit(lo),
            "· ≤", amount(vtop, hi, 10000, VALID_TIP + " (0: no top)"), unit(hi)))
        row("Target range", ("min_counts", "cpm_max", "dt_max"), line(
            "≥", amount("min_counts", lo, 1000, MIN_TIP), unit(lo),
            "· ≤", amount(ttop, hi, 10000, DT_TIP if hi == "dt" else
                          "The rule prefers a counting under this too (0: none) — where this "
                          "counter stops being linear"), unit(hi)))
        g = QLabel("not valid: flagged, used only when nothing is · target: what the rule "
                   "prefers among the valid")       # one line: a wrapped label grows the row
        g.setToolTip(VALID_TIP + "\n\n" + MIN_TIP)
        g.setStyleSheet("color:#8d8d8d;")
        f.addRow("", g)
        row("Counted more than once", ("pick_count",), combo(
            list(COUNT_RULES.items()) + [(f"round:{r[0]}", res.round_label(i))
                                         for i, r in enumerate(res.rounds if res else [])],
            now, COUNT_TIP, lambda x: self._rule(pick_count=x)))
        row("Consensus", ("count_agree", "count_tol_pct", "count_tol_sigma"), line(
            self._tick(s, "count_agree", "leave out one out of it"), "· agree within",
            num("count_tol_pct", 0, 100, 0.5, 1, "Two countings of a vial (in one window, "
                "decay-corrected to one instant) agree when this close …", 64), "% or",
            num("count_tol_sigma", 0, 20, 0.5, 1, "… or within this many standard deviations "
                "of their counting statistics: what counting alone gives — √ of the counts as "
                "counted over the tissue's own (background and dead time off). 1,000 counts "
                "is ±3 %, 10,000 ±1 %; 219 counted over a background of 162, ±26 %", 64),
            "σ of their counts"))
        row("Several countings", ("combine",), combo(
            list(COMBINE.items()), s.combine, COMBINE_TIP, lambda x: self._rule(combine=x)))
        f.addRow(QLabel("<b>Weighings</b>"))
        row("Typed by hand", ("pick_mass",), combo(
            [("auto", "wins over the tubes"), ("files", "not used — the tubes only")],
            s.pick_mass, "A mass typed in the tissue table (+ ▸ mass: weighed on paraffin, "
            "parafilm…) replaces the tubes' — or not. Not used, it is still in the side panel, "
            "to pick for a cell", lambda x: self._rule(pick_mass=x)))
        row("Weighed more than once", ("mass_rule",), combo(
            list(MASS_RULES.items()), s.mass_rule, MASS_TIP, lambda x: self._rule(mass_rule=x)))
        row("Consensus", ("mass_agree", "mass_tol_mg", "mass_tol_pct"), line(
            self._tick(s, "mass_agree", "leave out one out of it"), "· agree within",
            num("mass_tol_mg", 0, 1000, 0.5, 1, "Two weighings of a tube agree when this close "
                "(the balance repeats within ±0.4 mg) …", 64), "mg or",
            num("mass_tol_pct", 0, 100, 1, 0, "… or within this % of the lighter one", 64),
            "% of the tissue"))
        f.addRow("Several weighings", QLabel("their mean (ticked in the side panel)"))
        row("Weighing correction", ("drift_fix",), combo(list(DRIFT_MODES.items()), {True: "scale", False: ""}
                                        .get(s.drift_fix, s.drift_fix), DRIFT_TIP,
                                        lambda x: self._rule(drift_fix=x)))
        f.addRow(QLabel("<b>Activities and dose</b>"))
        rt = QWidget()
        h = QHBoxLayout(rt)
        h.setContentsMargins(0, 0, 0, 0)
        rule = "injection" if s.ref_rule == "injection" else "time"
        h.addWidget(combo([("injection", "each animal's injection"), ("time", "a time:")], rule,
                          "The time the activities are decay-corrected to (tissue table, "
                          "Results, report): each animal's injection, or one time for all — "
                          "typed beside (18:00; another day: 1/10 9:00). %IA, %IA/g and SUV do "
                          "not depend on it", lambda x: self._rule(ref_rule=x)), 1)
        e = _edit(s.ref_time, "first counting's" if not s.ref_time else "18:00", 110)
        e.setToolTip("Empty: the first counting's reference time")
        e.setVisible(rule == "time")
        e.editingFinished.connect(lambda: e.text().strip() != s.ref_time and (
            self._rule(ref_time=e.text().strip()) if not e.text().strip()
            or parse_time(e.text(), s.day) else
            self.statusBar().showMessage(f"{e.text()!r}: not a time — 18:00, or 1/10 9:00", 6000)))
        h.addWidget(e)
        row("Activities (Bq) at", ("ref_rule",), rt)
        c = QCheckBox("taken off the injected activity")
        c.setChecked(s.subtract_tail)
        c.setToolTip("The tail vial, or the tail typed on an animal card (that wins)")
        c.toggled.connect(lambda on: self._rule(subtract_tail=on))
        row("Injection site (tail)", ("subtract_tail",), c)
        isos = list(dict.fromkeys([a.isotope for a in s.animals if a.isotope]
                                  + list(s.half_lives)))
        if isos:
            hb = QWidget()
            hh = QHBoxLayout(hb)
            hh.setContentsMargins(0, 0, 0, 0)
            for iso in isos:
                key = next((k for k in s.half_lives if _study._canon(k) == _study._canon(iso)),
                           iso)
                n = QDoubleSpinBox()
                n.setKeyboardTracking(False)
                n.setRange(0, 1e7)
                n.setDecimals(5)
                n.setFixedWidth(100)
                n.setValue((s.hl_of(iso) or 0) / 3600)
                n.setToolTip("The half-life this study decay-corrects with, saved with it. A new "
                             "study takes Options › Isotopes'; a counter file that says another "
                             "is offered when it is read")
                n.editingFinished.connect(lambda n=n, key=key: n.value() > 0 and abs(
                    n.value() * 3600 - (s.hl_of(key) or 0)) > 1e-3 and self._rule(
                    half_lives={**s.half_lives, key: n.value()}))
                hh.addWidget(QLabel(iso))
                hh.addWidget(n)
                hh.addWidget(QLabel("h"))
            hh.addStretch(1)
            row("Half-lives", (), hb)
        v.addLayout(f)
        say = QLabel(RULES_SAID)                 # here: a form row does not grow a wrapped label
        say.setWordWrap(True)
        say.setStyleSheet("color:#8d8d8d;")
        v.addWidget(say)
        own = sorted({tuple(x[:2]) for x in s.chosen})
        if own:                                  # a line of its own: the buttons fit below
            h = QHBoxLayout()
            lab = QLabel(f"{len(own)} cell(s) with their own pick (Results ▸ side panel) — "
                         "they keep it whatever the rules")
            lab.setStyleSheet("color:#8d8d8d;")
            h.addWidget(lab)
            h.addWidget(AnimalCard._link("drop them", "Every cell back to the rules (Ctrl+Z "
                                         "undoes)", lambda: self._rule(chosen=[])))
            h.addStretch(1)
            v.addLayout(h)
        h = QHBoxLayout()
        h.addStretch(1)
        b = QPushButton("Make these the defaults")
        b.setToolTip("New studies start with these rules")
        b.setEnabled(bool(differ))
        b.clicked.connect(self._make_defaults)
        b2 = QPushButton("Back to the defaults")
        b2.setToolTip("This study takes the defaults: " + ", ".join(
            f"{k} {PREFS[k]}" for k in differ) if differ else "This study has the defaults")
        b2.setEnabled(bool(differ))
        b2.clicked.connect(lambda: self._rule(**{k: copy.deepcopy(PREFS[k]) for k in differ}))
        h.addWidget(b)
        h.addWidget(b2)
        v.addLayout(h)

    def _make_defaults(self):
        for k in self.DEFAULTED:
            self._set(k, copy.deepcopy(getattr(self.main.study, k)))
        self.refresh_rules()

    def _ranges(self, v):
        """The study's expected ranges, a row per tissue (its name in the study)."""
        heads = ["tissue", "mg min", "mg max", "%IA/g min", "%IA/g max"]
        t = QTableWidget(0, len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setMinimumHeight(110)

        def fill():
            rows = self.main.study.ranges
            tissues = [x.name for x in self.main.study.tissues]
            t.blockSignals(True)
            t.setRowCount(len(rows))
            for r, row in enumerate(rows):
                it = QTableWidgetItem(row[0])
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setToolTip("" if row[0] in tissues else "not in this study's tissues")
                t.setItem(r, 0, it)
                for c, x in enumerate(row[1:], 1):
                    t.setItem(r, c, QTableWidgetItem(f"{x:g}" if x else ""))
            t.blockSignals(False)
        self._fill_ranges = fill

        def read(*_):
            self._rule(ranges=[[t.item(r, 0).text()] + [_f(t.item(r, c).text()) or 0.0
                                                        for c in range(1, len(heads))]
                               for r in range(t.rowCount())])
        t.itemChanged.connect(read)
        fill()
        v.addWidget(t)
        menu = QMenu(self)

        def offer():
            menu.clear()
            have = {r[0] for r in self.main.study.ranges}
            tissues = [x.name for x in self.main.study.tissues if x.role == "tissue"]
            for name in tissues:
                if name not in have:
                    menu.addAction(name, lambda name=name: self._rule(
                        ranges=self.main.study.ranges + [[name, 0.0, 0.0, 0.0, 0.0]]))
            if menu.isEmpty():
                menu.addAction("every tissue of the study has a row" if tissues else
                               "no tissue in the study yet").setEnabled(False)
        menu.aboutToShow.connect(offer)
        plus = self._plus_minus(v, lambda: None, lambda: (
            [t.removeRow(r) for r in sorted({i.row() for i in t.selectedIndexes()},
                                            reverse=True)], read()))
        plus.setMenu(menu)
        plus.setFixedWidth(48)                   # room for the menu's arrow

    def _log_page(self):
        w, v = self._page("Log", "The log at the bottom of the board: what it records, and "
                          "whether it is written to a file when BioDist closes (else Study ▸ "
                          "Log ▸ Save keeps it). The checks it records can go in the report.")
        lg = PREFS["log"]

        def put(**kw):
            self._set("log", {**PREFS["log"], **kw})
        for k, text in LOG_KINDS.items():
            c = QCheckBox(text)
            c.setChecked(k in lg["what"])
            c.toggled.connect(lambda on, k=k: put(what=[
                x for x in LOG_KINDS if (x == k and on) or (x != k and x in PREFS["log"]["what"])]))
            v.addWidget(c)
        v.addSpacing(10)
        f = QFormLayout()
        c = _combo(list(LOG_SAVE.values()), LOG_SAVE[lg["autosave"]])
        f.addRow("Write it on exit", c)
        name = _combo(LOG_NAMES, lg["naming"], editable=True)
        name.setToolTip("YYYY YY MM DD hh mm ss: the session's start. Another session the same "
                        "day: .2, .3 …")
        ex = QLabel()
        ex.setStyleSheet("color:#8d8d8d;")

        def named():
            if PREFS["log"]["autosave"] == "append":
                name.setEnabled(False)
                ex.setText("BioDist.log")
                return
            name.setEnabled(True)
            ex.setText(_log_name(Path("."), _dt.datetime.now(), name.currentText()))
        name.lineEdit().editingFinished.connect(
            lambda: (put(naming=name.currentText().strip() or LOG_NAMES[0]), named()))
        name.activated.connect(lambda _: (put(naming=name.currentText()), named()))
        name.currentTextChanged.connect(lambda _: named())
        c.activated.connect(lambda i: (put(autosave=list(LOG_SAVE)[i]), named()))
        row = QHBoxLayout()
        row.addWidget(name, 1)
        row.addWidget(ex)
        f.addRow("Named", row)
        named()
        row = QHBoxLayout()
        e = _edit(lg["folder"], str(APP_DIR / "logs"))
        e.editingFinished.connect(lambda: put(folder=e.text().strip()))
        b = QPushButton("…")
        b.setFixedWidth(30)
        b.clicked.connect(lambda: (d := QFileDialog.getExistingDirectory(
            self, "Log folder", e.text())) and (e.setText(d), put(folder=d)))
        row.addWidget(e, 1)
        row.addWidget(b)
        f.addRow("In the folder", row)
        v.addLayout(f)
        v.addStretch(1)
        return w

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export options", "biodist_options.json",
                                              "JSON (*.json)")
        if path and not _save_prefs(Path(path)):
            QMessageBox.warning(self, APP_NAME, f"Could not write {path}")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import options", "", "JSON (*.json)")
        if path:
            self._apply(Path(path))

    def _reset(self):
        if QMessageBox.question(self, APP_NAME, "Every option back to its default?") == \
                QMessageBox.Yes:
            self._apply(None)

    def _apply(self, path):
        _load_prefs(path, None if path else {})
        _save_prefs()
        self._build()
        self.main._later(self.main._sync)()


# -------------------------------------------------------------------- report window
_ITEM = object()                     # _flat's mark for a list item (an animal, a loss…)


def _flat(x, at="") -> dict:
    """A study's json as {path: value}; list items named by their id / name / file, each
    marked `_ITEM` at its own path."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            out.update(_flat(v, f"{at} {k}".strip()))
        return out
    if isinstance(x, list) and x and all(isinstance(v, dict) for v in x):
        out = {}
        for i, v in enumerate(x):
            name = v.get("id") or v.get("name") or (Path(v["path"]).name if v.get("path")
                                                    else "") or \
                "/".join(str(v[k]) for k in ("animal", "tissue") if v.get(k)) or str(i + 1)
            out[f"{at} {name}"] = _ITEM
            out.update(_flat(v, f"{at} {name}"))
        return out
    return {at: ", ".join(map(str, x)) if isinstance(x, list) else "" if x is None else x}


def _changes(old: str, new: str, most=12) -> list[str]:
    """What an edit changed, a line per value: 'animals 107 full_mbq: 55.3 → 55.4'; an
    item added or removed is one line ('animals 7: added'), an empty one none."""
    a, b = _flat(json.loads(old)), _flat(json.loads(new))
    skip = (" typed ", " stamp ", " saved_sha256 ", " embedded ")   # bookkeeping, not edits
    items = [(k, "added", b) for k in b if b[k] is _ITEM and k not in a] + \
        [(k, "removed", a) for k in a if a[k] is _ITEM and k not in b]
    told = ("animals ", "tissues ", "sources ")   # an animal, tissue, file: logged as it goes
    out = [f"{k}: {what} (" + ", ".join(str(v) for p, v in side.items() if p.startswith(
               k + " ") and v not in ("", _ITEM))[:80] + ")" for k, what, side in items
           if any(v not in ("", _ITEM) for p, v in side.items() if p.startswith(k + " "))
           and not (k.startswith(told) and not any(
               k.startswith(i + " ") for i, x in side.items() if x is _ITEM))]
    out += [f"{k}: {a.get(k, '')} → {b.get(k, '')}" for k in dict.fromkeys([*a, *b])
            if a.get(k, "") != b.get(k, "") and _ITEM not in (a.get(k), b.get(k))
            and not any(k.startswith(i + " ") for i, *_ in items)
            and not any(x in f" {k} " for x in skip)]
    return out[:most] + ([f"… and {len(out) - most} more"] if len(out) > most else [])


def _sheet_link(tip, fn) -> QToolButton:
    """▤ on a section title: the list of what the results and the report show."""
    b = AnimalCard._link("▤", tip, fn)
    b.setStyleSheet(f"QToolButton{{border:none;color:{_ACCENT};font-size:15px;}}")
    return b


class _Revert(QStyledItemDelegate):
    """↺ drawn just after a renamed item's text; a click on it gives the name back."""

    @staticmethod
    def spot(view, it) -> QRect:
        r = view.visualItemRect(it)
        x = r.left() + 8 + view.fontMetrics().horizontalAdvance(it.text())
        return QRect(x, r.top(), 18, r.height())

    def paint(self, p, opt, idx):
        super().paint(p, opt, idx)
        view = self.parent()
        it = view.itemFromIndex(idx)
        if it and it.data(Qt.UserRole + 1):
            p.save()
            p.setPen(QColor(_ACCENT))
            p.drawText(self.spot(view, it), Qt.AlignCenter, "↺")
            p.restore()


class NamesWindow(QMainWindow):
    """▤: the animals on the left, the tissues on the right — which the results and the
    report show, in which order, under which name."""

    def __init__(self, main):
        super().__init__(main)
        self.setWindowTitle(f"{APP_NAME} — animals and tissues in the results and report")
        _undo_keys(self, main.undo, main.redo)
        self.animals = AnimalOrderWindow(main, self)
        self.tissues = OutputWindow(main, self)
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet("color:#555;")
        root = QWidget()
        h = QHBoxLayout(root)
        h.addWidget(self.animals, 1)
        h.addWidget(line)
        h.addWidget(self.tissues, 1)
        self.setCentralWidget(root)
        self.resize(1100, 640)
        self.setMinimumWidth(1100)     # user: no narrower than it opens

    def open(self):
        self.animals.fill()
        self.tissues.fill()
        self.show()
        self.raise_()
        self.activateWindow()


class OutputWindow(QWidget):
    """Which tissues the results and the report list, in which order: the grid's tissues on
    the left, the list on the right — drag across (or double-click), drag to reorder, Del."""

    WHAT, LEFT, RESET = "tissues", "<b>Tissues</b> — the grid", "every tissue, grid order"

    def __init__(self, main, win):
        super().__init__(win)
        self.main, self.win = main, win
        self._filling = False
        self.src = QListWidget()
        self.src.setDragDropMode(QAbstractItemView.DragOnly)
        self.src.setDefaultDropAction(Qt.CopyAction)
        self.src.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.src.itemDoubleClicked.connect(lambda _: self._add())
        self.out = QListWidget()
        self.out.setDragDropMode(QAbstractItemView.DragDrop)
        self.out.setDefaultDropAction(Qt.MoveAction)
        self.out.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.out.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.out.itemChanged.connect(self._renamed)
        self.out.setItemDelegate(_Revert(self.out))
        self.out.viewport().installEventFilter(self)
        for sig in ("rowsInserted", "rowsMoved", "rowsRemoved"):
            getattr(self.out.model(), sig).connect(self._changed)
        QShortcut(QKeySequence.Delete, self.out, self._remove)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:#8d8d8d;")
        mid = QVBoxLayout()
        mid.addStretch(1)
        for text, tip, fn in (("→", f"Add the selected {self.WHAT}", self._add),
                              ("←", "Take the selected ones out (Del)", self._remove)):
            b = QPushButton(text)
            b.setFixedWidth(36)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            mid.addWidget(b)
        mid.addStretch(1)
        reset = QPushButton(self.RESET)
        reset.setToolTip(f"Drop the list: the results and report show every one of the "
                         f"{self.WHAT}")
        reset.clicked.connect(lambda: self._apply([]))
        left, right = QVBoxLayout(), QVBoxLayout()
        self.right = right
        left.addWidget(QLabel(self.LEFT))
        left.addWidget(self.src, 1)
        right.addWidget(QLabel("<b>Results and report</b>"))
        right.addWidget(self.out, 1)
        right.addWidget(self.note)
        right.addWidget(reset)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.addLayout(left, 1)
        h.addLayout(mid)
        h.addLayout(right, 1)

    def open(self):
        self.win.open()

    def close(self):
        self.win.hide()

    def fill(self):
        st = self.main.study
        shown = [t.name for t in st.output_tissues()]
        self._filling = True
        self.src.clear()
        self.out.clear()
        for t in st.tissues:
            it = QListWidgetItem(t.name + ("" if t.role == "tissue" else f"   ({t.role})"))
            it.setData(Qt.UserRole, t.name)
            if t.name in shown:
                it.setForeground(QColor("#6f6f6f"))
            self.src.addItem(it)
        for n in shown:
            self.out.addItem(self._out_item(n))
        self._filling = False
        self.note.setText("Your order. A tissue added to the grid later is not in it until "
                          "added here." if st.output else
                          "Every collected tissue, in the grid's order — drag to set your own.")

    # ---- a name as the results and the report show it: typed over, ↺ gives it back
    def _labels(self) -> dict:
        return self.main.study.tissue_labels

    def _original(self, key) -> str:
        return key

    def _out_item(self, key) -> QListWidgetItem:
        lab = self._labels().get(key)
        it = QListWidgetItem(lab or self._original(key))
        it.setData(Qt.UserRole, key)
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        if lab:
            it.setData(Qt.UserRole + 1, True)
            it.setToolTip(f"“{self._original(key)}” everywhere else — ↺ gives it back")
        else:
            it.setToolTip("Double-click (or F2) to rename it for the results and the report")
        return it

    def _renamed(self, it):
        if self._filling:
            return
        key, text = it.data(Qt.UserRole), it.text().strip()
        labels = self._labels()
        if text and text != self._original(key):
            labels[key] = text
        else:
            labels.pop(key, None)
        self.main._later(self.main._sync)()
        QTimer.singleShot(0, self.fill)

    def eventFilter(self, obj, ev):
        """A click on a renamed item's ↺ (just after its name) gives the name back."""
        if ev.type() == QEvent.MouseButtonRelease and obj is self.out.viewport():
            it = self.out.itemAt(ev.position().toPoint())
            if it and it.data(Qt.UserRole + 1) and \
                    _Revert.spot(self.out, it).contains(ev.position().toPoint()):
                self._labels().pop(it.data(Qt.UserRole), None)
                self.main._later(self.main._sync)()
                QTimer.singleShot(0, self.fill)
                return True
        return super().eventFilter(obj, ev)

    def _changed(self, *_):
        if not self._filling:                    # after the drop is done
            QTimer.singleShot(0, lambda: self._apply(
                [self.out.item(i).data(Qt.UserRole) for i in range(self.out.count())]))

    def _add(self):
        have = [self.out.item(i).data(Qt.UserRole) for i in range(self.out.count())]
        self._apply(have + [it.data(Qt.UserRole) for it in self.src.selectedItems()])

    def _remove(self):
        gone = {it.data(Qt.UserRole) for it in self.out.selectedItems()}
        self._apply([self.out.item(i).data(Qt.UserRole) for i in range(self.out.count())
                     if self.out.item(i).data(Qt.UserRole) not in gone])

    def _apply(self, names):
        st = self.main.study
        names = list(dict.fromkeys(n for n in names if st.tissue(n)))
        # ponytail: the whole list emptied = back to every tissue
        st.output = [] if names == [t.name for t in st.tissues if t.role == "tissue"] else names
        self.main._later(self.main._sync)()
        self.fill()


class AnimalOrderWindow(OutputWindow):
    """The animals: the cards' order on the left — the order the data are dealt to them,
    dragged to change it —, the results' and report's on the right, grouped by molecule
    if ticked."""

    WHAT, RESET = "animals", "every animal, card order"
    LEFT = "<b>Animals</b> — the cards, the order the files are dealt in"

    def __init__(self, main, win):
        super().__init__(main, win)
        self.src.setDragDropMode(QAbstractItemView.DragDrop)    # reordered in place too
        self.src.setDefaultDropAction(Qt.MoveAction)
        self.src.model().rowsMoved.connect(self._cards_moved)
        self.group = QCheckBox("group by molecule")
        self.group.setToolTip("Each molecule's animals side by side, the molecule under each "
                              "animal's name — in the results and the report")
        self.group.toggled.connect(self._grouped)
        self.right.insertWidget(2, self.group)

    def fill(self):
        st = self.main.study
        shown = [a.id for a in st.output_animals()]
        self._filling = True
        self.src.clear()
        self.out.clear()
        for a in st.animals:
            it = QListWidgetItem(f"{a.label}   {a.molecule}")
            it.setData(Qt.UserRole, a.id)
            if a.id in shown:
                it.setForeground(QColor("#6f6f6f"))
            self.src.addItem(it)
        for a in st.output_animals():
            self.out.addItem(self._out_item(a.id))
        self.group.blockSignals(True)
        self.group.setChecked(st.group_by == "molecule")
        self.group.blockSignals(False)
        self._filling = False
        self.note.setText("Your order. An animal added later is not in it until added here."
                          if st.animal_output else
                          "Every animal, in the cards' order — drag to set your own.")

    def _labels(self) -> dict:
        return self.main.study.animal_labels

    def _original(self, key) -> str:
        a = self.main.study.animal(key)
        return a.label if a else key

    def _out_item(self, key) -> QListWidgetItem:
        it = super()._out_item(key)
        a = self.main.study.animal(key)
        if a and a.molecule:
            it.setToolTip(f"{a.molecule} — " + it.toolTip())
        return it

    def _cards_moved(self, *_):
        if not self._filling:
            QTimer.singleShot(0, self._reorder_cards)

    def _reorder_cards(self):
        st = self.main.study
        ids = [self.src.item(i).data(Qt.UserRole) for i in range(self.src.count())]
        st.animals.sort(key=lambda a: ids.index(a.id) if a.id in ids else len(ids))
        self.main.log("animal order: " + ", ".join(a.label for a in st.animals))
        self.main._later(self.main._sync)()
        self.fill()

    def _grouped(self, on):
        self.main.study.group_by = "molecule" if on else ""
        self.main._later(self.main._sync)()
        self.fill()

    def _changed(self, *_):
        if not self._filling and self.sender() is self.out.model():
            super()._changed()

    def _apply(self, ids):
        st = self.main.study
        ids = list(dict.fromkeys(i for i in ids if st.animal(i)))
        st.animal_output = [] if ids == [a.id for a in st.animals] else ids
        self.main._later(self.main._sync)()
        self.fill()


class ReportTree(QTreeWidget):
    """The report's sections in their order: a tick each, dragged to reorder; unfolded, what
    each holds — its parts ticked, its choices picked; a value table's unit, layout,
    decimals. Below the last, always: copy / remove the selected section, add one as it
    starts. Edits PREFS["report"] (the report window and Options › Report show the same);
    `changed` after each edit, `picked(i)` when a section is clicked (i: its spec)."""

    changed = Signal()
    picked = Signal(int)
    live: list = []                              # every tree shown: one edit, all redrawn

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setToolTip("Tick what goes in; drag a section to move it; unfold one (▸) for "
                        "what it shows")
        self._open: set[int] = set()             # unfolded sections, by spec
        self.itemChanged.connect(self._ticked)
        self.itemExpanded.connect(lambda it: (i := self._spec(it)) is not None
                                  and self._open.add(i))
        self.itemCollapsed.connect(lambda it: self._open.discard(self._spec(it)))
        self.itemClicked.connect(lambda it, _: it.parent() is None and (
            i := self._spec(it)) is not None and self.picked.emit(i))
        self.currentItemChanged.connect(lambda *_: self._bar_state())
        ReportTree.live.append(self)
        self.fill()

    @staticmethod
    def _spec(it) -> int | None:
        """The spec a section's item stands for (None: the bar, or a part)."""
        d = it.data(0, Qt.UserRole) if it else None
        return d[1] if d and d[0] == "on" else None

    def _current(self) -> int | None:
        it = self.currentItem()
        while it and it.parent():
            it = it.parent()
        return self._spec(it)

    def _bar(self):
        """The last line: copy / remove the selected section, add one from what each starts
        as — a section removed comes back from here."""
        it = QTreeWidgetItem(self)
        it.setFlags(Qt.ItemIsEnabled)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 4, 0, 4)
        self._b_copy = QPushButton("copy")
        self._b_copy.setToolTip("The selected section again, below it — then set it otherwise")
        self._b_copy.clicked.connect(lambda: (i := self._current()) is not None and self._copy(i))
        self._b_remove = QPushButton("remove")
        self._b_remove.setToolTip("Take the selected section out of the list (+ add brings it "
                                  "back, as it starts)")
        self._b_remove.clicked.connect(lambda: (i := self._current()) is not None
                                       and self._remove(i))
        add = QToolButton()
        add.setText("+ add")
        add.setToolTip("A section as it starts, below the selected one (or last)")
        add.setPopupMode(QToolButton.InstantPopup)
        add.setStyleSheet("QToolButton::menu-indicator{image:none;}")
        menu = QMenu(add)
        for key, lab in report.SECTIONS:
            for u in ([u for u, _ in report.VALUE_UNITS] if key == "values" else [""]):
                sp = report._one({"key": key, "on": True, **({"unit": u} if u else {})})
                menu.addAction(report.title(sp), lambda sp=sp: self._add(sp))
        add.setMenu(menu)
        for b in (self._b_copy, self._b_remove, add):
            h.addWidget(b)
        h.addStretch(1)
        self.setItemWidget(it, 0, box)
        self._bar_state()

    def _bar_state(self):
        on = self._current() is not None
        for b in (getattr(self, "_b_copy", None), getattr(self, "_b_remove", None)):
            if b is not None and isValid(b):
                b.setEnabled(on)

    @staticmethod
    def specs() -> list[dict]:
        return PREFS["report"]

    def fill(self):
        PREFS["report"] = report.clean(PREFS["report"])     # the shipped list, filled out
        sb = self.verticalScrollBar().value()
        self.blockSignals(True)
        self.clear()
        for i, sp in enumerate(self.specs()):
            if sp.get("gone"):
                continue
            top = QTreeWidgetItem([report.title(sp)])
            top.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled
                         | Qt.ItemIsSelectable)
            top.setCheckState(0, Qt.Checked if sp["on"] else Qt.Unchecked)
            top.setData(0, Qt.UserRole, ("on", i))
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.addTopLevelItem(top)

            def child(text, data=None, on=None):
                it = QTreeWidgetItem(top, [text])
                it.setFlags(Qt.ItemIsEnabled | (Qt.ItemIsUserCheckable if on is not None
                                                else Qt.NoItemFlags))
                if on is not None:
                    it.setCheckState(0, Qt.Checked if on else Qt.Unchecked)
                it.setData(0, Qt.UserRole, data)
                return it

            def row(label, w):
                it = child("")
                box = QWidget()
                h = QHBoxLayout(box)
                h.setContentsMargins(0, 0, 0, 0)
                if label:
                    h.addWidget(QLabel(label))
                h.addWidget(w)
                h.addStretch(1)
                self.setItemWidget(it, 0, box)
            for name, kind, label, choices, _ in report.OPTIONS.get(sp["key"], []):
                if kind == "bool":
                    child(label, ("bool", i, name), sp[name])
                elif kind == "multi":
                    for k, lab in choices:
                        child(lab, ("multi", i, name, k), k in sp[name])
                else:
                    c = _combo([lab for _, lab in choices], dict(choices)[sp[name]])
                    c.activated.connect(lambda x, i=i, name=name, ch=choices:
                                        self._set(i, name, ch[x][0]))
                    row(label, c)
            if sp["key"] == "values":
                cu = _combo([lab for _, lab in report.VALUE_UNITS],
                            dict(report.VALUE_UNITS)[sp["unit"]])
                cu.setToolTip("SUV: body-weight SUV, (Bq/g of tissue) / (injected Bq / g of "
                              "body) — g/g, unitless")
                cu.activated.connect(lambda x, i=i: self._set(i, "unit",
                                                              report.VALUE_UNITS[x][0]))
                row("unit", cu)
                cl = _combo([lab for _, lab in report.LAYOUTS], dict(report.LAYOUTS)[sp["layout"]])
                cl.activated.connect(lambda x, i=i: self._set(i, "layout", report.LAYOUTS[x][0]))
                row("layout", cl)
                nd = QSpinBox()
                nd.setRange(0, 8)
                nd.setKeyboardTracking(False)
                nd.setValue(PREFS["digits"].get(sp["unit"], 2) if sp["digits"] is None
                            else sp["digits"])
                nd.setToolTip("Decimals in this table — until set here, those of the Results")
                nd.valueChanged.connect(lambda n, i=i: self._set(i, "digits", n))
                row("decimals", nd)
            top.setExpanded(i in self._open)
            if i == getattr(self, "_select", None):
                self.setCurrentItem(top)
        self._select = None
        self._bar()
        self.blockSignals(False)
        self._bar_state()
        self.verticalScrollBar().setValue(sb)

    def _ticked(self, it, _col=0):
        d, sp_list = it.data(0, Qt.UserRole), self.specs()
        if not d:
            return
        on = it.checkState(0) == Qt.Checked
        sp = sp_list[d[1]]
        if d[0] == "on":
            sp["on"] = on
        elif d[0] == "bool":
            sp[d[2]] = on
        else:
            choices = next(o[3] for o in report.OPTIONS[sp["key"]] if o[0] == d[2])
            sp[d[2]] = [k for k, _ in choices
                        if (k == d[3] and on) or (k != d[3] and k in sp[d[2]])]
        self._done(refill=False)

    def _set(self, i, key, value):
        self.specs()[i][key] = value
        self._done()

    def _put(self, i, sp):
        """A section in at spec i, selected and unfolded; the specs after it shift."""
        self.specs().insert(i, sp)
        self._open = {j + (j >= i) for j in self._open} | {i}
        self._select = i
        self._done()

    def _copy(self, i):
        self._put(i + 1, copy.deepcopy(dict(self.specs()[i], on=True)))

    def _remove(self, i):
        """Out of the list. The last of a kind stays as "gone" (hidden): the shipped list
        would add it back otherwise."""
        sp = self.specs()[i]
        if any(x["key"] == sp["key"] and not x.get("gone") for j, x in
               enumerate(self.specs()) if j != i):
            del self.specs()[i]
            self._open = {j - (j > i) for j in self._open if j != i}
        else:
            self.specs()[i] = {"key": sp["key"], "on": False, "gone": True}
            self._open.discard(i)
        self._done()

    def _add(self, sp):
        """A section as it starts, below the selected one — taking the place of one of its
        kind removed before, if any."""
        cur = self._current()
        i = len(self.specs()) if cur is None else cur + 1
        gone = next((j for j, x in enumerate(self.specs()) if x.get("gone")
                     and x["key"] == sp["key"]), None)
        if gone is not None:
            del self.specs()[gone]
            self._open = {j - (j > gone) for j in self._open}
            i -= gone < i
        self._put(i, dict(sp))

    def dropEvent(self, ev):
        """A section dropped above or below another — never into one; on the bar: last."""
        src, tgt = self.currentItem(), self.itemAt(ev.position().toPoint())
        while src and src.parent():
            src = src.parent()
        while tgt and tgt.parent():
            tgt = tgt.parent()
        ev.setDropAction(Qt.IgnoreAction)
        ev.accept()
        i = self._spec(src)
        if i is None or not tgt or src is tgt:
            return
        j = self._spec(tgt)
        j = len(self.specs()) if j is None else \
            j + (ev.position().y() > self.visualItemRect(tgt).center().y())
        j -= j > i
        self.specs().insert(j, self.specs().pop(i))
        self._open = {j} if i in self._open else set()
        self._done()

    def _done(self, refill=True):
        """Kept for the next report; every tree shown follows."""
        PREFS["report"] = report.clean(PREFS["report"])
        _save_prefs()
        ReportTree.live = [t for t in ReportTree.live if isValid(t)]   # pages rebuilt: gone
        for t in ReportTree.live:
            if t is not self or refill:
                QTimer.singleShot(0, lambda t=t: isValid(t) and t.fill())
        self.changed.emit()


class ReportWindow(QMainWindow):
    """Pick the format, then the sections — ticked, in the order dragged, a table's unit and
    layout set on it, copied for a second unit —, see the report, save it as one file."""

    FORMATS = [(".odt", "Document (.odt) — opens in Word and LibreOffice"), (".pdf", "PDF"),
               (".xlsx", "Excel workbook — a sheet per section"), (".md", "Markdown text"),
               (".html", "Web page")]

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle(f"{APP_NAME} — report")
        self.resize(1100, 760)
        side = QWidget()
        side.setFixedWidth(320)
        v = self.layout_side = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)
        fmt = dict(self.FORMATS)
        self.c_format = _combo([lab for _, lab in self.FORMATS],
                               fmt.get(PREFS["report_format"], fmt[".odt"]))
        self.c_format.setToolTip("What Save writes. A workbook gets a sheet per section")
        self.c_format.activated.connect(self._format_set)
        v.addWidget(QLabel("<b>Format</b>"))
        v.addWidget(self.c_format)
        self.head = QLabel()
        v.addSpacing(8)
        v.addWidget(self.head)
        self.tree = ReportTree()
        self.tree.changed.connect(lambda: self.isVisible() and self.refresh())
        self.tree.picked.connect(self._goto)
        v.addWidget(self.tree, 1)
        b = QPushButton("Save report…")
        b.setToolTip("Ctrl+S")
        b.clicked.connect(self.save)
        QShortcut(QKeySequence.Save, self, self.save)
        v.addSpacing(8)
        v.addWidget(b)
        self.view = QTextBrowser()
        self.view.setMinimumWidth(MIN_VIEW)
        root = QWidget()
        h = QHBoxLayout(root)
        h.addWidget(side)
        h.addWidget(self.view, 1)
        self.setCentralWidget(root)
        self.statusBar()
        _undo_keys(self, lambda: main._prefs_undo(True), lambda: main._prefs_undo(False))
        self._head()

    @property
    def specs(self) -> list[dict]:
        return PREFS["report"]

    def _head(self):
        self.head.setText("<b>Sheets</b>" if self.ext == ".xlsx" else "<b>Sections</b>")

    @property
    def ext(self) -> str:
        return self.FORMATS[self.c_format.currentIndex()][0]

    def _format_set(self, _=0):
        PREFS["report_format"] = self.ext
        _save_prefs()
        self._head()
        if (ow := self.main.options_win) and getattr(ow, "_fmt", None) and isValid(ow._fmt):
            ow._fmt.setCurrentIndex(self.c_format.currentIndex())

    def _goto(self, r):
        """Scroll the preview to the clicked section: every ticked one is a level-2 heading."""
        if not (0 <= r < len(self.specs)) or not self.specs[r]["on"]:
            return
        n = sum(x["on"] for x in self.specs[:r])
        doc, b = self.view.document(), self.view.document().begin()
        while b.isValid():
            if b.blockFormat().headingLevel() == 2:
                if n == 0:
                    y = doc.documentLayout().blockBoundingRect(b).top()
                    return self.view.verticalScrollBar().setValue(int(y))
                n -= 1
            b = b.next()

    def _sections(self):
        m = self.main
        return report.build(m._eff, m.res, m.runs,
                            [x[10:] for x in m._log if x[10:11] in "✗⚠✓" and not re.search(
                                r"(?i)recount|guess|rack slip", x)], self.specs,
                            PREFS["digits"])

    def _title(self) -> str:
        s = self.main._eff
        return f"Biodistribution — {s.name or 'study'} ({s.date})"

    def refresh(self):
        self.view.setMarkdown(report.to_markdown(self._sections(), self._title()))
        root = self.view.document().rootFrame()  # a table as wide as the page drew its
        f = root.frameFormat()                   # border 2 px past it: a sideways bar
        f.setRightMargin(f.leftMargin() + 8)
        root.setFrameFormat(f)

    @busy("Writing the report…")
    def write(self, path: Path):
        secs, ext = self._sections(), path.suffix.lower()
        if ext == ".xlsx":
            return report.to_xlsx(secs, path)
        md = report.to_markdown(secs, self._title())
        if ext == ".md":
            return path.write_text(md, encoding="utf-8")
        doc = QTextDocument()
        doc.setMarkdown(md)
        if ext == ".html":
            return path.write_text(doc.toHtml(), encoding="utf-8")
        if ext == ".pdf":
            pdf = QPdfWriter(str(path))
            pdf.setPageSize(QPageSize(QPageSize.A4))
            pdf.setPageOrientation(QPageLayout.Landscape)
            return doc.print_(pdf)
        if not QTextDocumentWriter(str(path), b"ODF").write(doc):
            raise OSError(f"could not write {path}")

    def save(self):
        ext, lab = self.FORMATS[self.c_format.currentIndex()]
        name = f"{self.main._eff.name or 'biodist'}_report{ext}"
        path, _ = QFileDialog.getSaveFileName(self, "Save report", _here(self.main, name),
                                              f"{lab} (*{ext})")
        if not path:
            return
        path = str(Path(path).with_suffix(ext)) if Path(path).suffix.lower() != ext else path
        try:
            self.write(Path(path))
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not write the report:\n{e}")
            return
        self.statusBar().showMessage(f"Written to {path}", 6000)
        self.main.log(f"report written: {Path(path).name}")


# ----------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1180, 900)
        self.setAcceptDrops(True)
        self._loading = False
        self._path: Path | None = None
        self.runs: dict[str, hidex.Run] = {}
        self.results = ResultsWindow(self)
        self.results.data_changed.connect(self._data_changed)
        self.report = ReportWindow(self)
        self.animal_win = AnimalWindow(self)
        self.names_win = NamesWindow(self)
        self.output_win, self.animal_order = self.names_win.tissues, self.names_win.animals
        self.options_win: OptionsWindow | None = None
        self._log: list[str] = []            # "HH:MM:SS  ⚠ text", oldest first
        self._log_done: list[str] = []       # earlier studies' of this session
        self._log_start = _dt.datetime.now()
        self._log_path: Path | None = None
        self._facts: dict[str, tuple] = {}   # what the log last said: key -> (symbol, text)
        self._offered: set[str] = set()       # findings already offered a fix (this study)
        self._summaries: dict[str, str] = {}  # source uid -> its vials in one line
        self.cards: list[AnimalCard] = []
        self._want = None                     # (animal, row, col) Tab is heading to
        self.auto_notes: list[str] = []
        self.guess_why: dict[str, str] = {}      # source uid -> why the guess put it there
        sys.excepthook = self._error             # a click's exception: in the log, not lost
        self._undo: list[str] = []   # study snapshots (json), newest last
        self._redo: list[str] = []
        self._snap: str | None = None  # the state the stacks are relative to
        self._names: tuple = (None, [])     # (study, [(animal, ID, label)]) last drawn
        self._saved = ""               # what is on disk, to ask before losing edits

        _load_prefs()
        _PREFS_UNDO["now"] = [json.dumps(PREFS, sort_keys=True)]   # where Ctrl+Z starts
        self.study = _new_study()
        self._date_typed = False   # until then the first dropped run sets the date

        self._toolbar()
        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(10, 8, 10, 8)

        self.sec_animals = Section("Animals")
        self.sec_animals.bar.insertWidget(4, AnimalCard._link(
            "⤢", "Every animal side by side in the animal window: a table typed and pasted "
                 "into like Excel", self.animal_win.show_all))
        self.sec_animals.bar.insertWidget(5, _sheet_link(
            "The animals' order — the cards', the files are dealt in it — and which the "
            "results and the report show, in which order, grouped by molecule",
            self.animal_order.open))
        self.cards_row = QHBoxLayout()
        self.cards_row.setSpacing(8)
        self.cards_row.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.cards_row.setContentsMargins(0, 0, 0, 0)
        holder = QWidget()
        holder.setLayout(self.cards_row)
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidget(holder)
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.NoFrame)
        self.sec_animals.inner.addWidget(self.cards_scroll)
        v.addWidget(self.sec_animals)

        self.sec_tissues = Section("Tissues", "Add a tissue, a recorded list, a file…")
        self.m_tissues = QMenu(self)
        self.m_tissues.aboutToShow.connect(lambda: self._tissue_menu(self.m_tissues))
        self.sec_tissues.add_clicked.connect(
            lambda: self.m_tissues.exec(QCursor.pos()))
        self.sec_tissues.bar.insertWidget(4, _sheet_link(
            "Which tissues the results and the report show, and in which order",
            self.output_win.open))
        self.t_tissues = Table(["tissue", "role", "batch", "#"])
        self.t_tissues.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.t_tissues.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.t_tissues.delete_rows.connect(self.del_tissues)
        self.t_tissues.itemChanged.connect(self._tissue_edited)
        self.t_tissues.setItemDelegate(_Parts(self.t_tissues, lambda c: c >= TC))
        self.t_tissues.cellClicked.connect(self._tissue_fold)
        self._tissue_open: dict[str, bool] = {}   # tissue -> its typed rows shown (default)
        self.t_tissues.stretch = range(TC, 1000)    # the animals' columns
        self.t_tissues.cap = 150
        self._trows: list[tuple[int, str]] = []   # table row -> (tissue index, typed field)
        m = QMenu(self)
        m.aboutToShow.connect(lambda: self._tissue_menu(m))
        self.h_tissues = self._hint(
            self.sec_tissues,
            "A recorded list (+), or drop a one-column list here, or paste one with Ctrl+V; "
            "rename by double-clicking. "
            "Mark the injection site as <b>tail</b> and an empty control tube as <b>blank</b>. "
            "<b>+</b> on a tissue's row types a <b>mass</b> or an <b>activity</b> by hand "
            "(paraffin-weighed tissue, dose calibrator) — they win over the files — or a "
            "<b>note</b>. Tissues collected and counted on their own (straight after "
            "euthanasia…) are a <b>batch</b> of their own: a second list dropped is, or pick "
            "<b>new batch…</b>; <b>#</b> is the order in its batch.",
            "Open a recorded tissue list, drop a one-column list here, or paste one (Ctrl+V)",
            m)
        self.l_tissue_note = QLabel()
        self.l_tissue_note.setTextFormat(Qt.PlainText)   # no wrap: it would squeeze the board
        self.l_tissue_note.setStyleSheet("color:#8d8d8d;")
        self.sec_tissues.inner.addWidget(self.l_tissue_note)
        self.sec_tissues.inner.addWidget(self.t_tissues)
        self.batch_bar = QWidget()
        QHBoxLayout(self.batch_bar).setContentsMargins(0, 4, 0, 0)
        self.sec_tissues.inner.addWidget(self.batch_bar)
        v.addWidget(self.sec_tissues)

        self.sec_sources = Section("Data sources", "Add the counter's files")
        self.sec_sources.add_clicked.connect(self.open_files)
        self.t_sources = Table(["file", "run", "kind", "vials (racks)", "animals", "tissues",
                                "order", ""])
        self.t_sources.stretch = (7,)          # the blank last column: the strips' room
        self.t_sources.setEditTriggers(QAbstractItemView.DoubleClicked
                                       | QAbstractItemView.AnyKeyPressed)
        for c in (4, 5):                            # typed or picked: the whole file
            self.t_sources.setItemDelegateForColumn(c, _NameDelegate(
                self.t_sources, self._src_choices, self._src_names, lambda _: True))
        self.t_sources.setItemDelegateForColumn(3, _Middle(self.t_sources, lambda _: True))
        self.t_sources.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.t_sources.delete_rows.connect(self.del_sources)
        self.t_sources.cellClicked.connect(self._source_clicked)
        self._srows: list[int | None] = []          # table row -> source index; None: a strip
        self.h_sources = self._hint(
            self.sec_sources,
            "Drop the counter's files anywhere on the window (Hidex AutoExport .xlsx, Wizard2 "
            ".csv — the Wizard2 asks for its counting efficiency). Once the animals and tissues "
            "are in, BioDist works out which weighing is the empty and which the filled tubes "
            "(by tube weight, rack by rack — a rack weighed out of turn is caught), and gives "
            "the counts to the animals in order, each file to the tissue batch its vials fit. "
            "Click a file (▸) to unfold its vials and pick animal and tissue vial by vial — "
            "<b>Tab</b> then fills the vials after it the same way; <b>Guess again</b> hands "
            "it back. Which window and which counting are used: Options › Results.",
            "Add the counter's files — or drop them anywhere on the window", self.open_files)
        opts = QHBoxLayout()
        self.c_eff = QCheckBox("the counter's own efficiencies")
        self.c_eff.setToolTip(EFF_TIP)
        self.c_eff.toggled.connect(lambda on: self._data_changed({"file_eff": on}))
        opts.addWidget(self.c_eff)
        opts.addStretch(1)
        opts.addWidget(AnimalCard._link(
            "Guess again", "Let BioDist place the files again from the animals, the tissues "
                           "and the tube weights — asks whether those placed by hand go too, "
                           "then says what moved",
            lambda: self._guess_again()))
        self.w_src_opts = QWidget()                  # hidden with the table while empty
        opts.setContentsMargins(0, 0, 0, 0)
        self.w_src_opts.setLayout(opts)
        self.sec_sources.inner.addWidget(self.w_src_opts)
        self.t_eff = Table(["counter", "isotope", "energy window", "efficiency",
                            "Bq per CPM", "in the files"])
        self.t_eff.setToolTip(EFF_TIP)
        self.t_eff.setEditTriggers(QAbstractItemView.DoubleClicked
                                   | QAbstractItemView.AnyKeyPressed)
        self.t_eff.itemChanged.connect(self._eff_edited)
        self.t_eff.hide()
        box = QHBoxLayout()
        box.addWidget(self.t_eff)
        box.addStretch(1)
        self.sec_sources.inner.addLayout(box)
        self.sec_sources.inner.addWidget(self.t_sources)
        self._strip_open: dict[str, bool] = {}      # source uid -> unfolded / folded by hand
        self._strip_shape = None
        self._strip_rows: list = []      # per source: (uid, name, vials, summary, open)
        self._strip_sheets: dict[int, Sheet] = {}   # source index -> its unfolded vials
        self._proposal = None            # (source uid, {vial key: [animal, tissue]}): Tab fills
        v.addWidget(self.sec_sources)

        self.sec_check = Section("Log")
        self.check = QTextBrowser()
        self.check.setOpenExternalLinks(False)
        self.check.setMinimumHeight(140)
        self.check.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)   # height: stretch
        self.sec_check.inner.addWidget(self.check)
        v.addWidget(self.sec_check, 1)          # the check takes the height left over

        outer = QScrollArea()
        outer.setWidget(root)
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.NoFrame)
        self.setCentralWidget(outer)

        for keys, fn in (("Ctrl+N", self.new_study), ("Ctrl+P", self.show_report),
                         ("Ctrl+O", self.open_study), ("Ctrl+S", self.save_study),
                         ("Ctrl+Shift+S", lambda: self.save_study(True)),
                         ("Ctrl+R", self.show_results), ("F5", self.recompute),
                         ("Ctrl+Shift+N", self.add_animal), ("Ctrl+V", self.paste),
                         ("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo),
                         ("Ctrl+Shift+Z", self.redo)):
            QShortcut(QKeySequence(keys), self, fn)
        self.statusBar().showMessage("Drop the counter files anywhere, or open a saved study "
                                     "(Ctrl+O). F5 recomputes, Ctrl+R shows the results.")
        self._sync()
        self._reset_history()

    # ------------------------------------------------------------------- chrome
    @staticmethod
    def _later(fn):
        """Defer a full rebuild — a widget must not be destroyed inside its own signal."""
        return lambda *_: QTimer.singleShot(0, fn)

    def _hint(self, sec, html, text, plus) -> QWidget:
        """A section while it is empty: a + and a line saying what to do, in place of an
        empty table; the longer help on the title's tooltip (and the +'s)."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 4, 2, 6)
        b = QToolButton()
        b.setIcon(_plus(22))
        b.setIconSize(QSize(22, 22))
        b.setFixedSize(34, 34)
        b.setToolTip(html)
        b.setStyleSheet("QToolButton{border:1px dashed #555;border-radius:4px;} "
                        "QToolButton:hover{background:#3d3d3d;} "
                        "QToolButton::menu-indicator{image:none;}")
        if isinstance(plus, QMenu):
            b.setMenu(plus)
            b.setPopupMode(QToolButton.InstantPopup)
        else:
            b.clicked.connect(plus)
        lab = QLabel(text)
        lab.setStyleSheet("color:#8d8d8d;")
        h.addWidget(b)
        h.addWidget(lab)
        h.addStretch(1)
        sec._title.setToolTip(html)
        sec.inner.insertWidget(0, w)
        return w

    def _tissue_menu(self, m: QMenu):
        """The recorded lists, a file, the clipboard, one tissue — and recording this list."""
        m.clear()
        for name, tissues in PREFS["tissue_lists"].items():
            a = m.addAction(f"{name}  ({len(tissues)})",
                            lambda name=name: self._open_list(name))
            a.setToolTip(", ".join(tissues))
        if PREFS["tissue_lists"]:
            m.addSeparator()
        m.addAction("Open a file…", self.open_files)
        m.addAction("Paste a list (Ctrl+V)", self.paste)
        m.addAction("Add one tissue", self.add_tissue)
        m.addSeparator()
        rec = m.addAction("Record this list…", self._record_list)
        rec.setEnabled(bool(self.study.tissues))
        m.addAction("Edit the recorded lists…", lambda: self.show_options("Tissue table"))

    def _open_list(self, name):
        tissues = PREFS["tissue_lists"].get(name, [])
        b = self._set_tissues(list(tissues), name)
        self.log(f"tissue list “{name}”: {len(tissues)} tissues" + (f" (batch “{b}”)" if b
                                                                      else ""))

    def _record_list(self):
        """This study's tissues, in their order, kept under a name for the next study."""
        name, ok = QInputDialog.getText(self, APP_NAME, "Record this tissue list as:",
                                        text=self.study.name or "my tissues")
        if ok and name.strip():
            PREFS["tissue_lists"][name.strip()] = [x.name for x in self.study.tissues]
            _save_prefs()
            self.statusBar().showMessage(f"Recorded “{name.strip()}” — the Tissues' + offers "
                                         "it; Options › Tissue table edits it", 6000)

    def _toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        b = QToolButton()
        b.setText("Study")
        b.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(b)
        # the \t text only labels the shortcut: the QShortcuts below do the work
        for text, fn in (("New\tCtrl+N", self.new_study), ("Open…\tCtrl+O", self.open_study),
                         ("Save\tCtrl+S", self.save_study),
                         ("Save as…\tCtrl+Shift+S", lambda: self.save_study(True)),
                         (None, None), ("Add files…", self.open_files),
                         ("Report…\tCtrl+P", self.show_report)):
            if text:
                m.addAction(text, fn)
            else:
                m.addSeparator()
        lm = m.addMenu("Log")
        lm.addAction("Save log", self.save_log)
        lm.addAction("Save log as…", lambda: self.save_log(True))
        b.setMenu(m)
        tb.addWidget(b)
        tb.addAction("Options", self.show_options).setToolTip(
            "Card fields, formats, isotopes, species and strains…")
        tb.addSeparator()
        tb.addWidget(QLabel(" study "))
        self.e_name = _edit("", "name", 260)
        self.e_name.editingFinished.connect(
            lambda: setattr(self.study, "name", self.e_name.text().strip()))
        tb.addWidget(self.e_name)
        self.e_date = QDateEdit()
        self.e_date.setCalendarPopup(True)
        self.e_date.setDisplayFormat("yyyy-MM-dd")
        self.e_date.setToolTip("Experiment date — the day the HH:MM times above belong to")
        self.e_date.dateChanged.connect(self._date_edited)
        tb.addWidget(self.e_date)
        tb.addSeparator()
        for text, tip, fn, style in (
                ("Results", "Open the results grid (Ctrl+R)", self.show_results,
                 f"QPushButton{{background:{_ACCENT};color:white;font-weight:600;"
                 f"padding:3px 16px;border-radius:3px;}}"),
                ("Report…", "Choose what goes in a report and save it (Ctrl+P)",
                 self.show_report, "QPushButton{padding:3px 10px;}")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setStyleSheet(style)
            b.clicked.connect(fn)
            tb.addWidget(b)

    def _prefs_undo(self, back):
        """Ctrl+Z in the Options or the Report: the options as they were, everywhere."""
        if not _prefs_step(back):
            return QApplication.activeWindow().statusBar().showMessage(
                f"Nothing to {'undo' if back else 'redo'} in the options", 3000) \
                if isinstance(QApplication.activeWindow(), QMainWindow) else None
        if self.options_win:
            self.options_win._build()
        for tr in ReportTree.live:
            if isValid(tr):
                tr.fill()
        self.results._unit_set()
        self._later(self._sync)()

    def show_options(self, page=""):
        if self.options_win is None:
            self.options_win = OptionsWindow(self)
        ow = self.options_win
        names = [ow.topics.item(i).text() for i in range(ow.topics.count())]
        if page in names:
            ow.topics.setCurrentRow(names.index(page))
        ow.refresh_rules()
        _bring(ow)

    def _show_field(self, animal, key, on, every=False):
        """A card field shown or hidden — on every animal if Options says so, or `every` (the
        animal window's table view; a note is one card's). What it holds is kept; a field of
        one's own left empty goes."""
        every = (every or PREFS["field_all"]) and key != "note"
        for a in self.study.animals if every else [animal]:
            if _EV_SEP in key:                   # a procedure's: it lives in the procedure
                pass
            elif key not in CARD_KEYS and on:
                a.extra.setdefault(_xkey(a, key), "")
            elif key not in CARD_KEYS and not _get(a, key).strip():
                a.extra.pop(_xkey(a, key), None)
            a.show[key] = on
        if not on and key != "note":
            self.log(f"{key} hidden on {'every card' if every else animal.label}"
                     f" — what it holds is kept; the animal window's “on card” tick shows it "
                     "again, Ctrl+Z undoes it")
        self._later(self._sync)()

    def _date_edited(self, d: QDate):
        if self._loading:
            return
        self.study.date = d.toString(Qt.ISODate)
        self._date_typed = True
        self.log(f"study date set to {self.study.date}")
        self._sync()

    def _data_changed(self, fields):
        for k, v in fields.items():
            setattr(self.study, k, v)
        self.recompute()

    @busy("Guessing…")
    def _guess_again(self, keep=None):
        """Every file placed from the data again — those placed by hand too, if asked —
        then what moved, in a message and in the log."""
        st = self.study
        hand = [s for s in st.sources if not s.auto]
        if hand and keep is None:
            box = QMessageBox(QMessageBox.Question, APP_NAME,
                              f"{len(hand)} file(s) are placed by hand"
                              + (f", {sum(1 for s in hand if s.slotmap)} of them vial by vial"
                                 if any(s.slotmap for s in hand) else "")
                              + ". Guess them again too, or keep them as they are?", parent=self)
            b_keep = box.addButton("Keep them", QMessageBox.AcceptRole)
            box.addButton("Guess them too", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() not in box.buttons()[:2]:
                return
            keep = box.clickedButton() is b_keep

        def placed():
            out = {}
            for s in self._eff.sources:
                m = s.mapping(self.runs[s.path]) if s.path in self.runs else {}
                out[s.uid] = (KIND_LABEL.get(s.kind, s.kind),
                              names_summary([p[0] for p in m.values()], []), m)
            return out
        before = placed()
        for s in st.sources:
            if not (keep and not s.auto):
                s.auto = True
        self.recompute()
        after = placed()
        moved = []
        for s in st.sources:
            b, a = before.get(s.uid), after.get(s.uid)
            if not b or not a or b == a:
                continue
            n = sum(1 for k in set(b[2]) | set(a[2]) if b[2].get(k) != a[2].get(k))
            moved.append(f"{Path(s.path).name}: " + (
                f"{b[0]} {b[1]} → {a[0]} {a[1]}" if b[:2] != a[:2] else
                f"{n} vial(s) placed differently (the order typed by hand is gone)"))
        self.log("guess again" + (" (hand placements kept)" if keep else "") + ": "
                 + (f"{len(moved)} file(s) moved" if moved else "nothing moved"), "↻", "edits")
        for line in moved:
            self.log(line, "↻", "edits")
        if self.isVisible():
            QMessageBox.information(self, APP_NAME, "Guess again: " + (
                "every file stays where it was." if not moved else
                f"{len(moved)} file(s) placed differently (Ctrl+Z undoes it):\n\n"
                + "\n".join(moved[:20]) + ("\n…" if len(moved) > 20 else ""))
                + ("\n\n" + "\n".join(self.auto_notes[:10]) if self.auto_notes else ""))

    # -------------------------------------------------------------- drag and drop
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, ev):
        paths = [Path(u.toLocalFile()) for u in ev.mimeData().urls() if u.isLocalFile()]
        if paths:
            ev.acceptProposedAction()
            self.add_files(paths)

    def paste(self):
        """Ctrl+V: a tissue list, or a block of manual masses, depending on shape."""
        if sh := _sheet_for(QApplication.focusWidget()):
            return sh.paste()
        text = QApplication.clipboard().text().strip()
        if not text:
            return
        rows = [r.split("\t") for r in text.splitlines() if r.strip()]
        cur = self.t_tissues.currentItem() if self.t_tissues.hasFocus() else None
        if cur and cur.column() >= TC and self._trows[cur.row()][1]:
            for dr, vals in enumerate(rows):          # a block of typed values from Excel
                r = cur.row() + dr
                for dc, v in enumerate(vals):
                    c = cur.column() + dc
                    if r < len(self._trows) and self._trows[r][1] and \
                            c - TC < len(self.study.animals):
                        self._set_manual(r, c, v)
            self._sync()
            return
        if all(len(r) == 1 for r in rows):
            if any(_f(r[0]) is not None or parse_time(r[0], self.study.day) for r in rows):
                self.statusBar().showMessage(
                    "Paste not used: numbers or times are not a tissue list — click into a "
                    "field first to paste a value there", 7000)
                return
            self._set_tissues([r[0].strip() for r in rows], "pasted")
            self.statusBar().showMessage(f"Pasted {len(rows)} tissues", 5000)
            return
        added = 0
        for r in rows:
            if len(r) >= 3 and _f(r[2]) is not None:
                self.study.manual.append(Manual(r[0].strip(), r[1].strip(), mass_g=_f(r[2]),
                                                mbq=_f(r[3]) if len(r) > 3 else None,
                                                time=r[4].strip() if len(r) > 4 else ""))
                added += 1   # the tissue grid opens the mass/activity rows for these
        self.statusBar().showMessage(
            f"Pasted {added} hand-typed rows (animal, tissue, mass, [MBq], [time])"
            if added else "Paste not understood — expected one column of tissues, or "
                          "animal/tissue/mass columns", 7000)
        self._sync()

    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add files", _here(self),
                                                "Data (*.xlsx *.csv *.json);;All files (*)")
        if paths:
            self.add_files([Path(p) for p in paths])

    @busy("Reading the files…")
    def add_files(self, paths):
        """Classify every dropped file and put it where it belongs."""
        added, msgs, lists = 0, [], []
        for p in sorted(paths):
            if p.suffix.lower() == ".json":
                if self._keep_or_save():
                    self._load_study(p)
                return
            try:
                run = hidex.read(p)
            except Exception:  # noqa: BLE001 — not a Hidex file, try the other shapes
                run = None
            if run is not None:
                self.runs[str(p)] = run
                if any(Path(x.path) == Path(p) for x in self.study.sources):
                    continue                         # already in: dropping it again is a no-op
                self.study.sources.append(Source(uid=self.study.new_uid(), path=str(p),
                                                 kind=kind_of(run), stamp=stamp(p)))
                added += 1
                continue
            st = self.study
            try:                                 # masses typed in a sheet: animals across
                sheet = read_weights(p, st.animals, [t.name for t in st.tissues]) \
                    if st.animals and st.tissues else None
            except Exception:  # noqa: BLE001 — not that either
                sheet = None
            if sheet:
                msgs.append(self._weights_in(p, *sheet))
                continue
            try:
                animals = read_animals(p)
                if animals:
                    self.study.animals = animals
                    msgs.append(f"{p.name}: {len(animals)} animals")
                    continue
            except Exception:  # noqa: BLE001 — not the injected-activity layout either
                pass
            try:
                col = read_column(p)
            except Exception as e:  # noqa: BLE001
                msgs.append(f"{p.name}: not understood ({e})")
                continue
            if col:
                lists.append((p, col))
        # the longest list is the main run, whatever the file names sort as
        # ponytail: lists dropped one at a time take the first as main; the run column fixes it
        for p, col in sorted(lists, key=lambda x: -len(x[1])):
            b = self._set_tissues(col, p.stem)
            msgs.append(f"{p.name}: {len(col)} tissues"
                        + (f", counted on their own (batch “{b}” in Tissues)" if b else ""))
        if added:
            msgs.append(f"{added} counter file(s)")
            self._time_order()
            auto_assign(self.study, self.runs)     # the date below reads the kinds
            if not self._date_typed and self._file_date():
                self.study.date = self._file_date()
                msgs.append(f"date {self.study.date}")
        self.statusBar().showMessage(" · ".join(msgs) or "Nothing recognised", 8000)
        if msgs:
            self.log(" · ".join(msgs))
        self._sync()
        if added:
            self._offer_fixes()

    def _weights_in(self, p, rows, unsure, unknown) -> str:
        """A sheet of masses: each one a typed mass (it wins over the tubes); what could not
        be read, or barely anything, said in a message with the layout that always reads."""
        st = self.study
        for aid, tname, g in rows:
            m = next((x for x in st.manual if (x.animal, x.tissue) == (aid, tname)), None)
            if m is None:
                m = Manual(aid, tname)
                st.manual.append(m)
            m.mass_g, m.note = g, m.note or f"from {p.name}"
            m.typed.pop("mass_g", None)
            if (t := st.tissue(tname)) and "mass" not in t.hand:
                t.hand.append("mass")
                t.closed = [x for x in t.closed if x != "mass"]
        n_an = len({a for a, _, _ in rows}) or 1
        thin = len(rows) < 0.5 * n_an * sum(1 for t in st.tissues if t.role == "tissue")
        if (unsure or thin) and self.isVisible():
            QMessageBox.information(self, APP_NAME, (
                f"{p.name}: {len(rows)} mass(es) read, for {n_an} animal(s), as typed values."
                + ("\n\nNot understood:\n" + "\n".join(unsure[:12]) if unsure else "")
                + ("\n\nNot in the tissue list: " + ", ".join(unknown[:12]) if unknown else "")
                + "\n\nIf it was read wrong (Ctrl+Z undoes it), a sheet always reads like this: "
                  "a .xlsx or .csv, the tissues down the first column (header: tissue), one "
                  "column per animal headed by its ID, the masses in g."))
        return f"{p.name}: {len(rows)} masses for {n_an} animal(s) (typed rows)"

    def _offer_fixes(self, ask=None):
        """An animal's tubes put in order by hand in one file: its other files, same tubes,
        offered the same order — each ticked, to accept or not. `ask` stands in for the
        dialog (the smoke test)."""
        fixes = carry_fixes(self._eff, self.runs)
        if not fixes:
            return
        src = {s.uid: s for s in self.study.sources}
        lines = [f"{Path(src[u].path).name} ({KIND_LABEL.get(src[u].kind, src[u].kind)}): "
                 f"animal {a}, {len(m)} vial(s) — as in {name}" for u, a, name, m in fixes]
        if ask:
            keep = ask(lines)
        else:
            d = QDialog(self)
            d.setWindowTitle("Same tubes, same order?")
            v = QVBoxLayout(d)
            v.addWidget(QLabel("These animals' tubes were put in order by hand in one file.\n"
                               "Their other files hold the same tubes — place them the same "
                               "way?"))
            ticks = [QCheckBox(t) for t in lines]
            for t in ticks:
                t.setChecked(True)
                v.addWidget(t)
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb.accepted.connect(d.accept)
            bb.rejected.connect(d.reject)
            v.addWidget(bb)
            keep = [t.isChecked() for t in ticks] if d.exec() else [False] * len(ticks)
        for (u, a, name, m), ok in zip(fixes, keep):
            if ok:
                src[u].slotmap.update({k: list(x) for k, x in m.items()})
                src[u].auto = False
                self.log(f"{Path(src[u].path).name}: animal {a}'s vials placed as in {name}")
        if any(keep):
            self._sync()

    def _file_date(self) -> str:
        """The day the typed HH:MM belong to, read off the loaded runs: the day the filled
        tubes were weighed (right after collection), else the first counting day.

        Left to itself the date defaults to today, and a study opened the morning after the
        counting would decay every syringe time by a day: a silent ~20x error in %IA/g. The
        counts are no good when there is a weighing: they are often done the next day.
        """
        kinds = {s.path: s.kind for s in self.study.sources}
        for want in (("filled",), ("count", "weigh_count")):
            t = [r.normalized_to or r.started for p, r in self.runs.items()
                 if kinds.get(p) in want]
            if t := [x for x in t if x]:
                return min(t).date().isoformat()
        return ""

    def _set_tissues(self, names, source="") -> str:
        """Merge a list in. Two lists get dropped in real studies: the bulk, and the tissues
        weighed and counted on the spot (to freeze them quickly). A second list extends the
        first as a run of its own, named after the file's last word: ..._direct -> "direct".
        Returns that run's name, "" for the main one."""
        have = {t.name for t in self.study.tissues}
        new = unique_names([n for n in names if n not in have], have)
        batch = (re.split(r"[\s_\-]+", source.strip())[-1] or "2") if have and new else ""
        self.study.tissues += [Tissue(n, guess_role(n), batch=batch) for n in new]
        self._sync()
        return batch

    # ------------------------------------------------------------------ editing
    # what an animal added with + does not take from the one before: its own readings
    OWN = {"group", "exclusion reason", "comment", "euthanasia time"}

    def add_animal(self):
        """The next ID in the series (S1 -> S2); the tracer, the animal's details (species,
        strain, sex, DOB, supplier…) and which fields the card shows, from the last card —
        not its weight, syringes, times, aliases, note or procedures."""
        prev = self.study.animals[-1] if self.study.animals else Animal()
        self.study.animals.append(Animal(
            id=next_id(prev.id, {a.id for a in self.study.animals}),
            isotope=prev.isotope, molecule=prev.molecule,
            extra={k: v for k, v in prev.extra.items() if k.lower() not in self.OWN},
            show=dict(prev.show)))
        self.log(f"animal {self.study.animals[-1].id} added")
        self._sync()

    def _remove_animal(self, a: Animal):
        self.study.animals.remove(a)
        for s in self.study.sources:
            if a.id in s.animals:
                s.animals.remove(a.id)
        self.log(f"animal {a.label} removed")
        self._sync()

    def add_tissue(self):
        self.study.tissues.append(Tissue(f"tissue {len(self.study.tissues) + 1}"))
        self._sync()

    def del_tissues(self, rows):
        """Del clears the selected typed values; on a tissue it removes the tissue, on a
        typed row it closes that row."""
        idx = [(i.row(), i.column()) for i in self.t_tissues.selectedIndexes()]
        vals = [(r, c) for r, c in idx if c >= TC and self._trows[r][1]]
        if vals:
            for r, c in vals:
                self._set_manual(r, c, "")
        else:
            gone = []
            for r in sorted({r for r, _ in idx}):
                i, f = self._trows[r]
                tis = self.study.tissues[i]
                if not f:
                    gone.append(tis)
                elif f != "time":
                    self._hand(tis, self.HAND[f], False, sync=False)
            self.study.tissues = [t for t in self.study.tissues if t not in gone]
            if gone:
                self.log("removed: " + ", ".join(t.name for t in gone))
        self._sync()

    HAND = {"mass_g": "mass", "mbq": "activity", "note": "note"}

    def _hand(self, tis: Tissue, what: str, on: bool, sync=True):
        """Open or close the typed mass / activity / note rows of one tissue. Closing keeps
        what the row holds, unused (the files' values come back); opening it shows it again."""
        if on:
            tis.hand += [what] if what not in tis.hand else []
            tis.closed = [x for x in tis.closed if x != what]
        elif what in tis.hand:
            tis.hand.remove(what)
            if self._typed_count(tis, what):
                tis.closed += [what] if what not in tis.closed else []
        if sync:
            self._sync()

    def _drop_typed(self, tis: Tissue, what: str):
        """× on a typed row: the row goes, and what was typed in it, for every animal."""
        fields = {"mass": ("mass_g",), "activity": ("mbq", "time"), "note": ("note",)}[what]
        for m in [m for m in self.study.manual if m.tissue == tis.name]:
            for f in fields:
                setattr(m, f, "" if f in ("time", "note") else None)
                m.typed.pop(f, None)
            m.typed.pop({"mass_g": "mass_mg", "mbq": "kbq"}.get(fields[0], ""), None)
            if m.mass_g is None and m.mbq is None and not m.time and not m.note:
                self.study.manual.remove(m)
        tis.hand = [x for x in tis.hand if x != what]
        tis.closed = [x for x in tis.closed if x != what]
        self.log(f"{tis.name}: the {what} typed by hand removed", "✎", "edits")
        self._sync()

    def _typed_count(self, tis: Tissue, what: str) -> int:
        f = {"mass": "mass_g", "activity": "mbq", "note": "note"}[what]
        return sum(1 for m in self.study.manual if m.tissue == tis.name
                   and getattr(m, f) not in (None, ""))

    def _set_manual(self, row, col, text):
        """One typed value into the model; an entry left with nothing in it goes."""
        i, f = self._trows[row]
        tname, aid = self.study.tissues[i].name, self.study.animals[col - TC].id
        m = next((m for m in self.study.manual if (m.animal, m.tissue) == (aid, tname)), None)
        if m is None:
            m = Manual(aid, tname)
            self.study.manual.append(m)
        if f == "time":
            m.time = _typed(m.time, text, self.study.day)
        elif f == "note":
            m.note = text.strip()
        else:                                    # stored in g and MBq, typed as Options says
            k = 1000 if PREFS[_TYPED_UNIT[f][0]] == _TYPED_UNIT[f][1] else 1
            v = _f(text)
            setattr(m, f, None if v is None else v / k)
            m.typed.pop(f, None)
            m.typed.pop(_TYPED_UNIT[f][2], None)
            if v is not None:
                m.typed[f if k == 1 else _TYPED_UNIT[f][2]] = text.strip()
        v = _shown(m.time, self.study.day) if f == "time" else m.note if f == "note" else \
            _typed_num(m, f)
        if m.mass_g is None and m.mbq is None and not m.time and not m.note:
            self.study.manual.remove(m)
        return v

    def _tissue_edited(self, item):
        if self._loading:
            return
        i, f = self._trows[item.row()]
        tis, txt = self.study.tissues[i], item.text().strip()
        if f:
            v = self._set_manual(item.row(), item.column(), txt)
            self._loading = True
            item.setText(v)
            self._loading = False
            self.recompute()
            self.t_tissues.fit(PREFS["table_rows"])
        elif item.column() == 0 and txt != tis.name:
            if txt and not self.study.tissue(txt):
                self.study.rename_tissue(tis.name, txt)
            else:
                self.statusBar().showMessage(f"{txt!r} is already on the list" if txt else
                                             "A tissue needs a name — Del removes it", 5000)
            self._later(self._sync)()
        elif item.column() == 3:
            self._move_tissue(i, txt)

    def _tissue_fold(self, r, c):
        """A click on a tissue's ▸ / ▾ (left of its name) folds or unfolds its typed rows."""
        if c or r >= len(self._trows) or self._trows[r][1]:
            return
        tis = self.study.tissues[self._trows[r][0]]
        x = self.t_tissues.viewport().mapFromGlobal(QCursor.pos()).x()
        if tis.hand and x - self.t_tissues.visualItemRect(self.t_tissues.item(r, 0)).left() < 22:
            self._tissue_open[tis.name] = not self._tissue_open.get(tis.name, True)
            self._loading, was = True, self._loading     # redrawn cells are no edits (else
            try:                                         # 17 rebuilds: 9 s, 260930-2)
                self._sync_tissues()
            finally:
                self._loading = was
            self._tissue_values()

    def _tissue_clicked(self, r, button):
        """+ on a tissue's row: a row to type, for every animal — a mass, an activity, a note."""
        if r >= len(self._trows) or self._trows[r][1]:
            return
        tis = self.study.tissues[self._trows[r][0]]
        m = QMenu(self)
        m.setToolTipsVisible(True)
        for what, f, text, tip in (
                ("mass", "mass_g", f"Mass ({PREFS['typed_mass']})",
                 "Weighed on paraffin, … — wins over the tube weights"),
                ("activity", "mbq", "Activity", "Read on the dose calibrator, and when — wins "
                                                "over the counter"),
                ("note", "note", "Note", "Goes in the report")):
            act = m.addAction(text, lambda what=what, f=f: self._open_typed(tis, what, f, TC))
            act.setToolTip(tip + (f" — {n} kept from before" if what in tis.closed and (
                n := self._typed_count(tis, what)) else ""))
            act.setEnabled(what not in tis.hand)
        m.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _open_typed(self, tis, what, f, col):
        self._tissue_open[tis.name] = True       # a row opened is a row shown
        self._hand(tis, what, True)
        i = self.study.tissues.index(tis)
        if (i, f) in self._trows:
            r = self._trows.index((i, f))
            self.t_tissues.setCurrentCell(r, col)
            self.t_tissues.editItem(self.t_tissues.item(r, col))

    def _pick_batch(self, i, c):
        if c.currentIndex() < c.count() - 1:
            return self._set_batch(i, c.currentText())
        name, ok = QInputDialog.getText(
            self, "New batch", "Tissues collected, weighed and counted on their own (straight "
            "after euthanasia…) — their own tubes and countings.\n\nName of the batch:")
        if ok and name.strip():
            self._set_batch(i, name)
        else:
            self._later(self._sync)()

    def _with_selected(self, i) -> list[int]:
        """The tissue `i`, or every selected tissue if it is one of them."""
        sel = sorted({self._trows[x.row()][0] for x in self.t_tissues.selectedIndexes()
                      if not self._trows[x.row()][1]})
        return sel if i in sel else [i]

    def _set_batch(self, i, text):
        b = "" if text.strip().lower() in ("", "main") else text.strip()
        for k in self._with_selected(i):
            self.study.tissues[k].batch = b
        self._later(self._sync)()

    def _move_tissue(self, i, text):
        """A new # typed: the tissue moves within its batch, the other tissues keep their rows."""
        ts, tis, n = self.study.tissues, self.study.tissues[i], _f(text)
        slots = [k for k, t in enumerate(ts) if t.batch == tis.batch]
        mine = [ts[k] for k in slots if ts[k] is not tis]
        if n is not None:
            mine.insert(max(0, min(int(n) - 1, len(mine))), tis)
            for k, t in zip(slots, mine):
                ts[k] = t
        self._later(self._sync)()

    def del_sources(self, rows):
        for r in sorted({self._srows[r] for r in rows if r < len(self._srows)} - {None},
                        reverse=True):
            if 0 <= r < len(self.study.sources):
                self.log(f"{Path(self.study.sources[r].path).name} removed")
                del self.study.sources[r]
        self._sync()

    # -------------------------------------------------------------------- sync
    def _sync(self):
        """Rebuild every widget from the model. Cheap enough to do on any change."""
        self._loading = True
        try:
            self._sync_animals()
            self._sync_tissues()
            self._sync_sources()
            self.e_name.setText(self.study.name)
            self.e_date.setDate(QDate.fromString(self.study.day.isoformat(), Qt.ISODate))
            for hint, there, widgets in (
                    (self.h_tissues, bool(self.study.tissues), (self.t_tissues,)),
                    (self.h_sources, bool(self.study.sources), (
                        self.t_sources, self.w_src_opts))):
                hint.setVisible(not there)           # empty: a + and a line, no table
                for x in widgets:
                    x.setVisible(there)
        finally:
            self._loading = False
        self.recompute()
        self.animal_win.refresh()
        if self.names_win.isVisible():
            self.output_win.fill()
            self.animal_order.fill()

    def _sync_animals(self):
        while self.cards_row.count():
            w = self.cards_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        cards, self.cards = [], []
        for a in self.study.animals:
            card = AnimalCard(a, self.study.day)
            self.cards.append(card)
            card.changed.connect(self.recompute)
            card.rebuild.connect(self._later(self._sync))
            card.removed.connect(self._remove_animal)
            card.shown.connect(self._show_field)
            card.expand.connect(lambda a: self.animal_win.show_animal(
                self.study.animals.index(a)))
            card.hop.connect(self._hop)
            w, h = card, card.sizeHint().height()
            lim = 14 + PREFS["card_rows"] * (card.e_id.sizeHint().height() + 3)
            if PREFS["card_rows"] and h > lim:
                w, h = QScrollArea(), lim
                w.setWidget(card)
                w.setWidgetResizable(True)
                w.setFrameShape(QFrame.NoFrame)
                w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                w.setFixedSize(card.width() + w.verticalScrollBar().sizeHint().width(), h)
            self.cards_row.addWidget(w, 0, Qt.AlignTop)
            cards.append(w)
        add = QToolButton()
        add.setIcon(_plus(16))
        add.setIconSize(QSize(16, 16))
        add.setToolTip("Add an animal — next ID, same isotope and molecule (Ctrl+Shift+N)")
        add.setFixedSize(34, 34)
        add.setStyleSheet("QToolButton{border:1px dashed #555;border-radius:5px;} "
                          "QToolButton:hover{background:#3d3d3d;}")
        add.clicked.connect(self.add_animal)
        self.cards_row.addWidget(add, 0, Qt.AlignTop)
        self._fit_cards(cards)
        QTimer.singleShot(0, lambda: self._fit_cards(cards))   # once styled: fonts, DPI
        self.sec_animals.set_note(f"{len(self.study.animals)}")
        if self._want:                           # the field Tab went to, rebuilt meanwhile
            self._focus_card(*self._want)

    def _fit_cards(self, cards):
        """The Animals section as tall as its tallest card — measured once the cards are
        styled (before, at 125 % display scale, it came out a few px short: 16.png)."""
        hs = [w.maximumHeight() if isinstance(w, QScrollArea) else w.sizeHint().height()
              for w in cards if isValid(w)]
        if hs or not cards:
            self.cards_scroll.setFixedHeight(
                max(hs, default=40) + self.cards_scroll.horizontalScrollBar().sizeHint().height()
                + 2)

    def _hop(self, a, row, step):
        """Tab past the end of a card's row: the same row on the next card (Shift+Tab: the
        previous card, its row's last field)."""
        i = next((k for k, c in enumerate(self.cards) if c.a is a), None)
        if i is None or not 0 <= i + step < len(self.cards):
            return
        self._want = (self.cards[i + step].a.id, row, 0 if step > 0 else -1)
        self.cards[i].setFocus()                 # the field left is taken in first
        self._focus_card(*self._want)
        QTimer.singleShot(0, lambda: setattr(self, "_want", None))

    def _focus_card(self, aid, row, col):
        card = next((c for c in self.cards if c.a.id == aid), None)
        if card and card.focus(row, col):
            self.cards_scroll.ensureWidgetVisible(card)

    def _sync_tissues(self):
        """Tissues down; a tissue with typed values gets rows under it, one cell per animal."""
        st, t = self.study, self.t_tissues
        for m in st.manual:              # studies from before the grid: show what they hold
            tis = st.tissue(m.tissue)
            for what, v in (("mass", m.mass_g), ("activity", m.mbq), ("note", m.note or None)):
                if tis and v is not None and what not in tis.hand + tis.closed:
                    tis.hand.append(what)
        rows = []
        for i, tis in enumerate(st.tissues):
            rows.append((i, ""))
            if not self._tissue_open.get(tis.name, True):
                continue
            rows += [(i, "mass_g")] if "mass" in tis.hand else []
            rows += [(i, "mbq"), (i, "time")] if "activity" in tis.hand else []
            rows += [(i, "note")] if "note" in tis.hand else []
        self._trows = rows
        t.setRowCount(0)
        t.clearSpans()
        t.setColumnCount(TC + len(st.animals))
        t.setHorizontalHeaderLabels(["tissue", "role", "batch", "#", ""]
                                    + [a.label for a in st.animals])
        t.setRowCount(len(rows))
        man = {(m.animal, m.tissue): m for m in st.manual}
        sub = {"mass_g": f"mass ({PREFS['typed_mass']})",
               "mbq": f"activity ({PREFS['typed_activity']})", "time": "read at", "note": "note"}
        what_of = {"mass_g": "mass", "mbq": "activity", "time": "activity", "note": "note"}
        for r, (i, f) in enumerate(rows):
            tis = st.tissues[i]
            if not f:
                t.setItem(r, 0, QTableWidgetItem(tis.name))
                c = _combo(TISSUE_ROLES, tis.role)
                c.setToolTip("\n".join(f"{k}: {v}" for k, v in ROLE_HELP.items())
                             + "\nSeveral tissues selected: set on all of them")
                c.currentTextChanged.connect(
                    lambda v, i=i: ([setattr(self.study.tissues[k], "role", v)
                                     for k in self._with_selected(i)],
                                    self._later(self._sync)()))
                t.setCellWidget(r, 1, c)
                c = _combo(["main"] + [b for b in st.batch_names() if b] + ["new batch…"],
                           tis.batch or "main")
                c.setToolTip("The tubes this tissue is in: the main batch, or a batch of its "
                             "own (collected, weighed and counted on the spot, with its own "
                             "empty tubes) — new batch… starts one. Each batch's files go to "
                             "its own tissues. A recount of the same tubes is the same batch: "
                             "just drop its file (it makes a new counting round).\n"
                             "Several tissues selected: set on all of them")
                c.activated.connect(lambda _=0, i=i, c=c: self._pick_batch(i, c))
                t.setCellWidget(r, 2, c)
                pos = QTableWidgetItem(str(st.batch_tissues(tis.batch).index(tis.name) + 1))
                pos.setToolTip("Its place in its batch's vial order — type another to move it")
                t.setItem(r, 3, pos)
                b = QToolButton()
                b.setIcon(_plus(12))
                b.setIconSize(QSize(12, 12))
                b.setStyleSheet("QToolButton{border:none;background:transparent;} "
                                "QToolButton:hover{background:#3d3d3d;border-radius:3px;}")
                b.setToolTip("Type values for this tissue, for every animal: a mass (paraffin…),"
                             " an activity read on the dose calibrator, a note")
                b.clicked.connect(lambda _=0, r=r, b=b: self._tissue_clicked(r, b))
                t.setCellWidget(r, 4, _centred(b))
                if tis.hand:                             # ▸ / ▾: its typed rows folded or not
                    t.item(r, 0).setIcon(_glyph("▾" if self._tissue_open.get(tis.name, True)
                                                else "▸"))
                    t.item(r, 0).setToolTip("Click ▸ / ▾ to show or hide the values typed by "
                                            "hand for it; double-click to rename")
                for col in range(TC, t.columnCount()):
                    t.setItem(r, col, _ro("", _BLANK if tis.role == "blank" else "#a8a8a8"))
                continue
            lab = _ro(f"{tis.name} · {sub[f]}  ", "#9fb8c8")
            lab.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lab.setToolTip(("HH:MM on the study date; another day with its date, in any "
                            "order: 24/9 8:47, 8:47 9/24, 2026-09-24 08:47\n" if f == "time"
                            else "") + "Del on this label closes the row: what it holds is "
                                       "kept, unused, until the row is opened again")
            t.setItem(r, 0, lab)
            t.setSpan(r, 0, 1, TC)
            if f != "time":                          # × after the label: the row and its values
                lab.setForeground(QColor(0, 0, 0, 0))    # the widget shows the text
                box = QWidget()
                h = QHBoxLayout(box)
                h.setContentsMargins(0, 0, 4, 0)
                h.setSpacing(2)
                h.addStretch(1)
                txt = QLabel(f"{tis.name} · {sub[f]}")
                txt.setStyleSheet("color:#9fb8c8;")
                h.addWidget(txt)
                x = QToolButton()
                x.setText("×")
                x.setToolTip("Remove this row and what is typed in it — for every animal "
                             "(Ctrl+Z brings it back)")
                x.setStyleSheet("QToolButton{border:none;color:#c06060;font-weight:bold;}")
                x.clicked.connect(lambda _=0, tis=tis, w=what_of[f]: self._drop_typed(tis, w))
                h.addWidget(x)
                t.setCellWidget(r, 0, box)
            else:
                lab.setText(f"{tis.name} · {sub[f]}        ")
            for col, a in enumerate(st.animals, start=TC):
                m = man.get((a.id, tis.name))
                v = getattr(m, f, None)
                t.setItem(r, col, QTableWidgetItem(
                    _shown(v, st.day) if f == "time" else (v or "") if f == "note"
                    else _typed_num(m, f)))
                if f != "note":                          # right, under the value they stand
                    t.item(r, col).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)   # for
                    if PREFS["cell_mass"] and PREFS["cell_value"]:
                        t.item(r, col).setData(_SHARE, (0 if f == "mass_g" else 1, 2))
            for col in [0] + list(range(TC, TC + len(st.animals))):
                t.item(r, col).setBackground(QColor("#2a3238"))
        t.fit(PREFS["table_rows"])
        self._sync_batches()
        n = sum(1 for x in st.tissues if x.role == "tissue")
        self.sec_tissues.set_note(f"{n} tissue(s)" + (f" + {len(st.tissues) - n} other"
                                                      if len(st.tissues) > n else ""))

    def _tissue_values(self):
        """On each tissue's row, under each animal, what is in use — as Options › Tissue table
        says: mass (mg) and activity (MBq / kBq, at the reference time) by default; a blank
        tube's in dark orange. Over the table, a line saying at what time and from what."""
        t, st, res = self.t_tissues, self._eff, self.res
        self._loading, was = True, self._loading
        cm, cv = PREFS["cell_mass"], PREFS["cell_value"]
        for r, (i, f) in enumerate(self._trows):
            if f or i >= len(st.tissues):
                continue
            tn = st.tissues[i].name
            for col, a in enumerate(st.animals, start=TC):
                c = res.cell(a.id, tn)
                m = "" if c.mass_g is None or not cm else \
                    f"{c.mass_g * 1000:.1f} mg" if cm == "mg" else f"{c.mass_g:.4f} g"
                if cv == "bq":
                    v = res.at_ref(a.id, c.bq)
                    cpm = next((x[1] for x in c.raw.values() if x[1] is not None), None)
                    act = _act(v) if v is not None else "" if cpm is None else \
                        f"{cpm:,.0f} CPM"            # no efficiency yet: as the counter read
                elif cv == "counts":
                    n = c.raw.get(c.bq_src, (None,))[0]
                    act = "" if n is None else f"{n:,.0f} cts"
                elif cv:
                    v = res.value(st, a.id, tn, cv)
                    act = "" if v is None else f"{v:.{PREFS['digits'][cv]}f} " + \
                        dict(UNITS)[cv]
                else:
                    act = ""
                if it := t.item(r, col):
                    it.setText("\t".join(x for x in (m, act) if x) if m and act else m or act)
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    it.setToolTip(f"{a.label} / {tn}\nmass: "
                                  f"{res.source_label(a.id, tn, 'mass') or 'none'}\nactivity: "
                                  f"{res.source_label(a.id, tn, 'activity') or 'none'}"
                                  + (f"\n⚠ {'; '.join(c.flags)}" if c.flags else ""))
        self._loading = was
        self.t_tissues.fit(PREFS["table_rows"])
        say = []
        if "ref" in PREFS["tissue_note"] and cv == "bq" and res.rounds:   # a counting yet
            say.append("Activities at each animal's injection time (decay-corrected)"
                       if res.refs else f"Activities at {res.ref:%d %b %Y %H:%M}" + (
                           "" if st.ref_time else ", the first counting's reference")
                       + " (decay-corrected)")
        if "sources" in PREFS["tissue_note"] and res.cells:
            pick = "one counting round" if st.pick_count.startswith("round:") else \
                COUNT_RULES.get(st.pick_count, "").replace("auto — ", "")
            say.append(f"activity: {pick} (target range {_study.range_text(st, False)}), window "
                       f"{st.window or 'auto'}; mass: "
                       f"filled − empty tube, {MASS_RULES[st.mass_rule]}"
                       + ("; values typed by hand win" if st.manual else "")
                       + ". Options › Results changes these; the Results' side panel, one "
                         "cell's.")
        self.l_tissue_note.setText("\n".join(say))
        self.l_tissue_note.setVisible(bool(say) and bool(st.tissues))

    def _sync_batches(self):
        """With tissues in more than one batch: each batch's vial order, for the guess."""
        st, bar = self.study, self.batch_bar.layout()
        while bar.count():
            if w := bar.takeAt(0).widget():
                w.deleteLater()
        runs = [b for b in st.batch_names() if st.batch_tissues(b)]
        self.batch_bar.setVisible(len(runs) > 1)
        if len(runs) < 2:
            return
        for b in runs:
            bar.addWidget(QLabel(f"{b or 'main'} batch, vials"))
            c = _combo([PRESET_LABEL[ANIMAL_MAJOR], PRESET_LABEL[TISSUE_MAJOR]],
                       PRESET_LABEL[st.batch_order(b)])
            c.setToolTip("How the vials of this batch were racked — the guess deals them so")
            c.currentIndexChanged.connect(lambda v, b=b: (
                self.study.batches.__setitem__(b, [ANIMAL_MAJOR, TISSUE_MAJOR][v]),
                self.recompute()))
            bar.addWidget(c)
            bar.addSpacing(16)
        bar.addStretch(1)

    def _src_set(self, row, attr, value):
        src = self.study.sources[row]
        setattr(src, attr, value)
        src.auto = False
        self.recompute()

    def _src_choices(self, ix) -> list[str]:
        """What a file's animals / tissues cell offers: everyone, or a whole tissue run."""
        st = self.study
        if ix.column() == 4:
            return ["all"] + [a.id for a in st.animals if a.id]
        i = self._srows[ix.row()] if ix.row() < len(self._srows) else None
        b = st.sources[i].batch if i is not None else ""
        runs = [x for x in st.batch_names() if st.batch_tissues(x)]
        return ([f"{x or 'main'}: all" for x in runs] if len(runs) > 1 else ["all"]) + \
            st.batch_tissues(b)

    def _src_names(self, ix, text):
        """Animals or tissues typed for a whole file: its vials dealt to them in its order,
        the vials placed one by one let go."""
        i = self._srows[ix.row()] if ix.row() < len(self._srows) else None
        if i is None or not text:
            return
        st, src = self.study, self.study.sources[i]
        if ix.column() == 5 and ":" in text:        # "early: all" — a tissue run
            b, text = (x.strip() for x in text.split(":", 1))
            b = "" if b.lower() == "main" else b
            if b not in st.batch_names():
                return self.statusBar().showMessage(f"{b}: no such tissue run", 8000)
            src.batch = b
        every = ([a.id for a in st.animals if a.id] if ix.column() == 4
                 else st.batch_tissues(src.batch))
        typed = [x.strip() for x in text.split(",") if x.strip()]
        def one(x):                                 # the name, or the one it is part of
            m = [k for k in every if x.lower() in k.lower()]
            return next((k for k in every if k.lower() == x.lower()),
                        m[0] if len(m) == 1 else x)
        got = [one(x) for x in typed]
        if bad := [x for x in got if x not in every and x.lower() != "all"]:
            return self.statusBar().showMessage(
                f"{', '.join(bad)}: not on the animal cards or in the tissue list", 8000)
        got = [] if any(x.lower() == "all" for x in got) else got     # [] = all of them
        setattr(src, "animals" if ix.column() == 4 else "tissues", got)
        src.slotmap, src.auto = {}, False
        self.log(f"{Path(src.path).name}: {'animals' if ix.column() == 4 else 'tissues'} "
                 f"set to {text}")
        QTimer.singleShot(0, lambda: (self.recompute(), self._resync_sources()))

    def _sync_sources(self):
        st, t = self.study, self.t_sources
        t.setRowCount(0)
        t.setRowCount(len(st.sources))
        for r, s in enumerate(st.sources):
            run = self.runs.get(s.path)
            name = QTableWidgetItem(Path(s.path).name)
            name.setToolTip(f"{s.path}\n{run.run_type if run else 'not read'}"
                            + (f"\nstarted {run.started:%d %b %H:%M}" if run and run.started
                               else "")
                            + (f"\nbatch: {s.batch or 'main'}" if len(st.batch_names()) > 1
                               else "")
                            + ("\nguessed — edit the row to set it by hand" if s.auto else
                               "\nset by hand — Guess again to let BioDist place it"))
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)
            if not s.auto:
                name.setForeground(QColor(_ACCENT))
            t.setItem(r, 0, name)
            times = sorted(x.time for x in run.slots if x.time) if run else []
            times = times or ([run.started] if run and run.started else [])   # a weighing
            when = _ro("⤢" if not times else f"{times[0]:%d %b %H:%M}  ⤢" if len(times) == 1
                       else f"{times[0]:%d %b %H:%M}–{times[-1]:%H:%M}  ⤢")
            when.setToolTip("first and last vial measured — click for everything the file "
                            "holds, vial by vial; round n: the counting round (one pass of the "
                            "counter over the vials, Options › Data sources)")
            when.setData(Qt.UserRole, when.text())   # the times, the round put before them
            t.setItem(r, 1, when)
            if s.kind == "ignored":                  # kept in sight, left out of the numbers
                for it in (name, when):
                    it.setForeground(QColor(_IGNORED))
            c_k = _combo([KIND_LABEL[k] for k in KINDS], KIND_LABEL.get(s.kind, ""))
            c_k.setToolTip("tare: the empty tubes weighed\n"
                           "weight: the same tubes weighed with the tissue in — the mass is "
                           "the difference, cell by cell\n"
                           "count: a counting run\n"
                           "count + weight: a counting run that weighed the tubes too\n"
                           "(ignored): kept in the list, left out of every number")
            c_k.currentIndexChanged.connect(lambda v, i=r: self._src_set(i, "kind", KINDS[v]))
            t.setCellWidget(r, 2, c_k)
            racks = len({x.rack for x in run.slots}) if run else 0
            vials = _ro(f"{len(run.slots)} ({racks}){' *' if s.slotmap else ''}" if run
                        else "?")
            vials.setToolTip(f"{len(run.slots)} vials in {racks} rack(s)" if run else
                             "the file could not be read")
            if s.slotmap:
                vials.setToolTip(vials.toolTip() + "\n* some vials placed one by one")
            t.setItem(r, 3, vials)
            for c in (4, 5):                         # what the file's vials hold: _sync_strips
                it = QTableWidgetItem("")
                it.setToolTip("Type or pick to give the whole file to them: 107, 108 or all; "
                              "the tissues of a run: early: all")
                t.setItem(r, c, it)

            c_p = _combo([PRESET_LABEL[ANIMAL_MAJOR], PRESET_LABEL[TISSUE_MAJOR]],
                         PRESET_LABEL[s.preset])
            c_p.setToolTip("animal by animal: 107 Adrenal, 107 BAT … then 108 Adrenal …\n"
                           "tissue by tissue: tumor 107, 108, 109, then muscle 107, 108, "
                           "109 …\nAny other order: click the file (▸) and pick the first "
                           "vials by hand — Tab fills the rest the same way")
            c_p.currentIndexChanged.connect(
                lambda v, i=r: self._src_set(i, "preset", [ANIMAL_MAJOR, TISSUE_MAJOR][v]))
            t.setCellWidget(r, 6, c_p)
            t.setItem(r, 7, _ro(""))
        self._srows = list(range(len(st.sources)))
        self._strip_shape = None                     # the strips go back in at the next redraw
        self._sync_rounds(fit=False)
        t.fit(PREFS["table_rows"])
        self.sec_sources.set_note(f"{len(st.sources)} file(s)")
        self._sync_eff()

    def _sync_rounds(self, fit=True):
        """Each count file's counting round before its times, a tint per round so they read
        as blocks — Options › Data sources says whether."""
        t, res = self.t_sources, getattr(self, "res", None)
        changed = False
        for r, i in enumerate(self._srows):
            it = t.item(r, 1) if i is not None and i < len(self.study.sources) else None
            if it is None or it.data(Qt.UserRole) is None:
                continue
            k = res.round_of(Path(self.study.sources[i].path).name) \
                if res and PREFS["source_rounds"] else None
            text = it.data(Qt.UserRole) if k is None else f"round {k + 1} · {it.data(Qt.UserRole)}"
            if it.text() != text:
                it.setText(text)
                changed = True
            it.setData(Qt.BackgroundRole, None if k is None else
                       QColor("#2c3a33" if k % 2 == 0 else "#2c3340"))
        if fit and changed and len(t._base) > 1 and t._head(1) not in t._user:
            t._base[1] = max(t._base[1], t.sizeHintForColumn(1) + 12)
            t.setColumnWidth(1, t._base[1])
            t._width()

    def _eff_need(self) -> list[tuple]:
        """The counter·window rows the efficiency table shows: every one when the files'
        own are off, else those with none (a Wizard2 file, a Hidex one set to 1)."""
        st = self.study
        return [r for r in st.eff_rows(self.runs)
                if not st.file_eff or not (r[3] and abs(r[3] - 1) > 1e-9)]

    def _sync_eff(self):
        """The efficiency box: the tick, and under it the counter·window rows to type."""
        st, t = self.study, self.t_eff
        rows = st.eff_rows(self.runs)
        self.c_eff.blockSignals(True)
        self.c_eff.setChecked(st.file_eff)
        self.c_eff.blockSignals(False)
        self.c_eff.setVisible(bool(rows))
        need = self._eff_need()
        t.setVisible(bool(need))
        t.blockSignals(True)
        t.setRowCount(len(need))
        self._eff_keys = [k for k, *_ in need]
        for r, (k, counter, w, fe) in enumerate(need):
            iso, ew, eff = (st.efficiency.get(k) or ["", "", ""])[:3]
            iso = iso or w.split("_")[0].translate(_study._SUP)
            ew = ew or (w.split("_", 1)[1] + " keV" if "_" in w else "")
            e = _study._float(eff)
            for c, (text, edit) in enumerate((
                    (counter, False), (iso, True), (ew, True), ("" if e is None else f"{e:g}", True),
                    ("" if not e else f"{1 / 60 / e:.4g}", False),
                    ("none" if fe is None else f"{fe:g}" + (" — none set" if abs(fe - 1) < 1e-9
                                                             else ""), False))):
                it = QTableWidgetItem(text)
                if not edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    it.setForeground(QColor("#8d8d8d"))
                if c == 3 and e is None:
                    it.setBackground(_WARN)
                    it.setToolTip("Needed: until it is typed, activities in CPM only")
                t.setItem(r, c, it)
        t.blockSignals(False)
        t.fit()

    def _eff_edited(self, it):
        """An efficiency (isotope, energy window) typed: 0.78, 78 % — counts per decay."""
        r = it.row()
        if r >= len(getattr(self, "_eff_keys", [])):
            return
        cells = [(self.t_eff.item(r, c).text().strip() if self.t_eff.item(r, c) else "")
                 for c in (1, 2, 3)]
        e = _study._float(cells[2].rstrip("% "))
        if e is not None and ("%" in cells[2] or e > 1):
            e /= 100
        if cells[2] and not (e and 0 < e <= 1):
            self.statusBar().showMessage(f"{cells[2]!r}: an efficiency is counts per decay, "
                                         "0-1 (or a %)", 8000)
            QTimer.singleShot(0, self._sync_eff)
            return
        self.study.efficiency[self._eff_keys[r]] = [cells[0], cells[1], e]
        QTimer.singleShot(0, self.recompute)

    def _ask_eff(self) -> None:
        """Results asked for with counting files that hold no efficiency: one box to type
        them in (Later: the CPM stay, the Bq values wait)."""
        need = [r for r in self._eff_need() if r[0] in self.res.no_eff]
        if not need:
            return
        d = QDialog(self)
        d.setWindowTitle(f"{APP_NAME} — counting efficiency")
        f = QFormLayout(d)
        why = QLabel("These counting files hold no efficiency (counts per decay), so their "
                     "CPM cannot be made Bq — and no %IA. It depends on the counter, the "
                     "isotope and the energy window: Bq = CPM / 60 / efficiency.")
        why.setWordWrap(True)
        f.addRow(why)
        eds = []
        for k, counter, w, fe in need:
            e = _edit("", "0.78", 90)
            eds.append((k, w, e))
            f.addRow(f"{counter} · {w}" + (" (1 in the files)" if fe else ""), e)
        bb = QDialogButtonBox()
        bb.addButton("Use them", QDialogButtonBox.AcceptRole)
        bb.addButton("Later (CPM only)", QDialogButtonBox.RejectRole)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.Accepted:
            return
        for k, w, e in eds:
            v = _study._float(e.text().rstrip("% "))
            if v and (v > 1 or "%" in e.text()):
                v /= 100
            if v and 0 < v <= 1:
                iso = w.split("_")[0].translate(_study._SUP)
                ew = w.split("_", 1)[1] + " keV" if "_" in w else ""
                self.study.efficiency[k] = [iso, ew, v]
                self.log(f"efficiency {k.replace('|', ' · ')}: {v:g}", "✎", "edits")
        self.recompute()

    def _resync_sources(self):
        self._loading = True
        try:
            self._sync_sources()
            self._sync_strips()
        finally:
            self._loading = False

    def _source_clicked(self, r, c):
        """A click on a file's name folds or unfolds its vials under it; on its run time,
        opens what the file holds."""
        i = self._srows[r] if r < len(self._srows) else None
        if c == 1 and i is not None:
            _run_details(self, self.study.sources[i], self.runs.get(self.study.sources[i].path))
        if c == 0 and i is not None and i < len(self._strip_rows):
            uid, *_, is_open = self._strip_rows[i]
            self._strip_open[uid] = not is_open
            self._sync_strips()

    # ----------------------------------------------------------------- computing
    def _read_runs(self):
        for s in self.study.sources:
            if s.path and s.path not in self.runs:
                try:
                    self.runs[s.path] = hidex.read(s.path)
                except Exception:  # noqa: BLE001 — reported in the check panel
                    if s.path in self.study.embedded:      # the copy the study kept
                        self.runs[s.path] = hidex.unpack(s.path, self.study.embedded[s.path])

    def _check_files(self):
        """A study opened: its files as they were when it was saved? A changed one, the
        choice between the file now and the copy the study kept; a gone one, the copy."""
        st, changed, gone = self.study, [], []
        for s in st.sources:
            p = Path(s.path)
            if not p.exists():
                gone.append(s)
                continue
            try:
                now = stamp(p)
            except OSError:
                continue
            if not s.stamp:
                s.stamp = now                    # a study from before: from now on
            elif now["sha256"] != s.stamp.get("sha256"):
                changed.append(s)
        kept = [s for s in changed if s.path in st.embedded]
        if changed and self.isVisible():
            box = QMessageBox(QMessageBox.Warning, APP_NAME, f"{len(changed)} file(s) changed "
                              "since the study was saved:\n\n" + "\n".join(
                                  f"{Path(s.path).name}  (was {s.stamp.get('modified', '?')}, "
                                  f"now {stamp(s.path)['modified']})" for s in changed[:15]),
                              parent=self)
            box.addButton("Use the files as they are now", QMessageBox.AcceptRole)
            b_old = box.addButton("Use the copies the study kept", QMessageBox.RejectRole) \
                if kept else None
            box.exec()
            if b_old and box.clickedButton() is b_old:
                for s in kept:
                    self.runs[s.path] = hidex.unpack(s.path, st.embedded[s.path])
            else:
                for s in changed:
                    s.stamp = stamp(s.path)
            self.log(f"{len(changed)} file(s) changed since saved: " + (
                "the study's copies used" if b_old and box.clickedButton() is b_old
                else "the files used as they are now"), "⚠")
        if gone:
            self.log(f"{len(gone)} file(s) not found: " + ", ".join(
                Path(s.path).name for s in gone[:6]) + (" — the copies the study kept are used"
                if all(s.path in st.embedded for s in gone) else ""), "⚠")
        if st.outside_edit and self.isVisible():
            QMessageBox.information(self, APP_NAME, "This study file was changed outside "
                                    "BioDist since it was saved (it no longer matches the "
                                    "fingerprint saved with it). It opens as it is; saving it "
                                    "again writes a new fingerprint.")
            self.log("the study file was edited outside BioDist since it was saved", "⚠")

    def _time_order(self):
        """The files in the order they were run, which is the order the bench worked in."""
        self._read_runs()
        self.study.sources.sort(key=lambda s: getattr(self.runs.get(s.path), "started", None)
                                or _dt.datetime.max)

    def _renames(self) -> bool:
        """An animal's ID or alias changed, wherever it was typed (card, animal window, its
        table): the ID follows into everything that names the animal (a taken or empty ID
        is refused), and every view is redrawn — True if one was."""
        st = self.study
        # the animals themselves are kept, not id(): a removed one's id() can come back
        was = {id(a): (i, lab) for a, i, lab in self._names[1]} if self._names[0] is st else {}
        self._names = (st, [(a, a.id, a.label) for a in st.animals])
        moved = False
        for a in st.animals:
            old = was.get(id(a))
            if not old or (a.id, a.label) == old:
                continue
            if a.id != old[0]:
                if not a.id or any(b is not a and b.id == a.id for b in st.animals):
                    self.statusBar().showMessage(f"{a.id!r}: " + ("another animal has that "
                                                 "ID" if a.id else "an ID is needed")
                                                 + f" — {old[0]} kept", 8000)
                    a.id = old[0]
                    self._names = (st, [(b, b.id, b.label) for b in st.animals])
                else:
                    st.animal_renamed(old[0], a.id)
                    self.log(f"animal {old[0]} is now {a.id}", "✎", "edits")
            moved = True
        return moved

    def recompute(self):
        if self._renames() and not self._loading:
            return self._later(self._sync)()    # the headers, lists and menus all name it
        self._read_runs()
        # the guess follows every edit (an animal added, a tissue renamed); the table only
        # has to be redrawn when it moved something
        def placed():
            return repr([(s.kind, s.animals, s.tissues, s.slotmap) for s in self.study.sources])
        before = placed()
        self.guess_why = {}
        self.auto_notes = auto_assign(self.study, self.runs, self.guess_why)
        if placed() != before and not self._loading:
            QTimer.singleShot(0, self._resync_sources)
        self._record()
        # a source left at "(all)" means the study's own lists, resolved here so the model
        # stays literal and a saved study keeps working when the tissue list later changes
        eff = Study.from_json(self.study.to_json())
        for s in eff.sources:
            if not s.animals and not s.auto:     # a guess's empty list: placed nowhere
                s.animals = [a.id for a in eff.animals if a.id]
            if not s.tissues:
                s.tissues = [t.name for t in eff.tissues]
        self.res = compute(eff, self.runs)
        self._eff = eff
        self._tissue_values()
        self._sync_strips()
        self._sync_rounds()
        self._sync_eff()
        self._tail_hints()
        self.results.show_result(eff, self.res)
        if self.report.isVisible():
            self.report.refresh()
        self._sync_check()
        self._offer()
        if self.options_win and self.options_win.isVisible():
            QTimer.singleShot(0, self.options_win.refresh_rules)

    def _sync_strips(self):
        """In the sources table, under each file, its vials in rack order, the animal over the
        tissue: folded when the file's order places them, open when vials are placed one by
        one or left out; a click on the file name folds it. Typing into it places vials."""
        if not hasattr(self, "_eff"):
            return
        eff, t, rows = self._eff, self.t_sources, []
        for i, x in enumerate(eff.sources):
            run = self.runs.get(x.path)
            if not run:
                rows.append((x.uid, Path(x.path).name, [], "", False))
                continue
            m, raw = x.mapping(run), self.study.sources[i].slotmap
            vials = [(sl.key, raw[sl.key] if sl.key in raw else m.get(sl.key))
                     for sl in run.slots]
            rows.append((x.uid, Path(x.path).name, vials,
                         strip_summary([m.get(sl.key) for sl in run.slots]),
                         self._strip_open.get(x.uid, bool(raw) or len(m) < len(run.slots)
                                              and bool(eff.tissues))))   # no list: nothing
        #                                                                  to place them on yet
        self._strip_rows = rows
        self._summaries = {r[0]: r[3] for r in rows if r[2]}
        extra = [x for x in STRIP_ROWS if x in PREFS["strip_rows"]]
        labels = ["animal", "tissue"] + [
            f"activity ({ACTIVITY_UNITS[PREFS['strip_activity']]})" if x == "activity"
            else STRIP_ROWS[x] for x in extra]
        shape = [(r[0], [k for k, _ in r[2]], r[4]) for r in rows] + [
            labels, PREFS["strip_layout"], PREFS["strip_racks"]]
        if shape != self._strip_shape:
            self._strip_shape, self._strip_sheets = shape, {}
            for r in reversed(range(len(self._srows))):
                if self._srows[r] is None:
                    t.removeRow(r)
            self._srows = [x for x in self._srows if x is not None]
            for i, (uid, name, vials, _, is_open) in enumerate(rows):
                if not (is_open and vials) or i not in self._srows:
                    continue
                keys = [k for k, _ in vials]
                run = self.runs[self._eff.sources[i].path]
                how, size = self._strip_how(i)
                cells = _strip_cells([sl.rack for sl in run.slots], len(extra), how, size)
                sh = Sheet([])
                sh.vials, sh.cells = keys, cells
                sh.at = {rc: fi for fi, rc in cells.items()}
                sh.setRowCount(1 + max(r for r, _ in cells.values()))
                sh.setColumnCount(1 + max(c for _, c in cells.values()))
                names = ["vial", *labels]
                if how == "rows":
                    sh.setVerticalHeaderLabels([names[r % len(names)]
                                                for r in range(sh.rowCount())])
                    sh.horizontalHeader().setVisible(False)
                    sh.verticalHeader().setVisible(True)
                else:
                    sh.setHorizontalHeaderLabels([names[c % len(names)]
                                                  for c in range(sh.columnCount())])
                for r in range(sh.rowCount()):           # gaps and vial names: not typed in
                    for c in range(sh.columnCount()):
                        sh.put(r, c, "", editable=False)
                for k, key in enumerate(keys):
                    sh.put(*cells[(-1, k)], key, editable=False, color="#8d8d8d")
                sh.setAlternatingRowColors(False)
                sh.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                sh.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                sh.setToolTip("Click a cell to pick from the list, or type (any part of a "
                              "name completes). Placing a vial proposes the vials after it in "
                              "grey: Tab fills them. Select several and type: a comma list is "
                              "dealt along them (107, 108, 109 over six vials: 107 108 109 "
                              "107 108 109). Ctrl+V pastes a row from Excel, Del takes a "
                              "vial out")
                sh.setItemDelegate(_NameDelegate(sh, lambda ix, sh=sh: (
                    [a.id for a in self.study.animals if a.id],
                    [x.name for x in self.study.tissues], [])[
                        min(2, sh.at.get((ix.row(), ix.column()), (2,))[0])]))
                sh.key = lambda k, i=i: self._strip_key(i, k)
                sh.edited.connect(lambda out, i=i, sh=sh: self._strip_edited(i, sh.vials, [
                    (*sh.at[(r, c)], v) for r, c, v in out if (r, c) in sh.at]))
                self._strip_fit(sh, rows[i])
                box = QWidget()                      # its own width, not the table's
                h = QHBoxLayout(box)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(sh, 10)                  # up to its maximum width
                h.addStretch(1)
                box.setFixedHeight(sh.height())
                r = self._srows.index(i) + 1
                t.insertRow(r)
                self._srows.insert(r, None)
                t.setSpan(r, 0, 1, t.columnCount())
                t.setCellWidget(r, 0, box)
                self._strip_sheets[i] = sh
            t.fit(PREFS["table_rows"])
            for r, i in enumerate(self._srows):     # after fit: it sizes the columns only
                if i is None:
                    t.setRowHeight(r, t.cellWidget(r, 0).height())
            t.fit(PREFS["table_rows"])
        for i, (uid, name, vials, summary, is_open) in enumerate(rows):
            if i not in self._srows:
                continue
            r = self._srows.index(i)
            if it := t.item(r, 0):
                it.setText(f"{'▾' if is_open else '▸'}  {name}" if vials else name)
            if vials:
                src = self.study.sources[i]
                used = [v for _, v in vials if v and len(v) > 1 and v[0] and v[1]]
                bt = self.study.batch_tissues(src.batch)
                batch = f"{src.batch or 'main'}: " if len(self.study.batch_names()) > 1 else ""
                tip = summary + ("\nClick to " + ("fold" if is_open else
                                                   "see and edit the vials one by one"))
                for c, text in ((4, names_summary([v[0] for v in used], [
                                    a.id for a in self.study.animals if a.id])),
                                (5, batch + names_summary([v[1] for v in used], bt or [
                                    x.name for x in self.study.tissues]))):
                    if it := t.item(r, c):
                        it.setText(text)
                        it.setToolTip(tip)
            if not (sh := self._strip_sheets.get(i)):
                continue
            prop = self._proposal[1] if self._proposal and self._proposal[0] == uid else {}
            sh.blockSignals(True)                    # colouring a cell is not an edit
            for c, (key, v) in enumerate(vials):
                v, grey = v or [], key in prop and list(v or []) != prop[key]
                for r in (0, 1):
                    it = sh.put(*sh.cells[(r, c)], prop[key][r] if grey else v[r] if len(v) > r
                                else "")
                    f = it.font()
                    f.setItalic(grey)
                    it.setFont(f)
                    it.setForeground(QColor("#8a8a8a" if grey else _ACCENT if (
                        len(v) > 1 and v[0] and v[1]) or not (v and any(v)) else "#d9b44a"))
                    it.setToolTip("proposed — Tab fills it, Esc drops it" if grey else
                                  "" if len(v) > 1 and v[0] and v[1] else
                                  "not used" if not (v and any(v)) else
                                  "half placed: give it both an animal and a tissue")
            run = self.runs.get(self.study.sources[i].path)
            w = self._eff.window_for(run) if run else None
            for k, x in enumerate(extra):            # read off the file, as it is
                for c, sl in enumerate(run.slots if run else []):
                    g = next((v for v in (sl.sample_g, sl.total_g, sl.tare_g) if v is not None),
                             None)
                    v = g if x == "weight" else \
                        getattr(sl, PREFS["strip_activity"]).get(w) if w else None
                    sh.put(*sh.cells[(2 + k, c)], "" if v is None else f"{v:.4f}"
                           if x == "weight" else f"{v:.0f}", editable=False, color="#8d8d8d")
            sh.blockSignals(False)
            if not sh.fitted:
                self._strip_fit(sh, rows[i])
            sh.viewport().update()

    def _strip_how(self, i) -> tuple[str, int]:
        """A file of one animal goes across, a band per `strip_racks` racks; a file of
        several, in columns, an animal's tissues down each (a tissue's animals, tissue by
        tissue) — or as Options says."""
        src = self._eff.sources[i]
        run = self.runs[src.path]
        lay = PREFS["strip_layout"]
        many = len({p[0] for p in src.mapping(run).values()}) > 1
        if lay == "rows" or lay == "auto" and not many:
            return "rows", max(1, PREFS["strip_racks"])
        down = len(src.tissues) if src.preset == ANIMAL_MAJOR else len(src.animals)
        return "columns", max(1, min(down, len(run.slots)))

    def _strip_fit(self, sh, row):
        """As wide as what it holds (a tissue's name readable), up to the room there is."""
        sh.fitted = any(sh.item(*sh.cells[(1, c)]).text() for c in range(len(sh.vials))
                        if sh.item(*sh.cells[(1, c)]))
        sh.resizeColumnsToContents()
        for c in range(sh.columnCount()):
            sh.setColumnWidth(c, max(44, min(150, sh.columnWidth(c) + 10)))
        hh = sh.horizontalHeader().sizeHint().height() if not sh.horizontalHeader().isHidden() \
            else 0
        vw = sh.verticalHeader().sizeHint().width() if not sh.verticalHeader().isHidden() else 0
        sh.setMaximumWidth(2 * sh.frameWidth() + vw + sum(sh.columnWidth(c)
                                                          for c in range(sh.columnCount())))
        sh.setFixedHeight(2 * sh.frameWidth() + hh + sh.rowCount() * sh.verticalHeader()
                          .defaultSectionSize() + sh.horizontalScrollBar().sizeHint().height())

    def _tail_hints(self):
        """A tail left empty on a card but counted in a vial: in grey on the card, taken back
        to the injection time."""
        for card in self.cards:
            a = card.a
            bq = None if a.tail_mbq is not None else self.res.tail_bq.get(a.id)
            ia = at_injection(self._eff, self.res, a.id, bq) if bq else None
            card.tail_ia = None if ia is None else ia / 1e6
            card._show_dose()
            card.e_tail.setPlaceholderText("MBq" if ia is None else f"{ia / 1e6:.3g}")
            card.e_tail_t.setPlaceholderText("HH:MM" if ia is None
                                             else _shown(a.inj_time, self.study.day))
            card.e_tail.setToolTip("" if ia is None else
                                   f"Counted tail vial: {ia / 1e6:.4g} MBq at injection — "
                                   f"typing a value here replaces it")

    def _strip_edited(self, i, keys, out):
        """Vials placed by hand in a strip: stored as exceptions to the file's order."""
        st = self.study
        known = [[a.id for a in st.animals if a.id], [t.name for t in st.tissues]]
        out = [x for x in out if x[0] < 2]           # the rows under them are read, not typed
        src = st.sources[i]
        bad = []
        for r, c, text in out:
            name = next((k for k in known[r] if k.lower() == text.lower()), text)
            if text and name not in known[r]:
                bad.append(text)
                continue
            key = keys[c]
            v = list(src.slotmap[key]) if key in src.slotmap else list(
                self._eff.sources[i].mapping(self.runs[src.path]).get(key) or ["", ""])
            v = (v + ["", ""])[:2]
            v[r] = name
            src.slotmap[key] = v if any(v) else []
        src.auto = False
        self._proposal = None
        cols = {c for _, c, _ in out}
        if bad:
            self.statusBar().showMessage(f"{', '.join(dict.fromkeys(bad))}: not on the animal "
                                         "cards or in the tissue list — add it there first", 8000)
        elif len(cols) == 1 and i < len(self._strip_rows):
            c, eff = cols.pop(), self._eff.sources[i]
            vials = [v for _, v in self._strip_rows[i][2]]
            vials[c] = src.slotmap.get(keys[c]) or []
            a, t = (list(vials[c]) + ["", ""])[:2]
            every_a = [x.id for x in st.animals if x.id]
            every_t = [x.name for x in st.tissues]
            prop = propose(vials, c, eff.animals if a in eff.animals else every_a,
                           eff.tissues if t in eff.tissues else every_t, src.preset)
            if prop:
                self._proposal = (src.uid, {keys[k]: v for k, v in prop.items()})
                self.statusBar().showMessage(f"Tab fills the {len(prop)} grey vial(s) as "
                                             "proposed — Esc drops them", 15000)
        # redraws the strip (a bad name goes), then offers the fix to the animal's other files
        QTimer.singleShot(0, lambda: (self.recompute(), None if bad else self._offer_fixes()))

    def _strip_key(self, i, key) -> bool:
        """Tab on a strip with vials proposed in grey: they are placed. Esc drops them."""
        src = self.study.sources[i] if i < len(self.study.sources) else None
        if not (self._proposal and src and self._proposal[0] == src.uid
                and key in (Qt.Key_Tab, Qt.Key_Escape)):
            return False
        prop, self._proposal = self._proposal[1], None
        if key == Qt.Key_Tab:
            src.slotmap.update({k: list(v) for k, v in prop.items()})
            src.auto = False
            self.log(f"{Path(src.path).name}: {len(prop)} vial(s) filled as proposed")
        self.statusBar().clearMessage()
        QTimer.singleShot(0, self.recompute)
        return True

    def _windows_used(self, eff: Study) -> dict[str, list[str]]:
        """The windows each auto rule takes in the counting files: what the Results' window
        menu shows beside it."""
        out, keep = {}, (eff.window, eff.window_rule)
        for rule in ("wide", "peak"):
            eff.window, eff.window_rule = "", rule
            out[rule] = sorted({w.split("_", 1)[-1] for x in eff.sources
                                if x.kind in ("count", "weigh_count") and x.path in self.runs
                                and (w := eff.window_for(self.runs[x.path]))})
        eff.window, eff.window_rule = keep
        return out

    def _error(self, kind, err, tb):
        """Something broke inside BioDist (2026.10.5.3: the Results panel emptied with no
        word): the log says where, and the session's log file keeps it."""
        traceback.print_exception(kind, err, tb)
        at = traceback.extract_tb(tb)[-1] if tb else None
        self.log(f"internal error — {kind.__name__}: {err}"
                 + (f" ({Path(at.filename).name}:{at.lineno} {at.name})" if at else "")
                 + " — what was being done may be incomplete; please report it", "✗", "checks")

    def log(self, text, sym="·", kind=""):
        """A line at the bottom of the log, if Options records its kind (the checks: ✗ ⚠ ✓
        ↻ — the report can list them)."""
        kind = kind or ("checks" if sym in "✗⚠✓↻" else "files")
        if kind not in PREFS["log"]["what"]:
            return
        line = f"{_dt.datetime.now():%H:%M:%S}  {sym} {text}"
        self._log.append(line)
        col = {"✗": "#e08080", "⚠": "#d9b44a", "↻": "#888", "✓": _OK_TEXT}.get(sym, "#aaa")
        self.check.append(f"<span style='color:#777'>{line[:8]}</span>&nbsp;&nbsp;"
                          f"<span style='color:{col}'>{html.escape(line[10:])}</span>")
        sb = self.check.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _reset_log(self):
        """A new study: the screen starts over; the session's log file keeps it all."""
        self._offered = set()
        self._log_done += self._log
        self._log = []
        self._facts.clear()
        self.check.clear()

    def save_log(self, as_new=False) -> bool:
        if as_new or not self._log_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save the log", _here(self, f"{self.study.name or 'BioDist'}_log.txt"),
            "Text (*.txt *.log)")
            if not path:
                return False
            self._log_path = Path(path)
        try:
            self._log_path.write_text(self._log_text(), encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not write the log:\n{e}")
            return False
        self.statusBar().showMessage(f"Log saved to {self._log_path}", 6000)
        return True

    def _log_text(self) -> str:
        return (f"{APP_NAME} {__version__} — session of {self._log_start:%Y-%m-%d %H:%M:%S}\n"
                + "".join(x + "\n" for x in self._log_done + self._log))

    def _autosave_log(self):
        """On exit, as Options says: a file per session, or one appended to."""
        lg = PREFS["log"]
        if lg["autosave"] == "off" or not self._log_done + self._log:
            return
        folder = Path(lg["folder"] or APP_DIR / "logs")   # beside the options, not the runtime
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if lg["autosave"] == "session":
                (folder / _log_name(folder, self._log_start, lg["naming"])).write_text(
                    self._log_text(), encoding="utf-8")
            else:
                with open(folder / "BioDist.log", "a", encoding="utf-8") as fh:
                    fh.write("\n" + self._log_text())
        except OSError:
            pass                                 # ponytail: a log that cannot be written is lost

    def _sync_check(self):
        """The Check is a log: a problem goes in when it appears and again when it is gone,
        a file's placement and an animal's summary whenever they change."""
        s, res = self._eff, self.res
        now = {}                                     # key -> (symbol, text)

        def issue(text, sym="⚠"):
            now[text] = (sym, text)
        if not any(a.full_mbq for a in s.animals):
            issue("No injected activity yet — fill the syringe activity and times on the "
                  "animal cards, or drop the lab's injected-activity sheet.")
        if not s.tissues:
            issue("No tissue list — drop a one-column file, or paste one." + (
                f" The {len(s.sources)} file(s) wait for it: placed once it is there."
                if s.sources else ""))
        for n in res.notes:
            issue(n, "✗")
        for n in self.auto_notes:
            issue(n, "↻" if "recount" in n else "⚠")
        for n in unplaced(s, self.runs) if s.tissues else []:   # apart from the guess
            issue(n, "✗")
        fd = self._file_date()
        if fd and fd != s.date:
            issue(f"Study date {s.date} but the files point to {fd} (the filled tubes, else the "
                  f"first count) — the typed HH:MM times are read on the study date, so fix it "
                  f"in the toolbar unless that is really what you mean.")
        for a in s.animals:
            if a.isotope and not half_life_s(a.isotope):
                issue(f"{a.label}: no half-life for {a.isotope} — add it in Options → Isotopes; "
                      f"99mTc's is used until then.")

        for src in s.sources:
            run = self.runs.get(src.path)
            if not run:
                continue
            uid, name = src.uid, Path(src.path).name
            if uid in self._summaries:
                why = self.guess_why.get(uid, "") if src.auto else "placed by hand"
                now[f"src:{uid}"] = ("·", f"{name} ({KIND_LABEL.get(src.kind, src.kind)}"
                                          + (f"; {'guess: ' if src.auto else ''}{why}" if why
                                             else "") + (f"; {run.remark}" if run.remark else "")
                                          + f") — {self._summaries[uid]}")
            if src.auto:
                continue                             # the guess reports on its own
            need = len(src.pairs())
            if need != len(run.slots) and not src.slotmap:
                issue(f"{name}: {len(run.slots)} vials in the file but {need} animal×tissue "
                      f"slots asked for — set animals/tissues on that row so the two agree.")

        counted = {}
        for (aid, tname), c in res.cells.items():
            for f in c.flags:
                counted.setdefault(re.sub(r"[\d.,]+%?$", "", f.split(":")[0]).strip(), []).append(
                    f"{aid}/{tname}")
        for kind, where in sorted(counted.items()):
            shown = ", ".join(where[:8]) + (f" and {len(where) - 8} more" if len(where) > 8 else "")
            now[f"flag:{kind}"] = ("⚠", f"{kind} ({len(where)}): {shown}")

        waiting = []
        for a in s.animals:
            idb = res.injected_bq.get(a.id)
            if not any(k[0] == a.id for k in res.cells):
                waiting.append(a.label)
                continue
            ia = at_injection(s, res, a.id, idb)
            bits = [f"IA {ia / 1e6:,.2f} MBq at injection"] if ia else ["no injected activity yet"]
            rec = recovery_pct(s, res, a.id)
            if rec is not None:
                bits.append(f"sum of tissues {rec:,.1f} %IA")
            now[f"animal:{a.id}"] = ("·", f"{a.label}: " + " · ".join(bits))
        if waiting:
            now["waiting"] = ("·", f"no data yet: {', '.join(waiting)}")

        for key, (sym, text) in now.items():
            if self._facts.get(key) != (sym, text):
                self.log(text, sym, "summaries" if key.startswith(("src:", "animal:", "waiting"))
                         else "")
        for key, (sym, text) in self._facts.items():
            if key not in now and sym in ("✗", "⚠", "↻"):
                self.log(f"resolved: {text}", "✓")
        self._facts = now
        bad = sum(1 for c in res.cells.values() if c.flags)
        self.sec_check.set_note(f"{bad} flagged cell(s)" if bad else "clean")

    def _offer(self):
        """Findings with a fix (Result.suggest), said once per study: one box that does not
        block, a line each, ticked — Apply does the ticked ones (Ctrl+Z undoes them)."""
        new = [sg for sg in self.res.suggest if sg["key"] not in self._offered]
        if not new or not self.isVisible():
            return
        self._offered |= {sg["key"] for sg in new}
        d = QDialog(self)
        d.setWindowTitle(f"{APP_NAME} — worth a look")
        v = QVBoxLayout(d)
        ticks = []
        for sg in new:
            if "picks" in sg:
                a = self.study.animal(sg["animal"])
                text = (f"Animal {a.label if a else sg['animal']}: its small tissues weighed "
                        f"~{sg['mg']:.0f} mg more on the day than when weighed again, the "
                        f"activity unchanged ({', '.join(sg['tissues'][:5])}) — use the later "
                        "weighing for these cells")
            elif "empty" in sg:
                a = self.study.animal(sg["empty"][0])
                text = (f"{a.label if a else sg['empty'][0]} / {sg['empty'][1]}: "
                        f"{sg['mg']:.1f} mg and counting background"
                        + (f" ({sg['counts']:,.0f} counts)" if sg["counts"] is not None else "")
                        + " — an empty tube: mark it so (no value, no flag; Results ▸ side "
                          "panel undoes it)")
            elif "half_life" in sg:
                iso, fh, sh = sg["half_life"]
                text = (f"{iso}: the counter files decay-correct with a half-life of {fh:g} h, "
                        f"this study with {sh:g} h — use the files' (Options › Rules shows it)")
            else:
                text = ("The control tubes changed between their empty and filled weighings ("
                        + ", ".join(f"{_short(n)[-15:]} {mg:+.1f} mg" for n, mg in sg["drift"])
                        + ") — correct those weighings by them (scale)")
            c = QCheckBox(text)
            c.setChecked(True)
            c.setStyleSheet("QCheckBox{padding:3px;}")
            ticks.append((sg, c))
            v.addWidget(c)
        why = QLabel(" ".join(x for k, x in (
            ("picks", "A like amount on every small tube of an animal is no tissue: cold tubes "
                      "read heavy, or water on the outside, gone since."),
            ("drift", "The control tubes, weighed empty then filled with nothing put in, "
                      "should not change."),
            ("empty", "Under ~2 mg the balance reads about nothing, and counts under 3 σ of "
                      "the background are no activity: a tube with nothing in it."),
            ("half_life", "The counter decay-corrects its Bq to its own reference time with "
                          "its half-life; the study takes them on with its own.")) if any(
            k in sg for sg in new)) + " All of it is in the log; the Results' side panel "
            "shows every counting and weighing.")
        why.setWordWrap(True)
        why.setStyleSheet("color:#8d8d8d;")
        v.addWidget(why)
        bb = QDialogButtonBox()
        bb.addButton("Apply the ticked ones", QDialogButtonBox.AcceptRole)
        bb.addButton("Keep as it is", QDialogButtonBox.RejectRole)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)

        def apply():
            fields = {}
            chosen = list(self.study.chosen)
            for sg, c in ticks:
                if not c.isChecked():
                    continue
                if "picks" in sg:
                    keys = [p[:3] for p in sg["picks"]]
                    chosen = [x for x in chosen if x[:3] not in keys] + \
                        [list(p) for p in sg["picks"]]
                    fields["chosen"] = chosen
                elif "empty" in sg:
                    fields["empty"] = fields.get("empty", list(self.study.empty)) + [sg["empty"]]
                elif "half_life" in sg:
                    fields["half_lives"] = {**fields.get("half_lives", self.study.half_lives),
                                            sg["half_life"][0]: sg["half_life"][1]}
                else:
                    fields["drift_fix"] = "scale"
                self.log("applied: " + c.text()[:90], "✎", "edits")
            if fields:
                self._data_changed(fields)
        d.accepted.connect(apply)
        d.resize(760, d.sizeHint().height())
        d.show()

    def preview(self, chosen) -> tuple[Study, Result]:
        """The study as it is, with other picks: what the Results show before Apply."""
        st = dataclasses.replace(self._eff, chosen=copy.deepcopy(chosen))
        return st, compute(st, self.runs)

    def show_report(self):
        self.recompute()
        self.report.refresh()
        _bring(self.report)

    def show_results(self):
        self.recompute()
        if self.res.no_eff and self.isVisible():
            self._ask_eff()
        if not self.results.isVisible():
            self.results.fit_window()
        _bring(self.results)

    # ------------------------------------------------------------------- history
    def _state(self) -> str:
        """The study as undo and the * see it: without the files' data it keeps."""
        kept, self.study.embedded = self.study.embedded, {}
        try:
            return self.study.to_json()
        finally:
            self.study.embedded = kept

    def _record(self):
        """Every edit ends in recompute(), so comparing snapshots here catches them all."""
        now = self._state()
        if self._snap is not None and now != self._snap:
            if "edits" in PREFS["log"]["what"]:
                for line in _changes(self._snap, now):
                    self.log(line, "✎", "edits")
            self._undo.append(self._snap)
            del self._undo[:-100]
            self._redo.clear()
        self._snap = now
        self._title()

    def _reset_history(self):
        self._undo.clear()
        self._redo.clear()
        self._snap = self._saved = self._state()
        self._title()

    def _step(self, back: bool):
        self._record()               # a note still being typed is a step of its own
        src, dst = (self._undo, self._redo) if back else (self._redo, self._undo)
        if not src:
            self.statusBar().showMessage(f"Nothing to {'undo' if back else 'redo'}", 3000)
            return
        dst.append(self._snap)
        kept, self.study = self.study.embedded, Study.from_json(src.pop())
        self.study.embedded = kept
        self.log("undo" if back else "redo", "↻")
        self._snap = None            # _sync may tidy the restored study; that is no new step
        self._sync()

    def undo(self):
        self._step(True)

    def redo(self):
        self._step(False)

    def _dirty(self) -> bool:
        return self._state() != self._saved

    def _title(self):
        self.setWindowTitle(f"{APP_NAME} {__version__}"
                            + (f" — {self._path.name}" if self._path else "")
                            + (" *" if self._snap != self._saved else ""))

    def _keep_or_save(self) -> bool:
        """Before the study is replaced or the window closes: False means stay put."""
        if not self._dirty():
            return True
        ans = QMessageBox.question(
            self, APP_NAME, "Save the changes to this study first?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if ans == QMessageBox.Save:
            return self.save_study()
        return ans == QMessageBox.Discard

    def closeEvent(self, ev):
        if self._keep_or_save():
            self._autosave_log()
            ev.accept()
        else:
            ev.ignore()

    # ------------------------------------------------------------------ study i/o
    def open_study(self):
        if not self._keep_or_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open study", _here(self),
                                              "BioDist study (*.json)")
        if path:
            self._load_study(Path(path))

    def new_study(self):
        if not self._keep_or_save():
            return
        self.study = _new_study()
        self._path, self._date_typed = None, False
        self.runs.clear()
        self._reset_log()
        self.log("new study")
        self._snap = None            # another study, not an edit of this one
        self._sync()
        self._reset_history()

    @busy("Opening the study…")
    def _load_study(self, path: Path):
        try:
            self.study = Study.load(path)
        except Exception as e:  # noqa: BLE001 — a bad file must not take the window down
            QMessageBox.warning(self, APP_NAME, f"Could not open that study:\n{e}")
            return
        self._path = path
        self._date_typed = True    # a saved study carries its own date
        self.runs.clear()
        self._reset_log()
        self.log(f"opened {path.name}")
        self._check_files()
        self._time_order()
        self._snap = None            # another study, not an edit of this one
        self._sync()
        self._reset_history()
        self.statusBar().showMessage(f"Opened {path}", 6000)

    def save_study(self, as_new=False) -> bool:
        if as_new or not self._path:
            name = (self.study.name or "study") + ".json"
            path, _ = QFileDialog.getSaveFileName(self, "Save study", _here(self, name),
                                                  "BioDist study (*.json)")
            if not path:
                return False
            self._path = Path(path)
        self._read_runs()
        self.study.keep_half_lives()             # it reproduces whatever Options say later
        self.study.embedded = {s.path: hidex.pack(self.runs[s.path]) for s in self.study.sources
                               if s.path in self.runs} if PREFS["embed"] else {}
        try:
            self.study.save(self._path)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not save:\n{e}")
            return False
        self._record()
        self._saved = self._snap
        self._title()
        self.statusBar().showMessage(f"Saved to {self._path}", 6000)
        self.log(f"saved to {self._path.name}")
        return True
