from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import random
from utils.constants import *
from database import update_user_record

def create_deck():
    """Create a deck of cards"""
    return [(rank, suit) for suit in SUITS for rank in RANKS]


def calculate_score(hand):
    """Calculate the score of a hand, considering A as 1 or 11"""
    score = 0
    aces = 0
    for rank, _ in hand:
        if rank in ['J', 'Q', 'K']:
            score += 10
        elif rank == 'A':
            aces += 1
            score += 11  # count A as 11 initially
        else:
            score += int(rank)

    # adjust A to 1 if score exceeds 21
    while score > 21 and aces:
        score -= 10
        aces -= 1

    return score


def generate_blackjack_keyboard(room_id, player_id, room):
    """Generate action buttons for Blackjack"""
    keyboard = []
    
    # check if the player is bust or has stood
    player_idx = room["players"].index(player_id) if player_id in room["players"] else -1
    player_status = room.get("player_status", [])
    
    if player_idx >= 0 and player_idx < len(player_status) and (player_status[player_idx] == "bust" or player_status[player_idx] == "stand"):
        # player is bust or has stood, show only return to main menu
        keyboard.append([InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)])
    elif player_id == room.get("current_turn"):
        # player's turn
        keyboard.append([
            InlineKeyboardButton("Hit", callback_data=f"bj_hit_{room_id}"),
            InlineKeyboardButton("Stand", callback_data=f"bj_stand_{room_id}")
        ])
        keyboard.append([InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)])
    else:
        # not the player's turn
        keyboard.append([InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)])
    
    return InlineKeyboardMarkup(keyboard)


def format_card(card):
    """Format a card for display"""
    rank, suit = card
    return f"{rank}{suit}"


def format_hand(hand):
    """Format a player's hand for display"""
    return " ".join([format_card(card) for card in hand])


