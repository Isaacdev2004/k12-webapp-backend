from django.conf import settings
from djoser import email

class PasswordResetEmail(email.PasswordResetEmail):
    template_name = "email/password_reset.html"

    def get_context_data(self):
        context = super().get_context_data()
        
        # Get the protocol (http or https)
        protocol = 'https' if not settings.DEBUG else 'http'
        domain = settings.FRONTEND_URL.replace('https://', '').replace('http://', '')
        
        # Generate the password reset URL
        reset_url = f"{protocol}://{domain}/{settings.DJOSER['PASSWORD_RESET_CONFIRM_URL'].format(**context)}"
        
        context['reset_url'] = reset_url
        context['site_name'] = settings.SITE_NAME
        return context 

class ActivationEmail(email.ActivationEmail):
    template_name = "email/activation.html"

    def get_context_data(self):
        context = super().get_context_data()
        protocol = 'https' if not settings.DEBUG else 'http'
        domain = settings.FRONTEND_URL.replace('https://', '').replace('http://', '')
        activation_url = f"{protocol}://{domain}/{settings.DJOSER['ACTIVATION_URL'].format(**context)}"
        context['activation_url'] = activation_url
        context['site_name'] = settings.SITE_NAME
        return context

class ConfirmationEmail(email.ConfirmationEmail):
    template_name = "email/confirmation.html"

    def get_context_data(self):
        context = super().get_context_data()
        context['site_name'] = settings.SITE_NAME
        return context 