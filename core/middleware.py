from django.shortcuts import redirect
from .models import UserProfile


class SecurityHeadersMiddleware:
    """
    Middleware to add security headers that prevent caching and back button issues.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add headers to prevent caching of authenticated pages
        if request.user.is_authenticated:
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        
        return response


class OnboardingMiddleware:
    """
    Redirect authenticated users to complete their profile after first login.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        exempt_prefixes = (
            "/static/",
            "/media/",
            "/admin/",
            "/login/",
            "/signup/",
            "/logout/",
            "/complete-profile/",
            "/departments/",
            "/api/",
        )

        if request.user.is_authenticated and not path.startswith(exempt_prefixes):
            try:
                profile = request.user.profile
                # Admins skip onboarding entirely — auto-complete it
                if request.user.is_staff or request.user.is_superuser:
                    if not profile.onboarding_complete:
                        profile.onboarding_complete = True
                        profile.save(update_fields=['onboarding_complete'])
                elif not profile.onboarding_complete:
                    return redirect('core:complete_profile')
            except UserProfile.DoesNotExist:
                # Auto-complete for admins, redirect others
                if request.user.is_staff or request.user.is_superuser:
                    UserProfile.objects.create(user=request.user, onboarding_complete=True)
                else:
                    return redirect('core:complete_profile')

        return self.get_response(request)
