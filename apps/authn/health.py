"""Liveness and database readiness without object-store or SSO side effects."""
from django.db import connection, DatabaseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class LiveView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'status': 'ok', 'service': 'file-manager'})


class ReadyView(LiveView):
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except DatabaseError:
            return Response({'status':'unavailable', 'service':'file-manager'}, status=503)
        return super().get(request)
