from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'limit' # Allows client to set size: ?limit=50
    max_page_size = 50

    def get_paginated_response(self, data):
        return Response({
            'status': 'success',
            'page': self.page.number,
            'limit': self.page.paginator.per_page,
            'total': self.page.paginator.count,
            'data': data
        })
        