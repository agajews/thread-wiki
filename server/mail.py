import boto3
from botocore.exceptions import ClientError

client = boto3.client("ses", region_name="us-east-1")


def send_email(dest_email, subject, html_body, text_body):
    print("Sending email to", dest_email)
    try:
        client.send_email(
            Destination={"ToAddresses": [dest_email]},
            Message={
                "Body": {
                    "Html": {"Charset": "UTF-8", "Data": html_body},
                    "Text": {"Charset": "UTF-8", "Data": text_body},
                },
                "Subject": {"Charset": "UTF-8", "Data": subject},
            },
            Source="Thread Mailbot <mailbot@thread.wiki>",
        )
    except ClientError as e:
        print(e.response["Error"]["Message"])
