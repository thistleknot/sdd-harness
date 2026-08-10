# Tasks

## DOING

- [ ] `#1` Build LoRA probe
    - rank-4 on 3090

## PLANNED

- [ ] `#2` Wire 88 advance icons inline in advances reference table
    - Icons extracted to docs/img/advances/. Update gen_reference.py gen_advances() to add Icon column. CSV icon field ICON_ADVANCE_X → slug.

- [ ] `#3` Wire 46 building icons inline in buildings reference table
    - Icons extracted to docs/img/buildings/. Update gen_reference.py gen_buildings() to add Icon column. CSV icon field ICON_IMPROVE_X → slug.

- [ ] `#4` Fix terrain icon extraction and wire inline
    - 0 extracted — check icon column in terrain.csv, case sensitivity on TGA filenames. Also check TILEIMP_ prefix files (36 exist).

- [ ] `#5` Add artifact gem icons to Systems/Artifacts page
    - Use LotR MGGP025-061 gem images. Different colors per sphere. Copy to docs/img/artifacts/ and embed in systems/artifacts.md.

- [ ] `#6` Clean up stray files (test_centaur.png, .bak TGAs)

- [ ] `#7` Verify LotR catalog page renders correctly
    - docs/reference/lotr-catalog.md exists in nav. 458 PNGs in docs/img/lotr/. Should show each in table with LotR unit name.
