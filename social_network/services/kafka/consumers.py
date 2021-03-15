from random import sample
from asyncio import AbstractEventLoop, create_task, gather
from typing import Dict, Tuple, List
from json import loads

from aiokafka import AIOKafkaConsumer, ConsumerRecord

from aioredis import Redis

from social_network.settings import KafkaSettings, NewsCacheSettings
from social_network.db.models import New, NewsType
from social_network.db.managers import NewsManager, HobbiesManager, UserManager
from social_network.db.connectors_storage import ConnectorsStorage
from social_network.services.redis import RedisService, RedisKeys

from .utils import prepare_ssl_context
from .consts import Topic, Protocol
from .producer import KafkaProducer
from ..base import BaseService


class BaseKafkaConsumer(BaseService):
    group_id: str
    consumer: AIOKafkaConsumer
    topics: Tuple[str]

    def __init__(self,
                 conf: KafkaSettings,
                 loop: AbstractEventLoop,
                 **kwargs):
        self.conf = conf
        self.loop = loop
        self.task = None

    async def start(self):
        protocol = Protocol.SSL if self.conf.USE_SSL else Protocol.PLAIN
        self.consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=f'{self.conf.HOST}:{self.conf.PORT}',
            security_protocol=protocol,
            ssl_context=prepare_ssl_context(self.conf),
            loop=self.loop,
            group_id=self.group_id,
            consumer_timeout_ms=5000
        )
        await self.consumer.start()
        self.task = create_task(self.process())

    async def close(self):
        self.task.cancel()
        await self.consumer.stop()

    @staticmethod
    def parse(record: ConsumerRecord) -> Dict:
        return loads(record.value)

    async def process(self):
        async for record in self.consumer:
            await self._process(self.parse(record))
            await self.consumer.commit()

    async def _process(self, msg: Dict):
        raise NotImplemented


class BaseNewsKafkaConsumer(BaseKafkaConsumer):
    topics = (Topic.News,)


class PopulateNewsKafkaConsumer(BaseKafkaConsumer):
    group_id = 'populate'
    topics = (Topic.Populate,)

    def __init__(self,
                 conf: KafkaSettings,
                 loop: AbstractEventLoop,
                 connectors_storage: ConnectorsStorage,
                 kafka_producer: KafkaProducer):
        super().__init__(conf, loop)
        self.kafka_producer = kafka_producer
        self.hobbies_manager = HobbiesManager(connectors_storage)
        self.user_manager = UserManager(connectors_storage)

    async def _process(self, raw_new: Dict):
        new = New(**raw_new)
        if not new.populated:
            await self.populate(new)
        await self.kafka_producer.send(new.json())

    async def populate(self, new: New):
        if new.type == NewsType.ADDED_HOBBY:
            await self.populate_add_hobby(new)
        else:
            await self.populate_add_friend(new)
        new.populated = True

    async def populate_add_friend(self, new: New):
        for user_type in ('author', 'new_friend'):
            user_id = getattr(new.payload, user_type)
            if isinstance(user_id, int):
                user = await self.user_manager.get(user_id)
                setattr(new.payload, user_type, user.get_short())

    async def populate_add_hobby(self, new: New):
        hobby_id = new.payload.hobby
        if isinstance(hobby_id, int):
            new.payload.hobby = await self.hobbies_manager.get(hobby_id)


class NewsKafkaDatabaseConsumer(BaseNewsKafkaConsumer):
    group_id = 'news_database'

    def __init__(self,
                 conf: KafkaSettings,
                 loop: AbstractEventLoop,
                 connectors_storage: ConnectorsStorage):
        super().__init__(conf, loop)
        self.news_manager = NewsManager(connectors_storage)

    async def _process(self, raw_new: Dict):
        new = New(**raw_new)
        if new.stored:
            return
        await self.news_manager.create_from_model(new)


class NewsKafkaCacheConsumer(BaseNewsKafkaConsumer):
    group_id = 'news_cache'

    def __init__(self,
                 conf: KafkaSettings,
                 news_conf: NewsCacheSettings,
                 loop: AbstractEventLoop,
                 connector_storage: ConnectorsStorage,
                 redis_service: RedisService):
        super().__init__(conf, loop)
        self.news_conf = news_conf
        self.redis: Redis = redis_service
        self.users_manager = UserManager(connector_storage)

    async def _process(self, raw_new: Dict):
        new = New(**raw_new)
        follower_ids = await self.get_follower_ids(new.author_id)
        add_tasks = []
        for follower_id in follower_ids:
            task = create_task(self.add_new_to_feed(follower_id, new))
            add_tasks.append(task)

        await gather(*add_tasks)

    # TODO: refactor it, large big O
    async def add_new_to_feed(self, follower_id: int, new: New):
        max_feed_size = self.news_conf.MAX_FEED_SIZE
        sort_key = lambda raw_new: raw_new['created']

        feed = await self.redis.hget(RedisKeys.USER_FEED, follower_id) or []
        if new.id in {raw_new['id'] for raw_new in feed}:
            # Already cached
            return
        feed = sorted(feed, key=sort_key)

        earliest = new.created < feed[0]['created']
        offset = len(feed) - max_feed_size - 1
        if offset > 0:
            if earliest:
                # No need to add earliest key into cache
                return

            feed = feed[offset:]

        feed.append(new.dict())

        await self.redis.hset(RedisKeys.USER_FEED, follower_id,
                              sorted(feed, key=sort_key, reverse=True))

    async def get_follower_ids(self, user_id: int) -> List[int]:
        max_followers = self.news_conf.MAX_FOLLOWERS_PER_USERS
        followers = await self.redis.hget(RedisKeys.FOLLOWERS, user_id)

        if not followers:
            followers = await self.users_manager.get_friends_ids(user_id)
            await self.redis.hset(RedisKeys.FOLLOWERS, user_id, followers)
            await self.redis.expire(RedisKeys.FOLLOWERS, 5 * 60)

        if len(followers) > max_followers:
            followers = sample(followers, max_followers)

        return followers
