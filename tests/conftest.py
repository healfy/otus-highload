import asyncio
from os.path import dirname, abspath
from datetime import datetime, timedelta
from typing import Any, TypeVar, Type

import aiomysql
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import EmailStr

from social_network.settings import Settings, DatabaseSettings
from social_network.db.migrations.main import migrate
from social_network.db.db import get_connector
from social_network.db.connectors_storage import (
    ConnectorsStorage,
    BaseConnectorStorage
)
from social_network.db.models import (
    AccessToken,
    AuthUser,
    Friendship,
    FriendRequest,
    Hobby,
    UserHobby,
    DatabaseInfo,
    Shard,
    ShardState
)
from social_network.db.sharding.models import Message
from social_network.db.managers import (
    AccessTokenManager,
    AuthUserManager,
    FriendRequestManager,
    FriendshipManager,
    HobbiesManager,
    UsersHobbyManager,
    ShardsManager,
    DatabaseInfoManager
)
from social_network.db.sharding.managers import MessagesManager
from social_network.web.main import app
from social_network.web.api.v1.depends import (
    get_connectors_storage_storage,
    get_settings_depends,
    DependencyInjector
)
from social_network.utils.security import hash_password

CONFIG_PATH = dirname(abspath(__file__)) + '/settings/settings.json'


class VladimirHarconnen:
    ID: int
    EMAIL = EmailStr('Harkonnen.v@mail.com')
    FIRST_NAME = 'Vladimir'
    LAST_NAME = 'Harkonnen'
    PASSWORD = 'death_for_atreides!'
    HASHED_PASSWORD, SALT = hash_password(PASSWORD)
    AGE = 83
    CITY = 'Arrakis'
    GENDER = 'MALE'


class LetoAtreides:
    ID: int
    EMAIL = EmailStr('Atreides.L@mail.com')
    FIRST_NAME = 'Leto'
    LAST_NAME = 'Atreides'
    PASSWORD = 'death_for_harconnen!'
    HASHED_PASSWORD, SALT = hash_password(PASSWORD)
    AGE = 51
    CITY = 'Arrakis'
    GENDER = 'MALE'


class ShaddamIV:
    ID: int
    EMAIL = EmailStr('Emperor@mail.com')
    FIRST_NAME = 'Shaddam'
    LAST_NAME = 'IV'
    PASSWORD = 'SpiceMustFlow'
    HASHED_PASSWORD, SALT = hash_password(PASSWORD)
    AGE = 68
    CITY = None
    GENDER = None


SHARD_0_CONF = DatabaseSettings(
    HOST="localhost",
    PORT=3370,
    USER="otus",
    PASSWORD="otus",
    NAME="otus"
)

SHARD_1_CONF = DatabaseSettings(
    HOST="localhost",
    PORT=3371,
    USER="otus",
    PASSWORD="otus",
    NAME="otus"
)


@pytest.fixture(scope='session', autouse=True)
def event_loop(request):
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Fix for bug https://github.com/pytest-dev/pytest-asyncio/issues/171
pytest_asyncio.plugin.event_loop = event_loop

M = TypeVar('M')


class Factory(DependencyInjector):

    async def add_user_in_db(self, user_data: Any) -> AuthUser:
        manager = self.get_manager(AuthUserManager)
        user = await manager.create(email=user_data.EMAIL,
                                    age=user_data.AGE,
                                    hashed_password=user_data.HASHED_PASSWORD,
                                    salt=user_data.SALT,
                                    first_name=user_data.FIRST_NAME,
                                    last_name=user_data.LAST_NAME,
                                    city=user_data.CITY,
                                    gender=user_data.GENDER)
        user.password = user_data.PASSWORD
        return user

    async def add_token_in_db(self, user_id):
        manager = self.get_manager(AccessTokenManager)
        expired_at = datetime.now() + timedelta(
            seconds=self.conf.TOKEN_EXPIRATION_TIME
        )
        return await manager.create('foobar', user_id, expired_at)

    async def add_friend_request_in_db(self, from_user_id, to_user_id) \
            -> FriendRequest:
        manager = self.get_manager(FriendRequestManager)
        return await manager.create(from_user_id, to_user_id)

    async def add_friendship_in_db(self, user_id, friend_id) -> Friendship:
        manager = self.get_manager(FriendshipManager)
        return await manager.create(user_id, friend_id)

    async def add_hobby_in_db(self, hobby_name: str) -> Hobby:
        manager = self.get_manager(HobbiesManager)
        return await manager.create(hobby_name)

    async def add_user_hobby_in_db(self, user_id, hobby_id) -> UserHobby:
        manager = self.get_manager(UsersHobbyManager)
        return await manager.create(user_id, hobby_id)

    async def add_db(self, db_conf) -> DatabaseInfo:
        db_info_manager = self.get_manager(DatabaseInfoManager)
        return await db_info_manager.create(db_conf)

    async def add_shard(self, db_info, shard_table, shard_key, state) -> Shard:
        shard_manager = self.get_manager(ShardsManager)
        return await shard_manager.create(db_info.id, shard_table, shard_key,
                                          state)

    async def add_message(self, user_id_1, user_id_2, text) -> Message:
        message_manager = self.get_manager(MessagesManager)
        key = f'{user_id_1}:{user_id_2}'
        return await message_manager.create(key, user_id_1, text)


@pytest.fixture(name='settings', scope='session')
def get_settings() -> Settings:
    return Settings.from_json(CONFIG_PATH)


