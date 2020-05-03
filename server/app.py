# stuff to set:
# FLASK_ENV=development
# FLASK_APP=server/server.py
# FLASK_SECRET_KEY=<secret_key>
# MONGODB_CONNECT_STRING=<secret_key>

import os
from datetime import datetime
import flask
from pymodm import connect

app = flask.Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

if "FLASK_SERVER_NAME" in os.environ:
    SERVER_NAME = os.environ["FLASK_SERVER_NAME"]

connect(os.environ["MONGODB_CONNECT_STRING"])


def url_for(*args, **kwargs):
    return flask.url_for(*args, **kwargs).replace("%40", "@").replace("%7C", "|")


@app.context_processor
def inject_url_for_title():
    return dict(url_for=url_for)


@app.context_processor
def inject_utils():
    return dict(len=len, enumerate=enumerate, zip=zip, range=range, reversed=reversed)


def timestamp():
    return datetime.utcnow()
