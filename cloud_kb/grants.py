"""Owner browser decisions for the fixed read/new-note capture policy."""
import hashlib
import json
import time
import uuid

from botocore.exceptions import ClientError


READ_PREFIXES = ("Ideas/", "Projects/", "Areas/", "Resources/", "Archive/",
                 "Wiki/", "Personal Facts/", "Clippings/", "Templates/", "AGENTS.md")
CAPTURE_PREFIX = "Resources/_Review/AI Learning/"
GRANT_DAYS = (90, 365)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


class GrantDecisions:
    def __init__(self, table, owner_sub):
        self.table, self.owner_sub = table, owner_sub

    def key(self, client_id):
        return {"PK": "GRANT#" + self.owner_sub, "SK": "CLIENT#" + client_id}

    def get(self, client_id):
        return self.table.get_item(Key=self.key(client_id), ConsistentRead=True).get("Item")

    def decide(self, client_id, *, previous, action, mode, days):
        """Compare the displayed record and atomically save its decision/audit."""
        if action not in {"approve", "revoke"} or mode not in {"read", "capture"} or days not in GRANT_DAYS:
            raise ValueError("invalid_decision")
        if action == "revoke" and previous is None:
            raise ValueError("grant_changed")
        now, version = int(time.time()), uuid.uuid4().hex
        if action == "approve":
            item = {**self.key(client_id), "CreatedAt": now,
                    "ExpiresAt": now + days * 86400, "Revoked": False,
                    "Scopes": ["kb:read"] + (["kb:capture"] if mode == "capture" else []),
                    "Prefixes": sorted(READ_PREFIXES),
                    "CapturePrefixes": [CAPTURE_PREFIX] if mode == "capture" else [],
                    "PolicyRevision": "capture-raw-v2"}
        else:
            item = {**previous, "Revoked": True}
        item.update(GrantVersion=version, ApprovedAt=now, ApprovalMethod="owner-google-browser-v1")
        put = {"TableName": self.table.name, "Item": item,
               "ConditionExpression": "attribute_not_exists(PK)"}
        if previous is not None:
            # Compare every displayed attribute, including legacy grants without
            # a version. A stale browser tab must not undo a later revocation.
            names, values, conditions = {}, {}, []
            for index, (name, value) in enumerate(sorted(previous.items())):
                if name in {"PK", "SK"}:
                    continue
                attr, val = f"#a{index}", f":v{index}"
                names[attr], values[val] = name, value
                conditions.append(f"{attr} = {val}")
            if "GrantVersion" not in previous:
                names["#version"] = "GrantVersion"
                conditions.append("attribute_not_exists(#version)")
            put.update(ConditionExpression=" AND ".join(conditions),
                       ExpressionAttributeNames=names, ExpressionAttributeValues=values)
        audit = {"PK": "GRANT_AUDIT#" + hashlib.sha256(self.owner_sub.encode()).hexdigest(),
                 "SK": f"{now:012d}#{version}", "ClientId": client_id,
                 "Action": action, "DecidedAt": now, "GrantVersion": version,
                 "PreviousDigest": digest(previous), "ExpiresAtGrant": item["ExpiresAt"],
                 "Scopes": item["Scopes"], "Prefixes": item["Prefixes"],
                 "CapturePrefixes": item.get("CapturePrefixes", []),
                 "ApprovalMethod": item["ApprovalMethod"]}
        try:
            # The DynamoDB resource client serializes native values, including
            # conditional operands, for both transaction writes.
            self.table.meta.client.transact_write_items(TransactItems=[
                {"Put": put}, {"Put": {"TableName": self.table.name, "Item": audit,
                                        "ConditionExpression": "attribute_not_exists(PK)"}},
            ], ClientRequestToken=version)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                raise ValueError("grant_changed") from None
            raise
        return item
