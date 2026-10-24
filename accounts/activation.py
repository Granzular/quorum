from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def activation_credentials(user):
    """Issue expiring activation credentials for an inactive, provisioned account."""
    if user.is_active or user.has_usable_password():
        raise ValueError("Only accounts awaiting activation may receive a token.")
    return {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    }
