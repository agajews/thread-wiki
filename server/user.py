from pymodm import fields, MongoModel, EmbeddedMongoModel
from pymodm.errors import DoesNotExist
from pymongo.operations import IndexModel
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from flask import g

from .app import app, timestamp
from .errors import *
from .page import PageVersion


class User(MongoModel):
    email = fields.EmailField()
    passhash = fields.CharField(default=None)

    class Meta:
        indexes = [IndexModel("email", unique=True)]

    @property
    def is_banned(self):
        if self.banned_until is None:
            return False
        return self.banned_until > timestamp()

    @property
    def can_create(self):
        return not self.is_banned

    @property
    def banned_until(self):
        if not hasattr(self, "_banned_until"):
            self._banned_until = None
            first = None
            for flag in self.flags:
                if first is None:
                    first = flag.sender
                elif first != flag.sender:
                    first = None
                    self._banned_until = flag.timestamp + timedelta(days=1)
        return self._banned_until

    @property
    def flags(self):
        if not hasattr(self, "_flags"):
            versions = (
                PageVersion.objects.raw({"editor": self._id, "is_flagged": True})
                .only("flag")
                .all()
            )
            self._flags = [version.flag for version in versions]
        return self._flags

    @staticmethod
    def create_or_return(email):
        user = User(email=email)
        try:
            user.save()
        except DuplicateKeyError:
            return User.objects.get({"email": email})
        return user

    def set_password(self, password):
        self.passhash = generate_password_hash(password)
        User.objects.raw({"_id": self._id}).update(
            {"$set": {"passhash": self.passhash}}
        )

    def verify_password(self, password):
        return check_password_hash(self.passhash, password)

    @staticmethod
    def find(email):
        try:
            return User.objects.get({"email": email})
        except DoesNotExist:
            raise UserNotFound()
