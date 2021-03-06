import datetime

import fastapi
import pymongo
import pymongo.errors
import pymongo.results

from apps.common.enums import CodeAudiences
from apps.common.handlers import PasswordsHandler, TokensHandler
from apps.users.models import UserModel
from apps.users.repositories import UserRepository
from apps.users.schemas import JWTPayloadSchema, JWTRefreshSchema, UserCreateSchema, UserLoginSchema, UserUpdateSchema
from fastapi_mongodb.exceptions import HandlerException, RepositoryException
from fastapi_mongodb.handlers import BaseHandler, mongo_duplicate_key_error_handler
from fastapi_mongodb.pagination import Paginator
from fastapi_mongodb.projectors import BaseProjector
from fastapi_mongodb.repositories import BaseRepositoryConfig
from fastapi_mongodb.sorting import SortBuilder
from fastapi_mongodb.types import OID

__all__ = ["UsersHandler"]


class UsersHandler(BaseHandler):
    def __init__(self, request: fastapi.Request):
        super().__init__(request=request)
        self.user_repository = UserRepository()

    async def create_user(self, request: fastapi.Request, user: UserCreateSchema) -> dict:
        """Create new user"""
        user_model = UserModel(
            password_hash=PasswordsHandler.make_password(password=user.password), **user.dict(exclude_unset=True)
        )
        try:
            result: pymongo.results.InsertOneResult = await self.user_repository.insert_one(
                document=user_model.to_db(),
                session=request.state.db_session,
            )
        except pymongo.errors.DuplicateKeyError as error:
            mongo_duplicate_key_error_handler(model_name="User", fields=["email"], error=error)
        else:
            return {"acknowledged": result.acknowledged, "inserted_id": result.inserted_id}

    async def retrieve_user(self, request: fastapi.Request, query: dict):
        return await self.user_repository.find_one(query=query, session=request.state.db_session)

    async def users_list(
        self,
        request: fastapi.Request,
        query: dict,
        sort_by: SortBuilder,
        paginator: Paginator,
        projector: BaseProjector,
    ):
        return await self.user_repository.find(
            query=query,
            sort=sort_by.to_db(model=UserModel),
            skip=paginator.skip,
            limit=paginator.limit,
            session=request.state.db_session,
            projection=projector.to_db(),
            repository_config=BaseRepositoryConfig(convert=False),
        )

    async def delete_user(self, request: fastapi.Request, query: dict):
        result = await self.user_repository.delete_one(query=query, session=request.state.db_session)
        return {"acknowledged": result.acknowledged, "deleted_count": result.deleted_count}

    async def update_user(self, request: fastapi.Request, _id: OID, update: UserUpdateSchema):
        update_dict = update.dict(exclude_unset=True)
        if update_dict:
            password = update_dict.pop("password", None)
            if password is not None:
                update_dict["password_hash"] = PasswordsHandler.make_password(password=password)
            update_dict["updated_datetime"] = datetime.datetime.utcnow()
            user = await self.user_repository.find_one_and_update(
                query={"_id": _id},
                update={"$set": update_dict},
                session=request.state.db_session,
                return_document=pymongo.ReturnDocument.AFTER,
                repository_config=BaseRepositoryConfig(convert=False),
            )
        else:
            user = await self.user_repository.find_one(
                query={"_id": _id},
                session=request.state.db_session,
                repository_config=BaseRepositoryConfig(convert=False),
            )
        user = UserModel.from_db(data=user)
        return user

    async def login(self, request: fastapi.Request, credentials: UserLoginSchema) -> dict:
        try:
            user: UserModel = await self.retrieve_user(
                request=request, query={"email": credentials.email, "is_active": True}
            )
        except RepositoryException:
            pass
        else:
            if PasswordsHandler.check_password(password=credentials.password, password_hash=user.password_hash):
                return {
                    "access": TokensHandler.create_code(data={"id": str(user.id)}),
                    "refresh": TokensHandler.create_code(data={"id": str(user.id)}, aud=CodeAudiences.REFRESH_TOKEN),
                }
        raise HandlerException("Invalid credentials.")

    async def refresh(self, data: JWTRefreshSchema) -> dict:
        payload: JWTPayloadSchema = TokensHandler.read_code(
            code=data.refresh, aud=CodeAudiences.REFRESH_TOKEN, convert_to=JWTPayloadSchema
        )
        return {
            "access": TokensHandler.create_code(data={"id": payload.id}),
            "refresh": TokensHandler.create_code(data={"id": payload.id}, aud=CodeAudiences.REFRESH_TOKEN),
        }
