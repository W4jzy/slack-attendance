# Revize aplikace

## Co aplikace dělá

Python proces se Slack Bolt v Socket Mode obsluhuje Home tab, události, vlastní
i administrátorskou docházku, kategorie hráčů, historii, CSV export a připomínky.
Data jsou v MySQL/MariaDB; připomínky zpracovává vlákno stejného procesu.
Nasazení má běžet v jedné instanci. Vzor install/deploy pochází z `uniulti/deploy`;
systém číslovaných migrací vychází z aktualizované lokální verze `DiscordAttendance`.

## Opravené nálezy

- Kliknutí na docházku očekávalo poznámku výhradně ve `view.state.values`:
  podporuje také hlavní `state.values` z block_actions a chybějící pole zachová
  uloženou poznámku. Akce se potvrzuje jednou, po zápisu se přímo obnoví stejná
  stránka/filtr. Selhání vykreslení se propaguje, takže uživatel rozliší chybu
  uložení a chybu zobrazení. Výpadek načtení administrátorské skupiny dovolí
  vykreslit běžnou docházku bez administrátorských ovládacích prvků.
- Zachycené výjimky se logují s tracebackem; doplněno logování neošetřených
  výjimek a vláken. Služba směruje výstup do journalu; pro starou instalaci
  `/opt/slack_bot` je připraven `deploy/journal.conf` a postup v README.

- Chybějící závislost na MySQL konektoru a nereprodukovatelná instalace:
  kompletní připnuté `requirements.txt`, samostatné prostředí a systemd.
- Neplatné `db.sql` (čárka za posledním sloupcem `users`) a chybějící sloupce
  připomínek: číslované SQL migrace, souhrnný bootstrap a `migrate.py` s příkazy
  status/dry-run/migrate/check. Historie v `schema_migrations` kontroluje názvy
  a SHA-256 souborů; databázový zámek brání souběhu migrací. Install i deploy
  migrace spouští po záloze. `manage.py migrate` zůstává kompatibilní vstup.
- `except ConfigParser.Error` odkazoval na neexistující atribut a maskoval
  původní chybu: správná výjimka, UTF-8, vypnutá interpolace `%`, cesty nezávislé
  na pracovním adresáři a okamžitá aktualizace textů po uložení nastavení.
- Práva administrátora se kontrolovala jen při vykreslení nabídky:
  middleware nyní kontroluje administrativní akce, formuláře a vyhledávání uživatelů.
  Při chybě Slack API administrativní akci nepovolí.
- Změna docházky a historie používaly oddělená spojení/commity:
  jedna transakce se zámkem události chrání před souběžným vložením a neúplnou historií.
- Formulář ze sdílené zprávy dovoloval uložit docházku po uzávěrce:
  kontrola je nyní i při zápisu, stejně jako u vlastní a hromadné docházky.
  Administrátor může dál opravit docházku po uzávěrce.
- Duplicitní registrace obou handlerů duplikování událostí:
  zůstala jedna varianta s validací počtu 1–52.
- Importy přes `*` skrývaly původ symbolů a kolize: explicitní importy;
  odstraněné nepoužité importy, proměnné a nadbytečné dotazy.
- Povinné české locale shazovalo start na jiných systémech:
  dostupné varianty a fallback; instalátor nastavuje české locale.
- Připomínky po startu čekaly na půlhodinu: první kontrola proběhne hned.
  Měsíční opakování respektuje délku měsíce; zmeškané opakování pokračuje
  budoucím termínem, bez opakovaného dohánění při každé kontrole.
- Neúspěšné sdílení již připomínku neoznačí za vyřízenou.
- Lokální konfigurace, `.DS_Store` a prázdný `Test.md` byly sledované Gitem:
  vyřazeny ze sledování, lokální soubory zachovány, přidány vzory konfigurace.

## Co zbývá pro případné další rozšíření

- Připomínky nemají evidenci doručení jednotlivých zpráv. Při částečném selhání
  může další pokus zopakovat již doručené zprávy; pád mezi odesláním a uložením
  výsledku může způsobit totéž. Spolehlivější doručování vyžaduje frontu a evidenci pokusů.
- Termíny jsou uloženy bez časového pásma. Služba používá `Europe/Prague`, ale
  při přechodu letního/zimního času zůstávají místní časy potenciálně nejednoznačné.
- Existující duplicitní řádky docházky migrace automaticky nemaže. Nový zápis se
  serializuje přes událost; pro databázovou unikátnost je nejprve nutné posoudit
  existující duplicity a následně přidat unikátní index `(user_id, event_id)`.
- Některé seznamy používají statické Slack selecty a mohou narazit na limity
  při větším počtu kanálů či hráčů. Další krok je sjednocení na externí vyhledávání.
- `bot.py` zůstává velký. Rozdělení registrace handlerů podle funkcí aplikace
  dává smysl jako samostatný navazující refaktor s testy interakcí.
- Historické soubory `REMINDERS.md`, `REMINDER_SHARE_EVENTS.md` a
  `IMPLEMENTATION_NOTES.md` zůstávají jako kontext funkcí. Aktuální provozní postup
  je v README; původní SQL skripty byly nahrazeny číslovanými migracemi.

## Ověření a omezení

Regresní testy používají mock Slack API a databázového spojení. Ověřují práva,
rollback historie, uzávěrku, konfiguraci, opakování připomínek, migrace a registraci
handlerů. Ruff kontroluje chyby Pythonu, Bash kontrola syntaxi provozních skriptů.
V tomto Windows prostředí není MariaDB ani systemd: skutečný import SQL, obnovu
z dumpu a službu je nutné ověřit na cílovém Linuxu. Žádná zpráva nebyla odeslána do Slacku.
