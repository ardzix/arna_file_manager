from unittest.mock import patch
from django.db import OperationalError
from django.test import TestCase


class StorageReadinessTests(TestCase):
    def test_database_failure_affects_readiness_but_not_liveness(self):
        with patch('apps.authn.health.connection.cursor', side_effect=OperationalError('synthetic')):
            self.assertEqual(self.client.get('/health/ready').status_code, 503)
            self.assertEqual(self.client.get('/health/live').status_code, 200)

    def test_readiness_checks_configured_database(self):
        self.assertEqual(self.client.get('/health/ready').status_code, 200)
