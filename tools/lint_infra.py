#!/usr/bin/env python3
"""Run every pinned cfn-lint check with an evidence-based IAM catalogue update.

AWS DescribeType AWS::ApiGatewayV2::Stage create/update handlers declare
apigateway:TagResource/UntagResource (observed Sydney, 2026-10-18). The live
CreateStage denial also names TagResource. cfn-lint 1.57.2 omits these actions.
Only those two catalogue entries are added; W3037 remains enabled, including
rejection of misspelled actions. No lint rule or template result is suppressed.
"""
import argparse
from copy import deepcopy
from pathlib import Path

from cfnlint.api import lint
from cfnlint.core import get_rules


def rules_with_provider_actions():
    rules = get_rules([], [], [])
    permission_rule = rules.all_rules["W3037"]
    permission_rule._service_map = deepcopy(permission_rule._service_map)
    actions = permission_rule._service_map["apigateway"]["Actions"]
    for action in ("tagresource", "untagresource"):
        actions.setdefault(action, {})
    assert rules.is_rule_enabled(permission_rule)
    return rules


def validate(text):
    return lint(text, rules=rules_with_provider_actions(), regions=["ap-southeast-2"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("templates", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for template in args.templates:
        for match in validate(template.read_text()):
            print(f"{template}: {match}")
            failed |= match.rule.id.startswith(("E", "W"))
    raise SystemExit(1 if failed else 0)
