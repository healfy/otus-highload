from datetime import datetime as dt
from typing import Optional, List
from fastapi import (
    APIRouter,
    Depends,
)
from fastapi_utils.cbv import cbv

from social_network.db.models import (
    New,
    User,
    AddedPostNewPayload,
    TIMESTAMP_FORMAT
)
from social_network.db.managers import NewsManager

from ..depends import (
    get_user,
    get_news_manager
)
from .models import NewCreatePayload, NewsQueryParams
from ..utils import authorize_only

router = APIRouter()


@cbv(router)
class NewsViewSet:
    user_: Optional[User] = Depends(get_user)
    news_manager: NewsManager = Depends(get_news_manager)

    @router.post('/', response_model=New, status_code=201,
                 responses={
                     201: {'description': 'Hobby created.'},
                     401: {'description': 'Unauthorized.'},
                 })
    @authorize_only
    async def create(self, p: NewCreatePayload) -> New:
        payload = AddedPostNewPayload(author=self.user_.get_short(), text=p.text)
        new = New.from_payload(payload)
        await self.news_manager.create(
            id=new.id,
            author_id=new.author_id,
            news_type=new.type,
            payload=payload,
            created=dt.fromtimestamp(new.created).strftime(TIMESTAMP_FORMAT),
        )
        new.populated = True
        # TODO: send to followers
        return new

    @router.get('/', response_model=List[New], responses={
        200: {'description': 'List of news.'},
    })
    @authorize_only
    async def list(self, q: NewsQueryParams = Depends(NewsQueryParams)) \
            -> List[New]:
        return await self.news_manager.list(author_id=self.user_.id,
                                            order=q.order,
                                            limit=q.paginate_by,
                                            offset=q.offset)
