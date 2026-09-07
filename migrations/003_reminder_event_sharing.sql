-- Former alter_reminders_table.sql. Checks allow retry after partially committed DDL.

SET @column_exists = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reminders' AND COLUMN_NAME = 'reminder_type'
);
SET @migration_sql = IF(@column_exists = 0, 'ALTER TABLE `reminders` ADD COLUMN `reminder_type` varchar(20) DEFAULT ''message''', 'DO 0');
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @column_exists = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reminders' AND COLUMN_NAME = 'days_ahead'
);
SET @migration_sql = IF(@column_exists = 0, 'ALTER TABLE `reminders` ADD COLUMN `days_ahead` int DEFAULT 0', 'DO 0');
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @column_exists = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reminders' AND COLUMN_NAME = 'event_type_filter'
);
SET @migration_sql = IF(@column_exists = 0, 'ALTER TABLE `reminders` ADD COLUMN `event_type_filter` varchar(100) DEFAULT NULL', 'DO 0');
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

UPDATE `reminders` SET `reminder_type` = 'message' WHERE `reminder_type` IS NULL;
