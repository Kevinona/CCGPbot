from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext
from utils.constants import BOT_TOKEN
# 群组邀请链接
travel_group_link = None
game_group_link = None

def start(update: Update, context: CallbackContext) -> None:
    """处理 /start 命令，显示群组邀请按钮"""
    keyboard = [
        [InlineKeyboardButton("加入 Travel Group", url=travel_group_link)],
        [InlineKeyboardButton("加入 Game Group", url=game_group_link)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("请选择要加入的群组：", reply_markup=reply_markup)

def main(travel_link, game_link):
    global travel_group_link, game_group_link
    travel_group_link = travel_link
    game_group_link = game_link

    updater = Updater(token=BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))

    updater.start_polling()
    updater.idle()