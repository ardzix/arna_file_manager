import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("files", "0001_initial")]

    operations = [
        migrations.AlterField(model_name="fileasset", name="owner_scope", field=models.CharField(choices=[("user", "User"), ("org", "Organization"), ("service", "Service")], max_length=10)),
        migrations.AlterField(model_name="folder", name="owner_scope", field=models.CharField(choices=[("user", "User"), ("org", "Organization"), ("service", "Service")], max_length=10)),
        migrations.AlterField(model_name="fileasset", name="created_by_user_id", field=models.UUIDField(blank=True, null=True)),
        migrations.AddField(model_name="fileasset", name="owner_service_id", field=models.UUIDField(blank=True, null=True)),
        migrations.AddField(model_name="fileasset", name="created_by_service_id", field=models.UUIDField(blank=True, null=True)),
        migrations.AddIndex(model_name="fileasset", index=models.Index(fields=["owner_scope", "owner_service_id", "status"], name="files_filea_owner_s_eeebfc_idx")),
        migrations.CreateModel(
            name="FileShare",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_by_user_id", models.UUIDField(blank=True, null=True)),
                ("created_by_service_id", models.UUIDField(blank=True, null=True)),
                ("file", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shares", to="files.fileasset")),
            ],
        ),
        migrations.AddIndex(model_name="fileshare", index=models.Index(fields=["token_hash", "expires_at", "revoked_at"], name="files_files_token_h_1f7c7c_idx")),
    ]
