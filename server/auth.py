from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import DuplicateKeyError
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from flask import g, request
from bson import ObjectId
from .app import app, db, timestamp


def create_user(email):
    inserted = db.users.insert_one({"email": email})
    return inserted.inserted_id


def create_or_return_user(email):
    try:
        return create_user(email)
    except DuplicateKeyError:
        return db.users.find_one({"email": email})["_id"]


def set_password(email, password):
    db.users.update_one(
        {"email": email}, {"$set": {"passhash": generate_password_hash(password)}}
    )


def verify_password(email, password):
    user = db.users.find_one({"email": email})
    if user is None:
        return {"error": "notregistered"}
    if "passhash" not in user:
        return {"error": "passwordnotset"}
    if not check_password_hash(user["passhash"], password):
        return {"error": "incorrectpassword"}
    return {"user": user}


def generate_auth_token(_id, expiration=3600 * 24 * 365):
    s = Serializer(app.config["SECRET_KEY"], expires_in=expiration)
    return s.dumps({"_id": str(_id), "timestamp": timestamp()}).decode("utf-8")


def verify_auth_token(token):
    s = Serializer(app.config["SECRET_KEY"])
    try:
        data = s.loads(token)
    except:
        return None
    if timestamp() - data["timestamp"] > 3600:  # an hour
        g.reissue_token = True
    return db.users.find_one({"_id": ObjectId(data["_id"])})


@app.before_request
def populate_user():
    token = request.cookies.get("token")
    g.reissue_token = False
    g.user = verify_auth_token(token)


@app.after_request
def manage_token(response):
    if g.user is None:
        response.set_cookie("token", "", expires=0)
    elif g.reissue_token:
        token = generate_auth_token(g.user["_id"])
        response.set_cookie("token", token, max_age=3600 * 24 * 7)
    return response
