from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.test import APIClient


class ProfileMigrationTests(TransactionTestCase):
    old_target = [("accounts", "0007_alter_profile_user")]
    categories_target = [("accounts", "0008_profile_categories")]
    new_target = [("accounts", "0009_backfill_legacy_profiles")]

    def test_legacy_profiles_receive_defaults_and_remain_usable(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.old_target)
        try:
            old_apps = executor.loader.project_state(self.old_target).apps
            User = old_apps.get_model("accounts", "CustomUser")
            Profile = old_apps.get_model("accounts", "Profile")
            password = "Legacy-private-phrase-47!"
            user = User.objects.create(
                username="legacy_member", password=make_password(password),
                email="legacy@example.com", phone="123456789", is_active=True,
            )
            group = old_apps.get_model("auth", "Group").objects.create(name="Members")
            permission = old_apps.get_model("auth", "Permission").objects.get(
                content_type__app_label="accounts", codename="view_profile"
            )
            user.groups.add(group)
            user.user_permissions.add(permission)
            original_user = User.objects.values().get(pk=user.pk)
            old_profile = Profile.objects.create(
                user=user, matric_no="202412345678AB", dept="Computer Science",
                avatar="accounts/existing.png",
            )
            executor = MigrationExecutor(connection)
            executor.migrate(self.new_target)
            new_apps = executor.loader.project_state(self.new_target).apps
            migrated = new_apps.get_model("accounts", "Profile").objects.get(pk=old_profile.pk)
            self.assertEqual(migrated.user_id, user.pk)
            self.assertEqual(migrated.matric_no, "202412345678AB")
            self.assertEqual(migrated.dept, "Computer Science")
            self.assertEqual(migrated.avatar.name, "accounts/existing.png")
            self.assertEqual(migrated.profile_type, "student")
            self.assertEqual(migrated.level, 300)
            self.assertIsNone(migrated.graduation_year)
            self.assertEqual(migrated.job_title, "")
            self.assertEqual(migrated.bio, "")
            self.assertEqual(migrated.linkedin_url, "")
            self.assertEqual(new_apps.get_model("accounts", "Profile").objects.count(), 1)
            migrated_user = new_apps.get_model("accounts", "CustomUser")
            self.assertEqual(migrated_user.objects.values().get(pk=user.pk), original_user)
            self.assertEqual(list(user.groups.values_list("pk", flat=True)), [group.pk])
            self.assertEqual(
                list(user.user_permissions.values_list("pk", flat=True)), [permission.pk]
            )

            client = APIClient()
            login = client.post(
                "/api/accounts/auth/token/",
                {"username": user.username, "password": password}, format="json",
            )
            self.assertEqual(login.status_code, 200, login.data)
            client.credentials(HTTP_AUTHORIZATION="Bearer " + login.data["access"])
            response = client.patch(
                f"/api/accounts/student/manage-profile/{user.pk}/",
                {"profile": {"bio": "Updated after migration."}}, format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)
            migrated.refresh_from_db()
            self.assertEqual(migrated.bio, "Updated after migration.")
        finally:
            MigrationExecutor(connection).migrate(self.new_target)

    def test_backfill_preserves_classified_profiles_and_recorded_levels(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.categories_target)
        try:
            old_apps = executor.loader.project_state(self.categories_target).apps
            User = old_apps.get_model("accounts", "CustomUser")
            Profile = old_apps.get_model("accounts", "Profile")
            existing_profiles = []
            for username, fields in (
                ("student", {"profile_type": "student", "matric_no": "CSC/24/0001", "level": 100}),
                ("alumni", {"profile_type": "alumni", "matric_no": "CSC/20/0002", "graduation_year": 2024}),
                ("staff", {"profile_type": "staff", "job_title": "Lecturer"}),
            ):
                user = User.objects.create(username=username)
                profile = Profile.objects.create(user=user, **fields)
                existing_profiles.append(Profile.objects.values().get(pk=profile.pk))
            legacy = Profile.objects.create(
                user=User.objects.create(username="partially_completed"),
                matric_no="CSC/22/0003", level=400, dept="Computing",
                bio="Existing biography.", linkedin_url="https://example.com/member",
            )
            original_legacy = Profile.objects.values().get(pk=legacy.pk)

            MigrationExecutor(connection).migrate(self.new_target)

            for original in existing_profiles:
                self.assertEqual(Profile.objects.values().get(pk=original["id"]), original)
            self.assertEqual(
                Profile.objects.values().get(pk=legacy.pk),
                {**original_legacy, "profile_type": "student"},
            )
        finally:
            MigrationExecutor(connection).migrate(self.new_target)

    def test_rollback_and_reapplication_preserve_subsequent_profile_edits(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.categories_target)
        try:
            old_apps = executor.loader.project_state(self.categories_target).apps
            User = old_apps.get_model("accounts", "CustomUser")
            Profile = old_apps.get_model("accounts", "Profile")
            profile = Profile.objects.create(
                user=User.objects.create(username="legacy_edited"), matric_no="CSC/21/0004"
            )
            MigrationExecutor(connection).migrate(self.new_target)
            Profile.objects.filter(pk=profile.pk).update(level=500)

            MigrationExecutor(connection).migrate(self.categories_target)
            profile.refresh_from_db()
            self.assertEqual(profile.profile_type, "student")
            self.assertEqual(profile.level, 500)

            MigrationExecutor(connection).migrate(self.new_target)
            profile.refresh_from_db()
            self.assertEqual(profile.profile_type, "student")
            self.assertEqual(profile.level, 500)
        finally:
            MigrationExecutor(connection).migrate(self.new_target)
