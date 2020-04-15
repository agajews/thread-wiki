from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from datetime import datetime
from flask import g, request
from .app import app, db


def create_user(email, username):
    db.users.insert({"email": email, "username": username})


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
    return {"user": user, "username": user["username"]}


def timestamp():
    return datetime.utcnow().timestamp()


def generate_auth_token(username, expiration=3600 * 24 * 365):
    s = Serializer(app.config["SECRET_KEY"], expires_in=expiration)
    return s.dumps({"username": username, "timestamp": timestamp()}).decode("utf-8")


def verify_auth_token(token):
    s = Serializer(app.config["SECRET_KEY"])
    try:
        data = s.loads(token)
    except:
        return None
    if timestamp() - data["timestamp"] > 3600:  # an hour
        g.reissue_token = True
    return db.users.find_one({"username": data["username"]})


@app.before_request
def populate_user():
    token = request.cookies.get("token")
    g.user = verify_auth_token(token)
    g.reissue_token = False


@app.after_request
def reissue_token(response):
    if g.reissue_token and g.user is not None:
        token = generate_auth_token(g.user["username"])
        response.set_cookie("token", token, max_age=3600 * 24 * 7)
    return response