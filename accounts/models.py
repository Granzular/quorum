from django.contrib.auth.models import AbstractUser, UserManager
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, router

from main.media_cleanup import FileCleanupQuerySet, delete_with_file_cleanup, save_with_file_cleanup


class CustomUserManager(UserManager.from_queryset(FileCleanupQuerySet)):
    """Preserve user provisioning and cover deletion of file-owning dependants."""


validate_matric_no = RegexValidator(
    regex=r"\A(?:CSC/\d{2}/\d{4}|\d{12}[A-Za-z]{2})\Z",
    message="This field does not satisfy the pattern CSC/00/0000 or 202412345678AB",
)


class CustomUser(AbstractUser):
    objects = CustomUserManager()

    phone = models.CharField(max_length = 20, blank = True, null = True)

    def delete(self, using=None, keep_parents=False):
        using = using or router.db_for_write(type(self), instance=self)
        return delete_with_file_cleanup(
            self, super().delete, using=using, keep_parents=keep_parents,
        )


class Profile(models.Model):
    objects = models.Manager.from_queryset(FileCleanupQuerySet)()

    class Type(models.TextChoices):
        STUDENT = "student", "Student"
        ALUMNI = "alumni", "Alumni"
        STAFF = "staff", "Staff"

    class Level(models.IntegerChoices):
        LEVEL_100 = 100, "100"
        LEVEL_200 = 200, "200"
        LEVEL_300 = 300, "300"
        LEVEL_400 = 400, "400"
        LEVEL_500 = 500, "500"

    CATEGORY_FIELDS = ("matric_no", "level", "graduation_year", "job_title")
    TYPE_FIELDS = {
        Type.STUDENT: ("matric_no", "level"),
        Type.ALUMNI: ("matric_no", "graduation_year"),
        Type.STAFF: ("job_title",),
    }

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="profile"
    )
    profile_type = models.CharField(max_length=7, choices=Type.choices)
    avatar = models.ImageField(
        upload_to=settings.MEDIA_UPLOAD_FOLDERS['accounts']['avatars'], null=True, blank=True,
    )
    matric_no = models.CharField(
        unique=True, max_length=14, null=True, blank=True,
        validators=[validate_matric_no],
    )
    level = models.PositiveSmallIntegerField(
        choices=Level.choices, null=True, blank=True
    )
    graduation_year = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
    )
    job_title = models.CharField(max_length=128, blank=True)
    dept = models.CharField(max_length=64, default="Computer Science")
    bio = models.TextField(blank=True)
    linkedin_url = models.URLField(blank=True)

    def save(self, **kwargs):
        """Clean up replaced or cleared avatars after their reference commits."""
        return save_with_file_cleanup(self, super().save, **kwargs)

    def delete(self, using=None, keep_parents=False):
        using = using or router.db_for_write(type(self), instance=self)
        return delete_with_file_cleanup(
            self, super().delete, using=using, keep_parents=keep_parents,
        )

    def clean(self):
        """Validate the category's required fields and reject other stored values."""
        super().clean()
        if self.matric_no == "":
            self.matric_no = None
        if self.profile_type not in self.TYPE_FIELDS:
            raise ValidationError({"profile_type": "Select a valid profile type."})

        errors = {}
        applicable = self.TYPE_FIELDS[self.profile_type]
        for field in self.CATEGORY_FIELDS:
            value = getattr(self, field)
            empty = value is None or (isinstance(value, str) and not value.strip())
            if field in applicable and empty:
                errors[field] = f"This field is required for {self.profile_type} profiles."
            elif field not in applicable and not empty:
                errors[field] = f"This field is not applicable to {self.profile_type} profiles."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Profile of  {self.user.username}"
