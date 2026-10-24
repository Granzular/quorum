from collections.abc import Mapping
from copy import copy

from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from accounts.models import CustomUser as User, Profile


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            "profile_type", "matric_no", "level", "graduation_year", "job_title",
            "dept", "avatar", "bio", "linkedin_url",
        ]
        extra_kwargs = {"profile_type": {"required": True, "allow_null": False}}

    def validate(self, attrs):
        """Validate supplied fields and the complete state of a partial update."""
        candidate = copy(self.instance) if self.instance is not None else Profile()
        for field, value in attrs.items():
            setattr(candidate, field, value)

        errors = {}
        applicable = Profile.TYPE_FIELDS.get(candidate.profile_type)
        if applicable is not None:
            for field in Profile.CATEGORY_FIELDS:
                if field in attrs and field not in applicable:
                    errors[field] = [
                        f"This field is not applicable to {candidate.profile_type} profiles."
                    ]

        if self.instance is not None:
            if candidate.profile_type != self.instance.profile_type:
                errors["profile_type"] = ["Change the profile category in Django admin."]
            if "level" in attrs and candidate.level != self.instance.level:
                request = self.context.get("request")
                if request is None or not request.user.has_perm("accounts.change_profile"):
                    errors.setdefault(
                        "level", ["Only a profile administrator may change this field."]
                    )

        try:
            # Provisioning assigns the user; DRF checks uniqueness against the
            # bound profile so an unchanged matriculation number remains valid.
            candidate.full_clean(exclude=["user"], validate_unique=False)
        except DjangoValidationError as exc:
            for field, messages in exc.message_dict.items():
                errors.setdefault(field, messages)
        if errors:
            raise serializers.ValidationError(errors)
        if "matric_no" in attrs:
            attrs["matric_no"] = candidate.matric_no
        return attrs


class ProfileUpdateSerializer(ProfileSerializer):
    class Meta(ProfileSerializer.Meta):
        extra_kwargs = {"profile_type": {"required": False, "allow_null": False}}


class ProfileReadSerializer(ProfileSerializer):
    profile_type = serializers.ChoiceField(
        choices=Profile.Type.choices, allow_null=True, read_only=True
    )

    class Meta(ProfileSerializer.Meta):
        read_only_fields = ProfileSerializer.Meta.fields


class ProvisionAccountSerializer(serializers.ModelSerializer):
    """Keep flat account/profile input while sharing the profile's field rules."""

    class Meta:
        model = User
        fields = ["username"]

    def get_fields(self):
        fields = super().get_fields()
        for name, field in ProfileSerializer().get_fields().items():
            field.write_only = True
            fields[name] = field
        return fields

    def to_internal_value(self, data):
        if isinstance(data, Mapping) and "password" in data:
            raise serializers.ValidationError({
                "password": ["The user sets their password during activation."]
            })
        return super().to_internal_value(data)

    def validate(self, attrs):
        profile_data = {
            name: attrs.pop(name) for name in ProfileSerializer.Meta.fields if name in attrs
        }
        attrs["profile"] = ProfileSerializer(context=self.context).validate(profile_data)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        profile_data = validated_data.pop("profile")
        user = User.objects.create_user(**validated_data, password=None, is_active=False)
        Profile.objects.create(user=user, **profile_data)
        return user


class ActivateAccountSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    invalid_token_message = "This activation token is invalid or has expired."

    def validate(self, attrs):
        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id)
        except (ValueError, TypeError, OverflowError, DjangoValidationError, User.DoesNotExist):
            raise serializers.ValidationError({"token": [self.invalid_token_message]})
        if (
            user.is_active or user.has_usable_password()
            or not default_token_generator.check_token(user, attrs["token"])
        ):
            raise serializers.ValidationError({"token": [self.invalid_token_message]})
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages})
        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        user = validated_data["user"]
        original_password = user.password
        user.set_password(validated_data["password"])
        # Compare all token inputs when consuming it, so concurrent activation
        # requests cannot both succeed on SQLite or PostgreSQL.
        updated = User.objects.filter(
            pk=user.pk, is_active=False, password=original_password,
            last_login=user.last_login, email=user.email,
        ).update(password=user.password, is_active=True)
        if not updated:
            raise serializers.ValidationError({"token": [self.invalid_token_message]})
        user.is_active = True
        return user


class ManageProfileSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "phone", "profile"]
        extra_kwargs = {"email": {"read_only": True}, "phone": {"read_only": True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields["profile"].instance = getattr(self.instance, "profile", None)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            misplaced = {
                field: ["Submit this field inside the profile object."]
                for field in ProfileSerializer.Meta.fields if field in data
            }
            if misplaced:
                raise serializers.ValidationError(misplaced)
        return super().to_internal_value(data)

    def validate(self, attrs):
        request = self.context.get("request")
        if self.instance and request and self.instance.pk != request.user.pk:
            if not request.user.has_perm("accounts.change_customuser"):
                errors = {
                    field: ["You need permission to change another user's account fields."]
                    for field in attrs if field != "profile"
                }
                if errors:
                    raise serializers.ValidationError(errors)
        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        if profile_data is not None:
            self.fields["profile"].update(instance.profile, profile_data)
        return super().update(instance, validated_data)


class ManageProfileReadSerializer(ManageProfileSerializer):
    profile = ProfileReadSerializer(read_only=True)


class ActivationCredentialsSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class ProvisionAccountResponseSerializer(serializers.Serializer):
    username = serializers.CharField()
    activation = ActivationCredentialsSerializer()


class SuccessSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["success"])


class CurrentProfileResponseSerializer(SuccessSerializer):
    data = ManageProfileReadSerializer()


class AvatarDataSerializer(serializers.Serializer):
    avatar = serializers.CharField(allow_null=True)


class AvatarResponseSerializer(SuccessSerializer):
    data = AvatarDataSerializer()


class ProfileResponseSerializer(SuccessSerializer):
    data = ProfileReadSerializer()
