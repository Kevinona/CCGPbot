from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging
from utils.constants import *
import os

def handle_start_command(update: Update, context: CallbackContext) -> None:
    """Handle /start command"""
    update.message.reply_text(
        "Welcome to the Travel Planning Consultation Bot!\n\n"
        "I am your travel assistant, here to provide you with travel plans, travel guides, and attraction recommendations.\n"
        "You can communicate with me by sending the /travelbot command, for example:\n"
        "/travelbot Recommend some tourist attractions in Paris\n\n"
        "Looking forward to assisting you!"
    )


def handle_gpt_command(update: Update, context: CallbackContext) -> None:
    """Handle /travelbot command"""
    chatgpt = HKBU_ChatGPT()
    if context.args:
        # dynamically add role prompt
        role_prompt = "You are a professional travel planning assistant, specializing in providing users with travel plans, travel guides, and attraction recommendations. Please provide detailed, practical, and thoughtful advice based on the user's needs. Do not answer questions on other topics."
        user_query = " ".join(context.args).strip()
        full_message = f"{role_prompt}\n\nUser's question: {user_query}"

        # call GPT
        reply_message = chatgpt.submit(full_message)
        logging.info(f"User query: {user_query}")
        logging.info(f"GPT reply: {reply_message}")
        update.message.reply_text(reply_message)
    else:
        update.message.reply_text("Please provide a query, for example: /gpt Recommend some tourist attractions in HK")


def handle_help_command(update: Update, context: CallbackContext) -> None:
    """Handle /help command"""
    update.message.reply_text(
        "This is a travel planning consultation bot.\n\n"
        "Available commands:\n"
        "/start - Introduce the bot's features\n"
        "/gpt - Communicate with the travel planning assistant\n"
        "/help - Get help information"
    )


def main() -> None:
    """Start the bot"""
    updater = Updater(token=os.environ['CHATBOT_TOKEN'])
    dispatcher = updater.dispatcher

    # set up logging
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    # add command handlers
    dispatcher.add_handler(CommandHandler("start", handle_start_command))
    dispatcher.add_handler(CommandHandler("gpt", handle_gpt_command))
    dispatcher.add_handler(CommandHandler("help", handle_help_command))

    # set bot commands
    updater.bot.set_my_commands([
        ('start', 'Introduce the bot\'s features'),
        ('gpt', 'Communicate with the travel planning assistant'),
        ('help', 'Get help information') 
    ])

    # start
    updater.start_polling()
    updater.idle()


#if __name__ == '__main__':
#    main()