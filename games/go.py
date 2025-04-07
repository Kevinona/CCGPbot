from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import random
import threading
import time
from utils.constants import *
from database import update_user_record

def generate_go_board_keyboard(room_id, board):
    """Generate Go board as an inline keyboard"""
    keyboard = []
    # add coordinate labels (A-I)
    header_row = [InlineKeyboardButton(" ", callback_data=f"go_none")]
    for col in range(GO_BOARD_SIZE):
        header_row.append(InlineKeyboardButton(chr(65 + col), callback_data=f"go_none"))
    keyboard.append(header_row)
    
    # add board cells
    for row in range(GO_BOARD_SIZE):
        board_row = [InlineKeyboardButton(f"{row + 1}", callback_data=f"go_none")]
        for col in range(GO_BOARD_SIZE):
            cell = board[row][col]
            if cell == "B":
                display = "⚫"
            elif cell == "W":
                display = "⚪"
            else:
                display = "·"
            board_row.append(InlineKeyboardButton(display, callback_data=f"go_move_{room_id}_{row}_{col}"))
        keyboard.append(board_row)
    
    # add pass and return buttons
    keyboard.append([
        InlineKeyboardButton("Pass", callback_data=f"go_pass_{room_id}"),
        InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)
    ])
    return InlineKeyboardMarkup(keyboard)


def start_go_game(update: Update, context: CallbackContext, room_id, room):
    """Initialize Go game, create board, and set initial state"""
    # initialize board and current turn (host plays black)
    room["board"] = create_go_board()
    room["current_turn"] = room["host"]  # host plays first (black)
    room["pass_count"] = 0  # track consecutive passes
    room["black_captures"] = 0  # black captures
    room["white_captures"] = 0  # white captures
    
    # assign stone colors
    host_stone = "B"  # host plays black
    opponent_stone = "W"  # opponent plays white
    
    text = f"Go game started!\nRoom ID: {room_id}\nBoard size: {GO_BOARD_SIZE}x{GO_BOARD_SIZE}\n\n"
    text += f"Black (⚫): {room['player_names'][0]}\n"
    text += f"White (⚪): {room['player_names'][1]}\n\n"
    text += f"Current turn: Black ({room['player_names'][0]})\n"
    text += f"Black captures: {room['black_captures']}, White captures: {room['white_captures']}"
    
    reply_markup = generate_go_board_keyboard(room_id, room["board"])
    
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
    
    # if the opponent is GPT and GPT plays first
    if "GPT" in room["players"] and room["current_turn"] == "GPT":
        # let GPT play first with a slight delay
        def delayed_gpt_move():
            time.sleep(1)  # delay 1 second for better user experience
            make_gpt_go_move(context, room_id, room)
            
        threading.Thread(target=delayed_gpt_move).start()


