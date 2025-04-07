import pyodbc
import os

try:
    # create connection string using environment variables
    connection_string = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={os.environ['DB_server']};DATABASE={os.environ['DB_database']};UID={os.environ['DB_username']};PWD={os.envrion['DB_password']}"
    conn = pyodbc.connect(connection_string)
    print("connected to database")
    conn.close()
except Exception as e:
    print(f"database connect fail: {e}")


def update_user_record(user_id, username, game_name, result):
    """
    update or insert user game record.
    result: ('win', 'loss', 'draw')
    """
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        # make sure user_id and username are string
        user_id = str(user_id)
        username = str(username)

        # check if the user_id and game_name already exist
        cursor.execute("""
            SELECT wins, losses, draws FROM UserGameRecords
            WHERE user_id = ? AND game_name = ?
        """, (user_id, game_name))
        record = cursor.fetchone()

        if record:
            # update existing record
            if result == 'win':
                cursor.execute("""
                    UPDATE UserGameRecords
                    SET wins = wins + 1, username = ?
                    WHERE user_id = ? AND game_name = ?
                """, (username, user_id, game_name))
            elif result == 'loss':
                cursor.execute("""
                    UPDATE UserGameRecords
                    SET losses = losses + 1, username = ?
                    WHERE user_id = ? AND game_name = ?
                """, (username, user_id, game_name))
            elif result == 'draw':
                cursor.execute("""
                    UPDATE UserGameRecords
                    SET draws = draws + 1, username = ?
                    WHERE user_id = ? AND game_name = ?
                """, (username, user_id, game_name))
        else:
            # insert new record
            wins, losses, draws = 0, 0, 0
            if result == 'win':
                wins = 1
            elif result == 'loss':
                losses = 1
            elif result == 'draw':
                draws = 1

            cursor.execute("""
                INSERT INTO UserGameRecords (user_id, username, game_name, wins, losses, draws)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, username, game_name, wins, losses, draws))

        conn.commit()
        print(f"Record for user {username} has been updated! ")
    except Exception as e:
        print(f"Failed to update record: {e}")
    finally:
        conn.close()


def get_user_record(user_id):
    """
    Query the user's win/loss/draw records.
    """
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        # Ensure user_id is a string
        user_id = str(user_id)

        # Query user records
        cursor.execute("""
            SELECT username, game_name, wins, losses, draws FROM UserGameRecords
            WHERE user_id = ?
        """, (user_id,))
        records = cursor.fetchall()

        if records:
            # Construct return message
            message = f"Game records for user {records[0][0]}:\n"
            for record in records:
                game_name, wins, losses, draws = record
                message += f"Game: {game_name}\nWins: {wins}, Losses: {losses}, Draws: {draws}\n\n"
            return message
        else:
            return f"No records found for user {user_id}."
    except Exception as e:
        return f"Failed to query records: {e}"
    finally:
        conn.close()