# -*- coding: utf-8 -*-
from multiprocessing import Process
from sbot import main as sbot_main
from gamebot import main as gamebot_main
from chatbot import main as chatbot_main
from utils.constants import *

def main():
    # create two processes to run sbot and gamebot
    sbot_process = Process(target=sbot_main, args=(TRAVEL_GROUP, GAME_GROUP))
    gamebot_process = Process(target=gamebot_main)
    chatbot_process = Process(target=chatbot_main)

    # start the processes
    sbot_process.start()
    gamebot_process.start()
    chatbot_process.start()

    # wait for the processes to finish
    sbot_process.join()
    gamebot_process.join()
    chatbot_process.join()

if __name__ == "__main__":
    main()