from flask import Flask, request
from utils.logger import logger
from utils.message import message
from utils.responseParse import *
from utils.const import help_msg
import time
import requests
import yaml
import platform
import sys
import os
import json
import _thread
from pprint import pprint, pformat

# 读取配置文件
with open('./config.yml', encoding='utf8') as f:
    config = yaml.load(f.read(), Loader=yaml.SafeLoader)
    host = config['host']['address']
    port = config['host']['port']

# 创建日志对象
log = logger(config['log']['log-level'], 'AaTM.log')

# 创建Flask服务器对象
app = Flask(__name__)

# Python版本校验
version = platform.python_version_tuple()   # 获取Python版本
if int(version[1]) < 10:
    log.error(
        f'Your Python version is lower than 3.10, currently {platform.python_version()}. Please update it to 3.10+ to use this program!')
    sys.exit(1)
else:
    from utils.linkParse import getLink

# 已经推送过的入侵列表
invasions = []
previous_alerts = ''
if os.path.exists('invasions.txt'):
    with open('invasions.txt', encoding='utf8') as f:
        for line in f.readlines():
            invasions.append(line.replace('\n', ''))
else:
    with open('invasions.txt', 'wt') as f:
        f.close()


@app.route('/', methods=['GET', 'POST'])
def Handler():
    data = request.get_json()
    log.info(f'收到了新的payload：{data}')
    msg = message(data)
    if msg.user_id == config['options']['bot-qq']:
        if config['options']['auto-recall']['enable'] and 'AaTMbot 发现了新的警报任务！' not in msg.message:  # 自动撤回，推送类不撤回
            _thread.start_new_thread(
                autoRecall, (msg.message_id, config['options']['auto-recall']['delay']))
    else:
        if not msg.message.startswith('/'):
            log.debug(f'检测到非命令消息 {msg.message}，进行忽略')
            return 'Hello World'    # 非命令直接忽略
        if msg.message in ['/help', '/帮助']:
            content = help_msg
        else:
            link = getLink(msg.message)
            if not link.startswith('https://'):
                log.debug(f'消息 {msg.message} 无法解析出对应的链接')
                content = link
            elif not 'robot' in link:
                log.debug(f'由消息 {msg.message} 解析得到api链接 {link}')
                content = json.loads(getDetail(link))
                access_protocol = link.split('/')[-1]
                json_parser = {
                    'sortie': sortieParser,
                    'invasions': invasionParser
                }
                content = json_parser[access_protocol](content, invasions)
            else:
                log.debug(f'由消息 {msg.message} 解析得到api链接 {link}')
                content = getDetail(link)
        msgSender(msg, content)
    return 'Hello World'


def autoRecall(msg_id, delay):  # 自动撤回
    log.info(f'识别到由bot发出的消息，自动撤回已开启，将在 {delay} 秒后撤回消息 {msg_id}')
    time.sleep(delay)
    response = requests.get(
        f'{config["options"]["cqhttp"]["address"]}/delete_msg?message_id={msg_id}&access_token={config["options"]["cqhttp"]["access-token"]}')
    log.debug(f'撤回消息：状态码为 {response.status_code}，返回内容为{response.text}')


def msgSender(msg: message, content):   # 消息发送
    log.debug(f'正在尝试进行消息发送……')
    if msg.type == 'private' and (msg.user_id in config['options']['private'] or '*' in config['options']['private']):
        message = f'[CQ:reply,id={msg.message_id}]{content}'
    elif msg.type == 'group' and (msg.group_id in config['options']['groups'] or '*' in config['options']['groups']):
        message = f'[CQ:reply,id={msg.message_id}][CQ:at,qq={msg.user_id}]{content}'
    response = requests.get(
        f'{config["options"]["cqhttp"]["address"]}/send_msg?user_id={msg.user_id}&message_type={msg.type}&message={message}&group_id={msg.group_id}&access_token={config["options"]["cqhttp"]["access-token"]}')
    log.debug(f'通过调用链接 {config["options"]["cqhttp"]["address"]}/send_msg 发送了消息，query参数为 user_id={msg.user_id}&message_type={msg.type}&message={message}&group_id={msg.group_id}&access_token={config["options"]["cqhttp"]["access-token"]}')


def getDetail(link):    # 通过requests调用API获得详细信息
    response = requests.get(link).text
    log.debug(f'调用了 {link}，得到了如下的信息：{response}')
    return response


def autoPushAlert():    # 自动推送警报任务
    response = requests.get(
        f"{config['api']['address']}{config['api']['warframe']}{config['api']['warframe-path']['alerts']}")
    if response.text != '暂无警报事件' and previous_alerts != response.text:
        msg = f'''AaTMbot 发现了新的警报任务！

{response.text}'''
        previous_alerts = response.text
        if config['auto-push']['alerts']['channel']['groups']:
            groups = config['options']['groups']
            for group in groups:
                requests.get(f'{config["options"]["cqhttp"]["address"]}/send_msg?&message_type=group&message={msg}&group_id={group}&access_token={config["options"]["cqhttp"]["access-token"]}')
        if config['auto-push']['alerts']['channel']['private']:
            users = config['options']['private']
            for user in users:
                requests.get(f'{config["options"]["cqhttp"]["address"]}/send_msg?&message_type=private&message={msg}&user_id={user}&access_token={config["options"]["cqhttp"]["access-token"]}')
            
if __name__ == '__main__':  # 主函数
    if config['auto-push']['alerts']['enable']:
        log.info(f'检测到自动撤回启用，每次bot消息发送后将在 {config["options"]["auto-recall"]["delay"]} 秒后自动撤回')
        _thread.start_new_thread(autoPushAlert)
    app.run(host=host, port=port, debug=False)
