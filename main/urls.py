from django.urls import path
from main import views

app_name = 'main'

 
urlpatterns = [
    path('',view=views.Index.as_view()),
    path('library/',views.library_view,name='library'),
    path('library/course/',view=views.course_index,name='course_index'),
    path('library/course/<int:pk>/detail/',view=views.course_detail,name='course_detail'),
    path('library/cbt/',views.cbt_index_view,name='cbt_index'),
    path('library/cbt/<int:pk>/',views.cbt_detail_view,name='cbt_view'),
    path('sync/',view=views.sync),
]