#!/bin/bash
source venv/bin/activate
export FLASK_ENV=development
export FLASK_APP=server/server.py
export FLASK_SECRET_KEY=devkey
export MONGODB_CONNECT_STRING=mongodb://localhost:27017/thread_dev
