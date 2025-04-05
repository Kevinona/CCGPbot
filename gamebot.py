import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, ConversationHandler
import random
import string
import threading
import time

class HKBU_ChatGPT:
    '''
    def __init__(self, config_='./config.ini'):
        if type(config_) == str:
            self.config = configparser.ConfigParser()
            self.config.read(config_)
        elif type(config_) == configparser.ConfigParser:
            self.config = config_
    '''

    def submit(self, message):
        import requests
        conversation = [{"role": "user", "content": message}]

        url = (('https://genai.hkbu.edu.hk/general/rest') 
               + "/deployments/" 
               + ('gpt-4-o-mini')
               + "/chat/completions/?api-version="
               + ('2024-05-01-preview'))
        
        headers = {'Conteent-Type': 'application/json',
                   'api-key': ('7f35c371-9f67-4fc8-9e16-f4a72452f8c0'),}
        playload = {"messages": conversation}
        response = requests.post(url, json=playload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            return 'Error: ', response


# 启用日志记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 请将下面的 TOKEN 替换为您从 BotFather 获取的令牌
TOKEN = "7701763268:AAEuSw1_APH1i-kvWbR50Ac8GlcIf9L9n_c"

# 游戏状态
SELECTING_GAME, GAME_ACTION = range(2)

# 回调数据常量
TIC_TAC_TOE = "tictactoe"
GO = "go"
WHO_IS_SPY = "whoisspy"
BLACKJACK = "blackjack"
CREATE_GAME = "create"
MATCH_PLAYER = "match"
PLAY_WITH_GPT = "gpt"
BACK_TO_MAIN = "back_to_main"
CANCEL_MATCH = "cancel_match"
HIT = "hit"
STAND = "stand"

# 围棋相关常量
GO_BOARD_SIZE = 7  # 使用7x7的小棋盘
GO_PASS = "pass"  # 玩家选择跳过

# 谁是卧底相关常量
SPY_DISCUSS = "discuss"  # 讨论阶段
SPY_VOTE = "vote"  # 投票阶段
SPY_SKIP_DISCUSS = "skip_discuss"  # 跳过讨论直接投票
SPY_NEXT_ROUND = "next_round"  # 进入下一轮游戏

# 纸牌花色和大小
SUITS = ['♥', '♦', '♣', '♠']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

# 活跃房间存储，每个游戏对应一个房间字典
active_rooms = {
    TIC_TAC_TOE: {},
    GO: {},
    WHO_IS_SPY: {},
    BLACKJACK: {}
}

# 等待匹配的玩家列表
waiting_players = {
    TIC_TAC_TOE: [],
    GO: [],
    WHO_IS_SPY: [],
    BLACKJACK: []
}

# 游戏名称映射
game_names = {
    TIC_TAC_TOE: "井字棋",
    GO: "围棋",
    WHO_IS_SPY: "谁是卧底",
    BLACKJACK: "21点"
}

def generate_room_id():
    """生成一个随机6位房间ID"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

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
        "请选择想要玩的游戏："
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
                "status": "with_gpt"
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
    elif result == "draw":
        text = f"平局！\n房间ID：{room_id}\n最终棋盘："
        room["status"] = "finished"
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
    elif result == "draw":
        text = f"平局！\n房间ID：{room_id}\n最终棋盘："
        room["status"] = "finished"
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

def gpt_make_blackjack_decision(context, room_id, room):
    """让GPT在21点游戏中做出决策"""
    # 找到GPT的索引
    gpt_idx = room["players"].index("GPT")
    
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

def main() -> None:
    """启动机器人"""
    updater = Updater(token=TOKEN)
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

if __name__ == "__main__":
    main()
