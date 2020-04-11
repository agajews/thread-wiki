from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
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


def generate_auth_token(username, expiration=3600 * 24 * 365):
    s = Serializer(app.config["SECRET_KEY"], expires_in=expiration)
    return s.dumps({"username": username}).decode("utf-8")


def verify_auth_token(token):
    s = Serializer(app.config["SECRET_KEY"])
    try:
        data = s.loads(token)
    except:
        return None
    return db.users.find_one({"username": data["username"]})


@app.context_processor
def inject_user():
    return dict(current_user=g.current_user)


@app.before_request
def populate_user():
    token = request.cookies.get("token")
    g.current_user = verify_auth_token(token)
