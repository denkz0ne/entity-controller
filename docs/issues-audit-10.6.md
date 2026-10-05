# Audit issues pre 10.6

## Výsledná implementácia

Stav po implementácii 2026-10-05; finálny GitHub beh a SHA sú evidované
v release notes v10.6.0 a PR #33. Nasledujúci pôvodný audit je historický
záznam pred implementáciou, vrátane vtedajších počtov a chýbajúcich funkcií.

| Issue | Implementované | Regresie |
| --- | --- | --- |
| #14 | Samostatné presence ON/OFF mapovania, ANY hold, posledné OFF spustí celý delay, priority a hot reconfigure | `test_light_profile_restore.py`, `test_reconfigure.py`, model/config flow |
| #15 | Manuálne ON/atribúty a OFF samostatne, release po vyprázdnení, fresh trigger, EC kontext medzi entries, metadata bez takeover | Profile tests: manual session, idle ON, two outputs, flags, meaningful attributes |
| #16 | Restore/Custom, natívne HA sekvencie, scény, snapshot, cancel, izolácia chýb, migrácia OFF hooku, diagnostika | `test_lifecycle.py`, profile restore, migration, diagnostics |
| #17 | Basic filtre a Full escape hatch, capability intersection, jas/Kelvin/farba/efekt/transition/fan, day/night a legacy dáta | Browser capabilities/legacy/parameters; backend mixed domains/fan/errors |
| #18 | Basic/Full integruje #14–17; jediný model, explicitný Save/Close, validácia a bezpečný hot apply | Browser save/schema/revisions; config flow/panel/reconfigure |
| #24 | Prvý klik, live refresh bez odpojenia editora, draft/search/details, × bez zbalenia, error/revision ochrana | Browser pending render, failed save, authoritative response, remove/add |
| #25 | Kompaktné biele karty, priehľadný canvas, decision live/draft, otázniky pre klik/tap/keyboard; grid ≤550 px pri 1600 px | Browser layout 320/390/768/1600, mobile help, countdown popover |
| #26 | Vyhľadávanie pri písaní, friendly name/ID, empty result, šípky/Enter/Escape, chips, natívny icon selector a retry | Browser search/keyboard/native loader/icon |
| #27 | Spoločný interval, HA astral, okamžitý solar/offset preview, presné minúty, ±15 min/±12 h, drag→fixed, live solar refresh | Browser schedule/night/overnight/preview; panel/schedule backend |

Release gate je úspešný finálny commit v oboch GitHub joboch `tests` a
`panel-browser`. Browser testy používajú izolovaný panel a adapter natívnych HA
komponentov; nepreukazujú ovládanie fyzických svetiel ani prihlásený používateľov
HA. Používateľ požaduje testovanie na GH; inštalácia ani reštart jeho HA sa nerobia.
Obmedzenia OFF restoration sú v `temporary-light-profiles.md`. HACS 2.0.5 stále
ignoruje lokálnu HA značku; externý brands CDN je samostatné upstream obmedzenie.

## Pôvodný audit pred implementáciou

Audit z 2026-10-05 zahŕňa **všetkých 9 otvorených issues** repozitára
`denkz0ne/entity-controller`: #14, #15, #16, #17, #18, #24, #25, #26 a #27.
Zdroj: aktuálne telá issues získané cez GitHub CLI; stav kódu: pracovný checkout
`entity-controller-issues-work`. Posudzuje sa celé zadanie, nie iba podobný názov
ovládacieho prvku. Prečítanie existujúceho testu nie je dôkaz jeho úspešného behu.
Tento audit testy nespúšťal a nepotvrdzuje nasadenie ani správanie v živom HA.

## Platné rozhodnutie o ukladaní

Používateľ výslovne požaduje **Uložiť / Zavrieť**. Formulácie o automatickom
ukladaní v #18, #24, #26 a #27 sú týmto rozhodnutím nahradené. Zmena poľa mení
lokálny návrh; iba Uložiť odosiela konfiguráciu. Zavrieť zachová návrh na opätovné
otvorenie. Chýbajúci autosave preto nie je otvorená chyba. Stabilita, overená
odpoveď servera, ochrana novšieho návrhu a jasná chyba zostávajú požiadavkami.

