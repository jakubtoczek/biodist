"""Reader for Hidex Automatic Gamma Counter "AutoExport" .xlsx files.

Every export has the same shape on its `Results` sheet: a metadata header, a
`Counting windows` block, a `Racks` block, then a `Results` table.  The `Run type`
row says which of the three run kinds it is, and that decides which columns the
results table carries:

    Tare only        Rack, Vial, Tare (g)
    Count only       Rack, Vial, Time, Dead time factor, counts/CPM/Bq per window
    Weigh and count  ... plus Total mass (g), Tare (g), Sample mass (g)

The `Spectra` sheet holds 2047 channel columns per vial and is never read. Each window's
"Counting efficiency" (counts per decay) is what turned its CPM into Bq; 1 means none was set.

A Wizard2 .csv export reads into the same Run: a row per vial (Rack, Pos, measurement time,
Counts / CPM per isotope), no efficiency (the study supplies it), and its CPM decay-corrected
to a reference when the protocol says so — a reference the file does not give: it is worked
out from the CPM/counts ratio of the hot vials and undone, so CPM are at the counting time.

Run: python -m biodist.hidex <file.xlsx> ...   (dump)  |  python -m biodist.hidex --self-check
"""

from __future__ import annotations

import csv
import datetime as _dt
import math
import re
import statistics
import warnings
from dataclasses import dataclass, field
from pathlib import Path

# Hidex writes its sheets without a default style block; openpyxl says so on every file.
warnings.filterwarnings("ignore", message=".*no default style.*", module="openpyxl")

# Run-type substring -> kind. Matched case-insensitively against the "Run type" row.
_KINDS = [("weigh and count", "weigh_count"), ("tare only", "tare"), ("count only", "count")]
KIND_LABEL = {"tare": "Tare", "count": "Count", "weigh_count": "Weigh + count"}


@dataclass
class Slot:
    """One vial position in a run."""

    rack: int
    vial: int
    tare_g: float | None = None
    total_g: float | None = None
    sample_g: float | None = None  # only set when the run tared internally
    time: _dt.datetime | None = None
    dead_time: float | None = None
    bq: dict[str, float] = field(default_factory=dict)   # window -> normalized Bq
    cpm: dict[str, float] = field(default_factory=dict)  # window -> CPM at count time
    counts: dict[str, float] = field(default_factory=dict)  # window -> raw counts (statistics)
    secs: float | None = None       # counted for this long: CPM × secs / 60 = the net counts

    @property
    def key(self) -> str:
        return f"{self.rack}:{self.vial}"

    def mass_g(self, tare: float | None = None) -> float | None:
        """Sample mass: the run's own if it tared, else total minus the tare given."""
        if self.sample_g is not None:
            return self.sample_g
        t = self.tare_g if tare is None else tare
        if self.total_g is None or t is None:
            return None
        return self.total_g - t


@dataclass
class Run:
    """One Hidex export file."""

    path: Path
    template: str
    run_type: str
    kind: str                       # "tare" | "count" | "weigh_count"
    started: _dt.datetime | None
    normalized_to: _dt.datetime | None
    windows: list[str]              # full window names, e.g. "\u2079\u2079\u1d50Tc_112-168"
    half_life_s: dict[str, float]
    slots: list[Slot]
    counter: str = ""               # the machine: "Hidex AMG 2240360", "Wizard2"
    efficiency: dict[str, float] = field(default_factory=dict)   # window -> counts per decay
    remark: str = ""                # what reading it worked out, for the log

    @property
    def name(self) -> str:
        return self.path.name

    def short_windows(self) -> list[str]:
        """Window names without the isotope prefix: '\u2079\u2079\u1d50Tc_112-168' -> '112-168'."""
        return [w.split("_", 1)[-1] for w in self.windows]

    def by_key(self) -> dict[str, Slot]:
        return {s.key: s for s in self.slots}


def pack(run: Run) -> dict:
    """A run as plain, compact JSON: what a study keeps of it, to open without the file."""
    def iso(t):
        return t.isoformat() if t else None
    w = run.windows
    return {"t": run.template, "r": run.run_type, "k": run.kind, "s": iso(run.started),
            "n": iso(run.normalized_to), "w": w, "h": run.half_life_s, "c": run.counter,
            "e": run.efficiency, "m": run.remark,
            "v": [[x.rack, x.vial, x.tare_g, x.total_g, x.sample_g, iso(x.time), x.dead_time,
                   *([m.get(k) for k in w] for m in (x.bq, x.cpm, x.counts)), x.secs]
                  for x in run.slots]}


