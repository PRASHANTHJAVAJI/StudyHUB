from django.urls import path, include
from .views import home, create_group, group_details, join_session, leave_session, signup, profile, change_password, logout_view, landing, edit_session, delete_session, session_ics, join_waitlist, custom_login, mark_attendance, CASLoginViewCustom, cas_signup
from rest_framework.routers import DefaultRouter
from .views import StudySessionViewSet, SubjectTagViewSet

# Define the app namespace
app_name = 'core'

router = DefaultRouter()
router.register(r'sessions', StudySessionViewSet)
router.register(r'tags', SubjectTagViewSet)

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
    path('api/', include(router.urls)),  # API endpoints
]

