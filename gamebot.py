from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, ConversationHandler
import random
import string
import os
from utils.constants import *
from games.ttt import start_tictactoe_game, handle_ttt_move
from games.bj import start_blackjack_game, handle_blackjack_action
from games.go import start_go_game, handle_go_move
from games.spy import start_spy_game, handle_spy_discussion, handle_spy_vote, say_message, start_vote
from database import get_user_record

def generate_room_id():
    """Generate a random 6-character room ID"""
    while True:
        room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        # ensure the room ID is unique
        if all(room_id not in rooms for rooms in active_rooms.values()):
            return room_id


def start(update: Update, context: CallbackContext) -> int:
    """Handle /start command or return to the main menu"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("Tic Tac Toe", callback_data=TIC_TAC_TOE)],
        [InlineKeyboardButton("Go", callback_data=GO)],
        [InlineKeyboardButton("Who is the Spy", callback_data=WHO_IS_SPY)],
        [InlineKeyboardButton("Blackjack", callback_data=BLACKJACK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"Hello {user.first_name}, welcome to the Game Bot!\n"
        "Please select a game to play:\n\n"
        "You can also use the following commands:\n"
        "/record - Check your game win/loss/draw record\n"
        "/rooms - View active game rooms\n"
        "/join <Room ID> - Join a specific room\n"
        "/cancel - Cancel the current operation"
    )
    
    if update.message:
        update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        logger.error("Unable to determine the message source")
    
    return SELECTING_GAME


def get_game_name(game_type):
    """Safely get the game name to avoid KeyError"""
    return game_names.get(game_type, "Unknown Game")


def game_selection(update: Update, context: CallbackContext) -> int:
    """Handle actions after game selection"""
    query = update.callback_query
    query.answer()
    
    game_type = query.data
    
    # handle special actions
    if game_type in [CREATE_GAME, MATCH_PLAYER, PLAY_WITH_GPT, CANCEL_MATCH] or game_type.startswith(("start_game_", "cancel_room_", "end_game_")):
        return game_action(update, context)
    
    if game_type == BACK_TO_MAIN:
        return start(update, context)
    
    context.user_data["game_type"] = game_type

    if game_type in [TIC_TAC_TOE, GO, BLACKJACK]:
        keyboard = [
            [InlineKeyboardButton("Create Game", callback_data=CREATE_GAME)],
            [InlineKeyboardButton("Match Player", callback_data=MATCH_PLAYER)],
            [InlineKeyboardButton("Play with GPT", callback_data=PLAY_WITH_GPT)],
            [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("Create Game", callback_data=CREATE_GAME)],
            [InlineKeyboardButton("Match Player", callback_data=MATCH_PLAYER)],
            [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(
        f"You selected {get_game_name(game_type)}. Please choose an action:",
        reply_markup=reply_markup
    )
    return GAME_ACTION


def game_action(update: Update, context: CallbackContext) -> int:
    """Handle logic after selecting a specific game action"""
    query = update.callback_query
    query.answer()
    
    action = query.data
    
    if action == BACK_TO_MAIN:
        return start(update, context)
    
    # get game type from user_data or action
    game_type = context.user_data.get("game_type")
    
    # if action is CREATE_GAME, MATCH_PLAYER, etc., but no game_type, return to main menu
    if action in [CREATE_GAME, MATCH_PLAYER, PLAY_WITH_GPT] and not game_type:
        logger.error(f"Game type not defined, action={action}")
        return start(update, context)
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # remove user from waiting list if creating a game
    if action == CREATE_GAME and game_type and user_id in waiting_players.get(game_type, []):
        waiting_players[game_type].remove(user_id)
    
    if action == CREATE_GAME:
        room_id = generate_room_id()
        active_rooms[game_type][room_id] = {
            "host": user_id,
            "host_name": username,
            "players": [user_id],
            "player_names": [username],
            "status": "waiting"
        }
        keyboard = [
            [InlineKeyboardButton("Start Game", callback_data=f"start_game_{room_id}")],
            [InlineKeyboardButton("Cancel Room", callback_data=f"cancel_room_{room_id}")],
            [InlineKeyboardButton("Invite Friends", url=f"https://t.me/share/url?url=Join my {get_game_name(game_type)} game room! Room ID: {room_id}")],
            [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            f"You have successfully created a {get_game_name(game_type)} game room!\nRoom ID: {room_id}\nShare this ID with friends, they can join your room using /join {room_id}.\n\nCurrent players:\n1. {username} (Host)",
            reply_markup=reply_markup
        )
        
    elif action == MATCH_PLAYER:
        # check for available waiting rooms
        available_room = None
        for room_id, room in active_rooms[game_type].items():
            if room["status"] == "waiting" and len(room["players"]) < (8 if game_type == WHO_IS_SPY else 2):
                available_room = (room_id, room)
                break
                
        if available_room:
            # join available room
            room_id, room = available_room
            if user_id not in room["players"]:
                room["players"].append(user_id)
                room["player_names"].append(username)
                
                # notify host of new player
                try:
                    host_keyboard = [
                        [InlineKeyboardButton("Start Game", callback_data=f"start_game_{room_id}")],
                        [InlineKeyboardButton("Cancel Room", callback_data=f"cancel_room_{room_id}")],
                        [InlineKeyboardButton("Invite Friends", url=f"https://t.me/share/url?url=Join my {get_game_name(game_type)} game room! Room ID: {room_id}")],
                        [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                    ]
                    host_markup = InlineKeyboardMarkup(host_keyboard)
                    
                    context.bot.send_message(
                        chat_id=room["host"],
                        text=f"New player {username} has joined your room!\n\nGame: {get_game_name(game_type)}\nRoom ID: {room_id}",
                        reply_markup=host_markup
                    )
                except Exception as e:
                    logger.error(f"Failed to send message to host {room['host']}: {e}")
                
                player_keyboard = [
                    [InlineKeyboardButton("Invite Friends", url=f"https://t.me/share/url?url=Join my {get_game_name(game_type)} game room! Room ID: {room_id}")],
                    [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                ]
                player_markup = InlineKeyboardMarkup(player_keyboard)
                
                # notify current player of successful join
                query.edit_message_text(
                    f"You have successfully joined room {room_id}!\nGame: {get_game_name(game_type)}\nHost: {room.get('host_name', 'Unknown')}",
                    reply_markup=player_markup
                )
            else:
                query.edit_message_text(
                    f"You are already in room {room_id}!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]])
                )
        elif waiting_players[game_type] and waiting_players[game_type][0] != user_id:
            matched_player_id = waiting_players[game_type].pop(0)
            
            # get matched player's username
            matched_player_name = None
            try:
                matched_player = context.bot.get_chat(matched_player_id)
                matched_player_name = matched_player.username or matched_player.first_name
            except Exception as e:
                logger.error(f"Failed to get info for player {matched_player_id}: {e}")
                matched_player_name = "Unknown Player"
            
            room_id = generate_room_id()
            active_rooms[game_type][room_id] = {
                "host": matched_player_id,
                "host_name": matched_player_name,
                "players": [matched_player_id, user_id],
                "player_names": [matched_player_name, username],
                "status": "matched"
            }
            
            # notify matched player
            try:
                keyboard_for_matched = [[InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]]
                markup_for_matched = InlineKeyboardMarkup(keyboard_for_matched)
                context.bot.send_message(
                    chat_id=matched_player_id,
                    text=f"You have been matched with {username}!\nGame: {get_game_name(game_type)}\nRoom ID: {room_id}\nThe game will start soon...",
                    reply_markup=markup_for_matched
                )
            except Exception as e:
                logger.error(f"Failed to send message to player {matched_player_id}: {e}")
            
            # current player's interface
            keyboard = [
                [InlineKeyboardButton("Start Game", callback_data=f"start_game_{room_id}")],
                [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # send message to current player
            try:
                query.edit_message_text(
                    text=f"You have been matched with {matched_player_name}!\nGame: {get_game_name(game_type)}\nRoom ID: {room_id}\nClick the Start Game button to begin!",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Failed to edit message: {e}")
        else:
            # add user to waiting list
            if user_id not in waiting_players[game_type]:
                waiting_players[game_type].append(user_id)
                
            # if no available rooms or waiting players, prompt user to create a room
            if len(waiting_players[game_type]) == 1:  # Only current user is waiting
                keyboard = [
                    [InlineKeyboardButton("Create Room", callback_data=CREATE_GAME)],
                    [InlineKeyboardButton("Cancel Match", callback_data=CANCEL_MATCH)],
                    [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                query.edit_message_text(
                    f"There are no available {get_game_name(game_type)} rooms or waiting players.\nYou can create a new room or wait for other players.",
                    reply_markup=reply_markup
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("Cancel Match", callback_data=CANCEL_MATCH)],
                    [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                query.edit_message_text(
                    f"Matching you with an opponent for {get_game_name(game_type)}...\nPlease wait, you will be notified when a player joins.",
                    reply_markup=reply_markup
                )
    
    elif action == PLAY_WITH_GPT:
        if game_type in [TIC_TAC_TOE, GO, BLACKJACK]:
            room_id = generate_room_id()
            active_rooms[game_type][room_id] = {
                "host": user_id,
                "host_name": username,
                "players": [user_id, "GPT"],
                "player_names": [username, "GPT AI"],
                "status": "with_gpt",
                "gpt_state": {}
            }
            
            # add first/second move choice for Tic Tac Toe
            if game_type == TIC_TAC_TOE:
                keyboard = [
                    [InlineKeyboardButton("I go first (X)", callback_data=f"start_game_{room_id}")],
                    [InlineKeyboardButton("GPT goes first (O)", callback_data=f"gpt_first_{room_id}")],
                    [InlineKeyboardButton("Cancel Room", callback_data=f"cancel_room_{room_id}")],
                    [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("Start Game", callback_data=f"start_game_{room_id}")],
                    [InlineKeyboardButton("Cancel Room", callback_data=f"cancel_room_{room_id}")],
                    [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                ]
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(
                f"You have started a {get_game_name(game_type)} game with GPT!\nRoom ID: {room_id}\n\nCurrent players:\n1. {username} (Host)\n2. GPT AI",
                reply_markup=reply_markup
            )
    
    elif action == CANCEL_MATCH:
        if user_id in waiting_players[game_type]:
            waiting_players[game_type].remove(user_id)
        return start(update, context)
    
    # starting a game
    elif action.startswith("start_game_"):
        room_id = action.split("_")[-1]
        for game, rooms in active_rooms.items():
            if room_id in rooms and rooms[room_id]["host"] == user_id:
                room = rooms[room_id]
                room["status"] = "playing"
                if game == TIC_TAC_TOE:
                    start_tictactoe_game(update, context, room_id, room)
                    return SELECTING_GAME
                elif game == BLACKJACK:
                    start_blackjack_game(update, context, room_id, room)
                    return SELECTING_GAME
                elif game == GO:
                    start_go_game(update, context, room_id, room)
                    return SELECTING_GAME
                elif game == WHO_IS_SPY:
                    start_spy_game(update, context, room_id, room)
                    return SELECTING_GAME
                else:
                    player_list = "\n".join([f"{i+1}. {name}{' (Host)' if room['host'] == pid else ''}" 
                                       for i, (name, pid) in enumerate(zip(room["player_names"], room["players"]))])
                    keyboard = [
                        [InlineKeyboardButton("End Game", callback_data=f"end_game_{room_id}")],
                        [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    query.edit_message_text(
                        f"The game has started!\nGame: {get_game_name(game)}\nRoom ID: {room_id}\n\nPlayers:\n{player_list}\n\n(Game logic not implemented)",
                        reply_markup=reply_markup
                    )
                    
                    for player_id in room["players"]:
                        if isinstance(player_id, str) and player_id == "GPT":
                            continue
                        if player_id != user_id:
                            try:
                                context.bot.send_message(
                                    chat_id=player_id,
                                    text=f"The game has started!\nGame: {get_game_name(game)}\nRoom ID: {room_id}\n\nPlayers:\n{player_list}\n\n(Game logic not implemented)",
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]])
                                )
                            except Exception as e:
                                logger.error(f"Failed to send message to player {player_id}: {e}")
                    return SELECTING_GAME
                    
    # GPT first move
    elif action.startswith("gpt_first_"):
        room_id = action.split("_")[-1]
        room = active_rooms[TIC_TAC_TOE].get(room_id)
        if room and room["host"] == user_id:
            room["status"] = "playing"
            # set current turn to GPT
            room["current_turn"] = "GPT"
            start_tictactoe_game(update, context, room_id, room)
            return SELECTING_GAME
    
    elif action.startswith("cancel_room_"):
        room_id = action.split("_")[-1]
        for game, rooms in active_rooms.items():
            if room_id in rooms and rooms[room_id]["host"] == user_id:
                room = rooms[room_id]
                for player_id in room["players"]:
                    if isinstance(player_id, str) and player_id == "GPT":
                        continue
                    if player_id != user_id:
                        try:
                            context.bot.send_message(
                                chat_id=player_id,
                                text=f"The host has canceled room {room_id}.",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]])
                            )
                        except Exception as e:
                            logger.error(f"Failed to send message to player {player_id}: {e}")
                del rooms[room_id]
                query.edit_message_text(
                    f"You have successfully canceled room {room_id}.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]])
                )
                return SELECTING_GAME
    
    elif action.startswith("end_game_"):
        room_id = action.split("_")[-1]
        for game, rooms in active_rooms.items():
            if room_id in rooms and rooms[room_id]["host"] == user_id:
                room = rooms[room_id]
                for player_id in room["players"]:
                    if isinstance(player_id, str) and player_id == "GPT":
                        continue
                    if player_id != user_id:
                        try:
                            context.bot.send_message(
                                chat_id=player_id,
                                text=f"The host has ended the game. Room {room_id} is now closed.",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]])
                            )
                        except Exception as e:
                            logger.error(f"Failed to send message to player {player_id}: {e}")
                del rooms[room_id]
                query.edit_message_text(
                    f"The game has ended! Room {room_id} is now closed.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]])
                )
                return SELECTING_GAME
    
    return SELECTING_GAME


def join_room(update: Update, context: CallbackContext) -> None:
    """Handle /join command to join a specific room"""
    if not context.args:
        update.message.reply_text("Please provide a room ID, e.g., /join ABC123")
        return

    room_id = context.args[0].upper()
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    for game_type, rooms in active_rooms.items():
        if room_id in rooms:
            room = rooms[room_id]
            if room["status"] == "playing":
                update.message.reply_text("Sorry, the game in this room has already started.")
                return
                
            if game_type == WHO_IS_SPY and len(room["players"]) >= 8:
                update.message.reply_text("Sorry, the room is full (maximum 8 players).")
                return
            elif game_type != WHO_IS_SPY and len(room["players"]) >= 2:
                update.message.reply_text("Sorry, the room is full.")
                return
            
            is_new_player = False
            if user_id not in room["players"]:
                room["players"].append(user_id)
                room["player_names"].append(username)
                is_new_player = True
            
            player_list = "\n".join([f"{i+1}. {name}{' (Host)' if room['host'] == pid else ''}" 
                                   for i, (name, pid) in enumerate(zip(room["player_names"], room["players"]))])
            
            if is_new_player:
                host_keyboard = [
                    [InlineKeyboardButton("Start Game", callback_data=f"start_game_{room_id}")],
                    [InlineKeyboardButton("Cancel Room", callback_data=f"cancel_room_{room_id}")],
                    [InlineKeyboardButton("Invite Friends", url=f"https://t.me/share/url?url=Join my {get_game_name(game_type)} game room! Room ID: {room_id}")],
                    [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                ]
                host_markup = InlineKeyboardMarkup(host_keyboard)
                
                player_keyboard = [
                    [InlineKeyboardButton("Invite Friends", url=f"https://t.me/share/url?url=Join my {get_game_name(game_type)} game room! Room ID: {room_id}")],
                    [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
                ]
                player_markup = InlineKeyboardMarkup(player_keyboard)
                
                for player_id in room["players"]:
                    if isinstance(player_id, str) and player_id == "GPT":
                        continue
                    try:
                        if player_id == room["host"]:
                            context.bot.send_message(
                                chat_id=player_id,
                                text=f"New player {username} has joined your room!\n\nGame: {get_game_name(game_type)}\nRoom ID: {room_id}\n\nCurrent players:\n{player_list}",
                                reply_markup=host_markup
                            )
                        elif player_id != user_id:
                            context.bot.send_message(
                                chat_id=player_id,
                                text=f"New player {username} has joined the room!\n\nGame: {get_game_name(game_type)}\nRoom ID: {room_id}\n\nCurrent players:\n{player_list}",
                                reply_markup=player_markup
                            )
                    except Exception as e:
                        logger.error(f"Failed to send message to player {player_id}: {e}")
            
            player_keyboard = [
                [InlineKeyboardButton("Invite Friends", url=f"https://t.me/share/url?url=Join my {get_game_name(game_type)} game room! Room ID: {room_id}")],
                [InlineKeyboardButton("Back to Main Menu", callback_data=BACK_TO_MAIN)]
            ]
            player_markup = InlineKeyboardMarkup(player_keyboard)
            
            join_message = "You have successfully joined the room" if is_new_player else "You are already in the room"
            update.message.reply_text(
                f"{join_message} {room_id}!\nGame: {get_game_name(game_type)}\nHost: {room.get('host_name', 'Unknown')}\n\nCurrent players:\n{player_list}",
                reply_markup=player_markup
            )
            return

    update.message.reply_text(f"Could not find a game room with ID {room_id}. Please check if the ID is correct.")


def list_rooms(update: Update, context: CallbackContext) -> None:
    """Handle /rooms command to list active rooms"""
    response = "Current active game rooms:\n\n"
    found_rooms = False

    for game_type, rooms in active_rooms.items():
        if rooms:
            response += f"[{get_game_name(game_type)}]\n"
            for room_id, room_data in rooms.items():
                player_count = len(room_data["players"])
                max_players = 8 if game_type == WHO_IS_SPY else 2
                status = "Waiting" if room_data["status"] == "waiting" else "In Game"
                response += f"- Room ID: {room_id} | Players: {player_count}/{max_players} | Status: {status}\n"
            response += "\n"
            found_rooms = True

    if not found_rooms:
        response = "There are no active game rooms. Use /start to create a new room!"
    
    update.message.reply_text(response)


def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel and end the session"""
    update.message.reply_text("Operation canceled. Use /start to begin again.")
    return ConversationHandler.END


