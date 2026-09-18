from rest_framework.views import APIView
from main.drive_api import DriveService
from rest_framework.response import  Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from library.models import Resource, Course
from library.serializers import  (CourseSerializer, ResourceSerializer)
from library.paginators import CustomPagination
from rest_framework import status

class CourseViewset(ReadOnlyModelViewSet):
    """
    GET:
    Returns courses data.
    filters => level, unit.

    GET <search>:
    search by course title or course code
    filters => title, code

    authenticattion:
    - JWT required

    POST: NOT ALLOWED
    DELETE: NOT ALLOWED

    reponses:
    200: course data
    401: unauthorized
    400: bad request (e.g empty search query)
    """ 
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    pagination_class = CustomPagination
    #permission_classes = [IsAuthenticated,]

    def retrieve(self,request,*args,**kwargs):
            pk = kwargs.get('pk')
            try:
                res = self.queryset.get(id=pk)
                serializer = CourseSerializer(res)
                return Response({
                    'status':'success',
                    'data': serializer.data
                }, status=status.HTTP_200_OK)
            except Course.DoesNotExist:
                return Response({
                    'status':'error',
                    'message':'Course not found'
                }, status=status.HTTP_404_NOT_FOUND)
    
        
    @action(detail=False,methods=['GET'])
    def search(self,request):
        title = request.query_params.get('title')
        code = request.query_params.get('code')
        level = request.query_params.get('level')
        query = {}
        if title:
            query['title__icontains'] = title
        if code:
            query['code__icontains'] = code
        if level:
            query['level__icontains'] = level

        if len(query) == 0:
            # returns 404 if query is empty
            return Response({'error':'Empty search query'},status=400)

        queryset = Course.objects.filter(**query)
        serializer = CourseSerializer(queryset,many=True)
        return Response({
            'status':'success',
            'data':serializer.data
            })

    @action(detail=False,methods=['GET'])
    def retrieve_all(self,request):
        queryset = Course.objects.all()
        serializer = CourseSerializer(queryset,many=True)
        return Response({
            'status':'success',
            'total':queryset.count(),
            'data':serializer.data
            })
        

class ResourceViewset(ReadOnlyModelViewSet):
    """
    GET:
    Returns resource data.
    filters => level, unit.

    GET <search>:
    Returns data from a search query
    filters => title, mime_type

    authenticattion:
    - JWT required

    POST: NOT ALLOWED

    reponses:
    200: resource data
    401: unauthorized
    400: bad request (e.g empty search query)
    error response:
    {"status": "error","message":<message>}
    """
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    pagination_class = CustomPagination
    #permission_classes = [IsAuthenticated,]

    def retrieve(self,request,*args,**kwargs):
        pk = kwargs.get('pk')
        try:
            res = self.queryset.get(id=pk)
            serializer = ResourceSerializer(res)
            return Response({
                'status':'success',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        except Resource.DoesNotExist:
            return Response({
                'status':'error',
                'message':'Resource not found'
            }, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False)
    def search(self,request):
        name = request.query_params.get('name')
        mime_type = request.query_params.get('mime_type')

        query = {}
        if name:
            query['name__icontains'] = name
        if mime_type:
            query['mime_type__icontains'] = mime_type

        if len(query) == 0:
            # returns 404 if query is empty
            return Response({
                'status': 'error',
                'message':'Missing or empty search query'
                },status=400)

        queryset = Resource.objects.filter(**query)
        paginated_queryset = self.paginate_queryset(queryset)
        serializer = ResourceSerializer(queryset,many=True)

        return self.get_paginated_response(serializer.data)
    