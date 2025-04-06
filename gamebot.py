# -*- coding: utf-8 -*-
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
    """生成一个随机6位房间ID"""
    while True:
        room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        # 确保房间ID唯一
        if all(room_id not in rooms for rooms in active_rooms.values()):
            return room_id

def start(update: Update, context: CallbackContext) -> int:
    """处理 /start 命令或返回主菜单的操作，显示游戏选择界面"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("井字棋", callback_data=TIC_TAC_TOE)],
        [InlineKeyboardButton("围棋", callback_data=GO)],
        [InlineKeyboardButton("谁是卧底", callback_data=WHO_IS_SPY)],
        [InlineKeyboardButton("21点", callback_data=BLACKJACK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"你好 {user.first_name}，欢迎使用游戏机器人！\n"
        "请选择想要玩的游戏：\n\n"
        "你还可以使用以下命令：\n"
        "/record - 查询你的游戏输赢平记录\n"
        "/rooms - 查看当前活跃的游戏房间\n"
        "/join <房间ID> - 加入指定房间\n"
        "/cancel - 取消当前操作"
    )
    
    if update.message:
        update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        logger.error("无法获取消息来源")
    
    return SELECTING_GAME


def get_game_name(game_type):
    """安全地获取游戏名称，避免KeyError"""
    return game_names.get(game_type, "未知游戏")


def game_selection(update: Update, context: CallbackContext) -> int:
    """处理游戏选择后的操作"""
    query = update.callback_query
    query.answer()
    
    game_type = query.data
    
    # 如果回调数据为特殊操作，则交给 game_action 处理
    if game_type in [CREATE_GAME, MATCH_PLAYER, PLAY_WITH_GPT, CANCEL_MATCH] or game_type.startswith(("start_game_", "cancel_room_", "end_game_")):
        return game_action(update, context)
    
    if game_type == BACK_TO_MAIN:
        return start(update, context)
    
    context.user_data["game_type"] = game_type

    if game_type in [TIC_TAC_TOE, GO, BLACKJACK]:
        keyboard = [
            [InlineKeyboardButton("创建对局", callback_data=CREATE_GAME)],
            [InlineKeyboardButton("匹配玩家", callback_data=MATCH_PLAYER)],
            [InlineKeyboardButton("与GPT对战", callback_data=PLAY_WITH_GPT)],
            [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("创建对局", callback_data=CREATE_GAME)],
            [InlineKeyboardButton("匹配玩家", callback_data=MATCH_PLAYER)],
            [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(
        f"你选择了 {get_game_name(game_type)}，请选择操作：",
        reply_markup=reply_markup
    )
    return GAME_ACTION


def game_action(update: Update, context: CallbackContext) -> int:
    """处理选择具体游戏操作后的逻辑"""
    query = update.callback_query
    query.answer()
    
    action = query.data
    
    if action == BACK_TO_MAIN:
        return start(update, context)
    
    # 获取游戏类型，可能从user_data中获取或者就是当前的action（如create_game）
    game_type = context.user_data.get("game_type")
    
    # 如果action是CREATE_GAME, MATCH_PLAYER等，但没有game_type，则返回主菜单
    if action in [CREATE_GAME, MATCH_PLAYER, PLAY_WITH_GPT] and not game_type:
        logger.error(f"游戏类型未定义，action={action}")
        return start(update, context)
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # 如果用户在匹配队列中，且选择创建游戏，先将其从匹配队列中移除
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
            [InlineKeyboardButton("开始游戏", callback_data=f"start_game_{room_id}")],
            [InlineKeyboardButton("取消房间", callback_data=f"cancel_room_{room_id}")],
            [InlineKeyboardButton("邀请朋友加入", url=f"https://t.me/share/url?url=加入我的{get_game_name(game_type)}游戏房间！房间ID：{room_id}")],
            [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            f"你已成功创建一个{get_game_name(game_type)}游戏房间！\n房间ID: {room_id}\n将此ID分享给朋友，他们可以使用 /join {room_id} 加入你的房间。\n\n当前玩家：\n1. {username} (房主)",
            reply_markup=reply_markup
        )
        
    elif action == MATCH_PLAYER:
        # 先检查是否有可用的等待中的房间
        available_room = None
        for room_id, room in active_rooms[game_type].items():
            if room["status"] == "waiting" and len(room["players"]) < (8 if game_type == WHO_IS_SPY else 2):
                available_room = (room_id, room)
                break
                
        if available_room:
            # 如果有可用房间，加入该房间
            room_id, room = available_room
            if user_id not in room["players"]:
                room["players"].append(user_id)
                room["player_names"].append(username)
                
                # 通知房主有新玩家加入
                try:
                    host_keyboard = [
                        [InlineKeyboardButton("开始游戏", callback_data=f"start_game_{room_id}")],
                        [InlineKeyboardButton("取消房间", callback_data=f"cancel_room_{room_id}")],
                        [InlineKeyboardButton("邀请朋友加入", url=f"https://t.me/share/url?url=加入我的{get_game_name(game_type)}游戏房间！房间ID：{room_id}")],
                        [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                    ]
                    host_markup = InlineKeyboardMarkup(host_keyboard)
                    
                    context.bot.send_message(
                        chat_id=room["host"],
                        text=f"新玩家 {username} 加入了你的房间！\n\n游戏：{get_game_name(game_type)}\n房间ID：{room_id}",
                        reply_markup=host_markup
                    )
                except Exception as e:
                    logger.error(f"无法发送消息给房主 {room['host']}：{e}")
                
                player_keyboard = [
                    [InlineKeyboardButton("邀请朋友加入", url=f"https://t.me/share/url?url=加入我的{get_game_name(game_type)}游戏房间！房间ID：{room_id}")],
                    [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                ]
                player_markup = InlineKeyboardMarkup(player_keyboard)
                
                # 通知当前玩家已成功加入房间
                query.edit_message_text(
                    f"你已成功加入房间 {room_id}！\n游戏：{get_game_name(game_type)}\n房主：{room.get('host_name', '未知')}",
                    reply_markup=player_markup
                )
            else:
                query.edit_message_text(
                    f"你已经在房间 {room_id} 中了！",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
                )
        elif waiting_players[game_type] and waiting_players[game_type][0] != user_id:
            matched_player_id = waiting_players[game_type].pop(0)
            
            # 获取匹配到的玩家的用户名
            matched_player_name = None
            try:
                matched_player = context.bot.get_chat(matched_player_id)
                matched_player_name = matched_player.username or matched_player.first_name
            except Exception as e:
                logger.error(f"无法获取玩家 {matched_player_id} 的信息：{e}")
                matched_player_name = "未知玩家"
            
            room_id = generate_room_id()
            active_rooms[game_type][room_id] = {
                "host": matched_player_id,
                "host_name": matched_player_name,
                "players": [matched_player_id, user_id],
                "player_names": [matched_player_name, username],
                "status": "matched"
            }
            
            # 通知被匹配的玩家
            try:
                keyboard_for_matched = [[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]]
                markup_for_matched = InlineKeyboardMarkup(keyboard_for_matched)
                context.bot.send_message(
                    chat_id=matched_player_id,
                    text=f"已匹配到对手 {username}！\n游戏：{get_game_name(game_type)}\n房间ID：{room_id}\n游戏即将开始...",
                    reply_markup=markup_for_matched
                )
            except Exception as e:
                logger.error(f"无法发送消息给玩家 {matched_player_id}：{e}")
            
            # 当前玩家的界面
            keyboard = [
                [InlineKeyboardButton("开始游戏", callback_data=f"start_game_{room_id}")],
                [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # 发送消息给当前玩家
            try:
                query.edit_message_text(
                    text=f"已匹配到对手 {matched_player_name}！\n游戏：{get_game_name(game_type)}\n房间ID：{room_id}\n点击开始游戏按钮开始对局！",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"编辑消息失败：{e}")
        else:
            # 确保用户被添加到等待列表中
            if user_id not in waiting_players[game_type]:
                waiting_players[game_type].append(user_id)
                
            # 如果没有可用房间，也没有等待匹配的玩家，则提示用户创建房间
            if len(waiting_players[game_type]) == 1:  # 只有当前用户在等待
                keyboard = [
                    [InlineKeyboardButton("创建房间", callback_data=CREATE_GAME)],
                    [InlineKeyboardButton("取消匹配", callback_data=CANCEL_MATCH)],
                    [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                query.edit_message_text(
                    f"当前没有可加入的{get_game_name(game_type)}房间，也没有其他等待匹配的玩家。\n你可以创建一个新房间或继续等待其他玩家。",
                    reply_markup=reply_markup
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("取消匹配", callback_data=CANCEL_MATCH)],
                    [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                query.edit_message_text(
                    f"正在为你匹配{get_game_name(game_type)}的对手...\n请稍候，当有玩家加入时会通知你。",
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
            
            # 只为井字棋添加先手/后手选择
            if game_type == TIC_TAC_TOE:
                keyboard = [
                    [InlineKeyboardButton("我先手 (X)", callback_data=f"start_game_{room_id}")],
                    [InlineKeyboardButton("GPT先手 (O)", callback_data=f"gpt_first_{room_id}")],
                    [InlineKeyboardButton("取消房间", callback_data=f"cancel_room_{room_id}")],
                    [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("开始游戏", callback_data=f"start_game_{room_id}")],
                    [InlineKeyboardButton("取消房间", callback_data=f"cancel_room_{room_id}")],
                    [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                ]
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(
                f"你已开始与GPT的{get_game_name(game_type)}对局！\n房间ID: {room_id}\n\n当前玩家：\n1. {username} (房主)\n2. GPT AI",
                reply_markup=reply_markup
            )
    
    elif action == CANCEL_MATCH:
        if user_id in waiting_players[game_type]:
            waiting_players[game_type].remove(user_id)
        return start(update, context)
    
    # 处理开始游戏操作
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
                    player_list = "\n".join([f"{i+1}. {name}{' (房主)' if room['host'] == pid else ''}" 
                                       for i, (name, pid) in enumerate(zip(room["player_names"], room["players"]))])
                    keyboard = [
                        [InlineKeyboardButton("结束游戏", callback_data=f"end_game_{room_id}")],
                        [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    query.edit_message_text(
                        f"游戏已开始！\n游戏：{get_game_name(game)}\n房间ID：{room_id}\n\n参与玩家：\n{player_list}\n\n（游戏逻辑未实现）",
                        reply_markup=reply_markup
                    )
                    
                    for player_id in room["players"]:
                        if isinstance(player_id, str) and player_id == "GPT":
                            continue
                        if player_id != user_id:
                            try:
                                context.bot.send_message(
                                    chat_id=player_id,
                                    text=f"游戏已开始！\n游戏：{get_game_name(game)}\n房间ID：{room_id}\n\n参与玩家：\n{player_list}\n\n（游戏逻辑未实现）",
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
                                )
                            except Exception as e:
                                logger.error(f"无法发送消息给玩家 {player_id}：{e}")
                    return SELECTING_GAME
                    
    # 处理GPT先手操作
    elif action.startswith("gpt_first_"):
        room_id = action.split("_")[-1]
        room = active_rooms[TIC_TAC_TOE].get(room_id)
        if room and room["host"] == user_id:
            room["status"] = "playing"
            # 将当前回合设置为非房主（即GPT），让GPT先手
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
                                text=f"房主已取消房间 {room_id}。",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
                            )
                        except Exception as e:
                            logger.error(f"无法发送消息给玩家 {player_id}：{e}")
                del rooms[room_id]
                query.edit_message_text(
                    f"你已成功取消房间 {room_id}。",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
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
                                text=f"房主已结束游戏。房间 {room_id} 已关闭。",
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
                            )
                        except Exception as e:
                            logger.error(f"无法发送消息给玩家 {player_id}：{e}")
                del rooms[room_id]
                query.edit_message_text(
                    f"游戏已结束！房间 {room_id} 已关闭。",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
                )
                return SELECTING_GAME
    
    return SELECTING_GAME





def join_room(update: Update, context: CallbackContext) -> None:
    """处理 /join 命令，加入指定房间"""
    if not context.args:
        update.message.reply_text("请提供房间ID，例如：/join ABC123")
        return

    room_id = context.args[0].upper()
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    for game_type, rooms in active_rooms.items():
        if room_id in rooms:
            room = rooms[room_id]
            if room["status"] == "playing":
                update.message.reply_text("抱歉，该房间的游戏已经开始，无法加入。")
                return
                
            if game_type == WHO_IS_SPY and len(room["players"]) >= 8:
                update.message.reply_text("抱歉，该房间已满员（最多8人）。")
                return
            elif game_type != WHO_IS_SPY and len(room["players"]) >= 2:
                update.message.reply_text("抱歉，该房间已满员。")
                return
            
            is_new_player = False
            if user_id not in room["players"]:
                room["players"].append(user_id)
                room["player_names"].append(username)
                is_new_player = True
            
            player_list = "\n".join([f"{i+1}. {name}{' (房主)' if room['host'] == pid else ''}" 
                                   for i, (name, pid) in enumerate(zip(room["player_names"], room["players"]))])
            
            if is_new_player:
                host_keyboard = [
                    [InlineKeyboardButton("开始游戏", callback_data=f"start_game_{room_id}")],
                    [InlineKeyboardButton("取消房间", callback_data=f"cancel_room_{room_id}")],
                    [InlineKeyboardButton("邀请朋友加入", url=f"https://t.me/share/url?url=加入我的{get_game_name(game_type)}游戏房间！房间ID：{room_id}")],
                    [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                ]
                host_markup = InlineKeyboardMarkup(host_keyboard)
                
                player_keyboard = [
                    [InlineKeyboardButton("邀请朋友加入", url=f"https://t.me/share/url?url=加入我的{get_game_name(game_type)}游戏房间！房间ID：{room_id}")],
                    [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
                ]
                player_markup = InlineKeyboardMarkup(player_keyboard)
                
                for player_id in room["players"]:
                    if isinstance(player_id, str) and player_id == "GPT":
                        continue
                    try:
                        if player_id == room["host"]:
                            context.bot.send_message(
                                chat_id=player_id,
                                text=f"新玩家 {username} 加入了你的房间！\n\n游戏：{get_game_name(game_type)}\n房间ID：{room_id}\n\n当前玩家：\n{player_list}",
                                reply_markup=host_markup
                            )
                        elif player_id != user_id:
                            context.bot.send_message(
                                chat_id=player_id,
                                text=f"新玩家 {username} 加入了房间！\n\n游戏：{get_game_name(game_type)}\n房间ID：{room_id}\n\n当前玩家：\n{player_list}",
                                reply_markup=player_markup
                            )
                    except Exception as e:
                        logger.error(f"无法发送消息给玩家 {player_id}：{e}")
            
            player_keyboard = [
                [InlineKeyboardButton("邀请朋友加入", url=f"https://t.me/share/url?url=加入我的{get_game_name(game_type)}游戏房间！房间ID：{room_id}")],
                [InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]
            ]
            player_markup = InlineKeyboardMarkup(player_keyboard)
            
            join_message = "你已成功加入房间" if is_new_player else "你已在房间中"
            update.message.reply_text(
                f"{join_message} {room_id}！\n游戏：{get_game_name(game_type)}\n房主：{room.get('host_name', '未知')}\n\n当前玩家：\n{player_list}",
                reply_markup=player_markup
            )
            return

    update.message.reply_text(f"找不到房间ID为 {room_id} 的游戏房间，请检查ID是否正确。")



def list_rooms(update: Update, context: CallbackContext) -> None:
    """处理 /rooms 命令，列出当前活跃房间"""
    response = "当前活跃的游戏房间：\n\n"
    found_rooms = False

    for game_type, rooms in active_rooms.items():
        if rooms:
            response += f"【{get_game_name(game_type)}】\n"
            for room_id, room_data in rooms.items():
                player_count = len(room_data["players"])
                max_players = 8 if game_type == WHO_IS_SPY else 2
                status = "等待中" if room_data["status"] == "waiting" else "游戏中"
                response += f"- 房间ID: {room_id} | 玩家: {player_count}/{max_players} | 状态: {status}\n"
            response += "\n"
            found_rooms = True

    if not found_rooms:
        response = "当前没有活跃的游戏房间。使用 /start 创建一个新房间！"
    
    update.message.reply_text(response)

def cancel(update: Update, context: CallbackContext) -> int:
    """取消并结束会话"""
    update.message.reply_text("操作已取消，使用 /start 重新开始。")
    return ConversationHandler.END



def handle_record_command(update: Update, context: CallbackContext):
    """处理用户查询输赢平记录的命令"""
    user_id = update.effective_user.id
    try:
        message = get_user_record(user_id)
        update.message.reply_text(message)
    except Exception as e:
        update.message.reply_text(f"查询记录失败：{e}")


def main() -> None:
    """启动机器人"""
    updater = Updater(token=os.environ['GAMEBOT_TOKEN'])
    dispatcher = updater.dispatcher

    # 修改 ConversationHandler，添加过滤规则，避免处理以特定前缀开头的回调数据
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

    # 添加井字棋落子回调处理器
    dispatcher.add_handler(CallbackQueryHandler(handle_ttt_move, pattern=r"^ttt_move_"))
    # 添加21点游戏操作回调处理器
    dispatcher.add_handler(CallbackQueryHandler(handle_blackjack_action, pattern=r"^bj_(hit|stand)_"))
    # 添加围棋操作回调处理器
    dispatcher.add_handler(CallbackQueryHandler(handle_go_move, pattern=r"^go_(move|pass)_"))
    # 添加谁是卧底游戏操作回调处理器
    dispatcher.add_handler(CallbackQueryHandler(handle_spy_discussion, pattern=r"^spy_discuss_"))
    dispatcher.add_handler(CallbackQueryHandler(handle_spy_vote, pattern=r"^spy_vote_"))

    updater.start_polling()
    updater.idle()