def handle_record_command(update: Update, context: CallbackContext):
    """Handle user command to query win/loss/draw records"""
    user_id = update.effective_user.id
    try:
        message = get_user_record(user_id)
        update.message.reply_text(message)
    except Exception as e:
        update.message.reply_text(f"Failed to retrieve records: {e}")


def main() -> None:
    """Start the bot"""
    updater = Updater(token=os.environ['GAMEBOT_TOKEN'])
    dispatcher = updater.dispatcher

    # modify ConversationHandler to add filters for callback data prefixes
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_GAME: [
                CallbackQueryHandler(game_selection, pattern=r'^(?!ttt_move_|bj_hit_|bj_stand_|go_move_|go_pass_|gpt_first_|spy_).+')
            ],
            GAME_ACTION: [
                CallbackQueryHandler(game_action, pattern=r'^(?!ttt_move_|bj_hit_|bj_stand_|go_move_|go_pass_|gpt_first_|spy_).+')
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ]
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler("join", join_room))
    dispatcher.add_handler(CommandHandler("rooms", list_rooms))
    dispatcher.add_handler(CommandHandler("say", say_message))
    dispatcher.add_handler(CommandHandler("vote", start_vote))
    dispatcher.add_handler(CommandHandler("record", handle_record_command))

    # add callback handlers for specific games
    dispatcher.add_handler(CallbackQueryHandler(handle_ttt_move, pattern=r"^ttt_move_"))  # Tic Tac Toe
    dispatcher.add_handler(CallbackQueryHandler(handle_blackjack_action, pattern=r"^bj_(hit|stand)_"))  # Blackjack
    dispatcher.add_handler(CallbackQueryHandler(handle_go_move, pattern=r"^go_(move|pass)_"))  # Go
    dispatcher.add_handler(CallbackQueryHandler(handle_spy_discussion, pattern=r"^spy_discuss_"))  # Who is the Spy (discussion)
    dispatcher.add_handler(CallbackQueryHandler(handle_spy_vote, pattern=r"^spy_vote_"))  # Who is the Spy (vote)

    updater.start_polling()
    updater.idle()


# if __name__ == '__main__':
#     main()