def unpack(path, d: dict) -> Run:
    def when(s):
        return _dt.datetime.fromisoformat(s) if s else None
    w = d["w"]
    slots = [Slot(r, v, ta, to, sa, when(ti), dt,
                  *({k: x for k, x in zip(w, xs) if x is not None} for xs in rest[:3]),
                  *rest[3:4])                    # secs: packed since 2026.10.7
             for r, v, ta, to, sa, ti, dt, *rest in d["v"]]
    return Run(Path(path), d["t"], d["r"], d["k"], when(d["s"]), when(d["n"]), w, d["h"], slots,
               d.get("c", ""), d.get("e", {}), d.get("m", ""))


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _dtime(v):
    if isinstance(v, _dt.datetime):
        return v
    if isinstance(v, str) and v.strip():
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return _dt.datetime.strptime(v.strip(), fmt)
            except ValueError:
                continue
    return None


def _half_life_s(text) -> float | None:
    """'6,00718 h' -> seconds. Hidex writes the decimal comma of its locale."""
    if not isinstance(text, str):
        return None
    m = re.match(r"\s*([\d.,]+)\s*([a-zA-Z]+)", text)
    if not m:
        return None
    v = _num(m.group(1))
    unit = {"s": 1.0, "min": 60.0, "m": 60.0, "h": 3600.0, "d": 86400.0}.get(m.group(2).lower())
    return v * unit if v is not None and unit else None


def _section(rows, title):
    """Index of the row whose first cell is exactly `title`, or None."""
    for i, r in enumerate(rows):
        if r and isinstance(r[0], str) and r[0].strip() == title:
            return i
    return None


def _table(rows, start):
    """Header row at `start`, then data rows until the first blank first cell."""
    hdr = [(str(c).strip() if c is not None else "") for c in rows[start]]
    out = []
    for r in rows[start + 1:]:
        if not r or r[0] is None or (isinstance(r[0], str) and not r[0].strip()):
            break
        out.append(dict(zip(hdr, r)))
    return hdr, out


