import os
from typing import Optional
from sqlmodel import SQLModel, Field, Session, create_engine, select, and_, Column
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.pool import QueuePool, StaticPool
from datetime import datetime
import tiktoken
import sys,traceback

MODEL_MAX_TOKENS = {
    "gpt-3.5-turbo": 4096,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
}

class Message(SQLModel, table=True):
    """メッセージヒストリー"""
    id: Optional[int] = Field(nullable=True, primary_key=True)
    user: Optional[str] = Field(max_length=32, nullable=False)
    role: Optional[str] = Field(max_length=10, nullable=False)
    content: Optional[str] = Field(sa_column=Column(TEXT))
    token_number: Optional[int] = Field(nullable=False)
    status: int = 0
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now,
                                 nullable=False, sa_column_kwargs={'onupdate': datetime.now})


class User(SQLModel, table=True):
    """ユーザー設定"""
    user: Optional[str] = Field(max_length=32, nullable=False, primary_key=True)
    model: Optional[str] = Field(default="gpt-4", max_length=32, nullable=False)
    temperture: Optional[float] = Field(default=0.5, nullable=False)
    recent_message_origin: Optional[int] = Field(default=0, nullable=False)
    status: int = 0
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now,
                                 nullable=False, sa_column_kwargs={'onupdate': datetime.now})


