from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

app_name = 'accounts'

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view()),
    path('auth/token/refresh/', TokenRefreshView.as_view()),
    path('provision/', views.ProvisionAccountView.as_view(), name='provision'),
    path('activate/', views.ActivateAccountView.as_view(), name='activate'),
    path('student/register/',views.RegisterView.as_view()),
    path('student/register/<str:freshman>/',views.FreshmanRegisterView.as_view()),
    path('student/manage-profile/',views.ManageStudentProfileViewset.as_view({'get':'current'})),
    path('student/manage-profile/avatar/',views.AvatarUploadView.as_view())
        ]
router = DefaultRouter()
router.register(r'student/manage-profile',views.ManageStudentProfileViewset,basename='manage-profile')

urlpatterns += router.urls
