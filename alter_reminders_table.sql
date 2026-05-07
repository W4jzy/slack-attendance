-- Add new columns to reminders table for event sharing functionality

ALTER TABLE `reminders`
ADD COLUMN `reminder_type` VARCHAR(20) DEFAULT 'message' AFTER `active`,
ADD COLUMN `days_ahead` INT DEFAULT 0 AFTER `reminder_type`,
ADD COLUMN `event_type_filter` VARCHAR(100) DEFAULT NULL AFTER `days_ahead`;

-- Update existing reminders to have the default type
UPDATE `reminders` SET `reminder_type` = 'message' WHERE `reminder_type` IS NULL;
