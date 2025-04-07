# CCGPbot

## Project Overview
CCGPbot is a multi-functional Telegram bot that provides the following features:
- **Travel Assistant**: Offers travel plans, guides, and attraction recommendations by GPT.
- **Game Bot**: Provide Tic Tac Toe, Go, Who is the Spy, and Blackjack.
- **Group Management**: Provides quick access to join travel and game groups.
The bot is deployed on the Azure cloud platform, utilizing Azure SQL Database for data storage and HKBU GPT for GPT connect.

## Features
### 1. Travel Assistant
- Use the `/gpt` command to interact with the travel assistant.
- Get detailed travel advice, attraction recommendations, and travel plans.

### 2. Game Bot
Supports the following games:
- **Tic Tac Toe**: Play against another player or GPT.
- **Go**: A 7x7 board game with basic rules and scoring.
- **Who is the Spy**: A multiplayer game with a hidden spy.
- **Blackjack**: A card game supporting multiple players and GPT.

### 3. Group Management
- Provides buttons to join travel and game groups.

## File Structure
```
    CCGPbot/ 
        ├── .github/
        │   │
        │   └── workflows/
        │       │
        │       └── main_ccgdocker.yml # GitHub Actions
        ├── games/
        │   │
        │   ├── bj.py # blackjack
        │   │
        │   ├── go.py # go
        │   │
        │   ├── spy.py # who is the spy
        │   │
        │   └── ttt.py # tic tac toe
        │
        ├── utils/
        │   │
        │   └── constants.py # constants
        │
        ├── chatbot.py # travel assistant functionality
        │
        ├── database.py # database operations
        │
        ├── dockerfile # docker configuration
        │
        ├── gamebot.py # game bot functionality
        │
        ├── main.py # main entry point for all bots
        │
        ├── README.md # documentation
        │
        ├── requirements.txt # Python requirements
        │
        ├── sbot.py # group management bot
        │
        └── session_name.session # session file
```

## Usage Instructions
### 1. Travel Assistant
  - `/start`: Introduce the travel assistant features.
  - `/gpt <query>`: Get travel advice, e.g., `/gpt Recommend attractions in HK`.
  - `/help`: Display help information.

### 2. Game Bot
  - `/start`: Select a game to play.
  - `/record`: View your game win/loss/draw record.
  - `/rooms`: View active game rooms.
  - `/join` <Room ID>: Join a specific game room.
  - `/cancel`: Cancel the current operation.

 3. Group Management
  - `/start`: Display buttons to join travel and game groups.

## Requirements
Before running the bot, ensure the following:
### 1. Install all dependencies listed in `requirements.txt`:
```bash
pip install -r requirements.txt
```
### 2. Set the following environment variables:
- **Bot Tokens**:
  - `GAMEBOT_TOKEN`: Token for the game bot.
  - `SBOT_TOKEN`: Token for the group management bot.
  - `CHATBOT_TOKEN`: Token for the travel assistant bot.

- **Database Configuration**:
  - `DB_SERVER`: Azure SQL Database server address.
  - `DB_DATABASE`: Name of the database.
  - `DB_USERNAME`: Database username.
  - `DB_PASSWORD`: Database password.

- **GPT Configuration**:
  - `GPT_URL`: URL for the HKBU GPT service.
  - `GPT_MODELNAME`: Model name for GPT.
  - `GPT_APIVERSION`: API version for GPT.
  - `GPT_TOKEN`: Token for accessing GPT.

## Deployment
Using Docker
1. Build the Docker image:
```bash
docker build -t ccgpbot .
```
2. Run the container:
```bash
docker run -d --name ccgpbot \
    -e CHATBOT_TOKEN=<your-chatbot-token> \
    -e GAMEBOT_TOKEN=<your-gamebot-token> \
    -e SBOT_TOKEN=<your-sbot-token> \
    -e DB_SERVER=<your-azure-db-server> \
    -e DB_DATABASE=<your-database-name> \
    -e DB_USERNAME=<your-db-username> \
    -e DB_PASSWORD=<your-db-password> \
    -e GPT_URL=<your-gpt-url> \
    -e GPT_MODELNAME=<your-gpt-modelname> \
    -e GPT_APIVERSION=<your-gpt-apiversion> \
    -e GPT_TOKEN=<your-gpt-token> \
    ccgpbot
```
