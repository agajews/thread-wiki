from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from flask import g, request
from bson import ObjectId
from .app import app, timestamp
from .user import User


def generate_auth_token(_id, expiration=3600 * 24 * 365):
    s = Serializer(app.config["SECRET_KEY"], expires_in=expiration)
    return s.dumps({"_id": str(_id), "timestamp": timestamp().timestamp()}).decode(
        "utf-8"
    )


def verify_auth_token(token):
    s = Serializer(app.config["SECRET_KEY"])
    try:
        data = s.loads(token)
    except:
        return None
    if timestamp().timestamp() - data["timestamp"] > 3600:  # an hour
        g.reissue_token = True
    return User.objects.get({"_id": ObjectId(data["_id"])})


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
        token = generate_auth_token(g.user._id)
        response.set_cookie("token", token, max_age=3600 * 24 * 7)
    return response
