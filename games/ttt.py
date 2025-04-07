from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import random
import threading
import time
from utils.constants import *
from database import update_user_record

def generate_board_keyboard(room_id, board):
    """Generate Tic Tac Toe board as inline keyboard"""
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            index = i + j
            cell = board[index] if board[index] != " " else "　"
            row.append(InlineKeyboardButton(cell, callback_data=f"ttt_move_{room_id}_{index}"))
        keyboard.append(row)
    # return to main menu button
    keyboard.append([InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)])
    return InlineKeyboardMarkup(keyboard)


def check_win(board):
    """Check for winner or draw"""
    win_combinations = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]
    for a, b, c in win_combinations:
        if board[a] == board[b] == board[c] and board[a] != " ":
            return board[a], (a, b, c)
    if " " not in board:
        return "draw", None
    return None, None


def start_tictactoe_game(update: Update, context: CallbackContext, room_id, room):
    """Initialize Tic Tac Toe game"""
    # initialize board and set host as first player
    room["board"] = [" "] * 9
    room["current_turn"] = room["host"]
    text = f"Tic Tac Toe game started!\nRoom ID: {room_id}\n\nCurrent board:"
    reply_markup = generate_board_keyboard(room_id, room["board"])
    turn_marker = "X" if room["host"] == room["current_turn"] else "O"
    text += f"\nIt's {turn_marker}'s turn."
    
    query = update.callback_query
    query.edit_message_text(text, reply_markup=reply_markup)
    
    # notify other players in the room
    for player_id in room["players"]:
        if player_id == room["host"] or player_id == "GPT":
            continue
        try:
            context.bot.send_message(
                chat_id=player_id,
                text=text,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to player {player_id}: {e}")
    
    # check if GPT is in the room and it's GPT's turn
    if "GPT" in room["players"] and room["current_turn"] != room["host"]:
        def delayed_gpt_move():
            time.sleep(1)
            make_gpt_ttt_move(context, room_id, room)
            
        threading.Thread(target=delayed_gpt_move).start()


def handle_ttt_move(update: Update, context: CallbackContext) -> None:
    """Tic Tac Toe player move"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    # format: ttt_move_{room_id}_{index}
    if len(data) != 4:
        return
    room_id = data[2]
    try:
        index = int(data[3])
    except ValueError:
        return
    
    room = active_rooms[TIC_TAC_TOE].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("The room does not exist or the game has ended.")
        return
    
    user_id = update.effective_user.id
    # check if it's the player's turn
    if user_id != room["current_turn"]:
        query.answer("It's not your turn!", show_alert=True)
        return

    board = room["board"]
    if board[index] != " ":
        query.answer("This position is already taken!", show_alert=True)
        return

    # determine the player's marker: host is X, opponent is O
    marker = "X" if user_id == room["host"] else "O"
    board[index] = marker

    # check for winner or draw
    result, win_combo = check_win(board)
    if result == marker:
        win_type = ""
        if win_combo:
            # determine win type
            if win_combo in [(0, 1, 2), (3, 4, 5), (6, 7, 8)]:
                win_type = "(Horizontal line)"
            elif win_combo in [(0, 3, 6), (1, 4, 7), (2, 5, 8)]:
                win_type = "(Vertical line)"
            elif win_combo == (0, 4, 8):
                win_type = "(Diagonal from top-left to bottom-right)"
            elif win_combo == (2, 4, 6):
                win_type = "(Diagonal from top-right to bottom-left)"
        
        text = f"Congratulations {marker} wins! {win_type}\nRoom ID: {room_id}\nFinal board:"
        room["status"] = "finished"

        # update database records
        player_index = 0 if user_id == room["players"][0] else 1
        opponent_index = 1 - player_index
        update_user_record(user_id, room["player_names"][player_index], TIC_TAC_TOE, "win")
        update_user_record(room["players"][opponent_index], room["player_names"][opponent_index], TIC_TAC_TOE, "loss")

    elif result == "draw":
        text = f"It's a draw!\nRoom ID: {room_id}\nFinal board:"
        room["status"] = "finished"

        # update database records
        update_user_record(room["players"][0], room["player_names"][0], TIC_TAC_TOE, "draw")
        update_user_record(room["players"][1], room["player_names"][1], TIC_TAC_TOE, "draw")

    else:
        # switch turn
        next_player = room["players"][1] if user_id == room["host"] else room["players"][0]
        room["current_turn"] = next_player
        next_marker = "X" if next_player == room["host"] else "O"
        text = f"Current board:\nIt's {next_marker}'s turn.\nRoom ID: {room_id}"
    
    reply_markup = generate_board_keyboard(room_id, board)
    try:
        query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to edit the message: {e}")
    
    # notify other players in the room to update the board state
    for pid in room["players"]:
        if pid == user_id or pid == "GPT":
            continue
        try:
            context.bot.send_message(
                chat_id=pid,
                text=text,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to player {pid}: {e}")
            
    # if the game is not over and the next player is GPT, let GPT make a move
    if room["status"] == "playing" and next_player == "GPT":
        make_gpt_ttt_move(context, room_id, room)


def make_gpt_ttt_move(context, room_id, room):
    """GPT move in the Tic Tac Toe"""
    board = room["board"]
    gpt_state = room["gpt_state"]
    human_marker = "X"
    gpt_marker = "O"
    
    # find empty positions
    empty_indices = [i for i, cell in enumerate(board) if cell == " "]
    
    # if no empty positions, the game ends
    if not empty_indices:
        return
    
    # variable to explain GPT's move
    move_explanation = ""
    
    # GPT decision logic
    # 1. check if GPT can win
    for idx in empty_indices:
        board[idx] = gpt_marker
        result, _ = check_win(board)
        board[idx] = " "  # reset position
        if result == gpt_marker:
            chosen_idx = idx
            move_explanation = "Execute winning move"
            break
    else:
        # 2. block the player from winning
        for idx in empty_indices:
            board[idx] = human_marker
            result, _ = check_win(board)
            board[idx] = " "  # reset position
            if result == human_marker:
                chosen_idx = idx
                move_explanation = "Block player's winning move"
                break
        else:
            # 3. try to take the center position
            if 4 in empty_indices:
                chosen_idx = 4
                move_explanation = "Take center position"
            else:
                # 4. choose a corner or edge randomly
                corners = [i for i in [0, 2, 6, 8] if i in empty_indices]
                if corners:
                    chosen_idx = random.choice(corners)
                    move_explanation = "Choose a corner"
                else:
                    chosen_idx = random.choice(empty_indices)
                    move_explanation = "Choose an edge"
    
    # make GPT's move
    board[chosen_idx] = gpt_marker
    
    # check for winner or draw
    result, win_combo = check_win(board)
    if result == gpt_marker:
        win_type = ""
        if win_combo:
            # determine win type
            if win_combo in [(0, 1, 2), (3, 4, 5), (6, 7, 8)]:
                win_type = "(Horizontal line)"
            elif win_combo in [(0, 3, 6), (1, 4, 7), (2, 5, 8)]:
                win_type = "(Vertical line)"
            elif win_combo == (0, 4, 8):
                win_type = "(Diagonal from top-left to bottom-right)"
            elif win_combo == (2, 4, 6):
                win_type = "(Diagonal from top-right to bottom-left)"
        
        text = f"GPT AI {gpt_marker} wins! {win_type}\nRoom ID: {room_id}\nFinal board:"
        room["status"] = "finished"

        # update database records
        update_user_record(room["host"], room["player_names"][0], TIC_TAC_TOE, "loss")
        update_user_record("GPT", "GPT AI", TIC_TAC_TOE, "win")
    elif result == "draw":
        text = f"A draw! \nRoom ID: {room_id}\nFinal chessboard:"
        room["status"] = "finished"

        # update database records
        update_user_record(room["host"], room["player_names"][0], TIC_TAC_TOE, "draw")
        update_user_record("GPT", "GPT AI", TIC_TAC_TOE, "draw")
        
    else:
        # switch turn back to the player
        room["current_turn"] = room["host"]
        text = f"GPT AI has made a move ({move_explanation}).\nCurrent board:\nIt's X's turn.\nRoom ID: {room_id}"
    
    # generate keyboard and send to the player
    reply_markup = generate_board_keyboard(room_id, board)
    try:
        host_id = room["host"]
        context.bot.send_message(
            chat_id=host_id,
            text=text,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Failed to send GPT move message to player: {e}")