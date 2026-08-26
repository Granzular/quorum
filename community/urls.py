from django.urls import path
from rest_framework.routers import DefaultRouter
from community import views

app_name = 'community'

router = DefaultRouter()
router.register(r'blog/posts',views.PostViewSet)
urlpatterns = router.urls