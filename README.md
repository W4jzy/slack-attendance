# Slack Attendance

Slack aplikace pro události, docházku, administrátorské opravy, historii, CSV export
 a připomínky. Běží jako jeden Python proces v Socket Mode s MariaDB/MySQL.
Webserver, doména ani příchozí HTTP port nejsou potřeba.

## Slack aplikace

1. Na https://api.slack.com/apps vytvoř aplikaci **From a manifest** a vlož
   [slack-manifest.yaml](slack-manifest.yaml).
2. V **Basic Information → App-Level Tokens** vytvoř token s `connections:write`
   (`xapp-…`). Nainstaluj aplikaci do workspace a zkopíruj bot token (`xoxb-…`).
3. Vytvoř Slack user group pro správce, přidej do ní správce a zjisti její ID
   pomocí `python usergroups.py` po vyplnění bot tokenu.
4. Vyplň tokeny do `.env` a ID skupiny do `[settings] admin_group` v `config.ini`.
   Na serveru použij cesty uvedené níže. Pozvi bota do kanálů, kam má sdílet události.
5. Otevři aplikaci ve Slacku a její záložku Home.

Manifest zahrnuje `im:write` pro otevření DM při exportu a `groups:read` pro seznam
soukromých kanálů dostupných botovi; původní návod tato oprávnění neobsahoval.
Viz [conversations.open](https://docs.slack.dev/reference/methods/conversations.open/)
a [conversations.list](https://docs.slack.dev/reference/methods/conversations.list/).

## Lokální spuštění

Python 3.11+ a dostupná MariaDB/MySQL. Příklady jsou pro Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
cp config.ini.example config.ini
```

Ve Windows aktivuj `.venv\Scripts\Activate.ps1` a použij `Copy-Item` místo `cp`.
Vyplň konfiguraci, vytvoř databázi a účet (SQL příklad níže) a spusť:

```bash
python manage.py migrate
python manage.py check
python bot.py
```

Na Linuxu nastav `TZ=Europe/Prague`, případně nastav systémové časové pásmo.
Aplikace pracuje s místními časy. `ATTENDANCE_CONFIG` a `ATTENDANCE_ENV` mohou
odkazovat na jiné konfigurační soubory; výchozí jsou vedle zdrojových souborů.
`check` kontroluje konfiguraci, databázové sloupce a dokončené migrace,
neověřuje tokeny proti Slack API.

## První instalace serveru

Určeno pro Debian 12+/Ubuntu 24.04+ s MariaDB a systemd. Repozitář umísti například
 do `/opt/slack-attendance/app`, s právem čtení a průchodu pro službu.
Checkout a virtuální prostředí spravuje root; služba běží jako `slack-attendance`.

```bash
cd /opt/slack-attendance/app
sudo bash deploy/install.sh
```

První spuštění nainstaluje balíčky, Python prostředí, služební účet a vytvoří:

- `/var/lib/slack-attendance/.env` – Slack tokeny.
- `/var/lib/slack-attendance/config.ini` – administrátorská skupina, texty a databáze.

Skript skončí s výzvou k vyplnění těchto souborů. Neupravuj produkční konfiguraci
v checkoutu. Pro převzetí staré instalace zkopíruj hodnoty ze stávajících souborů,
včetně původního názvu databáze a účtu; existující data zachovej.
Potom pro novou lokální databázi spusť:

```bash
sudo bash deploy/install.sh --create-database
```

Volba `--create-database` vytvoří databázi a účet podle konfigurace pomocí MariaDB
root socket autentizace. Existující databázi nemaže a existujícímu účtu nemění heslo.
Pro už připravenou nebo vzdálenou databázi tuto volbu vynech.
`--skip-packages` přeskočí apt; ostatní potřebné nástroje už musejí být nainstalované.

Skript zazálohuje databázi i konfiguraci, provede migraci a kontrolu, nainstaluje
systemd službu a zapne start po restartu serveru. Při chybě po zastavení služby
ponechá službu zastavenou; postupuj podle logu a části Obnova.

Alternativní ruční příprava databáze (`sudo mariadb`; heslo nahraď vlastním):

```sql
CREATE DATABASE attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_czech_ci;
CREATE USER 'attendance'@'localhost' IDENTIFIED BY 'REPLACE_WITH_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON attendance.* TO 'attendance'@'localhost';
```

Pro tento účet nastav `host=localhost`. U vzdálené databáze připrav účet a přístup
na jejím serveru. Pro automatické zálohy je na aplikačním serveru potřeba
`mariadb-dump` a databázový účet s oprávněním číst celé aplikační schéma.

## Aktualizace

Změny nejdříve commitni a pushni na větev používanou serverem. Na serveru musí být
čistý Git checkout a funkční přístup k `origin` pro uživatele, který deploy spouští:

```bash
cd /opt/slack-attendance/app
sudo bash deploy/deploy.sh
```

Deploy zamkne souběžné nasazení, stáhne aktuální větev a přijme jen fast-forward.
Před aktualizací vytvoří `/var/backups/slack-attendance/<čas-ID>/` s dumpem databáze,
konfigurací, předchozím commitem a seznamem instalovaných balíčků. Pak zastaví bota,
aktualizuje kód/závislosti, provede opakovatelnou migraci a znovu službu spustí.
Počítej s krátkou odstávkou. Při chybě se stav automaticky nevrací.

Při prvním přechodu ze staré ruční instalace zastav původní proces/supervisor,
přesuň konfiguraci mimo Git a použij `install.sh`. Nenechávej běžet dvě instance,
protože by mohly odesílat stejné připomínky.

## Provoz a obnova

Logy aplikace i tracebacky zachycených chyb zapisuje Python na standardní chybový
výstup. Dodaná systemd služba explicitně směruje stdout i stderr do journalu.
`LOG_LEVEL=INFO` zahrnuje start, zápis docházky a obnovení pohledu; chyby obsahují
kontext uživatele/události a traceback. Text poznámky se v těchto provozních záznamech neloguje.

Pro starou službu s `WorkingDirectory=/opt/slack_bot` a výstupem do
`/var/log/slack-bot*.log` lze zachovat její cestu, Python i účet a přidat override.
Nahraď `NAZEV.service` skutečným názvem jednotky:

```bash
sudo systemctl edit NAZEV.service
```

Vlož obsah [deploy/journal.conf](deploy/journal.conf):

```ini
[Service]
Environment=PYTHONUNBUFFERED=1
Environment=LOG_LEVEL=INFO
StandardOutput=journal
StandardError=journal
SyslogIdentifier=slack-attendance
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart NAZEV.service
sudo journalctl -u NAZEV.service -n 100 --no-pager
sudo journalctl -u NAZEV.service -f
```

Override nahradí původní směrování `append:`; nové výstupy už nepřibývají do
původních log souborů. Jejich starý obsah zůstane zachovaný. Zobrazení tracebacků
vyžaduje také nasazení aktualizovaného Python kódu. Uchování journalu přes restart
serveru řídí systémové nastavení journald. Viz
[systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#StandardOutput=).

Po kliknutí na docházku lze rozlišit `Attendance saved` a
`Attendance view refreshed`; chybový záznam obsahuje `saved=True/False`.
Čtení poznámky podporuje hlavní `state` i starší `view.state`, chybějící pole
zachová uloženou poznámku. Strukturu akcí popisuje
[Slack block_actions](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload/).

Pro instalaci spravovanou novými deploy skripty použij přímo:

```bash
sudo systemctl status slack-attendance
sudo journalctl -u slack-attendance -n 100 --no-pager
sudo journalctl -u slack-attendance -f
sudo systemctl restart slack-attendance
```

Skript po startu sleduje stabilitu procesu 20 sekund. Není to potvrzení spojení se
Slackem: ověř log Socket Mode a Home tab. Připomínky se kontrolují hned po startu
 a následně v půlhodinových intervalech. Po výpadku se splatná připomínka odešle jednou
 a další termín opakování se posune do budoucnosti.

Při neúspěšném deployi nejdřív zkontroluj log. Oprav konfiguraci nebo závislosti,
spusť `manage.py migrate` a `manage.py check` s produkčními cestami a restartuj službu.
Všechny ruční příkazy musí používat stejnou konfiguraci jako systemd, například:

```bash
sudo env ATTENDANCE_CONFIG=/var/lib/slack-attendance/config.ini \
  ATTENDANCE_ENV=/var/lib/slack-attendance/.env TZ=Europe/Prague \
  /opt/slack-attendance/venv/bin/python /opt/slack-attendance/app/manage.py check
```

Pro návrat verze zastav službu, zjisti původní commit z `commit.txt` v záloze
 a přepni checkout na tento commit (`git switch --detach <commit>`). Obnov Python
závislosti podle zálohovaného `requirements.txt`. Po návratu na větev lze znovu
použít standardní deploy. Obnova staršího kódu nemusí vyžadovat obnovu databáze:
aktuální migrace pouze doplňuje tabulku/sloupce.

Pokud je nutná obnova databáze, se zastaveným botem nejprve zazálohuj současný stav,
zkontroluj cílovou databázi a importuj vybraný `database.sql` přes `mariadb`.
Dump obsahuje DROP/CREATE tabulek; import nahradí zálohované tabulky a ztratí změny
od pořízení zálohy. Obnov případně i konfiguraci a její vlastnictví
`slack-attendance:slack-attendance`, mód `600`. U návratu ke starému commitu použij
jeho odpovídající konfiguraci služby a umístění konfigurace.
Zálohy se automaticky nemažou; nastav jejich uchování a kopírování mimo server.

## Databázové migrace a testy

Migrace používají stejný postup jako DiscordAttendance: číslované soubory v
`migrations/`, samostatný runner a tabulku `schema_migrations` s verzí, názvem,
kontrolním součtem SHA-256 a časem úspěšného dokončení.

```bash
python migrate.py status
python migrate.py dry-run
python migrate.py migrate
python migrate.py check
```

`status` vypíše dokončené a čekající migrace. `dry-run` navíc ukáže SQL čekajících
migrací; SQL neprovádí ani neověřuje na databázi. Oba příkazy databázi pouze čtou,
nevytvářejí ani tabulku historie. `check` skončí chybou, pokud migrace chybí nebo
historie nesouhlasí. Tyto příkazy fungují i přes `manage.py`; jeho `check` navíc
ověří provozní konfiguraci a sloupce používané aplikací.

| Migrace | Obsah |
| --- | --- |
| `001_initial_schema.sql` | Uživatelé, události, docházka a historie |
| `002_add_reminders.sql` | Základní tabulka připomínek |
| `003_reminder_event_sharing.sql` | Typ připomínky, počet dnů dopředu a filtr typu události |

Pro novou i existující databázi spusť stejný `migrate` příkaz. Při převzetí databáze
bez historie migrací se všechny tři soubory provedou a zaznamenají: existující
tabulky zůstanou zachované, sloupce připomínek se přidají pouze při jejich absenci.
Platí to i po původních ručních SQL skriptech nebo předchozím `manage.py migrate`.
Libovolné ruční změny starého schématu migrace automaticky neopravují; nesoulad
sloupců používaných aplikací zachytí následný `manage.py check`.

`db.sql` je souhrnný bootstrap složený z číslovaných migrací, nikoli vstup runneru.
Install ani deploy jej přímo neimportují. Po případném ručním importu spusť
`migrate`, aby vznikla i historie. Původní `add_reminders_table.sql` a
`alter_reminders_table.sql` byly přesunuté do číslovaných migrací.

Install i deploy pořídí zálohu, vypíšou stav, provedou migrace a ověří výsledek
před startem bota. Runner má navíc databázový zámek proti souběhu z jiného procesu
nebo serveru. Ruční spuštění runneru samo zálohu netvoří; nejdříve ji vytvoř
příkazem `manage.py backup --output <soubor.sql>` se stejnou konfigurací.

Novou změnu přidej jako `004_popis_zmeny.sql` a další čísla ve vzestupném pořadí.
Již použité migrace nepřejmenovávej ani neupravuj: runner kontroluje jejich obsah
a odmítne také chybějící soubor nebo vložení starší verze mezi dokončené migrace.
Při změně migrací aktualizuj souhrnný `db.sql` jejich spojením v číselném pořadí;
regresní test hlídá jeho shodu. SQL může používat běžné příkazy a PREPARE/EXECUTE;
nepodporuje `USE`, vlastní `DELIMITER` ani spustitelné komentáře `/*! ... */`.

MariaDB/MySQL DDL není transakční. Při chybě runner danou migraci nezapíše jako
dokončenou a další migrace nepustí, ale již provedené DDL může zůstat v databázi.
Oprav příčinu a spusť migrace znovu; dodané migrace dovolují opakování po částečném
dokončení. Další migrace piš stejným způsobem nebo připrav postup obnovy ze zálohy.
Podrobnosti chyby zobrazí `python migrate.py migrate --verbose`.

```bash
python -m unittest discover -s tests -v
python -m pip install ruff
ruff check .
bash -n deploy/install.sh
bash -n deploy/deploy.sh
bash -n deploy/lib.sh
```

Testy neposílají zprávy do Slacku ani nemění skutečnou databázi.
Nálezy, provedené opravy a zbývající omezení jsou v [REVIEW.md](REVIEW.md).
