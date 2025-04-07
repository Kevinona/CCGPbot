from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import random
from utils.constants import *
from database import update_user_record

def start_spy_game(update: Update, context: CallbackContext, room_id, room):
    """Initialize Who is the Spy game and assign roles"""
    # check if there are at least 3 players
    if len(room["players"]) < 3:
        query = update.callback_query
        query.edit_message_text(
            f"The game requires at least 3 players, but only {len(room['players'])} are present.\nPlease invite more players to join.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]
            ])
        )
        return
    
    # set initial game state
    room["status"] = "playing"
    room["round"] = 1
    room["phase"] = "identity"  # identity assignment phase
    room["votes"] = {}  # player votes
    room["messages"] = []  # discussion messages
    room["eliminated"] = []  # eliminated players
    
    # randomly select a spy
    spy_idx = random.randrange(len(room["players"]))
    room["spy"] = room["players"][spy_idx]
    
    # use GPT to generate two related but different words
    chatgpt = HKBU_ChatGPT()
    prompt = "Generate two related but slightly different English words for the 'Who is the Spy' game. Format: 'Civilian word:Spy word'. No additional explanation. Example: 'Apple:Pear' or 'Cinema:Theater'."
    
    try:
        response = chatgpt.submit(prompt)
        # parse response to get two words
        words = response.strip().split(":")
        if len(words) != 2:
            # use default words if format is incorrect
            words = ["Apple", "Pear"]
    except Exception as e:
        logger.error(f"Failed to generate words: {e}")
        # use default words
        words = ["Apple", "Pear"]
    
    # save words
    room["word_civilian"] = words[0]
    room["word_spy"] = words[1]
    
    # assign roles and words to players
    for i, player_id in enumerate(room["players"]):
        if player_id == room["spy"]:
            room[f"word_{player_id}"] = room["word_spy"]
        else:
            room[f"word_{player_id}"] = room["word_civilian"]
    
    # notify all players of their roles and words
    query = update.callback_query
    
    # build player list
    player_list = "\n".join([f"{i+1}. {name}{' (Host)' if room['host'] == pid else ''}" 
                        for i, (name, pid) in enumerate(zip(room["player_names"], room["players"]))])
    
    # notify all players
    for player_id in room["players"]:
        word = room[f"word_{player_id}"]
        is_spy = player_id == room["spy"]
        
        message = (
            f"The game 'Who is the Spy' has started!\n"
            f"Room ID: {room_id}\n\n"
            f"Players:\n{player_list}\n\n"
            f"Your role: {'Spy' if is_spy else 'Civilian'}\n"
            f"Your word: {word}\n\n"
            f"Game rules:\n"
            f"1. Each player describes their word without directly saying it.\n"
            f"2. The spy's goal is to hide their identity, while civilians try to find the spy.\n"
            f"3. After each round of discussion, everyone votes to eliminate a player.\n"
            f"4. If the spy is eliminated, civilians win. If only the spy and one civilian remain, the spy wins."
        )
        
        # build buttons
        keyboard = [
            [InlineKeyboardButton("Start Discussion", callback_data=f"spy_discuss_{room_id}")],
            [InlineKeyboardButton("Skip Discussion and Vote", callback_data=f"spy_vote_{room_id}")],
            [InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            if player_id == update.effective_user.id:
                # update current message
                query.edit_message_text(message, reply_markup=reply_markup)
            else:
                # send new message to other players
                context.bot.send_message(
                    chat_id=player_id,
                    text=message,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Failed to send message to player {player_id}: {e}")
    
    return SELECTING_GAME


def handle_spy_discussion(update: Update, context: CallbackContext) -> None:
    """Handle discussion phase in Who is the Spy game"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    
    if len(data) < 3:
        return
    
    # format: spy_discuss_{room_id}
    action = data[1]
    room_id = data[2]
    
    # check if the room exists
    room = active_rooms[WHO_IS_SPY].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text(
            "The room does not exist or the game has ended.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]])
        )
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # check if the user is a valid player in the room
    if user_id not in room["players"] or user_id in room["eliminated"]:
        query.answer("You are not a valid player in this room!", show_alert=True)
        return
    
    # switch to discussion phase
    room["phase"] = "discussion"
    
    # build a list of active players (excluding eliminated players)
    active_players = []
    for i, (name, pid) in enumerate(zip(room["player_names"], room["players"])):
        if pid not in room["eliminated"]:
            active_players.append((i, name, pid))
    
    player_list = "\n".join([f"{i+1}. {name}{' (Host)' if room['host'] == pid else ''}" 
                             for i, name, pid in active_players])
    
    # build discussion message
    message = (
        f"Who is the Spy - Discussion Phase\n"
        f"Room ID: {room_id}, Round {room['round']}\n\n"
        f"Active players:\n{player_list}\n\n"
        f"Use the /say <content> command to describe your word.\n"
        f"Example: /say This thing is round and edible.\n\n"
        f"Any player can use the /vote command to start the voting phase at any time."
    )
    
    # add current discussion records
    if room["messages"]:
        message += "\n\nCurrent discussion records:"
        for msg in room["messages"]:
            message += f"\n{msg['player']}: {msg['content']}"
    
    # build buttons
    keyboard = [
        [InlineKeyboardButton("Start Voting", callback_data=f"spy_vote_{room_id}")],
        [InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # notify all players in the game
    for player_id in room["players"]:
        if player_id in room["eliminated"]:
            continue
            
        try:
            if player_id == user_id:
                # update the current message
                query.edit_message_text(message, reply_markup=reply_markup)
            else:
                # send a new message to other players
                context.bot.send_message(
                    chat_id=player_id,
                    text=message,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Failed to send message to player {player_id}: {e}")


def say_message(update: Update, context: CallbackContext) -> None:
    """Handle /say command for players to describe their word"""
    if not context.args:
        update.message.reply_text("Please provide your description, e.g., /say This thing is round and edible.")
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    message_content = " ".join(context.args)
    
    # find the room the player is in
    player_room = None
    player_room_id = None
    
    for room_id, room in active_rooms[WHO_IS_SPY].items():
        if user_id in room["players"] and room["status"] == "playing" and room["phase"] == "discussion" and user_id not in room["eliminated"]:
            player_room = room
            player_room_id = room_id
            break
    
    if not player_room:
        update.message.reply_text("You are not in any discussion phase of a 'Who is the Spy' game.")
        return
    
    # record the player's message
    player_room["messages"].append({
        "player": username,
        "player_id": user_id,
        "content": message_content
    })
    
    # build the updated discussion message
    active_players = []
    for i, (name, pid) in enumerate(zip(player_room["player_names"], player_room["players"])):
        if pid not in player_room["eliminated"]:
            active_players.append((i, name, pid))
    
    player_list = "\n".join([f"{i+1}. {name}{' (Host)' if player_room['host'] == pid else ''}" 
                         for i, name, pid in active_players])
    
    message = (
        f"Who is the Spy - Discussion Phase\n"
        f"Room ID: {player_room_id}, Round {player_room['round']}\n\n"
        f"Active players:\n{player_list}\n\n"
        f"Use the /say <content> command to describe your word.\n"
        f"Example: /say This thing is round and edible.\n\n"
        f"Any player can use the /vote command to start the voting phase at any time.\n\n"
        f"Current discussion records:"
    )
    
    for msg in player_room["messages"]:
        message += f"\n{msg['player']}: {msg['content']}"
    
    # build buttons
    keyboard = [
        [InlineKeyboardButton("Start Voting", callback_data=f"spy_vote_{player_room_id}")],
        [InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # notify all players in the game
    for player_id in player_room["players"]:
        if player_id in player_room["eliminated"]:
            continue
            
        try:
            context.bot.send_message(
                chat_id=player_id,
                text=message,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to player {player_id}: {e}")
    
    # confirm the message has been sent
    update.message.reply_text("Your description has been sent to all players.")


def handle_spy_vote(update: Update, context: CallbackContext) -> None:
    """Handle voting phase in Who is the Spy game"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    
    if len(data) < 3:
        return
    
    # format: spy_vote_{room_id} or spy_vote_{room_id}_{target_player_id}
    action = data[1]  # vote
    room_id = data[2]
    target_player_id = data[3] if len(data) > 3 else None
    
    # check if the room exists
    room = active_rooms[WHO_IS_SPY].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("The room does not exist or the game has ended.", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]]))
        return
    
    user_id = update.effective_user.id
    
    # check if the user is in the room
    if user_id not in room["players"] or user_id in room["eliminated"]:
        query.answer("You are not a valid player in this room!", show_alert=True)
        return
    
    # handle voting
    if target_player_id:
        # player selected a target to vote for
        target_player_id = int(target_player_id)
        
        # record the vote
        room["votes"][user_id] = target_player_id
        
        # check if all players have voted
        active_players = [pid for pid in room["players"] if pid not in room["eliminated"]]
        all_voted = all(pid in room["votes"] for pid in active_players)
        
        if all_voted:
            # all players have voted, tally the results
            return tally_votes(update, context, room_id, room)
        else:
            # notify the player that their vote has been recorded
            player_name = ""
            for i, pid in enumerate(room["players"]):
                if pid == target_player_id:
                    player_name = room["player_names"][i]
                    break
                    
            query.edit_message_text(
                f"You have voted for {player_name}.\nWaiting for other players to finish voting...",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]])
            )
            
            # notify other players that a vote has been cast
            voted_count = len(room["votes"])
            total_count = len(active_players)
            
            for player_id in active_players:
                if player_id == user_id or player_id in room["votes"]:
                    continue
                
                try:
                    context.bot.send_message(
                        chat_id=player_id,
                        text=f"A player has voted! {voted_count}/{total_count} players have voted."
                    )
                except Exception as e:
                    logger.error(f"Failed to send message to player {player_id}: {e}")
    else:
        # start the voting phase
        room["phase"] = "voting"
        room["votes"] = {}  # clear previous votes
        
        # build a list of active players
        active_players = []
        for i, (name, pid) in enumerate(zip(room["player_names"], room["players"])):
            if pid not in room["eliminated"] and pid != user_id:  # cannot vote for yourself
                active_players.append((i, name, pid))
        
        # build voting buttons
        keyboard = []
        for i, name, pid in active_players:
            keyboard.append([InlineKeyboardButton(name, callback_data=f"spy_vote_{room_id}_{pid}")])
        
        keyboard.append([InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # build voting message
        message = (
            f"Who is the Spy - Voting Phase\n"
            f"Room ID: {room_id}, Round {room['round']}\n\n"
            f"Select the player you think is the spy:"
        )
        
        # update the current message
        query.edit_message_text(message, reply_markup=reply_markup)
        
        # notify other players that voting has started
        for player_id in room["players"]:
            if player_id in room["eliminated"] or player_id == user_id:
                continue
                
            try:
                context.bot.send_message(
                    chat_id=player_id,
                    text="The voting phase has started! Select the player you think is the spy.",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Failed to send message to player {player_id}: {e}")


def tally_votes(update: Update, context: CallbackContext, room_id, room):
    """Tally votes and determine the eliminated player"""
    # count votes
    vote_counts = {}
    for voter, candidate in room["votes"].items():
        vote_counts[candidate] = vote_counts.get(candidate, 0) + 1
    
    # find the player with the most votes
    max_votes = 0
    eliminated_players = []
    
    for player_id, count in vote_counts.items():
        if count > max_votes:
            max_votes = count
            eliminated_players = [player_id]
        elif count == max_votes:
            eliminated_players.append(player_id)
    
    # if there's a tie, randomly select one player
    eliminated_player_id = random.choice(eliminated_players)
    room["eliminated"].append(eliminated_player_id)
    
    # get the name of the eliminated player
    eliminated_player_name = ""
    for i, pid in enumerate(room["players"]):
        if pid == eliminated_player_id:
            eliminated_player_name = room["player_names"][i]
            break
    
    # check if the game is over
    game_over = False
    winner = None
    
    # count remaining players
    remaining_players = [pid for pid in room["players"] if pid not in room["eliminated"]]
    
    # check if only two players remain and one is the spy
    if len(remaining_players) == 2 and room["spy"] in remaining_players:
        game_over = True
        winner = "spy"
    # check if the spy has been eliminated
    elif eliminated_player_id == room["spy"]:
        game_over = True
        winner = "civilians"
    
    # build vote result message
    vote_result = []
    for i, (name, pid) in enumerate(zip(room["player_names"], room["players"])):
        if pid in vote_counts:
            vote_result.append(f"{name}: {vote_counts[pid]} votes")
    
    # build message
    if game_over:
        message = (
            f"Who is the Spy - Game Over\n"
            f"Room ID: {room_id}\n\n"
            f"Vote results:\n{', '.join(vote_result)}\n\n"
            f"{eliminated_player_name} has been eliminated!\n\n"
        )
        
        # reveal the spy
        spy_name = ""
        for i, pid in enumerate(room["players"]):
            if pid == room["spy"]:
                spy_name = room["player_names"][i]
                break
        
        message += f"The spy was: {spy_name}\n"
        message += f"Civilian word: {room['word_civilian']}\n"
        message += f"Spy word: {room['word_spy']}\n\n"
        
        if winner == "spy":
            message += "The spy wins!"
        else:
            message += "The civilians win!"
        
        keyboard = [
            [InlineKeyboardButton("Start New Game", callback_data=f"start_game_{room_id}")],
            [InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]
        ]
        
        # update room status
        room["status"] = "finished"

        # record results in the database
        for i, player_id in enumerate(room["players"]):
            username = room["player_names"][i]
            if winner == "spy":
                if player_id == room["spy"]:
                    update_user_record(player_id, username, "WhoIsSpy", "win")
                else:
                    update_user_record(player_id, username, "WhoIsSpy", "loss")
            elif winner == "civilians":
                if player_id == room["spy"]:
                    update_user_record(player_id, username, "WhoIsSpy", "loss")
                else:
                    update_user_record(player_id, username, "WhoIsSpy", "win")
    else:
        # proceed to the next round
        room["round"] += 1
        room["phase"] = "discussion"
        room["messages"] = []  # clear discussion records
        
        message = (
            f"Who is the Spy - Round {room['round']}\n"
            f"Room ID: {room_id}\n\n"
            f"Vote results:\n{', '.join(vote_result)}\n\n"
            f"{eliminated_player_name} has been eliminated!\n\n"
            f"The game continues. Start a new round of discussion."
        )
        
        keyboard = [
            [InlineKeyboardButton("Start Discussion", callback_data=f"spy_discuss_{room_id}")],
            [InlineKeyboardButton("Skip Discussion and Vote", callback_data=f"spy_vote_{room_id}")],
            [InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # notify all players of the vote results
    for player_id in room["players"]:
        try:
            if player_id == update.effective_user.id:
                # update the current message
                query = update.callback_query
                query.edit_message_text(message, reply_markup=reply_markup)
            else:
                # send a new message to other players
                context.bot.send_message(
                    chat_id=player_id,
                    text=message,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Failed to send message to player {player_id}: {e}")
    
    return SELECTING_GAME


def start_vote(update: Update, context: CallbackContext) -> None:
    """Handle /vote command to start voting in Who is the Spy game"""
    user_id = update.effective_user.id
    
    # find the room the player is in
    player_room = None
    player_room_id = None
    
    for room_id, room in active_rooms[WHO_IS_SPY].items():
        if (user_id in room["players"] and 
            room["status"] == "playing" and 
            room["phase"] == "discussion" and 
            user_id not in room["eliminated"]):
            player_room = room
            player_room_id = room_id
            break
    
    if not player_room:
        update.message.reply_text("You are not in any discussion phase of a 'Who is the Spy' game.")
        return
    
    # switch to voting phase
    player_room["phase"] = "voting"
    player_room["votes"] = {}  # clear previous votes
    
    # build a list of active players (excluding the current player)
    active_players = []
    for i, (name, pid) in enumerate(zip(player_room["player_names"], player_room["players"])):
        if pid not in player_room["eliminated"] and pid != user_id:  # cannot vote for yourself
            active_players.append((i, name, pid))
    
    # build voting buttons
    keyboard = []
    for i, name, pid in active_players:
        keyboard.append([InlineKeyboardButton(name, callback_data=f"spy_vote_{player_room_id}_{pid}")])
    
    keyboard.append([InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # build voting message
    message = (
        f"Who is the Spy - Voting Phase\n"
        f"Room ID: {player_room_id}, Round {player_room['round']}\n\n"
        f"Select the player you think is the spy:"
    )
    
    # send voting message to the player who initiated the vote
    update.message.reply_text(message, reply_markup=reply_markup)
    
    # notify other players that voting has started
    for player_id in player_room["players"]:
        if player_id in player_room["eliminated"] or player_id == user_id:
            continue
            
        try:
            context.bot.send_message(
                chat_id=player_id,
                text=f"Player {update.effective_user.username or update.effective_user.first_name} has started voting! Select the player you think is the spy.",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to player {player_id}: {e}")