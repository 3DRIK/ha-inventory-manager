# Inventory Manager pre Home Assistant

Vlastná HACS integrácia na správu zásob (špajza, chladnička, skrinka, mraznička...).
Ku každej položke: názov, počet, jednotka, voliteľná exspirácia a voliteľný prah
nízkeho stavu. Podporuje ľubovoľný počet vlastných miestností.

Obsahuje:
- backend integráciu (`custom_components/inventory_manager`) s trvalým úložiskom (HA `Store`, JSON v `.storage`)
- servisy pre automatizácie (`inventory_manager.add_item`, `.consume`, `.restock`, ...)
- senzory pre každú miestnosť + globálne senzory (nízky stav, čoskoro exspiruje, exspirované, celkový počet)
- vlastnú Lovelace kartu `inventory-card` (žiadny build krok, číta CSS premenné z tvojej témy → sadne aj na tvoj gradient dashboard)
- eventy na zbernici (`inventory_manager_low_stock`, `inventory_manager_expiring_soon`) na napojenie vlastných notifikácií
- Repair issues (upozornenia priamo v Nastavenia → Systém → Opravy) pri nízkom stave / blížiacej sa exspirácii

## Inštalácia cez HACS

1. HACS → tri bodky vpravo hore → **Vlastné repozitáre**
2. URL tohto repozitára, kategória **Integrácia**
3. Nainštaluj **Inventory Manager**, reštartuj Home Assistant
4. Nastavenia → Zariadenia a služby → **Pridať integráciu** → *Inventory Manager*
5. Zadaj miestnosti oddelené čiarkou (napr. `Špajza, Chladnička, Mraznička, Skrinka`) a počet dní pred exspiráciou, kedy chceš dostať upozornenie

Karta `inventory-card.js` sa registruje automaticky (cez `add_extra_js_url`) — netreba ju
ručne pridávať do Lovelace resources.

### Pridanie karty do dashboardu

```yaml
type: custom:inventory-card
title: Zásoby
```

Karta má taby podľa miestností, tlačidlo `+` na pridanie novej miestnosti, formulár na
pridanie položky a +/− na rýchlu úpravu počtu. Farby berie z CSS premenných HA témy
(`--primary-color`, `--card-background-color`, ...), takže sa automaticky prispôsobí
tvojmu dark gradient dizajnu — ak chceš doladiť detaily (border-radius, akcent),
dá sa to cez `card-mod` rovnako ako pri Bubble Card / button-card.

## Servisy pre automatizácie

| Servis | Popis |
|---|---|
| `inventory_manager.add_item` | pridá položku (name, location, quantity, unit, expiration, threshold, category, notes) |
| `inventory_manager.update_item` | upraví existujúcu položku podľa `item_id` |
| `inventory_manager.remove_item` | odstráni položku |
| `inventory_manager.consume` | zníži počet o `amount` (default 1) |
| `inventory_manager.restock` | zvýši počet o `amount` (default 1) |
| `inventory_manager.add_location` | pridá miestnosť |
| `inventory_manager.remove_location` | odstráni miestnosť (položky sa presunú) |

`item_id` nájdeš v atribútoch senzorov (napr. `sensor.inventory_spajza` →
attribute `items`), alebo cez `sensor.inventory_nizky_stav_zasob` / `..._coskoro_exspiruje`.

## Senzory

- `sensor.<miestnosť>` — počet položiek v danej miestnosti, atribúty: `items`,
  `low_stock_items`, `expiring_soon_items`
- `sensor.nizky_stav_zasob` — globálny počet položiek pod prahom
- `sensor.coskoro_exspiruje` — globálny počet položiek exspirujúcich v rámci nastaveného okna
- `sensor.exspirovane_polozky` — už exspirované položky (diagnostický senzor)
- `sensor.celkovy_pocet_poloziek` — počet všetkých položiek (diagnostický senzor)

## Príklad automatizácie — notifikácia pri nízkom stave

```yaml
automation:
  - alias: "Zásoby - nízky stav"
    trigger:
      - platform: event
        event_type: inventory_manager_low_stock
    action:
      - service: notify.mobile_app_tvoj_telefon
        data:
          title: "Dochádzajú zásoby"
          message: >
            {{ trigger.event.data.items | map(attribute='name') | join(', ') }}
```

## Moje odporúčania a možné vylepšenia

Toto je funkčný základ. Ak by som na tom mal pokračovať, dával by som prioritu takto:

1. **Nákupný zoznam napojený na `todo` entitu.** Keď položka klesne pod prah, automaticky
   ju pridať do `todo.nakupny_zoznam` (natívna HA to-do entita). Je to prirodzené
   rozšírenie `low_stock` eventu, dá sa spraviť čisto ako automatizácia bez zásahu do kódu.
2. **Čiarový/QR kód.** Companion app vie skenovať čiarové kódy a poslať výsledok ako event —
   dá sa napojiť na `inventory_manager.consume`/`restock` cez `item_id` odvodené z kódu,
   uložené napr. v `notes` alebo novom poli `barcode`. Výrazne zrýchli reálne používanie
   pri nákupe/varení.
3. **Predikcia spotreby.** Ukladať históriu `consume` volaní (časová značka + množstvo) a
   počítať priemernú týždennú spotrebu → odhad "dôjde o N dní", nielen statický threshold.
   Dá sa pridať ako `history.jsonl` v store alebo cez recorder.
4. **Repair issue je momentálne jeden spoločný na všetky nízke položky** — dalo by sa
   rozbiť na per-item issues s `is_fixable=True` a tlačidlom "doplniť" priamo v UI.
5. **Import/export.** Servis na export celého inventára do CSV/JSON (zálohovanie,
   preddefinovanie zoznamu po veľkom nákupe) a import naspäť.
6. **Kategórie ako filter v karte**, nielen textový tag — pribudol by druhý riadok tabov
   alebo dropdown filter nad zoznamom položiek.
7. **Zdieľané miestnosti medzi viacerými config entries** nie sú riešené — momentálne je
   to single-instance integrácia (jedna inštancia = jeden spoločný inventár so všetkými
   miestnosťami), čo pre domácnosť dáva zmysel, ale ak by si chcel oddeliť napr.
   "domáca špajza" a "chata", treba by bolo podporiť viac inštancií.

Ak chceš, viem ktorýkoľvek z týchto bodov rovno domodelovať do kódu.

## Štruktúra repozitára

```
ha-inventory-manager/
├── hacs.json
├── README.md
└── custom_components/
    └── inventory_manager/
        ├── __init__.py          # setup, servisy, periodická kontrola, frontend registrácia
        ├── config_flow.py       # setup + options flow (miestnosti, expiry_warning_days)
        ├── const.py
        ├── manifest.json
        ├── sensor.py            # senzory per-miestnosť + globálne
        ├── services.yaml
        ├── storage.py           # HA Store + business logika (CRUD, low-stock, expiring)
        ├── strings.json / translations/{sk,en}.json
        ├── websocket_api.py     # WS príkazy pre kartu
        └── www/
            └── inventory-card.js
```