## Súhrn

| Issue | Stav celého zadania | Existujúci základ | Čo zostáva |
| --- | --- | --- | --- |
| [#14](https://github.com/denkz0ne/entity-controller/issues/14) | Chýba | Viac triggerov a event/duration režimy | Samostatné presence/hold entity, ANY hold, timer release, mapovanie, diagnostika, UI a testy |
| [#15](https://github.com/denkz0ne/entity-controller/issues/15) | Čiastočne | ContextTracker, manual_control príčina, BLOCKED ochrana | Manual OFF/ON/atribúty ako samostatná vlastnícka relácia a odblokovanie po vyprázdnení |
| [#16](https://github.com/denkz0ne/entity-controller/issues/16) | Čiastočne | Enter/exit hooky, ON/OFF/IGNORE a bezpečný reconcile | Lifecycle model, restore snímka, scény, natívne HA sekvencie, migrácia a diagnostika |
| [#17](https://github.com/denkz0ne/entity-controller/issues/17) | Čiastočne | Základné filtre/chips, denné/nočné service data | Capability intersection, svetelné ovládače, adapter, bezpečné zmiešané domény, advanced escape hatch |
| [#18](https://github.com/denkz0ne/entity-controller/issues/18) | Čiastočne | Inline editor Basic/Full, admin save API, hot apply, intervaly | Integrácia #14–17; všetky supported advanced polia a úplné UX kritériá |
| [#24](https://github.com/denkz0ne/entity-controller/issues/24) | Čiastočne; stabilizačný základ implementovaný | Explicit save, server form response, revisions, zachovanie editora, browser regresie | Širšie interakcie pod live refresh a reálny HA save/reload gate |
| [#25](https://github.com/denkz0ne/entity-controller/issues/25) | Čiastočne | Responsive grid, ľahký canvas, Basic a advanced skupiny | Dokončenie kompaktných pokročilých polí, tooltipov a hierarchie; závislé features podľa #14–17 |
| [#26](https://github.com/denkz0ne/entity-controller/issues/26) | Čiastočne | Vizuálny icon picker, chips, normalizované live vyhľadávanie | Rozsah ikon, prázdny výsledok, klávesnica, presné filtre a stabilita na živom HA |
| [#27](https://github.com/denkz0ne/entity-controller/issues/27) | Čiastočne | Spoločný interval, HA solar resolution, drag→fixed, ±15 min kroky | Okamžitý solar/offset preview návrhu, presné časy a DST/day-refresh regresie |

**Počet pri audite: 0 hotových celých issues, 8 čiastočných, 1 chýbajúce.**
Pracovné zmeny označené nižšie ako rozpracované sa nesmú zameniť za overené
splnenie všetkých acceptance criteria.

## Dôkazy a zostávajúce kroky

### #14 — Presence/hold

`model.py::ControllerConfig` obsahuje `trigger_entities` a `sensor_type`, ale
nemá samostatné presence entity/mapovanie. `manager.py` odoberá trigger/state/
override/interlock zmeny; `controller.py` nemá presence hold ani post-clear delay.
`test_manager.py::test_one_trigger_turning_off_keeps_duration_controller_active`
overuje agregáciu triggerov; **nie** nezávislé hold senzory, ktoré nesmú aktivovať.
Ani Advanced picker nesmie prezentovať trigger ako náhradu tejto funkcie.

Implementovať samostatný model a odber zmien, ANY-active agregáciu, odloženie
ACTIVE timer expiry bez opakovaného timer churn, delay od posledného presence OFF,
priority disabled/constrained/override/interlock/manual a hot reconfigure.
Pridať UI/SK/EN, diagnostiku, migráciu s prázdnym predvoleným zoznamom a všetkých
deväť scenárov z issue. Toto je závislosť deterministického release v #15.

### #15 — Manuálne prevzatie

`context.py::ContextTracker` rozpoznáva EC a child contexts; `test_context.py`
obsahuje príslušné testy. `controller.py::async_handle_state_entity_change`
ignoruje vlastný context; externé ON počas ACTIVE_TIMER vedie do BLOCKED,
externé OFF v kontrolovanom stave vedie do IDLE. OFF→IDLE tým ešte nedokazuje
ochranu proti ďalšiemu PIR. `manager.py::_only_ignored_attributes_changed`
filtruje explicitne ignorované atribúty, ale nie domain-specific significant set.
`test_controller_fsm.py::test_manual_state_change_while_active_enters_blocked`
a `test_manager.py::test_ignored_attribute_only_change_does_not_block_controller`
pokrývajú iba základ.

Chýba rozlíšenie manual_off/manual_on/manual_attribute_change, explicitná
vlastnícka relácia a jej timestamps, ochrana významných light zmien bez metadata
false positives, predvídateľné release po skončení trigger/presence session a
inter-controller ochrana. Rozpracované backend zmeny k manuálnej ochrane sa majú
znovu posúdiť proti všetkým desiatim scenárom issue; samotný nový boolean alebo
BLOCKED stav celé issue neuzatvára.

### #16 — Lifecycle a restore

`model.py::TransitionBehavior` a `DEFAULT_TRANSITION_BEHAVIORS` definujú hooky.
`controller.py::async_transition` spúšťa enter/exit; prechod medzi dvoma ACTIVE
variantmi neopakuje aktiváciu. `manager.py::_async_execute_behavior` v auditovanom
základe spracúva iba ON/OFF: enum CUSTOM sám o sebe nemá action sequence engine.
`actions.py` obsahuje služby aktivácie/blokovania/stay/night, nie lifecycle scény.
`ReconcileSnapshot` je snímka runtime podmienok, **nie** stavov svetiel pred EC.

`test_controller_fsm.py::test_stay_mode_entry_does_not_replay_active_behaviors`,
`test_stay_mode_exit_does_not_replay_active_behaviors`,
`test_reconcile_to_idle_does_not_run_enter_idle_action` a
`test_reconfigure.py::test_reconfigure_does_not_execute_idle_off_behavior`
dokladajú ochranu pred side effects pri reconcile.

Rozpracované restore zmeny musia zachytiť snímku presne raz pred vlastníctvom EC,
obnovovať svetlá podľa podporovaných on/off/brightness/color atribútov, izolovať
nedostupných súrodencov a neobnovovať cez aktívne manuálne prevzatie. Zostávajú
scény/natívne action sekvencie, validačný a migračný kontrakt, skutočný lifecycle
UI a last-action/result/snapshot/exit-policy diagnostika. `docs/actions.md`
zatiaľ popisuje kompatibilné runtime služby; obsah restore/scén treba doplniť.

### #17 — Domény a svetelné nastavenia

`www/entity-controller-panel.js::_editor` používa entity chips a filtre domén.
`renderField` ponecháva široké filtre pre pokročilé state mapping use cases.
`config_flow.py::CONTROLLER_SCHEMA` má natívne EntitySelector bez doménového
filtra v common trigger/control poliach. Service-data JSON žije v Advanced;
to ešte nevytvára friendly capability-aware light settings.

`manager.py::_async_execute_behavior` v základe zoskupuje entity podľa domény,
ale pridáva rovnaké `service_data` do každej domény. Zmiešané light+switch tak
potrebujú oddeliť light-only parametre. Existujúci
`test_manager.py::test_night_profile_uses_its_delay_and_service_data` potvrdzuje
night profil, nie capability intersection ani bezpečné mixed-domain payloady.

Root rozpracováva grafické denné/nočné parametre. Pred označením hotové treba
overiť jasné capability intersection, brightness-only/color-temp/RGB/effect
prípady, switch-only UI, neavailable zachovanie konfigurácie, advanced escape
hatch a jednotnú adapter vrstvu s #15/#16. Pridať testy desiatich scenárov issue,
SK/EN a normalized effective output diagnostics.

### #18 — Inline Basic/Full konfigurátor

`panel.js::_editor`, `_handleClick`, `_saveController` poskytujú gear, jeden
otvorený editor, Basic/Full a explicitné Uložiť/Zavrieť.
`panel.py::async_handle_panel_save` overuje admin, validuje cez
`CONTROLLER_SCHEMA`, zapisuje existujúcu ConfigEntry/Subentry, hot-applies
konfiguráciu a vracia autoritatívny form; nevzniká paralelný settings store.

`test_panel_browser.py::test_admin_config_panel_switches_modes_and_saves_explicitly`,
`test_editor_waits_for_explicit_save_and_has_manual_duration_input`,
`test_close_reopen_is_single_click_and_preserves_unsaved_draft` a
`test_saved_editor_payload_passes_ha_schema_without_changing_other_settings`
pokrývajú shell a nový save kontrakt. Backend hot reconfigure pokrýva
`test_reconfigure.py`, vrátane listener changes a safe idle reconcile.

Celé issue obsahuje presence, manuálne session semantics, lifecycle restore/
scene/action a capability controls z #14–17; preto je stále čiastočné. Name a
assignment zostávajú vo vnútri editora; zvážiť reuse status-row povrchov bez
duplicity. Full mode nesmie stratiť už podporované `on_enter_active`/
`on_exit_active`, keď Basic zobrazí iba dva zjednodušené action selectory.

### #24 — Stabilita editora a uloženia

`panel.js::_saveController` blokuje súbežný save jedného controllera,
porovnáva `_draftRevision`, prijíma server `form`/identity/resolved schedule a
pri zlyhaní zachová návrh s lokálnou chybou. `_render` zachováva pripojený editor
pri runtime aktualizáciách. Explicitné ukladanie odstránilo pôvodný autosave
queue závod; starší response nesmie vymazať novšie lokálne zmeny.

Konkrétne regresie v `test_panel_browser.py`:
`test_explicit_save_uses_authoritative_response_without_full_panel_reload`,
`test_failed_save_keeps_draft_and_reports_backend_error`,
`test_invalid_json_stops_save_before_websocket_submission`,
`test_save_response_preserves_new_edits_and_updates_current_controller`,
`test_first_save_click_survives_pending_render_from_live_update`,
`test_editor_picker_survives_runtime_refresh_and_normalizes_search`.
`docs/editor-save-review.md` uvádza rozsah predchádzajúcej opravy a výslovne
odlišuje schema test od skutočného save na používateľovom HA.

Dokončiť explicitnú regresiu multi-add→Save→fresh reload, remove→Save→reload,
rozbalené details a caret/list scroll pri opakovaných live aktualizáciách,
range drag počas refresh a validáciu na skutočnom HA. Root rozpracováva
zachovanie details; audit túto zmenu ešte nepovažuje za nasadenú alebo overenú.

### #25 — Hierarchia a kompaktnosť

`panel.js::_editor` má funkčné Basic skupiny, oddelené rules a Full details;
CSS používa HA theme variables, container responsive layout a kompaktný canvas.
`test_panel_browser.py::test_compact_editor_and_help_fit_panel_width` a
`test_mobile_help_opens_by_tap_without_changing_draft` poskytujú browser coverage
šírok a dotykových help ovládačov. `test_removing_rule_entity_keeps_rules_and_other_sections_open`
je pracovná regresia zachovania sections.

Root rozpracováva menšie Advanced polia a tooltips namiesto dlhých help textov,
zachovanie details a Basic decision summary. Celé issue vyžaduje tiež správne
poradie/grouping po pridaní #14–17, logické explicit mappings, samostatnú
monitoring/manual protection skupinu a overenie theme/mobile. Skontrolovať
reálny screenshot pri 1/2/3 stĺpcoch, dlhých názvoch, dark theme a veľkom zozname.

### #26 — Ikony a entity picker

`panel.js::_editor::entityPicker` zobrazuje friendly names/entity IDs a omieta
už zvolené entity. `_handleEditorInput` normalizuje diakritiku a tokeny; vyhľadáva
pri písaní. `test_editor_picker_survives_runtime_refresh_and_normalizes_search`
overuje `obyvacka poh`, zachovanie query a obnovenie výsledkov po vymazaní.
`test_controller_icon_is_selected_from_searchable_visual_picker` overuje click
na controller avatar, vizuálny výber a absenciu raw icon text poľa.

Icon picker v základe používa krátky pevný zoznam MDI ikon; nejde o prehliadanie
všetkých dostupných MDI/HA packs. Chýba zdokumentované overenie stabilného HA
selector API, explicitné oznámenie nulových výsledkov po query, Escape a arrow/
Enter navigation. Filtre treba zosúladiť s #17 a pokryť entity-ID search,
multi-add/remove s potvrdeným save a úplné keyboard/mobile scenáre.
Root rozpracováva CSS `[hidden]` opravu: `hidden` atribút musí aj pri author
`display` CSS skutočne odstrániť nezodpovedajúce výsledky z vizuálneho zoznamu.

### #27 — Intervaly a solar preview

`panel.js::_editor::schedule` je spoločný constraint/night renderer s wrap-fill
pre interval cez polnoc. `_updateDraftField` pri drag mení source na fixed a
nuluje offset; `_handleClick` používa ±15 min a clamp ±720 min. Štyri offset
polia sa nezobrazujú ako duplicate advanced inputs. Night toggle odhaľuje
kompletný schedule a duration editor.

`panel.py::_resolved_schedule` používa HA `get_astral_event_date` a lokálny deň;
`test_panel.py::test_resolved_schedule_uses_home_assistant_sun_time_and_configured_offset`
potvrdzuje backend výpočet. Browser regresie:
`test_schedule_range_displays_and_saves_an_overnight_window`,
`test_enabling_night_profile_reveals_valid_controls_and_keeps_duration`,
`test_dragging_solar_schedule_endpoint_switches_to_fixed_time`,
`test_solar_offset_uses_fifteen_minute_steps_once_in_basic_mode`.

**Zostávajúca chyba v auditovanom základe:** source change a offset step menia
návrh, ale handle číta `controller.resolved_schedule[prefix][side]` zo starého
uloženého endpointu. Fixed→sunrise, sunrise→sunset alebo +15 min preto nezískajú
správny okamžitý preview pred Save. Backend potrebuje nezapisujúci resolver
návrhu alebo payload oboch solar základov s dátumom/timezone; frontend nemá
odhadovať astronomy. Presné resolved minúty sa tiež zobrazujú v range so
`step=15`, čo môže snapnúť handle na iný čas než output. Odlišovať presnú
resolved pozíciu od krokovania manuálneho drag.

Doplniť source-switch preview, okamžitý offset preview, plus/minus limity,
disable/re-enable retention, current-day/DST/timezone a drag počas refresh.
Denná aktualizácia musí obnoviť semantic endpoint bez prepísania source; backend
astral výpočet sám nedokazuje, že otvorený editor túto aktualizáciu uvidí.

## Poradie realizácie

1. **#24 stability gate:** zachovať draft/details/search pri runtime refresh;
   overiť Save/Close, normalized response a save/reload kontrakt na HA.
2. **#26 a #27 existujúce chyby:** vizuálne skrytie výsledkov, explicitné empty
   state/keyboard a nezapisujúci solar/offset preview. Sú nezávislé od nových FSM
   vlastností a nesmú vyžadovať návrat autosave.
3. **#14 presence model:** nezávislé activation/hold, časovače a diagnostika.
4. **#15 ownership/manual session:** významné domain atribúty a release podmienka
   zahŕňajúca #14. Neuvoľňovať manuálnu ochranu len krátkym timerom pri obsadení.
5. **#16 lifecycle:** snapshot/restore s ownership z #15; scény/actions,
   izolované chyby entity, migrácia a diagnostika. Základ restore možno vyvíjať
   paralelne, ale release musí prejsť spoločnými ownership scenármi.
6. **#17 adapters a output controls:** capability intersection, mixed domains,
   denné/nočné friendly parametre a Full fallback. Zdieľať adapter s #15/#16.
7. **#18 + #25 integrácia:** doplniť UI všetkých podporovaných features, logické
   Advanced skupiny, Basic decision, SK/EN, dokumentáciu/changelog a vizuálne HA
   dôkazy. Čiastkové polish zmeny môžu ísť skôr; celé issues zavrieť až po dependents.

## Release a správa issues

Každé issue má zostať otvorené, kým chýbajúce acceptance body nemajú implementáciu,
relevantné regresie, GitHub Actions dôkaz a pri UI skutočný HA výsledok. Tento
audit nepridal GitHub komentáre ani issues nezatváral. Zmeny práve rozpracované
v shared checkout treba po dokončení znovu posúdiť a upraviť túto tabuľku; názov
verzie 10.6 ani existujúci zelený build samy o sebe nesplnia celé issue.
