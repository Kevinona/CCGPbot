from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import random
import threading
import time
from utils.constants import *  # 导入常量
from database import update_user_record  # 确保导入 update_user_record 函数

def generate_go_board_keyboard(room_id, board):
    """生成围棋棋盘的内联键盘"""
    keyboard = []
    # 添加坐标标签（A-I）
    header_row = [InlineKeyboardButton(" ", callback_data=f"go_none")]
    for col in range(GO_BOARD_SIZE):
        header_row.append(InlineKeyboardButton(chr(65 + col), callback_data=f"go_none"))
    keyboard.append(header_row)
    
    # 添加棋盘格子
    for row in range(GO_BOARD_SIZE):
        board_row = [InlineKeyboardButton(f"{row + 1}", callback_data=f"go_none")]  # 行号
        for col in range(GO_BOARD_SIZE):
            cell = board[row][col]
            if cell == "B":
                display = "⚫"  # 黑棋
            elif cell == "W":
                display = "⚪"  # 白棋
            else:
                display = "·"  # 空位，使用点而不是加号，更符合围棋习惯
            board_row.append(InlineKeyboardButton(display, callback_data=f"go_move_{room_id}_{row}_{col}"))
        keyboard.append(board_row)
    
    # 添加跳过和返回按钮
    keyboard.append([
        InlineKeyboardButton("跳过(Pass)", callback_data=f"go_pass_{room_id}"),
        InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)
    ])
    return InlineKeyboardMarkup(keyboard)

def start_go_game(update: Update, context: CallbackContext, room_id, room):
    """初始化围棋游戏，创建棋盘并设置初始状态"""
    # 初始化棋盘和当前回合（房主执黑）
    room["board"] = create_go_board()
    room["current_turn"] = room["host"]  # 先由房主走棋（黑棋）
    room["pass_count"] = 0  # 用于记录连续跳过的次数
    room["black_captures"] = 0  # 黑棋吃子数量
    room["white_captures"] = 0  # 白棋吃子数量
    
    # 确定双方棋子颜色
    host_stone = "B"  # 房主执黑
    opponent_stone = "W"  # 对手执白
    
    text = f"围棋对局开始！\n房间ID：{room_id}\n棋盘大小：{GO_BOARD_SIZE}x{GO_BOARD_SIZE}\n\n"
    text += f"黑棋（⚫）：{room['player_names'][0]}\n"
    text += f"白棋（⚪）：{room['player_names'][1]}\n\n"
    text += f"当前回合：黑棋 ({room['player_names'][0]})\n"
    text += f"黑方提子：{room['black_captures']}，白方提子：{room['white_captures']}"
    
    reply_markup = generate_go_board_keyboard(room_id, room["board"])
    
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
    
    # 如果对手是GPT，且是GPT先手（这种情况下需要修改初始化设置）
    if "GPT" in room["players"] and room["current_turn"] == "GPT":
        # 让GPT先手，稍微延迟一下以增加体验
        def delayed_gpt_move():
            time.sleep(1)  # 延迟1秒，让玩家有时间看到初始棋盘
            make_gpt_go_move(context, room_id, room)
            
        threading.Thread(target=delayed_gpt_move).start()

from database import update_user_record  # 确保导入 update_user_record 函数

