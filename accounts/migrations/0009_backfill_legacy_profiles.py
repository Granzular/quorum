from django.db import migrations, models


def backfill_legacy_profiles(apps, schema_editor):
    """Classify legacy profiles as students, defaulting missing levels to 300."""
    Profile = apps.get_model("accounts", "Profile")
    legacy_profiles = Profile.objects.using(schema_editor.connection.alias).filter(
        profile_type__isnull=True
    )
    legacy_profiles.filter(level__isnull=True).update(level=300)
    legacy_profiles.update(profile_type="student")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_profile_categories"),
    ]

    operations = [
        # These values also fit the 0008 schema; rollback must retain them
        # because migrated defaults cannot be distinguished from later edits.
        migrations.RunPython(backfill_legacy_profiles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="profile",
            name="profile_type",
            field=models.CharField(
                choices=[("student", "Student"), ("alumni", "Alumni"), ("staff", "Staff")],
                max_length=7,
            ),
        ),
    ]
