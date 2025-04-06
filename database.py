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
        print(f"用户 {username} 的记录已更新！")
    except Exception as e:
        print(f"更新记录失败: {e}")
    finally:
        conn.close()

def get_user_record(user_id):
    """
    查询用户的输赢平记录。
    :param user_id: 用户 ID
    :return: 用户的记录列表或消息字符串
    """
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        # 确保 user_id 是字符串
        user_id = str(user_id)

        # 查询用户记录
        cursor.execute("""
            SELECT username, game_name, wins, losses, draws FROM UserGameRecords
            WHERE user_id = ?
        """, (user_id,))
        records = cursor.fetchall()

        if records:
            # 构造返回消息
            message = f"用户 {records[0][0]} 的游戏记录：\n"  # 使用 username
            for record in records:
                username, game_name, wins, losses, draws = record
                message += f"游戏: {game_name}\n胜: {wins}, 负: {losses}, 平: {draws}\n\n"
            return message
        else:
            return f"用户 {user_id} 没有记录。"
    except Exception as e:
        return f"查询记录失败：{e}"
    finally:
        conn.close()