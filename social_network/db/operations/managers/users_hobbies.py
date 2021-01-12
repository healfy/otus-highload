from functools import lru_cache
from collections import defaultdict
from typing import List, Dict
from itertools import groupby

from ..base import BaseModel
from ..db import BaseDatabaseConnector
from ..queries import UserHobbyQueries

from .crud import CRUDManager
from .hobbies import Hobby


class UserHobby(BaseModel):
    _table_name = 'users_hobbies_mtm'
    _fields = ('id', 'user_id', 'hobby_id')

    user_id: int
    hobby_id: int


class UsersHobbyManager(CRUDManager):
    model = UserHobby
    # TODO: refactor crud
    queries = {}

    async def create(self, user_id: int, hobby_id: int) -> UserHobby:
        return await self._create((user_id, hobby_id))

    async def delete_by_ids(self, user_id: int, hobby_id: int):
        params = (user_id, hobby_id)
        return await self.execute(UserHobbyQueries.DROP_USER_HOBBY, params,
                                  raise_if_empty=False)

    async def get_hobby_for_users(self, user_ids: List[int]) \
            -> Dict[int, List[Hobby]]:
        params = (user_ids,)
        results = await self.execute(UserHobbyQueries.GET_HOBBIES_FOR_USERS,
                                     params, raise_if_empty=False)
        parsed_result: Dict[int, List[Hobby]] = defaultdict(list)
        for key, group in groupby(results, lambda x: x[0]):
            for item in group:
                parsed_result[key].append(Hobby(id=item[1], name=item[2]))
        return parsed_result


# TODO: class method?
@lru_cache(1)
def get_user_hobby_manager(connector: BaseDatabaseConnector) \
        -> UsersHobbyManager:
    return UsersHobbyManager(connector)
