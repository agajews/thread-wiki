# stuff to set:
# FLASK_ENV=development
# FLASK_APP=server/server.py
# FLASK_SECRET_KEY=<secret_key>
# remember to create indexes for:
#   1. page.titles
#   2. (page.versions.isflagged, page.versions.editor) (maybe not)
#   3. users.email

import os
from datetime import datetime
import flask
from pymongo import MongoClient

app = flask.Flask(__name__)
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]

client = MongoClient("localhost", 27017)
db = client.thread_dev


def url_for(*args, **kwargs):
    return flask.url_for(*args, **kwargs).replace("%40", "@").replace("%7C", "|")


@app.context_processor
def inject_url_for_title():
    return dict(url_for=url_for)


@app.context_processor
def inject_utils():
    return dict(len=len, enumerate=enumerate, zip=zip)


def timestamp():
    return datetime.utcnow().timestamp()
