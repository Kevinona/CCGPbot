from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext
import os
# invite link
travel_group_link = None
game_group_link = None

def start(update: Update, context: CallbackContext) -> None:
    """/start command handler"""
    keyboard = [
        [InlineKeyboardButton("Join Travel Group", url=travel_group_link)],
        [InlineKeyboardButton("Join Game Group", url=game_group_link)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Choose the group you want to join:", reply_markup=reply_markup)

def main(travel_link, game_link):
    global travel_group_link, game_group_link
    travel_group_link = travel_link
    game_group_link = game_link

    updater = Updater(token=os.environ['SBOT_TOKEN'], use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))

    updater.start_polling()
    updater.idle()