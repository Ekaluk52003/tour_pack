from allauth.account.adapter import DefaultAccountAdapter
from django.forms import ValidationError


class NoNewUsersAccountAdapter(DefaultAccountAdapter):
    """
    Adapter that disables user registration in django-allauth
    """
    def is_open_for_signup(self, request):
        """
        This method controls whether user registration is allowed.
        Return False to disable registration.
        """
        return False
