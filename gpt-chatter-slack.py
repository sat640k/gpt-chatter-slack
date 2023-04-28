import os
import sys
import openai
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from model import TalkHistory
import re
import logging

logging.basicConfig(stream = sys.stdout, format = "%(levelname)s %(asctime)s - %(message)s", level = logging.ERROR)

#MODEL_NAME = "gpt-3.5-turbo"
MODEL_NAME = "gpt-4"
#MODEL_NAME = "gpt-4-32k"


os.environ["SLACK_BOT_TOKEN"] = TalkHistory.read_secret("/run/secrets/SLACK_BOT_TOKEN")
app = App()


# /echo コマンドを処理する
@app.command("/echo")
def repeat_text(ack, body, logger):
    text = body["text"]
    user = body["user_id"]
    ack(f"Echo from Slack: You said '{text}'")


@app.command("/help")
def handle_display_help(ack, body, logger):
    """
    Slash Command: ヘルプを表示する
    """
    logging.info("print help.")
    ack("help：ヘルプを表示\nclear：会話の履歴をリセットします\nhistory：会話の履歴の行数を表示します\ntemperture {0.0~1.0}：温度パラメータを設定または表示します")


@app.command("/history")
def handle_get_rows(ack, body, logger):
    """
    Slash Command: 会話の履歴の保持数を表示する
    """
    user = body["user_id"]
    history = TalkHistory()
    result = history.hold_rows(user)
    logging.debug(result)

    logging.info("print count of message history. count=%d tokens=%d" % (result["rows"], result["tokens"]))
    ack("現在%d行の会話中の履歴を保持しています。トークン数は%dです。" % (result["rows"], result["tokens"]))

@ app.command("/clear")
def handle_peg_now(ack, body, logger):
    """
    Slash Command: 会話の履歴をリセットする
    """
    logging.debug(body)
    user=body["user_id"]
    history=TalkHistory()
    history.peg_now(user)

    logging.info("reset message history.")
    ack("話題をリセットしました。")


@ app.command("/temperture")
def handle_update_temperture(ack, body, logger):
    """
    Slash Command: tempertureパラメータを更新する
    """
    logging.debug(body)
    text=body["text"]
    user=body["user_id"]
    history=TalkHistory()
    if text.strip() == "":
        # パラメータがない場合は、現在のパラメータを表示する
        logging.info("print temperture. user=%s, temperture=%1.1f" %
                (user, history.get_temperture(user)))
        ack("現在のtempertureパラメータは、%1.1fです。" % history.get_temperture(user))
    elif re.fullmatch(r'[0-1]{\.}[0-9]', text.strip()) or float(text.strip()) < 0.0 or float(text.strip()) > 1.0:
        # パラメータが不正な場合は、エラーを返す
        logging.info("invalid temperture. user=%s, temperture=%1.1f" %
                (user, float(text.strip())))
        ack("tempertureパラメータは、0.0から1.0の間で指定してください。")
    else:
        # 正しいパラメータがある場合は、tempertureを更新する
        history.update_temperture(user, float(text.strip()))
        logging.info("update temperture, user=%s, temperture=%1.1f" %
                (user, float(text.strip())))
        ack("tempertureパラメータを%1.1fに更新しました。" % history.get_temperture(user))

@ app.command("/model")
def handle_select_model(ack, body, logger):
    """
    Slash Command: modelを選択する
    """
    logging.debug(body)
    text=body["text"]
    user=body["user_id"]
    history=TalkHistory()
    if text.strip() == "":
        # パラメータがない場合は、現在のパラメータを表示する
        your_model = history.get_model(user)
        if your_model["name"] == False:
            logging.warning("cannot get model. user=%s" % user)
            ack("現在選択されているモデルを取得できませんでした。")
        else:
            logging.info("print model. user=%s, model=%s" %
                    (user, history.get_model(user)["name"]))
            ack("現在選択されているモデルは、%sです。トークンの最大長は%dです。" % (your_model["name"], your_model["tokens"]))
    else:
        # 正しいパラメータがある場合は、tempertureを更新する
        if history.update_choose_model(user, text.strip()) == False:
            logging.warning("invalid model. user=%s, model=%s" %
                    (user, text.strip()))
            ack("使用するモデルを更新できません。")
        else:
            logging.info("update choose model, user=%s, model=%s" %
                    (user, text.strip()))
            ack("使用するモデルを%sに更新しました。" % history.get_model(user)["name"])

@ app.command("/init")
def handle_init(ack, body, logger):
    """
    Slash Command: ユーザーデーターを初期作成する
    """
    logging.debug(body)
    user=body["user_id"]
    history=TalkHistory()
    history.init_user_data(user)

    logging.info("init user data.")
    ack("ユーザーデータを初期化しました。")

@ app.event("message")
def handle_message_events(body, logger, say):
    """
    DM応答: Slackからのメッセージを受け取り、OpenAI APIに投げる
    """
    history=TalkHistory()

    # Slackから送られてきたメッセージを取得
    event=body["event"]
    user=event['user']
    message=event['text']
    channel_type=event['channel_type']

    # DM以外のメッセージには反応しない
    if channel_type != "im":
        logging.debug("its not direct message. channel_type=%s" % channel_type)
        return

    logging.debug("append request: "+message)

    # 送信メッセージの履歴を保存
    history.save_message(user, "user", message)

    # OpenAI APIに投げて返答を取得
    #openai.api_key=os.environ["OPENAI_API_TOKEN"]
    openai.api_key = TalkHistory.read_secret("/run/secrets/OPENAI_API_TOKEN")
    msg=history.get_recent_message_history(user)
    # msg.append({"role": "assistant", "content": answer})
    logging.info("message history:")
    logging.debug(msg)
    try:
        response=openai.ChatCompletion.create(
            model=MODEL_NAME,
            messages=msg,
            temperature=0.5
        )
    except openai.error.APIConnectionError as e:
        logging.exception(str(e))
        say("OpenAI APIに接続できませんでした。")
        return
    except openai.error.InvalidRequestError as e:
        logging.exception(str(e))
        say("OpenAI APIに接続できませんでした。")
        return
    except Exception as e:
        logging.exception(str(e))
        say("OpenAI APIに接続できませんでした。")
        return

    # OpenAI APIから得られた返答をSlackに送信
    say(response["choices"][0]["message"]["content"])

    # 回答の会話履歴を保存
    answer=response["choices"][0]["message"]["content"].strip()
    logging.info("append answer: "+answer)
    history.save_message(user, "assistant", answer)


if __name__ == "__main__":
    try:
        TalkHistory().create_table()
        #handler=SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
        handler = SocketModeHandler(app, TalkHistory.read_secret("/run/secrets/SLACK_APP_TOKEN"))
        handler.start()
        sys.exit(0)
    except Exception as e:
        logging.exception(str(e))
        sys.exit(1)
