from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import random
import threading
import time
from utils.constants import *  # 导入常量
from database import update_user_record

def generate_board_keyboard(room_id, board):
    """生成井字棋棋盘的内联键盘，每个按钮对应一个棋格"""
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            index = i + j
            cell = board[index] if board[index] != " " else "　"  # 使用全角空格保证按钮大小一致
            row.append(InlineKeyboardButton(cell, callback_data=f"ttt_move_{room_id}_{index}"))
        keyboard.append(row)
    # 添加返回主菜单按钮
    keyboard.append([InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)])
    return InlineKeyboardMarkup(keyboard)

def check_win(board):
    """检查棋盘是否有胜者或平局，返回 'X'、'O'、'draw' 或 None，以及赢的组合"""
    win_combinations = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),  # 行
        (0, 3, 6), (1, 4, 7), (2, 5, 8),  # 列
        (0, 4, 8), (2, 4, 6)              # 对角线
    ]
    for a, b, c in win_combinations:
        if board[a] == board[b] == board[c] and board[a] != " ":
            return board[a], (a, b, c)
    if " " not in board:
        return "draw", None
    return None, None

def start_tictactoe_game(update: Update, context: CallbackContext, room_id, room):
    """为井字棋初始化棋盘，发送棋盘消息，并通知当前回合"""
    # 初始化棋盘和当前回合（房主执 X）
    room["board"] = [" "] * 9
    room["current_turn"] = room["host"]  # 先由房主走棋
    text = f"井字棋对局开始！\n房间ID：{room_id}\n\n当前棋盘："
    reply_markup = generate_board_keyboard(room_id, room["board"])
    # 根据当前回合显示提示（X或O）
    turn_marker = "X" if room["host"] == room["current_turn"] else "O"
    text += f"\n轮到 {turn_marker} 的玩家走棋。"
    
    query = update.callback_query
    query.edit_message_text(text, reply_markup=reply_markup)
    
    # 向房间其他玩家发送棋盘状态
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
            logger.error(f"无法发送消息给玩家 {player_id}：{e}")
    
    # 检查是否有GPT玩家并且是否轮到GPT（特殊情况，如果用户选择GPT先手）
    if "GPT" in room["players"] and room["current_turn"] != room["host"]:
        # 让GPT先手，稍微延迟一下以增加体验
        def delayed_gpt_move():
            time.sleep(1)  # 延迟1秒，让玩家有时间看到初始棋盘
            make_gpt_ttt_move(context, room_id, room)
            
        threading.Thread(target=delayed_gpt_move).start()

