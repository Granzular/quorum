from django.shortcuts import render
from django.views import View
from main.drive_api import start_resource_indexing
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from library.models import Course
from community.models import Content
from django.shortcuts import get_object_or_404

class Index(View):
    def get(self,request):
        courses = Course.objects.all()
        posts = Content.objects.all()
        context = {
            'levels': [
                {
                    'name': '100',
                    'first': courses.filter(level='100',semester='first'),
                    'second': courses.filter(level='100',semester='second'),
                },
                {
                    'name':'200',
                    'first': courses.filter(level='200',semester='first'),
                    'second': courses.filter(level='200',semester='second'),
                },
                {
                    'name': '300',
                    'first': courses.filter(level='300',semester='first'),
                    'second': courses.filter(level='300',semester='second'),
                },
                {
                    'name': '400',
                    'first': courses.filter(level='400',semester='first'),
                    'second': courses.filter(level='400',semester='second'),
                },
                {
                    'name': '500',
                    'first': courses.filter(level='500',semester='first'),
                    'second': courses.filter(level='500',semester='second'),
                },
            ],
            'posts': posts
        }
        return render(request,'main/index.html',context=context)

# LIBRARY 
def library_view(request):
    if request.method == 'GET':
        return render(request,'main/library/index.html')

# COURSES
def course_index(request):
    if request.method == 'GET':
        return render(request,'main/library/courses/index.html')


def course_detail(request,pk):
    if request.method == 'GET':
        course = get_object_or_404(Course,id=pk)
        context = {
            'course':course,
        }
        return render(request,'main/course_detail.html',context)

# CBT
def cbt_index_view(request):
    if request.method == 'GET':
        return render(request,'main/library/cbt/index.html')

def cbt_detail_view(request,pk):
    if request.method == 'GET':
        return render(request,'main/library/cbt/detail.html')


# SYNC
@login_required
def sync(request):

    if request.method == 'GET' and request.user.is_superuser:
        start_resource_indexing()
        return JsonResponse(data={'msg':'ok'})
