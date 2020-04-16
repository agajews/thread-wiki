import os
from datetime import datetime
from flask import Flask
from pymongo import MongoClient

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]

client = MongoClient("localhost", 27017)
db = client.thread_dev


def timestamp():
    return datetime.utcnow().timestamp()
