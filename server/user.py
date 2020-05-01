from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import DuplicateKeyError
from .app import app


class User(MongoModel):
    email = fields.EmailField()
    passhash = fields.CharField(default=None)
    flags = fields.EmbeddedDocumentListField(Flag)
    banned_until = fields.DateTimeField(default=None)


class Flag(EmbeddedMongoModel):
    sender = fields.ReferenceField(User)
    timestamp = fields.DateTimeField()
    version = fields.ReferenceField(Version)


class User:
    def __init__(self, _id, email, passhash=None):
        self._id = _id
        self.email = email
        self.passhash = passhash
        self._banned_until = None

    @staticmethod
    def create_or_return(email):
        try:
            db.users.insert_one({"email": email})
        except DuplicateKeyError:
            pass
        return User.from_dict(db.users.find_one({"email": email}))

    @staticmethod
    def find(_id=None, email=None):
        assert _id is not None or email is not None
        if _id is not None:
            query = {"_id": _id}
        elif email is not None:
            query = {"email": email}
        user = db.users.find_one(query)
        if user is None:
            raise UserNotFound()
        return User.from_dict(user)

    @staticmethod
    def from_dict(user):
        return User(user["_id"], user["email"], user.get("passhash"))

    def set_password(self, password):
        self.passhash = generate_password_hash(password)
        db.users.update_one(
            {"email": self.email}, {"$set": {"passhash": self.passhash}}
        )

    def verify_password(self, password):
        return check_password_hash(self.passhash, password)

    def login(self, password):
        g.reissue_token = True
        if self.verify_password(password):
            g.user = self
        else:
            raise IncorrectPassword()

    @property
    def banned_until(self):
        if self._banned_until is None:
            flags = db.flags.find_one({"user": self._id})
            if flags is not None:
                if "banned_until" in flags:
                    self._banned_until = flags["banned_until"]
                else:
                    self._banned_until = 0
        return self._banned_until

    def is_owner(self, page):
        return self._id == page.owner

    def can_edit(self, page):
        if is_owner(page):
            return True
        if page.is_frozen:
            return False
        return timestamp() > self.banned_until


def is_owner():
    if g.user is None:
        return False
    return g.user.is_owner(g.page)


def can_edit():
    if g.user is None:
        return False
    return g.user.can_edit(g.page)


@app.context_processor
def inject_permissions():
    return dict(is_owner=is_owner, can_edit=can_edit)