def handle_go_move(update: Update, context: CallbackContext) -> None:
    """Handle Go player's move"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    # format: go_move_{room_id}_{row}_{col} or go_pass_{room_id}
    
    if len(data) < 3:
        return
    
    action = data[1]
    room_id = data[2]
    
    room = active_rooms[GO].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("The room does not exist or the game has ended.")
        return
    
    user_id = update.effective_user.id
    # check if it's the player's turn
    if user_id != room["current_turn"]:
        query.answer("It's not your turn!", show_alert=True)
        return
    
    board = room["board"]
    
    # determine the player's stone: host is black (B), opponent is white (W)
    stone = "B" if user_id == room["host"] else "W"
    opponent_stone = "W" if stone == "B" else "B"
    
    if action == "pass":
        # player chooses to pass
        room["pass_count"] += 1
        pass_message = f"{room['player_names'][0] if stone == 'B' else room['player_names'][1]} chose to pass."
        
        # check if both players pass consecutively, ending the game
        if room["pass_count"] >= 2:
            # simple territory calculation (actual Go requires more complex rules)
            black_territory = sum(row.count("B") for row in board)
            white_territory = sum(row.count("W") for row in board)
            
            # include captures in the score
            black_score = black_territory + room["black_captures"]
            white_score = white_territory + room["white_captures"]
            
            winner = "Black" if black_score > white_score else "White" if white_score > black_score else "Draw"
            result_message = (
                f"Game over! Both players passed consecutively.\n\n"
                f"Black score: {black_score} (territory: {black_territory}, captures: {room['black_captures']})\n"
                f"White score: {white_score} (territory: {white_territory}, captures: {room['white_captures']})\n\n"
                f"Result: {winner} wins!"
            )
            
            room["status"] = "finished"
            text = f"{pass_message}\n\n{result_message}\n\nRoom ID: {room_id}"
            
            # record results in the database
            for i, player_id in enumerate(room["players"]):
                username = room["player_names"][i]
                if winner == "Black":
                    if i == 0:
                        update_user_record(player_id, username, "Go", "win")
                    else:
                        update_user_record(player_id, username, "Go", "loss")
                elif winner == "White":
                    if i == 0:
                        update_user_record(player_id, username, "Go", "loss")
                    else:
                        update_user_record(player_id, username, "Go", "win")
                else:  # Draw
                    update_user_record(player_id, username, "Go", "draw")
            
            # notify all players the game has ended
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]])
            for pid in room["players"]:
                if pid == "GPT":
                    continue
                try:
                    context.bot.send_message(
                        chat_id=pid,
                        text=text,
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Failed to send message to player {pid}: {e}")
            return
        else:
            # switch turn
            next_player = room["players"][1] if user_id == room["host"] else room["players"][0]
            room["current_turn"] = next_player
            next_stone = "B" if next_player == room["host"] else "W"
            
            text = (
                f"{pass_message}\n\n"
                f"Current turn: {'Black' if next_stone == 'B' else 'White'} "
                f"({room['player_names'][0 if next_stone == 'B' else 1]})\n"
                f"Room ID: {room_id}\n"
                f"Black captures: {room['black_captures']}, White captures: {room['white_captures']}"
            )
    else:
        # player places a stone
        try:
            row = int(data[3])
            col = int(data[4])
        except (ValueError, IndexError):
            return
        
        # check if the move is valid
        if not is_valid_go_move(board, row, col, stone):
            query.answer("Invalid move!", show_alert=True)
            return
        
        # reset pass count
        room["pass_count"] = 0
        
        # place the stone
        board[row][col] = stone
        
        # remove captured opponent stones
        captured = remove_captured_stones(board, row, col)
        if captured > 0:
            if stone == "B":
                room["black_captures"] += captured
            else:
                room["white_captures"] += captured
        
        # switch turn
        next_player = room["players"][1] if user_id == room["host"] else room["players"][0]
        room["current_turn"] = next_player
        next_stone = "B" if next_player == room["host"] else "W"
        
        move_text = f"{chr(65 + col)}{row + 1}"
        text = f"{'Black' if stone == 'B' else 'White'} placed a stone at {move_text}"
        if captured > 0:
            text += f", capturing {captured} stones."
        
        text += (
            f"\n\nCurrent turn: {'Black' if next_stone == 'B' else 'White'} "
            f"({room['player_names'][0 if next_stone == 'B' else 1]})\n"
            f"Room ID: {room_id}\n"
            f"Black captures: {room['black_captures']}, White captures: {room['white_captures']}"
        )
    
    reply_markup = generate_go_board_keyboard(room_id, board)
    try:
        query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
    
    # notify other players in the room to update the board
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
        make_gpt_go_move(context, room_id, room)


def make_gpt_go_move(context, room_id, room):
    """Let GPT make a move in the Go game"""
    board = room["board"]
    stone = "W"

    # delay for better user experience
    time.sleep(2)

    try:
        # create a string representation of the board
        board_str = ""
        for r in range(GO_BOARD_SIZE):
            row_str = ""
            for c in range(GO_BOARD_SIZE):
                if board[r][c] == "B":
                    row_str += "⚫"
                elif board[r][c] == "W":
                    row_str += "⚪"
                else:
                    row_str += "·"
            board_str += row_str + "\n"

        # find all valid moves
        valid_moves = []
        for row in range(GO_BOARD_SIZE):
            for col in range(GO_BOARD_SIZE):
                if is_valid_go_move(board, row, col, stone):
                    col_letter = chr(col + ord('A'))
                    row_num = row + 1
                    valid_moves.append(f"{col_letter}{row_num}")

        # prompt
        prompt = f"""You are a Go AI assistant. Please choose the best move for white on a 7x7 Go board.

