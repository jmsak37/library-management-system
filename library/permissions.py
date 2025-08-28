# library/permissions.py
from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Allow read-only access to unauthenticated users.
    Unsafe methods require admin.
    """
    def has_permission(self, request, view):
        # Safe methods allowed
        if request.method in permissions.SAFE_METHODS:
            return True
        # Otherwise user must be staff
        return bool(request.user and request.user.is_staff)
