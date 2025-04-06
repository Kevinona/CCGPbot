from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging
from utils.constants import *
import os

def main() -> None:
    """启动机器人"""
    updater = Updater(token=os.environ['CHATBOT_TOKEN'])
    dispatcher = updater.dispatcher

    # 设置日志
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    # 添加命令处理器
    dispatcher.add_handler(CommandHandler("start", handle_start_command))
    dispatcher.add_handler(CommandHandler("travelbot", handle_travelbot_command))
    dispatcher.add_handler(CommandHandler("help", handle_help_command))

    # 设置机器人命令
    updater.bot.set_my_commands([
        ('start', '介绍机器人的功能'),
        ('travelbot', '与旅行规划助手沟通'),
        ('help', '获取帮助信息') 
    ])

    # 启动机器人
    updater.start_polling()
    updater.idle()

def handle_start_command(update: Update, context: CallbackContext) -> None:
    """处理 /start 指令"""
    update.message.reply_text(
        "欢迎使用旅行规划咨询机器人！\n\n"
        "我是您的旅行助手，可以为您提供旅行计划、旅游攻略、景点推荐等服务。\n"
        "您可以通过发送 /travelbot 指令与我沟通，例如：\n"
        "/travelbot 推荐一下巴黎的旅游景点\n\n"
        "期待为您服务！"
    )

def handle_travelbot_command(update: Update, context: CallbackContext) -> None:
    """处理 /travelbot 指令"""
    chatgpt = HKBU_ChatGPT()
    if context.args:
        # 动态添加角色 prompt
        role_prompt = "你是一个专业的旅行规划助手，专注于为用户提供旅行计划、旅游攻略、景点推荐等服务。请根据用户的需求，提供详细、实用且贴心的建议。其他话题不予回答。"
        user_query = " ".join(context.args).strip()
        full_message = f"{role_prompt}\n\n用户的问题：{user_query}"

        # 调用 ChatGPT
        reply_message = chatgpt.submit(full_message)
        logging.info(f"用户查询: {user_query}")
        logging.info(f"GPT 回复: {reply_message}")
        update.message.reply_text(reply_message)
    else:
        update.message.reply_text("请提供查询内容，例如：/travelbot 你好")

def handle_help_command(update: Update, context: CallbackContext) -> None:
    """处理 /help 指令"""
    update.message.reply_text(
        "这是一个旅行规划咨询机器人。\n\n"
        "可用命令：\n"
        "/start - 介绍机器人的功能\n"
        "/travelbot - 与旅行规划助手沟通\n"
        "/help - 获取帮助信息"
    )

if __name__ == '__main__':
    main()