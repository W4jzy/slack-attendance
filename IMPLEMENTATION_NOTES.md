# Implementace Reminder systému - Přehled změn

## Vytvořené soubory

### 1. `reminders.py`
Nový modul obsahující kompletní logiku pro práci s remindery:
- Funkce pro vytváření, úpravu a mazání reminderů
- Zobrazení seznamu reminderů
- Modální okna pro přidání a úpravu
- Zpracování reminderů (odesílání zpráv, opakování)

### 2. `REMINDERS.md`
Dokumentace pro uživatele a administrátory:
- Návod k instalaci
- Návod k používání
- Technické detaily
- Řešení problémů

### 3. `add_reminders_table.sql`
SQL skript pro přidání tabulky reminders do existující databáze

## Upravené soubory

### 1. `db.sql`
- ✅ Přidána tabulka `reminders` s indexy a auto_increment

### 2. `db.py`
- ✅ Přidáno 8 nových funkcí pro práci s remindery:
  - `add_reminder_to_db()` - Vytvoření reminderu
  - `get_all_active_reminders()` - Seznam aktivních reminderů
  - `get_due_reminders()` - Remindery k odeslání
  - `update_reminder_next_time()` - Aktualizace času opakování
  - `deactivate_reminder()` - Deaktivace reminderu
  - `delete_reminder()` - Smazání reminderu
  - `load_reminder_from_db()` - Načtení jednoho reminderu
  - `update_reminder()` - Úprava reminderu

### 3. `attendance.py`
- ✅ Změněno menu "Upravit události" → "Upravit události >" (indikace submenu)
- ✅ Přidána nová funkce `show_edit_events_menu()` pro zobrazení submenu s možnostmi:
  - Přidat událost
  - Seznam událostí
  - Reminders (nová funkce)

### 4. `bot.py`
- ✅ Přidán import `threading`, `time` a `timedelta`
- ✅ Přidán import `from reminders import *`
- ✅ Inicializace globálního loggeru pro reminder loop
- ✅ Aktualizován `MENU_ACTIONS` o nové akce:
  - `go_to_edit_events_menu` - Zobrazení submenu
  - `go_to_reminders` - Zobrazení seznamu reminderů
- ✅ Přidány nové handlery:
  - `@app.action("go_to_edit_events_menu")` - Handler pro submenu
  - `@app.action("go_to_reminders")` - Handler pro seznam reminderů
  - `@app.action("open_add_reminder_modal")` - Handler pro otevření modalu
  - `@app.view("add_reminder_modal")` - Handler pro vytvoření reminderu
  - `@app.action(reminder_overflow)` - Handler pro menu u reminderu
  - `@app.view(edit_reminder)` - Handler pro úpravu reminderu
- ✅ Přidán reminder loop:
  - `wait_for_30min_alignment()` - Čeká na zarovnání na :00 nebo :30
  - `reminder_loop_thread()` - Hlavní loop kontrolující remindery
  - `start_reminder_loop()` - Spouští reminder loop v threadu
  - Automatické spuštění při startu aplikace

## Struktura menu

```
Hlavní menu (overflow)
├── Obnovit
├── Upravit události > ← ZMĚNĚNO (přidána šipka)
│   ├── Přidat událost ← PŘESUNUTO sem
│   ├── Seznam událostí (zobrazí existující události)
│   └── Reminders ← NOVÉ
│       ├── Přidat reminder
│       └── Seznam reminderů (s možností upravit/smazat)
├── Upravit docházku
├── Vyplnit hromadně
└── Upravit nastavení
```

## Funkce reminders

### Typ opakování
- **Jednorázově** (`once` / `NULL`) - Pošle se jednou a deaktivuje se
- **Denně** (`daily`) - Opakuje se každý den (+1 den)
- **Týdně** (`weekly`) - Opakuje se každý týden (+7 dní)
- **Měsíčně** (`monthly`) - Opakuje se každý měsíc (+1 měsíc)

### Reminder Loop
- Běží v samostatném background threadu
- Kontrola každých **30 minut** (v :00 a :30)
- První spuštění čeká na zarovnání času
- Zpracování všech reminderů s `remind_at <= NOW()`
- Automatické aktualizace pro opakované remindery

## Instalace

1. **Databáze**: Spusťte `add_reminders_table.sql` nebo použijte aktualizovaný `db.sql`
2. **Restart aplikace**: Aplikace automaticky startuje reminder loop
3. **Přístup**: Hlavní menu → Upravit události → Reminders

## Testování

### Vytvoření testovacího reminderu
1. Otevřete menu Reminders
2. Klikněte "Přidat reminder"
3. Vyberte kanál (např. #general)
4. Nastavte čas za 1-2 minuty
5. Napište zprávu "Test reminder"
6. Vyberte "Jednorázově"
7. Klikněte "Vytvořit"

### Ověření funkčnosti
- Reminder se zobrazí v seznamu
- Po uplynutí času (+ max 30 min na další kontrolu) by se měla zpráva poslat
- Reminder by se měl deaktivovat (zmizet ze seznamu)

## Kompatibilita

- ✅ Používá stejný databázový přístup jako zbytek aplikace
- ✅ Stejný styl UI/UX jako existující funkce
- ✅ Konzistentní error handling
- ✅ Logování všech operací
- ✅ Graceful shutdown při ukončení aplikace

## Poznámky

- Reminder loop běží asynchronně v background threadu
- Při ukončení aplikace (Ctrl+C) se reminder loop ukončí gracefully
- Všechny chyby se logují, ale nezastaví hlavní aplikaci
- Channel ID je Slack channel ID (vybírá se z dostupných kanálů)
