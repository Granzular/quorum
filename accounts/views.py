from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.activation import activation_credentials
from accounts.models import CustomUser as User, Profile
from accounts.permissions import CanProvisionAccount
from accounts.serializers import (
    ActivateAccountSerializer,
    AvatarResponseSerializer,
    CurrentProfileResponseSerializer,
    LogoutSerializer,
    ManageProfileReadSerializer,
    ManageProfileSerializer,
    ProfileResponseSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
    ProvisionAccountResponseSerializer,
    ProvisionAccountSerializer,
    RevokingTokenRefreshSerializer,
    SuccessSerializer,
)


FIELD_ERRORS = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Field-keyed validation errors; profile update errors are nested under profile.",
)
UNAUTHENTICATED = OpenApiResponse(description="A valid JWT is required.")
FORBIDDEN = OpenApiResponse(description="The account lacks the required Django permissions.")
THROTTLED = OpenApiResponse(description="The authentication rate limit was exceeded.")
TOKEN_REJECTED = OpenApiResponse(
    description="The credentials or token were invalid, expired, or revoked."
)


@extend_schema(
    request=TokenObtainPairSerializer,
    responses={200: TokenObtainPairSerializer, 401: TOKEN_REJECTED, 429: THROTTLED},
    tags=["Authentication"],
)
class LoginView(TokenObtainPairView):
    """Issue an access/refresh token pair for an active account."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"


@extend_schema(
    request=RevokingTokenRefreshSerializer,
    responses={
        200: RevokingTokenRefreshSerializer, 401: TOKEN_REJECTED, 429: THROTTLED,
    },
    tags=["Authentication"],
)
class RefreshAccessTokenView(TokenRefreshView):
    """Rotate a valid refresh token and issue a new access token."""

    serializer_class = RevokingTokenRefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_refresh"


@extend_schema(
    responses={
        201: ProvisionAccountResponseSerializer, 400: FIELD_ERRORS,
        401: UNAUTHENTICATED, 403: FORBIDDEN,
    },
    tags=["Accounts"],
)
class ProvisionAccountView(generics.CreateAPIView):
    """Provision an inactive account and return activation credentials for private sharing.

    Requires accounts.add_customuser and accounts.add_profile. Supply profile_type
    and its category fields using the existing flat input format. A student needs
    matric_no and level; alumni need matric_no and graduation_year; staff need
    job_title. Every inapplicable field is rejected, including empty or null values.
    The user chooses a password during activation. Groups and permissions are
    managed separately in Django admin.
    """

    serializer_class = ProvisionAccountSerializer
    permission_classes = [IsAuthenticated, CanProvisionAccount]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"username": user.username, "activation": activation_credentials(user)},
            status=status.HTTP_201_CREATED,
            headers={"Cache-Control": "no-store"},
        )


@extend_schema(deprecated=True)
class RegisterView(ProvisionAccountView):
    """Legacy provisioning alias with the same administrative permissions.

    Public registration is disabled. Use /api/accounts/provision/.
    """


class FreshmanRegisterView(RegisterView):
    """Retain the legacy freshman URL as an administrative provisioning alias."""

    @extend_schema(operation_id="accounts_student_register_freshman_create")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


@extend_schema(
    responses={200: SuccessSerializer, 400: FIELD_ERRORS, 429: THROTTLED},
    tags=["Accounts"],
)
class ActivateAccountView(generics.GenericAPIView):
    """Activate a provisioned account using uid, token, and a new password.

    Tokens expire according to PASSWORD_RESET_TIMEOUT and are consumed when
    activation sets the password. Django password validators apply. A successful
    activation enables the existing JWT login flow and does not change groups,
    permissions, or profile fields.
    """

    serializer_class = ActivateAccountSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_activation"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "success"}, headers={"Cache-Control": "no-store"})


@extend_schema(
    request=LogoutSerializer,
    responses={
        204: OpenApiResponse(description="The supplied refresh token was blacklisted."),
        400: FIELD_ERRORS,
        401: UNAUTHENTICATED,
        429: THROTTLED,
    },
    tags=["Authentication"],
)
class LogoutView(generics.GenericAPIView):
    """Blacklist the authenticated account's refresh token.

    The access token used for this request remains valid until its normal expiry.
    """

    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_logout"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    partial_update=extend_schema(
        responses={
            200: ManageProfileReadSerializer, 400: FIELD_ERRORS,
            401: UNAUTHENTICATED,
            404: OpenApiResponse(description="The profile is missing or outside the caller's access."),
        },
        tags=["Profiles"],
    ),
    current=extend_schema(
        responses={
            200: CurrentProfileResponseSerializer, 401: UNAUTHENTICATED,
            404: OpenApiResponse(description="The current account has no profile."),
        },
        tags=["Profiles"],
    ),
)
class ManageStudentProfileViewset(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Read the current profile or partially update an account's nested profile.

    The legacy student path supports all three categories. Ordinary users may
    update their own account and common/profile fields, except level and category.
    accounts.change_profile permits editing other profiles and changing levels.
    Editing another account's username or names also requires
    accounts.change_customuser. Category changes use Django admin. Inapplicable
    fields are rejected even when explicitly empty.
    """

    queryset = User.objects.select_related("profile").filter(profile__isnull=False)
    serializer_class = ManageProfileSerializer
    http_method_names = ["get", "patch", "head", "options"]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        if self.request.user.has_perm("accounts.change_profile"):
            return queryset
        return queryset.filter(pk=self.request.user.pk)

    @action(methods=["get"], detail=True)
    def current(self, request, *args, **kwargs):
        """Return the authenticated account, regardless of any legacy URL id."""
        user = get_object_or_404(self.get_queryset(), pk=request.user.pk)
        return Response({
            "status": "success",
            "data": ManageProfileSerializer(user).data,
        })


class AvatarUploadView(APIView):
    """Read or update the current account's profile through the avatar endpoint.

    PUT accepts multipart/form-data or form data with the avatar field. Existing
    profile fields remain accepted and follow the same category and administrative
    level restrictions as nested profile updates. Missing fields are unchanged.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: AvatarResponseSerializer, 401: UNAUTHENTICATED,
            404: OpenApiResponse(description="The current account has no profile."),
        },
        tags=["Profiles"],
    )
    def get(self, request):
        profile = get_object_or_404(Profile, user=request.user)
        return Response({
            "status": "success",
            "data": {"avatar": profile.avatar.url if profile.avatar else None},
        })

    @extend_schema(
        request=ProfileUpdateSerializer,
        responses={
            200: ProfileResponseSerializer, 400: FIELD_ERRORS, 401: UNAUTHENTICATED,
            404: OpenApiResponse(description="The current account has no profile."),
        },
        description=(
            "Partially update the current profile using form data. Every field is "
            "optional in this PUT request. An uploaded image uses the avatar field; "
            "category validation applies to any other supplied profile fields. "
            "Level changes require accounts.change_profile; category changes use Django admin."
        ),
        tags=["Profiles"],
    )
    def put(self, request):
        profile = get_object_or_404(Profile, user=request.user)
        serializer = ProfileUpdateSerializer(
            profile, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "success", "data": ProfileSerializer(profile).data})
