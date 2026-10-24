from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ProfileMigrationTests(TransactionTestCase):
    old_target = [("accounts", "0007_alter_profile_user")]
    new_target = [("accounts", "0008_profile_categories")]

    def test_existing_profiles_are_preserved_without_invented_categories_or_levels(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.old_target)
        try:
            old_apps = executor.loader.project_state(self.old_target).apps
            User = old_apps.get_model("accounts", "CustomUser")
            Profile = old_apps.get_model("accounts", "Profile")
            user = User.objects.create(username="legacy_member", password="!")
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
            self.assertIsNone(migrated.profile_type)
            self.assertIsNone(migrated.level)
            self.assertIsNone(migrated.graduation_year)
            self.assertEqual(migrated.job_title, "")
            self.assertEqual(migrated.bio, "")
            self.assertEqual(migrated.linkedin_url, "")
            self.assertEqual(new_apps.get_model("accounts", "Profile").objects.count(), 1)
        finally:
            MigrationExecutor(connection).migrate(self.new_target)
