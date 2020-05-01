from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import DuplicateKeyError
from datetime import timedelta
from .app import app


class User(MongoModel):
    email = fields.EmailField()
    passhash = fields.CharField(default=None)
    flags = fields.ListField(fields.ReferenceField(Flag))
    banned_until = fields.DateTimeField(default=None)

    def add_flag(self, flag):
        self.flags.append(flag)
        User.objects.raw({"_id": self._id}).update({"$push": {"flags": flag._id}})
        self.update_ban()

    def remove_flag(self, flag):
        self.flags.remove(flag)
        User.objects.raw({"_id": self._id}).update({"$pull": {"flags": flag._id}})
        self.update_ban()

    def update_ban(self):
        first = None
        self.banned_until = None
        for flag in self.flags:
            if first is None:
                first = flag.sender
            elif first != flag.sender:
                first = None
                self.banned_until = flag.timestamp + timedelta(days=1)
        User.objects.raw({"_id": self._id, "flags": self.flags.to_son()}).update(
            {"$set": {"banned_until": self.banned_until}}
        )

    def is_banned(self):
        if self.banned_until is None:
            return False
        return self.banned_until > timestamp()

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
