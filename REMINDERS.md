# Reminder systém - Instalace a použití

## Instalace databáze

Před spuštěním aplikace je potřeba přidat tabulku `reminders` do databáze. Spusťte následující SQL příkaz:

```sql
CREATE TABLE IF NOT EXISTS `reminders` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `channel_id` varchar(50) NOT NULL,
  `remind_at` datetime NOT NULL,
  `message` text NOT NULL,
  `repeat_type` varchar(100) DEFAULT NULL,
  `active` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;
```

Nebo použijte kompletní `db.sql` soubor, který již obsahuje tuto tabulku.

## Funkce

### Přístup k reminderům

1. V hlavní obrazovce (Home tab) klikněte na menu (⋮)
2. Vyberte **"Upravit události >"**
3. V submenu klikněte na **"Reminders"** → **"Otevřít"**

### Vytvoření nového reminderu

1. V seznamu reminderů klikněte na tlačítko **"Přidat reminder"**
2. Vyplňte formulář:
   - **Kanál**: Vyberte Slack kanál, kam se má reminder poslat
   - **Datum a čas reminderu**: Vyberte datum a čas pomocí datetime pickeru
   - **Zpráva**: Napište text reminderu (může být delší text)
   - **Opakování**: Vyberte typ opakování:
     - **Jednorázově**: Reminder se pošle pouze jednou
     - **Denně**: Reminder se opakuje každý den
     - **Týdně**: Reminder se opakuje každý týden
     - **Měsíčně**: Reminder se opakuje každý měsíc
3. Klikněte na **"Vytvořit"**

### Úprava reminderu

1. V seznamu reminderů klikněte na menu (⋮) u daného reminderu
2. Vyberte **"Upravit"**
3. Upravte potřebné údaje
4. Klikněte na **"Uložit"**

### Smazání reminderu

1. V seznamu reminderů klikněte na menu (⋮) u daného reminderu
2. Vyberte **"Smazat"**
3. Reminder bude okamžitě deaktivován

## Fungování reminders

### Kontrola reminderů

- Remindery se kontrolují **každých 30 minut** (v :00 a :30)
- Aplikace při startu počká na zarovnání na :00 nebo :30 před prvním spuštěním
- Všechny remindery, které mají čas <= aktuální čas, jsou zpracovány

### Opakování

- **Jednorázově**: Po odeslání se reminder deaktivuje
- **Denně**: Po odeslání se čas posune o +1 den
- **Týdně**: Po odeslání se čas posune o +7 dní
- **Měsíčně**: Po odeslání se čas posune o +1 měsíc (při dni > 28 se použije den 28)

### Seznam reminderů

Každý reminder zobrazuje:
- **ID**: Unikátní identifikátor
- **Datum a čas**: Kdy se reminder pošle
- **Typ opakování**: Jednorázově/Denně/Týdně/Měsíčně
- **Kanál**: Kde se reminder pošle
- **Zpráva**: Náhled první části zprávy

## Technické detaily

### Soubory

- `db.sql` - SQL schema včetně tabulky reminders
- `db.py` - Databázové funkce pro práci s remindery
- `reminders.py` - Logika zobrazení a zpracování reminderů
- `bot.py` - Handlery a hlavní reminder loop
- `attendance.py` - Upravené menu pro submenu "Upravit události"

### Databázové funkce

- `add_reminder_to_db()` - Vytvoření reminderu
- `get_all_active_reminders()` - Seznam aktivních reminderů
- `get_due_reminders()` - Remindery k odeslání
- `update_reminder()` - Úprava reminderu
- `delete_reminder()` - Smazání reminderu
- `update_reminder_next_time()` - Aktualizace času pro opakované remindery
- `deactivate_reminder()` - Deaktivace reminderu

### Reminder Loop

- Běží v samostatném background threadu
- Startuje automaticky při spuštění aplikace
- Zarovnává se na :00 a :30 každé hodiny
- Kontroluje databázi každých 30 minut
- Odešle zprávy do příslušných kanálů
- Aktualizuje nebo deaktivuje remindery podle typu opakování

## Řešení problémů

### Reminder se neposlal

- Zkontrolujte, že bot má oprávnění posílat zprávy do daného kanálu
- Zkontrolujte, že `channel_id` v databázi je validní
- Zkontrolujte logy aplikace pro případné chybové hlášky

### Reminder se neopakuje

- Zkontrolujte, že `repeat_type` v databázi není NULL (pro opakované remindery)
- Zkontrolujte, že `active` je 1
- Zkontrolujte, že `remind_at` byl správně aktualizován po odeslání

### Reminder loop neběží

- Zkontrolujte výstup při startu aplikace - měla by se zobrazit zpráva "⏰ Reminder loop aktivován (každých 30 minut)"
- Zkontrolujte logy pro zprávu "Starting reminder loop thread..."
- Zkontrolujte, že aplikace běží (není ukončená)