def handle_go_move(update: Update, context: CallbackContext) -> None:
    """处理围棋玩家的落子操作"""
    query = update.callback_query
    query.answer()
    data = query.data.split("_")
    # 格式：go_move_{room_id}_{row}_{col} 或 go_pass_{room_id}
    
    if len(data) < 3:
        return
    
    action = data[1]  # move 或 pass
    room_id = data[2]
    
    room = active_rooms[GO].get(room_id)
    if not room or room["status"] != "playing":
        query.edit_message_text("该房间不存在或游戏已结束。")
        return
    
    user_id = update.effective_user.id
    # 判断是否轮到该玩家
    if user_id != room["current_turn"]:
        query.answer("还不是你的回合！", show_alert=True)
        return
    
    board = room["board"]
    
    # 判断当前玩家使用的棋子：房主为黑棋(B)，对手为白棋(W)
    stone = "B" if user_id == room["host"] else "W"
    opponent_stone = "W" if stone == "B" else "B"
    
    if action == "pass":
        # 玩家选择跳过
        room["pass_count"] += 1
        pass_message = f"{room['player_names'][0] if stone == 'B' else room['player_names'][1]} 选择跳过(Pass)"
        
        # 检查是否连续两次跳过，如果是则游戏结束
        if room["pass_count"] >= 2:
            # 简单计算领地（实际围棋需要更复杂的算法）
            black_territory = sum(row.count("B") for row in board)
            white_territory = sum(row.count("W") for row in board)
            
            # 考虑提子
            black_score = black_territory + room["black_captures"]
            white_score = white_territory + room["white_captures"]
            
            winner = "黑棋" if black_score > white_score else "白棋" if white_score > black_score else "平局"
            result_message = f"游戏结束，双方连续跳过！\n\n黑棋得分：{black_score}（领地：{black_territory}，提子：{room['black_captures']}）\n白棋得分：{white_score}（领地：{white_territory}，提子：{room['white_captures']}）\n\n结果：{winner}获胜！"
            
            room["status"] = "finished"
            text = f"{pass_message}\n\n{result_message}\n\n房间ID：{room_id}"
            
            # 调用 update_user_record 记录胜负
            for i, player_id in enumerate(room["players"]):
                username = room["player_names"][i]
                if winner == "黑棋":
                    if i == 0:  # 黑棋玩家
                        update_user_record(player_id, username, "Go", "win")
                    else:  # 白棋玩家
                        update_user_record(player_id, username, "Go", "loss")
                elif winner == "白棋":
                    if i == 0:  # 黑棋玩家
                        update_user_record(player_id, username, "Go", "loss")
                    else:  # 白棋玩家
                        update_user_record(player_id, username, "Go", "win")
                else:  # 平局
                    update_user_record(player_id, username, "Go", "draw")
            
            # 通知所有玩家游戏结束
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
            for pid in room["players"]:
                try:
                    context.bot.send_message(
                        chat_id=pid,
                        text=text,
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"无法发送消息给玩家 {pid}：{e}")
            return  # 游戏结束，直接返回
        else:
            # 切换回合
            next_player = room["players"][1] if user_id == room["host"] else room["players"][0]
            room["current_turn"] = next_player
            next_stone = "B" if next_player == room["host"] else "W"
            
            text = f"{pass_message}\n\n当前回合：{'黑棋' if next_stone == 'B' else '白棋'} ({room['player_names'][0 if next_stone == 'B' else 1]})\n房间ID：{room_id}\n黑方提子：{room['black_captures']}，白方提子：{room['white_captures']}"
    else:
        # 玩家落子
        try:
            row = int(data[3])
            col = int(data[4])
        except (ValueError, IndexError):
            return
        
        # 检查落子是否有效
        if not is_valid_go_move(board, row, col, stone):
            query.answer("这里不能落子！", show_alert=True)
            return
        
        # 重置连续跳过计数
        room["pass_count"] = 0
        
        # 执行落子
        board[row][col] = stone
        
        # 检查并移除被吃掉的对手棋子
        captured = remove_captured_stones(board, row, col)
        if captured > 0:
            if stone == "B":
                room["black_captures"] += captured
            else:
                room["white_captures"] += captured
        
        # 切换回合
        next_player = room["players"][1] if user_id == room["host"] else room["players"][0]
        room["current_turn"] = next_player
        next_stone = "B" if next_player == room["host"] else "W"
        
        move_text = f"{chr(65 + col)}{row + 1}"
        text = f"{'黑棋' if stone == 'B' else '白棋'} 落子于 {move_text}"
        if captured > 0:
            text += f"，提子 {captured} 个"
        
        text += f"\n\n当前回合：{'黑棋' if next_stone == 'B' else '白棋'} ({room['player_names'][0 if next_stone == 'B' else 1]})\n房间ID：{room_id}\n黑方提子：{room['black_captures']}，白方提子：{room['white_captures']}"
    
    reply_markup = generate_go_board_keyboard(room_id, board)
    try:
        query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"编辑消息失败：{e}")
    
    # 通知房间内其他玩家更新棋盘状态
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
            logger.error(f"无法发送消息给玩家 {pid}：{e}")
            
    # 如果游戏没有结束，且下一个玩家是GPT，则让GPT执行移动
    if room["status"] == "playing" and next_player == "GPT":
        make_gpt_go_move(context, room_id, room)

