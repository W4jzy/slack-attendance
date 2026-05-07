# Implementace Sdílení Událostí v Reminders

## Co bylo implementováno

Reminder systém byl rozšířen o možnost automatického sdílení událostí do Slack kanálů.

## Změny v databázi

Spusťte SQL skript pro přidání nových sloupců:

```bash
mysql -u your_user -p attendance < alter_reminders_table.sql
```

Přidané sloupce do tabulky `reminders`:
- `reminder_type` - Typ reminderu ('message' nebo 'share_events')
- `days_ahead` - Kolik dní dopředu hledat události (pro share_events typ)
- `event_type_filter` - Filtr typu události (zatím nepoužito, připraveno pro budoucí rozšíření)

## Jak to funguje

### Typy reminderů

1. **Zpráva** (`message`)
   - Pošle jednoduchou textovou zprávu do kanálu
   - Funguje stejně jako před úpravou

2. **Sdílet události** (`share_events`)
   - Najde všechny události v konkrétní den
   - Den je vypočítán jako: `remind_at + days_ahead`
   - Pro každou nalezenou událost pošle samostatnou zprávu s detaily
   - Pokud nejsou žádné události, pošle custom text ze pole "Zpráva"

### Příklad použití

**Týdenní reminder na páteční události:**
1. Typ: "Sdílet události"
2. Kanál: #general
3. Datum a čas: Každé pondělí 8:00
4. Dny dopředu: 4 (pondělí + 4 dny = pátek)
5. Zpráva: "Tento týden nejsou naplánované žádné události"
6. Opakování: Týdně

**Výsledek:**
- Každé pondělí v 8:00 se reminder podívá na páteční události
- Pokud jsou události, sdílí je do #general s detaily
- Pokud nejsou, pošle zprávu "Tento týden nejsou naplánované žádné události"

**Ranní reminder na dnešní události:**
1. Typ: "Sdílet události"
2. Kanál: #treninky
3. Datum a čas: Každý den 7:00
4. Dny dopředu: 0 (dnes)
5. Zpráva: "Dnes není naplánovaný trénink"
6. Opakování: Denně

## UI Změny

### Modal pro přidání/editaci reminderu

Obsahuje nová pole:
- **Typ reminderu** - Radio buttons (Zpráva / Sdílet události)
- **Dny dopředu** - Number input (0-30 dní)
  - Hint: "Kolik dní dopředu hledat události ke sdílení"
- **Zpráva** - Dvojí účel:
  - Pro "Zpráva": celý text zprávy
  - Pro "Sdílet události": text když nejsou žádné události

### Seznam reminderů

Zobrazuje:
- Ikona typu: 💬 pro zprávy, 📅 pro sdílení událostí
- Typ: "Zpráva" nebo "Sdílet události"
- Days ahead: Zobrazuje "+Xd" pokud > 0

Příklad:
```
✅ ID 5 📅 Sdílet události (+4d)
📅 14.05.2026 08:00 | 🔁 Týdně | 📢 #general
💬 _Tento týden nejsou naplánované žádné události_
```

## Zpracování Reminderů

Funkce `process_due_reminders()` v `reminders.py`:

1. Načte všechny remindery které mají `remind_at <= NOW()` a `active = 1`
2. Pro každý reminder:
   - **message type**: Pošle zprávu do kanálu
   - **share_events type**:
     - Vypočítá target_date = remind_at + days_ahead
     - Načte události na ten den z databáze
     - Pokud jsou události: sdílí každou samostatně
     - Pokud nejsou: pošle custom message
3. Aktualizuje nebo deaktivuje reminder podle `repeat_type`

## Formát sdílené události

```
📅 *Název události*

📍 Adresa (nebo "Adresa není specifikována")
🕐 Začátek: DD.MM.YYYY HH:MM
🕑 Konec: DD.MM.YYYY HH:MM
🏷️ Typ: Trénink/Turnaj/Ostatní

_Custom zpráva z reminderu_

_Automatický reminder_
```

## Soubory upravené

### Databáze
- `alter_reminders_table.sql` - SQL skript pro úpravu tabulky

### Backend (db.py)
- `add_reminder_to_db()` - Přidány parametry reminder_type, days_ahead
- `get_all_reminders()` - Vrací nové sloupce
- `get_due_reminders()` - Vrací nové sloupce
- `load_reminder_from_db()` - Vrací nové sloupce
- `update_reminder()` - Aktualizuje nové sloupce

### Reminders (reminders.py)
- `build_add_reminder_modal()` - Přidána pole pro typ a days_ahead
- `build_edit_reminder_modal()` - Přidána pole pro typ a days_ahead
- `build_reminders_list_view()` - Zobrazuje typ a days_ahead
- `process_due_reminders()` - Rozšířeno o zpracování share_events typu

### Bot handlers (bot.py)
- `handle_add_reminder_submission()` - Extrahuje reminder_type a days_ahead
- `handle_edit_reminder_submission()` - Extrahuje reminder_type a days_ahead

## Testing

1. Spusťte SQL skript
2. Restartujte bot
3. Vytvořte testovací reminder typu "Sdílet události":
   - Nastavte na dnešní datum + pár minut
   - Days ahead: 0
   - Vytvořte testovací událost na dnes
4. Počkejte až reminder vyprší (zarovnává se na :00 a :30 minut)
5. Zkontrolujte zda byly události sdíleny do kanálu

## Poznámky

- Reminder loop běží každých 30 minut (zarovnáno na :00 a :30)
- Všechny události v daný den jsou sdíleny (bez filtru typu)
- Každá událost je sdílena jako samostatná zpráva
- Footer zprávy obsahuje "_Automatický reminder_" místo jména odesílatele
