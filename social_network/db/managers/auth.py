from typing import Optional

from pydantic import EmailStr

from ..queries import UserQueries

from ..crud import CRUDManager
from ..models import AuthUser, Gender


class AuthUserManager(CRUDManager):
    model = AuthUser
    queries = {}

    async def create(self,
                     email: EmailStr,
                     hashed_password: str,
                     salt: str,
                     age: int,
                     first_name: str,
                     last_name: Optional[str] = None,
                     city: Optional[str] = None,
                     gender: Optional[Gender] = None,
                     ) -> AuthUser:
        params = (email, hashed_password, salt, age, first_name,
                  last_name, city, gender)
        return await self._create(params)

    async def get_by_email(self, email: EmailStr) -> AuthUser:
        users = await self.execute(UserQueries.GET_USER_BY_EMAIL, (email,))
        return AuthUser.from_db(users[0])