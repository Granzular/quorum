from django.shortcuts import render
from django.views import View
from main.drive_api import start_resource_indexing
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required


class Index(View):
    def get(self,request):
        
        """
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
        """ 
        return JsonResponse(data={'data':'You are on the backend of the application. Please use the frontend to access the application.'})


# SYNC
@login_required
def sync(request):

    if request.method == 'GET' and request.user.is_superuser:
        start_resource_indexing()
        return JsonResponse(data={'msg':'ok'})