@pytest.fixture(name='cursor', scope='session')
async def get_cursor(settings) -> aiomysql.Cursor:
    db_conf = settings.DATABASE.MASTER
    conn = await aiomysql.connect(host=db_conf.HOST,
                                  port=db_conf.PORT,
                                  user=db_conf.USER,
                                  db=db_conf.NAME,
                                  password=db_conf.PASSWORD.get_secret_value(),
                                  autocommit=True)
    async with conn.cursor() as cursor:
        yield cursor


@pytest.fixture(name='db', autouse=True, scope='session')
async def create_test_database(settings: Settings):
    db_conf = settings.DATABASE.MASTER
    conn = await aiomysql.connect(host=db_conf.HOST,
                                  port=db_conf.PORT,
                                  user=db_conf.USER,
                                  password=db_conf.PASSWORD.get_secret_value(),
                                  autocommit=True)
    cursor = await conn.cursor()
    try:
        await cursor.execute(f"CREATE SCHEMA {db_conf.NAME};")
    except Exception:
        await cursor.execute(f"DROP SCHEMA {db_conf.NAME};")
        await cursor.execute(f"CREATE SCHEMA {db_conf.NAME};")

    migrate(db_conf)
    yield
    await cursor.execute(f"DROP SCHEMA {db_conf.NAME};")


@pytest.fixture(name='connector_storage')
async def get_connector_storage(settings) -> BaseConnectorStorage:
    storage = ConnectorsStorage()
    connector = await get_connector(settings.DATABASE.MASTER)
    storage._connectors[settings.DATABASE.MASTER.json()] = connector
    return storage


@pytest.fixture(name='app')
async def get_test_client(connector_storage, settings) -> TestClient:
    app.dependency_overrides[get_connectors_storage_storage] = lambda: \
        connector_storage
    app.dependency_overrides[get_settings_depends] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides = {}


@pytest.fixture(name='factory')
def get_factory(connector_storage, settings) -> Factory:
    return Factory(connector_storage, settings)


@pytest.fixture(name='user1')
async def add_user_in_db1(factory, cursor: aiomysql.Cursor) -> AuthUser:
    yield await factory.add_user_in_db(VladimirHarconnen)
    await cursor.execute('DELETE FROM users WHERE email = %s;',
                         (VladimirHarconnen.EMAIL,))


@pytest.fixture(name='user2')
async def add_user_in_db2(factory, cursor: aiomysql.Cursor) -> AuthUser:
    yield await factory.add_user_in_db(LetoAtreides)
    await cursor.execute('DELETE FROM users WHERE email = %s;',
                         (LetoAtreides.EMAIL,))


@pytest.fixture(name='user3')
async def add_user_in_db3(factory, cursor: aiomysql.Cursor) -> AuthUser:
    yield await factory.add_user_in_db(ShaddamIV)
    await cursor.execute('DELETE FROM users WHERE email = %s;',
                         (ShaddamIV.EMAIL,))


@pytest.fixture(name='token1')
async def get_token_for_user1(factory, user1) -> AccessToken:
    return await factory.add_token_in_db(user1.id)


@pytest.fixture(name='token2')
async def get_token_for_user2(factory, user2) -> AccessToken:
    return await factory.add_token_in_db(user2.id)


@pytest.fixture(name='token3')
async def get_token_for_user3(factory, user3) -> AccessToken:
    return await factory.add_token_in_db(user3.id)


@pytest.fixture(name='friend_request')
async def get_friend_request(factory, user1, user2) -> FriendRequest:
    return await factory.add_friend_request_in_db(user1.id, user2.id)


@pytest.fixture(name='friendship')
async def get_friendship(factory, user1, user2) -> Friendship:
    return await factory.add_friendship_in_db(user1.id, user2.id)


@pytest.fixture(name='hobby')
async def get_hobby(factory, cursor: aiomysql.Cursor) -> Hobby:
    yield await factory.add_hobby_in_db('War')
    await cursor.execute('DELETE FROM hobbies;')


@pytest.fixture(name='user_hobby')
async def get_user_hobby(factory, user1, hobby, cursor: aiomysql.Cursor) \
        -> UserHobby:
    yield await factory.add_user_hobby_in_db(user1.id, hobby.id)
    await cursor.execute('DELETE FROM users_hobbies_mtm;')


@pytest.fixture(name='drop_users_after_test')
async def drop_users_after_test(cursor: aiomysql.Cursor):
    yield
    await cursor.execute('DELETE FROM users')


@pytest.fixture(name='message_shards')
async def add_message_shards_into_db(factory, cursor):
    db_0 = await factory.add_db(SHARD_0_CONF)
    db_1 = await factory.add_db(SHARD_1_CONF)
    await factory.add_shard(db_0, 'messages', 0, ShardState.READY)
    await factory.add_shard(db_1, 'messages', 1, ShardState.READY)
    yield
    await cursor.execute('DELETE FROM shards_info')
    await cursor.execute('DELETE FROM database_info')


@pytest.fixture(name='clear_messages_after')
async def clear_messages(connector_storage: ConnectorsStorage):
    connector_0 = await connector_storage.get_connector(SHARD_0_CONF)
    connector_1 = await connector_storage.get_connector(SHARD_1_CONF)
    yield
    await connector_0.make_query('DELETE FROM messages', raise_if_empty=False)
    await connector_1.make_query('DELETE FROM messages', raise_if_empty=False)


@pytest.fixture(name='message_1')
async def add_message_1_into_db(factory, cursor, user1, user2, message_shards,
                                clear_messages_after):
    return await factory.add_message(user1.id, user2.id, 'foo')


@pytest.fixture(name='message_2')
async def add_message_2_into_db(factory, cursor, user1, user2, message_shards,
                                clear_messages_after):
    return await factory.add_message(user1.id, user2.id, 'bar')
