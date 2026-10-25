from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter

app_name = 'accounts'

urlpatterns = [
    path('auth/token/', views.LoginView.as_view(), name='token-obtain'),
    path('auth/token/refresh/', views.RefreshAccessTokenView.as_view(), name='token-refresh'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
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
