# stuff to set:
# FLASK_ENV=development
# FLASK_APP=server/server.py
# FLASK_SECRET_KEY=devkey
# MONGODB_CONNECT_STRING=mongodb://localhost:27017/thread_dev
# AWS_ACCESS_KEY_ID=<access key>
# AWS_SECRET_ACCESS_KEY=<secret key>

import os
from datetime import datetime
import flask
from flask_moment import Moment
from pymodm import connect
from urllib.parse import urljoin

app = flask.Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
moment = Moment(app)

if "FLASK_SERVER_NAME" in os.environ:
    app.config.update(SERVER_NAME=os.environ["FLASK_SERVER_NAME"])

connect(os.environ["MONGODB_CONNECT_STRING"])


def url_for(*args, **kwargs):
    return (
        flask.url_for(*args, **kwargs)
        .replace("%40", "@")
        .replace("%7C", "|")
        .replace("%28", "(")
        .replace("%29", ")")
    )


def absolute_url(url):
    return urljoin("https://thread.wiki/", url)


@app.context_processor
def inject_url_for_title():
    return dict(url_for=url_for, absolute_url=absolute_url)


@app.context_processor
def inject_utils():
    return dict(
        len=len,
        enumerate=enumerate,
        zip=zip,
        range=range,
        reversed=reversed,
        isinstance=isinstance,
    )


def timestamp():
    return datetime.utcnow()
