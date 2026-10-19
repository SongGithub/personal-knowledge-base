"""Cloudflare DNS boundary and ACM validation tests; never contact real services."""
import json
import unittest
from unittest.mock import Mock, patch

from cloud_kb.cloudflare import CloudflareDns, ensure_certificate_validated


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return json.dumps({"success": True, "result": self.value}).encode()


class CloudflareTests(unittest.TestCase):
    def client(self, records):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            if request.full_url.endswith("/zones?name=midu.com.au&status=active&per_page=50"):
                value = [{"id": "synthetic-zone", "name": "midu.com.au"}]
            elif request.method == "GET":
                value = records
            else:
                value = {"id": "synthetic-record"}
            return Response(value)

        dns = CloudflareDns("synthetic-token", opener=opener)
        return dns, calls

    def test_creates_dns_only_record_in_the_configured_zone(self):
        dns, calls = self.client([])
        self.assertEqual(dns.ensure_cname("mcp.midu.com.au", "d-example.execute-api.ap-southeast-2.amazonaws.com"), "created")
        request, _ = calls[-1]
        payload = json.loads(request.data)
        self.assertEqual(request.method, "POST")
        self.assertEqual(payload["name"], "mcp.midu.com.au")
        self.assertIs(payload["proxied"], False)
        self.assertEqual(payload["ttl"], 1)

    def test_rejects_records_outside_the_mcp_subdomain(self):
        dns, _calls = self.client([])
        with self.assertRaisesRegex(ValueError, "out_of_scope"):
            dns.ensure_cname("www.midu.com.au", "example.invalid")

    def test_refuses_to_overwrite_a_conflicting_dns_record(self):
        dns, _calls = self.client([{"id": "old", "type": "A", "name": "mcp.midu.com.au", "content": "192.0.2.1"}])
        with self.assertRaisesRegex(RuntimeError, "dns_conflict"):
            dns.ensure_cname("mcp.midu.com.au", "d-example.execute-api.ap-southeast-2.amazonaws.com")

    def test_acm_validation_record_is_written_and_issued_certificate_returns(self):
        dns, _calls = self.client([])
        acm = Mock()
        acm.describe_certificate.return_value = {"Certificate": {
            "DomainName": "mcp.midu.com.au", "Type": "AMAZON_ISSUED", "Status": "ISSUED"}}
        with patch("cloud_kb.cloudflare.time.sleep"):
            ensure_certificate_validated(acm, dns, "synthetic-cert", wait_seconds=0)
        acm.describe_certificate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
