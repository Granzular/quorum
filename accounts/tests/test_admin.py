from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser as User, Profile
from accounts.tests.test_api import PASSWORD, grant, profile_payload


class ProfileAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("profile_admin", password=PASSWORD, is_staff=True)
        grant(cls.admin, "change_profile", "view_profile", "add_profile")
        cls.member = User.objects.create_user("member", password=PASSWORD)
        cls.profile = Profile.objects.create(user=cls.member, **profile_payload("student"))

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("admin:accounts_profile_change", args=[self.profile.pk])

    def profile_form(self, **overrides):
        return {
            "user": self.member.pk, "profile_type": "student", "matric_no": "CSC/24/1234",
            "level": 200, "graduation_year": "", "job_title": "",
            "dept": "Computer Science", "bio": "", "linkedin_url": "", "_save": "Save",
            **overrides,
        }

    def test_administrator_can_update_student_level(self):
        response = self.client.post(self.url, self.profile_form(level=300))
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.level, 300)

    def test_staff_flag_without_permission_is_insufficient(self):
        admin = User.objects.create_user("unprivileged_admin", is_staff=True)
        self.client.force_login(admin)
        self.assertEqual(self.client.post(self.url, self.profile_form(level=300)).status_code, 403)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.level, 200)

    def test_non_admin_cannot_use_admin_site(self):
        self.client.force_login(self.member)
        response = self.client.post(self.url, self.profile_form(level=300))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_admin_category_change_requires_explicitly_clearing_old_fields(self):
        response = self.client.post(
            self.url, self.profile_form(profile_type="alumni", graduation_year=2024)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("level", response.context["adminform"].form.errors)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, "student")
        response = self.client.post(
            self.url, self.profile_form(profile_type="alumni", graduation_year=2024, level="")
        )
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, "alumni")
        self.assertEqual(self.profile.graduation_year, 2024)
        self.assertIsNone(self.profile.level)
        self.assertEqual(self.profile.matric_no, "CSC/24/1234")

    def test_admin_can_complete_legacy_profile_without_changing_memberships(self):
        Profile.objects.filter(pk=self.profile.pk).update(profile_type=None, level=None)
        group = Group.objects.create(name="Existing members")
        self.member.groups.add(group)
        response = self.client.post(self.url, self.profile_form(level=400))
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, "student")
        self.assertEqual(self.profile.level, 400)
        self.assertEqual(list(self.member.groups.values_list("pk", flat=True)), [group.pk])

    def test_admin_form_enforces_required_category_fields(self):
        for category, overrides, missing in (
            ("student", {"level": ""}, "level"),
            ("alumni", {"level": "", "graduation_year": ""}, "graduation_year"),
            ("staff", {"matric_no": "", "level": "", "job_title": ""}, "job_title"),
        ):
            with self.subTest(category=category):
                response = self.client.post(
                    self.url, self.profile_form(profile_type=category, **overrides)
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(missing, response.context["adminform"].form.errors)

    def test_admin_staff_conversion_stores_null_matriculation(self):
        response = self.client.post(
            self.url, self.profile_form(
                profile_type="staff", matric_no="", level="", job_title="Lecturer"
            )
        )
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, "staff")
        self.assertIsNone(self.profile.matric_no)
        self.assertIsNone(self.profile.level)


class AccountProvisioningAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("superuser", password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("admin:accounts_customuser_add")

    def account_form(self, **overrides):
        return {
            "username": "provisioned", "email": "", "first_name": "", "last_name": "",
            "phone": "",
            "profile-TOTAL_FORMS": "1", "profile-INITIAL_FORMS": "0",
            "profile-MIN_NUM_FORMS": "1", "profile-MAX_NUM_FORMS": "1",
            "profile-0-profile_type": "student", "profile-0-matric_no": "CSC/25/0123",
            "profile-0-level": "100", "profile-0-graduation_year": "",
            "profile-0-job_title": "", "profile-0-dept": "Computer Science",
            "profile-0-bio": "", "profile-0-linkedin_url": "", "_save": "Save",
            **overrides,
        }

    def test_admin_creation_provisions_inactive_account_and_profile(self):
        response = self.client.post(self.url, self.account_form())
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="provisioned")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.groups.exists())
        self.assertEqual(user.profile.level, 100)
        messages = [str(message) for message in response.wsgi_request._messages]
        self.assertTrue(any("activation uid" in message for message in messages))

    def test_admin_creation_requires_valid_profile_before_persisting(self):
        response = self.client.post(self.url, self.account_form(**{"profile-0-level": ""}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="provisioned").exists())
        formset = response.context["inline_admin_formsets"][0].formset
        self.assertIn("level", formset.errors[0])

    def test_admin_cannot_omit_profile_form(self):
        response = self.client.post(self.url, self.account_form(**{"profile-TOTAL_FORMS": "0"}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="provisioned").exists())

    def test_admin_provisioning_requires_profile_add_permission(self):
        administrator = User.objects.create_user("account_only_admin", is_staff=True)
        grant(administrator, "add_customuser", "change_customuser")
        self.client.force_login(administrator)
        self.assertEqual(self.client.post(self.url, self.account_form()).status_code, 403)

    def test_administrator_can_reissue_activation_for_pending_accounts(self):
        self.client.post(self.url, self.account_form())
        pending = User.objects.get(username="provisioned")
        response = self.client.post(
            reverse("admin:accounts_customuser_changelist"),
            {"action": "issue_activation_credentials", "_selected_action": [pending.pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(any(
            "activation uid" in str(message) for message in response.wsgi_request._messages
        ))
        pending.refresh_from_db()
        self.assertFalse(pending.is_active)

    def test_read_only_user_admin_cannot_issue_activation_credentials(self):
        pending = User.objects.create_user("pending_member", password=None, is_active=False)
        Profile.objects.create(user=pending, **profile_payload("staff"))
        viewer = User.objects.create_user("account_viewer", is_staff=True)
        grant(viewer, "view_customuser")
        self.client.force_login(viewer)
        response = self.client.post(
            reverse("admin:accounts_customuser_changelist"),
            {"action": "issue_activation_credentials", "_selected_action": [pending.pk]},
        )
        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(any(
            "activation uid" in str(message) for message in response.wsgi_request._messages
        ))
