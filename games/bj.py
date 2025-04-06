from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import random
from utils.constants import *  # 导入常量
from database import update_user_record  # 确保导入 update_user_record 函数

def create_deck():
    """创建一副扑克牌"""
    return [(rank, suit) for suit in SUITS for rank in RANKS]

def calculate_score(hand):
    """计算手牌的分数，考虑A可以为1或11"""
    score = 0
    aces = 0
    for rank, _ in hand:
        if rank in ['J', 'Q', 'K']:
            score += 10
        elif rank == 'A':
            aces += 1
            score += 11  # 先将A计为11点
        else:
            score += int(rank)

    # 如果总分超过21并且有A，则将A视为1点
    while score > 21 and aces:
        score -= 10
        aces -= 1

    return score

def generate_blackjack_keyboard(room_id, player_id, room):
    """生成21点游戏的操作按钮"""
    keyboard = []
    
    # 检查玩家是否爆牌或者已经停牌
    player_idx = room["players"].index(player_id) if player_id in room["players"] else -1
    player_status = room.get("player_status", [])
    
    if player_idx >= 0 and player_idx < len(player_status) and (player_status[player_idx] == "bust" or player_status[player_idx] == "stand"):
        # 玩家已爆牌或停牌，只显示返回主菜单
        keyboard.append([InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)])
    elif player_id == room.get("current_turn"):
        # 轮到该玩家出牌
        keyboard.append([
            InlineKeyboardButton("要牌", callback_data=f"bj_hit_{room_id}"),
            InlineKeyboardButton("停牌", callback_data=f"bj_stand_{room_id}")
        ])
        keyboard.append([InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)])
    else:
        # 不是该玩家的回合
        keyboard.append([InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)])
    
    return InlineKeyboardMarkup(keyboard)

def format_card(card):
    """格式化牌面以便显示"""
    rank, suit = card
    return f"{rank}{suit}"

def format_hand(hand):
    """格式化玩家手牌以便显示"""
    return " ".join([format_card(card) for card in hand])

def start_blackjack_game(update: Update, context: CallbackContext, room_id, room):
    """初始化21点游戏，发牌并通知玩家"""
    # 初始化牌组
    room["deck"] = create_deck()
    random.shuffle(room["deck"])
    
    # 初始化玩家手牌和状态
    room["hands"] = [[] for _ in range(len(room["players"]))]
    room["player_status"] = ["playing" for _ in range(len(room["players"]))]
    
    # 给每位玩家发两张牌
    for i, _ in enumerate(room["players"]):
        for _ in range(2):
            if room["deck"]:
                card = room["deck"].pop()
                room["hands"][i].append(card)
    
    # 设置当前回合玩家（从房主开始）
    room["current_turn"] = room["host"]
    room["round"] = 1
    
    # 构建游戏状态信息
    game_info = format_blackjack_game_state(room_id, room)
    
    query = update.callback_query
    reply_markup = generate_blackjack_keyboard(room_id, room["host"], room)
    query.edit_message_text(game_info, reply_markup=reply_markup)
    
    # 发送游戏状态给其他玩家
    for i, player_id in enumerate(room["players"]):
        if player_id == room["host"]:
            continue
        
        # 如果是GPT玩家，直接让其进行决策
        if player_id == "GPT":
            # 当前不是GPT的回合，不需要做任何事
            continue
        
        try:
            player_reply_markup = generate_blackjack_keyboard(room_id, player_id, room)
            context.bot.send_message(
                chat_id=player_id,
                text=game_info,
                reply_markup=player_reply_markup
            )
        except Exception as e:
            logger.error(f"无法发送消息给玩家 {player_id}：{e}")

def format_blackjack_game_state(room_id, room):
    """格式化21点游戏状态信息"""
    game_info = f"21点游戏开始！\n房间ID：{room_id}\n当前回合：{room.get('round', 1)}\n\n玩家状态：\n"
    
    for i, (player_id, player_name) in enumerate(zip(room["players"], room["player_names"])):
        hand = room["hands"][i]
        score = calculate_score(hand)
        status = room["player_status"][i]
        status_text = {
            "playing": "游戏中",
            "stand": "停牌",
            "bust": "爆牌"
        }.get(status, status)
        
        turn_indicator = "➡️ " if player_id == room.get("current_turn") else ""
        game_info += f"{turn_indicator}{i+1}. {player_name}"
        game_info += f" ({status_text})"
        game_info += f": {format_hand(hand)} = {score}点"
        if status == "bust":
            game_info += " (爆牌!)"
        game_info += "\n"
    
    return game_info


