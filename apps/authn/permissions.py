"""Shared SSO permission checks for humans, devices and service callers."""
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


def require_permission(principal, permission):
    granted = principal.scopes if principal.principal_type == 'service' else principal.permissions
    if permission not in granted:
        raise PermissionDenied(f'Missing SSO permission: {permission}.')


class HasFilePermission(BasePermission):
    def has_permission(self, request, view):
        permission = view.required_permissions.get(request.method)
        if permission:
            require_permission(request.user, permission)
        return True
