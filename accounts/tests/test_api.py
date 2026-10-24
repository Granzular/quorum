from datetime import datetime, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.tokens import default_token_generator
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import override_settings
from PIL import Image
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounts.activation import activation_credentials
from accounts.models import CustomUser as User, Profile
from accounts.serializers import ActivateAccountSerializer, ProvisionAccountSerializer


PROVISION = "/api/accounts/provision/"
ACTIVATE = "/api/accounts/activate/"
CURRENT = "/api/accounts/student/manage-profile/"
AVATAR = CURRENT + "avatar/"
TOKEN = "/api/accounts/auth/token/"
PASSWORD = "Long-private-phrase-47!"


def profile_payload(category):
    return {
        "student": {"profile_type": "student", "matric_no": "CSC/24/1234", "level": 200},
        "alumni": {
            "profile_type": "alumni", "matric_no": "202412345678AB", "graduation_year": 2024,
        },
        "staff": {"profile_type": "staff", "job_title": "Lecturer"},
    }[category].copy()


def grant(user, *codenames):
    user.user_permissions.add(*Permission.objects.filter(
        content_type__app_label="accounts", codename__in=codenames
    ))


def image_upload():
    stream = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(stream, format="PNG")
    return SimpleUploadedFile("avatar.png", stream.getvalue(), content_type="image/png")


class AccountAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("owner", password=PASSWORD)
        cls.owner_profile = Profile.objects.create(
            user=cls.owner, profile_type="student", matric_no="CSC/20/0001", level=200
        )
        cls.other = User.objects.create_user("other", password=PASSWORD)
        cls.other_profile = Profile.objects.create(
            user=cls.other, profile_type="alumni",
            matric_no="CSC/18/0002", graduation_year=2022,
        )
        cls.administrator = User.objects.create_user("administrator", password=PASSWORD)
        cls.administrators = Group.objects.create(name="Profile administrators")
        cls.administrators.permissions.add(*Permission.objects.filter(
            content_type__app_label="accounts",
            codename__in=("add_customuser", "add_profile", "change_profile"),
        ))
        cls.administrator.groups.add(cls.administrators)

    def setUp(self):
        super().setUp()
        media = TemporaryDirectory(prefix="quorum-profile-tests-")
        self.addCleanup(media.cleanup)
        media_override = override_settings(MEDIA_ROOT=media.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

    def provision(self, category="student", **overrides):
        data = {"username": "new_member", **profile_payload(category), **overrides}
        return self.client.post(PROVISION, data, format="json")

    def update_profile(self, data, user=None):
        user = user or self.owner
        return self.client.patch(CURRENT + f"{user.pk}/", {"profile": data}, format="json")


class ProvisioningTests(AccountAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.administrator)

    def test_valid_creation_for_each_category_is_inactive_and_unprivileged(self):
        for category in ("student", "alumni", "staff"):
            with self.subTest(category=category):
                response = self.provision(category, username=f"new_{category}")
                self.assertEqual(response.status_code, 201, response.data)
                user = User.objects.get(username=f"new_{category}")
                self.assertFalse(user.is_active)
                self.assertFalse(user.has_usable_password())
                self.assertFalse(user.is_staff)
                self.assertFalse(user.is_superuser)
                self.assertFalse(user.groups.exists())
                self.assertFalse(user.user_permissions.exists())
                self.assertEqual(user.profile.profile_type, category)
                user.profile.full_clean()
                self.assertEqual(user.profile.dept, "Computer Science")
                self.assertEqual(set(response.data), {"username", "activation"})
                self.assertTrue(default_token_generator.check_token(
                    user, response.data["activation"]["token"]
                ))
                self.assertEqual(response["Cache-Control"], "no-store")

    def test_public_provisioning_and_legacy_registration_are_denied(self):
        self.client.force_authenticate(None)
        for url in (PROVISION, "/api/accounts/student/register/",
                    "/api/accounts/student/register/freshman/"):
            with self.subTest(url=url):
                response = self.client.post(
                    url, {"username": "outsider", **profile_payload("student")}, format="json"
                )
                self.assertEqual(response.status_code, 401, response.data)
        self.assertFalse(User.objects.filter(username="outsider").exists())

    def test_legacy_registration_aliases_use_admin_provisioning(self):
        for index, url in enumerate((
            "/api/accounts/student/register/", "/api/accounts/student/register/freshman/",
        )):
            response = self.client.post(
                url, {"username": f"legacy_{index}", **profile_payload("staff")}, format="json"
            )
            self.assertEqual(response.status_code, 201, response.data)
            self.assertFalse(User.objects.get(username=f"legacy_{index}").is_active)

    def test_authenticated_user_cannot_provision(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.provision().status_code, 403)

    def test_provisioning_requires_both_model_permissions(self):
        for codename in ("add_customuser", "add_profile"):
            with self.subTest(permission=codename):
                user = User.objects.create_user(codename, is_staff=True)
                grant(user, codename)
                self.client.force_authenticate(user)
                self.assertEqual(self.provision().status_code, 403)
        self.assertFalse(User.objects.filter(username="new_member").exists())

    def test_staff_category_confers_no_provisioning_permission(self):
        user = User.objects.create_user("departmental_staff")
        Profile.objects.create(user=user, **profile_payload("staff"))
        self.client.force_authenticate(user)
        self.assertEqual(self.provision().status_code, 403)

    def test_missing_or_invalid_profile_type(self):
        for value in (None, "", "administrator", ["student"]):
            with self.subTest(value=value):
                response = self.provision(profile_type=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn("profile_type", response.data)
        response = self.client.post(PROVISION, {"username": "missing_type"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("profile_type", response.data)

    def test_required_category_fields_are_checked_before_creating_user(self):
        for category, fields in (
            ("student", ("matric_no", "level")),
            ("alumni", ("matric_no", "graduation_year")),
            ("staff", ("job_title",)),
        ):
            for field in fields:
                for omission in (True, False):
                    with self.subTest(category=category, field=field, omitted=omission):
                        data = {"username": "incomplete", **profile_payload(category)}
                        if omission:
                            data.pop(field)
                        else:
                            data[field] = "" if field in ("matric_no", "job_title") else None
                        response = self.client.post(PROVISION, data, format="json")
                        self.assertEqual(response.status_code, 400, response.data)
                        self.assertIn(field, response.data)
                        self.assertIsInstance(response.data[field], list)
        self.assertFalse(User.objects.filter(username="incomplete").exists())

    def test_inapplicable_fields_are_rejected_even_when_empty(self):
        fields = {
            "student": {"graduation_year": 2024, "job_title": "Tutor"},
            "alumni": {"level": 300, "job_title": "Tutor"},
            "staff": {"matric_no": "CSC/25/4444", "level": 100, "graduation_year": 2024},
        }
        for category, invalid in fields.items():
            for field, value in invalid.items():
                for supplied in (value, None, ""):
                    with self.subTest(category=category, field=field, value=supplied):
                        response = self.provision(category, **{field: supplied})
                        self.assertEqual(response.status_code, 400, response.data)
                        self.assertIn(field, response.data)
        self.assertFalse(User.objects.filter(username="new_member").exists())

    def test_both_existing_matriculation_formats_and_letter_case_work(self):
        for index, matric in enumerate(("CSC/00/0000", "202412345678AB", "202412345678aB")):
            response = self.provision(username=f"format_{index}", matric_no=matric)
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(User.objects.get(username=f"format_{index}").profile.matric_no, matric)

    def test_invalid_matriculation_formats_have_field_errors(self):
        for matric in ("invalid", "CSC/2/1234", "CSC/24/12345", "csc/24/1234",
                       "20241234567AB", "202412345678ABC", "CSC/24/1234x"):
            with self.subTest(matric=matric):
                response = self.provision(matric_no=matric)
                self.assertEqual(response.status_code, 400)
                self.assertIn("matric_no", response.data)

    def test_matriculation_is_unique_across_student_and_alumni(self):
        response = self.provision("alumni", matric_no=self.owner_profile.matric_no)
        self.assertEqual(response.status_code, 400)
        self.assertIn("matric_no", response.data)
        self.assertFalse(User.objects.filter(username="new_member").exists())

    def test_multiple_staff_profiles_store_null_matriculation(self):
        for index in range(2):
            response = self.provision("staff", username=f"staff_{index}")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertIsNone(User.objects.get(username=f"staff_{index}").profile.matric_no)

    def test_optional_common_fields_and_department(self):
        for category in ("student", "alumni", "staff"):
            response = self.provision(
                category, username=f"common_{category}", bio="Research and teaching.",
                linkedin_url="https://www.linkedin.com/in/quorum-member/", dept="Computing",
            )
            self.assertEqual(response.status_code, 201, response.data)
            profile = User.objects.get(username=f"common_{category}").profile
            self.assertEqual(profile.bio, "Research and teaching.")
            self.assertEqual(profile.linkedin_url, "https://www.linkedin.com/in/quorum-member/")
            self.assertEqual(profile.dept, "Computing")

    def test_invalid_field_values(self):
        for category, field, values in (
            ("student", "level", (0, 150, 600, True)),
            ("alumni", "graduation_year", (0, -1, 10000, "last year")),
            ("staff", "job_title", (" " * 3, "x" * 129)),
            ("staff", "linkedin_url", ("not a URL",)),
            ("staff", "dept", ("", "x" * 65)),
        ):
            for value in values:
                with self.subTest(category=category, field=field, value=value):
                    response = self.provision(category, **{field: value})
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertIn(field, response.data)

    def test_provisioning_does_not_accept_password_or_create_active_user(self):
        response = self.provision(password=PASSWORD)
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        self.assertFalse(User.objects.filter(username="new_member").exists())

    def test_profile_failure_rolls_back_new_user(self):
        serializer = ProvisionAccountSerializer(data={
            "username": "rollback", **profile_payload("student"),
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch("accounts.serializers.Profile.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                serializer.save()
        self.assertFalse(User.objects.filter(username="rollback").exists())

    def test_duplicate_username_does_not_create_a_profile(self):
        count = Profile.objects.count()
        response = self.provision(username=self.owner.username)
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)
        self.assertEqual(Profile.objects.count(), count)

    def test_avatar_can_be_uploaded_during_provisioning(self):
        response = self.client.post(
            PROVISION,
            {"username": "with_avatar", **profile_payload("staff"), "avatar": image_upload()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(User.objects.get(username="with_avatar").profile.avatar.name.startswith("accounts/"))


class ProfileUpdateTests(AccountAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.owner)

    def test_current_profile_keeps_existing_envelope_and_user_fields(self):
        response = self.client.get(CURRENT)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(
            set(response.data["data"]),
            {"username", "email", "first_name", "last_name", "phone", "profile"},
        )
        self.assertEqual(response.data["data"]["profile"]["matric_no"], "CSC/20/0001")
        self.assertEqual(response.data["data"]["profile"]["profile_type"], "student")

    def test_valid_partial_update_preserves_unsupplied_fields_and_other_profiles(self):
        response = self.update_profile({"bio": "A new biography."})
        self.assertEqual(response.status_code, 200, response.data)
        self.owner_profile.refresh_from_db()
        self.other_profile.refresh_from_db()
        self.assertEqual(self.owner_profile.bio, "A new biography.")
        self.assertEqual(self.owner_profile.matric_no, "CSC/20/0001")
        self.assertEqual(self.owner_profile.level, 200)
        self.assertEqual(self.other_profile.user_id, self.other.pk)
        self.assertEqual(self.other_profile.bio, "")
        self.assertEqual(self.other_profile.matric_no, "CSC/18/0002")

    def test_unchanged_unique_value_is_valid_in_nested_update(self):
        response = self.update_profile({"matric_no": self.owner_profile.matric_no})
        self.assertEqual(response.status_code, 200, response.data)

    def test_duplicate_or_invalid_matriculation_update_is_rejected(self):
        for value in (self.other_profile.matric_no, "invalid", "", None):
            response = self.update_profile({"matric_no": value})
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("matric_no", response.data["profile"])
        self.owner_profile.refresh_from_db()
        self.assertEqual(self.owner_profile.matric_no, "CSC/20/0001")

    def test_account_fields_can_be_updated_without_resubmitting_profile(self):
        response = self.client.patch(
            CURRENT + f"{self.owner.pk}/", {"first_name": "Ada"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.first_name, "Ada")

    def test_empty_nested_update_is_valid_for_complete_profile(self):
        self.assertEqual(self.update_profile({}).status_code, 200)

    def test_partial_updates_reject_inapplicable_fields_for_each_category(self):
        staff = User.objects.create_user("staff_owner")
        Profile.objects.create(user=staff, **profile_payload("staff"))
        for user, fields in (
            (self.owner, {"graduation_year": 2024, "job_title": "Tutor"}),
            (self.other, {"level": 300, "job_title": "Tutor"}),
            (staff, {"matric_no": "CSC/25/7777", "level": 300, "graduation_year": 2024}),
        ):
            self.client.force_authenticate(user)
            for field, value in fields.items():
                for supplied in (value, None, ""):
                    with self.subTest(user=user.username, field=field, value=supplied):
                        response = self.update_profile({field: supplied}, user=user)
                        self.assertEqual(response.status_code, 400, response.data)
                        self.assertIn(field, response.data["profile"])

    def test_profile_type_changes_cannot_leave_incompatible_data(self):
        for data in (
            {"profile_type": "alumni", "graduation_year": 2024},
            {"profile_type": "alumni", "graduation_year": 2024, "level": None},
            {"profile_type": "staff", "job_title": "Lecturer", "matric_no": None, "level": None},
        ):
            response = self.update_profile(data)
            self.assertEqual(response.status_code, 400)
            self.assertIn("profile_type", response.data["profile"])
            self.assertIn("level", response.data["profile"])
        self.owner_profile.refresh_from_db()
        self.assertEqual(self.owner_profile.profile_type, "student")
        self.assertEqual(self.owner_profile.level, 200)

    def test_profile_administrators_also_use_admin_for_category_changes(self):
        self.client.force_authenticate(self.administrator)
        response = self.update_profile({"profile_type": "alumni", "graduation_year": 2024})
        self.assertEqual(response.status_code, 400)
        self.assertIn("profile_type", response.data["profile"])

    def test_missing_or_null_profile_type_is_not_accepted_as_a_change(self):
        response = self.update_profile({"profile_type": None})
        self.assertEqual(response.status_code, 400)
        self.assertIn("profile_type", response.data["profile"])

    def test_ordinary_user_cannot_change_level_but_may_resubmit_same_value(self):
        self.assertEqual(self.update_profile({"level": 200}).status_code, 200)
        for value in (300, None):
            response = self.update_profile({"level": value})
            self.assertEqual(response.status_code, 400)
            self.assertIn("level", response.data["profile"])
        self.owner_profile.refresh_from_db()
        self.assertEqual(self.owner_profile.level, 200)

    def test_is_staff_alone_does_not_authorize_level_changes(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.assertEqual(self.update_profile({"level": 300}).status_code, 400)

    def test_group_permission_authorizes_administrative_level_change(self):
        self.client.force_authenticate(self.administrator)
        response = self.update_profile({"level": 300})
        self.assertEqual(response.status_code, 200, response.data)
        self.owner_profile.refresh_from_db()
        self.assertEqual(self.owner_profile.level, 300)
        self.assertFalse(self.administrator.is_staff)

    def test_ordinary_user_cannot_update_another_account(self):
        response = self.update_profile({"bio": "unauthorized"}, user=self.other)
        self.assertEqual(response.status_code, 404)
        self.other_profile.refresh_from_db()
        self.assertEqual(self.other_profile.bio, "")

    def test_profile_permission_does_not_grant_other_account_field_changes(self):
        self.client.force_authenticate(self.administrator)
        response = self.client.patch(
            CURRENT + f"{self.owner.pk}/",
            {"username": "renamed", "profile": {"level": 300}}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)
        self.owner.refresh_from_db()
        self.owner_profile.refresh_from_db()
        self.assertEqual(self.owner.username, "owner")
        self.assertEqual(self.owner_profile.level, 200)

    def test_combined_invalid_update_changes_neither_user_nor_profile(self):
        response = self.client.patch(
            CURRENT + f"{self.owner.pk}/",
            {"first_name": "Changed", "profile": {"job_title": "Invalid"}}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.first_name, "")

    def test_update_preserves_groups_and_permissions(self):
        group = Group.objects.create(name="Community contributors")
        self.owner.groups.add(group)
        grant(self.owner, "view_profile")
        response = self.update_profile({"bio": "Updated"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(self.owner.groups.values_list("pk", flat=True)), [group.pk])
        self.assertEqual(
            list(self.owner.user_permissions.values_list("codename", flat=True)), ["view_profile"]
        )

    def test_misplaced_profile_fields_are_not_silently_ignored(self):
        response = self.client.patch(
            CURRENT + f"{self.owner.pk}/", {"graduation_year": 2024}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("graduation_year", response.data)

    def test_common_optional_fields_can_be_cleared(self):
        response = self.update_profile({"bio": "", "linkedin_url": "", "avatar": None})
        self.assertEqual(response.status_code, 200, response.data)
        response = self.update_profile({"linkedin_url": "invalid"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("linkedin_url", response.data["profile"])

    def test_read_only_contact_fields_keep_existing_behavior(self):
        response = self.client.patch(
            CURRENT + f"{self.owner.pk}/",
            {"email": "ignored@example.com", "phone": "123"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "")
        self.assertIsNone(self.owner.phone)

    def test_profile_routes_require_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(CURRENT).status_code, 401)
        self.assertEqual(self.update_profile({"bio": "unauthorized"}).status_code, 401)
        self.assertEqual(self.client.get(AVATAR).status_code, 401)
        self.assertEqual(self.client.put(AVATAR, {}, format="multipart").status_code, 401)

    def test_missing_profile_returns_404(self):
        user = User.objects.create_user("without_profile")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(CURRENT).status_code, 404)
        self.assertEqual(self.client.get(AVATAR).status_code, 404)
        self.assertEqual(self.update_profile({}, user=user).status_code, 404)

    def test_legacy_profile_requires_administrator_completion(self):
        Profile.objects.filter(pk=self.owner_profile.pk).update(profile_type=None, level=None)
        response = self.update_profile({"bio": "legacy"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("profile_type", response.data["profile"])
        response = self.client.get(CURRENT)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["data"]["profile"]["profile_type"])

    def test_avatar_upload_retains_path_and_response(self):
        response = self.client.put(AVATAR, {"avatar": image_upload()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "success")
        self.assertTrue(response.data["data"]["avatar"].startswith("/media/accounts/"))
        self.assertEqual(
            self.client.get(AVATAR).data["data"]["avatar"], response.data["data"]["avatar"]
        )

    def test_avatar_endpoint_validates_other_profile_fields(self):
        for data, field in (
            ({"graduation_year": 2024}, "graduation_year"),
            ({"job_title": ""}, "job_title"),
            ({"matric_no": "invalid"}, "matric_no"),
            ({"matric_no": self.other_profile.matric_no}, "matric_no"),
            ({"level": 300}, "level"),
            ({"profile_type": "alumni", "graduation_year": 2024}, "profile_type"),
        ):
            response = self.client.put(AVATAR, data, format="multipart")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn(field, response.data)

    def test_avatar_endpoint_checks_all_categories(self):
        staff = User.objects.create_user("avatar_staff")
        Profile.objects.create(user=staff, **profile_payload("staff"))
        for user, fields in (
            (self.other, {"level": 300, "job_title": "Tutor"}),
            (staff, {"matric_no": "CSC/25/7777", "level": 300, "graduation_year": 2024}),
        ):
            self.client.force_authenticate(user)
            for field, value in fields.items():
                response = self.client.put(AVATAR, {field: value}, format="multipart")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

    def test_avatar_endpoint_allows_unchanged_matriculation_and_common_fields(self):
        response = self.client.put(
            AVATAR, {"matric_no": self.owner_profile.matric_no, "bio": "Updated"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_invalid_avatar_does_not_change_profile(self):
        response = self.client.put(
            AVATAR,
            {"avatar": SimpleUploadedFile("fake.png", b"invalid"), "bio": "Changed"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("avatar", response.data)
        self.owner_profile.refresh_from_db()
        self.assertEqual(self.owner_profile.bio, "")


class ActivationTests(AccountAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.administrator)
        response = self.provision()
        self.assertEqual(response.status_code, 201, response.data)
        self.credentials = response.data["activation"]
        self.pending = User.objects.get(username="new_member")
        self.client.force_authenticate(None)

    def activate(self, **overrides):
        return self.client.post(
            ACTIVATE, {**self.credentials, "password": PASSWORD, **overrides}, format="json"
        )

    def test_activation_enables_jwt_login_and_profile_access(self):
        login_data = {"username": "new_member", "password": PASSWORD}
        self.assertEqual(self.client.post(TOKEN, login_data, format="json").status_code, 401)
        response = self.activate()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"status": "success"})
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)
        self.assertTrue(self.pending.check_password(PASSWORD))
        login = self.client.post(TOKEN, login_data, format="json")
        self.assertEqual(login.status_code, 200, login.data)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + login.data["access"])
        self.assertEqual(self.client.get(CURRENT).status_code, 200)

    def test_activation_preserves_groups_and_does_not_accept_profile_or_privileges(self):
        self.pending.groups.add(self.administrators)
        response = self.activate(
            is_staff=True, is_superuser=True, groups=[], profile_type="staff", level=500
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_staff)
        self.assertFalse(self.pending.is_superuser)
        self.assertEqual(self.pending.profile.profile_type, "student")
        self.assertEqual(self.pending.profile.level, 200)
        self.assertEqual(
            list(self.pending.groups.values_list("pk", flat=True)), [self.administrators.pk]
        )

    def test_token_is_single_use(self):
        self.assertEqual(self.activate().status_code, 200)
        response = self.activate(password="Another-private-phrase-67!")
        self.assertEqual(response.status_code, 400)
        self.assertIn("token", response.data)
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.check_password(PASSWORD))

    def test_two_validated_requests_cannot_both_consume_token(self):
        data = {**self.credentials, "password": PASSWORD}
        first = ActivateAccountSerializer(data=data)
        second = ActivateAccountSerializer(data=data)
        self.assertTrue(first.is_valid(), first.errors)
        self.assertTrue(second.is_valid(), second.errors)
        first.save()
        with self.assertRaises(ValidationError):
            second.save()

    def test_invalid_activation_credentials_do_not_enable_account(self):
        for changes in ({"uid": "!"}, {"uid": "OTk5OTk5OQ"}, {"token": "invalid"}):
            response = self.activate(**changes)
            self.assertEqual(response.status_code, 400)
            self.assertIn("token", response.data)
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_active)
        self.assertFalse(self.pending.has_usable_password())

    def test_expired_token_is_rejected(self):
        issued_at = datetime(2026, 1, 1)
        with patch.object(default_token_generator, "_now", return_value=issued_at):
            self.credentials = activation_credentials(self.pending)
        expired_at = issued_at + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1)
        with patch.object(default_token_generator, "_now", return_value=expired_at):
            response = self.activate()
        self.assertEqual(response.status_code, 400)
        self.assertIn("token", response.data)

    def test_weak_password_is_rejected_without_consuming_token(self):
        response = self.activate(password="123")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_active)
        self.assertEqual(self.activate().status_code, 200)

    def test_activation_does_not_reactivate_disabled_existing_users(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        response = self.activate(
            uid=urlsafe_base64_encode(force_bytes(self.owner.pk)),
            token=default_token_generator.make_token(self.owner),
        )
        self.assertEqual(response.status_code, 400)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)

    def test_missing_activation_fields_are_structured_errors(self):
        response = self.client.post(ACTIVATE, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {"uid", "token", "password"})