Important: This is a 7x7 board, not the standard 19x19 board.
The board coordinate system is as follows (top-left is A1, bottom-right is G7):
  A B C D E F G
1 · · · · · · ·
2 · · · · · · ·
3 · · · · · · ·
4 · · · · · · ·
5 · · · · · · ·
6 · · · · · · ·
7 · · · · · · ·

Current board state (⚫ = black, ⚪ = white, · = empty):
{board_str}
Black captures: {room['black_captures']}, White captures: {room['white_captures']}
Consecutive passes: {room['pass_count']}

Valid moves:
{', '.join(valid_moves) if valid_moves else "No valid moves, you must pass"}

Please choose one move or explicitly state "pass". Reply with a single valid coordinate (e.g., D4, E5) or "pass" without explanation."""

        # call GPT
        chatgpt = HKBU_ChatGPT()
        response = chatgpt.submit(prompt)

        # log the raw response
        logger.info(f"GPT raw response: '{response}'")

        # parse the response
        response = response.strip().lower()

        # check if GPT chose to pass
        if "pass" in response:
            room["pass_count"] += 1
            text = "White (GPT) chose to pass."

            # check if both players passed consecutively
            if room["pass_count"] >= 2:
                # calculate scores
                black_territory = sum(row.count("B") for row in board)
                white_territory = sum(row.count("W") for row in board)

                black_score = black_territory + room["black_captures"]
                white_score = white_territory + room["white_captures"]

                winner = "Black" if black_score > white_score else "White" if white_score > black_score else "Draw"
                result_message = (
                    f"Game over! Both players passed consecutively.\n\n"
                    f"Black score: {black_score} (territory: {black_territory}, captures: {room['black_captures']})\n"
                    f"White score: {white_score} (territory: {white_territory}, captures: {room['white_captures']})\n\n"
                    f"Result: {winner} wins!"
                )

                room["status"] = "finished"
                text = f"{text}\n\n{result_message}\n\nRoom ID: {room_id}"

                # record results
                for i, player_id in enumerate(room["players"]):
                    username = room["player_names"][i]
                    if winner == "Black":
                        if i == 0:
                            update_user_record(player_id, username, "Go", "win")
                        else:
                            update_user_record(player_id, username, "Go", "loss")
                    elif winner == "White":
                        if i == 0:
                            update_user_record(player_id, username, "Go", "loss")
                        else:
                            update_user_record(player_id, username, "Go", "win")
                    else:  # Draw
                        update_user_record(player_id, username, "Go", "draw")

                # notify all players the game has ended
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]])
                for pid in room["players"]:
                    if pid == 'GPT':
                        continue
                    try:
                        context.bot.send_message(
                            chat_id=pid,
                            text=text,
                            reply_markup=reply_markup
                        )
                    except Exception as e:
                        logger.error(f"Failed to send message to player {pid}: {e}")
                return
            else:
                # switch turn back to the player
                room["current_turn"] = room["host"]
                text += f"\n\nCurrent turn: Black ({room['player_names'][0]})\nRoom ID: {room_id}\nBlack captures: {room['black_captures']}, White captures: {room['white_captures']}"
        else:
            # try to parse the move
            import re
            match = re.search(r'([a-gA-G])([1-7])', response)
            if match:
                col_letter = match.group(1).lower()
                row_number = match.group(2)

                col = ord(col_letter) - ord('a')
                row = int(row_number) - 1

                if is_valid_go_move(board, row, col, stone):
                    board[row][col] = stone
                    room["pass_count"] = 0

                    captured = remove_captured_stones(board, row, col)
                    if captured > 0:
                        room["white_captures"] += captured

                    room["current_turn"] = room["host"]

                    move_text = f"{chr(65 + col)}{row + 1}"
                    text = f"White (GPT) placed a stone at {move_text}"
                    if captured > 0:
                        text += f", capturing {captured} stones."

                    text += f"\n\nCurrent turn: Black ({room['player_names'][0]})\nRoom ID: {room_id}\nBlack captures: {room['black_captures']}, White captures: {room['white_captures']}"
                else:
                    logger.warning(f"Invalid move suggested by GPT: {response}")
                    text = _make_fallback_go_move(context, room_id, room)
            else:
                logger.warning(f"Failed to parse GPT response: '{response}'")
                text = _make_fallback_go_move(context, room_id, room)
    except Exception as e:
        logger.error(f"Error during GPT decision-making: {e}")
        text = _make_fallback_go_move(context, room_id, room)

    # send the updated board to the player
    reply_markup = generate_go_board_keyboard(room_id, board)
    try:
        host_id = room["host"]
        context.bot.send_message(
            chat_id=host_id,
            text=text,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Failed to send GPT move message to player: {e}")


def _make_fallback_go_move(context, room_id, room):
    """Fallback Go AI strategy when GPT API fails"""
    board = room["board"]
    stone = "W"
    
    # simple Go AI strategy:
    # 1. Randomly select a valid position
    # 2. If no valid position is found after 10 attempts, pass
    valid_moves = []
    for row in range(GO_BOARD_SIZE):
        for col in range(GO_BOARD_SIZE):
            if is_valid_go_move(board, row, col, stone):
                valid_moves.append((row, col))
    
    # if there are valid moves
    if valid_moves:
        # randomly select a position
        row, col = random.choice(valid_moves)
        
        # place the stone
        board[row][col] = stone
        
        # reset pass count
        room["pass_count"] = 0
        
        # remove captured opponent stones
        captured = remove_captured_stones(board, row, col)
        if captured > 0:
            room["white_captures"] += captured
        
        # switch turn back to the player
        room["current_turn"] = room["host"]
        
        move_text = f"{chr(65 + col)}{row + 1}"
        text = f"White (GPT) placed a stone at {move_text}"
        if captured > 0:
            text += f", capturing {captured} stones."
        
        text += f"\n\nCurrent turn: Black ({room['player_names'][0]})\nRoom ID: {room_id}\nBlack captures: {room['black_captures']}, White captures: {room['white_captures']}"
    else:
        # no valid moves, pass
        room["pass_count"] += 1
        text = "White (GPT) chose to pass."
        
        # check if both players passed consecutively
        if room["pass_count"] >= 2:
            # calculate scores
            black_territory = sum(row.count("B") for row in board)
            white_territory = sum(row.count("W") for row in board)
            
            black_score = black_territory + room["black_captures"]
            white_score = white_territory + room["white_captures"]
            
            winner = "Black" if black_score > white_score else "White" if white_score > black_score else "Draw"
            result_message = (
                f"Game over! Both players passed consecutively.\n\n"
                f"Black score: {black_score} (territory: {black_territory}, captures: {room['black_captures']})\n"
                f"White score: {white_score} (territory: {white_territory}, captures: {room['white_captures']})\n\n"
                f"Result: {winner} wins!"
            )
            
            room["status"] = "finished"
            text = f"{text}\n\n{result_message}\n\nRoom ID: {room_id}"
            
            # record results
            for i, player_id in enumerate(room["players"]):
                username = room["player_names"][i]
                if winner == "Black":
                    if i == 0:
                        update_user_record(player_id, username, "Go", "win")
                    else:
                        update_user_record(player_id, username, "Go", "loss")
                elif winner == "White":
                    if i == 0:
                        update_user_record(player_id, username, "Go", "loss")
                    else:
                        update_user_record(player_id, username, "Go", "win")
                else:  # Draw
                    update_user_record(player_id, username, "Go", "draw")

            # notify all players the game has ended
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]])
            for pid in room["players"]:
                if pid == "GPT":
                    continue
                try:
                    context.bot.send_message(
                        chat_id=pid,
                        text=text,
                        reply_markup=reply_markup
                   )
                except Exception as e:
                    logger.error(f"Failed to send message to player {pid}: {e}")
            return
        else:
            # switch turn back to the player
            room["current_turn"] = room["host"]
            text += f"\n\nCurrent turn: Black ({room['player_names'][0]})\nRoom ID: {room_id}\nBlack captures: {room['black_captures']}, White captures: {room['white_captures']}"
    
    return text


def create_go_board():
    """Create an empty Go board"""
    board = [["E" for _ in range(GO_BOARD_SIZE)] for _ in range(GO_BOARD_SIZE)]
    logger.info(f"Created Go board with size: {len(board)}x{len(board[0])}")
    return board


def get_liberties(board, row, col, checked=None):
    """Check the liberties (empty adjacent points) of a stone"""
    if checked is None:
        checked = set()
    
    if row < 0 or row >= GO_BOARD_SIZE or col < 0 or col >= GO_BOARD_SIZE:
        return 0
    
    stone = board[row][col]
    if stone == "E":
        return 1
    
    pos = (row, col)
    if pos in checked:
        return 0
    
    checked.add(pos)
    liberties = 0
    
    # check four directions
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for dr, dc in directions:
        new_row, new_col = row + dr, col + dc
        if 0 <= new_row < GO_BOARD_SIZE and 0 <= new_col < GO_BOARD_SIZE:
            if board[new_row][new_col] == "E":
                liberties += 1
            elif board[new_row][new_col] == stone:
                liberties += get_liberties(board, new_row, new_col, checked)
    
    return liberties


def get_connected_stones(board, row, col, stones=None):
    """Get all connected stones of the same color"""
    if stones is None:
        stones = set()
    
    if row < 0 or row >= GO_BOARD_SIZE or col < 0 or col >= GO_BOARD_SIZE:
        return stones
    
    stone = board[row][col]
    if stone == "E":
        return stones
    
    pos = (row, col)
    if pos in stones:
        return stones
    
    stones.add(pos)
    
    # check four directions
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for dr, dc in directions:
        new_row, new_col = row + dr, col + dc
        if 0 <= new_row < GO_BOARD_SIZE and 0 <= new_col < GO_BOARD_SIZE:
            if board[new_row][new_col] == stone:
                get_connected_stones(board, new_row, new_col, stones)
    
    return stones


def remove_captured_stones(board, row, col):
    """Remove captured stones and return the count"""
    stone = board[row][col]
    opponent = "W" if stone == "B" else "B"
    captured_count = 0
    
    # check four directions for opponent stones
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for dr, dc in directions:
        new_row, new_col = row + dr, col + dc
        if 0 <= new_row < GO_BOARD_SIZE and 0 <= new_col < GO_BOARD_SIZE:
            if board[new_row][new_col] == opponent:
                # get all connected opponent stones
                stones = get_connected_stones(board, new_row, new_col)
                # check if these stones have liberties
                has_liberty = False
                for stone_row, stone_col in stones:
                    for dr2, dc2 in directions:
                        liberty_row, liberty_col = stone_row + dr2, stone_col + dc2
                        if 0 <= liberty_row < GO_BOARD_SIZE and 0 <= liberty_col < GO_BOARD_SIZE:
                            if board[liberty_row][liberty_col] == "E":
                                has_liberty = True
                                break
                    if has_liberty:
                        break
                
                # remove stones if no liberties
                if not has_liberty:
                    for stone_row, stone_col in stones:
                        board[stone_row][stone_col] = "E"
                    captured_count += len(stones)
    
    return captured_count


def is_valid_go_move(board, row, col, stone):
    """Check if a Go move is valid"""
    # check if within board boundaries
    if row < 0 or row >= GO_BOARD_SIZE or col < 0 or col >= GO_BOARD_SIZE:
        return False
    
    # check if the position is empty
    if board[row][col] != "E":
        return False
    
    # temporarily place the stone
    board[row][col] = stone
    
    # check for liberties
    liberties = get_liberties(board, row, col)
    
    # if no liberties, check if it captures opponent stones
    if liberties == 0:
        opponent = "W" if stone == "B" else "B"
        captured = False
        
        # check four directions for opponent stones
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc
            if 0 <= new_row < GO_BOARD_SIZE and 0 <= new_col < GO_BOARD_SIZE:
                if board[new_row][new_col] == opponent:
                    # check liberties of opponent stones
                    opp_liberties = get_liberties(board, new_row, new_col)
                    if opp_liberties == 0:
                        captured = True
                        break
        
        # if no capture, the move is invalid
        if not captured:
            board[row][col] = "E"
            return False
    
    # reset the position (actual placement happens later)
    board[row][col] = "E"
    return True