def make_gpt_go_move(context, room_id, room):
    """让GPT在围棋游戏中做出决策"""
    board = room["board"]
    # GPT执白棋
    stone = "W"
    
    # 延迟一下，让玩家有更好的游戏体验
    time.sleep(2)
    
    # 使用HKBU_ChatGPT API进行更智能的围棋决策
    try:
        # 创建棋盘状态的字符串表示
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
        
        # 找出所有有效的落子位置
        valid_moves = []
        for row in range(GO_BOARD_SIZE):
            for col in range(GO_BOARD_SIZE):
                if is_valid_go_move(board, row, col, stone):
                    # 将坐标转换为棋盘表示形式（例如A1, B2）
                    col_letter = chr(col + ord('A'))
                    row_num = row + 1
                    valid_moves.append(f"{col_letter}{row_num}")
        
        # 构建提示信息
        prompt = f"""你是一个围棋AI助手。请为白棋在7x7的围棋棋盘上选择一个最佳的落子位置。

重要：这是一个7x7的棋盘，不是19x19的标准棋盘。
棋盘坐标系统如下（左上角是A1，右下角是G7）：
  A B C D E F G
1 · · · · · · ·
2 · · · · · · ·
3 · · · · · · ·
4 · · · · · · ·
5 · · · · · · ·
6 · · · · · · ·
7 · · · · · · ·

当前棋盘状态（⚫代表黑棋，⚪代表白棋，·代表空位）：
{board_str}
黑方提子：{room['black_captures']}，白方提子：{room['white_captures']}
连续跳过次数：{room['pass_count']}

根据围棋规则，以下是当前所有有效的落子位置：
{', '.join(valid_moves) if valid_moves else "没有有效的落子位置，你必须跳过(Pass)"}

请从上述有效位置中选择一个，或者如果认为应该跳过(Pass)，请明确说明。
坐标说明：
- 列用字母A-G表示（大写或小写均可）
- 行用数字1-7表示
- 请只回复一个有效的坐标（如D4, E5）或者"pass"，不要解释你的决策。"""

        # 调用HKBU_ChatGPT
        chatgpt = HKBU_ChatGPT()
        response = chatgpt.submit(prompt)
        
        # 记录原始响应
        logger.info(f"GPT原始响应: '{response}'")
        
        # 解析响应
        response = response.strip().lower()
        
        # 检查是否是跳过(Pass)
        if "pass" in response:
            # 选择跳过
            room["pass_count"] += 1
            text = "白棋(GPT) 选择跳过(Pass)"
            
            # 检查是否连续两次跳过
            if room["pass_count"] >= 2:
                # 计算得分
                black_territory = sum(row.count("B") for row in board)
                white_territory = sum(row.count("W") for row in board)
                
                black_score = black_territory + room["black_captures"]
                white_score = white_territory + room["white_captures"]
                
                winner = "黑棋" if black_score > white_score else "白棋" if white_score > black_score else "平局"
                result_message = f"游戏结束，双方连续跳过！\n\n黑棋得分：{black_score}（领地：{black_territory}，提子：{room['black_captures']}）\n白棋得分：{white_score}（领地：{white_territory}，提子：{room['white_captures']}）\n\n结果：{winner}获胜！"
                
                room["status"] = "finished"
                text = f"{text}\n\n{result_message}\n\n房间ID：{room_id}"

                # 调用 update_user_record 记录胜负
                for i, player_id in enumerate(room["players"]):
                    username = room["player_names"][i]
                    if winner == "黑棋":
                        if i == 0:  # 黑棋玩家
                            update_user_record(player_id, username, "Go", "win")
                        else:  # 白棋玩家
                            update_user_record(player_id, username, "Go", "loss")
                    elif winner == "白棋":
                        if i == 0:  # 黑棋玩家
                            update_user_record(player_id, username, "Go", "loss")
                        else:  # 白棋玩家
                            update_user_record(player_id, username, "Go", "win")
                    else:  # 平局
                        update_user_record(player_id, username, "Go", "draw")
        
                # 通知所有玩家游戏结束
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
                for pid in room["players"]:
                    try:
                        context.bot.send_message(
                            chat_id=pid,
                            text=text,
                            reply_markup=reply_markup
                        )
                    except Exception as e:
                        logger.error(f"无法发送消息给玩家 {pid}：{e}")
                return  # 游戏结束，直接返回


            else:
                # 切换回合回到玩家
                room["current_turn"] = room["host"]
                text += f"\n\n当前回合：黑棋 ({room['player_names'][0]})\n房间ID：{room_id}\n黑方提子：{room['black_captures']}，白方提子：{room['white_captures']}"
        else:
            # 尝试解析坐标
            # 提取字母和数字
            col_letter = None
            row_number = None
            
            # 从响应中寻找坐标格式（例如A1, B2），确保严格匹配A-G和1-7的范围
            import re
            match = re.search(r'([a-gA-G])([1-7])', response)
            if match:
                col_letter = match.group(1).lower()  # 转换为小写以统一处理
                row_number = match.group(2)
                
                # 转换为棋盘索引
                col = ord(col_letter) - ord('a')
                row = int(row_number) - 1
                
                # 记录转换后的坐标
                logger.info(f"提取坐标: {col_letter.upper()}{row_number}, 转换为索引: [{row},{col}]")
                
                # 验证坐标是否在预计算的有效移动列表中
                move_str = f"{col_letter.upper()}{row_number}"
                if move_str in valid_moves:
                    # 执行落子
                    board[row][col] = stone
                    
                    # 重置连续跳过计数
                    room["pass_count"] = 0
                    
                    # 检查并移除被吃掉的对手棋子
                    captured = remove_captured_stones(board, row, col)
                    if captured > 0:
                        room["white_captures"] += captured
                    
                    # 切换回合回到玩家
                    room["current_turn"] = room["host"]
                    
                    move_text = f"{chr(65 + col)}{row + 1}"
                    text = f"白棋(GPT) 落子于 {move_text}"
                    if captured > 0:
                        text += f"，提子 {captured} 个"
                    
                    text += f"\n\n当前回合：黑棋 ({room['player_names'][0]})\n房间ID：{room_id}\n黑方提子：{room['black_captures']}，白方提子：{room['white_captures']}"
                else:
                    # 如果GPT提供的移动不在有效列表中，使用备用策略
                    logger.warning(f"GPT提供的移动不在有效列表中: {move_str}, 索引: [{row},{col}]")
                    text = _make_fallback_go_move(context, room_id, room)
            else:
                # 如果无法解析坐标，使用备用策略
                logger.warning(f"无法从GPT响应中解析有效坐标: '{response}'")
                text = _make_fallback_go_move(context, room_id, room)
    except Exception as e:
        logger.error(f"使用GPT进行围棋决策时出错：{e}")
        # 出错时使用备用策略
        text = _make_fallback_go_move(context, room_id, room)
    
    # 生成键盘并发送给玩家
    reply_markup = generate_go_board_keyboard(room_id, board)
    try:
        host_id = room["host"]
        context.bot.send_message(
            chat_id=host_id,
            text=text,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"向玩家发送GPT移动消息失败：{e}")

