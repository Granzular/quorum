from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from accounts.activation import activation_credentials
from accounts.models import CustomUser, Profile


class ProvisionUserForm(forms.ModelForm):
    """Administrators provision identity; the user supplies a password on activation."""

    class Meta:
        model = CustomUser
        fields = ("username", "email", "first_name", "last_name", "phone")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False
        user.set_unusable_password()
        if commit:
            user.save()
            self.save_m2m()
        return user


class ProfileInline(admin.StackedInline):
    model = Profile
    min_num = 1
    max_num = 1
    extra = 0
    can_delete = False

    def get_formset(self, request, obj=None, **kwargs):
        kwargs["validate_min"] = True
        return super().get_formset(request, obj, **kwargs)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    add_form = ProvisionUserForm
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ProvisionUserForm.Meta.fields}),
    )
    fieldsets = UserAdmin.fieldsets + (("Contact", {"fields": ("phone",)}),)
    actions = ["issue_activation_credentials"]

    def has_add_permission(self, request):
        return (
            super().has_add_permission(request)
            and request.user.has_perm("accounts.add_profile")
        )

    def get_inlines(self, request, obj):
        # Existing accounts manage profiles separately from account permissions.
        return [ProfileInline] if obj is None else []

    def show_activation_credentials(self, request, user):
        credentials = activation_credentials(user)
        self.message_user(
            request,
            f"Share privately with {user.username}: activation uid "
            f"{credentials['uid']}, token {credentials['token']}.",
            level=messages.SUCCESS,
        )

    def response_add(self, request, obj, post_url_continue=None):
        self.show_activation_credentials(request, obj)
        return super().response_add(request, obj, post_url_continue)

    @admin.action(
        description="Issue activation credentials for pending accounts", permissions=["change"]
    )
    def issue_activation_credentials(self, request, queryset):
        for user in queryset:
            if not user.is_active and not user.has_usable_password():
                self.show_activation_credentials(request, user)
            else:
                self.message_user(
                    request, f"{user.username} is not awaiting activation.",
                    level=messages.WARNING,
                )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "profile_type", "level", "graduation_year", "job_title")
    list_filter = ("profile_type", "level")
    search_fields = ("user__username", "matric_no")
