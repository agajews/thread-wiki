# stuff to set:
# FLASK_ENV=development
# FLASK_APP=server/server.py
# FLASK_SECRET_KEY=<secret_key>
import os
from datetime import datetime
import flask
from pymongo import MongoClient

app = flask.Flask(__name__)
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]

client = MongoClient("localhost", 27017)
db = client.thread_dev


def url_for(*args, **kwargs):
    return flask.url_for(*args, **kwargs).replace("%40", "@")


@app.context_processor
def inject_url_for_title():
    return dict(url_for=url_for)


def timestamp():
    return datetime.utcnow().timestamp()
