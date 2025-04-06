# -*- coding: utf-8 -*-
from multiprocessing import Process
from sbot import main as sbot_main
from gamebot import main as gamebot_main
from utils.constants import *

def main():
    # 创建两个进程分别运行 sbot 和 gamebot
    sbot_process = Process(target=sbot_main, args=(TRAVEL_GROUP, GAME_GROUP))
    gamebot_process = Process(target=gamebot_main)

    # 启动进程
    sbot_process.start()
    gamebot_process.start()

    # 等待进程结束
    sbot_process.join()
    gamebot_process.join()

if __name__ == "__main__":
    main()