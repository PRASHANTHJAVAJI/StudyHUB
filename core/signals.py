from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create a UserProfile when a User is created.
    """
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={'education_level': UserProfile.BACHELORS}
        )

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Save the UserProfile when a User is saved.
    """
    try:
        instance.profile.save()
    except UserProfile.DoesNotExist:
        UserProfile.objects.create(user=instance, education_level=UserProfile.BACHELORS)


# CAS-specific signal handler
try:
    from django_cas_ng.signals import cas_user_authenticated
    
    @receiver(cas_user_authenticated)
    def cas_user_authenticated_callback(sender, user, created, attributes, **kwargs):
        """
        Handle CAS user authentication - ensure UserProfile exists and update email if available.
        """
        if created:
            # New user created via CAS - ensure profile exists
            UserProfile.objects.get_or_create(
                user=user,
                defaults={'education_level': UserProfile.BACHELORS}
            )
            # Update email from CAS attributes if available
            if attributes and 'mail' in attributes:
                email = attributes.get('mail')
                if email and not user.email:
                    user.email = email
                    user.save()
        else:
            # Existing user - just ensure profile exists
            UserProfile.objects.get_or_create(
                user=user,
                defaults={'education_level': UserProfile.BACHELORS}
            )
            # Update email from CAS attributes if available and different
            if attributes and 'mail' in attributes:
                email = attributes.get('mail')
                if email and user.email != email:
                    user.email = email
                    user.save()
except ImportError:
    # django-cas-ng not installed yet, skip this signal
    pass
