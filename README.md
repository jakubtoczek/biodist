# BioDist

<img src="src/biodist/assets/biodist.png" width="96" align="right" alt="BioDist icon">

Desktop app that turns **gamma counter** exports (Hidex AMG, Wizard2) and the lab's weighing
sheets into a biodistribution table — **%IA/g**, %IA, SUV, Bq, masses — ready to paste into
Excel, with a report of how every value was made.

- **Drop the files, check the guesses**: it works out what each counter file is (tares,
  weighings, countings), matches the racks, places every vial on its animal and tissue, and
  says why in its log — you check and correct, it never decides silently.
- **Every measure kept**: countings and weighings repeated, recounted or typed by hand sit side
  by side; rules you can see choose among them (target range, consensus, drift of the control
  tubes), and flags say what looks off.
- **The injected activity done right**: full and empty syringe, the tail and other corrections,
  each decayed from its own time — across a clock change too.
- **One study file**: the inputs, the rules, a copy of the counter's data, and the results once
  you have **validated** them; a report (`.odt`, `.pdf`, `.xlsx`, `.md`, `.html`) of how every
  number was made, ARRIVE items included.

## Install (Windows)

1. On the GitHub page: **Code ▸ Download ZIP**, and extract it somewhere it can stay
   (`C:\Users\Public\BioDist`, or your Documents).
   If Windows says *"Windows protected your PC"* when the launcher starts, right-click the
   ZIP ▸ Properties ▸ tick **Unblock** before extracting (not every PC shows it).
2. Double-click **`BioDist.bat`**. The first start downloads [`uv`](https://github.com/astral-sh/uv),
   Python and the libraries into `C:\ProgramData\PyApps` (shared with other tools set up
   the same way) and puts a **BioDist** shortcut on the Desktop; later starts are quick.
   `BioDist.bat private` the first time keeps everything in `C:\Users\Public\BioDist`
   instead; `BIODIST_RUNTIME` sets another place.
   To pin it to the taskbar: right-click its taskbar button while it runs (or its Start
   menu entry, which it keeps up to date) ▸ *Pin to taskbar*.

`uninstall.bat` takes it all away again. Your options stay in `biodist_options.json` beside
`BioDist.bat` — copy it to take them to another PC.

## Use

The window is a board, top to bottom: **Animals**, **Tissues**, **Data sources**, **Log**.
**Drop files anywhere on it** — the counter's exports, a weighing sheet, the tissue list, a
saved study or an InjAct recording — and BioDist puts each one where it belongs. Hover
anything for what it does.

1. **Animals** — a card per animal: ID, weight, isotope and tracer, syringe full and empty
   with their times, injection time, tail (injection site), the other corrections to the
   injected activity; **⤢** for everything else (the animal's information, **+ model**,
   **+ procedure**).
2. **Tissues** — the vials in counting order, each with its role (`tissue`, `tail`, `blank`,
   `standard`); **+** on a tissue for a mass or an activity measured apart (dose calibrator).
3. **Data sources** — the counter's files: BioDist works out what each one is (tare, weight,
   count, count + weight) and places the vials on animals and tissues; **check it**, and the
   log's ✗ and ⚠.
4. **Results** (Ctrl+R) — tissues down, animals across, in the unit you pick; click a cell for
   every counting and weighing behind it. **Report** (Ctrl+P) — the sections you tick, as
   `.xlsx`, `.odt`, `.pdf`, `.md` or `.html`.
5. **Ctrl+S** saves the study as one `.json` and asks you to **validate the results** (your
   initials or name if you like): only validated results are kept in the study.

Every feature, a study step by step, the options and how the numbers are made:
**[GUIDE.md](GUIDE.md)**. The version is in the window title and on every report.

## Works with

- **InjAct** (Android, at the bench) — its experiment file *is* a BioDist study: open it here,
  then drop the counter's files. What InjAct records and BioDist does not show is kept, so the
  study opens again in InjAct. Options › Import reads InjAct's settings (isotopes, strains,
  procedures, animal fields), and InjAct imports BioDist's.
- **BioDistAn** — statistics and figures from the study's validated results (%IA/g, or SUV
  from the animals' body weights); a study not validated, or changed since, it does not open.

## Development

```
uv run python -m biodist                         # launch
uv run python -m biodist.hidex --self-check      # file reader vs internal reference exports
uv run python -m biodist.study                   # calculations (%IA/g) vs internal reference values
uv run python misc/smoke_test.py                 # the whole window, driven without a screen
uv run python misc/bump.py                       # stamp today's date as the version
```

The three checks read reference exports kept outside this repository (not shared); their
folder can be given at the end of the command. `study.py` is the model and maths (no Qt),
`app.py` the window, `hidex.py` the counter files' reader.

## Licence

MIT — see [LICENSE](LICENSE).
