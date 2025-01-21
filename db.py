import mysql.connector
import json
from datetime import datetime
from configparser import ConfigParser
from typing import Optional, List, Dict, Any
import logging
import config

class DatabaseError(Exception):
    """Base exception for database related errors"""
    pass

def connect_to_db() -> mysql.connector.MySQLConnection:
    """
    Create database connection with error handling.
    
    Returns:
        mysql.connector.MySQLConnection: Database connection
        
    Raises:
        DatabaseError: If connection fails
    """
    config = ConfigParser()
    config.read("config.ini")

    try:
        connection = mysql.connector.connect(
            host=config.get("database", "host"),
            user=config.get("database", "user"),
            password=config.get("database", "password"),
            database=config.get("database", "database")
        )
        return connection
    except mysql.connector.Error as err:
        raise DatabaseError(f"Failed to connect to database: {err}")
    except Exception as e:
        raise DatabaseError(f"Unexpected error connecting to database: {e}")

def execute_query(query: str, params: Optional[tuple] = None, 
                 fetchone: bool = False, 
                 logger: Optional[logging.Logger] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Execute SQL query with error handling and resource management.
    
    Args:
        query: SQL query to execute
        params: Query parameters
        fetchone: Whether to fetch one result or all results
        logger: Optional logger instance
        
    Returns:
        Optional[List[Dict[str, Any]]]: Query results
        
    Raises:
        DatabaseError: If query execution fails
    """
    connection = None
    cursor = None
    try:
        connection = connect_to_db()
        cursor = connection.cursor(dictionary=True)
        
        if logger:
            logger.debug(f"Executing query: {query} with params: {params}")
            
        cursor.execute(query, params or ())
        
        if query.strip().lower().startswith("select"):
            if fetchone:
                return cursor.fetchone()
            return cursor.fetchall()
        else:
            connection.commit()
            return None
            
    except mysql.connector.Error as err:
        if connection:
            connection.rollback()
        if logger:
            logger.error(f"Database query error: {err}")
        raise DatabaseError(f"Query execution failed: {err}")
    except Exception as e:
        if connection:
            connection.rollback()
        if logger:
            logger.error(f"Unexpected database error: {e}")
        raise DatabaseError(f"Unexpected error during query execution: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_training_status(status: str) -> str:
    """Map standard status to training status."""
    status_map = {
        "Coming": config.coming_training,
        "Late": config.late_training,
        "Not Coming": config.notcoming_training
    }
    return status_map.get(status, status)

def get_other_status(status: str) -> str:
    """Map standard status to other status."""
    status_map = {
        "Coming": config.coming_text,
        "Late": config.late_text,
        "Not Coming": config.notcoming_text
    }
    return status_map.get(status, status)

def load_events_from_db(logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    """Load upcoming events from database"""
    query = """
        SELECT * FROM events 
        WHERE end_time > %s
        ORDER BY start_time ASC
    """ 
    now = datetime.now()
    return execute_query(query, (now,), logger=logger)

def load_events_by_type_from_db(type, logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT * FROM events 
        WHERE end_time > %s
        AND type = %s
        ORDER BY start_time ASC
    """ 
    now = datetime.now()
    return execute_query(query, (now, type,), logger=logger)

def load_users_from_db(logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT * FROM users 
        ORDER BY name ASC
    """
    return execute_query(query, logger=logger)

def load_user_in_event(event_id, user_id, logger: Optional[logging.Logger] = None) -> Optional[Dict[str, Any]]:
    query = """
        SELECT u.user_id, u.name, p.status, p.note
        FROM users u
        LEFT JOIN participants p ON p.user_id = u.user_id AND p.event_id = %s
        WHERE u.user_id = %s;
    """
    return execute_query(query, (event_id, user_id,), fetchone=True, logger=logger)

def load_users_not_in_event(event_id, logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT u.user_id, u.name
        FROM users u
        LEFT JOIN participants p ON u.user_id = p.user_id AND p.event_id = %s
        WHERE p.user_id IS NULL 
        ORDER BY name ASC
    """
    return execute_query(query, (event_id,), logger=logger)

def load_participants_in_range(start_date, end_date, logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT u.name, p.status, p.note, e.name AS event_name, e.start_time, e.end_time
        FROM users u
        JOIN participants p ON u.user_id = p.user_id
        JOIN events e ON p.event_id = e.id
        WHERE DATE(e.start_time) >= %s
        AND DATE(e.end_time) <= %s
        ORDER BY e.start_time ASC, u.name ASC
    """
    return execute_query(query, (start_date, end_date,), logger=logger)

def load_event_from_db(event_id, logger: Optional[logging.Logger] = None) -> Optional[Dict[str, Any]]:
    query = """
        SELECT * FROM events 
        WHERE id = %s
    """
    return execute_query(query, (event_id,), fetchone=True, logger=logger)

def load_participants_from_event(event_id, logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT u.user_id, u.name, u.category, p.status, p.note
        FROM participants p
        JOIN users u ON p.user_id = u.user_id
        WHERE event_id = %s
        ORDER BY u.name ASC
    """
    return execute_query(query, (event_id,), logger=logger)

def load_events_in_range_from_db(start_date, end_date, logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT * FROM events 
        WHERE lock_time >= %s
        AND DATE(start_time) <= %s
        AND type = "Trénink"
    """
    return execute_query(query, (start_date, end_date,), logger=logger)

def load_events_by_date_from_db(date, logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT * FROM events 
        WHERE DATE(start_time) = %s
    """
    return execute_query(query, (date,), logger=logger)

def load_history_from_event(event_id, logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT h.user_id, u.name, h.old_status, h.new_status, h.old_note, h.new_note, h.timestamp
        FROM history h
        JOIN users u ON h.user_id = u.user_id
        WHERE event_id = %s
        ORDER BY h.timestamp DESC
    """
    return execute_query(query, (event_id,), logger=logger)

def load_participants_for_user(user_id, logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT event_id, status, note, user_id
        FROM participants
        WHERE user_id = %s;
    """
    return execute_query(query, (user_id,), logger=logger)

def load_from_db(logger: Optional[logging.Logger] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT 
            e.id AS event_id,
            e.name AS event_name,
            DATE_FORMAT(e.start_time, '%d.%m.%Y %H:%i') AS start_time,
            DATE_FORMAT(e.end_time, '%d.%m.%Y %H:%i') AS end_time,
            DATE_FORMAT(e.lock_time, '%d.%m.%Y %H:%i') AS lock_time,
            e.type AS event_type,
            e.address AS event_address,
            GROUP_CONCAT(
                CONCAT(
                    '{"user_id": "', u.user_id, '", ',
                    '"name": "', u.name, '", ',
                    '"status": "', p.status, '", ',
                    '"note": "', COALESCE(p.note, ''), '"}'
                )
            ) AS participants
        FROM 
            events e
        INNER JOIN 
            participants p ON e.id = p.event_id
        INNER JOIN 
            users u ON p.user_id = u.user_id
        GROUP BY 
            e.id
        ORDER BY 
            e.start_time;
    """
    results = execute_query(query, logger=logger)
    events = []
    for row in results:
        event = {
            "id": row['event_id'],
            "name": row['event_name'],
            "start_time": row['start_time'],
            "end_time": row['end_time'],
            "lock_time": row['lock_time'],
            "type": row['event_type'],
            "address": row['event_address'],
            "participants": json.loads(f"[{row['participants']}]")
        }
        events.append(event)
    return events

def add_user(name, user_id, logger: Optional[logging.Logger] = None) -> None:
    query = "INSERT INTO users (name, users_id) VALUES (%s, %s)"
    execute_query(query, (name, user_id), logger=logger)



def add_event_to_db(name, start_time, end_time, lock_time, event_type, address, logger: Optional[logging.Logger] = None) -> None:
    start_time = datetime.fromtimestamp(start_time)
    end_time = datetime.fromtimestamp(end_time)
    lock_time = datetime.fromtimestamp(lock_time)

    query = """
    INSERT INTO events (name, start_time, end_time, lock_time, type, address)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    execute_query(query, (name, start_time, end_time, lock_time, event_type, address), logger=logger)

def update_participation(event_id, user_id, status, logger: Optional[logging.Logger] = None) -> None:
    query = """
            UPDATE participants 
            SET status = %s 
            WHERE user_id = %s AND event_id = %s
        """
    execute_query(query, (status, user_id, event_id), logger=logger)

def insert_participation(event_id: int, user_id: str, status: str, 
                        note: Optional[str] = None,
                        logger: Optional[logging.Logger] = None) -> None:
    """
    Insert or update participant record with proper error handling.
    
    Args:
        event_id: Event ID
        user_id: User ID
        status: Participation status
        note: Optional note
        logger: Optional logger instance
        
    Raises:
        DatabaseError: If database operation fails
    """
    try:
        if note is not None:
            note = note.strip()

        event = execute_query(
            "SELECT type FROM events WHERE id = %s",
            (event_id,),
            fetchone=True,
            logger=logger
        )
        if not event:
            raise DatabaseError(f"Event {event_id} not found")

         # Map status if event is training
        if event['type'] == 'Trénink':
            new_status = get_training_status(status)
        else:
            new_status = get_other_status(status)

        participant = execute_query(
            "SELECT * FROM participants WHERE user_id = %s AND event_id = %s",
            (user_id, event_id),
            fetchone=True,
            logger=logger
        )

        if participant:
            execute_query(
                """UPDATE participants 
                   SET status = %s, note = %s 
                   WHERE user_id = %s AND event_id = %s""",
                (status, note, user_id, event_id),
                logger=logger
            )

            if event['type'] == 'Trénink':
                old_status = get_training_status(participant['status'])
            else:
                old_status = get_other_status(participant['status'])

            log_participant_change(event_id, user_id, old_status, 
                                 new_status, participant['note'], note, logger)
        else:
            execute_query(
                """INSERT INTO participants (user_id, event_id, status, note) 
                   VALUES (%s, %s, %s, %s)""",
                (user_id, event_id, status, note),
                logger=logger
            )
            log_participant_change(event_id, user_id, "Nezadáno", 
                                 new_status, None, note, logger)

    except DatabaseError:
        if logger:
            logger.error(f"Failed to update participation for user {user_id} in event {event_id}")
        raise

def log_participant_change(event_id, user_id, old_status, new_status, old_note, new_note, logger: Optional[logging.Logger] = None) -> None:
    query = """
        INSERT INTO history (event_id, user_id, old_status, new_status, old_note, new_note) 
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    execute_query(query, (event_id, user_id, old_status, new_status, old_note, new_note), logger=logger)

def duplicate_event_to_db(name, start_time, end_time, lock_time, event_type, address, logger: Optional[logging.Logger] = None) -> None:
    query = """
    INSERT INTO events (name, start_time, end_time, lock_time, type, address)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    execute_query(query, (name, start_time, end_time, lock_time, event_type, address), logger=logger)

def update_event(name, event_type, address, lock_timestamp, event_id, logger: Optional[logging.Logger] = None) -> None:
    lock_time = datetime.fromtimestamp(lock_timestamp)

    query = """
    UPDATE events
    SET name = %s, type = %s, address = %s, lock_time = %s
    WHERE id = %s
    """
    execute_query(query, (name, event_type, address, lock_time, event_id), logger=logger)

def update_participant(participant_id, status, note, logger: Optional[logging.Logger] = None) -> None:
    query = """
    UPDATE participants
    SET status = %s, note = %s
    WHERE id = %s
    """
    execute_query(query, (status, note, participant_id), logger=logger)

def delete_event(event_id, logger: Optional[logging.Logger] = None) -> None:
    query = "DELETE FROM events WHERE id = %s"
    execute_query(query, (event_id,), logger=logger)

def check_user(user_id, name, logger: Optional[logging.Logger] = None) -> None:
    query = """
        SELECT * FROM users WHERE user_id = %s
    """
    user = execute_query(query, (user_id,), fetchone=True, logger=logger)
    if not user:
        query = """
            INSERT INTO users (user_id, name) 
            VALUES (%s, %s)
        """
        execute_query(query, (user_id, name), logger=logger)

def update_user_category(user_id: str, category: str, logger: Optional[logging.Logger] = None) -> None:
    """
    Update the category of a user.
    
    Args:
        user_id: User ID
        category: New category
        logger: Optional logger instance
        
    Raises:
        DatabaseError: If database operation fails
    """
    query = """
        UPDATE users
        SET category = %s
        WHERE user_id = %s
    """
    execute_query(query, (category, user_id), logger=logger)

def check_user_category(user_id: str, logger: Optional[logging.Logger] = None) -> bool:
    """
    Check if a category exists for a user.
    
    Args:
        user_id: User ID
        logger: Optional logger instance
        
    Returns:
        bool: True if category exists, False otherwise
        
    Raises:
        DatabaseError: If database operation fails
    """
    query = """
        SELECT category FROM users
        WHERE user_id = %s
    """
    result = execute_query(query, (user_id,), fetchone=True, logger=logger)
    return result is not None and result.get('category') is not None

def load_users_by_category(category: str, logger: Optional[logging.Logger] = None) -> List[str]:
    """
    Load all user IDs by category.
    
    Args:
        category: Category to filter users by
        logger: Optional logger instance
        
    Returns:
        List[str]: List of user IDs in the specified category
        
    Raises:
        DatabaseError: If database operation fails
    """
    query = """
        SELECT user_id FROM users
        WHERE category = %s
        ORDER BY name ASC
    """
    results = execute_query(query, (category,), logger=logger)
    return [user['user_id'] for user in results]

