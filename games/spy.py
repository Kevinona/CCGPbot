from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import random
from utils.constants import *  # 导入常量
from database import update_user_record  # 确保导入 update_user_record 函数


def start_spy_game(update: Update, context: CallbackContext, room_id, room):
    """初始化谁是卧底游戏，生成身份并分发给玩家"""
    # 检查玩家数量，至少需要3人
    if len(room["players"]) < 3:
        query = update.callback_query
        query.edit_message_text(
            f"谁是卧底游戏至少需要3名玩家，当前只有{len(room['players'])}名玩家。\n请邀请更多玩家加入后再开始游戏。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
            ])
        )
        return
    
    # 设置游戏初始状态
    room["status"] = "playing"
    room["round"] = 1
    room["phase"] = "identity"  # 身份分配阶段
    room["votes"] = {}  # 玩家投票记录
    room["messages"] = []  # 玩家讨论记录
    room["eliminated"] = []  # 被淘汰的玩家
    
    # 随机选择一名玩家作为卧底
    spy_idx = random.randrange(len(room["players"]))
    room["spy"] = room["players"][spy_idx]
    
    # 使用GPT生成两个相关但不同的词语
    chatgpt = HKBU_ChatGPT()
    prompt = "请生成两个相关但有细微差别的中文词语，用于'谁是卧底'游戏。格式为'普通玩家词语:卧底词语'，不要有其他任何解释。例如：'苹果:梨子'或'电影院:剧场'。"
    
    try:
        response = chatgpt.submit(prompt)
        # 解析响应，获取两个词语
        words = response.strip().split(":")
        if len(words) != 2:
            # 如果格式不正确，使用默认词语
            words = ["苹果", "梨子"]
    except Exception as e:
        logger.error(f"生成词语失败：{e}")
        # 使用默认词语
        words = ["苹果", "梨子"]
    
    # 保存词语
    room["word_civilian"] = words[0]
    room["word_spy"] = words[1]
    
    # 为每个玩家分配身份和词语
    for i, player_id in enumerate(room["players"]):
        if player_id == room["spy"]:
            room[f"word_{player_id}"] = room["word_spy"]
        else:
            room[f"word_{player_id}"] = room["word_civilian"]
    
    # 通知所有玩家他们的身份和词语
    query = update.callback_query
    
    # 构建玩家列表
    player_list = "\n".join([f"{i+1}. {name}{' (房主)' if room['host'] == pid else ''}" 
                        for i, (name, pid) in enumerate(zip(room["player_names"], room["players"]))])
    
    # 通知所有玩家
    for player_id in room["players"]:
        word = room[f"word_{player_id}"]
        is_spy = player_id == room["spy"]
        
        message = (
            f"谁是卧底游戏开始了！\n"
            f"房间ID：{room_id}\n\n"
            f"参与玩家：\n{player_list}\n\n"
            f"你的身份是：{'卧底' if is_spy else '平民'}\n"
            f"你拿到的词语是：{word}\n\n"
            f"游戏规则：\n"
            f"1. 每个人轮流描述自己拿到的词语，但不能直接说出词语本身\n"
            f"2. 卧底的目标是隐藏自己，平民的目标是找出卧底\n"
            f"3. 每轮讨论后，所有人投票选出一名怀疑的玩家\n"
            f"4. 如果卧底被淘汰，平民胜利；如果最后只剩卧底和一名平民，卧底胜利"
        )
        
        # 构建按钮
        keyboard = [
            [InlineKeyboardButton("开始讨论", callback_data=f"spy_discuss_{room_id}")],
            [InlineKeyboardButton("跳过讨论直接投票", callback_data=f"spy_vote_{room_id}")],
            [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            if player_id == update.effective_user.id:
                # 更新当前消息
                query.edit_message_text(message, reply_markup=reply_markup)
            else:
                # 发送新消息给其他玩家
                context.bot.send_message(
                    chat_id=player_id,
                    text=message,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"无法发送消息给玩家 {player_id}：{e}")
    
    return SELECTING_GAME

def handle_spy_discussion(update: Update, context: CallbackContext) -> None:
    """处理谁是卧底游戏中的讨论阶段"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    
    if len(data) < 3:
        return
    
    # 格式：spy_discuss_{room_id}
    action = data[1]
    room_id = data[2]
    
    # 检查房间是否存在
    room = active_rooms[WHO_IS_SPY].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("该房间不存在或游戏已结束。", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]]))
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # 检查用户是否在该房间
    if user_id not in room["players"] or user_id in room["eliminated"]:
        query.answer("你不是该房间的有效玩家！", show_alert=True)
        return
    
    # 切换到讨论阶段
    room["phase"] = "discussion"
    
    # 构建玩家列表（不包括已淘汰玩家）
    active_players = []
    for i, (name, pid) in enumerate(zip(room["player_names"], room["players"])):
        if pid not in room["eliminated"]:
            active_players.append((i, name, pid))
    
    player_list = "\n".join([f"{i+1}. {name}{' (房主)' if room['host'] == pid else ''}" 
                         for i, name, pid in active_players])
    
    # 构建讨论消息
    message = (
        f"谁是卧底 - 讨论阶段\n"
        f"房间ID：{room_id}，第{room['round']}轮\n\n"
        f"存活玩家：\n{player_list}\n\n"
        f"请使用 /say <内容> 命令发表你对词语的描述。\n"
        f"例如：/say 这个东西是圆的，可以吃。\n\n"
        f"所有玩家都可以随时使用 /vote 命令开始投票环节。"
    )
    
    # 添加当前讨论记录
    if room["messages"]:
        message += "\n\n当前讨论记录："
        for msg in room["messages"]:
            message += f"\n{msg['player']}: {msg['content']}"
    
    # 构建按钮
    keyboard = [
        [InlineKeyboardButton("开始投票", callback_data=f"spy_vote_{room_id}")],
        [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 通知所有在游戏中的玩家
    for player_id in room["players"]:
        if player_id in room["eliminated"]:
            continue
            
        try:
            if player_id == user_id:
                # 更新当前消息
                query.edit_message_text(message, reply_markup=reply_markup)
            else:
                # 发送新消息给其他玩家
                context.bot.send_message(
                    chat_id=player_id,
                    text=message,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"无法发送消息给玩家 {player_id}：{e}")

def say_message(update: Update, context: CallbackContext) -> None:
    """处理 /say 命令，让玩家在谁是卧底游戏中发表描述"""
    if not context.args:
        update.message.reply_text("请提供你要说的内容，例如：/say 这个东西是圆的，可以吃。")
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    message_content = " ".join(context.args)
    
    # 查找玩家所在的房间
    player_room = None
    player_room_id = None
    
    for room_id, room in active_rooms[WHO_IS_SPY].items():
        if user_id in room["players"] and room["status"] == "playing" and room["phase"] == "discussion" and user_id not in room["eliminated"]:
            player_room = room
            player_room_id = room_id
            break
    
    if not player_room:
        update.message.reply_text("你当前不在任何谁是卧底游戏的讨论阶段中。")
        return
    
    # 记录玩家的发言
    player_room["messages"].append({
        "player": username,
        "player_id": user_id,
        "content": message_content
    })
    
    # 构建更新后的讨论消息
    active_players = []
    for i, (name, pid) in enumerate(zip(player_room["player_names"], player_room["players"])):
        if pid not in player_room["eliminated"]:
            active_players.append((i, name, pid))
    
    player_list = "\n".join([f"{i+1}. {name}{' (房主)' if player_room['host'] == pid else ''}" 
                         for i, name, pid in active_players])
    
    message = (
        f"谁是卧底 - 讨论阶段\n"
        f"房间ID：{player_room_id}，第{player_room['round']}轮\n\n"
        f"存活玩家：\n{player_list}\n\n"
        f"请使用 /say <内容> 命令发表你对词语的描述。\n"
        f"例如：/say 这个东西是圆的，可以吃。\n\n"
        f"所有玩家都可以随时使用 /vote 命令开始投票环节。\n\n"
        f"当前讨论记录："
    )
    
    for msg in player_room["messages"]:
        message += f"\n{msg['player']}: {msg['content']}"
    
    # 构建按钮
    keyboard = [
        [InlineKeyboardButton("开始投票", callback_data=f"spy_vote_{player_room_id}")],
        [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 通知所有在游戏中的玩家
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
            logger.error(f"无法发送消息给玩家 {player_id}：{e}")
    
    # 确认消息已发送
    update.message.reply_text("你的描述已发送给所有玩家。")

def handle_spy_vote(update: Update, context: CallbackContext) -> None:
    """处理谁是卧底游戏中的投票阶段"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    
    if len(data) < 3:
        return
    
    # 格式：spy_vote_{room_id} 或 spy_vote_{room_id}_{target_player_id}
    action = data[1]  # vote
    room_id = data[2]
    target_player_id = data[3] if len(data) > 3 else None
    
    # 检查房间是否存在
    room = active_rooms[WHO_IS_SPY].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("该房间不存在或游戏已结束。", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]]))
        return
    
    user_id = update.effective_user.id
    
    # 检查用户是否在该房间
    if user_id not in room["players"] or user_id in room["eliminated"]:
        query.answer("你不是该房间的有效玩家！", show_alert=True)
        return
    
    # 处理投票
    if target_player_id:
        # 玩家选择了投票目标
        target_player_id = int(target_player_id)  # 转换为整数，因为用户ID是整数
        
        # 记录投票
        room["votes"][user_id] = target_player_id
        
        # 检查是否所有玩家都已投票
        active_players = [pid for pid in room["players"] if pid not in room["eliminated"]]
        all_voted = all(pid in room["votes"] for pid in active_players)
        
        if all_voted:
            # 所有玩家都已投票，计算结果
            return tally_votes(update, context, room_id, room)
        else:
            # 通知玩家投票已记录
            player_name = ""
            for i, pid in enumerate(room["players"]):
                if pid == target_player_id:
                    player_name = room["player_names"][i]
                    break
                    
            query.edit_message_text(
                f"你已投票给 {player_name}。\n等待其他玩家完成投票...",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
            )
            
            # 通知其他玩家有人完成投票
            voted_count = len(room["votes"])
            total_count = len(active_players)
            
            for player_id in active_players:
                if player_id == user_id or player_id in room["votes"]:
                    continue
                
                try:
                    context.bot.send_message(
                        chat_id=player_id,
                        text=f"有玩家完成了投票！当前已有 {voted_count}/{total_count} 名玩家完成投票。"
                    )
                except Exception as e:
                    logger.error(f"无法发送消息给玩家 {player_id}：{e}")
    else:
        # 开始投票阶段
        room["phase"] = "voting"
        room["votes"] = {}  # 清空之前的投票
        
        # 构建存活玩家列表
        active_players = []
        for i, (name, pid) in enumerate(zip(room["player_names"], room["players"])):
            if pid not in room["eliminated"] and pid != user_id:  # 不能投自己
                active_players.append((i, name, pid))
        
        # 构建投票按钮
        keyboard = []
        for i, name, pid in active_players:
            keyboard.append([InlineKeyboardButton(name, callback_data=f"spy_vote_{room_id}_{pid}")])
        
        keyboard.append([InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 构建投票消息
        message = (
            f"谁是卧底 - 投票阶段\n"
            f"房间ID：{room_id}，第{room['round']}轮\n\n"
            f"请选择你认为是卧底的玩家："
        )
        
        # 更新当前消息
        query.edit_message_text(message, reply_markup=reply_markup)
        
        # 通知其他玩家投票已开始
        for player_id in room["players"]:
            if player_id in room["eliminated"] or player_id == user_id:
                continue
                
            try:
                context.bot.send_message(
                    chat_id=player_id,
                    text=f"投票阶段开始了！请选择你认为是卧底的玩家。",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"无法发送消息给玩家 {player_id}：{e}")



def tally_votes(update: Update, context: CallbackContext, room_id, room):
    """计算投票结果，确定被淘汰的玩家"""
    # 统计票数
    vote_counts = {}
    for voter, candidate in room["votes"].items():
        vote_counts[candidate] = vote_counts.get(candidate, 0) + 1
    
    # 找出得票最多的玩家
    max_votes = 0
    eliminated_players = []
    
    for player_id, count in vote_counts.items():
        if count > max_votes:
            max_votes = count
            eliminated_players = [player_id]
        elif count == max_votes:
            eliminated_players.append(player_id)
    
    # 如果有多人得票相同，随机选择一人
    eliminated_player_id = random.choice(eliminated_players)
    room["eliminated"].append(eliminated_player_id)
    
    # 获取被淘汰玩家的姓名
    eliminated_player_name = ""
    for i, pid in enumerate(room["players"]):
        if pid == eliminated_player_id:
            eliminated_player_name = room["player_names"][i]
            break
    
    # 检查游戏是否结束
    game_over = False
    winner = None
    
    # 统计剩余玩家
    remaining_players = [pid for pid in room["players"] if pid not in room["eliminated"]]
    
    # 检查是否只剩下两名玩家且其中一名是卧底
    if len(remaining_players) == 2 and room["spy"] in remaining_players:
        game_over = True
        winner = "spy"  # 卧底胜利
    # 检查卧底是否被淘汰
    elif eliminated_player_id == room["spy"]:
        game_over = True
        winner = "civilians"  # 平民胜利
    
    # 构建投票结果消息
    vote_result = []
    for i, (name, pid) in enumerate(zip(room["player_names"], room["players"])):
        if pid in vote_counts:
            vote_result.append(f"{name}: {vote_counts[pid]}票")
    
    # 构建消息
    if game_over:
        # 游戏结束
        message = (
            f"谁是卧底 - 游戏结束\n"
            f"房间ID：{room_id}\n\n"
            f"投票结果：\n{', '.join(vote_result)}\n\n"
            f"{eliminated_player_name} 被淘汰了！\n\n"
        )
        
        # 卧底身份揭晓
        spy_name = ""
        for i, pid in enumerate(room["players"]):
            if pid == room["spy"]:
                spy_name = room["player_names"][i]
                break
        
        message += f"卧底是：{spy_name}\n"
        message += f"平民词语：{room['word_civilian']}\n"
        message += f"卧底词语：{room['word_spy']}\n\n"
        
        if winner == "spy":
            message += "卧底获胜！"
        else:
            message += "平民获胜！"
        
        keyboard = [
            [InlineKeyboardButton("开始新游戏", callback_data=f"start_game_{room_id}")],
            [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
        ]
        
        # 更新房间状态
        room["status"] = "finished"

        # 调用 update_user_record 记录胜负
        for i, player_id in enumerate(room["players"]):
            username = room["player_names"][i]
            if winner == "spy":
                if player_id == room["spy"]:
                    update_user_record(player_id, username, "WhoIsSpy", "win")  # 卧底胜利
                else:
                    update_user_record(player_id, username, "WhoIsSpy", "loss")  # 平民失败
            elif winner == "civilians":
                if player_id == room["spy"]:
                    update_user_record(player_id, username, "WhoIsSpy", "loss")  # 卧底失败
                else:
                    update_user_record(player_id, username, "WhoIsSpy", "win")  # 平民胜利
    else:
        # 进入下一轮
        room["round"] += 1
        room["phase"] = "discussion"
        room["messages"] = []  # 清空讨论记录
        
        message = (
            f"谁是卧底 - 第{room['round']}轮\n"
            f"房间ID：{room_id}\n\n"
            f"投票结果：\n{', '.join(vote_result)}\n\n"
            f"{eliminated_player_name} 被淘汰了！\n\n"
            f"游戏继续，请开始新一轮的讨论。"
        )
        
        keyboard = [
            [InlineKeyboardButton("开始讨论", callback_data=f"spy_discuss_{room_id}")],
            [InlineKeyboardButton("跳过讨论直接投票", callback_data=f"spy_vote_{room_id}")],
            [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 通知所有玩家投票结果
    for player_id in room["players"]:
        try:
            if player_id == update.effective_user.id:
                # 更新当前消息
                query = update.callback_query
                query.edit_message_text(message, reply_markup=reply_markup)
            else:
                # 发送新消息给其他玩家
                context.bot.send_message(
                    chat_id=player_id,
                    text=message,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"无法发送消息给玩家 {player_id}：{e}")
    
    return SELECTING_GAME

def start_vote(update: Update, context: CallbackContext) -> None:
    """处理 /vote 命令，让玩家在谁是卧底游戏中直接开始投票"""
    user_id = update.effective_user.id
    
    # 查找玩家所在的房间
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
        update.message.reply_text("你当前不在任何谁是卧底游戏的讨论阶段中，无法发起投票。")
        return
    
    # 切换到投票阶段
    player_room["phase"] = "voting"
    player_room["votes"] = {}  # 清空之前的投票
    
    # 构建存活玩家列表（除了自己）
    active_players = []
    for i, (name, pid) in enumerate(zip(player_room["player_names"], player_room["players"])):
        if pid not in player_room["eliminated"] and pid != user_id:  # 不能投自己
            active_players.append((i, name, pid))
    
    # 构建投票按钮
    keyboard = []
    for i, name, pid in active_players:
        keyboard.append([InlineKeyboardButton(name, callback_data=f"spy_vote_{player_room_id}_{pid}")])
    
    keyboard.append([InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 构建投票消息
    message = (
        f"谁是卧底 - 投票阶段\n"
        f"房间ID：{player_room_id}，第{player_room['round']}轮\n\n"
        f"请选择你认为是卧底的玩家："
    )
    
    # 发送投票消息给发起投票的玩家
    update.message.reply_text(message, reply_markup=reply_markup)
    
    # 通知其他玩家投票已开始
    for player_id in player_room["players"]:
        if player_id in player_room["eliminated"] or player_id == user_id:
            continue
            
        try:
            context.bot.send_message(
                chat_id=player_id,
                text=f"玩家 {update.effective_user.username or update.effective_user.first_name} 发起了投票！请选择你认为是卧底的玩家。",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"无法发送消息给玩家 {player_id}：{e}")