def handle_blackjack_action(update: Update, context: CallbackContext) -> None:
    """处理21点游戏中的要牌/停牌操作"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    
    if len(data) != 3:
        return
        
    action_type = data[1]  # hit 或 stand
    room_id = data[2]
    
    room = active_rooms[BLACKJACK].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("该房间不存在或游戏已结束。")
        return
    
    user_id = update.effective_user.id
    
    # 确认是否是该玩家的回合
    if user_id != room.get("current_turn"):
        query.answer("还不是你的回合！", show_alert=True)
        return
    
    player_idx = room["players"].index(user_id)
    
    # 处理玩家操作
    if action_type == "hit":
        # 玩家要牌
        if room["deck"]:
            card = room["deck"].pop()
            room["hands"][player_idx].append(card)
            score = calculate_score(room["hands"][player_idx])
            
            if score > 21:
                # 玩家爆牌
                room["player_status"][player_idx] = "bust"
                # 通知玩家爆牌
                query.answer(f"你抽到了 {format_card(card)}，总分 {score} 点，爆牌了！", show_alert=True)
            else:
                query.answer(f"你抽到了 {format_card(card)}，当前总分 {score} 点", show_alert=True)
    
    elif action_type == "stand":
        # 玩家停牌
        room["player_status"][player_idx] = "stand"
        query.answer("你选择了停牌", show_alert=True)
    
    # 轮到下一个玩家
    next_player_idx = find_next_player(room)
    
    # 检查游戏是否结束
    game_over = check_blackjack_game_over(room)
    
    if game_over:
        # 游戏结束，确定赢家
        room["status"] = "finished"
        winner_info = determine_blackjack_winner(room)
        game_info = format_blackjack_game_state(room_id, room) + "\n\n" + winner_info
        
        # 调用 update_user_record 记录胜负
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
                update_user_record(player_id, username, "Blackjack", "win")  # 胜利
            elif room["player_status"][i] == "bust":
                update_user_record(player_id, username, "Blackjack", "loss")  # 爆牌失败
            else:
                update_user_record(player_id, username, "Blackjack", "draw")  # 平局
        
        # 发送结果给所有玩家
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
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
                logger.error(f"无法发送消息给玩家 {player_id}：{e}")
    else:
        # 游戏继续，更新当前玩家
        if next_player_idx != -1:
            room["current_turn"] = room["players"][next_player_idx]
        
        # 可能增加回合数
        if next_player_idx == 0:  # 回到第一个玩家
            room["round"] = room.get("round", 1) + 1
        
        # 更新游戏状态并发送给所有玩家
        game_info = format_blackjack_game_state(room_id, room)
        reply_markup = generate_blackjack_keyboard(room_id, user_id, room)
        
        try:
            query.edit_message_text(game_info, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"编辑消息失败：{e}")
        
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
                logger.error(f"无法发送消息给玩家 {player_id}：{e}")
        
        # 检查是否轮到GPT出牌，如果是则自动进行决策
        if room["current_turn"] == "GPT":
            gpt_make_blackjack_decision(context, room_id, room)

def find_next_player(room):
    """找到下一个应该行动的玩家"""
    current_idx = room["players"].index(room["current_turn"])
    
    # 从下一个玩家开始检查
    for i in range(1, len(room["players"]) + 1):
        next_idx = (current_idx + i) % len(room["players"])
        # 如果玩家还在游戏中（没有爆牌或停牌）
        if room["player_status"][next_idx] == "playing":
            return next_idx
    
    # 如果没有可以行动的玩家，返回-1
    return -1

def check_blackjack_game_over(room):
    """检查21点游戏是否结束"""
    # 如果所有玩家都停牌或爆牌，游戏结束
    return all(status in ["stand", "bust"] for status in room["player_status"])

def determine_blackjack_winner(room):
    """确定21点游戏的赢家"""
    max_score = 0
    winners = []
    
    # 找出未爆牌的玩家中分数最高的
    for i, status in enumerate(room["player_status"]):
        if status != "bust":
            score = calculate_score(room["hands"][i])
            if score > max_score:
                max_score = score
                winners = [i]
            elif score == max_score:
                winners.append(i)
    
    if not winners:
        return "所有玩家都爆牌了，没有赢家！"
    
    if len(winners) == 1:
        winner_idx = winners[0]
        return f"赢家是 {room['player_names'][winner_idx]}，得分 {max_score} 点！"
    else:
        winner_names = [room["player_names"][idx] for idx in winners]
        return f"平局！赢家有：{', '.join(winner_names)}，得分 {max_score} 点！"
    

def gpt_make_blackjack_decision(context, room_id, room):
    """让GPT在21点游戏中做出决策"""
    # 找到GPT的索引
    gpt_idx = room["players"].index("GPT")
    gpt_state = room["gpt_state"]
    
    # 获取GPT的手牌和分数
    gpt_hand = room["hands"][gpt_idx]
    gpt_score = calculate_score(gpt_hand)
    
    # GPT的21点策略: 
    # - 17分或以上: 停牌
    # - 16分或以下: 要牌
    decision = "stand" if gpt_score >= 17 else "hit"
    
    # 如果决定要牌
    if decision == "hit":
        if room["deck"]:
            card = room["deck"].pop()
            room["hands"][gpt_idx].append(card)
            new_score = calculate_score(room["hands"][gpt_idx])
            
            # 检查是否爆牌
            if new_score > 21:
                room["player_status"][gpt_idx] = "bust"
                decision_text = f"GPT AI 选择要牌，抽到了 {format_card(card)}，总分 {new_score} 点，爆牌了！"
            else:
                decision_text = f"GPT AI 选择要牌，抽到了 {format_card(card)}，当前总分 {new_score} 点"
    else:
        # 选择停牌
        room["player_status"][gpt_idx] = "stand"
        decision_text = f"GPT AI 选择停牌，总分 {gpt_score} 点"
    
    # 轮到下一个玩家
    next_player_idx = find_next_player(room)
    
    # 检查游戏是否结束
    game_over = check_blackjack_game_over(room)
    
    # 找到房主ID，用于发送消息
    host_id = room["host"]
    
    # 通知房主GPT的决策
    try:
        if game_over:
            # 游戏结束，确定赢家
            room["status"] = "finished"
            winner_info = determine_blackjack_winner(room)
            game_info = format_blackjack_game_state(room_id, room) + "\n\n" + decision_text + "\n\n" + winner_info

            # 调用 update_user_record 记录胜负
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
                    update_user_record(player_id, username, "Blackjack", "win")  # 胜利
                elif room["player_status"][i] == "bust":
                    update_user_record(player_id, username, "Blackjack", "loss")  # 爆牌失败
                else:
                    update_user_record(player_id, username, "Blackjack", "draw")  # 平局
            
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
            context.bot.send_message(
                chat_id=host_id,
                text=game_info,
                reply_markup=reply_markup
            )
        else:
            # 游戏继续，更新当前玩家
            if next_player_idx != -1:
                room["current_turn"] = room["players"][next_player_idx]
            
            # 可能增加回合数
            if next_player_idx == 0:  # 回到第一个玩家
                room["round"] = room.get("round", 1) + 1
            
            # 更新游戏状态
            game_info = format_blackjack_game_state(room_id, room) + "\n\n" + decision_text
            reply_markup = generate_blackjack_keyboard(room_id, host_id, room)
            
            context.bot.send_message(
                chat_id=host_id,
                text=game_info,
                reply_markup=reply_markup
            )
            
            # 如果轮到GPT再次出牌，递归调用此函数
            if room["current_turn"] == "GPT":
                gpt_make_blackjack_decision(context, room_id, room)
    except Exception as e:
        logger.error(f"发送GPT决策消息失败：{e}")