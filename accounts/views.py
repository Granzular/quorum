from rest_framework import status
from rest_framework import generics, mixins, viewsets
from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from accounts.serializers import RegisterSerializer, ManageProfileSerializer, ProfileSerializer
from accounts.models import CustomUser as User, Profile


class RegisterView(generics.CreateAPIView):
    """
    POST:
    fields: username, matric_no, password
    endpoint: api/v0/accounts/student/register/

    GET: Method not allowed
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,) # Anyone can sign up


class ManageStudentProfileViewset(mixins.UpdateModelMixin,viewsets.GenericViewSet):
   
    queryset = User.objects.only('username','email','first_name','last_name','phone')
    serializer_class = ManageProfileSerializer
    http_method_names = ['get','patch','head','options']
    permission_classes = [IsAuthenticated]

    @action(methods=['get'],detail=True)
    def current(self,request,*args,**kwargs):
        user = request.user
        profile = user.profile
        serializer = ManageProfileSerializer(user)
        return Response({
            'status' : 'success',
            'data': serializer.data
        })


class AvatarUploadView(APIView):

    """
    Handles user profile image upload.

    This endpoint accepts file uploads via multipart/form-data and stores
    the uploaded image in the configured media storage (e.g., MEDIA_ROOT
    or external storage like S3 depending on deployment).

    Request format:
        - Content-Type: multipart/form-data
        - Body:
            file: image file (required)

    Example request:
        POST /api/accounts/student/manage-profile/1/
        Content-Type: multipart/form-data

        file: <binary image file>

    Response format:
        The API always responds with JSON.

    Example response:
        {
            "status": "success",
            "message": "Avatar uploaded successfully",
            "avatar_url": "/media/avatars/user_1.png"
        }

    Notes:
        - Only authenticated users can access this endpoint.
        - Existing avatars may be overwritten depending on implementation.
        - Supported formats depend on Django/Pillow configuration.
"""

    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        profile = request.user.profile
        avatar = profile.avatar
        avatar = avatar.url if avatar else None

        return Response({
            'status' : 'success',
            'data': {'avatar':avatar}
        })

    def put(self, request):
        profile = request.user.profile
        serializer = ProfileSerializer(profile, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': 'success',
                'data': serializer.data,
            })

        return Response(serializer.errors, status=400)

    