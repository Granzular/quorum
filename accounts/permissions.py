from rest_framework.permissions import BasePermission


class CanProvisionAccount(BasePermission):
    """Provisioning requires permission to create both account and profile records."""

    message = "You need permission to add users and profiles to provision accounts."

    def has_permission(self, request, view):
        return request.user.has_perms(
            ("accounts.add_customuser", "accounts.add_profile")
        )
