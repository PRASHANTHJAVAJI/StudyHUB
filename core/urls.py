from django.urls import path, include
from .views import home, create_group, group_details, join_session, leave_session, signup, profile, change_password, logout_view, landing, edit_session, delete_session, session_ics, join_waitlist, custom_login, mark_attendance

# REST Framework router - conditional in case rest_framework is not installed
try:
    from rest_framework.routers import DefaultRouter
    from .views import StudySessionViewSet, SubjectTagViewSet
    router = DefaultRouter()
    router.register(r'sessions', StudySessionViewSet)
    router.register(r'tags', SubjectTagViewSet)
    REST_FRAMEWORK_AVAILABLE = True
except (ImportError, TypeError):
    REST_FRAMEWORK_AVAILABLE = False
    router = None

# Define the app namespace
app_name = 'core'

urlpatterns = [
    path('', landing, name='landing'),
    path('feed/', home, name='home'),
    path('login/', custom_login, name='login'),
    path('signup/', signup, name='signup'),
    path('profile/', profile, name='profile'),
    path('change-password/', change_password, name='change_password'),
    path('logout/', logout_view, name='logout'),
    path('create/', create_group, name='create'),
    path('session/<int:pk>/', group_details, name='detail'),
    path('session/<int:pk>/edit/', edit_session, name='edit'),
    path('session/<int:pk>/delete/', delete_session, name='delete'),
    path('session/<int:pk>/join/', join_session, name='join'),
    path('session/<int:pk>/leave/', leave_session, name='leave'),
    path('session/<int:pk>/waitlist/', join_waitlist, name='waitlist'),
    path('session/<int:pk>/calendar/', session_ics, name='calendar'),  # ICS download
    path('session/<int:pk>/attendance/', mark_attendance, name='attendance'),  # Mark attendance
]

# Add API endpoints if REST framework is available
if REST_FRAMEWORK_AVAILABLE and router:
    urlpatterns.append(path('api/', include(router.urls)))  # API endpoints

