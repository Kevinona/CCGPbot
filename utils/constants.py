import logging
import os

# logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# GPT
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


# invite links
GAME_GROUP = "https://t.me/+UCuqOkw1md9kZTRl"
TRAVEL_GROUP = "https://t.me/+Hxk2dIl2qwI4Yzg1"


# game states
SELECTING_GAME, GAME_ACTION = range(2)


# callback data
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


# go
GO_BOARD_SIZE = 7  # 7X7 board
GO_PASS = "pass"  # pass move


# spy
SPY_DISCUSS = "discuss"
SPY_VOTE = "vote"
SPY_SKIP_DISCUSS = "skip_discuss"
SPY_NEXT_ROUND = "next_round"


# bj
SUITS = ['♥', '♦', '♣', '♠']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']


# active list for rooms
active_rooms = {
    TIC_TAC_TOE: {},
    GO: {},
    WHO_IS_SPY: {},
    BLACKJACK: {}
}


# waiting list for players to join
waiting_players = {
    TIC_TAC_TOE: [],
    GO: [],
    WHO_IS_SPY: [],
    BLACKJACK: []
}


# game names for display
game_names = {
    TIC_TAC_TOE: "Tic Tac Toe",
    GO: "Go",
    WHO_IS_SPY: "Who is the Spy",
    BLACKJACK: "Blackjack"
}