from __future__ import annotations

from app.middleware.error_handler import DuplicateError
from app.models.member import Member
from app.repositories.unit_of_work import IUnitOfWorkFactory


class MemberService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def create(self, pan: str, name: str) -> Member:
        with self._uow_factory() as uow:
            existing = uow.members.get_by_pan(pan)
            if existing:
                raise DuplicateError(f"Member with PAN {pan} already exists")
            return uow.members.create(pan=pan, name=name)

    def list_all(self) -> list[Member]:
        with self._uow_factory() as uow:
            return uow.members.list_all()
