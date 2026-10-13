from django.db import models


class DeviceProofReplay(models.Model):
    proof_hash = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField(db_index=True)
