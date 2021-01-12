from typing import List
from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)
from fastapi_utils.cbv import cbv

from social_network.db import (
    UserManager,
    UserHobby,
    UsersHobbyManager,
    User,
    DatabaseError,
)

from .models import UsersQueryParams
from ..depends import (
    get_user_manager_depends,
    get_user_hobby_manager_depends,
    get_user_id,
)
from ..utils import authorize_only

router = APIRouter()


@cbv(router)
class UserViewSet:
    user_id: int = Depends(get_user_id)
    user_manager: UserManager = Depends(get_user_manager_depends)
    user_hobby_manager: UsersHobbyManager = Depends(
        get_user_hobby_manager_depends
    )

    @router.get('/', response_model=List[User], responses={
        200: {'description': 'List of users.'},
    })
    async def users(self, q: UsersQueryParams = Depends(UsersQueryParams)):
        offset = (q.page - 1) * q.paginate_by
        users = await self.user_manager.list(first_name=q.first_name,
                                             last_name=q.last_name,
                                             friend_id=q.friends_of,
                                             order=q.order,
                                             order_by=q.order_by,
                                             limit=q.paginate_by,
                                             offset=offset)
        if not users:
            return []
        hobbies = await self.user_hobby_manager.get_hobby_for_users(
            [user.id for user in users]
        )
        for user in users:
            user.hobbies = hobbies[user.id]
        return users

    @router.get('/{id}', response_model=User, responses={
        200: {'description': 'User.'},
        404: {'description': 'User not found.'}
    })
    async def user(self, id: int) -> User:
        user = await self.user_manager.get(id)
        hobbies = await self.user_hobby_manager.get_hobby_for_users(
            [user.id]
        )
        user.hobbies = hobbies[user.id]
        return user

    @router.put('/hobbies/{id}', status_code=201, response_model=UserHobby,
                responses={
                    200: {'description': 'Hobby added.'},
                    400: {'description': 'Already added.'},
                })
    @authorize_only
    async def add_hobby(self, id: int) -> UserHobby:
        try:
            return await self.user_hobby_manager.create(self.user_id, id)
        except DatabaseError:
            raise HTTPException(400, detail='Hobby not found or already added')

    @router.delete('/hobbies/{id}', status_code=204, responses={
        204: {'description': 'Hobby removed.'},
    })
    @authorize_only
    async def remove_hobby(self, id: int):
        await self.user_hobby_manager.delete_by_ids(self.user_id, id)
