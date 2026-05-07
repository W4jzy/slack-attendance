-- SQL skript pro přidání tabulky reminders do existující databáze
-- Spusťte tento skript, pokud aktualizujete existující instalaci

-- Vytvoření tabulky reminders
CREATE TABLE IF NOT EXISTS `reminders` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `channel_id` varchar(50) NOT NULL,
  `remind_at` datetime NOT NULL,
  `message` text NOT NULL,
  `repeat_type` varchar(100) DEFAULT NULL,
  `active` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

-- Poznámka: Tato tabulka je již součástí hlavního db.sql souboru
