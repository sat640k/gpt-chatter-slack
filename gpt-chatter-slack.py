import os
import sys
import openai
import tiktoken
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

app = App()
msg = []
#msg = [{"role": "system", "content": ""}]

def log_out(message):
    print(message, file=sys.stderr)

def count_token(message_history):
    encoder = tiktoken.get_encoding("cl100k_base")

    count = 0
    for message_part in message_history:
        count += len(enc.encode(message_part))

    return count

@app.message("--help")
def handle_app_exit(say):
    global msg
    msg = []
    log_out("print help.")
    say("会話をリセット：会話の履歴をリセットします。\n会話の履歴の数：会話の履歴の行数を表示します。")

@app.message("会話の履歴の数")
def handle_app_exit(say):
    global msg
    log_out("print count of message history. count=%d" % len(msg))
    say("会話の履歴は、現在%d行を保持しています" % len(msg))
    say("現在記憶している会話のトークン数は%dです。" % count_token(msg))

@app.message("会話をリセット")
def handle_app_exit(say):
    global msg
    msg = []
    log_out("reset message history.")
    say("会話の履歴をリセットしました")

@app.event("message")
def handle_message_events(body, logger, say):
    global msg

    logger.info(body)

    event = body["event"]
    message = event['text']

    log_out("append request: "+message)
    msg.append({"role": "user", "content": message})

    openai.api_key = os.environ["OPENAI_API_TOKEN"]
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=msg,
        temperature=1
    )

    say(response["choices"][0]["message"]["content"])

    answer = response["choices"][0]["message"]["content"].strip()
    log_out("append answer: "+answer)
    msg.append({"role": "assistant", "content": answer})

    if response["usage"]["total_tokens"] > 3000:
        while count_token(msg) > 3000:
            log_out("msg pop")
            say("履歴をひとつ削除します。現在のトークン数は%dです。" % count_token(msg))
            msg.pop(1)
            msg.pop(1)


if __name__ == "__main__":
    try:
        handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
        handler.start()
        sys.exit(0)
    except Exception as e:
        log_out(str(e))
        sys.exit(1)
