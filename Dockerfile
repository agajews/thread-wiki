FROM python:3.6-alpine

RUN adduser -D thread

WORKDIR /home/thread

COPY requirements.txt requirements.txt
RUN python -m venv venv
RUN venv/bin/pip install -r requirements.txt
RUN venv/bin/pip install gunicorn

COPY server server
COPY thread.py start.sh ./
RUN chmod +x start.sh

ENV FLASK_APP thread.py

RUN chown -R thread:thread ./
USER thread

EXPOSE 5000
ENTRYPOINT ["./start.sh"]
