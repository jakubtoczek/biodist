# BioDist

<img src="src/biodist/assets/biodist.png" width="96" align="right" alt="BioDist icon">

Desktop GUI to turn **gamma counter** exports (Hidex AMG) into a biodistribution table in
**%IA/g** (% of injected activity per gram of tissue), ready to paste into Excel.

## Install (Windows)

No admin rights, no PATH or registry changes.

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
**Drop files anywhere on it** — the counter's exports, the tissue list, a saved study — and
BioDist puts each one where it belongs. Hover anything for what it does. Every feature, a
study step by step and how the numbers are made: **[the user guide](GUIDE.md)**.

- **Animals** — a card per animal: ID, weight, isotope and tracer, syringe full and empty
  with their times, injection time, tail (activity left at the injection site). **+** adds
  an animal; **⤢** opens the animal window for everything else.
- **Tissues** — the vials in counting order. **+** loads a list (a recorded one, a file or
  the clipboard). Each tissue has a **role**: `tissue`, `tail`, `blank` (an empty control
  tube) or `standard`. **+** on a tissue adds a row to type a mass or an activity measured
  apart (paraffin, dose calibrator).
- **Data sources** — the counter's files, a row each. BioDist works out what each one is
  (tare, weight, count, count + weight), matches the racks, spots recounts and places the
  vials on animals and tissues; the log says why, file by file — just check it. Click a file
  (▸) to see its vials and place them by hand.
- **Log** — what happened and what looks wrong (✗ ⚠), and when it is resolved (✓).

**Ctrl+S** saves the study as one `.json`. It keeps a copy of the counter files' data, so it
opens the same when they are moved.

### Results (Ctrl+R)

Tissues down, animals across. **data** picks the unit (%IA/g, %IA, SUV, Bq, mass…);
**show** adds rows (injected activity, activity at the SPECT / PET start…); **highlight**
picks the flags that tint a cell; **▤** sets which animals and tissues show, in which order.

Click a cell: the side panel (**sources**) shows its countings and weighings side by side,
ticked where in use, ⚠ where something looks off (hover for why). Click a row to use it
alone (Ctrl+click adds or removes one; a counting's energy window is picked in its row),
then **Apply** to keep it for the selected cells.

**⧉** copies the table (Ctrl+C the selection); **Export…** writes `.xlsx` / `.csv`.

### Report (Ctrl+P)

Tick the sections, drag them in order, then **Save report…** — `.xlsx` (a sheet per
section), `.odt` (Word), `.pdf`, `.md` or `.html`.

### Options

To choose various options.

The version is in the window title and on every report.

## Dev

```
uv run python -m biodist                         # launch
uv run python -m biodist.hidex --self-check      # file reader vs internal reference exports
uv run python -m biodist.study                   # calculations (%IA/g) vs internal reference values
uv run python misc/smoke_test.py                 # the whole window, driven without a screen
uv run python misc/bump.py                       # stamp today's date as the version
```

The three checks read reference exports kept outside this repository (not shared); their
folder can be given at the end of the command.