def start_blackjack_game(update: Update, context: CallbackContext, room_id, room):
    """Initialize Blackjack game, deal cards, and notify players"""
    # initialize deck
    room["deck"] = create_deck()
    random.shuffle(room["deck"])
    
    # initialize player hands and statuses
    room["hands"] = [[] for _ in range(len(room["players"]))]
    room["player_status"] = ["playing" for _ in range(len(room["players"]))]
    
    # deal two cards to each player
    for i, _ in enumerate(room["players"]):
        for _ in range(2):
            if room["deck"]:
                card = room["deck"].pop()
                room["hands"][i].append(card)
    
    # set the current turn to the host
    room["current_turn"] = room["host"]
    room["round"] = 1
    
    # build game state info
    game_info = format_blackjack_game_state(room_id, room)
    
    query = update.callback_query
    reply_markup = generate_blackjack_keyboard(room_id, room["host"], room)
    query.edit_message_text(game_info, reply_markup=reply_markup)
    
    # send game state to other players
    for i, player_id in enumerate(room["players"]):
        if player_id == room["host"]:
            continue
        
        # skip GPT players for now
        if player_id == "GPT":
            continue
        
        try:
            player_reply_markup = generate_blackjack_keyboard(room_id, player_id, room)
            context.bot.send_message(
                chat_id=player_id,
                text=game_info,
                reply_markup=player_reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to player {player_id}: {e}")


def format_blackjack_game_state(room_id, room):
    """Format Blackjack game state info"""
    game_info = f"Blackjack game started!\nRoom ID: {room_id}\nCurrent round: {room.get('round', 1)}\n\nPlayer statuses:\n"
    
    for i, (player_id, player_name) in enumerate(zip(room["players"], room["player_names"])):
        hand = room["hands"][i]
        score = calculate_score(hand)
        status = room["player_status"][i]
        status_text = {
            "playing": "Playing",
            "stand": "Stand",
            "bust": "Bust"
        }.get(status, status)
        
        turn_indicator = "➡️ " if player_id == room.get("current_turn") else ""
        game_info += f"{turn_indicator}{i+1}. {player_name}"
        game_info += f" ({status_text})"
        game_info += f": {format_hand(hand)} = {score} points"
        if status == "bust":
            game_info += " (Bust!)"
        game_info += "\n"
    
    return game_info


def handle_blackjack_action(update: Update, context: CallbackContext) -> None:
    """Handle hit/stand actions in Blackjack"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    
    if len(data) != 3:
        return
        
    action_type = data[1]
    room_id = data[2]
    
    room = active_rooms[BLACKJACK].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("The room does not exist or the game has ended.")
        return
    
    user_id = update.effective_user.id
    
    # check if it's the player's turn
    if user_id != room.get("current_turn"):
        query.answer("It's not your turn!", show_alert=True)
        return
    
    player_idx = room["players"].index(user_id)
    
    # handle player actions
    if action_type == "hit":
        # player chooses to hit
        if room["deck"]:
            card = room["deck"].pop()
            room["hands"][player_idx].append(card)
            score = calculate_score(room["hands"][player_idx])
            
            if score > 21:
                # player busts
                room["player_status"][player_idx] = "bust"
                query.answer(f"You drew {format_card(card)}, total score {score}, you busted!", show_alert=True)
            else:
                query.answer(f"You drew {format_card(card)}, current total score {score}", show_alert=True)
    
    elif action_type == "stand":
        # player chooses to stand
        room["player_status"][player_idx] = "stand"
        query.answer("You chose to stand", show_alert=True)
    
    # move to the next player
    next_player_idx = find_next_player(room)
    
    # check if the game is over
    game_over = check_blackjack_game_over(room)
    
    if game_over:
        # determine the winner
        room["status"] = "finished"
        winner_info = determine_blackjack_winner(room)
        game_info = format_blackjack_game_state(room_id, room) + "\n\n" + winner_info
        
        # record results
        max_score = 0
        winners = []
        for i, status in enumerate(room["player_status"]):
            if status != "bust":
                score = calculate_score(room["hands"][i])
                if score > max_score:
                    max_score = score
                    winners = [i]
                elif score == max_score:
                    winners.append(i)
        
        for i, player_id in enumerate(room["players"]):
            username = room["player_names"][i]
            if i in winners:
                update_user_record(player_id, username, "Blackjack", "win")
            elif room["player_status"][i] == "bust":
                update_user_record(player_id, username, "Blackjack", "loss")
            else:
                update_user_record(player_id, username, "Blackjack", "draw")
        
        # send results to all players
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]])
        query.edit_message_text(game_info, reply_markup=reply_markup)
        
        for player_id in room["players"]:
            if player_id == user_id or player_id == "GPT":
                continue
            try:
                context.bot.send_message(
                    chat_id=player_id,
                    text=game_info,
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Failed to send message to player {player_id}: {e}")
    else:
        # update the current player
        if next_player_idx != -1:
            room["current_turn"] = room["players"][next_player_idx]
        
        # increment round if back to the first player
        if next_player_idx == 0:
            room["round"] = room.get("round", 1) + 1
        
        # update game state and send to all players
        game_info = format_blackjack_game_state(room_id, room)
        reply_markup = generate_blackjack_keyboard(room_id, user_id, room)
        
        try:
            query.edit_message_text(game_info, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
        
        for player_id in room["players"]:
            if player_id == user_id or player_id == "GPT":
                continue
            try:
                player_reply_markup = generate_blackjack_keyboard(room_id, player_id, room)
                context.bot.send_message(
                    chat_id=player_id,
                    text=game_info,
                    reply_markup=player_reply_markup
                )
            except Exception as e:
                logger.error(f"Failed to send message to player {player_id}: {e}")
        
        # check if it's GPT's turn, if so, make a decision
        if room["current_turn"] == "GPT":
            gpt_make_blackjack_decision(context, room_id, room)


def find_next_player(room):
    """Find the next player to act"""
    current_idx = room["players"].index(room["current_turn"])
    
    # check from the next player
    for i in range(1, len(room["players"]) + 1):
        next_idx = (current_idx + i) % len(room["players"])
        if room["player_status"][next_idx] == "playing":
            return next_idx
    
    # no players left to act
    return -1


def check_blackjack_game_over(room):
    """Check if the Blackjack game is over"""
    return all(status in ["stand", "bust"] for status in room["player_status"])


def determine_blackjack_winner(room):
    """Determine the winner of the Blackjack game"""
    max_score = 0
    winners = []
    
    # find the highest score among players who didn't bust
    for i, status in enumerate(room["player_status"]):
        if status != "bust":
            score = calculate_score(room["hands"][i])
            if score > max_score:
                max_score = score
                winners = [i]
            elif score == max_score:
                winners.append(i)
    
    if not winners:
        return "All players busted, no winner!"
    
    if len(winners) == 1:
        winner_idx = winners[0]
        return f"The winner is {room['player_names'][winner_idx]} with a score of {max_score}!"
    else:
        winner_names = [room["player_names"][idx] for idx in winners]
        return f"It's a tie! Winners: {', '.join(winner_names)} with a score of {max_score}!"
    

def gpt_make_blackjack_decision(context, room_id, room):
    """Let GPT make a decision in the Blackjack game"""
    # find GPT's index
    gpt_idx = room["players"].index("GPT")
    gpt_state = room["gpt_state"]
    
    # get GPT's hand and score
    gpt_hand = room["hands"][gpt_idx]
    gpt_score = calculate_score(gpt_hand)
    
    # GPT's Blackjack strategy:
    # - Stand on 17 or higher
    # - Hit on 16 or lower
    decision = "stand" if gpt_score >= 17 else "hit"
    
    # If GPT decides to hit
    if decision == "hit":
        if room["deck"]:
            card = room["deck"].pop()
            room["hands"][gpt_idx].append(card)
            new_score = calculate_score(room["hands"][gpt_idx])
            
            # check if GPT busted
            if new_score > 21:
                room["player_status"][gpt_idx] = "bust"
                decision_text = f"GPT AI chose to hit, drew {format_card(card)}, total score {new_score}, busted!"
            else:
                decision_text = f"GPT AI chose to hit, drew {format_card(card)}, current total score {new_score}"
    else:
        # GPT decides to stand
        room["player_status"][gpt_idx] = "stand"
        decision_text = f"GPT AI chose to stand, total score {gpt_score}"
    
    # move to the next player
    next_player_idx = find_next_player(room)
    
    # check if the game is over
    game_over = check_blackjack_game_over(room)
    
    # get the host ID to send messages
    host_id = room["host"]
    
    # notify the host of GPT's decision
    try:
        if game_over:
            # game over, determine the winner
            room["status"] = "finished"
            winner_info = determine_blackjack_winner(room)
            game_info = format_blackjack_game_state(room_id, room) + "\n\n" + decision_text + "\n\n" + winner_info

            # record results
            max_score = 0
            winners = []
            for i, status in enumerate(room["player_status"]):
                if status != "bust":
                    score = calculate_score(room["hands"][i])
                    if score > max_score:
                        max_score = score
                        winners = [i]
                    elif score == max_score:
                        winners.append(i)
        
            for i, player_id in enumerate(room["players"]):
                username = room["player_names"][i]
                if i in winners:
                    update_user_record(player_id, username, "Blackjack", "win")
                elif room["player_status"][i] == "bust":
                    update_user_record(player_id, username, "Blackjack", "loss")
                else:
                    update_user_record(player_id, username, "Blackjack", "draw")
            
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Return to Main Menu", callback_data=BACK_TO_MAIN)]])
            context.bot.send_message(
                chat_id=host_id,
                text=game_info,
                reply_markup=reply_markup
            )
        else:
            # update the current player
            if next_player_idx != -1:
                room["current_turn"] = room["players"][next_player_idx]
            
            # increment round if back to the first player
            if next_player_idx == 0:
                room["round"] = room.get("round", 1) + 1
            
            # update game state
            game_info = format_blackjack_game_state(room_id, room) + "\n\n" + decision_text
            reply_markup = generate_blackjack_keyboard(room_id, host_id, room)
            
            context.bot.send_message(
                chat_id=host_id,
                text=game_info,
                reply_markup=reply_markup
            )
            
            # if it's GPT's turn again, recursively call this function
            if room["current_turn"] == "GPT":
                gpt_make_blackjack_decision(context, room_id, room)
    except Exception as e:
        logger.error(f"Failed to send GPT decision message: {e}")