def read(path) -> Run:
    """Parse one AutoExport file (or a Wizard2 .csv). Raises ValueError if it is neither."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return read_wizard(path)
    import openpyxl                      # half a second: paid on the first file, not at start
    from openpyxl.worksheet._read_only import ReadOnlyWorksheet
    # ponytail: opening a read-only workbook scans every sheet for its size, the ~2000-column
    # Spectra one too (0.13 s of a file's 0.16 s); rows are read to their end without it.
    # Pinned openpyxl 3.1 — if an update renames _get_size this only costs time again.
    ReadOnlyWorksheet._get_size = lambda self: None
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    if "Results" not in wb.sheetnames:
        raise ValueError(f"{path.name}: no 'Results' sheet — not a Hidex AutoExport file")
    rows = [r for r in wb["Results"].iter_rows(values_only=True)]
    wb.close()
    if not rows or not (isinstance(rows[0][0], str) and "Hidex" in rows[0][0]):
        raise ValueError(f"{path.name}: missing the Hidex header line")

    meta = {}
    for r in rows[:20]:
        if r and isinstance(r[0], str) and len(r) > 1 and r[1] is not None:
            meta.setdefault(r[0].strip(), r[1])

    run_type = str(meta.get("Run type", ""))
    kind = next((k for sub, k in _KINDS if sub in run_type.lower()), "")
    if not kind:
        raise ValueError(f"{path.name}: unrecognised run type {run_type!r}")

    windows, half, eff = [], {}, {}
    i = _section(rows, "Counting windows")
    if i is not None:
        _, wrows = _table(rows, i + 1)
        for w in wrows:
            name = w.get("Isotope")
            if name:
                windows.append(str(name))
                hl = _half_life_s(w.get("Half-life"))
                if hl:
                    half[str(name)] = hl
                if (e := _num(w.get("Counting efficiency"))) is not None:
                    eff[str(name)] = e

    # "Results" titles both the sheet's own header and the table; the table is the last one.
    i = next((j for j in range(len(rows) - 1, -1, -1)
              if rows[j] and isinstance(rows[j][0], str) and rows[j][0].strip() == "Results"), None)
    if i is None:
        raise ValueError(f"{path.name}: no results table")
    _, data = _table(rows, i + 1)

    slots = []
    for d in data:
        s = Slot(rack=int(_num(d.get("Rack")) or 0), vial=int(_num(d.get("Vial")) or 0))
        s.tare_g = _num(d.get("Tare (g)"))
        s.total_g = _num(d.get("Total mass (g)"))
        s.sample_g = _num(d.get("Sample mass (g)"))
        s.time = _dtime(d.get("Time"))
        s.dead_time = _num(d.get("Dead time factor"))
        s.secs = _num(d.get("Counted time (s)"))
        for w in windows:
            bq = _num(d.get(f"Normalized {w} (Bq)"))
            if bq is not None:
                s.bq[w] = bq
            cpm = _num(d.get(f"{w} (CPM)"))
            if cpm is not None:
                s.cpm[w] = cpm
            n = _num(d.get(f"{w} (counts)"))
            if n is not None:
                s.counts[w] = n
        slots.append(s)

    return Run(
        path=path,
        template=str(meta.get("Template", "")),
        run_type=run_type,
        kind=kind,
        started=_dtime(meta.get("Run started")),
        normalized_to=_dtime(meta.get("Result normalization")),
        windows=windows,
        half_life_s=half,
        slots=slots,
        counter=f"Hidex AMG {meta.get('AMG serial number', '')}".strip(),
        efficiency=eff,
    )


def _decay_ref(slots, w: str, secs: dict, hl_s: float | None) -> _dt.datetime | None:
    """The instant a Wizard2 file's CPM were decay-corrected to, or None if they were not.
    CPM / (counts per minute) is the correction (plus dead time and background, small on hot
    vials): corrected, it grows with the counting time as the decay does, every vial giving
    the same reference; not corrected, it stays near 1."""
    if not hl_s:
        return None
    lam = math.log(2) / hl_s
    # ponytail: background pulls a thin vial's estimate late, dead time a hot one's early
    # (000563: 10:12 at 1,000 counts, 09:42 at 790,000); 10,000-50,000 counts sit within a
    # minute of the reference. Fit dead time and background (ln r ~ rate, 1/rate) if a file
    # has no vials there
    for lo, hi in ((10000, 50000), (1000, math.inf)):
        pts = [(s.time, s.cpm[w] * secs[s.key] / 60 / s.counts[w]) for s in slots
               if s.time and lo <= s.counts.get(w, 0) < hi and s.cpm.get(w, 0) > 0
               and secs[s.key]]
        if len(pts) >= 2:
            break
    if len(pts) < 2 or statistics.median(math.log(r) for _, r in pts) < 0.03:
        return None
    t0s = [t - _dt.timedelta(seconds=math.log(r) / lam) for t, r in pts]
    ts = [t for t, _ in pts]

    def mad(xs):
        m = statistics.median(x.timestamp() for x in xs)
        return statistics.median(abs(x.timestamp() - m) for x in xs)
    if (max(ts) - min(ts)).total_seconds() > 1200 and mad(t0s) > 0.3 * mad(ts):
        return None                              # tracks the clock: no fixed reference
    t0 = _dt.datetime.fromtimestamp(statistics.median(x.timestamp() for x in t0s))
    return (t0 + _dt.timedelta(seconds=30)).replace(second=0, microsecond=0)


def read_wizard(path) -> Run:
    """A Wizard2 .csv export: one row per vial, Counts / CPM per isotope, no efficiency."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows or not {"Rack", "Pos", "Measurement date & time"} <= set(rows[0]):
        raise ValueError(f"{path.name}: not a Wizard2 export")
    windows = [k[:-4] for k in rows[0] if k.endswith(" CPM")]
    if not windows:
        raise ValueError(f"{path.name}: no CPM column")
    from .study import half_life_s               # here: study imports this module
    slots, secs = [], {}
    for d in rows:
        s = Slot(rack=int(_num(d.get("Rack")) or 0), vial=int(_num(d.get("Pos")) or 0))
        s.time = _dtime(d.get("Measurement date & time"))
        secs[s.key] = s.secs = _num(d.get("Time")) or 0
        for w in windows:
            if (n := _num(d.get(f"{w} Counts"))) is not None:
                s.counts[w] = n
            if (c := _num(d.get(f"{w} CPM"))) is not None:
                s.cpm[w] = c
        slots.append(s)
    half = {w: hl for w in windows if (hl := half_life_s(w))}
    said = []
    for w in windows:
        t0 = _decay_ref(slots, w, secs, half.get(w))
        if t0:
            lam = math.log(2) / half[w]
            for s in slots:
                if w in s.cpm and s.time:
                    s.cpm[w] *= math.exp(-lam * (s.time - t0).total_seconds())
            said.append(f"{w} CPM decay-corrected by the counter to {t0:%d %b %H:%M} — undone")
    times = [s.time for s in slots if s.time]
    return Run(path=path, template=str(rows[0].get("Protocol name", "")),
               run_type="Wizard2 count", kind="count", started=min(times, default=None),
               normalized_to=None, windows=windows, half_life_s=half, slots=slots,
               counter="Wizard2", remark="; ".join(said))


def is_hidex(path) -> bool:
    try:
        read(path)
        return True
    except Exception:  # noqa: BLE001 — any failure means "not one of ours"
        return False