class TalkHistory:
    engine = None
    DATABASE_URL = None

    def __init__(self) -> None:
        #DATABASE_URL = "sqlite:///db/history.db"
        self.DATABASE_URL = TalkHistory.read_secret("/run/secrets/DATABASE_URL")
        self.engine = create_engine(
            self.DATABASE_URL, poolclass=StaticPool, echo=True)


    @staticmethod
    def read_secret(secret_path):
        with open(secret_path, 'r') as secret_file:
            secret = secret_file.read().strip()
        return secret

    def count_token(self, message_history):
        """
        トークン数をカウントする
        """
        enc = tiktoken.get_encoding("cl100k_base")

        count = 0
        for message_part in message_history:
            count += len(enc.encode(message_part))

        return count
    
    def init_user_data(self, user: str):
        """
        ユーザーのデータを初期化する
        """
        try:
            with Session(self.engine) as session:
                # ユーザー検索
                statement = select(User).where(User.user == user)
                result_user = session.exec(statement).first()
                if result_user == None:
                    # ユーザーが存在しない場合は新規作成する
                    session.add(User(user=user, model="gpt-4", temperture=0.5, recent_message_origin=0))
                    session.commit()
                else:
                    # ユーザーが存在する場合は、何もしない
                    pass

            return True

        except Exception as e:
            print(e)
            raise e

    def get_model(self, user: str):
        """
        現在のモデル選択を取得する
        """
        try:
            with Session(self.engine) as session:
                # ユーザー検索
                statement = select(User).where(User.user == user)
                result_user = session.exec(statement).first()
                if result_user == None:
                    # ユーザーが存在しない場合はエラー
                    return False
                return {
                    "name": result_user.model,
                    "tokens": MODEL_MAX_TOKENS[result_user.model]
                }

        except Exception as e:
            print(e)
            raise e

    def update_choose_model(self, user: str, model: str):
        """
        モデルを選択する
        """

        if model in MODEL_MAX_TOKENS == False:
            return False

        try:
            with Session(self.engine) as session:
                # ユーザー検索
                statement = select(User).where(User.user == user)
                result_user = session.exec(statement).first()
                if result_user == None:
                    # ユーザーが存在しない場合は新規作成する
                    return False

                result_user.model = model
                session.commit()

        except Exception as e:
            print(e)
            raise e

    def get_recent_message_history(self, user: str):
        """
        最新の会話履歴を取得する
        """
        try:
            with Session(self.engine) as session:
                # ユーザーの選択するモデルを取得する
                choose_model = self.get_model(user)
                if choose_model == False:
                    return False

                # ユーザーとの会話の開始地点を取得する
                statement = select(User).where(User.user == user)
                result_user = session.exec(statement).first()
                recent_message_origin = 0
                if result_user == None:
                    # ユーザーが存在しない場合は新規作成する
                    session.add(User(user=user))
                    session.commit()
                else:
                    recent_message_origin = result_user.recent_message_origin

                # 会話履歴を取得する
                statement = select(Message).where(and_(Message.user == user, Message.id >
                                                       recent_message_origin, Message.status == 0)).order_by(Message.id.desc())
                result_recent = []
                result_tokens = 0
                for history_part in session.exec(statement).all():
                    # 直近の会話履歴のうち、トークン数が上限を超えない範囲のみ取得して返す
                    result_tokens += history_part.token_number
                    if result_tokens > choose_model["tokens"]:
                        # トークン数が上限を超えた場合は、その会話履歴を終端として保存し、メッセージづくりを終える
                        self.peg_now(user, history_part.id)
                        break

                    result_recent.append(
                        {"role": history_part.role, "content": history_part.content})

                result_recent.reverse()
                return result_recent

        except Exception as e:
            print(e)
            raise e

    def save_message(self, user: str, role: str, message: str):
        """
        メッセージを保存する
        """
        try:
            with Session(self.engine) as session:
                session.add(Message(user=user, role=role, content=message,
                            token_number=self.count_token(message)))
                session.commit()

        except Exception as e:
            print(e)
            raise e

    def get_temperture(self, user: str):
        """
        現在の温度設定を取得する
        """
        try:
            with Session(self.engine) as session:
                # ユーザー検索
                statement = select(User).where(User.user == user)
                result_user = session.exec(statement).first()
                if result_user == None:
                    # ユーザーが存在しない場合はエラー
                    return False
                return result_user.temperture

        except Exception as e:
            print(e)
            raise e

    def update_temperture(self, user: str, temperture: float):
        """
        温度設定を更新する
        温度は0.0〜1.0の範囲で設定する
        """

        if float(temperture) < 0.0 or float(temperture) > 1.0:
            return False

        try:
            with Session(self.engine) as session:
                # ユーザー検索
                statement = select(User).where(User.user == user)
                result_user = session.exec(statement).first()
                if result_user == None:
                    # ユーザーが存在しない場合は新規作成する
                    return False

                result_user.temperture = temperture
                session.commit()

        except Exception as e:
            print(e)
            raise e

    def peg_now(self, user: str, message_id=None):
        """
        最新の会話履歴を終端にする
        """
        try:
            with Session(self.engine) as session:
                # ユーザーとの会話の開始地点を取得する
                statement = select(User).where(User.user == user)
                result_user = session.exec(statement).first()
                if result_user == None:
                    # ユーザーが存在しない場合は何もしない
                    return False

                # 会話の開始地点が指定されていない場合は、同ユーザーの会話履歴の最新レコードを終端として取得する
                if message_id == None:
                    # 同ユーザーの会話履歴の最新レコードを取得する
                    statement = select(Message).where(
                        and_(Message.user == user, Message.status == 0)).order_by(Message.id.desc())
                    result_recent = session.exec(statement).first()
                    if result_recent == None:
                        return False
                    message_id = result_recent.id

                # 最新の会話履歴を終端にする
                result_user.recent_message_origin = message_id
                session.commit()
                return True

        except Exception as e:
            print(e)
            return False

    def hold_rows(self, user: str):
        """
        会話履歴の行数をカウントする
        """
        try:
            with Session(self.engine) as session:
                # ユーザーの会話履歴の終端レコードのIDを取得
                statement = select(User).where(User.user == user)
                result_user = session.exec(statement).first()
                if result_user == None:
                    # ユーザーが存在しない場合はエラー
                    return False
                recent_message_origin = result_user.recent_message_origin

                # 同ユーザーの有効な会話履歴を取得し、行数とトークン数を数える
                statement = select(Message).where(
                    and_(Message.user == user, Message.id > recent_message_origin))
                result_rows = 0
                result_tokens = 0
                for row in session.exec(statement).all():
                    result_rows += 1
                    result_tokens += row.token_number
                return {
                    "rows": result_rows,
                    "tokens": result_tokens
                }

        except Exception as e:
            print(e)
            return False

    @staticmethod
    def create_table():
        history = TalkHistory()
        SQLModel.metadata.create_all(history.engine)