def _make_fallback_go_move(context, room_id, room):
    """当GPT API失败时，使用简单的围棋AI策略作为备用"""
    board = room["board"]
    stone = "W"  # GPT执白棋
    
    # 简单的围棋AI策略：
    # 1. 随机选择一个有效的位置
    # 2. 如果连续尝试10次都找不到有效位置，则选择跳过(Pass)
    valid_moves = []
    for row in range(GO_BOARD_SIZE):
        for col in range(GO_BOARD_SIZE):
            if is_valid_go_move(board, row, col, stone):
                valid_moves.append((row, col))
    
    # 如果有有效的落子位置
    if valid_moves:
        # 随机选择一个位置
        row, col = random.choice(valid_moves)
        
        # 执行落子
        board[row][col] = stone
        
        # 重置连续跳过计数
        room["pass_count"] = 0
        
        # 检查并移除被吃掉的对手棋子
        captured = remove_captured_stones(board, row, col)
        if captured > 0:
            room["white_captures"] += captured
        
        # 切换回合回到玩家
        room["current_turn"] = room["host"]
        
        move_text = f"{chr(65 + col)}{row + 1}"
        text = f"白棋(GPT) 落子于 {move_text}"
        if captured > 0:
            text += f"，提子 {captured} 个"
        
        text += f"\n\n当前回合：黑棋 ({room['player_names'][0]})\n房间ID：{room_id}\n黑方提子：{room['black_captures']}，白方提子：{room['white_captures']}"
    else:
        # 没有有效的落子位置，选择跳过
        room["pass_count"] += 1
        text = "白棋(GPT) 选择跳过(Pass)"
        
        # 检查是否连续两次跳过
        if room["pass_count"] >= 2:
            # 计算得分
            black_territory = sum(row.count("B") for row in board)
            white_territory = sum(row.count("W") for row in board)
            
            black_score = black_territory + room["black_captures"]
            white_score = white_territory + room["white_captures"]
            
            winner = "黑棋" if black_score > white_score else "白棋" if white_score > black_score else "平局"
            result_message = f"游戏结束，双方连续跳过！\n\n黑棋得分：{black_score}（领地：{black_territory}，提子：{room['black_captures']}）\n白棋得分：{white_score}（领地：{white_territory}，提子：{room['white_captures']}）\n\n结果：{winner}获胜！"
            
            room["status"] = "finished"
            text = f"{text}\n\n{result_message}\n\n房间ID：{room_id}"
            # 调用 update_user_record 记录胜负
            for i, player_id in enumerate(room["players"]):
                username = room["player_names"][i]
                if winner == "黑棋":
                    if i == 0:  # 黑棋玩家
                        update_user_record(player_id, username, "Go", "win")
                    else:  # 白棋玩家
                        update_user_record(player_id, username, "Go", "loss")
                elif winner == "白棋":
                    if i == 0:  # 黑棋玩家
                        update_user_record(player_id, username, "Go", "loss")
                    else:  # 白棋玩家
                        update_user_record(player_id, username, "Go", "win")
                else:  # 平局
                    update_user_record(player_id, username, "Go", "draw")

            # 通知所有玩家游戏结束
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("返回主菜单", callback_data=BACK_TO_MAIN)]])
            for pid in room["players"]:
                try:
                    context.bot.send_message(
                        chat_id=pid,
                        text=text,
                        reply_markup=reply_markup
                   )
                except Exception as e:
                    logger.error(f"无法发送消息给玩家 {pid}：{e}")
            return  # 游戏结束，直接返回


        else:
            # 切换回合回到玩家
            room["current_turn"] = room["host"]
            text += f"\n\n当前回合：黑棋 ({room['player_names'][0]})\n房间ID：{room_id}\n黑方提子：{room['black_captures']}，白方提子：{room['white_captures']}"
    
    return text