def handle_ttt_move(update: Update, context: CallbackContext) -> None:
    """处理井字棋玩家点击棋格的操作"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    # 格式：ttt_move_{room_id}_{index}
    if len(data) != 4:
        return
    room_id = data[2]
    try:
        index = int(data[3])
    except ValueError:
        return
    
    room = active_rooms[TIC_TAC_TOE].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("该房间不存在或游戏已结束。")
        return
    
    user_id = update.effective_user.id
    # 判断是否轮到该玩家
    if user_id != room["current_turn"]:
        query.answer("还不是你的回合！", show_alert=True)
        return

    board = room["board"]
    if board[index] != " ":
        query.answer("该位置已被占用！", show_alert=True)
        return

    # 判断当前玩家使用的棋子：房主为 X，对手为 O
    marker = "X" if user_id == room["host"] else "O"
    board[index] = marker

    # 检查是否有胜者或平局
    result, win_combo = check_win(board)
    if result == marker:
        win_type = ""
        if win_combo:
            # 确定获胜类型（行、列或对角线）
            if win_combo in [(0, 1, 2), (3, 4, 5), (6, 7, 8)]:
                win_type = "（横向连成一线）"
            elif win_combo in [(0, 3, 6), (1, 4, 7), (2, 5, 8)]:
                win_type = "（纵向连成一线）"
            elif win_combo == (0, 4, 8):
                win_type = "（左上至右下对角线）"
            elif win_combo == (2, 4, 6):
                win_type = "（右上至左下对角线）"
        
        text = f"恭喜 {marker} 获胜！{win_type}\n房间ID：{room_id}\n最终棋盘："
        room["status"] = "finished"

        # 更新数据库记录
        player_index = 0 if user_id == room["players"][0] else 1
        opponent_index = 1 - player_index
        update_user_record(user_id, room["player_names"][player_index], TIC_TAC_TOE, "win")
        update_user_record(room["players"][opponent_index], room["player_names"][opponent_index], TIC_TAC_TOE, "loss")

    elif result == "draw":
        text = f"平局！\n房间ID：{room_id}\n最终棋盘："
        room["status"] = "finished"

        # 更新数据库记录
        update_user_record(room["players"][0], room["player_names"][0], TIC_TAC_TOE, "draw")
        update_user_record(room["players"][1], room["player_names"][1], TIC_TAC_TOE, "draw")

    else:
        # 切换回合
        next_player = room["players"][1] if user_id == room["host"] else room["players"][0]
        room["current_turn"] = next_player
        next_marker = "X" if next_player == room["host"] else "O"
        text = f"当前棋盘：\n轮到 {next_marker} 的玩家走棋。\n房间ID：{room_id}"
    
    reply_markup = generate_board_keyboard(room_id, board)
    try:
        query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"编辑消息失败：{e}")
    
    # 通知房间内其他玩家更新棋盘状态（不再排除房主）
    for pid in room["players"]:
        if pid == user_id:
            continue
        try:
            context.bot.send_message(
                chat_id=pid,
                text=text,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"无法发送消息给玩家 {pid}：{e}")
            
    # 如果游戏没有结束，且下一个玩家是GPT，则让GPT执行移动
    if room["status"] == "playing" and next_player == "GPT":
        make_gpt_ttt_move(context, room_id, room)

def make_gpt_ttt_move(context, room_id, room):
    """让GPT在井字棋游戏中做出决策"""
    board = room["board"]
    gpt_state = room["gpt_state"]
    human_marker = "X"  # 玩家总是X（因为玩家是房主）
    gpt_marker = "O"    # GPT总是O
    
    # 找出空位置
    empty_indices = [i for i, cell in enumerate(board) if cell == " "]
    
    # 如果没有空位，游戏结束
    if not empty_indices:
        return
    
    # 用于生成解释的变量
    move_explanation = ""
    
    # GPT的决策逻辑
    # 1. 检查是否有可以获胜的位置
    for idx in empty_indices:
        board[idx] = gpt_marker
        result, _ = check_win(board)
        board[idx] = " "  # 恢复空位
        if result == gpt_marker:
            # 找到获胜位置
            chosen_idx = idx
            move_explanation = "执行获胜步骤"
            break
    else:
        # 2. 检查是否需要阻止玩家获胜
        for idx in empty_indices:
            board[idx] = human_marker
            result, _ = check_win(board)
            board[idx] = " "  # 恢复空位
            if result == human_marker:
                # 找到需要阻止的位置
                chosen_idx = idx
                move_explanation = "阻止玩家获胜"
                break
        else:
            # 3. 尝试占据中间位置
            if 4 in empty_indices:
                chosen_idx = 4
                move_explanation = "选择中心位置"
            else:
                # 4. 随机选择一个角落或边缘
                corners = [i for i in [0, 2, 6, 8] if i in empty_indices]
                if corners:
                    chosen_idx = random.choice(corners)
                    move_explanation = "选择角落位置"
                else:
                    chosen_idx = random.choice(empty_indices)
                    move_explanation = "选择边缘位置"
    
    # 执行GPT的移动
    board[chosen_idx] = gpt_marker
    
    # 检查是否有胜者或平局
    result, win_combo = check_win(board)
    if result == gpt_marker:
        win_type = ""
        if win_combo:
            # 确定获胜类型（行、列或对角线）
            if win_combo in [(0, 1, 2), (3, 4, 5), (6, 7, 8)]:
                win_type = "（横向连成一线）"
            elif win_combo in [(0, 3, 6), (1, 4, 7), (2, 5, 8)]:
                win_type = "（纵向连成一线）"
            elif win_combo == (0, 4, 8):
                win_type = "（左上至右下对角线）"
            elif win_combo == (2, 4, 6):
                win_type = "（右上至左下对角线）"
        
        text = f"GPT AI {gpt_marker} 获胜！{win_type}\n房间ID：{room_id}\n最终棋盘："
        room["status"] = "finished"

        # 更新数据库记录
        update_user_record(
            room["host"],  # 玩家ID
            room["player_names"][0],  # 玩家用户名（房主）
            TIC_TAC_TOE,
            "loss"  # 玩家输了
        )
        update_user_record(
            "GPT",  # GPT ID
            "GPT AI",  # 玩家用户名（GPT）
            TIC_TAC_TOE,
            "win"  # GPT 赢了
        )
    elif result == "draw":
        text = f"平局！\n房间ID：{room_id}\n最终棋盘："
        room["status"] = "finished"

        # 更新数据库记录
        update_user_record(
            room["host"],  # 玩家ID
            room["player_names"][0],  # 玩家用户名（房主）
            TIC_TAC_TOE,
            "draw"  # 平局
        )
        update_user_record(
            "GPT",  # GPT ID
            "GPT AI",  # 玩家用户名（GPT）
            TIC_TAC_TOE,
            "draw"  # 平局
        )
        
    else:
        # 切换回合回到玩家
        room["current_turn"] = room["host"]
        text = f"GPT AI 已落子（{move_explanation}）。\n当前棋盘：\n轮到 X 的玩家走棋。\n房间ID：{room_id}"
    
    # 生成键盘并发送给玩家
    reply_markup = generate_board_keyboard(room_id, board)
    try:
        host_id = room["host"]
        context.bot.send_message(
            chat_id=host_id,
            text=text,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"向玩家发送GPT移动消息失败：{e}")