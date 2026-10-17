"""Local operator credentials or the platform's temporary AWS role; no logging."""
import ast
from pathlib import Path
import re

import boto3


def session_from_file(path: Path | None = None):
    values = {}
    if path is not None:
        for raw in path.expanduser().read_text().splitlines():
            match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", raw)
            if not match:
                continue
            value = match[2]
            if value.startswith(('"', "'")):
                value = ast.literal_eval(value)
            else:
                value = value.split(" #", 1)[0].strip()
            if isinstance(value, str):
                values[match[1]] = value
        if not values.get("AWS_ACCESS_KEY_ID") or not (values.get("AWS_SECRET_ACCESS_KEY") or values.get("AWS_ACCESS_KEY")):
            raise ValueError("The selected local file lacks AWS credential fields")
    arguments = {"region_name": "ap-southeast-2"}
    if path is not None:
        arguments.update(aws_access_key_id=values["AWS_ACCESS_KEY_ID"],
                         aws_secret_access_key=values.get("AWS_SECRET_ACCESS_KEY") or values["AWS_ACCESS_KEY"],
                         aws_session_token=values.get("AWS_SESSION_TOKEN"))
    return boto3.Session(**arguments)
