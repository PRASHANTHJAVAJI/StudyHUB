from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import UserProfile

class Command(BaseCommand):
    help = 'Create user profiles for existing users'

    def handle(self, *args, **options):
        users_without_profiles = User.objects.filter(profile__isnull=True)
        
        created_count = 0
        for user in users_without_profiles:
            UserProfile.objects.create(user=user, education_level=UserProfile.BACHELORS, onboarding_complete=False)
            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'Created profile for user: {user.username}')
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} user profiles')
        )