def create_go_board():
    """创建一个空的围棋棋盘"""
    # 确保棋盘大小为9x9
    board = [["E" for _ in range(GO_BOARD_SIZE)] for _ in range(GO_BOARD_SIZE)]
    logger.info(f"Created Go board with size: {len(board)}x{len(board[0])}")
    return board

def get_liberties(board, row, col, checked=None):
    """检查一个棋子的气数（临近的空点）"""
    if checked is None:
        checked = set()
    
    if row < 0 or row >= GO_BOARD_SIZE or col < 0 or col >= GO_BOARD_SIZE:
        return 0
    
    stone = board[row][col]
    if stone == "E":  # 如果是空点，则有一气
        return 1
    
    pos = (row, col)
    if pos in checked:  # 如果已经检查过，避免无限递归
        return 0
    
    checked.add(pos)
    liberties = 0
    
    # 检查上下左右四个方向
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
    """获取与给定位置相连的所有同色棋子"""
    if stones is None:
        stones = set()
    
    if row < 0 or row >= GO_BOARD_SIZE or col < 0 or col >= GO_BOARD_SIZE:
        return stones
    
    stone = board[row][col]
    if stone == "E":  # 空点
        return stones
    
    pos = (row, col)
    if pos in stones:  # 如果已经加入集合，避免无限递归
        return stones
    
    stones.add(pos)
    
    # 检查上下左右四个方向
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for dr, dc in directions:
        new_row, new_col = row + dr, col + dc
        if 0 <= new_row < GO_BOARD_SIZE and 0 <= new_col < GO_BOARD_SIZE:
            if board[new_row][new_col] == stone:
                get_connected_stones(board, new_row, new_col, stones)
    
    return stones

