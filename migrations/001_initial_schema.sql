-- Core attendance tables. Existing installations keep their tables and data.
CREATE TABLE IF NOT EXISTS `users` (
  `user_id` varchar(50) NOT NULL,
  `name` varchar(100) NOT NULL,
  `category` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

CREATE TABLE IF NOT EXISTS `events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `start_time` datetime NOT NULL,
  `end_time` datetime NOT NULL,
  `lock_time` datetime NOT NULL,
  `type` varchar(100) NOT NULL,
  `address` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

CREATE TABLE IF NOT EXISTS `participants` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(50) DEFAULT NULL,
  `event_id` int DEFAULT NULL,
  `status` varchar(100) DEFAULT NULL,
  `note` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `participants_ibfk_1` (`user_id`),
  KEY `participants_ibfk_2` (`event_id`),
  CONSTRAINT `participants_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  CONSTRAINT `participants_ibfk_2` FOREIGN KEY (`event_id`) REFERENCES `events` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;

CREATE TABLE IF NOT EXISTS `history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `event_id` int NOT NULL,
  `user_id` varchar(50) NOT NULL,
  `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `old_status` varchar(20) DEFAULT NULL,
  `new_status` varchar(20) DEFAULT NULL,
  `old_note` varchar(255) DEFAULT NULL,
  `new_note` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `event_id` (`event_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `history_ibfk_1` FOREIGN KEY (`event_id`) REFERENCES `events` (`id`) ON DELETE CASCADE,
  CONSTRAINT `history_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_czech_ci;
