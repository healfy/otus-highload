import asyncio
from uuid import uuid4
from typing import Optional, List
from fastapi import (
    APIRouter,
    Depends,
    WebSocket
)
from fastapi_utils.cbv import cbv

from social_network.db.models import (
    New,
    User,
    AddedPostNewPayload,
)
from social_network.db.managers import NewsManager, UserManager
from social_network.services.kafka import KafkaProducer
from social_network.services.redis import RedisService, RedisKeys

from ..depends import (
    get_user,
    get_kafka_producer,
    get_redis_client,
    get_news_manager,
    get_user_manager,
)
from .models import NewCreatePayload, NewsQueryParams
from ..utils import authorize_only

router = APIRouter()


# TODO: indempotent requests in all places
@cbv(router)
class NewsViewSet:
    kafka_producer: KafkaProducer = Depends(get_kafka_producer)
    redis: RedisService = Depends(get_redis_client)
    user_: Optional[User] = Depends(get_user)
    news_manager: NewsManager = Depends(get_news_manager)
    user_manager: UserManager = Depends(get_user_manager)

    @router.post('/', response_model=New, status_code=201,
                 responses={
                     201: {'description': 'Hobby created.'},
                     401: {'description': 'Unauthorized.'},
                 })
    @authorize_only
    async def create(self, p: NewCreatePayload) -> New:
        payload = AddedPostNewPayload(author=self.user_.get_short(),
                                      text=p.text)
        new = New.from_payload(payload)
        await self.news_manager.create_from_model(new)
        new.populated, new.stored = True, True
        await self.kafka_producer.send(new.json())
        return new

    @router.get('/feed/', response_model=List[New], responses={
        200: {'description': 'User feed.'},
    })
    @authorize_only
    async def feed(self, q: NewsQueryParams = Depends(NewsQueryParams)) \
            -> List[New]:
        cached = await self.get_feed_from_cache()
        cached = cached[q.offset:q.paginate_by + q.offset]
        if len(cached) >= q.paginate_by:
            return cached

        friends_ids = await self.user_manager.get_friends_ids(self.user_.id)
        return await self.news_manager.list(author_ids=friends_ids,
                                            order=q.order,
                                            limit=q.paginate_by,
                                            offset=q.offset)

    @router.get('/{user_id}/', response_model=List[New], responses={
        200: {'description': 'List of news for user.'},
    })
    async def list(self, user_id: int,
                   q: NewsQueryParams = Depends(NewsQueryParams)) -> List[New]:
        return await self.news_manager.list(author_ids=[user_id],
                                            order=q.order,
                                            limit=q.paginate_by,
                                            offset=q.offset)

    async def get_feed_from_cache(self) -> List[New]:
        feed = await self.redis.hget(
            RedisKeys.USER_FEED, str(self.user_.id)
        ) or []
        return [New(**new) for new in feed]


@router.websocket('/ws')
async def real_time_feed(ws: WebSocket):
    await ws.accept()
    while True:
        await asyncio.sleep(5)
        data = {
            "id": str(uuid4()),
            "author_id": 1,
            "type": "ADDED_POST",
            "payload": {
                "author": {
                    "id": 1,
                    "first_name": "sender",
                    "last_name": "sender"
                },
                "text": "Hello world"
            },
            "created": 1613736977.09478,
            "populated": True,
            "stored": True
        }
        await ws.send_json(data)
