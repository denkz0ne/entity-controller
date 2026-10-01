# Task 02 — Configurator information architecture, Slovak copy, and hints

## Goal
Make the controller form understandable without reading source code. A normal motion-light controller should be configurable from the first visible section; advanced concepts should be grouped, collapsed, translated, and explained with short hints.

This task is UX/copy only unless selector changes require data normalization. Do not change FSM semantics here.

## Current RC.3 problems

- The form is split into many technically correct but overly granular sections.
- Several labels expose implementation terminology without explaining the effect (`state_entities`, override, interlock, constraint, backoff).
- Some Slovak strings lack diacritics or use raw English terms inconsistently.
- Select values such as `event`, `duration`, `fixed`, `sunrise`, `sunset`, `on`, `off`, `ignore` should be localized where Home Assistant selector translation APIs allow it.
- Timeouts/delays are presented as raw seconds even where a duration-style selector would be easier.
- `enabled_default` / `stay_mode_default` are creation defaults, while live state is later controlled by native switches. Showing them unchanged during reconfigure is confusing.

## Target section layout

### 1. Základné nastavenie — expanded
Keep the common path visible and short:

- **Názov**
- **Ikona**
- **Spúšťacie entity**
- **Ovládané entity**
- **Čas aktivity** / base delay

A user creating a basic motion-light rule should not need to open any collapsed section.

### 2. Spúšťanie a časovač — collapsed

- Typ spúšťača
- Reset časovača pri uvoľnení duration senzora
- Backoff enable/factor/max

Suggested Slovak labels/hints:

- **Typ spúšťača** — `Udalosť` / `Trvanie`
  - Hint: `Udalosť spustí časovač. Trvanie drží EC aktívny, kým je podmienka aktívna, podľa nastavenia časovača.`
- **Po uvoľnení spúšťača spustiť časovač znova**
  - Hint: `Platí pre typ Trvanie. Po zániku posledného aktívneho spúšťača začne celý čas aktivity odznova.`
- **Adaptívne predlžovanie času**
  - Hint: `Opakované spustenia počas aktivity môžu čas postupne predĺžiť až po nastavené maximum.`

Prefer a native duration selector for human-facing delay/timeout values if it can round-trip cleanly to the stored seconds model. Keep seconds internally if convenient.

### 3. Ručné zásahy a sledovaný stav — collapsed

- Stavové entity
- Blokovať pri ručnom zásahu
- Timeout blokovania

Copy:

- **Stavové entity**
  - Hint: `Voliteľné doplnkové entity, podľa ktorých EC sleduje skutočný stav. Ovládané entity sa sledujú automaticky.`
- **Rešpektovať ručný zásah**
  - Hint: `Ak niekto zmení sledovanú entitu mimo EC, controller prejde do stavu Blokovaný namiesto toho, aby zmenu hneď prepísal.`
- **Automaticky odblokovať po**
  - Hint: `Prázdne/0 = bez automatického timeoutu.`

### 4. Override a Interlock — collapsed
Keep both concepts together but clearly different.

- **Override entity**
  - Hint: `Aktívny override prevezme controller do stavu Override. Použi ho, keď má iný režim dočasne nahradiť bežnú logiku EC.`
- **Blokovacia podmienka (Interlock)**
  - Hint: `Aktívna entita blokuje tento controller. Helper môže byť zdieľaný medzi viacerými controllermi.`

Do not create or own these Helpers. They are entity selectors only.

### 5. Povolené časové okno — collapsed

- Enable
- Start source/time/offset
- End source/time/offset

Copy:

- **Povoliť iba v časovom okne**
  - Hint: `Mimo tohto okna je controller v stave Časovo obmedzený a bežný trigger ho nespustí.`
- Source values: `Pevný čas`, `Východ slnka`, `Západ slnka`.

Make it explicit that this is the **allowed** window, not the blocked window.

### 6. Nočný profil — collapsed
Night profile stays separate because it changes behavior; it does not block EC.

- Enable
- Start/end source/time/offset
- Night delay
- Night ON/OFF service data

Hint on section/enable:
`Nočný profil nemení povolenie controllera. Počas svojho okna môže použiť iný čas aktivity a iné parametre zapnutia/vypnutia.`

### 7. Akcie pri zmene stavu — collapsed, advanced

- Day ON/OFF service data
- Transition behavior fields

Translate behavior choices:
- `on` -> `Zapnúť`
- `off` -> `Vypnúť`
- `ignore` -> `Nerobiť nič`

Add a short section hint:
`Určuje, čo EC urobí pri vstupe do alebo odchode zo stavov. Predvolene zapína pri Aktivácii a vypína pri prechode do Nečinný.`

### 8. Pokročilé mapovanie stavov — collapsed, advanced

- trigger ON/OFF states
- state ON/OFF states
- override ON/OFF states
- ignored state attributes

Hint:
`Použi iba pri entitách, ktorých aktívny stav nie je bežné on/off (napr. playing, home).`

Explicit OFF mappings have a separate runtime-fix task; do not claim they work until Task 06 is merged.

## Creation-only values

`enabled_default` and `stay_mode_default` belong only to controller creation. After creation the live values belong to the native Enabled and Stay Mode switches and are persisted by the runtime.

- Show these defaults only when adding a controller, or otherwise make it unmistakable that they do not directly change the current switch state.
- Reconfigure must not present a field that appears to change live Enabled/Stay state while the runtime silently preserves another value.

## Translation requirements

- Correct Slovak grammar and diacritics everywhere.
- Keep “Entity Controller” and the technical term `EC` as product terminology.
- Avoid unexplained English in user-facing Slovak copy.
- English `strings.json` remains complete and equivalent.
- Add descriptions/hints only where they materially explain behavior; do not add paragraphs below obvious fields such as Name/Icon.
- Reuse the same wording for add and reconfigure flows; avoid duplicated manually drifting translations if the HA structure allows it.

## Acceptance criteria

- Basic controller creation needs only Name, Trigger, Controlled entities, and delay in the expanded section.
- Advanced sections are collapsed.
- Override, Interlock, constraint, blocking, duration mode, backoff, and night profile each have a concise Slovak explanation.
- Selector option labels are localized where supported.
- No raw “seconds” UI for common durations if a native duration selector can be safely used.
- Creation-only defaults are no longer misleading during reconfigure.
- EN and SK translation JSON validate and contain matching keys.
- Config flow tests verify normalized stored data is unchanged or explicitly migrated.

## Relevant source

- `custom_components/entity_controller/config_flow.py`
- `custom_components/entity_controller/strings.json`
- `custom_components/entity_controller/translations/sk.json`
- `docs/configuration.md`