# --------------------------------------------------------------------- self-check
def _self_check(data_dir):
    """Assert the reader agrees with the 260903 sample set."""
    d = Path(data_dir)
    tare0 = read(d / "Tare-001-20260902-161122-AutoExport.xlsx")
    tare1 = read(d / "Tare-001-20260903-153146-AutoExport.xlsx")
    cnt1 = read(d / "Tc-99m-002-20260903-185456-AutoExport.xlsx")
    cnt2 = read(d / "Tc-99m-002-20260904-040117-AutoExport.xlsx")
    gtare = read(d / "Tare-001-20260902-165551-AutoExport.xlsx")
    gwc = read(d / "Tc-99m_weights-010-20260903-141827-AutoExport.xlsx")

    kinds = [r.kind for r in (tare0, tare1, cnt1, cnt2, gtare, gwc)]
    assert kinds == ["tare", "tare", "count", "count", "tare", "weigh_count"], kinds
    assert len(tare0.slots) == len(tare1.slots) == 25, "individual tare runs hold 25 vials"
    assert len(cnt1.slots) == len(cnt2.slots) == 25
    assert len(gtare.slots) == len(gwc.slots) == 6, "the group run holds 6 vials"

    assert not tare0.windows and cnt1.short_windows() == ["112-168", "15-2047"]
    assert abs(cnt1.half_life_s[cnt1.windows[0]] - 6.00718 * 3600) < 1, "comma decimal half-life"
    assert cnt1.normalized_to == cnt2.normalized_to == _dt.datetime(2026, 9, 3, 16, 0)

    # masses: filled minus empty, vial by vial
    w = cnt1.windows[0]
    m = {a.key: b.tare_g - a.tare_g for a, b in zip(tare0.slots, tare1.slots)}
    assert abs(m["2:4"] - 0.9223) < 1e-4, m["2:4"]          # liver
    assert abs(m["1:4"] - 0.1691) < 1e-4, m["1:4"]          # blood
    assert cnt1.by_key()["2:4"].bq[w] == 130138             # liver, first count
    assert cnt2.by_key()["2:4"].bq[w] == 136095             # ... and the overnight recount
    assert cnt1.by_key()["2:3"].bq[w] < 10, "kidneys went to the dose calibrator: empty slot"
    assert cnt1.by_key()["2:4"].counts[w] > 1000 > cnt1.by_key()["2:3"].counts[w]

    # the group run tared from a separate file, so mass needs the paired tare
    tg = gtare.by_key()
    assert gwc.slots[0].mass_g() is None, "no internal tare in this weigh-and-count run"
    assert abs(gwc.slots[0].mass_g(tg["1:1"].tare_g) - 0.2767) < 1e-4
    assert abs(gwc.slots[3].mass_g(tg["1:4"].tare_g) - 0.0676) < 1e-4
    assert cnt1.efficiency == {cnt1.windows[0]: 0.758, cnt1.windows[1]: 0.856}, cnt1.efficiency
    assert cnt1.counter == "Hidex AMG 2240360", cnt1.counter
    assert unpack(cnt1.path, pack(cnt1)).efficiency == cnt1.efficiency
    assert cnt1.slots[0].secs and unpack(cnt1.path, pack(cnt1)).slots[0].secs == cnt1.slots[0].secs
    old = pack(cnt1)
    old["v"] = [x[:-1] for x in old["v"]]        # packed before 2026.10.7: no counted time
    assert unpack(cnt1.path, old).slots[0].secs is None

    # Wizard2: no efficiency; 000563's CPM decay-corrected by the counter to 10:00, undone
    wz = d.parent / "data_misc" / "wizard2" / "000563.csv"
    if wz.exists():
        w2 = read(wz)
        assert (w2.counter, w2.kind, w2.windows, len(w2.slots)) == ("Wizard2", "count",
                                                                    ["Tc-99m"], 96), w2
        assert "to 01 Dec 10:00" in w2.remark and not w2.efficiency, w2.remark
        s = w2.by_key()["1:2"]                   # 47,896 counts in 60 s: ~47,835 CPM then
        assert abs(s.cpm["Tc-99m"] / (s.counts["Tc-99m"] * 60 / 60.04) - 1) < 0.01
    print("hidex self-check ok (6 files, 3 run kinds, Wizard2)")


def _main(argv):
    if "--self-check" in argv:
        i = argv.index("--self-check")
        d = argv[i + 1] if len(argv) > i + 1 else r"C:\Code\BioDist\data_260903"
        _self_check(d)
        return 0
    for p in argv:
        r = read(p)
        print(f"{r.name}\n  {KIND_LABEL[r.kind]} | {r.run_type} | started {r.started}"
              f"\n  windows {r.short_windows()} | norm {r.normalized_to} | {len(r.slots)} slots")
        for s in r.slots[:5]:
            print(f"    {s.key:>6}  tare={s.tare_g} total={s.total_g} dt={s.dead_time} bq={s.bq}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
