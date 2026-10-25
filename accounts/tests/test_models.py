from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import CustomUser as User, Profile
from accounts.tests.test_api import profile_payload


class ProfileModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("model_user")

    def test_all_categories_validate_and_default_department_is_preserved(self):
        for category in ("student", "alumni", "staff"):
            profile = Profile(user=self.user, **profile_payload(category))
            profile.full_clean()
            self.assertEqual(profile.dept, "Computer Science")

    def test_category_requirements_are_enforced_by_model_validation(self):
        for category, field in (
            ("student", "level"), ("alumni", "graduation_year"), ("staff", "job_title")
        ):
            data = profile_payload(category)
            data.pop(field)
            with self.subTest(category=category), self.assertRaises(ValidationError) as caught:
                Profile(user=self.user, **data).full_clean()
            self.assertIn(field, caught.exception.message_dict)

    def test_model_rejects_nonempty_inapplicable_data(self):
        with self.assertRaises(ValidationError) as caught:
            Profile(user=self.user, **profile_payload("staff"), level=200).full_clean()
        self.assertIn("level", caught.exception.message_dict)

    def test_new_profile_requires_type(self):
        with self.assertRaises(ValidationError) as caught:
            Profile(user=self.user, matric_no="CSC/24/1234").full_clean()
        self.assertIn("profile_type", caught.exception.message_dict)

    def test_database_rejects_null_profile_type(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Profile.objects.create(
                user=self.user, profile_type=None, matric_no="CSC/24/1234", level=300
            )

    def test_matriculation_validator_requires_complete_string(self):
        with self.assertRaises(ValidationError) as caught:
            Profile(
                user=self.user, **{**profile_payload("student"), "matric_no": "CSC/24/1234\n"}
            ).full_clean()
        self.assertIn("matric_no", caught.exception.message_dict)

    def test_database_retains_matriculation_uniqueness_and_one_to_one_relationship(self):
        Profile.objects.create(user=self.user, **profile_payload("student"))
        other = User.objects.create_user("duplicate")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Profile.objects.create(user=other, **profile_payload("student"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Profile.objects.create(user=self.user, **profile_payload("staff"))

    def test_blank_staff_matriculation_is_normalized_to_null(self):
        profile = Profile(user=self.user, **profile_payload("staff"), matric_no="")
        profile.full_clean()
        self.assertIsNone(profile.matric_no)

    def test_user_deletion_cascades_to_profile(self):
        profile = Profile.objects.create(user=self.user, **profile_payload("student"))
        profile_id = profile.pk
        self.user.delete()
        self.assertFalse(Profile.objects.filter(pk=profile_id).exists())
