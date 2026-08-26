from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import status
from community.models import Content
from community.serializers import PostSerializer
from main.paginators import CustomPagination
from django.shortcuts import get_object_or_404
import logging

logger = logging.getLogger(__name__)

class PostViewSet(ModelViewSet):
    queryset = Content.objects.filter(type='post').prefetch_related('replies')
    serializer_class = PostSerializer
    pagination_class = CustomPagination
    permission_classes = []

    @action(methods=['post'],detail=True)
    def create_comment(self,request,*args,**kwargs):
        pk = kwargs.get('pk')
        data = request.data
        parent = get_object_or_404(Content,id=pk)
        data['parent'] = parent.id
        data['type'] = 'comment'
        serializer = PostSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({
            'status':'success',
            'data': serializer.data,
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'status': 'error',
                'message': 'invalid data'
            }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    @action(methods=['get'],detail=True)
    def list_comment(self,request,*args,**kwargs):
        pk = kwargs.get('pk')
        parent = get_object_or_404(Content,id=pk)
        queryset = Content.objects.filter(parent=parent)
        serializer = PostSerializer(self.paginate_queryset(queryset),many=True)

        return self.get_paginated_response(serializer.data)

    @action(methods=['patch'],detail=True)
    def edit_comment(self,request,*args,**kwargs):
        pk = kwargs.get('pk')
        data = request.data
        parent = get_object_or_404(Content,id=pk)
        data['parent'] = parent.id
        data['type'] = 'comment'
        serializer = PostSerializer(data=data,partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
            'status':'success',
            'data': serializer.data,
            })
        else:
            return Response({
                'status': 'error',
                'message': 'invalid data'
            }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    
    @action(methods=['delete'],detail=True)
    def delete_comment(self,request,*args,**kwargs):
        pk = kwargs.get('pk')
        parent = get_object_or_404(Content,id=pk)