def remove_captured_stones(board, row, col):
    """移除被吃掉的棋子，返回移除的数量"""
    stone = board[row][col]
    opponent = "W" if stone == "B" else "B"
    captured_count = 0
    
    # 检查上下左右四个方向的对手棋子
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for dr, dc in directions:
        new_row, new_col = row + dr, col + dc
        if 0 <= new_row < GO_BOARD_SIZE and 0 <= new_col < GO_BOARD_SIZE:
            if board[new_row][new_col] == opponent:
                # 检查对手棋子的整个连通区域
                stones = get_connected_stones(board, new_row, new_col)
                # 检查这些棋子是否还有气
                has_liberty = False
                for stone_row, stone_col in stones:
                    # 检查每个棋子的四周
                    for dr2, dc2 in directions:
                        liberty_row, liberty_col = stone_row + dr2, stone_col + dc2
                        if 0 <= liberty_row < GO_BOARD_SIZE and 0 <= liberty_col < GO_BOARD_SIZE:
                            if board[liberty_row][liberty_col] == "E":
                                has_liberty = True
                                break
                    if has_liberty:
                        break
                
                # 如果没有气，则移除这些棋子
                if not has_liberty:
                    for stone_row, stone_col in stones:
                        board[stone_row][stone_col] = "E"
                    captured_count += len(stones)
    
    return captured_count

def is_valid_go_move(board, row, col, stone):
    """检查围棋落子是否有效"""
    # 检查是否在棋盘范围内
    if row < 0 or row >= GO_BOARD_SIZE or col < 0 or col >= GO_BOARD_SIZE:
        return False
    
    # 检查该位置是否已有棋子
    if board[row][col] != "E":
        return False
    
    # 暂时放置棋子
    board[row][col] = stone
    
    # 检查是否有气
    liberties = get_liberties(board, row, col)
    
    # 如果没有气，检查是否能吃掉对手棋子
    if liberties == 0:
        opponent = "W" if stone == "B" else "B"
        captured = False
        
        # 检查上下左右四个方向的对手棋子
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc
            if 0 <= new_row < GO_BOARD_SIZE and 0 <= new_col < GO_BOARD_SIZE:
                if board[new_row][new_col] == opponent:
                    # 检查对手棋子的气
                    opp_liberties = get_liberties(board, new_row, new_col)
                    if opp_liberties == 0:
                        captured = True
                        break
        
        # 如果不能吃掉对手棋子，则这步棋无效
        if not captured:
            board[row][col] = "E"  # 恢复空点
            return False
    
    # 恢复空点（实际落子将在后续操作中进行）
    board[row][col] = "E"
    return True