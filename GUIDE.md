# BioDist — user guide

BioDist turns the exports of a Hidex AMG gamma counter (tare weighings, filled-tube weighings,
countings) into a biodistribution table: **%IA/g**, %IA, SUV, Bq, masses — one tissue per row,
one animal per column, ready to paste into Excel — and writes a report of how every value
was made. Everything is kept in one study file.

> **Check the guesses.** BioDist guesses what each file is and where its vials go — from
> tube weights, run times and activities — and says why in the log. It is a starting
> point, not a result: before using the values, check in Data sources that every file has
> the right kind, animals and tissues, and read the log's ✗ and ⚠. A guess that looks
> right can still be wrong (two racks of tubes that happen to weigh alike, a rack weighed
> out of turn, a vial left out). The rules that choose among repeated countings and
> weighings are defaults too: review them for your study (Options › Rules).

- [Features](#features)
- [A study, step by step](#a-study-step-by-step)
- [The board](#the-board): animals, tissues, data sources, log
- [Results](#results)
- [Report](#report)
- [Options](#options)
- [How the numbers are made](#how-the-numbers-are-made)
- [When something looks wrong](#when-something-looks-wrong)
- [Shortcuts](#shortcuts)

---

## Features

**Reading the data**
- Hidex AMG *AutoExport* `.xlsx` files of every run type: tare only, count only, weigh and count.
- PerkinElmer Wizard2 `.csv` exports, countings only (no weighings, no efficiency in the
  file: it is typed in Data sources). Added to broaden the tool's reach: the reader is
  checked on sample exports, but no study using a Wizard2 has been run through BioDist
  end to end yet — check its values with particular care.
- Drop anything anywhere on the window: counter files, a tissue list (one column), a saved
  study. Files dropped before the tissue list wait for it.
- Each file's kind is worked out: empty tubes (tare), filled tubes (weight), counting,
  counting + weighing — and where its vials go (which animal, which tissue).
- Racks are matched on tube weight: a filled rack finds its empty rack even when it was
  weighed out of turn (a rack slip), and a tube taken out between two weighings is noticed.
- Recounts are recognised (the same activities, vial by vial, once decayed to one time).
- Every guess is explained in the log, file by file; any of it can be changed by hand.
- The counter's own counting efficiency is read for each energy window; it can be typed
  instead.

**Animals**
- A card per animal: ID and aliases, species, strain, genotype, sex, date of birth (or age),
  body weight, isotope and molecule, injection time, syringe full and empty, tail.
- The animal window: every field, grouped as the values need them (red), as ARRIVE 2.0 asks
  (amber), and the rest; copy a field to the other animals; corrections to the injected
  activity; notes.
- ARRIVE item 9 in two parts: the **model**, days or weeks before (diet, treatment, tumour,
  surgery) and the study day's **procedures** (pre-, co- or post-injection, imaging — SPECT,
  PET, CT… —, anaesthesia), or any other — each kind with its own fields, pre-filled as
  Options says (by case: `4-5 % if agent = isoflurane`).
- Times typed as a clock time (13:10, 13:10 d+1) or after the injection (2 h p.i.); days as a
  date, an age (8 wk) or from the study day (D-14) — the other forms are worked out.
- Every animal side by side in one table: type into several cells at once, paste from Excel.

**Tissues**
- Recorded tissue lists, a file, the clipboard, or one at a time.
- A role per tissue: tissue, tail (injection site), blank (control tube, empty vial),
  standard. Blanks check the balance and the background.
- Masses or activities measured apart (paraffin, dose calibrator) typed on the tissue's own
  row; they replace the files' values for that cell.
- Weighing sheets made by hand, dropped like the rest: `.xlsx`, `.ods` (LibreOffice), `.csv`,
  and a balance's `.wt` (one weight a line, in the tissues' order; its name says the animal
  and the pass: `S2 empty.wt`, `S2 full.wt`). Tissues down; an animal's block of columns
  under its ID or alias (`MICID MI 37`, `SKG-75`, `S1` all name animal 37, SKG-75, 1),
  blocks across and further down; or one animal a sheet, named in the file name; or one row
  a tube with an animal column. Each column's header says what it holds — empty tube /
  tare / vide / foil, full tube / plein / total mass, a mass (direct, difference, wt,
  tissue); said once over several columns, it holds for them. A mass is used as typed; an
  empty tube is a tare and a full tube is weighed against it, so a sheet of tares and the
  full tubes (another sheet, a `.wt`, the counter's run) make the mass together. A full tube
  far lighter than its tare is a tissue weighed on its own. What does not add up (465 typed
  for 3.465) is listed, not used.
- The table shows, for each animal, the mass and activity in use.

**Results**
- %IA/g, %IA, SUV, Bq/g (kBq/g, MBq/g), Bq (kBq, MBq), mass (g or mg), counts, CPM, dead
  time, and where each value comes from.
- Rows for the injected activity, the activity at the SPECT / PET start, the tail, the body
  weight, the sum of the tissues.
- Cells tinted by what looks off (no mass, at background, under or over the valid range,
  measures that disagree, out of the expected range).
- Click a cell: every counting and weighing of it side by side, with its flags; click another
  (or pick another energy window) and Apply to use it for that cell — or for all the selected.
- Copy to Excel in one click, export `.xlsx` / `.csv`; choose and rename the animals and
  tissues shown, and their order.

**Rules (how the values are chosen)**
- Which energy window, which counting when a vial was counted several times, which weighing
  when a tube was weighed several times — saved with the study, so it reproduces.
- A validity range and a target range for countings: a bottom (counts, CPM or the activity
  in the vial) and a top (the dead time, or counts, CPM, activity).
- Measures that do not agree with the others (the consensus) are flagged, and can be left out.
- Control tubes can correct every weighing after the tares for balance drift.
- A tube that weighs about nothing and counts background is offered to be marked empty.
- The study keeps its half-lives; a counter file that decay-corrects with another one is said,
  and what the file said is kept with it.
- Times across a clock change are counted in real time (22:00 → 04:00 over the October change:
  7 h); a time in the hour the clock repeats or skips is said in the log.
- Cross-checks: a count file placed nowhere, rounds that each miss an animal the other
  counted, two files reading the same vials placed on different animals.

**Report and records**
- Report sections ticked, ordered, copied: study, data files, animals, ARRIVE check, value
  tables in any unit, checks, raw counts, repeated measures.
- Saved as `.xlsx`, `.odt` (Word), `.pdf`, `.md` or `.html`.
- A log of what happened and what looks wrong, saved per session if wished.
- The study file keeps the counter files' data and where they are, also from its own folder:
  move the study's folder with its files and it opens on them; move the study alone and it
  still finds them; a file gone, its copy is used; a file changed since, you choose.
- Undo / redo of every edit (Ctrl+Z / Ctrl+Y).

---

## A study, step by step

**Before or on the study day**

1. **New study** (Ctrl+N). Type its name and check the date in the toolbar (the day the
   HH:MM times belong to). Save it (Ctrl+S) where its files will live.
2. **Animals.** Fill the first card; **+** after the last card adds the next one, with the
   same isotope and molecule. ⤢ on a card opens the animal window for the ARRIVE items and
   the procedures; *▦ every animal* there fills a field for all of them at once.
3. **Tissues.** **+** in the empty Tissues section ▸ a recorded list (or a file, or paste). Check
   the roles: the control tube and empty vials should be `blank`, the tail vial `tail`.
4. **Empty tubes.** Drop the tare files as they come off the counter. They are dealt to the
   animals in time order (the first file to animal 1…).

**After the dissection**

5. **Filled tubes.** Drop the weighing files. Each is matched to its empty tubes by weight,
   rack by rack, and takes their places.
6. **Injection.** Syringe full and empty (MBq and time), injection time, and the tail if it
   was read on the dose calibrator, on each card.

**Counting**

7. Drop the counting files. A second pass over the same vials is recognised as a recount;
   the passes (a pause of 20 min also ends one) are dealt to the animals in round order, so
   a file missing from one round shifts no animal. **Round n** holds each vial's nth pass: a
   group of animals counted later, after a pause, is still their round 1.
8. Read the **log**: what each file was taken for and why, and anything that looks wrong.

**Results and report**

9. **Results** (Ctrl+R): pick the unit; click any cell to see where it comes from.
10. **Report** (Ctrl+P): tick the sections, save.

Files can come in any order and at any time: the guess is made again after every change —
so check Data sources and the log again after each file added.

---

### A study recorded at the bench

An experiment recorded in **InjAct** (the Android bench app) is a BioDist study already: open
its `.json` here (drop it, or Ctrl+O). The animals, their syringes, injection, tail and other
corrections, the tissues read in the dose calibrator or weighed, the molecules and their
radiolabelling, the animals' information and procedures are filled in; then drop the counter's
files as usual. What InjAct keeps that BioDist does not show (how each reading was displayed on
the calibrator, what the experiment's animals share) is kept when BioDist saves the study, so it
opens again in InjAct. Options › Import reads InjAct's settings, and InjAct imports BioDist's.

---

## The board

The main window, top to bottom. Each section folds (▾) and shows its count.

### Animals

A card per animal. The fields:

| field | |
|---|---|
| ID, aliases | the ID columns are named by; **+ alias** for an ear tag, a cage code |
| species, strain, genotype | strain lists per species; a listed strain fills its genotype |
| sex, DOB, g | date of birth (or an age: 12 wk); ▾ in it: supplier, arrival date, age at arrival — the DOB follows, in grey |
| batch | in the animal window, by the supplier: the batch it came in (delivery date, lot or order) |
| tracer | isotope (its half-life is used) and molecule |
| injection | the injection time |
| syringe full / empty | MBq and the time each was read |
| tail | activity left at the injection site (MBq, time) — wins over a tail vial |

- A dot by the syringes: yellow once they and the injection time give the injected
  activity, green once the tail is known too.
- **×** on a field hides it on the cards (Options: on every card); what it holds is kept.
- **+ note**: a free note. **⤢**: the animal window.
- **Tab** moves along a row and on to the next card; **Enter** goes down.
- Times: `11:38`, `11:38:20`, `9:00 d+1` (next day), `1/10 9:00`; `12h39` is read as 12:39.

**The animal window** (⤢ on a card; the ⤢ beside *Animals* opens every animal at once):
- *Biodistribution info* (red when empty and needed), *ARRIVE 2.0* (amber when ARRIVE asks
  for it), *Other*. **copy ▾** copies a field to the other animals (every animal listed, the one copied
  from greyed); **on card** shows it on
  the card.
- **+ correction / note**: a correction to the injected activity — activity that did not go
  in (a cotton on the tail…), taken off it; notes on the biodistribution.
- **Model** — **+ model** and a kind: what was done days or weeks before (diet, treatment
  with its start and end, tumour, surgery with its own anaesthesia and analgesia). Which kinds
  are the model is ticked in Options › Procedures.
- **Procedures** — **+ procedure** and a kind. The first imaging adds its anaesthesia as a
  procedure of its own — a CT added to a SPECT shares it; SPECT/CT typed as one modality
  becomes two sessions. Each kind opens with its fields (Options › Procedures), pre-filled
  (isoflurane, then 4-5 % and 1.5-2 %; SPECT's system, and its isotope / EW by the animal's
  isotope); a change carries what depended on it, a field emptied by hand stays empty;
  **+ field** adds one to that procedure only. A procedure's field has its **copy ▾** and
  **on card** too (the card shows it as *imaging · start*). Time fields take a clock time or
  a time after the injection; day fields a date, an age or D-14 — the others are worked out
  in grey.
- **▦ every animal**: a table, a column per animal; **copy ▾** and **on card** at the end of
  each line, outside the table, as on one animal's page. Select several cells and type to fill them all (a comma list is
  dealt out); Ctrl+V pastes a row or a block copied from Excel.
- ◀ ▶ and the list switch animals; Ctrl+Z undoes.

### Tissues

The vials of one animal, in counting order.

- **+** while the table is empty: a recorded list, open a file, paste, one tissue, edit the
  recorded lists. Once there is a list, none is loaded over it: the **+ under the table** adds
  one tissue (its name ready to type), and **export** writes the list to a file (one tissue a
  line) or records it among the lists the empty table offers.
- Columns: **tissue** (renaming it follows everywhere), **role**, **batch**, **#** (its place;
  typing a number moves it), then one column per animal with the mass and activity in use.
- **role**: `tissue` (in the results), `tail` (taken off the injected activity), `blank`
  (control tube, empty vial — checks the balance and the background), `standard`.
- **batch**: tissues weighed and counted on the spot, in runs of their own (a tumour, a
  muscle), get a batch name; the rest are *main*.
- **+** on a tissue: a row to type a **mass**, an **activity** (dose calibrator, with its
  time) or a **note** for each animal; it replaces the files' value for that cell. **×**
  removes the row and its values; ▸ / ▾ folds the typed rows.
- **▤** beside the title: which tissues the results and the report show, in which order,
  under which name (▤ beside *Animals*: the same for the animals — their order is also
  the order files are dealt in — grouped by molecule if wished).

### Data sources

A row per counter file:

| column | |
|---|---|
| file | ▸ unfolds its vials |
| run | when it ran; ⤢ every column the file holds |
| kind | **tare** (empty tubes), **weight** (filled tubes), **count**, **count + weight**, **(ignored)** |
| vials (racks) | how many |
| animals, tissues | where its vials went |
| order | animal by animal, or tissue by tissue |

- **The guess** (made again after every change): weighings are matched rack by rack on tube
  weight; the earlier side of a match is the empty tubes, dealt to the animals in time order;
  a filled run takes the places of the empty run it matched — every rack must match, so two
  runs of empty tubes are never taken for empty + filled. Counts follow the animals in time
  order; a recount goes where its first counting went (the closest match, if several), and
  the chains of recounts are dealt in round order. The log says why for each file. Then the
  checks: a file placed nowhere, two rounds each missing an animal the other counted (a file
  missing and the others shifted), two files reading the same vials vial by vial but placed
  differently.
- **Unfold a file** (▸): its vials, the animal over the tissue. Type an animal or a tissue
  under a vial to place it; **Tab** fills the rest the same way (Esc drops the proposal).
  BioDist then offers the same fix for that animal's other files.
- **kind**: set it by hand if the guess is wrong; *(ignored)* keeps the file in the study
  but out of every value.
- **Guess again**: everything from the data again (it asks about the files placed by hand).
- **Efficiencies** (under the table): the counting efficiency per counter and energy window —
  the file's own, or typed.

### Log

What happened, newest last: ✗ a problem with the values, ⚠ worth a look, ↻ a recount,
✓ resolved. Study ▸ Log ▸ Save log. Options › Log chooses what it records and whether it is
saved on exit.

When something looks off across a study (an animal's tubes all heavier on the day, control
tubes that moved), BioDist offers the fix once, ready to apply.

---

## Results

Ctrl+R, or the green *Results* button.

- **data**: %IA/g, %IA, SUV, Bq/g, kBq/g, MBq/g, Bq, kBq, MBq, mass (g, mg), counts, CPM,
  dead time, activity source, mass source (Options › Results window: which ones the list
  offers). **decimals**: per unit, kept; Bq and counts are whole (26,100,000 Bq).
- **show**: rows under the tissues — tail and standards, blanks, injected activity, activity
  in the animal at the SPECT / PET start, tail (%IA), body weight, sum of tissues (%IA).
- **highlight**: which problems tint a cell — red, no usable value: *mass <= 0*, *no mass*,
  *at background* (net counts under 3 σ, the detection limit); amber, worth a look: *activity
  in a blank* (1,000 counts or more), *under* / *over the valid range* (the counting in use,
  none of the vial's being valid), *counts differ* / *weighings differ*, *out of the expected
  range* (Options › Rules ▸ Expected per tissue). Hover an item for what it means.
- **▤**: animals and tissues shown, their order and names.
- **⧉** copies the whole table; Ctrl+C the selection; **Export…** (Ctrl+E) `.xlsx` / `.csv`.

**The side panel** (*sources*): click a cell (or select several).
- **Countings**: a row per counting round, its energy window picked in the row (the one in
  use shown) — counts, CPM, kBq at injection, dead time; the dose calibrator when one was
  typed. **Tare** and **weighings**: the tube weights and the tissue mass each gives.
- Ticks are what is in use (half-ticked: by some of the selected cells); **⚠** where
  something is off — hover for why: not valid (too few counts, dead time), out of the
  consensus, disagreeing with another measure.
- **Click a row**: each selected cell that has it uses it alone. **Ctrl+click** adds it, or
  takes it out when ticked. **Another window** in a row: the cells using that counting take it
  in that window, the others keep theirs (all selected, a kidney read on the dose calibrator
  stays on it). A cell without that row, or that would not change, keeps what it had.
- The table shows the result at once (green, bold); **Apply** keeps it for those cells (shown
  in italics after); another cell or closing drops it. **Back to the rules** removes a cell's
  own choice (and ticks not applied); greyed, *follow the rules ✓*: the cells have none.
  **see the rules**: Options › Rules; Options › Results window: a row per window, or a click
  that always adds or removes, can be set instead.
- **empty tube**: ticked, the cells have no value and no flag — nothing was collected in the
  tube. BioDist offers it for a tissue weighing under ~2 mg that counts background (net under
  3 σ); the report's checks list it.

### Validating the results

Saving a study asks **Validate the results?** whenever the %IA/g table as the Results show it
(its tissues, animals, labels and values) is not the one already validated in the study:

- **Validate and save** — the table is kept in the study with the time, and your initials or
  name if you typed them (nothing typed is fine too).
- **Save without validating** — the study is saved, its results are not: they are computed again
  when it is opened, but nothing outside BioDist can use them.
- **Cancel** — nothing is saved.

A change that leaves the table as it was (a note, a procedure) keeps the validation; one that
changes a value, a label or the order asks again. Closing BioDist, opening another study or
starting a new one with results saved but not validated asks too. Opened, the log says when the
results were validated and by whom — and if the study was changed since by another app or by
hand. **BioDistAn** reads only validated results.

---

## Report

Ctrl+P. The sections in a list — tick, drag to reorder, unfold (▸) for what each shows:

| section | |
|---|---|
| General | study, animals, tissues, isotope, molecule, counting efficiency per window; values chosen by hand; the rules (off by default); software and date |
| Sources | counting efficiencies; the data files (those used, or all with what each gave); measures typed by hand |
| Animals | the animals; procedures before the study day; the study day (tracer, injection, corrections, imaging, euthanasia) |
| ARRIVE check | what is missing, or every item per animal |
| Tissue values | one table per unit, its layout and decimals — copy it for another unit |
| Checks | the flagged values and what the log found |
| Raw counts | as exported by the counter |
| Repeated measures | how far repeat countings, energy windows and weighings agree |

Under the last section: **copy** / **remove** the selected one, **+ add** a section as it
starts. **Save report…**: `.xlsx` (a sheet per section), `.odt`, `.pdf`, `.md`, `.html`. The
same list is in Options › Report.

---

## Options

Saved as they change in `biodist_options.json` beside `BioDist.bat`; Ctrl+Z undoes;
Export / Import / Reset to defaults. **Import** reads BioDist's options, or InjAct's settings —
then only what the two share changes (isotopes and half-lives; strains, procedures, animal
fields, whether the tail is subtracted); the rest stays.

| page | |
|---|---|
| Animal cards | the fields a card shows; hide / show on every card; lines before a card scrolls |
| Formats | how times and dates are shown; numbers as typed or tidied |
| Isotopes | names and half-lives |
| Species and strains | strains per species, their genotype |
| Animal fields | the animal's information, field by field as Procedures' (type, list, example, pre-filled — on a new animal and by case: `SPF if supplier = Janvier`), and whether InjAct asks for it at the bench; the core fields (species, strain, the dates, route, euthanasia…) can't be removed or renamed |
| Procedures | the kinds — ticked **model**: done days or weeks before (+ model), else the study day's (+ procedure) — and each kind's fields: type (text, list, time · p.i., date · age · D-n), list items, example, shared line, shown when (`modality = SPECT`), pre-filled (`isoflurane`; by case: `4-5 % if agent = isoflurane; 99mTc (140 keV ± 20 %) if isotope = 99mTc`), asked at the bench or not |
| Tissue table | what a cell shows, the units typed in, the line over the table, the recorded tissue lists |
| Data sources | what shows under a file's vials, how they are laid out, how the guess works |
| Rules | the rules of the study open (below), expected ranges per tissue |
| Results window | the units the data list offers, the decimals box, what show / highlight offer and tick, the side panel (a row per counting or per window; what a click does), decimals |
| Report | the report's sections and format |
| Study file | keep the counter files' data in the study |
| Log | what it records; saved per session or appended, where, under which name |

**Options › Rules**, saved with each study (*Make these the defaults* for new
studies). A change applies at once; **●** marks a rule that is not the defaults (hover: what
they are) — *Back to the defaults* takes them all:
- **Countings**
  - **Counting window**: the widest (one isotope) or the photopeak, or one by name.
  - **Typed by hand**: an activity typed in the tissue table (dose calibrator) wins over the
    counter, or is not used (still in the side panel, to pick for a cell).
  - **Ranges in**: the bottom and the top of both ranges, from one list — counts (in the
    window in use: the default bottom), counts (whole spectrum: the file's widest window),
    CPM, CPM (whole spectrum), Bq, kBq, MBq (the activity in the vial as counted); the top
    also the dead time (the default). Counts tell how sure a value is (a bottom); the dead time
    or the whole spectrum's CPM how busy the counter was (a top). One top: any but the dead
    time means no dead-time bound.
  - **Valid**: a bottom and a top (0: none) — others are flagged and used only when nothing
    better exists. **Target range**: the same two, stricter — what the rule prefers among the
    valid ones.
  - **Counted more than once**: the first, the last, the most counts, all combined, one round.
  - **Consensus**: leave out a counting out of it; two agree within a % or σ.
  - **Several countings**: weighted by their counts, or their mean.
- **Weighings**
  - **Typed by hand**: a mass typed in the tissue table (paraffin, parafilm) wins over the
    tubes, or is not used.
  - **Weighed more than once**: the first (day-of), the last, the median, the mean.
  - **Consensus**: leave out a weighing out of it; two agree within mg or %.
  - **Weighing correction**: every weighing after the tares (filled tubes, count + weight)
    corrected by its own file's control tubes (scale / offset), or not. The side panel's mass
    table shows each file's control-tube change (⚖ mg; grey when not applied).
- **Activities and dose**: activities at each injection or one time; tail taken off the
  injected activity; **half-lives** — the study's own, saved with it (a new study takes
  Options › Isotopes'). A counter file decay-correcting with another half-life is offered:
  use the file's.

---

## How the numbers are made

**Activity.** The Hidex gives Bq corrected for dead time and normalised to one instant per
file, using the counting efficiency of each energy window (Bq = CPM / 60 / efficiency). A
Wizard2 gives CPM, made Bq with the efficiency typed in Data sources; when its protocol
decay-corrected the CPM, the time it corrected them to is worked out from the vials and
undone (the log says so). BioDist decay-corrects it with the half-life of the animal's isotope (the study's own) to each animal's injection time (or one
time for all). **%IA/g does not depend on that time** — dose and tissue are decayed alike.

**Injected activity** = syringe full − syringe empty − corrections − tail (the card's, else
the counted `tail` vial), each decayed from its own time.

**Mass** = filled tube − empty tube, or the counter's own sample mass if it tared, or a mass
typed by hand. The same tube weighed again later should agree within the balance's ±0.4 mg;
two weighings more than 2 mg and 10 % apart do not agree. The control tubes (`blank`) weighed
empty then filled should not change: when they do, the log says by how much, and the rules
can correct the whole weighing.

```
%IA/g = 100 · A_tissue / (A_injected · m)          SUV = (A_tissue / m) / (A_injected / W)
```

**Repeat countings.** A counting is **valid** with enough counts (≥ 500 by default: ±8 % in
the wide window once its background is off, about the limit of quantification —
`misc/extra/261008_validity_threshold.md`)
and a dead time ≤ 1.5; the **target range** (≥ 10,000, ±1 %; dead time ≤ 1.1) is what the rule
picks from. By default the first counting in it is used — one counting, not an average.
Several combined are weighted by their counts: decay correction scales a value, not how sure
it is. Two valid countings agree within 3 % or 3 σ of their counting statistics — σ from the
counts that are the tissue's own (the counter takes the background off), so a thin late
counting is not held against a good one.

**The consensus.** When more than half of a vial's valid countings (a tube's weighings)
agree, one out of it is flagged — and left out before the rule picks, if the rules say so.

**Blank vials.** A blank that reads background in one round and hot in another held
something else that time (a tail counted later in its slot): left out of the blank, and said.

---

## When something looks wrong

| | |
|---|---|
| Files dropped before the tissue list | they wait: placed as soon as the list is there |
| A file has the wrong kind | set **kind** in Data sources; *(ignored)* to keep it out |
| Vials on the wrong animal or tissue | unfold the file (▸), type the right ones, Tab |
| "placed nowhere" | a vial with no animal or tissue — unfold the file and place it |
| A count is CPM only, no %IA | no counting efficiency for that window: Data sources ▸ efficiencies |
| A value seems off | click it in the Results: every source side by side, why it is flagged |
| An edit went wrong | Ctrl+Z (Ctrl+Y redoes) |
| The study's files moved | found from the study's folder or where they were; else the study's copy (said in the log); a file changed since: you choose |
| "clock change" in the log | a time falls in the hour the clock repeats (October) or skips (March): read as summer time — check it |

---

## Files

- **Reads**: Hidex AMG AutoExport `.xlsx` (tare, weighing, counting, counting + weighing) and
  Wizard2 `.csv`; weighing sheets (`.xlsx`, `.ods`, `.csv`, a balance's `.wt`); a tissue list
  (a file or the clipboard); a study `.json` — BioDist's or InjAct's.
- **Writes**: the study (`.json`, format `biodist-study` 2): animals, tissues, rules, each data
  file's place (as it was, and from the study's folder — so the folder can move with its files),
  its fingerprint and what it says of itself (counter, half-lives, efficiencies), and a copy of
  its data, so the study opens the same when a file is gone. Results as `.xlsx` / `.csv`;
  reports; the options (`biodist_options.json`); a log per session if wished.
- The counter's files are never modified.

---

## Shortcuts

| | |
|---|---|
| Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S | new / open / save / save as |
| Ctrl+R / Ctrl+P | results / report |
| Ctrl+Z / Ctrl+Y | undo / redo (in every window) |
| Ctrl+V | paste a tissue list, or values into a table |
| Ctrl+C, Ctrl+E | copy, export (Results) |
| Ctrl+Shift+N | add an animal |
| F5 | compute again |
| Tab, Enter | along a card's row and on to the next card; down |
| Del | empty the selected cells (a table), remove the selected tissue |

The version is in the window title and on every report.
