# Rice SSO (CAS) Login Setup Guide

This guide provides clear steps to implement Rice University's Single Sign-On (SSO) authentication using CAS (Central Authentication Service).

## Prerequisites

1. **Rice IT Approval**: Your application must be registered with Rice IT
2. **Service URL**: Your production URL must be whitelisted in Rice's CAS server
3. **Valid Rice Credentials**: You need a Rice NetID to test authentication

## Step-by-Step Implementation

### Step 1: Install Required Packages

```bash
pip install django-cas-ng
```

Add to `requirements.txt`:
```
django-cas-ng==5.0.0
```

### Step 2: Update Settings (`studyhub/settings.py`)

Add `django_cas_ng` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    'rest_framework',
    'django_filters',
    'django_cas_ng',  # Add this
    # local
    'core',
]
```

Add CAS middleware to `MIDDLEWARE` (after AuthenticationMiddleware):

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_cas_ng.middleware.CASMiddleware",  # Add this
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]
```

Update authentication backends:

```python
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'django_cas_ng.backends.CASBackend',  # Add this
]
```

Add CAS configuration:

```python
# CAS (Central Authentication Service) settings for Rice SSO
CAS_SERVER_URL = 'https://idp.rice.edu/idp/profile/cas/'
CAS_VERSION = '3'
CAS_REDIRECT_URL = '/feed/'
CAS_LOGOUT_COMPLETELY = True
CAS_CREATE_USER = True  # Automatically create users from CAS
CAS_USERNAME_ATTRIBUTE = 'uid'  # Attribute to use as username
CAS_EMAIL_ATTRIBUTE = 'mail'  # Attribute to use as email
CAS_FORCE_CHANGE_USERNAME_CASE = 'lower'  # Convert username to lowercase
```

Update LOGIN_URL:

```python
LOGIN_URL = "/accounts/login"  # Change from "/login/" to "/accounts/login"
```

### Step 3: Update URLs (`studyhub/urls.py`)

Add CAS authentication URLs:

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('rest_framework.urls')),
    path('', include('core.urls', namespace='core')),
]

# CAS authentication URLs
try:
    import django_cas_ng.views
    urlpatterns += [
        path('accounts/login/', django_cas_ng.views.LoginView.as_view(), name='cas_ng_login'),
        path('accounts/logout/', django_cas_ng.views.LogoutView.as_view(), name='cas_ng_logout'),
    ]
except ImportError:
    pass
```

### Step 4: Update Login Template (`templates/registration/login.html`)

Add a CAS login button (optional - you can also redirect all login to CAS):

```html
<div class="d-grid mb-3">
    <a href="{% url 'cas_ng_login' %}" class="btn btn-outline-primary btn-lg">
        <i class="fas fa-university me-2"></i>RICE SSO Login
    </a>
</div>
```

### Step 5: Handle User Profile Creation (`core/signals.py`)

Add signal handler to create UserProfile when CAS users are created:

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile

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
    # django-cas-ng not installed, skip this signal
    pass
```

### Step 6: Run Migrations

```bash
python manage.py migrate
```

This will create the necessary django_cas_ng tables.

### Step 7: Contact Rice IT

**Before going to production, you MUST:**

1. **Contact Rice IT** to register your application
2. **Provide your service URL** (e.g., `https://yourdomain.com`)
3. **Get approval** for your application to use Rice CAS
4. **Verify** your service URL is whitelisted in Rice's CAS server

**Contact Information:**
- Rice IT Help Desk
- Email: helpdesk@rice.edu
- Phone: (713) 348-HELP (4357)

**Information to provide:**
- Application name: StudyHub
- Service URL: Your production URL
- Purpose: Student study session management platform
- Expected user base: Rice students

### Step 8: Test the Implementation

1. **Start the server:**
   ```bash
   python manage.py runserver
   ```

2. **Access login:**
   - Go to `http://127.0.0.1:8000/accounts/login/`
   - You should be redirected to Rice CAS login page

3. **Login with Rice credentials:**
   - Enter your Rice NetID and password
   - After successful authentication, you'll be redirected back to your app

4. **Verify user creation:**
   - Check Django admin to see if the user was created
   - Verify UserProfile was created automatically

## Important Notes

### Development vs Production

- **Development**: You can test locally, but you'll need Rice credentials
- **Production**: Your service URL MUST be registered with Rice IT

### Service URL Configuration

The service URL in Rice's CAS server must match exactly:
- If your app is at `https://studyhub.rice.edu`, that's your service URL
- CAS will redirect back to this URL after authentication
- Make sure this URL is accessible and properly configured

### User Attributes

Rice CAS provides these attributes:
- `uid`: Username (NetID)
- `mail`: Email address
- Other attributes may be available - check with Rice IT

### Logout Behavior

With `CAS_LOGOUT_COMPLETELY = True`:
- Logging out from your app also logs out from Rice CAS
- Users will need to log in again to Rice CAS for other services

## Troubleshooting

### Issue: "Service not authorized"
- **Solution**: Your service URL is not registered with Rice IT
- Contact Rice IT to register your application

### Issue: Redirect loop
- **Solution**: Check that `CAS_SERVER_URL` is correct
- Verify your service URL matches what's registered with Rice

### Issue: User not created
- **Solution**: Ensure `CAS_CREATE_USER = True` in settings
- Check Django logs for errors

### Issue: Email not populated
- **Solution**: Verify `CAS_EMAIL_ATTRIBUTE = 'mail'` is correct
- Check if Rice CAS provides email in attributes

## Testing Checklist

- [ ] django-cas-ng installed
- [ ] Settings updated with CAS configuration
- [ ] URLs configured for CAS login/logout
- [ ] Middleware added
- [ ] Migrations run
- [ ] Rice IT approval obtained
- [ ] Service URL registered
- [ ] Test login with Rice credentials
- [ ] User created successfully
- [ ] UserProfile created automatically
- [ ] Email populated from CAS attributes
- [ ] Logout works correctly

## Next Steps After Setup

1. **Add authorization control** (optional):
   - Restrict access to specific users
   - Use custom authentication backend
   - Add user whitelist

2. **Customize login flow**:
   - Add custom CAS login view
   - Handle post-login redirects
   - Add welcome messages

3. **Monitor authentication**:
   - Log authentication attempts
   - Track user creation
   - Monitor for errors

## Support

If you encounter issues:
1. Check Django logs for detailed error messages
2. Verify all settings match this guide
3. Contact Rice IT if CAS authentication fails
4. Check django-cas-ng documentation: https://django-cas-ng.readthedocs.io/

