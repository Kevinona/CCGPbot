import logging
import os

# 启用日志记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class HKBU_ChatGPT:
    def submit(self, message):
        import requests
        conversation = [{"role": "user", "content": message}]

        url = ((os.environ['GPT_URL']) 
               + "/deployments/" 
               + (os.environ['GPT_MODELNAME'])
               + "/chat/completions/?api-version="
               + (os.environ['GPT_APIVERSION']))
        
        headers = {'Conteent-Type': 'application/json',
                   'api-key': (os.environ['GPT_TOKEN']),}
        playload = {"messages": conversation}
        response = requests.post(url, json=playload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            return 'Error: ', response


# 群组邀请链接
GAME_GROUP = "https://t.me/+UCuqOkw1md9kZTRl"
TRAVEL_GROUP = "https://t.me/+Hxk2dIl2qwI4Yzg1"


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


